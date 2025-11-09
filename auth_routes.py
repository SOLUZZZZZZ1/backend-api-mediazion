# auth_routes.py — mínimo viable y estable
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import pg_conn
import bcrypt

auth_router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterIn(BaseModel):
    name: str
    email: str
    password: str

class LoginIn(BaseModel):
    email: str
    password: str

class ChangePwdIn(BaseModel):
    email: str
    old_password: str
    new_password: str

@auth_router.post("/register")
def register(body: RegisterIn):
    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("INSERT INTO mediadores (name, email, password_hash) VALUES (%s,%s,%s);",
                    (body.name, body.email.lower(), hashed))
        cx.commit()
    return {"ok": True, "message": "Usuario creado"}

@auth_router.post("/login")
def login(body: LoginIn):
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("SELECT password_hash FROM mediadores WHERE LOWER(email)=LOWER(%s);", (body.email,))
        row = cur.fetchone()
        if not row or not row[0] or not bcrypt.checkpw(body.password.encode(), row[0].encode()):
            raise HTTPException(401, "Usuario o contraseña incorrectos")
    return {"ok": True, "token": "ok"}  # el Panel solo comprueba ok:true

@auth_router.post("/change_password")
def change_password(body: ChangePwdIn):
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("SELECT password_hash FROM mediadores WHERE LOWER(email)=LOWER(%s);", (body.email,))
        row = cur.fetchone()
        if not row or not row[0] or not bcrypt.checkpw(body.old_password.encode(), row[0].encode()):
            raise HTTPException(401, "Contraseña actual incorrecta")
        new_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
        cur.execute("UPDATE mediadores SET password_hash=%s WHERE LOWER(email)=LOWER(%s);",
                    (new_hash, body.email))
        cx.commit()
    return {"ok": True, "message": "Contraseña cambiada."}
