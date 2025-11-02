# db.py — conexión PostgreSQL para MEDIAZION
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")  # p.ej. postgresql://user:pass@host:5432/dbname

def pg_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está definido en las variables de entorno")
    # Si usas la URL externa de Render, añade ?sslmode=require en el DSN o define PGSSLMODE=require
    return psycopg2.connect(DATABASE_URL, connect_timeout=10, cursor_factory=RealDictCursor)
