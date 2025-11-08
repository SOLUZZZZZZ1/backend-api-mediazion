# actas_routes.py — Generación de Actas (DOCX) con logo de MEDIAZION
import os
import io
import datetime as dt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from db import pg_conn
import httpx
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

actas_router = APIRouter(prefix="/actas", tags=["actas"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

DEFAULT_LOGO_URL = os.getenv("MEDIAZION_LOGO_URL", "https://mediazion.eu/logo.png")

class ActaIn(BaseModel):
    case_no: str = Field(..., description="Número o identificador del caso/expediente")
    date_iso: str = Field(..., description="Fecha ISO, p.ej. 2025-11-08")
    mediator_alias: str = Field(..., description="Alias público del mediador")
    parties: str = Field(..., description="Partes intervinientes / representación")
    summary: str = Field(..., description="Resumen de hechos / antecedentes")
    agreements: str = Field(..., description="Acuerdos alcanzados / compromisos / próximos pasos")
    confidentiality: Optional[bool] = True
    location: Optional[str] = "España"
    logo_url: Optional[str] = None  # si no viene, se usa DEFAULT_LOGO_URL

def _fetch_logo_bytes(url: str) -> Optional[bytes]:
    try:
        if not url:
            url = DEFAULT_LOGO_URL
        with httpx.Client(timeout=10.0) as cli:
            r = cli.get(url)
            r.raise_for_status()
            return r.content
    except Exception:
        return None

def _paragraph(doc: Document, text: str, bold=False, size=11, align=None):
    p = doc.add_paragraph()
    run = p.add_run(text.strip())
    if bold:
        run.bold = True
    run.font.size = Pt(size)
    if align:
        p.alignment = align
    return p

@actas_router.post("/render_docx")
def render_acta_docx(body: ActaIn):
    # Validar fecha
    try:
        d = dt.datetime.fromisoformat(body.date_iso)
        fecha_fmt = d.strftime("%d/%m/%Y")
    except Exception:
        raise HTTPException(400, "date_iso inválida. Use formato ISO, p.ej. 2025-11-08")

    # Crear DOCX
    doc = Document()

    # Encabezado con logo
    logo_bytes = _fetch_logo_bytes(body.logo_url or DEFAULT_LOGO_URL)
    section = doc.sections[0]
    header = section.header
    header_p = header.paragraphs[0]
    header_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if logo_bytes:
        r = header_p.add_run()
        r.add_picture(io.BytesIO(logo_bytes), width=Inches(2.2))  # ~ 5.5cm
    else:
        header_p.add_run("MEDIAZION").bold = True

    # Línea divisoria
    _paragraph(doc, "", size=1)
    rule = doc.add_paragraph()
    rule_run = rule.add_run("—" * 40)
    rule.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Título
    p_title = _paragraph(doc, "ACTA DE SESIÓN DE MEDIACIÓN", bold=True, size=16, align=WD_ALIGN_PARAGRAPH.CENTER)
    _paragraph(doc, f"Expediente: {body.case_no}", bold=True, size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    _paragraph(doc, f"Fecha: {fecha_fmt} · Lugar: {body.location}", size=10, align=WD_ALIGN_PARAGRAPH.CENTER)

    _paragraph(doc, "")  # Espacio

    # Datos fijos
    _paragraph(doc, f"Mediador/a: {body.mediator_alias}", bold=True, size=12)
    _paragraph(doc, f"Partes intervinientes:", bold=True, size=12)
    _paragraph(doc, body.parties, size=11)
    _paragraph(doc, "")  # Espacio

    _paragraph(doc, "Antecedentes / Hechos:", bold=True, size=12)
    _paragraph(doc, body.summary, size=11)
    _paragraph(doc, "")  # Espacio

    _paragraph(doc, "Acuerdos y compromisos:", bold=True, size=12)
    _paragraph(doc, body.agreements, size=11)
    _paragraph(doc, "")  # Espacio

    if body.confidentiality:
        _paragraph(doc, "Cláusula de confidencialidad:", bold=True, size=12)
        _paragraph(
            doc,
            "Las partes reconocen el carácter confidencial del proceso de mediación, comprometiéndose a no divulgar, "
            "ni utilizar en procedimientos judiciales o administrativos, la información u opiniones manifestadas durante la sesión, "
            "salvo obligación legal en contrario.",
            size=10
        )
        _paragraph(doc, "")  # Espacio

    # Firma
    _paragraph(doc, "Firmas:", bold=True, size=12)
    _paragraph(doc, "______________________________      ______________________________", size=11)
    _paragraph(doc, "Parte A                                          Parte B", size=10)
    _paragraph(doc, "")  # Espacio
    _paragraph(doc, "______________________________", size=11)
    _paragraph(doc, "Mediador/a", size=10)

    # Guardar en /uploads
    ts = dt.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fname = f"Acta_{body.case_no}_{ts}.docx".replace(" ", "_")
    out_path = os.path.join(UPLOAD_DIR, fname)
    try:
        doc.save(out_path)
    except Exception as e:
        raise HTTPException(500, f"No se pudo escribir el DOCX: {e}")

    url = f"/uploads/{fname}"
    return {"ok": True, "url": url}
