# mediadores_routes.py — estado PRO/BASIC + listado público (Directorio)

from fastapi import APIRouter, HTTPException
from pydantic import EmailStr
from typing import Optional, List
from db import pg_conn

mediadores_router = APIRouter()

# ---------- ESTADO MEDIADOR ----------
@mediadores_router.get("/mediadores/status")
def mediador_status(email: EmailStr):
    """
    Devuelve el estado PRO/BÁSICO del mediador (panel).
    """
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                SELECT subscription_status, status
                  FROM mediadores
                 WHERE LOWER(email)=LOWER(%s)
                """,
                (email,),
            )
            row = cur.fetchone()

        if not row:
            return {"email": email, "subscription_status": "none", "status": "missing"}

        subscription_status, status = row

        return {
            "email": email,
            "subscription_status": subscription_status or "none",
            "status": status or "active",
        }

    except Exception as e:
        raise HTTPException(500, f"Error consultando estado: {e}")


# ---------- ACTIVAR TRIAL ----------
@mediadores_router.post("/mediadores/set_trial")
def set_trial(email: EmailStr, days: int = 7):
    """
    Activa PRO (trial) del mediador por X días.
    """
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                UPDATE mediadores
                   SET subscription_status='trialing',
                       status='active',
                       trial_used=true,
                       trial_start=NOW(),
                       trial_end=NOW() + (%s || ' days')::interval
                 WHERE LOWER(email)=LOWER(%s)
                """,
                (days, email),
            )
            updated = cur.rowcount
            cx.commit()

        if updated == 0:
            raise HTTPException(404, "Mediador no encontrado")

        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Error activando trial: {e}")


# ---------- LISTADO PÚBLICO (Directorio) ----------
@mediadores_router.get("/mediadores/public")
def mediadores_public(
    q: Optional[str] = None,
    provincia: Optional[str] = None,
    especialidad: Optional[str] = None,
    limit: int = 100,
):
    """
    Directorio público de mediadores activos.
    Filtra por nombre, bio, provincia o especialidad.
    """
    sql = """
    SELECT id, name, public_slug, bio, website, photo_url, cv_url, provincia, especialidad
      FROM mediadores
     WHERE status='active'
    """
    params: List = []

    if q:
        sql += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(bio) LIKE LOWER(%s))"
        like = f"%{q}%"
        params += [like, like]

    if provincia:
        sql += " AND LOWER(provincia)=LOWER(%s)"
        params.append(provincia.lower())

    if especialidad:
        sql += " AND LOWER(especialidad)=LOWER(%s)"
        params.append(especialidad.lower())

    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(min(200, max(1, limit)))

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
    except Exception as e:
        raise HTTPException(500, f"Error listando mediadores: {e}")

    items = []
    for r in rows:
        items.append(
            {
                "id": r[0],
                "name": r[1],
                "public_slug": r[2],
                "bio": r[3] or "",
                "website": r[4] or "",
                "photo_url": r[5] or "",
                "cv_url": r[6] or "",
                "provincia": r[7] or "",
                "especialidad": r[8] or "",
            }
        )

    return {"ok": True, "items": items}
