# migrate_routes.py — corregido: añade columnas y baja trials (idempotente)
import os
from fastapi import APIRouter, Header, HTTPException
from db import pg_conn

router = APIRouter(prefix="/admin/migrate", tags=["admin-migrate"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS mediadores (
  id SERIAL PRIMARY KEY
);
"""

SQL_ADD_COLS = """
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS email TEXT UNIQUE;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS provincia TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS especialidad TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS dni_cif TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS tipo TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT TRUE;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'none';
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS trial_used BOOLEAN DEFAULT FALSE;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS trial_start TIMESTAMP NULL;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS trial_end   TIMESTAMP NULL;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS subscription_id TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
"""

SQL_UNIQ_EMAIL = """
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
     WHERE tablename='mediadores' AND indexname='mediadores_email_lower_uniq'
  ) THEN
    CREATE UNIQUE INDEX mediadores_email_lower_uniq ON mediadores (LOWER(email));
  END IF;
END$$;
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
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_CREATE_TABLE)
                cur.execute(SQL_ADD_COLS)
                cur.execute(SQL_UNIQ_EMAIL)
            cx.commit()
        return {"status": "ok", "message": "Columnas/índice asegurados (mediadores)."}
    except Exception as e:
        raise HTTPException(500, f"Migration error: {e}")

@router.post("/downgrade_trials")
def downgrade_trials(x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_LOWER_TRIAL)
                n = cur.rowcount
            cx.commit()
        return {"status": "ok", "lowered": n}
    except Exception as e:
        raise HTTPException(500, f"Downgrade error: {e}")
