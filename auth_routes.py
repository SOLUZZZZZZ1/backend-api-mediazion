# auth_routes.py — login + cambio de contraseña (bcrypt)
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr
from db import pg_conn
import bcrypt, secrets, os

auth_router = APIRouter(prefix="/auth", tags=["auth"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@auth_router.post("/login")
def login(body: LoginIn):
    email = body.email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT password_hash FROM mediadores WHERE email=LOWER(%s)", (email,))
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(401, "Usuario o contraseña incorrectos")
            if not bcrypt.checkpw(body.password.encode("utf-8"), row[0].encode("utf-8")):
                raise HTTPException(401, "Usuario o contraseña incorrectos")
    token = secrets.token_urlsafe(24)  # placeholder hasta implementar sesiones/JWT
    return {"ok": True, "token": token}

class ChangePasswordIn(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str

@auth_router.post("/change_password")
def change_password(body: ChangePasswordIn):
    email = body.email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT password_hash FROM mediadores WHERE email=LOWER(%s)", (email,))
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(404, "Usuario no encontrado")
            if not bcrypt.checkpw(body.current_password.encode("utf-8"), row[0].encode("utf-8")):
                raise HTTPException(401, "Contraseña actual incorrecta")
            new_hash = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt()).decode()
            cur.execute("UPDATE mediadores SET password_hash=%s WHERE email=LOWER(%s)", (new_hash, email))
            cx.commit()
    return {"ok": True, "message": "Contraseña actualizada correctamente"}
