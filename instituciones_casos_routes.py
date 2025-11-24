# instituciones_casos_routes.py — Casos institucionales (lista + detalle + estado + notas)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from db import pg_conn

router = APIRouter(prefix="/api/instituciones", tags=["instituciones-casos"])

class CasoResumen(BaseModel):
    id: int
    asunto: str
    ciudadano_nombre: str
    estado: str
    fecha_creacion: str

class CasoDetalle(BaseModel):
    id: int
    institucion_email: str
    ciudadano_nombre: str
    ciudadano_email: Optional[str] = None
    ciudadano_telefono: Optional[str] = None
    asunto: str
    descripcion: Optional[str] = None
    estado: str
    fecha_creacion: str
    fecha_actualizacion: Optional[str] = None

class NotaEntrada(BaseModel):
    contenido: str

class Nota(BaseModel):
    id: int
    caso_id: int
    contenido: str
    creada_en: str

class EstadoEntrada(BaseModel):
    estado: str  # pendiente | en_gestion | resuelto | etc.

SQL_CREATE_CASOS = """
CREATE TABLE IF NOT EXISTS casos_institucion (
  id SERIAL PRIMARY KEY,
  institucion_email TEXT NOT NULL,
  ciudadano_nombre TEXT NOT NULL,
  ciudadano_email TEXT,
  ciudadano_telefono TEXT,
  asunto TEXT NOT NULL,
  descripcion TEXT,
  estado TEXT DEFAULT 'pendiente',
  fecha_creacion TIMESTAMP DEFAULT NOW(),
  fecha_actualizacion TIMESTAMP
);
"""

SQL_CREATE_NOTAS = """
CREATE TABLE IF NOT EXISTS casos_notas (
  id SERIAL PRIMARY KEY,
  caso_id INTEGER NOT NULL REFERENCES casos_institucion(id) ON DELETE CASCADE,
  contenido TEXT NOT NULL,
  creada_en TIMESTAMP DEFAULT NOW()
);
"""

def _ensure_tables():
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(SQL_CREATE_CASOS)
            cur.execute(SQL_CREATE_NOTAS)
        cx.commit()

@router.get("/casos", response_model=List[CasoResumen])
def listar_casos(email: str):
    if not email:
        raise HTTPException(400, "Email institucional requerido")

    _ensure_tables()

    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, asunto, ciudadano_nombre, estado, fecha_creacion
                      FROM casos_institucion
                     WHERE LOWER(institucion_email) = LOWER(%s)
                     ORDER BY fecha_creacion DESC, id DESC
                    """,
                    (email,),
                )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(500, f"Error listando casos: {e}")

    casos: list[CasoResumen] = []
    for cid, asunto, ciudadano_nombre, estado, fecha_creacion in rows:
        casos.append(
            CasoResumen(
                id=cid,
                asunto=asunto,
                ciudadano_nombre=ciudadano_nombre,
                estado=estado or "pendiente",
                fecha_creacion=fecha_creacion.isoformat() if fecha_creacion else "",
            )
        )
    return casos

@router.get("/casos/{caso_id}", response_model=CasoDetalle)
def obtener_caso(caso_id: int):
    _ensure_tables()
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    """
                    SELECT id,
                           institucion_email,
                           ciudadano_nombre,
                           ciudadano_email,
                           ciudadano_telefono,
                           asunto,
                           descripcion,
                           estado,
                           fecha_creacion,
                           fecha_actualizacion
                      FROM casos_institucion
                     WHERE id = %s
                    """,
                    (caso_id,),
                )
                row = cur.fetchone()
    except Exception as e:
        raise HTTPException(500, f"Error obteniendo caso: {e}")

    if not row:
        raise HTTPException(404, "Caso no encontrado")

    (
        cid,
        institucion_email,
        ciudadano_nombre,
        ciudadano_email,
        ciudadano_telefono,
        asunto,
        descripcion,
        estado,
        fecha_creacion,
        fecha_actualizacion,
    ) = row

    return CasoDetalle(
        id=cid,
        institucion_email=institucion_email,
        ciudadano_nombre=ciudadano_nombre,
        ciudadano_email=ciudadano_email,
        ciudadano_telefono=ciudadano_telefono,
        asunto=asunto,
        descripcion=descripcion,
        estado=estado or "pendiente",
        fecha_creacion=fecha_creacion.isoformat() if fecha_creacion else "",
        fecha_actualizacion=fecha_actualizacion.isoformat() if fecha_actualizacion else None,
    )

@router.post("/casos/{caso_id}/estado")
def actualizar_estado_caso(caso_id: int, entrada: EstadoEntrada):
    nuevo_estado = (entrada.estado or "").strip()
    if not nuevo_estado:
        raise HTTPException(400, "El estado no puede estar vacío")

    _ensure_tables()
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    """
                    UPDATE casos_institucion
                       SET estado = %s,
                           fecha_actualizacion = NOW()
                     WHERE id = %s
                    """,
                    (nuevo_estado, caso_id),
                )
                n = cur.rowcount
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error actualizando estado del caso: {e}")

    if n == 0:
        raise HTTPException(404, "Caso no encontrado")

    return {"ok": True, "id": caso_id, "estado": nuevo_estado}

@router.post("/casos/{caso_id}/nota", response_model=Nota)
def agregar_nota_caso(caso_id: int, entrada: NotaEntrada):
    contenido = (entrada.contenido or "").strip()
    if not contenido:
        raise HTTPException(400, "El contenido de la nota no puede estar vacío")

    _ensure_tables()
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute("SELECT id FROM casos_institucion WHERE id = %s", (caso_id,))
                if not cur.fetchone():
                    raise HTTPException(404, "Caso no encontrado")

                cur.execute(
                    """
                    INSERT INTO casos_notas (caso_id, contenido)
                    VALUES (%s, %s)
                    RETURNING id, creada_en
                    """,
                    (caso_id, contenido),
                )
                nid, creada_en = cur.fetchone()
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error agregando nota: {e}")

    return Nota(
        id=nid,
        caso_id=caso_id,
        contenido=contenido,
        creada_en=creada_en.isoformat() if creada_en else "",
    )

@router.get("/casos/{caso_id}/notas", response_model=list[Nota])
def listar_notas_caso(caso_id: int):
    _ensure_tables()
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, caso_id, contenido, creada_en
                      FROM casos_notas
                     WHERE caso_id = %s
                     ORDER BY creada_en DESC, id DESC
                    """,
                    (caso_id,),
                )
                rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(500, f"Error listando notas: {e}")

    notas: list[Nota] = []
    for nid, cid, contenido, creada_en in rows:
        notas.append(
            Nota(
                id=nid,
                caso_id=cid,
                contenido=contenido,
                creada_en=creada_en.isoformat() if creada_en else "",
            )
        )
    return notas
