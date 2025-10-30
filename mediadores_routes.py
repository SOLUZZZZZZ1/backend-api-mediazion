# mediadores_routes.py — alta + directorio público + suscripción con verificación de alta
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlite3 import Row

from utils import db, sha256
import stripe

mediadores_router = APIRouter()

# ------------ utils internas ------------
def _mediadores_columns() -> List[str]:
    con = db()
    cur = con.execute("PRAGMA table_info(mediadores)")
    cols = [r[1] for r in cur.fetchall()]
    con.close()
    return cols

def _now_iso() -> str:
    return datetime.utcnow().isoformat()

def _normalize_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return v[0] if v else ""
    return str(v)

# ------------ Alta de mediador ------------
@mediadores_router.post("/mediadores/register")
async def mediador_register(request: Request):
    ctype = (request.headers.get("content-type") or "").lower()
    try:
        if ctype.startswith("application/json"):
            raw = await request.json()
        else:
            form = await request.form()
            raw = dict(form)
    except Exception:
        raise HTTPException(400, "Cuerpo inválido")

    name  = _normalize_str(raw.get("name") or raw.get("nombre")).strip()
    email = _normalize_str(raw.get("email")).strip().lower()
    if not name or not email:
        raise HTTPException(422, "Faltan nombre o email")

    candidate = {
        "name": name,
        "email": email,
        "password_hash": sha256(email or ""),
        "status": "pending",
        "created_at": _now_iso(),
        "telefono": _normalize_str(raw.get("telefono")).strip(),
        "bio": _normalize_str(raw.get("bio")).strip(),
        "provincia": _normalize_str(raw.get("provincia")).strip(),
        "especialidad": _normalize_str(raw.get("especialidad")).strip(),
        "web": _normalize_str(raw.get("web")).strip(),
        "linkedin": _normalize_str(raw.get("linkedin")).strip(),
        "photo_url": "",
        "cv_url": "",
        "is_subscriber": 0,
        "subscription_status": "",
        "is_trial": 1,
        "trial_expires_at": (datetime.utcnow() + timedelta(days=7)).date().isoformat(),
    }

    cols = _mediadores_columns()
    insert_cols = [c for c in candidate.keys() if c in cols]
    values = [candidate[c] for c in insert_cols]

    placeholders = ",".join(["?"] * len(values))
    sql = f"INSERT INTO mediadores ({', '.join(insert_cols)}) VALUES ({placeholders})"

    con = db()
    try:
        con.execute(sql, tuple(values))
        con.commit()
    except Exception as e:
        con.rollback()
        raise HTTPException(400, f"No se pudo registrar: {e}")
    finally:
        con.close()

    return {"ok": True, "message": "Alta registrada. Revisa tu correo. Ya puedes activar tu prueba gratuita."}

# ------------ Directorio público ------------
@mediadores_router.get("/mediadores/public")
def mediadores_public(q: Optional[str] = None,
                      provincia: Optional[str] = None,
                      especialidad: Optional[str] = None) -> List[Dict[str, Any]]:
    cols = _mediadores_columns()
    con = db()
    con.row_factory = Row
    visible = [c for c in ["id","name","provincia","especialidad","bio"] if c in cols]
    if not visible:
        raise HTTPException(500, "La tabla 'mediadores' no tiene columnas esperadas")
    sql = f"SELECT {', '.join(visible)} FROM mediadores WHERE 1=1"
    params: List[Any] = []
    if q and "name" in cols:
        sql += " AND name LIKE ?"; params.append(f"%{q}%")
    if provincia and "provincia" in cols:
        sql += " AND provincia LIKE ?"; params.append(f"%{provincia}%")
    if especialidad and "especialidad" in cols:
        sql += " AND especialidad LIKE ?"; params.append(f"%{especialidad}%")
    sql += " ORDER BY id DESC"
    rows = con.execute(sql, tuple(params)).fetchall()
    con.close()
    return [dict(r) for r in rows]

# ------------ Suscripción (exige alta previa) ------------
class SubscribeIn(BaseModel):
    email: EmailStr
    priceId: Optional[str] = None

def _stripe_client():
    key = os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(500, "STRIPE_SECRET no configurada")
    stripe.api_key = key
    return stripe

@mediadores_router.post("/subscribe")
def subscribe(body: SubscribeIn):
    con = db()
    row = con.execute("SELECT id FROM mediadores WHERE email=?", (body.email.lower(),)).fetchone()
    con.close()
    if not row:
        raise HTTPException(400, "Antes debes completar el alta de mediador.")

    price = body.priceId or os.getenv("STRIPE_PRICE_ID")
    if not price:
        raise HTTPException(400, "Falta STRIPE_PRICE_ID")

    try:
        cli = _stripe_client()
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
