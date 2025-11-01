# mediadores_routes.py — alta + directorio + suscripción
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlite3 import Row
from utils import db, sha256, now_iso, send_mail

mediadores_router = APIRouter()

def _cols() -> List[str]:
    con = db()
    con.row_factory = None
    cur = con.execute("PRAGMA table_info(mediadores)")
    res = [r[1] for r in cur.fetchall()]
    con.close()
    return res

def _norm(v: Any) -> str:
    if v is None: return ""
    if isinstance(v, list): return v[0] if v else ""
    return str(v)

@mediadores_router.post("/mediadores/register")
async def mediador_register(request: Request):
    ctype = (request.headers.get("content-type") or "").lower()
    try:
        raw = await request.json() if ctype.startswith("application/json") else dict(await request.form())
    except Exception:
        raise HTTPException(400, "Cuerpo inválido")

    name  = _norm(raw.get("name") or raw.get("nombre")).strip()
    email = _norm(raw.get("email")).strip().lower()
    telefono = _norm(raw.get("telefono") or raw.get("phone")).strip()
    bio = _norm(raw.get("bio")).strip()
    provincia = _norm(raw.get("provincia")).strip()
    especialidad = _norm(raw.get("especialidad")).strip()
    web = _norm(raw.get("web")).strip()
    linkedin = _norm(raw.get("linkedin")).strip()

    if not name or not email:
        raise HTTPException(422, "Faltan nombre o email")

    candidate = {
        "name": name,
        "email": email,
        "password_hash": sha256(email),
        "status": "pending",
        "created_at": now_iso(),
        "telefono": telefono,
        "bio": bio,
        "provincia": provincia,
        "especialidad": especialidad,
        "web": web,
        "linkedin": linkedin,
        "photo_url": "",
        "cv_url": "",
        "is_subscriber": 0,
        "subscription_status": "",
        "is_trial": 0,
        "trial_expires_at": "",
    }
    cols = _cols()
    ins_cols = [c for c in candidate.keys() if c in cols]
    values = [candidate[c] for c in ins_cols]

    con = db()
    try:
        con.execute(f"INSERT INTO mediadores ({', '.join(ins_cols)}) VALUES ({','.join(['?']*len(values))})", tuple(values))
        con.commit()
    except Exception as e:
        con.rollback()
        raise HTTPException(400, f"No se pudo registrar: {e}")
    finally:
        con.close()

    # notifica
    try:
        send_mail(
            "MEDIAZION · Alta recibida",
            f"Hola {name}, hemos recibido tu alta. Te avisaremos al aprobarla.\n\nEquipo MEDIAZION",
            to=email
        )
        send_mail(
            "Nueva alta de mediador",
            f"Nombre: {name}\nEmail: {email}\nProvincia: {provincia}\nEspecialidad: {especialidad}",
            to=os.getenv("MAIL_TO", "info@mediazion.eu")
        )
    except Exception:
        pass

    return {"ok": True, "message": "Alta registrada. Revisa tu correo. Ya puedes activar tu prueba gratuita."}

@mediadores_router.get("/mediadores/public")
def mediadores_public(q: Optional[str] = None, provincia: Optional[str] = None, especialidad: Optional[str] = None):
    con = db()
    con.row_factory = Row
    sql = "SELECT id,name,provincia,especialidad,bio,photo_url,cv_url FROM mediadores WHERE status='approved'"
    params: List[Any] = []
    if q:
        sql += " AND name LIKE ?"; params.append(f"%{q}%")
    if provincia:
        sql += " AND provincia LIKE ?"; params.append(f"%{provincia}%")
    if especialidad:
        sql += " AND especialidad LIKE ?"; params.append(f"%{especialidad}%")
    sql += " ORDER BY id DESC"
    rows = con.execute(sql, tuple(params)).fetchall()
    con.close()
    return [dict(r) for r in rows]

# Suscripción Stripe (trial 7 días)
class SubscribeIn(BaseModel):
    email: EmailStr
    priceId: Optional[str] = None

import stripe as _stripe

def _stripe_client():
    key = os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(500, "STRIPE_SECRET no configurada")
    _stripe.api_key = key
    return _stripe

@mediadores_router.post("/subscribe")
def subscribe(body: SubscribeIn):
    con = db()
    row = con.execute("SELECT id,status FROM mediadores WHERE email=?", (body.email.lower(),)).fetchone()
    con.close()
    if not row:
        raise HTTPException(400, "Antes debes completar el alta de mediador.")
    price = body.priceId or os.getenv("STRIPE_PRICE_ID")
    if not price:
        raise HTTPException(400, "Falta STRIPE_PRICE_ID")

    cli = _stripe_client()
    try:
        session = cli.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price, "quantity": 1}],
            customer_email=body.email,
            subscription_data={"trial_period_days": 7},
            allow_promotion_codes=True,
            success_url="https://mediazion.eu/suscripcion/ok",
            cancel_url="https://mediazion.eu/suscripcion/cancel",
        )
        return {"ok": True, "url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")
