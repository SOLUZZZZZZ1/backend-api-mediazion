# ai_routes.py — IA institucional + asistente profesional + documentos + IMÁGENES (Vision)

import os
import io
import re
import base64
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
import httpx
from pathlib import Path

# --- OpenAI client ---
try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False

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

ai_router = APIRouter()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# -------------------- Seguridad básica --------------------
def token_gate(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Gate mínimo: espera Authorization: Bearer <algo>.
    Puedes sustituirlo por tu get_current_user real si lo importas del módulo de mediadores.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
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
MODEL_VISION  = os.getenv("OPENAI_MODEL_VISION",  "gpt-4o")  # mismo modelo para visión

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
        "sesiones y comunicaciones. Sé preciso, confidencial, evita datos personales salvo que el usuario lo aporte. "
        "No inventes acuerdos ni datos si no se dan."
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

# -------------------- IA con documento (TXT/MD/PDF/DOCX/IMÁGENES) --------------------
class AssistWithIn(BaseModel):
    doc_url: str   # e.g. "/api/upload/get/xxx" o "https://..."
    prompt: str
    max_chars: Optional[int] = 120_000  # límite de texto

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

def _vision_from_image_bytes(data: bytes, prompt: str) -> str:
    """
    Usa GPT-4o con visión para analizar una imagen + prompt.
    Codificamos la imagen como base64 data URL.
    """
    client = _client()
    b64 = base64.b64encode(data).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    system = (
        "Eres un asistente jurídico-profesional de MEDIAZION. Vas a recibir una imagen "
        "(por ejemplo, un documento escaneado, una pizarra con notas o un fragmento de acta) "
        "junto con un encargo. Extrae la información relevante de la imagen y responde con rigor, "
        "pensando en mediación, acuerdos y comunicaciones claras. Si algo no se ve bien, dilo."
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL_VISION,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
        )
        out = resp.choices[0].message.content
        return out
    except Exception as ex:
        raise HTTPException(500, f"IA (imagen) error: {ex}")

@ai_router.post("/assist_with")
async def ai_assist_with(body: AssistWithIn, _=Depends(token_gate)):
    """
    Usa IA con un documento adjunto (subido o remoto) + prompt del usuario.
    Lee: /api/upload/get/{fname} o http(s)://...
    Si es TXT/MD/PDF/DOCX → extrae texto y redacta.
    Si es una IMAGEN (JPG/PNG/WEBP/GIF) → usa GPT-4o con visión.
    """
    filename = "doc.bin"
    raw = b""

    if _is_http(body.doc_url):
        filename, raw = await _download_http(body.doc_url)
    else:
        local = body.doc_url
        if local.startswith("/"):
            local = "." + local
        path = Path(local).resolve()
        if str(path).find(str(Path(".").resolve())) != 0:
            raise HTTPException(403, "Ruta no permitida")
        raw = _read_local(path)
        filename = path.name

    ext = "." + filename.split(".")[-1].lower() if "." in filename else ".bin"

    # Si es imagen → visión
    if ext in IMAGE_EXTS:
        out = _vision_from_image_bytes(raw, body.prompt)
        return {"ok": True, "text": out}

    # Si es texto → extraemos
    text = _extract_text_bytes(raw, ext)
    if not text.strip():
        raise HTTPException(400, "El documento no tiene texto legible")

    max_chars = body.max_chars or 120_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...texto recortado por longitud...]"

    system = (
        "Eres el asistente profesional de MEDIAZION. Recibirás un documento textual y un encargo. "
        "Responde con rigor, bien estructurado y orientado a mediación (actas, resúmenes, borradores de acuerdos, comunicaciones). "
        "No inventes datos. Si algo no está en el documento, dilo claramente."
    )
    user_message = f"{body.prompt}\n\n=== DOCUMENTO INTEGRAL ===\n{text}"

    client = _client()
    try:
        resp = client.chat.completions.create(
            model=MODEL_ASSIST,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"IA error: {ex}")
