"""
casos_routes.py — Gestor de casos/expedientes para mediadores PRO en Mediazion.

Este router añade el recurso /api/casos con:
- GET /api/casos           → listar casos del mediador autenticado
- POST /api/casos          → crear caso nuevo
- GET /api/casos/{id}      → detalle de un caso
- PUT /api/casos/{id}      → actualizar caso
- DELETE /api/casos/{id}   → (opcional) eliminar/archivar caso

IMPORTANTE:
- Está pensado para encajar con tu backend FastAPI actual.
- Solo tendrás que ajustar 2–3 imports marcados con el comentario:  # ⬅ AJUSTAR IMPORT
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Session

# ==========================
# IMPORTS A AJUSTAR
# ==========================

# Usa la misma Base y get_db que tu proyecto.
# Si tu módulo se llama distinto (por ejemplo "db" en lugar de "database"),
# solo cambia la ruta del import.
from .database import Base, get_db   # ⬅ AJUSTAR IMPORT si es necesario

# Si ya tienes un modelo "Mediador" no hace falta importarlo aquí,
# solo usamos la FK "mediadores.id" a nivel SQL. No es obligatorio
# tener la relación en Python para que funcione.

# Dependencia que devuelve el mediador autenticado.
# Si ya tienes algo como get_current_user / get_current_mediador
# en otro módulo, impórtalo y úsalo.
# EJEMPLO:
# from .auth_routes import get_current_mediador
#
# De momento definimos un "stub" tipado que puedes enlazar con tu lógica real.
class MediadorIdentity(BaseModel):
    id: int
    email: Optional[str] = None
    subscription_status: Optional[str] = None


def get_current_mediador() -> MediadorIdentity:
    """
    ⛔ IMPORTANTE:
    ----------------
    ESTA FUNCIÓN ES SOLO UN "PLACEHOLDER" PARA QUE EL ARCHIVO SEA AUTOCONTENIDO.

    En tu proyecto REAL debes:
    - Eliminar esta función.
    - Importar la dependencia que ya uses para extraer el mediador del JWT,
      por ejemplo:

        from .auth_routes import get_current_mediador

    y usarla en los Depends() de los endpoints de abajo.
    """
    # Esto evitará que el servidor arranque si alguien olvida sustituirla.
    raise RuntimeError(
        "get_current_mediador() de casos_routes.py es un placeholder. "
        "Importa la dependencia real desde tu módulo de autenticación."
    )


# ==========================
# MODELO SQLALCHEMY
# ==========================

class Caso(Base):
    __tablename__ = "casos"

    id = Column(Integer, primary_key=True, index=True)
    mediador_id = Column(Integer, ForeignKey("mediadores.id"), index=True)

    titulo = Column(String(255), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(String(50), nullable=False, default="abierto")

    # Para futuro: adjuntar documentos del caso (URLs S3)
    # Ej: [{"name": "acta.pdf", "url": "https://....", "type": "pdf"}]
    archivos = Column(JSON, nullable=True)

    fecha_inicio = Column(DateTime, nullable=False, default=datetime.utcnow)
    fecha_cierre = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ==========================
# ESQUEMAS Pydantic
# ==========================

class ArchivoItem(BaseModel):
    name: str
    url: str
    type: Optional[str] = None


class CasoBase(BaseModel):
    titulo: str = Field(..., max_length=255)
    descripcion: Optional[str] = None
    estado: Optional[str] = Field(
        default="abierto",
        description="abierto | en_curso | cerrado",
    )
    archivos: Optional[List[ArchivoItem]] = None


class CasoCreate(CasoBase):
    pass


class CasoUpdate(BaseModel):
    titulo: Optional[str] = Field(None, max_length=255)
    descripcion: Optional[str] = None
    estado: Optional[str] = Field(
        default=None,
        description="abierto | en_curso | cerrado",
    )
    archivos: Optional[List[ArchivoItem]] = None


class CasoOut(BaseModel):
    id: int
    mediador_id: int
    titulo: str
    descripcion: Optional[str]
    estado: str
    archivos: Optional[List[ArchivoItem]]
    fecha_inicio: datetime
    fecha_cierre: Optional[datetime]

    class Config:
        orm_mode = True


# ==========================
# ROUTER
# ==========================

router = APIRouter(
    prefix="/casos",
    tags=["casos"],
)


def ensure_pro_user(mediador: MediadorIdentity):
    """
    Control de acceso PRO/BASIC:
    - Permite acceso si subscription_status es 'active' o 'trialing'.
    - Restringe si es 'none' / 'expired' / etc.
    Ajusta los valores según tus enums reales.
    """
    status_value = (mediador.subscription_status or "").lower()
    if status_value not in ("active", "trialing", "pro"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu plan actual no incluye el gestor de casos.",
        )


# ==========================
# ENDPOINTS
# ==========================

@router.get("/", response_model=List[CasoOut])
def listar_casos(
    db: Session = Depends(get_db),
    mediador: MediadorIdentity = Depends(get_current_mediador),
):
    """
    Devuelve SOLO los casos del mediador autenticado.
    """
    ensure_pro_user(mediador)
    rows = (
        db.query(Caso)
        .filter(Caso.mediador_id == mediador.id)
        .order_by(Caso.created_at.desc())
        .all()
    )
    return rows


@router.post("/", response_model=CasoOut, status_code=status.HTTP_201_CREATED)
def crear_caso(
    payload: CasoCreate,
    db: Session = Depends(get_db),
    mediador: MediadorIdentity = Depends(get_current_mediador),
):
    """
    Crea un caso nuevo para el mediador autenticado.
    """
    ensure_pro_user(mediador)

    now = datetime.utcnow()
    fecha_cierre = None
    if payload.estado and payload.estado.lower() == "cerrado":
        fecha_cierre = now

    nuevo = Caso(
        mediador_id=mediador.id,
        titulo=payload.titulo.strip(),
        descripcion=(payload.descripcion or "").strip() or None,
        estado=(payload.estado or "abierto").lower(),
        archivos=[a.dict() for a in (payload.archivos or [])] or None,
        fecha_inicio=now,
        fecha_cierre=fecha_cierre,
        created_at=now,
        updated_at=now,
    )

    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.get("/{caso_id}", response_model=CasoOut)
def obtener_caso(
    caso_id: int,
    db: Session = Depends(get_db),
    mediador: MediadorIdentity = Depends(get_current_mediador),
):
    """
    Devuelve el detalle de un caso concreto del mediador.
    """
    ensure_pro_user(mediador)

    caso = (
        db.query(Caso)
        .filter(Caso.id == caso_id, Caso.mediador_id == mediador.id)
        .first()
    )

    if not caso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Caso no encontrado.",
        )

    return caso


@router.put("/{caso_id}", response_model=CasoOut)
def actualizar_caso(
    caso_id: int,
    payload: CasoUpdate,
    db: Session = Depends(get_db),
    mediador: MediadorIdentity = Depends(get_current_mediador),
):
    """
    Actualiza un caso del mediador.
    """
    ensure_pro_user(mediador)

    caso = (
        db.query(Caso)
        .filter(Caso.id == caso_id, Caso.mediador_id == mediador.id)
        .first()
    )

    if not caso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Caso no encontrado.",
        )

    if payload.titulo is not None:
        caso.titulo = payload.titulo.strip() or caso.titulo

    if payload.descripcion is not None:
        caso.descripcion = payload.descripcion.strip() or None

    if payload.estado is not None:
        estado = payload.estado.lower()
        caso.estado = estado
        if estado == "cerrado" and not caso.fecha_cierre:
            caso.fecha_cierre = datetime.utcnow()
        if estado in ("abierto", "en_curso") and caso.fecha_cierre is not None:
            caso.fecha_cierre = None

    if payload.archivos is not None:
        caso.archivos = [a.dict() for a in payload.archivos] or None

    caso.updated_at = datetime.utcnow()

    db.add(caso)
    db.commit()
    db.refresh(caso)

    return caso


@router.delete("/{caso_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_caso(
    caso_id: int,
    db: Session = Depends(get_db),
    mediador: MediadorIdentity = Depends(get_current_mediador),
):
    """
    Elimina un caso del mediador.
    Si prefieres "soft delete", en lugar de borrar puedes:
      - añadir campo 'archivado' o
      - cambiar estado a 'cerrado'/'eliminado'.

    Por simplicidad aquí BORRAMOS el registro.
    """
    ensure_pro_user(mediador)

    caso = (
        db.query(Caso)
        .filter(Caso.id == caso_id, Caso.mediador_id == mediador.id)
        .first()
    )

    if not caso:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Caso no encontrado.",
        )

    db.delete(caso)
    db.commit()
    return None
