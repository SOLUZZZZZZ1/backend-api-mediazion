# voces_routes.py — Publicación de artículos (solo PRO) + lectura pública
import os, re
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field, EmailStr
from db import pg_conn

voces_router = APIRouter(prefix="/voces", tags=["voces"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "8354Law18354Law1@"

BANNED = {"política", "partido", "campaña electoral"}  # filtro simple (puedes ampliarlo)

def _slugify(t: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\-\s_]", "", (t or "").strip().lower())
    s = re.sub(r"[\s_]+", "-", s)
    return s or "articulo"

def _is_pro(email: str) -> bool:
    q = """
        SELECT subscription_status
          FROM mediadores
         WHERE LOWER(email)=LOWER(%s)
    """
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute(q, (email,))
        row = cur.fetchone()
        if not row:
            return False
        subs = row[0] if not isinstance(row, dict) else row["subscription_status"]
        return subs in ("trialing", "active")

class PostIn(BaseModel):
    email: EmailStr = Field(..., description="Email del autor PRO")
    title: str = Field(..., min_length=4, max_length=160)
    slug: Optional[str] = Field(None, description="Opcional; si no viene, se genera")
    summary: str = Field(..., min_length=10, max_length=400)
    content: str = Field(..., min_length=50)
    accept_terms: bool = Field(..., description="Debe ser true para publicar")
    status: Optional[str] = Field("published", description="published|draft (opcional)")

class PostOut(BaseModel):
    title: str
    slug: str
    author_email: str
    summary: str
    content: Optional[str] = None
    published_at: Optional[str] = None

def _moderation_check(texts: List[str]):
    blob = " ".join(texts).lower()
    for w in BANNED:
        if w in blob:
            raise HTTPException(400, f"Contenido no permitido: “{w}”")

@voces_router.post("/post")
def create_or_update_post(body: PostIn):
    if not body.accept_terms:
        raise HTTPException(400, "Debes aceptar las condiciones antes de publicar.")
    if not _is_pro(body.email):
        raise HTTPException(403, "Solo los mediadores PRO pueden publicar.")

    _moderation_check([body.title, body.summary, body.content])

    slug = (body.slug or _slugify(body.title))
    # garantizar unicidad añadiendo sufijo si existe
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("SELECT id FROM posts WHERE slug=%s;", (slug,))
        if cur.fetchone() is not None:
            base = slug
            i = 2
            while True:
                slug = f"{base}-{i}"
                cur.execute("SELECT id FROM posts WHERE slug=%s;", (slug,))
                if cur.fetchone() is None:
                    break
                i += 1

        now = datetime.now(timezone.utc)
        # upsert sencillo por (title+email) o crear siempre uno nuevo; aquí creamos nuevo siempre
        cur.execute("""
            INSERT INTO posts (author_email, title, slug, summary, content, status, created_at, published_at)
            VALUES (%s,%s,%s,%s,%s,%s,NOW(), %s)
            RETURNING id;
        """, (
            body.email.strip().lower(),
            body.title.strip(),
            slug,
            body.summary.strip(),
            body.content.strip(),
            body.status if body.status in ("published", "draft") else "published",
            now if (body.status or "published") == "published" else None
        ))
        pid = cur.fetchone()[0]
        cx.commit()

    return {"ok": True, "id": pid, "slug": slug}

@voces_router.get("/public")
def list_public(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=50)):
    off = (page - 1) * size
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("""
            SELECT title, slug, summary, author_email,
                   COALESCE(to_char(published_at, 'YYYY-MM-DD'), '') AS pub
              FROM posts
             WHERE status='published'
             ORDER BY published_at DESC NULLS LAST, id DESC
             LIMIT %s OFFSET %s;
        """, (size, off))
        rows = cur.fetchall() or []
    out = []
    for r in rows:
        title, slug, summary, author_email, pub = r
        out.append({
            "title": title,
            "slug": slug,
            "summary": summary,
            "author_email": author_email,
            "published_at": pub
        })
    return {"ok": True, "items": out, "page": page, "size": size}

@voces_router.get("/{slug}")
def get_by_slug(slug: str):
    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("""
            SELECT title, slug, summary, content, author_email,
                   COALESCE(to_char(published_at, 'YYYY-MM-DD'), '') AS pub
              FROM posts
             WHERE slug=%s AND status='published'
             LIMIT 1;
        """, (slug,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "Artículo no encontrado")
        title, slug, summary, content, author_email, pub = r
    return {
        "ok": True,
        "post": {
            "title": title, "slug": slug, "summary": summary, "content": content,
            "author_email": author_email, "published_at": pub
        }
    }

# (Opcional) Moderación
class ModerateIn(BaseModel):
    slug: str
    status: str = Field(..., description="published|draft|rejected")
    reason: Optional[str] = None

@voces_router.post("/moderate")
def moderate_post(body: ModerateIn, x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")
    if body.status not in ("published", "draft", "rejected"):
        raise HTTPException(400, "Estado inválido")

    with pg_conn() as cx, cx.cursor() as cur:
        cur.execute("UPDATE posts SET status=%s WHERE slug=%s;", (body.status, body.slug))
        cx.commit()
    return {"ok": True}
