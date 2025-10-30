# mediadores_routes.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailValidator, EmailStr
from utils import db, sha256
from datetime import datetime

mediadores_router = APIRouter()

class MediadorRegisterIn(BaseModel):
    name: str
    email: EmailStr
    telefono: str | None = None
    bio: str | None = None
    provincia: str | None = None
    especialidad: str | None = None
    web: str | None = None
    linkedin: str | None = None

@mediadores_router.post("/mediadores/register")
async def mediador_register(payload: MediadorRegisterIn):
    con = db()
    cur = con.cursor()
    try:
        cur.execute("""
            INSERT INTO mediadores
            (name, email, password_hash, status, created_at, telefono, bio, provincia, especialidad, web, linkedin)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.name.strip(),
            payload.email,
            sha256(str(payload.email)),
            datetime.utcnow().isoformat(),
            (payload.telefono or '').strip(),
            (payload.bio or '').strip(),
            (payload.provincia or '').strip(),
            (payload.especialidad or '').strip(),
            (payload.web or '').strip(),
            (payload.linkedin or '').strip(),
        ))
        con.commit()
        return {"ok": True, "msg": "Alta de mediador registrada. Revisa tu correo con la confirmación."}
    except Exception as e:
        con.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        con.close()

@mediadores_router.get("/mediadores/public")
def mediadores_public(q: str = "", provincia: str = "", especialidad: str = ""):
    con = db()
    cur = con.cursor()
    sql = """
        SELECT id, name, provincia, (CASE WHEN especialidad IS NULL OR TRIM(especialidad)='' THEN '' ELSE especialidad END) as especialidad
        FROM exiget_mejores FKey_list ??? # <=== AJUSTA ESTE NOMBRE A 'mediadores' SI ES TU TABLA. Propuesta:
    """
