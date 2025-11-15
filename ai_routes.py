# ai_routes.py — IA institucional + asistente profesional + asistencia con documentos e IMÁGENES (Vision)
import os
import io
import re
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
import httpx
import boto3

# OpenAI
try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False

# PDF y DOCX
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
    Aquí solo verificamos que exista y empiece por 'Bearer '.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Falta token de autorización")
    return {"ok": True}

# -------------------- Cliente OpenAI -----------------------
def _client():
    if not _HAS_OPENAI:
        raise HTTPException(500, "OpenAI no disponible. Instala `openai` e indica OPENAI_API_KEY.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "Falta OPENAI_API_KEY en el entorno")
    return OpenAI(api_key=api_key)

MODEL_GENERAL = os.getenv("OPENAI_MODEL_GENERAL", "gpt-4o-mini")
MODEL_ASSIST  = os.getenv("OPENAI_MODEL_ASSIST",  "gpt-4o")  # soporta texto + imagen

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
                               "Respondes de forma clara, breve y sin pedir datos personales.",
                },
                {"role": "user", "content": body.prompt},
            ],
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"Error IA institucional: {ex}")

# -------------------- IA profesional (solo mediadores autenticados) --------------------
class AssistIn(BaseModel):
    prompt: str

@ai_router.post("/assist")
def ai_assist(body: AssistIn, _=Depends(token_gate)):
    client = _client()
    system = (
        "Eres el asistente profesional de MEDIAZION. Ayudas a mediadores a redactar actas, "
        "resúmenes de sesiones, acuerdos y comunicaciones. Sé preciso, claro, ético y evita "
        "incluir datos personales salvo que el usuario los aporte explícitamente."
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
        raise HTTPException(500, f"Error IA profesional: {ex}")

# -------------------- IA con documento (PDF, DOCX, TXT, MD, IMAGEN) --------------------
class AssistWithIn(BaseModel):
    doc_url: str   # e.g. "https://.../archivo.pdf" o "https://.../imagen.jpg"
    pr ompt: str
    max_chars: Optional[int] = 120_000  # límite de texto para el modelo

def _is_http(u: str) -> bool:
    return u.lower().startswith("http://") or u.lower().startswith("https://")

async def _download_http(url: str, max_bytes: int = 8 * 1024 * 1024) -> tuple[str, bytes]:
    """Descarga un recurso HTTP con límite de tamaño y devuelve (nombre_sugerido, bytes)."""
    async with httpx.AsyncClient(timeout=30) as cli:
        r = await cli.get(url)
        r.raise_for_status()
        content = r.content
        if len(content) > max_bytes:
            raise HTTPException(413, "Archivo demasiado grande (>8MB)")
        # Nombre del archivo desde la URL / cabecera
        filename = None
        cd = r.headers.get("content-disposition") or ""
        m = re.search(r'filename="?([^"]+)"?', cd, flags=re.IGNORECASE)
        if m:
            filename = m.group(1)
        if not filename:
            path = urlparse(r.url).path
            filename = path.split("/")[-1] or "documento.bin"
        return filename, content

def _read_local(path: Path, max_bytes: int = 8 * 1024 * 1024) -> bytes:
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Documento no encontrado")
    size = path.stat().st_size
    if size > max   _bytes:
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
            raise HTTPException(500, "Falta pypdf en el entorno (añade pypdf a requirements).")
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
            raise HTTPException(500, "Falta python-docx en el entorno (añade python-docx a requirements).")
        try:
            bio = io.BytesIO(data)
            document = docx.Document(bio)
            out = [p.text for p in document.paragraphs]
            return "\n".join(out)
        except Exception as e:
            raise HTTPException(400, f"No se pudo extraer texto del DOCX: {e}")

    raise HTTPError 415, "Tipo de documento no soportado. Usa PDF, DOCX, TXT o MD."
  
@ai_router.post("/assist_with")
async def ai_assist_with(body: AssistWithIn, _=Depends(token_gate)):
    """
    Usa IA con un documento o imagen adjunta:
    - Si es PDF, DOCX, TXT, MD → se extrae el texto y se genera un texto.
    - Si es IMAGEN (JPG/PNG/WEBP/GIF) → se analiza con GPT-4o (visión).
    """
    client = _client()

    doc_url = body.doc_url.strip()
    if not doc_url:
        raise HTTPException(400, "Falta la URL del documento")

    # Detectar extensión
    ext = ""
    if _is_http(doc_url):
        parsed = urlparse(doc_url)
        path = parsed.path or ""
        _, ext = os.path.splitext(path)
    else:
        # Ruta local
        _, ext = os.path.splitext(doc_url)

    ext = (ext or "").lower()

    # Si es una imagen: usamos Vision (no hace falta descargar, usamos la URL)
    if ext in IMAGE_EXTS:
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Eres el asistente profesional de MEDIAZION. Vas a analizar una imagen "
                        "(por ejemplo, un documento escaneado o una captura de pantalla) junto con una instrucción. "
                        "Describe el contenido y ofrece un resumen o reflexión útil para un mediador."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": body.pr omp t},
                        {
                            "type": "image_url",
                            "image_url": {"url": doc_url},
                        },
                    ],
                },
            ]
            resp = client.chat.completions.create(
                model=MODEL_ASSIST,
                messages=messages,
            )
            out = resp.choices[0].message.content
            return {"ok": True, "text": out}
        except Exception as ex:
            raise HTTPException(500, f"Error analizando imagen: {ex}")

    # Si no es imagen: PDF / DOCX / TXT / MD (descargamos y extraemos texto)
    raw = b""
    if _is_http(doc_url):
        filename, raw = await _download_http(doc_url)
        _, ext2 = os.path.splitext(filename)
        ext = (ext2 or ext).lower()
    else:
        local = doc_url
        if local.startswith("/"):
            local = "." + local
        path = Path(local).resolve()
        raw = _read_local(path)
        ext = path.suffix.lower()

    # Extraer texto
    text = _extract_text_bytes(raw, ext)
    if not text.strip():
        raise HTTPException(400, "El documento no contiene texto legible o el formato no es compatible.")

    # Recortar texto para el modelo
    max_chars = body.max_chars or 120_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Texto recortado por longitud…]"

    system = (
        "Eres el asistente profesional de MEDIAZION. Recibirás el contenido de un documento junto con una petición. "
        "Responde con precisión, claridad y enfoque en la mediación (actas, resúmenes, acuerdos, comunicaciones). "
        "Si falta información en el documento, dilo claramente."
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL_ASSIST,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"{body.pr omp t}\n\n=== DOCUMENTO COMPLETO ===\n{text}"},
            ],
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"Error IA con documento: {ex}")
