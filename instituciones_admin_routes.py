# instituciones_admin_routes.py — Gestión admin de instituciones (Mediazion)
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db import pg_conn
from contact_routes import _send_mail, MAIL_FROM_NAME, MAIL_FROM

# Usamos el mismo patrón de token admin que el resto de módulos
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"


def _auth(x_admin_token: Optional[str]):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


admin_instituciones_router = APIRouter(
    prefix="/instituciones/admin",
    tags=["instituciones-admin"],
)


# -------------------------
# Modelos de entrada
# -------------------------
class CambiarEstadoBody(BaseModel):
    estado: str  # pendiente | aprobada | rechazada


class CrearUsuarioBody(BaseModel):
    solicitud_id: int
    password: str
    meses: int = 6
    creado_por: str = "admin@mediazion.eu"


class DesactivarUsuarioBody(BaseModel):
    email: str


# -------------------------
# Helpers internos
# -------------------------
VALID_ESTADOS = {"pendiente", "aprobada", "rechazada"}


def _row_to_registro(row):
    """
    Convierte una fila de instituciones_registro en dict.
    Orden de columnas según SQL en migrate_routes.py:
      id, tipo, institucion, cargo, nombre, email,
      telefono, provincia, comentarios, estado, created_at
    """
    if not row:
        return None
    return {
        "id": row[0],
        "tipo": row[1],
        "institucion": row[2],
        "cargo": row[3],
        "nombre": row[4],
        "email": row[5],
        "telefono": row[6],
        "provincia": row[7],
        "comentarios": row[8],
        "estado": row[9],
        "created_at": row[10].isoformat() if row[10] else None,
    }


# -------------------------
# Endpoints: solicitudes
# -------------------------
@admin_instituciones_router.get("/solicitudes")
def listar_solicitudes(x_admin_token: Optional[str] = Header(None)):
    """
    Devuelve el listado de solicitudes institucionales.
    Usado por el panel AdminInstituciones.jsx (tabla principal).
    """
    _auth(x_admin_token)
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute(
            """
            SELECT id, tipo, institucion, cargo, nombre, email,
                   telefono, provincia, comentarios, estado, created_at
              FROM instituciones_registro
             ORDER BY created_at DESC, id DESC
            """
        )
        rows = cur.fetchall()
    items = [_row_to_registro(r) for r in rows]
    return {"ok": True, "items": items}


