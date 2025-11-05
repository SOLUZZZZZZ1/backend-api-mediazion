# migrate_routes.py — migración mínima para columnas nuevas
import os
from fastapi import APIRouter, Header, HTTPException
from db import pg_conn

router = APIRouter(prefix="/admin/migrate", tags=["admin-migrate"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

SQL_ADD_COLS = """
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS dni_cif TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS tipo TEXT;
ALTER TABLE mediadores ADD COLUMN IF NOT EXISTS password_hash TEXT;
"""

@router.post("/add_cols")
def add_cols(x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(SQL_ADD_COLS)
            cx.commit()
        return {"ok": True, "message": "Columnas añadidas (dni_cif, tipo, password_hash)"}
    except Exception as e:
        raise HTTPException(500, f"Migration error: {e}")
