"""
casos_routes.py — Gestor de casos/expedientes para mediadores PRO en Mediazion.

Endpoints (una vez incluido en app.py con prefix="/api"):

- GET    /api/casos           → listar casos del mediador autenticado
- POST   /api/casos           → crear caso nuevo
- GET    /api/casos/{id}      → detalle de un caso
- PUT    /api/casos/{id}      → actualizar caso
- DELETE /api/casos/{id}      → eliminar caso
"""
from datetime import datetime
from typing import List, Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Session

# ==========================
# IMPORTS ADAPTADOS A MEDIAZION
# ==========================

# Usa el mismo módulo que ya usas para la base de datos.
# Si en tu proyecto el archivo se llama distinto, cambia 'database'
# por el nombre real (por ejemplo, 'db').
from database import Base, get_db  # ← Si tu módulo se llama distinto, cambia aquí solo el nombre.

# IMPORTANTE: aquí asumimos que en auth_routes tienes una función
# que devuelve el usuario/mediador autenticado a partir del JWT.
# Si el nombre es distinto, ajusta el import.
from auth_routes import get_current_user


class MediadorIdentity(BaseModel):
    id: int
    email: Optional[str] = None
    subscription_status: Optional[str] = None


def get_current_mediador(user: Any = Depends(get_current_user)) -> MediadorIdentity:
    """
    Adapta el objeto devuelto por get_current_user a un esquema sencillo
    con id / email / subscription_status.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado.",
        )

    # user puede ser un objeto ORM o un dict; intentamos ambas cosas.
    def _get(attr: str):
        if hasattr(user, attr):
            return getattr(user, attr)
        if isinstance(user, dict):
            return user.get(attr)
        return None

    uid = _get("id")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario sin id.",
        )

    email = _get("email")
    subs = _get("subscription_status") or _get("plan") or None

    return MediadorIdentity(id=uid, email=email, subscription_status=subs)


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

casos_router = APIRouter()


def ensure_pro_user(mediador: MediadorIdentity):
    """
    Control de acceso PRO/BASIC:
    - Permite acceso si subscription_status es 'active' o 'trialing' o 'pro'.
    - Restringe si es 'none' / 'expired' / etc.
    Ajusta los valores según tus enums reales.
    Si NO tienes todavía este campo, puedes comentar la llamada a ensure_pro_user
    en los endpoints hasta que lo actives.
    """
    status_value = (mediador.subscription_status or "").lower()
    if status_value and status_value not in ("active", "trialing", "pro"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu plan actual no incluye el gestor de casos.",
        )


# ==========================
# ENDPOINTS
# ==========================

@casos_router.get("/casos", response_model=List[CasoOut])
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


@casos_router.post("/casos", response_model=CasoOut, status_code=status.HTTP_201_CREATED)
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


@casos_router.get("/casos/{caso_id}", response_model=CasoOut)
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


@casos_router.put("/casos/{caso_id}", response_model=CasoOut)
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


@casos_router.delete("/casos/{caso_id}", status_code=status.HTTP_204_NO_CONTENT)
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
