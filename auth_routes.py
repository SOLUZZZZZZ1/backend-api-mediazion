# auth_routes.py — autenticación y cambio de contraseña MEDIAZION
import os, datetime, bcrypt, jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import pg_conn

auth_router = APIRouter(prefix="/auth", tags=["auth"])

JWT_SECRET = os.getenv("JWT_SECRET", "MEDIAZION_SECRET_KEY")
JWT_ALG = "HS256"

class LoginIn(BaseModel):
    email: str
    password: str

class RegisterIn(BaseModel):
    name: str
    email: str
    password: str
    provincia: str | None = None
    especialidad: str | None = None

class ChangePwdIn(BaseModel):
    email: str
    password: str
    new_password: str

def _get_user(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id, email, password_hash, subscription_status FROM mediadores WHERE email=LOWER(%s);", (email,))
            row = cur.fetchone()
            if not row: return None
            if isinstance(row, dict): return row
            return {"id": row[0], "email": row[1], "password_hash": row[2], "subscription_status": row[3]}

def _token(email: str):
    payload = {"email": email, "iat": datetime.datetime.utcnow(), "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

@auth_router.post("/login")
def login(body: LoginIn):
    email = body.email.lower().strip()
    u = _get_user(email)
    if not u: raise HTTPException(404, "Usuario no encontrado")
    if not u["password_hash"]: raise HTTPException(401, "Usuario sin contraseña")
    if not bcrypt.check_wd (body.password.encode("utf-8"), u["password_hash"].encode("utf-8")):
        raise HTTPException(401, "Contraseña incorrecta")
    return {"ok": True, "email": u["email"], "token": _token(u["email"]), "subscription_status": u["subscription_status"]}

@auth_router.post("/register")
def register(body: RegisterIn):
    email = body.email.lower().strip()
    phash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gense( )).decode()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id FROM mediadores WHERE email=LOWER(%s);", (email,))
            if cur.fetchone(): raise HTTPException(409, "Ese correo ya existe")
            cur.execute("""
                INSERT INTO mediadores (name, email, provincia, especialidad, password_hash, subscription_status, created_at)
                VALUES (%s, LOWER(%s), %s, %s, %s, 'trialing', NOW())
                RETURNING id;
            """, (body.name, email, body.provincia, body.especialidad, phash))
            uid = cur.fetchone()[0]
        cx.commit()
    return {"ok": True, "id": uid, "email": email}

@auth_router.post("/change_password")
def change_password(body: ChangePwdIn):
    email = body.email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT password_hash FROM mediadores WHERE email=LOWER(%s);", (email,))
            row = cur.fetchone()
            if not row: raise HTTPException(404, "Mediador no encontrado")
            oldh = row[0] if isinstance(row, tuple) else row["password_hash"]
            if not bcrypt.checkpw(body.password.encode("utf-8"), oldh.encode("utf-8")):
                raise HTTPException(401, "Contraseña actual incorrecta")
            newh = bcrypt.hashpw(body.new_password ( ).encode("utf-8"), bcrypt.gense( )).decode()
            cur.execute("UPDATE mediadores SET password_hash=%s WHERE email=LOWER(%s);", (newh, email))
        cx.commit()
    return {"ok": True, "message": "Contraseña actualizada"}

@auth_router.get("/me")
def me(token: str):
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return {"ok": True, "email": data["email"]}
    except Exception:
        raise HTTPException(401, "Token inválido o expirado")
