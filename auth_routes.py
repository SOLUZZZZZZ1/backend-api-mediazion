# auth_routes.py — autenticación y cambio de contraseña MEDIAZION
import bcrypt
import datetime
import jwt
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import pg_conn

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# =============================
# CONFIG
# =============================
JWT_SECRET = os.getenv("JWT_SECRET", "MEDIAZION_SECRET_KEY")
JWT_ALG = "HS256"


# =============================
# MODELOS
# =============================
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
    old_password: str
    new_password: str


# =============================
# FUNCIONES AUXILIARES
# =============================
def _row_to_dict(cur, row):
    if not row: return None
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}

def _get_mediador(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id, email, password_hash, subscription_status FROM mediadores WHERE email=LOWER(%s)", (email,))
            return _row_to_dict(cur, cur.fetchone())

def _create_token(email: str):
    payload = {
        "email": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7),
        "iat": datetime.datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


# =============================
# ENDPOINTS
# =============================

# ---- LOGIN ----
@auth_router.post("/login")
def login(body: LoginIn):
    m = _get_mediador(body.email.lower().strip())
    if not m:
        raise HTTPException(404, "Usuario no encontrado")
    if not m.get("password_hash"):
        raise HTTPException(401, "Usuario sin contraseña asignada")

    if not bcrypt.checkpw(body.password.encode("utf-8"), m["password_hash"].encode("utf-8")):
        raise HTTPException(401, "Contraseña incorrecta")

    token = _create_token(m["email"])
    return {
        "ok": True,
        "token": token,
        "email": m["email"],
        "subscription_status": m["subscription_status"]
    }


# ---- REGISTRO ----
@auth_router.post("/register")
def register(body: RegisterIn):
    email = body.email.lower().strip()
    pwd_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode()

    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id FROM mediadores WHERE email=LOWER(%s)", (email,))
            if cur.fetchone():
                raise HTTPException(409, "Este correo ya está registrado")

            cur.execute("""
                INSERT INTO mediadores (name, email, provincia, especialidad, password_hash, subscription_status)
                VALUES (%s, LOWER(%s), %s, %s, %s, 'trialing')
                RETURNING id;
            """, (body.name, email, body.provincia, body.especialidad, pwd_hash))
            uid = cur.fetchone()[0]
        cx.commit()

    return {"ok": True, "id": uid, "email": email}


# ---- CAMBIO DE CONTRASEÑA ----
@auth_router.post("/change_password")
def change_password(body: ChangePwdIn):
    email = body.email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT password_hash FROM mediadores WHERE email=LOWER(%s)", (email,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Mediador no encontrado")

            old_hash = row[0] if isinstance(row, tuple) else row["password_hash"]
            if not bcrypt.checkpw(body.old_password.encode("utf-8"), old_hash.encode("utf-8")):
                raise HTTPException(401, "Contraseña actual incorrecta")

            new_hash = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt()).decode()
            cur.execute("UPDATE mediadores SET password_hash=%s WHERE email=LOWER(%s)", (new_hash, email))
        cx.commit()

    return {"ok": True, "message": "Contraseña cambiada correctamente"}


# ---- VALIDAR TOKEN ----
@auth_router.get("/me")
def me(token: str):
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return {"ok": True, "email": data["email"]}
    except Exception:
        raise HTTPException(401, "Token inválido o expirado")
