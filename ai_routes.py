# ai_routes.py — IA institucional + asistente profesional + asistente con documento / imagen (Vision)
import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
import httpx
import io
import re
from pathlib import Path

# --- OpenAI client ---
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
        raise HTTPException(401, "Missing token")
    return {"ok": True}

# -------------------- Cliente OpenAI --------------------
def _client():
    if not _HAS_OPENAI:
        raise HTTPException(500, "OpenAI no disponible. Instala `openai`.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "Falta OPENAI_API_KEY en entorno")
    return OpenAI(api_key=api_key)

MODEL_GENERAL = os.getenv("OPENAI_MODEL_GENERAL", "gpt-4o-mini")
MODEL_ASSIST  = os.getenv("OPENAI_MODEL_ASSIST",  "gpt-4o")  # usamos gpt-4o para texto + visión

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
                    "content": (
                        "Eres el asistente institucional de MEDIAZION. "
                        "Respondes claro, breve y sin pedir ni retener datos personales."
                    ),
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

# -------------------- IA con documento (TXT/MD/PDF/DOCX/IMAGEN) --------------------
class AssistWithIn(BaseModel):
    doc_url: str   # e.g. "https://.../archivo.pdf" o "https://.../imagen.jpg"
    prompt: str
    max_chars: Optional[int] = 120_000

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
        # Nombre sugerido desde cabeceras o URL
        filename = None
        cd = r.headers.get("content-disposition") or ""
        m = re.search(r'filename="?([^"]+)"?', cd, flags=re.IGNORECASE)
        if m:
            filename = m.group(1)
        if not filename:
            path = r.url.path or ""
            filename = path.split("/")[-1] or "doc.bin"
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
            out = [p.text for p in document.paragraphs]
            return "\n".join(out)
        except Exception as e:
            raise HTTPException(400, f"No se pudo extraer texto del DOCX: {e}")

    raise HTTPException(415, "Tipo de documento no soportado. Usa TXT, MD, PDF o DOCX.")

@ai_router.post("/assist_with")
async def ai_assist_with(body: AssistWithIn, _=Depends(token_gate)):
    """
    Usa IA con un documento o imagen adjunto:
    - Si es PDF/DOCX/TXT/MD → extrae texto y responde.
    - Si es imagen (JPG/PNG/WEBP/GIF) → usa GPT-4o con visión sobre la URL.
    """
    client = _client()

    doc_url = (body.doc_url or "").strip()
    if not doc_url:
        raise HTTPException(400, "Falta la URL del documento")

    # 1) Detectar extensión de forma rápida
    ext = ""
    if "." in doc_url:
        ext = "." + doc_url.split("?")[0].split(".")[-1].lower()

    # 2) IMAGEN → Vision (usamos directamente la URL pública, no hace falta leer bytes)
    if ext in IMAGE_EXTS:
        system = (
            "Eres el asistente profesional de MEDIAZION. Vas a analizar una imagen "
            "(por ejemplo un documento escaneado, una captura de pantalla, etc.) "
            "junto con una instrucción. Describe el contenido relevante y responde "
            "pensando en mediación (hechos, posiciones, posibles acuerdos)."
        )
        try:
            resp = client.chat.completions.create(
                model=MODEL_ASSIST,
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": body.prompt},
                            {"type": "image_url", "image_url": {"url": doc_url}},
                        ],
                    },
                ],
            )
            out = resp.choices[0].message.content
            return {"ok": True, "text": out}
        except Exception as ex:
            raise HTTPException(500, f"IA (visión) error: {ex}")

    # 3) DOCUMENTO TEXTO → PDF/DOCX/TXT/MD: descargamos y extraemos texto
    filename = "doc.bin"
    raw = b""

    if _is_http(doc_url):
        filename, raw = await _download_http(doc_url)
        if "." in filename:
            ext = "." + filename.split(".")[-1].lower()
        else:
            ext = ext or ".bin"
    else:
        # rutas locales (no recomendado en producción, pero lo mantenemos por compatibilidad)
        local = doc_url
        if local.startswith("/"):
            local = "." + local
        path = Path(local).resolve()
        # seguridad básica: sólo dentro de la carpeta actual
        if str(path).find(str(Path(".").resolve())) != 0:
            raise HTTPException(403, "Ruta no permitida")
        raw = _read_local(path)
        ext = path.suffix.lower()

    text = _extract_text_bytes(raw, ext)
    if not text.strip():
        raise HTTPException(400, "El documento no tiene texto legible")

    # recortar si es demasiado grande
    max_chars = body.max_chars or 120_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...texto recortado por longitud…]"

    system = (
        "Eres el asistente profesional de MEDIAZION. Recibirás el contenido de un documento "
        "junto con una instrucción. Responde con rigor, bien estructurado y orientado a "
        "mediación (actas, resúmenes, borradores de acuerdos, comunicaciones). "
        "No inventes datos; si algo no está en el documento, dilo claramente."
    )
    user_message = f"{body.prompt}\n\n=== DOCUMENTO COMPLETO ===\n{text}"

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
