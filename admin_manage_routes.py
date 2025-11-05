# admin_manage_routes.py — utilidades de administración de mediadores (USO TEMPORAL)
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Header, HTTPException, Query
from db import pg_conn

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
    """
    Borra TODO el contenido de la tabla mediadores y reinicia el contador de IDs.
    ¡PELIGRO! Úsalo solo en entornos de prueba o si estás seguro.
    """
    _auth(x_admin_token)
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("TRUNCATE TABLE mediadores RESTART IDENTITY;")
        cx.commit()
    return {"ok": True, "message": "Tabla 'mediadores' vaciada y secuencia reiniciada."}

@admin_manage.post("/purge_by_domain")
def purge_by_domain(domain: str = Query(..., description="Ej: @mailinator.com"),
                    x_admin_token: str | None = Header(None)):
    """
    Elimina todos los mediadores cuyo email termine en un dominio concreto.
    Ejemplo: /admin/mediadores/purge_by_domain?domain=@mailinator.com
    """
    _auth(x_admin_token)
    if not domain.startswith("@"):
        domain = "@" + domain
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("DELETE FROM mediadores WHERE LOWER(email) LIKE LOWER(%s);", (f"%{domain.lower()}",))
            n = cur.rowCount if hasattr(cur, "rowCount") else cur.rowcount
        cx.commit()
    return {"ok": True, "deleted": n, "domain": domain}

@admin_manage.post("/purge_where")
def purge_where(status: str = Query(None, description="status=active/disabled/canceled"),
                subscription_status: str = Query(None, description="none/trialing/active/expired"),
                older_than_days: int = Query(None, ge=1),
                x_admin_token: str | None = Header(None)):
    """
    Borrado selectivo por estado y/o antigüedad de created_at.
    - status: 'active' | 'disabled' | 'canceled'
    - subscription_status: 'none' | 'trialing' | 'active' | 'expired'
    - older_than_days: borra los que sean más antiguos que hoy - N días
    """
    _auth(x_admin_token)
    clauses = []
    params = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    if subscription_status:
        clauses.append("subscription_status = %s")
        params.append(subscription_status)
    if older_than_days:
        clauses.append("created_at < %s")
        params.append(datetime.now(timezone.utc) - timedelta(days=older_than_days))

    if not clauses:
        raise HTTPException(400, "Debes indicar al menos un filtro (status, subscription_status o older_than_days).")

    where = " AND ".join(clauses)
    sql = f"DELETE FROM mediadores WHERE {where};"

    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(sql, tuple(params))
            n = cur.rowcount
        cx.commit()
    return {"ok": True, "deleted": n, "filters": {"status": status, "subscription_status": subscription_status, "older_than_days": older_than_days}}
