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
            cur.execute(
                """
                SELECT id, email, public_slug, bio, website, photo_url, cv_url, provincia, especialidad
                  FROM mediadores
                 WHERE email = LOWER(%s);
                """,
                (email,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "No encontrado")
    return {
        "ok": True,
        "perfil": {
            "id": row[0],
            "email": row[1],
            "public_slug": row[2],
            "bio": row[3] or "",
            "website": row[4] or "",
            "photo_url": row[5] or "",
            "cv_url": row[6] or "",
            "provincia": row[7] or "",
            "especialidad": row[8] or "",
        },
    }

@perfil_router.post("")
def save_perfil(body: PerfilIn):
    email = body.email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id FROM mediadores WHERE email=LOWER(%s);", (email,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Mediador no encontrado")
            cur.execute(
                """
                UPDATE mediadores SET
                    public_slug = COALESCE(%s, public_slug),
                    bio         = COALESCE(%s, bio),
                    website     = COALESCE(%s, website),
                    photo_url   = COALESCE(%s, photo_url),
                    cv_url      = COALESCE(%s, cv_url)
                 WHERE
