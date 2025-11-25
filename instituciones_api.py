# instituciones_api.py — Endpoints para perfil y contraseña institucional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import bcrypt

from db import pg_conn

router = APIRouter(prefix="/api/instituciones", tags=["instituciones"])


# ---------- Modelos ----------

class PerfilInstitucionUpdate(BaseModel):
  email: str
  nombre: str
  telefono: Optional[str] = ""
  persona_contacto: Optional[str] = ""
  observaciones: Optional[str] = ""


class PasswordChange(BaseModel):
  password_actual: str
  password_nueva: str


# ---------- PERFIL INSTITUCIONAL ----------

@router.get("/perfil")
def get_perfil(email: str):
  """Devuelve el perfil institucional para el correo indicado.

  Usa la tabla instituciones_registro como base de datos de perfil.
  Si no encuentra nada, devuelve 404 (el frontend ya sabe interpretarlo
  como 'perfil aún no configurado').
  """
  if not email:
    raise HTTPException(400, "email requerido")

  with pg_conn() as cx:
    with cx.cursor() as cur:
      cur.execute(
        """SELECT id, tipo, institucion, cargo, nombre, email, telefono,
                          provincia, comentarios, created_at, estado
               FROM instituciones_registro
              WHERE LOWER(email) = LOWER(%s)
              ORDER BY created_at DESC
              LIMIT 1""",
        (email,),
      )
      row = cur.fetchone()

  if not row:
    raise HTTPException(404, "Perfil no encontrado")

  (
    _id,
    tipo,
    institucion,
    cargo,
    persona_nombre,
    correo,
    telefono,
    provincia,
    comentarios,
    created_at,
    estado,
  ) = row

  return {
    "email": correo,
    "nombre": institucion,               # nombre visible de la institución
    "telefono": telefono,
    "persona_contacto": persona_nombre,  # persona de contacto
    "observaciones": comentarios,
    "tipo": tipo,
    "cargo": cargo,
    "provincia": provincia,
    "estado": estado,
    "created_at": created_at.isoformat() if created_at else None,
  }


@router.put("/perfil")
def update_perfil(email: str, body: PerfilInstitucionUpdate):
  """Actualiza (o crea) los datos de perfil de la institución.

  Se apoya en instituciones_registro: si existe una fila para ese email,
  se actualiza la más reciente; si no, se inserta una nueva entrada.
  """
  if not email:
    raise HTTPException(400, "email requerido")

  # Normalizamos correo
  email_norm = email.strip().lower()
  if not email_norm:
    raise HTTPException(400, "email inválido")

  # Valores procedentes del body
  nuevo_nombre_inst = body.nombre.strip()
  if not nuevo_nombre_inst:
    raise HTTPException(400, "nombre de institución requerido")

  telefono = (body.telefono or "").strip() or None
  persona_contacto = (body.persona_contacto or "").strip() or None
  observaciones = (body.observaciones or "").strip() or None

  with pg_conn() as cx:
    with cx.cursor() as cur:
      # Miramos si ya hay un registro existente
      cur.execute(
        """SELECT id
               FROM instituciones_registro
              WHERE LOWER(email) = LOWER(%s)
              ORDER BY created_at DESC
              LIMIT 1""",
        (email_norm,),
      )
      row = cur.fetchone()

      if row:
        reg_id = row[0]
        cur.execute(
          """UPDATE instituciones_registro
                 SET institucion = %s,
                     nombre = COALESCE(%s, nombre),
                     telefono = %s,
                     comentarios = %s
               WHERE id = %s""",
          (
            nuevo_nombre_inst,
            persona_contacto,
            telefono,
            observaciones,
            reg_id,
          ),
        )
      else:
        # Insertamos un registro básico
        cur.execute(
          """INSERT INTO instituciones_registro
                  (tipo, institucion, cargo, nombre, email, telefono,
                   provincia, comentarios, estado)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, %s, 'aprobada')
                RETURNING id""",
          (
            "otra",
            nuevo_nombre_inst,
            "Contacto",
            persona_contacto or nuevo_nombre_inst,
            email_norm,
            telefono,
            None,
            observaciones,
          ),
        )
        reg_id = cur.fetchone()[0]

    cx.commit()

  return {
    "ok": True,
    "id": reg_id,
    "email": email_norm,
    "nombre": nuevo_nombre_inst,
  }


# ---------- CAMBIO DE CONTRASEÑA ----------

@router.post("/password")
def cambiar_password(email: str, body: PasswordChange):
  """Permite cambiar la contraseña de un usuario institucional.

  Opera sobre la tabla instituciones_usuarios.
  """
  if not email:
    raise HTTPException(400, "email requerido")

  email_norm = email.strip().lower()
  if not email_norm:
    raise HTTPException(400, "email inválido")

  if not body.password_actual or not body.password_nueva:
    raise HTTPException(400, "Contraseñas requeridas")

  if len(body.password_nueva) < 8:
    raise HTTPException(
      400, "La nueva contraseña debe tener al menos 8 caracteres."
    )

  with pg_conn() as cx:
    with cx.cursor() as cur:
      # Recuperamos hash actual
      cur.execute(
        """SELECT id, password_hash
               FROM instituciones_usuarios
              WHERE LOWER(email) = LOWER(%s)
              LIMIT 1""",
        (email_norm,),
      )
      row = cur.fetchone()

      if not row:
        raise HTTPException(404, "Usuario institucional no encontrado")

      user_id, stored_hash = row

      # Comprobamos contraseña actual
      try:
        if not bcrypt.checkpw(
          body.password_actual.encode("utf-8"),
          stored_hash.encode("utf-8"),
        ):
          raise HTTPException(400, "La contraseña actual no es correcta.")
      except ValueError:
        # Por si el hash guardado no es válido
        raise HTTPException(500, "Hash de contraseña inválido en el servidor.")

      # Generamos nuevo hash
      new_hash = bcrypt.hashpw(
        body.password_nueva.encode("utf-8"), bcrypt.gensalt()
      ).decode("utf-8")

      # Guardamos
      cur.execute(
        """UPDATE instituciones_usuarios
               SET password_hash = %s
             WHERE id = %s""",
        (new_hash, user_id),
      )

    cx.commit()

  return {"ok": True, "email": email_norm, "message": "Contraseña actualizada."}
