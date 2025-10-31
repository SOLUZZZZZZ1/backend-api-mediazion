# mediadores_routes.py — alta + directorio + suscripción
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from sqlite3 import Row
from utils import db, sha256, now_iso, send_mail

mediadores_router = APIRouter()

def _cols() -> List[str]:
    con = db(); cur = con.execute("PRAGMA table_info(mediadores)")
    cols = [r[1] for r in cur.fetchall()]; con.close()
    return cols

def _norm(v: Any) -> str:
    if v is None: return ""
    return str(v).strip()

@mediadores_router.post("/mediadores/register")
async def mediador_register(request: Request):
    ctype = (request.headers.get("content-type") or "").lower()
    try:
        raw = await request.json() if ctype.startswith("application/json") else dict(await request.form())
    except Exception:
        raise HTTPException(400, "Cuerpo inválido")

    name  = _norm(raw.get("name") or raw.get("nombre"))
    email = _norm(raw.get("email")).lower()
    if not name or not email:
        raise HTTPException(422, "Faltan nombre o email")

    cand: Dict[str, Any] = {
        "name": name,
        "email": email,
        "password_hash": sha256(email),
        "status": "pending",
        "created_at": now_iso(),
        "telefono": _norm(raw.get("telefono")),
        "bio": _norm(raw.get("bio")),
        "provincia": _norm(raw.get("provincia")),
        "especialidad": _norm(raw.get("especialidad")),
        "web": _norm(raw.get("web")),
        "linkedin": _norm(raw.get("linkedin")),
        "photo_url": "",
        "cv_url": "",
        "is_subscriber": 0,
        "subscription_status": "",
        "is_trial": 0,
        "trial_expires_at": ""
    }
    cols = _cols()
    insert_cols = [c for c in cand if c in cols]
    values = [cand[c] for c in insert_cols]

    con = db()
    try:
        placeholders = ",".join(["?"]*len(values))
        sql = f"INSERT INTO mediadores ({', '.join(insert_cols)}) VALUES ({placeholders})"
        con.execute(sql, tuple(values)); con.commit()
    except Exception as e:
        con.rollback()
        raise HTTPException(400, f"No se pudo registrar: {e}")
    finally:
        con.close()

    # emails
    body_user = (
        f"Hola {name},\n\n"
        "Hemos recibido tu alta como mediador en MEDIAZION.\n"
        "En breve revisaremos tus datos. Mientras tanto, puedes activar tu prueba PRO de 7 días desde la web.\n\n"
        "— MEDIAZION"
    )
    try:
        send_mail(email, "Alta recibida · MEDIAZION", body_user)
        send_mail(os.getenv("MAIL_TO","info@mediazion.eu"),
                  "Nueva alta de mediador",
                  f"{name} <{email}>\nProvincia: {cand['provincia']}\nEspecialidad: {cand['especialidad']}")
    except Exception:
        # no bloquea el alta si falla el correo
        pass

    return {"ok": True, "message": "Alta registrada. Revisa tu correo."}

@mediadores_router.get("/mediadores/public")
def mediadores_public(q: Optional[str] = None,
                      provincia: Optional[str] = None,
                      especialidad: Optional[str] = None) -> List[Dict[str, Any]]:
    cols = _cols()
    sel = [c for c in ["id","name","bio","provincia","especialidad","photo_url","cv_url"] if c in cols]
    if not sel: raise HTTPException(500, "Tabla 'mediadores' sin columnas esperadas")
    con = db(); con.row_factory = Row
    sql = f"SELECT {', '.join(sel)} FROM mediadores WHERE status='approved'"
    params: List[Any] = []
    if q and "name" in cols: sql += " AND name LIKE ?"; params.append(f"%{q}%")
    if provincia and "provincia" in cols: sql += " AND provincia LIKE ?"; params.append(f"%{provincia}%")
    if especialidad and "especialidad" in cols: sql += " AND especialidad LIKE ?"; params.append(f"%{especialidad}%")
    sql += " ORDER BY id DESC"
    rows = con.execute(sql, tuple(params)).fetchall()
    con.close()
    # normaliza especialidad string → lista
    out = []
    for r in rows:
        d = dict(r)
        if "especialidad" in d and isinstance(d["especialidad"], str):
            d["especialidad"] = [s.strip() for s in d["especialidad"].split(",") if s.strip()]
        out.append(d)
    return out

# Suscripción Stripe (requiere alta previa)
import stripe as _stripe

def _stripe_client():
    key = os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY")
    if not key: raise HTTPException(500, "STRIPE_SECRET no configurada")
    _stripe.api_key = key
    return _stripe

@mediadores_router.post("/subscribe")
def subscribe(body: Dict[str, str]):
    email = _norm(body.get("email")).lower()
    price = _norm(body.get("priceId") or os.getenv("STRIPE_PRICE_ID"))
    if not email: raise HTTPException(400, "Falta email")
    if not price: raise HTTPException(400, "Falta STRIPE_PRICE_ID")

    con = db()
    row = con.execute("SELECT id FROM mediadores WHERE email=?", (email,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(400, "Antes debes completar el alta de mediador.")

    try:
        cli = _stripe_client()
        session = cli.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price, "quantity": 1}],
            customer_email=email,
            subscription_data={"trial_period_days": 7},
            allow_promotion_codes=True,
            success_url="https://mediazion.eu/suscripcion/ok",
            cancel_url="https://mediazion.eu/suscripcion/cancel"
        )
        return {"ok": True, "url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")
