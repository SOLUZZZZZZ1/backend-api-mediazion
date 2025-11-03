from fastapi import APIRouter
from db import pg_conn

db_router = APIRouter()

@db_router.get("/db/health")
def db_health():
    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute("SELECT 1 AS ok;")
                row = cur.fetchone()
        return {"ok": True, "db": bool(row)}
    except Exception as e:
        return {"ok": False, "error": str(e)}