# migrate_routes.py — añadir columnas y bajar trial a básico (usar SOLO en despliegue inicial / cron manual)
import os
from fastapi import APIRouter, Header, HTTPException
from db import pg_conn

router = APIRouter(prefix="/admin/migrate", tags=["admin-migrate"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

SQL_ADD_COLS = """
ALTER TABLE IF NOT EXISTS mediadores ADD COLUMN IF NOT EXISTS dni_cif TEXT;
ALTER TABLE IF NOT EXISTS mediadores ADD COLUMN IF NOT EXISTS tipo TEXT;
ALTER TABLE IF NOT EXISTS mediadores ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE IF NOT EXISTS mediadores ADD COLUMN IF NOT EXISTS trial_start TIMESTAMP NULL;
ALTER TABLE IF NOT EXISTS mediadores ADD COLUMN IF NOT EXISTS trial_end   TIMESTAMP NULL;
ALTER TABLE IF NOT EXISTS mediadores ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'none';
"""

SQL_LOWER_TRIAL = """
UPDATE mediadores
   SET subscription_status='expired', status='active'
 WHERE subscription_status='trialing'
   AND trial_end IS NOT NULL
   AND trial_end < NOW()
   AND (trial_used IS FALSE OR trial_used IS NULL);
"""

@router.post("/add_cols")
def add_cols(x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(SQL_ADD_COLS)
        cx.commit()
    return {"ok": True, "message": "Columnas esenciales aseguradas (dni_cif, tipo, password_hash, trial_* , subscription_status)"}

@router.post("/downgrade_trials")
def downgrade_trials(x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(SQL_LOWER_TRIAL)
            count = cur.rowcount
        cx.commit()
    return {"ok": True, "lowered": count}
