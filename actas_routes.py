# actas_routes.py — Generación de actas (DOCX) con logo en cabecera
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import os
import io
import re
import requests

try:
    import docx
    from docx.shared import Cm, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except Exception as e:
    raise RuntimeError("Falta dependencia python-docx en el entorno") from e

from db import pg_conn  # si no usas DB aquí, puedes quitarlo

actas_router = APIRouter(prefix="/actas", tags=["actas"])

# URL por defecto del logo (puedes cambiarla por env var)
LOGO_URL_DEFAULT = "https://mediazion.eu/logo.png"
LOGO_URL = os.getenv("LOGO_URL", LOGO_URL_DEFAULT)

UPLOADS_DIR = os.path.join("uploads", "actas")
os.makedirs(UPLOADS_DIR, exist_ok=True)


def _download_logo(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def _insert_logo_header(document: "docx.document.Document", logo_bytes: bytes, width_cm: float = 3.2):
    """
    Inserta el logo en el encabezado (arriba a la derecha) de la primera sección.
    El encabezado de la primera sección se replica en todas las páginas si no se crean secciones nuevas.
    """
    section = document.sections[0]
    header = section.header
    # Asegura un párrafo
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run()
    run.add_picture(io.BytesIO(logo_bytes), width=Cm(width_cm))


def _h(text: str) -> str:
    """ Limpia texto para filename. """
    t = re.sub(r"[^\w\-\.\(\)\s]", "_", text or "")
    return re.sub(r"\s+", "_", t).strip("_") or "ACTA"


class ActaIn(BaseModel):
    case_no: str = Field(..., description="Identificador del expediente, ej. MED-2025-001")
    date_iso: str = Field(..., description="Fecha ISO YYYY-MM-DD")
    mediator_alias: str = Field(..., description="Nombre/alias del mediador que aparece en el acta")
    parties: str = Field(..., description="Partes implicadas, ej. 'Parte A; Parte B'")
    summary: str = Field(..., description="Resumen/desarrollo de la sesión")
    agreements: str = Field(..., description="Acuerdos alcanzados (si aplica)")
    confidentiality: bool = Field(default=True, description="Incluir cláusula de confidencialidad")
    notes: Optional[str] = Field(default=None, description="Observaciones adicionales")
    header_title: Optional[str] = Field(default="ACTA DE MEDIACIÓN", description="Título del documento")
    include_logo: bool = Field(default=True, description="Insertar logo en cabecera")
    logo_url: Optional[str] = Field(default=None, description="URL del logo a usar (si se quiere sobreescribir)")


@actas_router.post("/render_docx")
def render_docx(body: ActaIn):
    """
    Genera un DOCX con el acta y devuelve una URL de descarga en /uploads/actas/...
    Si include_logo=True, inserta el logo en el header (usa LOGO_URL o body.logo_url).
    """
    # 1) Crear documento y estilos
    document = docx.Document()
    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # 2) Logo (header)
    if body.include_logo:
        logo_url = (body.logo_url or LOGO_URL).strip()
        logo_bytes = _download_logo(logo_url)
        if logo_bytes:
            try:
                _insert_logo_header(document, logo_bytes, width_cm=3.2)
            except Exception:
                # Nunca romper generación por el logo
                pass

    # 3) Título
    if body.header_title:
        p = document.add_paragraph()
        run = p.add_run(body.header_title.upper())
        run.bold = True
        run.font.size = Pt(16)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 4) Datos de cabecera
    document.add_paragraph()
    meta = document.add_paragraph()
    meta.style = document.styles["Normal"]
    meta.add_run("Expediente: ").bold = True
    meta.add_run(f"{body.case_no}\n")
    meta.add_run("Fecha: ").bold = True
    meta.add_run(f"{body.date_iso}\n")
    meta.add_run("Mediador/a: ").bold = True
    meta.add_run(f"{body.mediator_alias}\n")
    meta.add_run("Partes: ").bold = True
    meta.add_run(f"{body.parties}\n")

    document.add_paragraph()  # espacio

    # 5) Cuerpo
    sec1 = document.add_paragraph()
    sec1.add_run("DESARROLLO / RESUMEN").bold = True
    document.add_paragraph(body.summary or "")

    document.add_paragraph()
    sec2 = document.add_paragraph()
    sec2.add_run("ACUERDOS ALCANZADOS").bold = True
    document.add_paragraph(body.agreements or "")

    if body.notes:
        document.add_paragraph()
        sec3 = document.add_paragraph()
        sec3.add_run("OBSERVACIONES").bold = True
        document.add_paragraph(body.notes)

    if body.confidentiality:
        document.add_paragraph()
        sec4 = document.add_paragraph()
        sec4.add_run("CONFIDENCIALIDAD").bold = True
        document.add_paragraph(
            "Las partes se comprometen a mantener la confidencialidad de la información intercambiada durante el proceso "
            "de mediación, de acuerdo con la normativa aplicable y el acuerdo de confidencialidad suscrito."
        )

    # 6) Firma(s)
    document.add_paragraph()
    firm = document.add_paragraph()
    firm.add_run("\n\nFirmas:\n").bold = True
    document.add_paragraph("Mediador/a: ________________________________")
    document.add_paragraph("Parte A:   ________________________________")
    document.add_paragraph("Parte B:   ________________________________")

    # 7) Guardar
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fname = f"Acta_{_h(body.case_no)}_{ts}.docx"
    fpath = os.path.join(UPLOADS_DIR, fname)

    try:
        document.save(fpath)
    except Exception as e:
        raise HTTPException(500, f"No se pudo generar el DOCX: {e}")

    # 8) Respuesta con URL relativa (servir vía /uploads)
    url = f"/uploads/actas/{fname}"
    return {"ok": True, "url": url}
