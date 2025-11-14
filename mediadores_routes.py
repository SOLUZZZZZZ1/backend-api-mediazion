# mediadores_routes.py — COMPLETO Y FINAL

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
import bcrypt
from datetime import datetime, timedelta, timezone

mediadores_router = APIRouter()


# ============================
#  MODELO DE ALTA
# ============================

class MediadorRegisterIn(BaseModel):
    name: str
    email: EmailStr
    phone: str
    provincia: str
    especialidad: str
    dni_cif: str
    tipo: str
    accept: bool = True


# ============================
#  ALTA DE MEDIADORES
# ============================

@mediadores_router.post("/mediadores/register")
def mediador_register(body: MediadorRegisterIn):
    email = body.email.lower().strip()

    try:
        with pg_conn() as cx, cx.cursor() as cur:

            # ¿Existe ya?
            cur.execute("SELECT 1 FROM mediadores WHERE LOWER(email)=LOWER(%s);", (email,))
            if cur.fetchone():
                raise HTTPException(409, "Este correo ya está registrado")

            # Contraseña temporal
            temp_password = "Mediazion123"   # puedes cambiarla o hacerla aleatoria
            hashed = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

            # Insertar usuario
            cur.execute("""
                INSERT INTO mediadores
                (name, email, phone, provincia, especialidad, dni_cif, tipo,
                 status, subscription_status, password_hash, trial_used,
                 created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,
                        'active','trialing',%s,TRUE,
                        NOW());
            """, (
                body.name, email, body.phone, body.provincia,
                body.especialidad, body.dni_cif, body.tipo,
                hashed
            ))

            cx.commit()

        # IMPORTANTE: devolver contraseña temporal
        return {
            "ok": True,
            "message": "Alta correcta. Usa la contraseña temporal enviada.",
            "temp_password": temp_password
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error registrando mediador: {e}")


# ============================
# ESTADO DEL MEDIADOR
# ============================

@mediadores_router.get("/mediadores/status")
def mediador_status(email: EmailStr):
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("""
                SELECT subscription_status, status
                FROM mediadores
                WHERE LOWER(email)=LOWER(%s)
            """, (email,))
            row = cur.fetchone()

        if not row:
            return {"email": email, "subscription_status": "none", "status": "missing"}

        subscription_status, status = row
        return {
            "email": email,
            "subscription_status": subscription_status or "none",
            "status": status or "active"
        }

    except Exception as e:
        raise HTTPException(500, f"Error consultando estado: {e}")


# ============================
# ACTIVAR PRUEBA GRATIS (7 días)
# ============================

@mediadores_router.post("/mediadores/set_trial")
def set_trial(email: EmailStr, days: int = 7):

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("""
                UPDATE mediadores
                   SET subscription_status='trialing',
                       status='active',
                       trial_used=TRUE,
                       trial_start=%s,
                       trial_end=%s
                 WHERE LOWER(email)=LOWER(%s)
            """, (now, end, email))

            updated = cur.rowcount
            cx.commit()

        if updated == 0:
            raise HTTPException(404, "Mediador no encontrado")

        return {"ok": True, "trial_until": end.isoformat()}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error activando trial: {e}")
