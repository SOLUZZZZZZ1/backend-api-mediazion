# migrate_routes.py — migraciones idempotentes (mediadores + voces + utilidades)
import os
from fastapi import APIRouter, Header, HTTPException
from db import pg_conn

router = APIRouter(prefix="/admin/migrate", tags=["admin-migrate"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

def _auth(x_admin_token: str | None):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")

# ---------------- Mediadores (ya lo tenías) ----------------
SQL_CREATE_MEDIADORES = """
CREATE TABLE IF NOT EXISTS mediadores (
  id SERIAL PRIMARY KEY
);
"""

SQL_ADD_COLS_MEDIADORES = """
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

@router.post("/mediadores/add_cols")
def add_cols_mediadores(x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_CREATE_MEDIADORES)
                cur.execute(SQL_ADD_COLS_MEDIADORES)
                cur.execute(SQL_UNIQ_EMAIL)
            cx.commit()
        return {"status": "ok", "message": "Columnas/índice asegurados (mediadores)."}
    except Exception as e:
        raise HTTPException(500, f"Migration error: {e}")

@router.post("/mediadores/downgrade_trials")
def downgrade_trials(x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_LOWER_TRIAL)
                n = cur.rowcount
            cx.commit()
        return {"status": "ok", "lowered": n}
    except Exception as e:
        raise HTTPException(500, f"Downgrade error: {e}")

# ---------------- VOCES (posts + comentarios) ----------------
SQL_VOCES = """
-- Tabla de publicaciones
CREATE TABLE IF NOT EXISTS posts (
  id            SERIAL PRIMARY KEY,
  author_email  TEXT NOT NULL,
  title         TEXT NOT NULL,
  slug          TEXT UNIQUE,
  summary       TEXT,
  content       TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'draft',
  created_at    TIMESTAMP DEFAULT NOW(),
  published_at  TIMESTAMP NULL
);

-- Índices útiles
CREATE INDEX IF NOT EXISTS posts_status_idx  ON posts (status);
CREATE INDEX IF NOT EXISTS posts_created_idx ON posts (created_at DESC);

-- Unicidad robusta por slug (lower)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'posts_slug_lower_ux'
  ) THEN
    CREATE UNIQUE INDEX posts_slug_lower_ux ON posts ((LOWER(slug)));
  END IF;
END$$;

-- Tabla de comentarios
CREATE TABLE IF NOT EXISTS post_comments (
  id           SERIAL PRIMARY KEY,
  post_id      INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  author_email TEXT NOT NULL,
  content      TEXT NOT NULL,
  created_at   TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS post_comments_post_idx ON post_comments (post_id, created_at DESC);
"""

@router.post("/voces/init")
def voces_init(x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_VOCES)
            cx.commit()
        return {"status": "ok", "message": "Voces (posts + comments) listo."}
    except Exception as e:
        raise HTTPException(500, f"Voces init error: {e}")

# ---------------- Utilidad: idempotencia webhooks ----------------
SQL_STRIPE_EVENTS = """
CREATE TABLE IF NOT EXISTS stripe_events (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMP DEFAULT NOW()
);
"""

@router.post("/util/stripe_events")
def ensure_stripe_events(x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_STRIPE_EVENTS)
            cx.commit()
        return {"status": "ok", "message": "Tabla stripe_events asegurada."}
    except Exception as e:
        raise HTTPException(500, f"Stripe events error: {e}")
