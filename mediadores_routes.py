# mediadores_routes.py — alta + directorio público + suscripción con verificación de alta
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlite3 import Row
from utils import db, sha256
import stripe

mediadores_router = APIRouter()

# ---------- Utilidades internas ----------
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

# ---------- Alta de mediador ----------
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

    name = _normalize_str(raw.get("name") or raw.get("nombre")).strip()
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
        "trial_expires_at": (datetime.utcnow().date().isoformat()),
    }

    cols = _mediadores_columns()
    insert_cols = [c for c in candidate.keys() if c in cols]
    values = [candidate[c] for c in insert_cols]

    placeholders = ",".join(["?"] * len(values))
   
