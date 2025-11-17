# voces_routes.py — Gestión de VOCES con moderación IA (Mediazion)
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr
from db import pg_conn
from datetime import datetime
import re
import os
import json

voces_router = APIRouter(prefix="/voces", tags=["voces"])


def _slugify(title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not base:
        base = "post"
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{base}-{ts}"


def _row_dict(row, cols):
    if isinstance(row, dict):
        return row
    return {col: row[i] for i, col in enumerate(cols)}


def _moderate_text(title: str, summary: str | None, content: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_TOKEN")
    if not api_key:
        return {"action": "publish", "risk": "low", "reasons": ["no_api_key"]}
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)
        texto = f"TÍTULO: {title}\n\nRESUMEN: {summary or ''}\n\nCONTENIDO:\n{content}"
        system_prompt = (
            "Eres un moderador de contenidos para la plataforma profesional de mediación 'Mediazion'. "
            "Clasifica el texto según estas normas:\n"
            "- PROHIBIDO: insultos, discurso de odio, incitación a la violencia, acoso, datos personales de terceros, "
            "contenido sexual explícito, propaganda política partidista, revelación de información confidencial de casos.\n"
            "- PERMITIDO: opiniones profesionales, reflexiones sobre conflictos, experiencias personales sin datos "
            "identificables, explicaciones sobre mediación, análisis jurídicos generales.\n\n"
            "Devuelve SIEMPRE un JSON con este formato EXACTO (sin texto adicional):\n"
            "{ 'action': 'publish' | 'review' | 'reject', 'risk': 'low' | 'medium' | 'high', 'reasons': ['...'] }."
        )
        model_name = os.getenv("OPENAI_MODEL_GENERAL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": texto},
            ],
            max_tokens=200,
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        cleaned = raw.replace("'", '"')
        data = json.loads(cleaned)
        action = str(data.get("action", "publish")).lower()
        risk = str(data.get("risk", "low")).lower()
        reasons = data.get("reasons") or []
        if not isinstance(reasons, list):
            reasons = [str(reasons)]
        if action not in ("publish", "review", "reject"):
            action = "publish"
        if risk not in ("low", "medium", "high"):
            risk = "low"
        return {"action": action, "risk": risk, "reasons": reasons}
    except Exception:
        return {"action": "publish", "risk": "low", "reasons": ["error_ia"]}


class VozCreate(BaseModel):
    email: EmailStr
    title: str
    summary: str | None = None
    content: str


class VozLegacy(BaseModel):
    email: EmailStr
    title: str
    summary: str | None = None
    content: str
    accept_terms: bool | None = False


class CommentIn(BaseModel):
    email: EmailStr
    slug: str
    content: str


@voces_router.post("")
def crear_con_moderacion(body: VozCreate):
    email = body.email.strip().lower()
    title = body.title.strip()
    content = body.content.strip()
    summary = (body.summary or "").strip() or None
    if not email or not title or not content:
        raise HTTPException(400, "Falta email, título o contenido.")
    slug = _slugify(title)
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                INSERT INTO posts (author_email, title, slug, summary, content, status, created_at)
                VALUES (LOWER(%s), %s, %s, %s, %s, 'pending_ai', NOW())
                RETURNING id;
                """,
                (email, title, slug, summary, content),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(500, "No se pudo recuperar el ID creado.")
            post_id = row[0]
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"No se pudo crear el borrador: {e}")

    mod = _moderate_text(title, summary, content)
    action = mod.get("action", "publish")
    new_status = "published"
    set_published_at = True
    if action == "review":
        new_status = "pending_review"
        set_published_at = False
    elif action == "reject":
        new_status = "rejected"
        set_published_at = False
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            if set_published_at:
                cur.execute(
                    """
                    UPDATE posts
                       SET status=%s,
                           published_at=NOW()
                     WHERE id=%s;
                    """,
                    (new_status, post_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE posts
                       SET status=%s
                     WHERE id=%s;
                    """,
                    (new_status, post_id),
                )
            cx.commit()
    except Exception:
        pass

    return {
        "ok": True,
        "id": post_id,
        "slug": slug,
        "status": new_status,
        "moderation": mod,
    }


