# instituciones_actas_routes.py — Actas institucionales vinculadas a casos
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from db import pg_conn

router = APIRouter(prefix="/api/instituciones", tags=["instituciones-actas"])

class ActaIn(BaseModel):
    contenido: str

class Acta(BaseModel):
    id: int
    caso_id: int
    contenido: str
    fecha: str

SQL_CREATE_ACTAS = """
CREATE TABLE IF NOT EXISTS actas_institucion (
  id SERIAL PRIMARY KEY,
  caso_id INTEGER NOT NULL REFERENCES casos_institucion(id) ON DELETE CASCADE,
  institucion_email TEXT NOT NULL,
  contenido TEXT NOT NULL,
  fecha TIMESTAMP DEFAULT NOW()
);
"""

def _ensure_actas_table():
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(SQL_CREATE_ACTAS)
        cx.commit()

@router.get("/casos/{caso_id}/actas", response_model=List[Acta])
def listar_actas(caso_id: int):
    _ensure_actas_table()
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, caso_id, contenido, fecha
                      FROM actas_institucion
                     WHERE caso_id = %s
                     ORDER BY fecha DESC, id DESC
                    """,
                    (caso_id,),
                )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(500, f"Error listando actas: {e}")

    actas: list[Acta] = []
    for aid, cid, contenido, fecha in rows:
        actas.append(
            Acta(
                id=aid,
                caso_id=cid,
                contenido=contenido,
                fecha=fecha.isoformat() if fecha else "",
            )
        )
    return actas

@router.post("/casos/{caso_id}/actas", response_model=Acta)
def crear_acta(caso_id: int, body: ActaIn):
    _ensure_actas_table()
    contenido = (body.contenido or "").strip()
    if not contenido:
        raise HTTPException(400, "El contenido del acta no puede estar vacío.")

    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    "SELECT institucion_email FROM casos_institucion WHERE id = %s",
                    (caso_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(404, "Caso no encontrado.")
                institucion_email = row[0]

                cur.execute(
                    """
                    INSERT INTO actas_institucion (caso_id, institucion_email, contenido)
                    VALUES (%s, %s, %s)
                    RETURNING id, fecha
                    """,
                    (caso_id, institucion_email, contenido),
                )
                aid, fecha = cur.fetchone()
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error creando acta: {e}")

    return Acta(
        id=aid,
        caso_id=caso_id,
        contenido=contenido,
        fecha=fecha.isoformat() if fecha else "",
    )
