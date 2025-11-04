# migrate_routes.py — ejecuta la migración de la tabla mediadores (solo admin)
from fastapi import APIRouter, Header, HTTPException
from db import pg_conn
import os

router = APIRouter(prefix="/admin/migrate", tags=["admin-migrate"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

SQL = """
CREATE TABLE IF NOT EXISTS mediadores (
  id SERIAL PRIMARY KEY,
  name TEXT,
  email TEXT UNIQUE,
  phone TEXT,
  provincia TEXT,
  especialidad TEXT,
  approved BOOLEAN DEFAULT TRUE,
  status TEXT DEFAULT 'active',
  subscription_status TEXT DEFAULT 'none',
  trial_used BOOLEAN DEFAULT FALSE,
  trial_start TIMESTAMP NULL,
  subscription_id TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS provincia TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS especialidad TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS subscription_id TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT TRUE;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'none';
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS trial_used BOOLEAN DEFAULT FALSE;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS trial_start TIMESTAMP NULL;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE tablename='mediadores' AND indexname='mediadores_email_key'
  ) THEN
    CREATE UNIQUE INDEX mediadores_email_key ON mediadores (LOWER(email));
  END IF;
END$$;
"""

@router.post("/db")
def migrate_db(x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL)
            cx.commit()
        return {"ok": True, "message": "Migración ejecutada correctamente"}
    except Exception as e:
        raise HTTPException(500, f"Migration error: {e}")
