# migrate_routes.py — Migraciones Mediazion (voces, mediadores, perfil, agenda)
from fastapi import APIRouter, HTTPException
from db import pg_conn

router = APIRouter()

# ------------------ VOCES (ya estaba) ------------------
SQL_VOCES = """
CREATE TABLE IF NOT EXISTS posts (
  id SERIAL PRIMARY KEY,
  author_email TEXT NOT NULL,
  title TEXT NOT NULL,
  slug TEXT UNIQUE,
  summary TEXT,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TIMESTAMP DEFAULT NOW(),
  published_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS post_comments (
  id SERIAL PRIMARY KEY,
  post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  author_email TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
"""

# ------------------ PERFIL (ya estaba) ------------------
SQL_PERFIL = """
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS cv_url TEXT;
"""

# ------------------ AGENDA (NUEVA MIGRACIÓN) ------------------
SQL_AGENDA = """
CREATE TABLE IF NOT EXISTS agenda (
  id SERIAL PRIMARY KEY,
  mediador_email TEXT NOT NULL,
  titulo TEXT NOT NULL,
  descripcion TEXT,
  fecha TIMESTAMP NOT NULL,
  tipo TEXT NOT NULL, -- cita, recordatorio, videollamada
  caso_id INTEGER,
  created_at TIMESTAMP DEFAULT NOW(),
  FOREIGN KEY (caso_id) REFERENCES casos(id) ON DELETE SET NULL
);
"""

# ============================================================
# ====================== ENDPOINTS ===========================
# ============================================================

@router.post("/admin/migrate/voces/init")
def init_voces():
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(SQL_VOCES)
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error migrando VOCES: {e}")
    return {"ok": True, "msg": "Voces OK"}


@router.post("/admin/migrate/perfil/add_cols")
def perfil_cols():
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(SQL_PERFIL)
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error migrando PERFIL: {e}")
    return {"ok": True, "msg": "Perfil columnas OK"}


@router.post("/admin/migrate/agenda/init")
def init_agenda():
    """
    Crear tabla agenda.
    """
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(SQL_AGENDA)
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error migrando AGENDA: {e}")
    return {"ok": True, "msg": "Agenda creada OK"}