@voces_router.post("/post")
def crear_post_directo(body: VozLegacy):
    if not body.accept_terms:
        raise HTTPException(400, "Debes aceptar las condiciones de publicación.")
    email = body.email.strip().lower()
    title = body.title.strip()
    content = body.content.strip()
    summary = (body.summary or "").strip() or None
    if not email or not title or not content:
        raise HTTPException(400, "Falta email, título o contenido.")
    slug = _slugify(title)
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                INSERT INTO posts (author_email, title, slug, summary, content, status, created_at, published_at)
                VALUES (LOWER(%s), %s, %s, %s, %s, 'published', NOW(), NOW())
                RETURNING id, slug;
                """,
                (email, title, slug, summary, content),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(500, "No se pudo recuperar el post creado.")
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"No se pudo publicar: {e}")
    return {"ok": True, "id": row[0], "slug": row[1]}


@voces_router.post("/{post_id}/publish")
def publicar_manual(post_id: int, email: EmailStr = Query(...)):
    email_norm = email.strip().lower()
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                "SELECT id, slug, author_email, status FROM posts WHERE id=%s;",
                (post_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Post no encontrado.")
            pid, slug, author, status = row
            if author.lower() != email_norm:
                raise HTTPException(403, "No puedes publicar un post de otro usuario.")
            if status == "rejected":
                raise HTTPException(
                    400,
                    "La IA ha marcado este contenido como rechazado. Revisa el texto antes de intentar publicarlo de nuevo.",
                )
            cur.execute(
                """
                UPDATE posts
                   SET status='published',
                       published_at=NOW()
                 WHERE id=%s;
                """,
                (pid,),
            )
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error publicando: {e}")
    return {"ok": True, "id": post_id, "slug": slug}


@voces_router.get("/public")
def listar_public(limit: int = 20):
    COLS = ["id", "author_email", "title", "slug", "summary", "published_at"]
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                SELECT id, author_email, title, slug, summary, published_at
                  FROM posts
                 WHERE status='published'
                 ORDER BY published_at DESC NULLS LAST, created_at DESC
                 LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall() or []
    except Exception as e:
        raise HTTPException(500, f"Error listando publicaciones: {e}")
    items = []
    for r in rows:
        d = _row_dict(r, COLS)
        if d.get("published_at"):
            d["published_at"] = d["published_at"].isoformat()
        items.append(d)
    return {"ok": True, "items": items}


@voces_router.get("/{slug}")
def detalle_publicacion(slug: str):
    COLS = [
        "id",
        "author_email",
        "title",
        "slug",
        "summary",
        "content",
        "status",
        "created_at",
        "published_at",
    ]
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                SELECT id, author_email, title, slug, summary, content,
                       status, created_at, published_at
                  FROM posts
                 WHERE slug=%s;
                """,
                (slug,),
            )
            row = cur.fetchone()
    except Exception as e:
        raise HTTPException(500, f"Error cargando post: {e}")
    if not row:
        raise HTTPException(404, "Artículo no encontrado.")
    d = _row_dict(row, COLS)
    if d.get("published_at"):
        d["published_at"] = d["published_at"].isoformat()
    return {"ok": True, "post": d}


@voces_router.get("/{slug}/comments")
def listar_comentarios(slug: str):
    COLS = ["id", "author_email", "content", "created_at"]
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("SELECT id FROM posts WHERE slug=%s;", (slug,))
            p = cur.fetchone()
            if not p:
                return {"items": []}
            post_id = p[0]
            cur.execute(
                """
                SELECT id, author_email, content, created_at
                  FROM post_comments
                 WHERE post_id=%s
                 ORDER BY created_at ASC;
                """,
                (post_id,),
            )
            rows = cur.fetchall() or []
    except Exception as e:
        raise HTTPException(500, f"Error listando comentarios: {e}")
    items = []
    for r in rows:
        d = _row_dict(r, COLS)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        items.append(d)
    return {"items": items}


@voces_router.post("/comment")
def crear_comentario(body: CommentIn):
    email = body.email.strip().lower()
    content = body.content.strip()
    if not email or not content:
        raise HTTPException(400, "Faltan datos.")
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("SELECT id FROM posts WHERE slug=%s;", (body.slug,))
            p = cur.fetchone()
            if not p:
                raise HTTPException(404, "Post no encontrado.")
            post_id = p[0]
            cur.execute(
                """
                INSERT INTO post_comments (post_id, author_email, content, created_at)
                VALUES (%s, %s, %s, NOW())
                RETURNING id, author_email, content, created_at;
                """,
                (post_id, email, content),
            )
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
