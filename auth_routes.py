# auth_routes.py — login + change-password (bcrypt)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
import bcrypt

auth_router = APIRouter(prefix="/auth", tags=["auth"])

class LoginIn(BaseModel):
    email: EmailStr
    password: str

def _get_hash(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT password_hash FROM mediadores WHERE email=LOWER(%s)", (email,))
            row = cur.fetchone()
            return row[0] if row else None

@auth_router.post("/login")
def login(body: LoginIn):
    email = body.email.lower().strip()
    stored = _get_hash(email)
    if not stored or not bcrypt.checkpw(body.password.encode("utf-8"), stored.encode("utf-8")):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    return {"ok": True}

class ChangeIn(BaseModel):
    email: EmailStr
    old_password: str
    new_password: str

@auth_router.post("/change-password")
def change_password(body: ChangeIn):
    email = body.email.lower().strip()
    stored = _get_hash(email)
    if not stored:
        raise HTTPException(404, "Usuario no encontrado")
    if not bcrypt.checkpw(body.old_password.encode("utf-8"), stored.encode("utf-8")):
        raise HTTPException(401, "Contraseña actual incorrecta")
    new_hash = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt()).decode()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("UPDATE mediadores SET password_hash=%s WHERE email=LOWER(%s)", (new_hash, email))
        cx.commit()
    return {"msg": "Contraseña actualizada"}
