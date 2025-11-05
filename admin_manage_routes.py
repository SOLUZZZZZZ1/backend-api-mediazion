# admin_manage_routes.py — exists + delete por email (solo admin)
from fastapi import APIRouter, HTTPException, Header, Query
from db import pg_conn
import os

admin_manage = APIRouter(prefix="/admin/mediadores", tags=["admin-mediadores"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

@admin_manage.get("/exists")
def exists(email: str = Query(...), x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT 1 FROM mediadores WHERE email=LOWER(%s) LIMIT 1", (email.lower().strip(),))
            return {"ok": True, "exists": bool(cur.fetchone())}

@admin_manage.delete("/delete")
def delete(email: str = Query(...), x_admin_token: str | None = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("DELETE FROM mediadores WHERE email=LOWER(%s)", (email.lower().strip(),))
            n = cur.rowcount
            cx.commit()
    return {"ok": True, "deleted": n}
