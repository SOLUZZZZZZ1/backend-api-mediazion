# utils_pg.py — crea/asegura tablas en PostgreSQL
from db import pg_conn

def ensure_db():
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS mediadores (
                id SERIAL PRIMARY KEY,
                name TEXT,
                email TEXT UNIQUE,
                especialidad TEXT,
                provincia TEXT,
                approved BOOLEAN DEFAULT TRUE,
                status TEXT DEFAULT 'active',
                subscription_status TEXT DEFAULT 'none',
                trial_used BOOLEAN DEFAULT FALSE,
                trial_start TIMESTAMP NULL,
                subscription_id TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)
            cx.commit()
