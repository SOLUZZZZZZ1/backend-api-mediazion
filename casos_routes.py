# casos_routes.py — Gestor de casos/expedientes para mediadores PRO (PostgreSQL + pg_conn)
#
# Endpoints expuestos (una vez incluido en app.py con prefix="/api"):
#
#   GET    /api/casos?email=...          → listar casos del mediador
#   POST   /api/casos                    → crear caso nuevo
#   GET    /api/casos/{caso_id}?email=   → detalle (propietario)
#   PUT    /api/casos/{caso_id}          → actualizar caso (propietario)
#   DELETE /api/casos/{caso_id}?email=   → eliminar caso (propietario)
#
# Diseño:
#   - Sin SQLAlchemy, solo PostgreSQL directo usando db.pg_conn().
#   - Identificación por email (igual que voces, mediadores, perfil).
#   - Tabla "casos" se crea automáticamente si no existe.

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr

from db import pg_conn  # mismo helper que usas en auth_routes / migrate_routes

casos_router = APIRouter(prefix="/casos", tags=["casos"])


# ----------------- SQL: creación de tabla (idempotente) -----------------

SQL_CREATE_CASOS = """
CREATE TABLE IF NOT EXISTS casos (
  id SERIAL PRIMARY KEY,
  mediador_email  TEXT NOT NULL,
  titulo          TEXT NOT NULL,
  descripcion     TEXT,
  estado          TEXT NOT NULL DEFAULT 'abierto',   -- abierto | en_curso | cerrado
  archivos        JSONB,
  fecha_inicio    TIMESTAMP DEFAULT NOW(),
  fecha_cierre    TIMESTAMP NULL,
  created_at      TIMESTAMP DEFAULT NOW(),
  updated_at      TIMESTAMP DEFAULT NOW()
);
"""


def _ensure_table(cur) -> None:
    """Crea la tabla 'casos' si aún no existe (idempotente)."""
    cur.execute(SQL_CREATE_CASOS)


# ----------------- Esquemas Pydantic -----------------

class CasoCreate(BaseModel):
    email: EmailStr
    titulo: str
    descripcion: Optional[str] = None
    estado: Optional[str] = "abierto"


class CasoUpdate(BaseModel):
    email: EmailStr
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[str] = None


class CasoOut(BaseModel):
    id: int
    mediador_email: EmailStr
    titulo: str
    descripcion: Optional[str]
    estado: str
    fecha_inicio: Optional[datetime]
    fecha_cierre: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True


# ----------------- Helpers de acceso -----------------

