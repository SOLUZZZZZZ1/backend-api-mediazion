
# voces_routes.py — Gestión unificada de VOCES para Mediazion
# -----------------------------------------------------------
# Backend REAL: PostgreSQL directo con pg_conn() (sin ORM).
# Compatible con:
#   - VocesNuevo.jsx  (crear + publicar)
#   - VocesPublic.jsx (listar publicados)
#   - VocesDetalle.jsx (detalle + comentarios)
#
# NOTA: La tabla "posts" + "post_comments" ya se crea desde /admin/migrate/voces/init

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr
from db import pg_conn
from datetime import datetime
import re

voces_router = APIRouter(prefix="/voces", tags=["voces"])


# ---------------- Helpers -----------------

def _slugify(title: str) -> str:
    """Genera un slug único basado en el título."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not base:
        base = "post"
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{base}-{ts}"


def _row_dict(row, cols):
    """Convierte una row (tuple o dict) a dict estándar."""
    if isinstance(row, dict):
        return row
    return {col: row[i] for i, col in enumerate(cols)}


# ---------------- Modelos -----------------

class VozCreate(BaseModel):
    email: EmailStr
    title: str
    summary: str | None = None
    content: str


class CommentIn(BaseModel):
    email: EmailStr
    slug: str
    content: str


# ---------------- ENDPOINTS -----------------

@voces_router.post("")
def crear_borrador(body: VozCreate):
    """Paso 1: crear borrador (status='draft')."""
    email = body.email.strip().lower()
    title = body.title.strip()
    content = body.content.strip()

    if not email or not title or not content:
        raise HTTPException(400, "Falta email, título o contenido.")

    slug = _slugify(title)

    SQL = """
        INSERT INTO posts (author_email, title, slug, summary, content, status, created_at)
        VALUES (LOWER(%s), %s, %s, %s, %s, 'draft', NOW())
        RETURNING id, slug;
    """

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(SQL, (email, title, slug, body.summary, content))
            row = cur.fetchone()
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"No se pudo crear el borrador: {e}")

    return {"ok": True, "id": row[0], "slug": row[1]}


@voces_router.post("/{post_id}/publish")
def publicar_post(post_id: int, email: EmailStr = Query(...)):
    """Paso 2: publicar (status='published')."""
    email_norm = email.lower()

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            # verificar autor
            cur.execute("SELECT id, slug, author_email FROM posts WHERE id=%s;", (post_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Post no encontrado.")

            pid, slug, author = row
            if author.lower() != email_norm:
                raise HTTPException(403, "No puedes publicar un post de otro usuario.")

            # publicar
            cur.execute("""
                UPDATE posts
                   SET status='published',
                       published_at=NOW()
                 WHERE id=%s;
            """, (pid,))
            cx.commit()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error publicando: {e}")

    return {"ok": True, "id": post_id, "slug": slug}


@voces_router.get("/public")
def listar_public(limit: int = 20):
    """Listado público de artículos."""
    COLS = ["id", "author_email", "title", "slug", "summary", "published_at"]

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("""
                SELECT id, author_email, title, slug, summary, published_at
                  FROM posts
                 WHERE status='published'
                 ORDER BY published_at DESC NULLS LAST
                 LIMIT %s;
            """, (limit,))
            rows = cur.fetchall() or []
    except Exception as e:
        raise HTTPException(500, f"Error listando publicaciones: {e}")

    items = []
    for r in rows:
        d = _row_dict(r, COLS)
        if d["published_at"]:
            d["published_at"] = d["published_at"].isoformat()
        items.append(d)

    return {"ok": True, "items": items}


@voces_router.get("/{slug}")
def detalle_publicacion(slug: str):
    """Detalle de un post (público)."""
    COLS = ["id", "author_email", "title", "slug", "summary", "content",
            "status", "created_at", "published_at"]

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("""
                SELECT id, author_email, title, slug, summary, content,
                       status, created_at, published_at
                  FROM posts
                 WHERE slug=%s;
            """, (slug,))
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(500, f"Error cargando post: {e}")

    if not row:
        raise HTTPException(404, "Artículo no encontrado.")

    d = _row_dict(row, COLS)
    if d["published_at"]:
        d["published_at"] = d["published_at"].isoformat()

    return {"ok": True, "post": d}


@voces_router.get("/{slug}/comments")
def listar_comentarios(slug: str):
    """Comentarios del artículo."""
    COLS = ["id", "author_email", "content", "created_at"]

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            # obtener id del post
            cur.execute("SELECT id FROM posts WHERE slug=%s;", (slug,))
            p = cur.fetchone()
            if not p:
                return {"items": []}

            post_id = p[0]

            cur.execute("""
                SELECT id, author_email, content, created_at
                  FROM post_comments
                 WHERE post_id=%s
                 ORDER BY created_at ASC;
            """, (post_id,))
            rows = cur.fetchall() or []

    except Exception as e:
        raise HTTPException(500, f"Error listando comentarios: {e}")

    items = []
    for r in rows:
        d = _row_dict(r, COLS)
        if d["created_at"]:
            d["created_at"] = d["created_at"].isoformat()
        items.append(d)

    return {"items": items}


@voces_router.post("/comment")
def crear_comentario(body: CommentIn):
    """Crear comentario en un post existente."""
    email = body.email.lower()
    content = body.content.strip()

    if not email or not content:
        raise HTTPException(400, "Faltan datos.")

    # obtener post_id por slug
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("SELECT id FROM posts WHERE slug=%s;", (body.slug,))
            p = cur.fetchone()
            if not p:
                raise HTTPException(404, "Post no encontrado.")

            post_id = p[0]

            cur.execute("""
                INSERT INTO post_comments (post_id, author_email, content, created_at)
                VALUES (%s, %s, %s, NOW())
                RETURNING id, author_email, content, created_at;
            """, (post_id, email, content))

            row = cur.fetchone()
            cx.commit()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error creando comentario: {e}")

    return {
        "ok": True,
        "comment": {
            "id": row[0],
            "author_email": row[1],
            "content": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
        },
    }
