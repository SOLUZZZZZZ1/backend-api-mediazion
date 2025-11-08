# admin_manage_routes.py — utilidades admin mediadores (incl. purge_email)
import os
from fastapi import APIRouter, Header, HTTPException, Query
from db import pg_conn
from datetime import datetime, timedelta, timezone

admin_manage = APIRouter(prefix="/admin/mediadores", tags=["admin-mediadores"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

def _auth(x_admin_token: str | None):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")

@admin_manage.get("/count")
def count_all(x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM mediadores;")
            n = cur.fetchone()[0]
    return {"ok": True, "count": n}

@admin_manage.post("/purge_all")
def purge_all(x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("TRUNCATE TABLE mediadores RESTART IDENTITY;")
        cx.commit()
    return {"ok": True, "message": "Tabla mediadores vaciada."}

@admin_manage.post("/purge_by_domain")
def purge_by_domain(domain: str = Query(..., description="Ej: gmail.com o @gmail.com"),
                    x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    d = domain if domain.startswith("@") else f"@{domain}"
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("DELETE FROM mediadores WHERE LOWER(email) LIKE LOWER(%s);", (f"%{d.lower()}",))
            n = cur.rowcount
        cx.commit()
    return {"ok": True, "deleted": n, "domain": d}

@admin_manage.post("/purge_where")
def purge_where(status: str = Query(None), subscription_status: str = Query(None),
                older_than_days: int = Query(None, ge=1),
                x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    clauses, params = [], []
    if status:
        clauses.append("status=%s"); params.append(status)
    if subscription_status:
        clauses.append("subscription_status=%s"); params.append(subscription_status)
    if older_than_days:
        clauses.append("created_at < %s")
        params.append(datetime.now(timezone.utc) - timedelta(days=older_than_days))
    if not clauses:
        raise HTTPException(400, "Indica al menos un filtro.")
    sql = f"DELETE FROM mediadores WHERE {' AND '.join(clauses)};"
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(sql, tuple(params))
            n = cur.rowcount
        cx.commit()
    return {"ok": True, "deleted": n}

# NUEVO: borrar por email exacto
@admin_manage.post("/purge_email")
def purge_email(email: str = Query(...), x_admin_token: str | None = Header(None)):
    _auth(x_admin_token)
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("DELETE FROM mediadores WHERE LOWER(email)=LOWER(%s);", (email,))
            n = cur.rowcount
        cx.commit()
    return {"ok": True, "deleted": n, "email": email}
