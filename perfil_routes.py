# perfil_routes.py — Gestión de perfil del mediador (alias/bio/web/foto/cv) + listado público
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from db import pg_conn

perfil_router = APIRouter(prefix="/perfil", tags=["perfil"])

class PerfilIn(BaseModel):
    email: str
    public_slug: Optional[str] = None
    bio: Optional[str] = None
    website: Optional[str] = None
    photo_url: Optional[str] = None
    cv_url: Optional[str] = None

@perfil_router.get("")
def get_perfil(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                SELECT id, email, public_slug, bio, website, photo_url, cv_url, provincia, especialidad
                  FROM mediadores
                 WHERE email = LOWER(%s);
            """, (email,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "No encontrado")
    if isinstance(row, dict):
        return {"ok": True, "perfil": row}
    return {"ok": True, "perfil": {
        "id": row[0], "email": row[1], "public_slug": row[2],
        "bio": row[3] or "", "website": row[4] or "",
        "photo_url": row[5] or "", "cv_url": row[6] or "",
        "provincia": row[7] or "", "especialidad": row[8] or ""
    }}

@perfil_router.post("")
def save_perfil(body: PerfilIn):
    email = body.email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur execute("SELECT id FROM mediadores WHERE email=LOWER(%s);", (email,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Mediador no encontrado")
            cur.execute("""
                UPDATE mediadores SET
                    public_slug = COALESCE(%s, public_slug),
                    bio         = COALESCE(%s, bio),
                    website     = COALESCE(%s, website),
                    photo_url   = COALESCE(%s, photo_url),
                    cv_url      = COALESCE(%s, cv_url)
                 WHERE email = LOWER(%s);
            """, (body.public_slug, body.bio, body.website, body.photo_url, body.cv_url, email))
        cx.commit()
    return {"ok": True}

@perfil_router.get("/public")
def list_public(q: Optional[str]=None, provincia: Optional[str]=None, especialidad: Optional[str]=None, limit: int=100):
    sql = """
    SELECT id, name, public_slug, bio, website, photo_url, cv_url, provincia, especialidad
      FROM mediadores
     WHERE approved IS TRUE
       AND (subscription_status IN ('active','trialing'))
    """
    params = []
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

    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

    items: List[dict] = []
    for r in rows:
        if isinstance(r, dict):
            items.append(r)
        else:
            items.append({
                "id": r[0], "name": r[1], "public_slug": r[2],
                "bio": r[3] or "", "website": r[4] or "",
                "photo_url": r[5] or "", "cv_url": r[6] or "",
                "provincia": r[7] or "", "especialidad": r[8] or ""
            })
    return items
