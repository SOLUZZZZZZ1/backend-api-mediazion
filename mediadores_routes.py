# mediadores_routes.py — versión PostgreSQL
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr
from typing import Optional
from db import pg_conn

mediadores_router = APIRouter()

class AltaIn(BaseModel):
    name: str
    email: EmailStr
    especialidad: Optional[str] = None
    provincia: Optional[str] = None

@mediadores_router.post("/mediadores/register")
def alta_mediador(data: AltaIn):
    """Alta / reactivación de mediador. Se marca approved=true y status=active."""
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mediadores (name, email, especialidad, provincia, approved, status, subscription_status, trial_used)
                VALUES (%s, LOWER(%s), %s, %s, TRUE, 'active', 'none', FALSE)
                ON CONFLICT (email) DO UPDATE SET
                    name = EXCLUDED.name,
                    especialidad = EXCLUDED.especialidad,
                    provincia = EXCLUDED.provincia,
                    approved = TRUE,
                    status = 'active'
                """,
                (data.name, data.email, data.especialidad or None, data.provincia or None),
            )
            cx.commit()
    return {"ok": True, "message": "Alta registrada. Revisa tu correo. Ya puedes activar tu prueba gratuita."}

@mediadores_router.post("/mediadores/disable/{mediador_id}")
def disable_mediador(mediador_id: int):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("UPDATE mediadores SET status='disabled', approved=FALSE WHERE id=%s", (mediador_id,))
            cx.commit()
    return {"ok": True}

@mediadores_router.get("/mediadores/public")
def listar_mediadores(
    limit: int = Query(50, ge=1, le=200),
    provincia: Optional[str] = Query(None),
    especialidad: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
):
    filtros = ["approved = TRUE", "status = 'active'"]
    params = []
    if provincia:
        filtros.append("LOWER(provincia) = LOWER(%s)"); params.append(provincia)
    if especialidad:
        filtros.append("LOWER(especialidad) = LOWER(%s)"); params.append(especialidad)
    if q:
        like = f"%{q.lower()}%"
        filtros.append("(LOWER(name) LIKE %s OR LOWER(email) LIKE %s OR LOWER(provincia) LIKE %s OR LOWER(especialidad) LIKE %s)")
        params.extend([like, like, like, like])

    sql = f"""
        SELECT id, name, email, especialidad, provincia, created_at
          FROM mediadores
         WHERE {' AND '.join(filtros)}
         LIMIT %s
    """
    params.append(limit)
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return rows