def _row_to_dict(row) -> dict:
    """
    Convierte una fila devuelta por psycopg/psycopg2 en un dict.
    Funciona tanto si row es dict como si es tupla (SELECT con columnas en orden fijo).
    """
    if row is None:
        return {}

    # Si es dict (psycopg3 con row_factory=dict_row)
    if isinstance(row, dict):
        return row

    # Si es tupla, usamos el orden definido en los SELECT de abajo.
    # SELECT id, mediador_email, titulo, descripcion, estado,
    #        fecha_inicio, fecha_cierre, created_at, updated_at
    return {
        "id": row[0],
        "mediador_email": row[1],
        "titulo": row[2],
        "descripcion": row[3],
        "estado": row[4],
        "fecha_inicio": row[5],
        "fecha_cierre": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


# ----------------- ENDPOINTS -----------------

@casos_router.get("", response_model=List[CasoOut])
def listar_casos(email: EmailStr = Query(..., description="Email del mediador")):
    """
    Devuelve todos los casos del mediador indicado por email.
    """
    email_norm = email.strip().lower()
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            _ensure_table(cur)
            cur.execute(
                """
                SELECT id, mediador_email, titulo, descripcion, estado,
                       fecha_inicio, fecha_cierre, created_at, updated_at
                  FROM casos
                 WHERE LOWER(mediador_email) = LOWER(%s)
                 ORDER BY created_at DESC;
                """,
                (email_norm,),
            )
            rows = cur.fetchall() or []
    except Exception as e:
        raise HTTPException(500, f"Error listando casos: {e}")

    return [_row_to_dict(r) for r in rows]


@casos_router.post("", response_model=CasoOut)
def crear_caso(body: CasoCreate):
    """
    Crea un caso nuevo asociado al email del mediador.
    """
    email_norm = body.email.strip().lower()
    titulo = (body.titulo or "").strip()
    if not titulo:
        raise HTTPException(400, "Título obligatorio")

    estado = (body.estado or "abierto").strip().lower()
    if estado not in ("abierto", "en_curso", "cerrado"):
        estado = "abierto"

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            _ensure_table(cur)
            cur.execute(
                """
                INSERT INTO casos (mediador_email, titulo, descripcion, estado,
                                   fecha_inicio, created_at, updated_at)
                VALUES (LOWER(%s), %s, %s, %s, NOW(), NOW(), NOW())
                RETURNING id, mediador_email, titulo, descripcion, estado,
                          fecha_inicio, fecha_cierre, created_at, updated_at;
                """,
                (email_norm, titulo, body.descripcion, estado),
            )
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(500, f"No se pudo crear el caso: {e}")

    if not row:
        raise HTTPException(500, "No se pudo recuperar el caso creado.")

    return _row_to_dict(row)


@casos_router.get("/{caso_id}", response_model=CasoOut)
def obtener_caso(caso_id: int, email: EmailStr = Query(...)):
    """
    Devuelve el detalle de un caso, verificando que pertenece al mediador (email).
    """
    email_norm = email.strip().lower()
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            _ensure_table(cur)
            cur.execute(
                """
                SELECT id, mediador_email, titulo, descripcion, estado,
                       fecha_inicio, fecha_cierre, created_at, updated_at
                  FROM casos
                 WHERE id = %s
                   AND LOWER(mediador_email) = LOWER(%s);
                """,
                (caso_id, email_norm),
            )
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(500, f"Error obteniendo caso: {e}")

    if not row:
        raise HTTPException(404, "Caso no encontrado")

    return _row_to_dict(row)


@casos_router.put("/{caso_id}", response_model=CasoOut)
def actualizar_caso(caso_id: int, body: CasoUpdate):
    """
    Actualiza un caso del mediador.
    Se identifica por id + email propietario.
    """
    email_norm = body.email.strip().lower()

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            _ensure_table(cur)
            # Cargar caso actual
            cur.execute(
                """
                SELECT id, mediador_email, titulo, descripcion, estado,
                       fecha_inicio, fecha_cierre, created_at, updated_at
                  FROM casos
                 WHERE id = %s
                   AND LOWER(mediador_email) = LOWER(%s);
                """,
                (caso_id, email_norm),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Caso no encontrado")

            current = _row_to_dict(row)

            new_titulo = (body.titulo or current["titulo"] or "").strip()
            new_desc = (
                body.descripcion
                if body.descripcion is not None
                else current["descripcion"]
            )
            new_estado = (body.estado or current["estado"] or "abierto").strip().lower()
            if new_estado not in ("abierto", "en_curso", "cerrado"):
                new_estado = current["estado"] or "abierto"

            fecha_cierre = current["fecha_cierre"]
            if new_estado == "cerrado" and not fecha_cierre:
                fecha_cierre = datetime.utcnow()
            if new_estado in ("abierto", "en_curso") and fecha_cierre is not None:
                fecha_cierre = None

            cur.execute(
                """
                UPDATE casos
                   SET titulo = %s,
                       descripcion = %s,
                       estado = %s,
                       fecha_cierre = %s,
                       updated_at = NOW()
                 WHERE id = %s
                   AND LOWER(mediador_email) = LOWER(%s)
                RETURNING id, mediador_email, titulo, descripcion, estado,
                          fecha_inicio, fecha_cierre, created_at, updated_at;
                """,
                (
                    new_titulo,
                    new_desc,
                    new_estado,
                    fecha_cierre,
                    caso_id,
                    email_norm,
                ),
            )
            updated = cur.fetchone()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"No se pudo actualizar el caso: {e}")

    if not updated:
        raise HTTPException(404, "Caso no encontrado tras actualizar")

    return _row_to_dict(updated)


@casos_router.delete("/{caso_id}")
def eliminar_caso(caso_id: int, email: EmailStr = Query(...)):
    """
    Elimina un caso del mediador.
    Si prefieres 'soft delete' más adelante, se puede cambiar por estado = 'eliminado'.
    """
    email_norm = email.strip().lower()
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            _ensure_table(cur)
            cur.execute(
                """
                DELETE FROM casos
                 WHERE id = %s
                   AND LOWER(mediador_email) = LOWER(%s);
                """,
                (caso_id, email_norm),
            )
            n = cur.rowcount
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"No se pudo eliminar el caso: {e}")

    if n == 0:
        raise HTTPException(404, "Caso no encontrado")

    return {"ok": True, "deleted": caso_id}
