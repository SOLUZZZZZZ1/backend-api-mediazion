# auth_routes.py — login + change_password + reset_password (admin)
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
    token = secrets.token_urlsafe(24)  # placeholder
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
    return {"ok": True, "message": "Contraseña actualizada"}

class ResetPasswordIn(BaseModel):
    email: EmailStr

@auth_router.post("/reset_password")
def reset_password(body: ResetPasswordIn, x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    email = body.email.lower().strip()
    temp_password = secrets.token_urlsafe(6)[:10]
    new_hash = bcrypt.hashpw(temp_password.encode("utf-8"), bcrypt.gensalt()).decode()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("UPDATE mediadores SET password_hash=%s WHERE email=LOWER(%s)", (new_hash, email))
            if cur.rowcount == 0:
                raise HTTPException(404, "Usuario no encontrado")
            cx.commit()
    # enviar correo (best-effort)
    try:
        from contact_routes import _send_mail
        html = f"<p>Nueva contraseña temporal: <strong>{temp_password}</strong></p>"
        _send_mail(email, "Tu nueva contraseña temporal · MEDIAZION", html, email)
    except Exception:
        pass
    return {"ok": True, "message": "Contraseña temporal generada y enviada"}
