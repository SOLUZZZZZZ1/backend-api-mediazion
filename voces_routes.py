# src/voces_routes.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from datetime import datetime
import re
from db import pg_conn

voces_router = APIRouter()

class PostIn(BaseModel):
    email: EmailStr
    title: str
    summary: str
    content: str
    accept_terms: bool = False

def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\\s_-]", "", text or "")
    s = re.sub(r"\\s+", "-", s.strip().lower())
    return s or "articulo"

@vocab_router.post("/voces/post")
def crear_o_actualizar_post(body: PostIn):
    if not body.accept_terms:
        raise HTTPException(status_code=400, detail="Debes aceptar las condiciones")
    # comprobaremos si el autor es PRO en tu lógica (si tienes /api/mediadores/status). Aquí se omite para simplificar.

    slug = _slugify(body.title)
    with pg_conn() as cx, cx.cursor() as cur:
        # Resolver colisión de slug
        cur.execute("SELECT id FROM posts WHERE slug=%s", (slug,))
        row = cur.fetchone()
        if row:
            slug = f"{slug}-{int(datetime.utcnow().timestamp())}"

        cur.execute("""
          INSERT INTO posts (author_email, title, slug, summary, content, status, created_at, published_at)
          VALUES (%s,%s,%s,%s,%s,'published', NOW(), NOW())
          RETURNING id
        """, (body.email.lower(), body.title.strip(), slug, body.summary.strip(), body.content))
        pid = cur.fetchone()[0]
        cx.commit()
    return {"ok": True, "id": pid, "slug": slug}

@voces_router.get("/voces/public")
def listar_public():
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("""
            SELECT id, title, slug, summary, author_email, to_char(COALESCE(published_at, NOW()), 'YYYY-MM-DD') as published
            FROM posts
            WHERE status='published'
            ORDER BY published_at DESC, id DESC
            LIMIT 50
        """)
        rows = cur.fetchall()
    items = [
        {"id": r[0], "title": r[1], "slug": r[2], "summary": r[3], "author_email": r[4], "published_at": r[5]}
        for r in rows or []
    ]
    return {"ok": True, "items": items}

@voces_router.get("/voces/{slug}")
def detalle(slug: str):
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("""
            SELECT id, title, slug, summary, content, author_email, to_char(COALESCE(published_at, NOW()), 'YYYY-MM-DD') as published
            FROM posts WHERE slug=%s AND status='published' LIMIT 1
        """, (slug,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Artículo no encontrado")
    return {
        "ok": True,
        "post": {
            "id": r[0], "title": r[1], "slug": r[2], "summary": r[3],
            "content": r[4], "author_email": r[5], "published_at": r[6]
        }
    }
