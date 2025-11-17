# agenda_routes.py — Agenda profesional Mediazion
# ------------------------------------------------
# Estilo Mediazion: PostgreSQL directo (pg_conn), sin ORM.

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr
from db import pg_conn
from datetime import datetime

agenda_router = APIRouter(prefix="/agenda")


# ----------------- MODELOS -----------------

class AgendaCreate(BaseModel):
    email: EmailStr
    titulo: str
    descripcion: str | None = None
    fecha: datetime
    tipo: str  # cita | recordatorio | videollamada
    caso_id: int | None = None


# ----------------- ENDPOINTS -----------------

@agenda_router.get("")
def listar_agenda(email: EmailStr = Query(...)):
    """
    Lista todos los eventos de agenda del mediador.
    """
    email_norm = email.lower()

    SQL = """
        SELECT id, mediador_email, titulo, descripcion, fecha, tipo, caso_id, created_at
          FROM agenda
         WHERE LOWER(mediador_email)=LOWER(%s)
         ORDER BY fecha ASC;
    """

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(SQL, (email_norm,))
            rows = cur.fetchall() or []
    except Exception as e:
        raise HTTPException(500, f"Error listando agenda: {e}")

    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "email": r[1],
            "titulo": r[2],
            "descripcion": r[3],
            "fecha": r[4].isoformat(),
            "tipo": r[5],
            "caso_id": r[6],
            "created_at": r[7].isoformat(),
        })

    return {"ok": True, "items": result}


@agenda_router.post("")
def crear_evento(body: AgendaCreate):
    """
    Crea un evento de agenda.
    """
    email = body.email.lower()
    tipo = body.tipo.lower()

    if tipo not in ("cita", "recordatorio", "videollamada"):
        raise HTTPException(400, "Tipo inválido de evento.")

    SQL = """
        INSERT INTO agenda (mediador_email, titulo, descripcion, fecha, tipo, caso_id)
        VALUES (LOWER(%s), %s, %s, %s, %s, %s)
        RETURNING id;
    """

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(SQL, (
                email,
                body.titulo.strip(),
                body.descripcion,
                body.fecha,
                tipo,
                body.caso_id
            ))
            row = cur.fetchone()
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error creando evento: {e}")

    return {"ok": True, "id": row[0]}
