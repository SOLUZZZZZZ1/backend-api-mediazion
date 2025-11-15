# ai_routes.py — IA institucional + asistente profesional + asistente con documento
import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel
import httpx
import io
import re
from pathlib import Path

# PDF y DOCX (asegúrate de tenerlos en requirements)
try:
    import pypdf
    _HAS_PYPDF = True
except Exception:
    _HAS_PYPDF = False

try:
    import docx  # python-docx
    _HAS_DOXC = True
except Exception:
    _HAS_DOXC = False

# --- OpenAI client ---
try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False

ai_router = APIRouter()

# -------------------- Seguridad básica para endpoints privados --------------------
def token_gate(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Gate mínimo: espera Authorization: Bearer <algo>.
    Puedes sustituirlo por tu get_current_user real si lo importas del módulo de mediadores.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
    # Aquí solo validamos que exista un token; si quieres comprueba el token contra tu tabla "sessions".
    return {"ok": True}

# -------------------- Utilidades OpenAI --------------------
def _client():
    if not _HAS_OPENAI:
        raise HTTPException(500, "OpenAI no disponible. Instala `openai`.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "Falta OPENAI_API_KEY en entorno")
    return OpenAI(api_key=api_key)

MODEL_GENERAL = os.getenv("OPENAI_MODEL_GENERAL", "gpt-4o-mini")
MODEL_ASSIST  = os.getenv("OPENAI_MODEL_ASSIST",  "gpt-4o")

# -------------------- IA pública (institucional) --------------------
class CompleteIn(BaseModel):
    prompt: str

@ai_router.post("/complete")
def ai_complete(body: CompleteIn):
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=MODEL_GENERAL,
            messages=[
                {
                    "role": "system",
                    "content": "Eres el asistente institucional de MEDIAZION. "
                               "Responde claro, amable y sin pedir ni retener datos personales.",
                },
                {"role": "user", "content": body.prompt},
            ],
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"IA error: {ex}")

# -------------------- IA profesional (solo mediadores autenticados) --------------------
class AssistIn(BaseModel):
    prompt: str

@ai_router.post("/assist")
def ai_assist(body: AssistIn, _=Depends(token_gate)):
    client = _client()
    system = (
        "Eres el asistente profesional de MEDIAZION. Ayudas a mediadores a redactar actas, resúmenes de "
        "sesiones y comunicaciones. Sé preciso, confidencial, evita datos personales salvo que el usuario lo aporte."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL_ASSIST,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": body.prompt},
            ],
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"IA error: {ex}")

# -------------------- IA con documento (TXT/MD/PDF/DOCX) --------------------
class AssistWithIn(BaseModel):
    doc_url: str   # e.g. "/api/upload/get/xxx" o "https://..."
    prompt: str
    max_chars: Optional[int] = 120_000  # límite de texto para no desbordar al modelo

def _is_http(u: str) -> bool:
    return u.lower().startswith("http://") or u.lower().startswith("https://")

async def _download_http(url: str, max_bytes: int = 8 * 1024 * 1024) -> tuple[str, bytes]:
    """Descarga un recurso HTTP con límite de tamaño y devuelve (nombre sugerido, bytes)."""
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(url)
        r.raise_for_status()
        content = r.content
        if len(content) > max_bytes:
            raise HTTPException(413, "Archivo demasiado grande (>8MB)")
        # Intenta sugerir nombre desde cabeceras o URL
        filename = None
        cd = r.headers.get("content-disposition") or ""
        m = re.search(r'filename="?([^"]+)"?', cd, flags=re.IGNORECASE)
        if m:
            filename = m.group(1)
        if not filename:
            filename = url.split("?")[0].rstrip("/").split("/")[-1] or "doc.bin"
        return filename, content

def _read_local(path: Path, max_bytes: int = 8 * 1024 * 1024) -> bytes:
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Documento no encontrado")
    size = path.stat().st_size
    if size > max_bytes:
        raise HTTPException(413, "Archivo demasiado grande (>8MB)")
    return path.read_bytes()

def _extract_text_bytes(data: bytes, ext: str) -> str:
    ext = ext.lower()
    # TXT / MD
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="ignore")
    # PDF
    if ext == ".pdf":
        if not _HAS_PYPDF:
            raise HTTPException(500, "Falta pypdf en el entorno (añade pypdf a requirements)")
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            out = []
            for page in reader.pages:
                out.append(page.extract_text() or "")
            return "\n".join(out)
        except Exception as e:
            raise HTTPException(400, f"No se pudo extraer texto del PDF: {e}")
    # DOCX
    if ext == ".docx":
        if not _HAS_DOXC:
            raise HTTPException(500, "Falta python-docx en el entorno (añade python-docx a requirements)")
        try:
            bio = io.BytesIO(data)
            document = docx.Document(bio)
            out = []
            for p in document.paragraphs:
                out.append(p.text)
            return "\n".join(out)
        except Exception as e:
            raise HTTPException(400, f"No se pudo extraer texto del DOCX: {e}")

    raise HTTPException(415, "Tipo de documento no soportado. Usa TXT, MD, PDF o DOCX.")

@ai_router.post("/assist_with")
async def ai_assist_with(body: AssistWithIn, request: Request, _=Depends(token_gate)):
    """
    Usa IA con un documento adjunto (subido o remoto) + prompt del usuario.
    Soporta:
      - http(s)://...
      - /api/upload/get/{filename}  (mismo backend)
      - rutas locales (compatibilidad legado)
    """
    doc_url = (body.doc_url or "").strip()
    if not doc_url:
        raise HTTPException(400, "doc_url vacío")

    filename = "doc.bin"
    raw = b""

    # 1) URL absoluta http(s)
    if _is_http(doc_url):
        filename, raw = await _download_http(doc_url)

    # 2) URL relativa a /api/... (ej.: /api/upload/get/xxx)
    elif doc_url.startswith("/api/"):
        base = str(request.base_url).rstrip("/")   # ej: https://mediazion.eu
        full_url = base + doc_url                  # ej: https://mediazion.eu/api/upload/get/xxx
        filename, raw = await _download_http(full_url)

    # 3) Ruta local (no recomendado en Render, pero se mantiene por compatibilidad)
    else:
        local = doc_url
        if local.startswith("/"):
            local = "." + local  # monta ruta relativa
        path = Path(local).resolve()
        # Seguridad mínima: solo leer dentro del directorio actual
        if str(path).find(str(Path(".").resolve())) != 0:
            raise HTTPException(403, "Ruta no permitida")
        raw = _read_local(path)
        filename = path.name

    # 2) Extraer texto
    ext = "." + filename.split(".")[-1].lower() if "." in filename else ".bin"
    text = _extract_text_bytes(raw, ext)
    if not text.strip():
        raise HTTPException(400, "El documento no tiene texto legible")

    # 3) Recortar y construir prompt
    max_chars = body.max_chars or 120_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...texto recortado por longitud...]"

    system = (
        "Eres el asistente profesional de MEDIAZION. Recibirás un documento textual y un encargo. "
        "Responde con rigor, bien estructurado y orientado a mediación (actas, resúmenes, borradores de acuerdos, comunicaciones). "
        "No inventes datos. Si algo no está en el documento, dilo claramente."
    )
    user_message = f"{body.prompt}\n\n=== DOCUMENTO INTEGRAL ===\n{text}"

    # 4) Llamar a OpenAI
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=MODEL_ASSIST,
            messages=[
                {"role":"system","content": system},
                {"role":"user","content": user_message}
            ]
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"IA error: {ex}")
