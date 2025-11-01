# mediadores_routes.py — Alta auto-aprobada + listado público
import os, sqlite3
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

mediadores_router = APIRouter()
DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def _cx():
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    return cx

class AltaIn(BaseModel):
    name: str
    email: EmailStr
    especialidad: Optional[str] = None
    provincia: Optional[str] = None

@mediadores_router.post("/mediadores/register")
def alta(data: AltaIn):
    # Alta auto-aprobada; si existe, lo reactivamos
    with _cx() as cx:
        try:
            cx.execute(
                "INSERT INTO mediadores (name,email,especialidad,provincia,approved,status,subscription_status,trial_used) "
                "VALUES (?,?,?,?,1,'active','none',0)",
                (data.name, data.email.lower(), data.especialidad, data.provincia)
            )
            cx.commit()
        except sqlite3.IntegrityError:
            cx.execute(
                "UPDATE mediadores SET approved=1,status='active' WHERE lower(email)=lower(?)",
                (data.email.lower(),)
            )
            cx.commit()
    return {"ok": True, "message": "Alta registrada. Revisa tu correo. Ya puedes activar tu prueba gratuita."}

@mediadores_router.get("/mediadores/public")
def public_list(
    limit: int = Query(50, ge=1, le=200),
    provincia: Optional[str]=Query(None),
    especialidad: Optional[str]=Query(None),
    q: Optional[str]=Query(None)
):
    where = ["approved=1","status='active'"]
    params: list = []
    if provincia:
        where.append("lower(provincia)=lower(?)"); params.append(provincia)
    if especialidad:
        where.append("lower(especialidad)=lower(?)"); params.append(especialidad)
    if q:
        where.append("(lower(name) LIKE ? OR lower(email) LIKE ? OR lower(provincia) LIKE ? OR lower(especialidad) LIKE ?)")
        params += [f"%{q.lower()}%"]*4
    sql = ("SELECT id,name,email,especialidad,provincia,created_at "
           "FROM mediadores WHERE " + " AND ".join(where) +
           " ORDER BY id DESC LIMIT ?")
    params.append(limit)
    with _cx() as cx:
        cur = cx.execute(sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]
