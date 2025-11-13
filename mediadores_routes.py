# mediadores_routes.py — Estado del mediador (BÁSICO / PRO / TRIAL)
from fastapi import APIRouter, HTTPException
from pydantic import EmailStr
from db import pg_conn

mediadores_router = APIRouter()

@mediadores_router.get("/mediadores/status")
def mediador_status(email: EmailStr):
    """
    Devuelve el estado de PRO/BÁSICO del mediador.
    El frontend usa esta ruta para abrir el panel PRO.
    """
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("""
                SELECT subscription_status, status
                FROM mediadores
                WHERE LOWER(email)=LOWER(%s)
            """, (email,))
            row = cur.fetchone()

        if not row:
            return {
                "email": email,
                "subscription_status": "none",
                "status": "missing"
            }

        subscription_status, status = row

        return {
            "email": email,
            "subscription_status": subscription_status or "none",
            "status": status or "active"
        }

    except Exception as e:
        raise HTTPException(500, f"Error consultando estado: {e}")


@mediadores_router.post("/mediadores/set_trial")
def set_trial(email: EmailStr, days: int = 7):
    """
    Activa el modo PRO (trial) del mediador por X días.
    Lo usa “Probar PRO”
    """
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("""
                UPDATE mediadores
                SET subscription_status='trialing',
                    status='active',
                    trial_used=true,
                    trial_start=NOW(),
                    trial_end=NOW() + (%s || ' days')::interval
                WHERE LOWER(email)=LOWER(%s)
            """, (days, email))
            updated = cur.rowcount
            cx.commit()

        if updated == 0:
            raise HTTPException(404, "Mediador no encontrado")

        return {"ok": True, "message": "Trial activado", "email": email}

    except Exception as e:
        raise HTTPException(500, f"Error activando trial: {e}")
