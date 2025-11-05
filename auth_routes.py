# auth_routes.py — login básico para el Panel de Mediador
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
import bcrypt, secrets

auth_router = APIRouter(prefix="/auth", tags=["auth"])

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@auth_router.post("/login")
def login(data: LoginIn):
    email = data.email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT password_hash FROM mediadores WHERE email = LOWER(%s)", (email,))
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(401, "Usuario o contraseña incorrectos")
            pwd_ok = bcrypt.checkpw(data.password.encode("utf-8"), row[0].encode("utf-8"))
            if not pwd_ok:
                raise HTTPException(401, "Usuario o contraseña incorrectos")
    # Devuelve token simple (a futuro JWT)
    token = secrets.token_urlsafe(24)
    return {"ok": True, "token": token}
