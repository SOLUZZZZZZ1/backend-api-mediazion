# auth_routes.py — mínimo estable: register / login / change_password (bcrypt correcto)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
import bcrypt

auth_router = APIRouter(prefix="/auth", tags=["auth"])

# ======== INPUT MODELS ========
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ChangePwdIn(BaseModel):
    email: EmailStr
    old_password: str
    new_password: str

# ======== HELPERS ========
def _get_password_hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def _check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# ======== ENDPOINTS ========
@auth_router.post("/register")
def register(body: RegisterIn):
    email = body.email.strip().lower()
    hashed = _get_password_hash(body.password)
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            # si ya existe, devolvemos 409
            cur.execute("SELECT 1 FROM mediadores WHERE LOWER(email)=LOWER(%s);", (email,))
            if cur.fetchone():
                raise HTTPException(409, "Este correo ya está registrado")
            cur.execute("""
                INSERT INTO mediadores (name, email, password_hash, status, subscription_status, created_at)
                VALUES (%s, LOWER(%s), %s, 'active', 'none', NOW());
            """, (body.name.strip(), email, hashed))
            cx.commit()
        return {"ok": True, "message": "Usuario creado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Register error: {e}")

@auth_router.post("/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("SELECT password_hash FROM mediadores WHERE LOWER(email)=LOWER(%s);", (email,))
        row = cur.fetchone()
        if not row or not row[0]:
            raise HTTPException(401, "Usuario o contraseña incorrectos")
        if not _check_password(body.password, row[0]):
            raise HTTPException(401, "Usuario o contraseña incorrectos")
    # El frontend solo necesita ok:true para entrar; si luego usas JWT, cámbialo aquí
    return {"ok": True, "token": "ok"}

@auth_router.post("/change_password")
def change_password(body: ChangePwdIn):
    email = body.email.strip().lower()
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("SELECT password_hash FROM mediadores WHERE LOWER(email)=LOWER(%s);", (email,))
        row = cur.fetchone()
        if not row or not row[0] or not _check_password(body.old_password, row[0]):
            raise HTTPException(401, "Contraseña actual incorrecta")
        new_hash = _get_password_hash(body.new_password)
        cur.execute("UPDATE mediadores SET password_hash=%s WHERE LOWER(email)=LOWER(%s);", (new_hash, email))
        cx.commit()
    return {"ok": True, "message": "Contraseña cambiada."}
