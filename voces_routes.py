# voces_routes.py — creación y listado de artículos (Voces)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
from datetime import datetime
import re

voces_router = APIRouter()

# ---------- MODELO ----------
class VozIn(BaseModel):
    email: EmailStr
    title: str
    summary: str
    content: str
    accept_terms: bool = False

# ---------- SLUG ----------
def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\-\s]", "", text)
    s = re.sub(r"\s+", "-", s.strip().lower())
    return s or "publicacion"

# ---------- CREAR PUBLICACIÓN ----------
@voces_router.post("/voces/post")
def crear_post(body: VozIn):
    if not body.accept_terms:
        raise HTTPException(400, "Debes aceptar las condiciones de publicación.")

    slug = slugify(body.title)

    try:
        with pg_conn() as cx, cx.cursor() as cur:

            # aseguramos slug único
            cur.execute("SELECT id FROM posts WHERE slug=%s", (slug,))
            if cur.fetchone():
                slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

            cur.execute(
                """
                INSERT INTO posts (author_email,title,slug,summary,content,status,created_at,published_at)
                VALUES (%s,%s,%s,%s,%s,'published',NOW(),NOW())
                RETURNING id
                """,
                (body.email.lower(), body.title, slug, body.summary, body.content)
            )
            pid = cur.fetchone()[0]
            cx.commit()

        return {"ok": True, "id": pid, "slug": slug}

    except Exception as e:
        raise HTTPException(500, f"Error creando post: {e}")

# ---------- LISTADO PÚBLICO ----------
@voces_router.get("/voces/public")
def listar_public():
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, slug, summary, author_email,
                       to_char(published_at,'YYYY-MM-DD')
                FROM posts
                WHERE status='published'
                ORDER BY published_at DESC
                LIMIT 50
                """
            )
            rows = cur.fetchall()

        items = [
            {
                "id": r[0],
                "title": r[1],
                "slug": r[2],
                "summary": r[3],
                "author_email": r[4],
                "published_at": r[5],
            }
            for r in rows
        ]
        return {"ok": True, "items": items}

    except Exception as e:
        raise HTTPException(500, f"Error listando publicaciones: {e}")

# ---------- DETALLE ----------
@voces_router.get("/voces/{slug}")
def detalle_publicacion(slug: str):
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                SELECT id,title,slug,summary,content,author_email,
                       to_char(published_at,'YYYY-MM-DD')
                FROM posts
                WHERE slug=%s AND status='published'
                LIMIT 1
                """,
                (slug,)
            )
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "Publicación no encontrada")

        return {
            "ok": True,
            "post": {
                "id": r[0],
                "title": r[1],
                "slug": r[2],
                "summary": r[3],
                "content": r[4],
                "author_email": r[5],
                "published_at": r[6],
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error obteniendo el artículo: {e}")