@admin_instituciones_router.get("/solicitudes/{solicitud_id}")
def obtener_solicitud(
    solicitud_id: int, x_admin_token: Optional[str] = Header(None)
):
    """
    Devuelve el detalle de una solicitud concreta.
    Usado al pulsar "Ver detalle" en la tabla.
    """
    _auth(x_admin_token)
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute(
            """
            SELECT id, tipo, institucion, cargo, nombre, email,
                   telefono, provincia, comentarios, estado, created_at
              FROM instituciones_registro
             WHERE id = %s
            """,
            (solicitud_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    item = _row_to_registro(row)
    return {"ok": True, "item": item}


@admin_instituciones_router.post("/solicitudes/{solicitud_id}/estado")
def cambiar_estado(
    solicitud_id: int,
    body: CambiarEstadoBody,
    x_admin_token: Optional[str] = Header(None),
):
    """
    Cambia el estado de una solicitud: pendiente | aprobada | rechazada.
    """
    _auth(x_admin_token)
    nuevo_estado = body.estado.strip().lower()
    if nuevo_estado not in VALID_ESTADOS:
        raise HTTPException(
            status_code=400,
            detail=f"Estado no válido. Usa uno de: {', '.join(sorted(VALID_ESTADOS))}",
        )

    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute(
            "UPDATE instituciones_registro SET estado=%s WHERE id=%s;",
            (nuevo_estado, solicitud_id),
        )
        updated = cur.rowcount
        cx.commit()

    if updated == 0:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    return {"ok": True, "id": solicitud_id, "estado": nuevo_estado}


# -------------------------
# Endpoints: usuarios institucionales
# -------------------------
@admin_instituciones_router.post("/crear_usuario")
def crear_usuario_desde_solicitud(
    body: CrearUsuarioBody,
    x_admin_token: Optional[str] = Header(None),
):
    """
    Crea/actualiza un usuario institucional a partir de una solicitud.
    También actualiza el estado de la solicitud a 'aprobada' y
    devuelve datos para mostrar en el panel admin.

    Si ya existe un usuario con ese email, se reactiva, se
    actualiza la contraseña y se renueva la fecha de expiración.
    """
    _auth(x_admin_token)

    if not body.password:
        raise HTTPException(status_code=400, detail="La contraseña es obligatoria")
    if body.meses <= 0:
        raise HTTPException(status_code=400, detail="Meses debe ser > 0")

    # 1) Recuperar la solicitud
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute(
            """
            SELECT id, tipo, institucion, cargo, nombre, email,
                   telefono, provincia, comentarios, estado, created_at
              FROM instituciones_registro
             WHERE id = %s
            """,
            (body.solicitud_id,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")

        solicitud = _row_to_registro(row)

        # 2) Calcular fechas de activación / expiración
        now = datetime.now(timezone.utc)
        # Para simplificar: meses * 30 días
        dias = body.meses * 30
        fecha_expiracion = now + timedelta(days=dias)

        # 3) Hash de contraseña
        hashed = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

        # 4) Insertar o actualizar usuario institucional
        cur.execute(
            """
            INSERT INTO instituciones_usuarios
                (email, password_hash, institucion, tipo, cargo, nombre,
                 provincia, estado, fecha_activacion, fecha_expiracion, creado_por)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'activo',%s,%s,%s)
            ON CONFLICT (email)
            DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                institucion   = EXCLUDED.institucion,
                tipo          = EXCLUDED.tipo,
                cargo         = EXCLUDED.cargo,
                nombre        = EXCLUDED.nombre,
                provincia     = EXCLUDED.provincia,
                estado        = 'activo',
                fecha_activacion = EXCLUDED.fecha_activacion,
                fecha_expiracion = EXCLUDED.fecha_expiracion,
                creado_por    = EXCLUDED.creado_por
            """,
            (
                solicitud["email"],
                hashed,
                solicitud["institucion"],
                solicitud["tipo"],
                solicitud["cargo"],
                solicitud["nombre"],
                solicitud["provincia"],
                now,
                fecha_expiracion,
                body.creado_por,
            ),
        )

        # 5) Marcar la solicitud como aprobada
        cur.execute(
            "UPDATE instituciones_registro SET estado='aprobada' WHERE id=%s;",
            (body.solicitud_id,),
        )

        cx.commit()

    # 6) Enviar correo a la institución con la contraseña temporal
    try:
        asunto = "Mediazion · Acceso institucional"
        html = f"""
        <div style="font-family:system-ui,Segoe UI,Roboto,Arial; white-space:pre-wrap">
Hola {solicitud["nombre"]},

Tu acceso institucional a Mediazion ha sido activado.

Datos principales:
- Institución: {solicitud["institucion"]}
- Tipo: {solicitud["tipo"]}
- Email de acceso: {solicitud["email"]}
- Contraseña temporal: {body.password}
- Vigencia: {body.meses} meses (hasta {fecha_expiracion.date().isoformat()})

Te recomendamos cambiar la contraseña en tu primer acceso.

Un saludo,
{MAIL_FROM_NAME or "Mediazion"}
{MAIL_FROM}
        </div>
        """
        _send_mail(
            solicitud["email"],
            asunto,
            html,
            solicitud["nombre"],
        )
    except Exception as e:
        # No rompemos el flujo si el email falla
        print(f"[AVISO] Error enviando correo a usuario institucional: {e}")

    return {
        "ok": True,
        "institucion": solicitud["institucion"],
        "email": solicitud["email"],
        "fecha_expiracion": fecha_expiracion.isoformat(),
    }


@admin_instituciones_router.post("/desactivar_usuario")
def desactivar_usuario(
    body: DesactivarUsuarioBody,
    x_admin_token: Optional[str] = Header(None),
):
    """
    Desactiva/suspende manualmente el acceso de un usuario institucional.
    - Cambia estado a 'suspendido'
    - Si la fecha de expiración es futura o NULL, la adelanta a ahora
    """
    _auth(x_admin_token)
    email = body.email.strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email obligatorio")

    now = datetime.now(timezone.utc)

    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute(
            """
            UPDATE instituciones_usuarios
               SET estado = 'suspendido',
                   fecha_expiracion = CASE
                       WHEN fecha_expiracion IS NULL OR fecha_expiracion > %s
                       THEN %s
                       ELSE fecha_expiracion
                   END
             WHERE LOWER(email) = LOWER(%s);
            """,
            (now, now, email),
        )
        updated = cur.rowcount
        cx.commit()

    if updated == 0:
        raise HTTPException(status_code=404, detail="Usuario institucional no encontrado")

    return {"ok": True, "email": email, "estado": "suspendido"}
