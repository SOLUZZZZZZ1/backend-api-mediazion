# voces_routes.py — Gestión de VOCES con moderación IA (Mediazion)
# ---------------------------------------------------------------
# Backend: FastAPI + PostgreSQL directo usando db.pg_conn (sin ORM).
#
# Tablas (creadas por migrate_routes.voces_init):
#   posts (id, author_email, title, slug, summary, content, status, created_at, published_at)
#   post_comments (id, post_id, author_email, content, created_at)
#
# Estados (status):
#   - 'draft'          → borrador (si en futuro lo usas)
#   - 'pending_ai'     → creado, pendiente de moderación IA
#   - 'pending_review' → IA recomienda revisión manual
#   - 'rejected'       → IA rechaza
#   - 'published'      → publicado (aparece en Voces públicas)
#
# ENDPOINTS:
#   POST   /api/voces                → crear post + moderar con IA
#   POST   /api/voces/{id}/publish   → publicar manualmente (autor) si no está rejected
#   POST   /api/voces/post           → LEGACY: crear + publicar directo (para VocesEditor antiguo)
#   GET    /api/voces/public         → listado público (status='published')
#   GET    /api/voces/{slug}         → detalle de un post
#   GET    /api/voces/{slug}/comments → comentarios del post
#   POST   /api/voces/comment        → crear comentario
#   DELETE /api/voces/{id}?email=... → borrar artículo (solo autor)
#
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, EmailStr
from db import pg_conn
from datetime import datetime
import re
import os
import json

voces_router = APIRouter(prefix="/voces", tags=["voces"])


# ---------------- Helpers ----------------

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


def _moderate_text(title: str, summary: str | None, content: str) -> dict:
    """
    Usa IA para moderar el texto.
    Devuelve dict:
      { "action": "publish" | "review" | "reject",
        "risk": "low" | "medium" | "high",
        "reasons": [...] }
    Si falla la IA o no hay API key → publish/low.
    """
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
        # Cualquier error → no bloqueamos
        return {"action": "publish", "risk": "low", "reasons": ["error_ia"]}


# ---------------- Modelos ----------------

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


# ---------------- Crear + moderar (VocesNuevo.jsx) ----------------

@voces_router.post("")
def crear_con_moderacion(body: VozCreate):
    """
    Crea un post y aplica moderación IA inmediatamente.

    Flujo:
      - Inserta con status='pending_ai'
      - Llama a IA
      - action:
          - publish → status='published', published_at=NOW()
          - review  → status='pending_review'
          - reject  → status='rejected'
    """
    email = body.email.strip().lower()
    title = body.title.strip()
    content = body.content.strip()
    summary = (body.summary or "").strip() or None

    if not email or not title or not content:
        raise HTTPException(400, "Falta email, título o contenido.")

    slug = _slugify(title)

    # 1) Insertar como pending_ai
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

    # 2) Moderar con IA (no bloqueante si falla)
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
        # Si falla esta parte, dejamos pending_ai en DB y no rompemos nada
        pass

    return {
        "ok": True,
        "id": post_id,
        "slug": slug,
        "status": new_status,
        "moderation": mod,
    }


# ---------------- LEGACY: /voces/post (VocesEditor antiguo) ----------------

@voces_router.post("/post")
def crear_post_directo(body: VozLegacy):
    """
    Endpoint LEGACY usado por VocesEditor.jsx:
    POST /api/voces/post

    - Requiere accept_terms=True
    - Crea y PUBLICA el post directamente (status='published').
      (Esta ruta NO aplica moderación IA dura, para no romper tu flujo viejo).
    """
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


# ---------------- Publicar manual (segundo paso) ----------------

@voces_router.post("/{post_id}/publish")
def publicar_manual(post_id: int, email: EmailStr = Query(...)):
    """
    Publicación manual (autor) usada por VocesNuevo.jsx como segundo paso.
    - No permite publicar si status='rejected'.
    """
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


# ---------------- Listado público ----------------

@voces_router.get("/public")
def listar_public(limit: int = 20):
    """Listado público de artículos (status='published')."""
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


# ---------------- Detalle + comentarios ----------------

@voces_router.get("/{slug}")
def detalle_publicacion(slug: str):
    """Detalle de un post, por slug."""
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
    """Comentarios del artículo."""
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
    """Crear comentario en un post existente."""
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


# ---------------- Borrar publicación ----------------

@voces_router.delete("/{post_id}")
def borrar_post(post_id: int, email: EmailStr = Query(...)):
    """
    Elimina un artículo de Voces.
    Solo puede borrar el autor (author_email = email).
    """
    email_norm = email.strip().lower()

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            # comprobar autor
            cur.execute(
                "SELECT id, author_email FROM posts WHERE id=%s;",
                (post_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Artículo no encontrado.")

            pid, author = row
            if author.lower() != email_norm:
                raise HTTPException(403, "No puedes borrar un artículo que no es tuyo.")

            cur.execute("DELETE FROM posts WHERE id=%s;", (pid,))
            cx.commit()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error eliminando artículo: {e}")

    return {"ok": True, "deleted": post_id}
