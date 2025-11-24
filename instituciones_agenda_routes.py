# instituciones_agenda_routes.py — Agenda institucional vinculada a casos
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from db import pg_conn
from datetime import datetime

router = APIRouter(prefix="/api/instituciones", tags=["instituciones-agenda"])

class EventoIn(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    fecha: str         # ISO string
    tipo: str          # cita | recordatorio | videollamada | otro
    caso_id: Optional[int] = None

class Evento(BaseModel):
    id: int
    institucion_email: str
    titulo: str
    descripcion: Optional[str] = None
    fecha: str
    tipo: str
    caso_id: Optional[int] = None

SQL_CREATE_AGENDA = """
CREATE TABLE IF NOT EXISTS agenda_institucion (
  id SERIAL PRIMARY KEY,
  institucion_email TEXT NOT NULL,
  caso_id INTEGER,
  titulo TEXT NOT NULL,
  descripcion TEXT,
  fecha TIMESTAMP NOT NULL,
  tipo TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  FOREIGN KEY (caso_id) REFERENCES casos_institucion(id) ON DELETE SET NULL
);
"""

def _ensure_agenda_table():
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(SQL_CREATE_AGENDA)
        cx.commit()

@router.get("/agenda", response_model=List[Evento])
def listar_eventos(email: str, caso_id: Optional[int] = None):
    if not email:
        raise HTTPException(400, "Email institucional requerido")

    _ensure_agenda_table()

    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                if caso_id is not None:
                    cur.execute(
                        """
                        SELECT id, institucion_email, titulo, descripcion, fecha, tipo, caso_id
                          FROM agenda_institucion
                         WHERE LOWER(institucion_email) = LOWER(%s)
                           AND caso_id = %s
                         ORDER BY fecha ASC, id ASC
                        """,
                        (email, caso_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, institucion_email, titulo, descripcion, fecha, tipo, caso_id
                          FROM agenda_institucion
                         WHERE LOWER(institucion_email) = LOWER(%s)
                         ORDER BY fecha ASC, id ASC
                        """,
                        (email,),
                    )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(500, f"Error listando agenda: {e}")

    eventos: list[Evento] = []
    for eid, inst_email, titulo, descripcion, fecha, tipo, cid in rows:
        eventos.append(
            Evento(
                id=eid,
                institucion_email=inst_email,
                titulo=titulo,
                descripcion=descripcion,
                fecha=fecha.isoformat() if fecha else "",
                tipo=tipo,
                caso_id=cid,
            )
        )
    return eventos

@router.post("/agenda", response_model=Evento)
def crear_evento(email: str, body: EventoIn):
    institucion_email = (email or "").strip()
    if not institucion_email:
        raise HTTPException(400, "Email institucional requerido")

    titulo = (body.titulo or "").strip()
    if not titulo:
        raise HTTPException(400, "El título es obligatorio.")

    tipo = (body.tipo or "").strip() or "cita"

    try:
        fecha = datetime.fromisoformat(body.fecha)
    except Exception:
        raise HTTPException(400, "Fecha inválida (usa formato ISO).")

    _ensure_agenda_table()

    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agenda_institucion (institucion_email, caso_id, titulo, descripcion, fecha, tipo)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        institucion_email,
                        body.caso_id,
                        titulo,
                        body.descripcion,
                        fecha,
                        tipo,
                    ),
                )
                eid = cur.fetchone()[0]
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error creando evento de agenda: {e}")

    return Evento(
        id=eid,
        institucion_email=institucion_email,
        titulo=titulo,
        descripcion=body.descripcion,
        fecha=fecha.isoformat(),
        tipo=tipo,
        caso_id=body.caso_id,
    )

@router.delete("/agenda/{evento_id}")
def borrar_evento(evento_id: int):
    _ensure_agenda_table()

    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    "DELETE FROM agenda_institucion WHERE id = %s",
                    (evento_id,),
                )
                n = cur.rowcount
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error borrando evento: {e}")

    if n == 0:
        raise HTTPException(404, "Evento no encontrado")

    return {"ok": True, "id": evento_id}
