# agenda_routes.py — Agenda profesional Mediazion (crear + listar + editar + borrar)
# Backend: FastAPI + PostgreSQL directo con db.pg_conn (sin ORM)

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr
from db import pg_conn
from datetime import datetime
from typing import Optional

agenda_router = APIRouter(prefix="/agenda")


# ----------------- MODELOS -----------------

class AgendaCreate(BaseModel):
    email: EmailStr
    titulo: str
    descripcion: Optional[str] = None
    fecha: datetime
    tipo: str  # cita | recordatorio | videollamada
    caso_id: Optional[int] = None


class AgendaUpdate(BaseModel):
    email: EmailStr
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    fecha: Optional[datetime] = None
    tipo: Optional[str] = None
    caso_id: Optional[int] = None


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
            "fecha": r[4].isoformat() if r[4] else None,
            "tipo": r[5],
            "caso_id": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
        })

    return {"ok": True, "items": result}


@agenda_router.post("")
def crear_evento(body: AgendaCreate):
    """
    Crea un evento de agenda.
    """
    email = body.email.lower()
    tipo = (body.tipo or "").lower()

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


@agenda_router.put("/{evento_id}")
def actualizar_evento(evento_id: int, body: AgendaUpdate):
    """
    Edita un evento de agenda (solo si pertenece al mediador).
    """
    email_norm = body.email.lower()

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            # Cargar evento actual
            cur.execute(
                "SELECT id, mediador_email, titulo, descripcion, fecha, tipo, caso_id FROM agenda WHERE id=%s;",
                (evento_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Evento no encontrado.")

            _, mediador_email, titulo, descripcion, fecha, tipo, caso_id = row

            if mediador_email.lower() != email_norm:
                raise HTTPException(403, "No puedes editar un evento que no es tuyo.")

            # Nuevos valores
            new_titulo = body.titulo.strip() if body.titulo is not None else titulo
            new_desc = body.descripcion if body.descripcion is not None else descripcion
            new_fecha = body.fecha if body.fecha is not None else fecha
            new_tipo = (body.tipo or tipo or "").lower()
            if new_tipo not in ("cita", "recordatorio", "videollamada"):
                new_tipo = tipo
            new_caso_id = body.caso_id if body.caso_id is not None else caso_id

            cur.execute(
                """
                UPDATE agenda
                   SET titulo=%s,
                       descripcion=%s,
                       fecha=%s,
                       tipo=%s,
                       caso_id=%s
                 WHERE id=%s;
                """,
                (new_titulo, new_desc, new_fecha, new_tipo, new_caso_id, evento_id),
            )
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error editando evento: {e}")

    return {"ok": True, "id": evento_id}


@agenda_router.delete("/{evento_id}")
def borrar_evento(evento_id: int, email: EmailStr = Query(...)):
    """
    Borra un evento de agenda (solo si pertenece al mediador).
    """
    email_norm = email.lower()

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                "SELECT id, mediador_email FROM agenda WHERE id=%s;",
                (evento_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Evento no encontrado.")

            _, mediador_email = row
            if mediador_email.lower() != email_norm:
                raise HTTPException(403, "No puedes borrar un evento que no es tuyo.")

            cur.execute("DELETE FROM agenda WHERE id=%s;", (evento_id,))
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error borrando evento: {e}")

    return {"ok": True, "deleted": evento_id}
