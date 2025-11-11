# migrate_routes.py — Migraciones idempotentes (mediadores + voces + perfil) + utilidades admin
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException
from db import pg_conn
import bcrypt  # para setear contraseñas temporales

router = APIRouter(prefix="/admin/migrate", tags=["admin-migrate"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

# --- Autenticación simple admin ---
def _auth(x_admin_token: str | None):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")

# ---------------- MEDIADORES ----------------
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
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS password_must_change BOOLEAN DEFAULT FALSE;
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

# ---------------- VOCES ----------------
SQL_VOCES = """
CREATE TABLE IF NOT EXISTS posts (
  id SERIAL PRIMARY KEY,
  author_email  TEXT NOT NULL,
  title         TEXT NOT NULL,
  slug          TEXT UNIQUE,
  summary       TEXT,
  content       TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'draft',
  created_at    TIMESTAMP DEFAULT NOW(),
  published_at  TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS post_comments (
  id SERIAL PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  author_email TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
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

# ---------------- PERFIL ----------------
SQL_PERFIL_COLS = """
ALTER TABLE mediadores
  ADD COLUMN IF NOT EXISTS public_slug TEXT,
  ADD COLUMN IF NOT EXISTS bio TEXT,
  ADD COLUMN IF NOT EXISTS website TEXT,
  ADD COLUMN IF NOT EXISTS photo_url TEXT,
  ADD COLUMN IF NOT EXISTS cv_url TEXT;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname = 'mediadores_public_slug_lower_ux'
  ) THEN
    CREATE UNIQUE INDEX mediadores_public_slug_lower_ux ON mediadores ((LOWER(public_slug)));
  END IF;
END$$;
"""

@router.post("/perfil/add_cols")
def perfil_add_cols(x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_PERFIL_COLS)
            cx.commit()
        return {"status": "ok", "message": "Columnas de perfil (alias/bio/web/foto/cv) aseguradas."}
    except Exception as e:
        raise HTTPException(500, f"Perfil migration error: {e}")

# ---------------- LIMPIEZA / UTILIDADES ADMIN ----------------

@router.post("/mediadores/clear_all")
def clear_all_mediadores(x_admin_token: str | None = Header(None)):
    """Borra TODOS los mediadores (solo pruebas)."""
    _auth(x_admin_token)
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute("DELETE FROM mediadores;")
            cx.commit()
        return {"status": "ok", "message": "Todos los mediadores han sido eliminados."}
    except Exception as e:
        raise HTTPException(500, f"Clear error: {e}")

@router.post("/mediadores/set_temp_password")
def set_temp_password(email: str, temp_password: str, x_admin_token: str | None = Header(None)):
    """Fija una contraseña temporal para un mediador existente (por email)."""
    _auth(x_admin_token)
    if not email or not temp_password:
        raise HTTPException(400, "email y temp_password son obligatorios")
    try:
        hashed = bcrypt.hashpw(temp_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    "UPDATE mediadores SET password_hash=%s WHERE LOWER(email)=LOWER(%s);",
                    (hashed, email),
                )
                updated = cur.rowcount
            cx.commit()
        if updated == 0:
            raise HTTPException(404, "User not found")
        return {"status": "ok", "email": email, "message": "Contraseña temporal aplicada."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Set password error: {e}")

# ---------------- ACTIVAR TRIAL PRO 7 DÍAS ----------------

@router.post("/mediadores/set_trial")
def set_trial(email: str, days: int = 7, x_admin_token: str | None = Header(None)):
    """Activa periodo de prueba (trial PRO) para un mediador existente."""
    _auth(x_admin_token)
    if not email:
        raise HTTPException(400, "email requerido")
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute("""
                    UPDATE mediadores
                       SET subscription_status='trialing',
                           status='active',
                           trial_used=FALSE,
                           trial_start=%s,
                           trial_end=%s
                     WHERE LOWER(email)=LOWER(%s);
                """, (now, end, email))
                n = cur.rowcount
            cx.commit()
        if n == 0:
            raise HTTPException(404, "Mediador no encontrado")
        return {"ok": True, "email": email, "trial_until": end.isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error activando trial: {e}")
