# actas_routes.py — Generación de Actas (DOCX) con LOGO MEDIAZION destacado
import os
import io
import datetime as dt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from db import pg_conn
import httpx

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

actas_router = APIRouter(prefix="/actas", tags=["actas"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

DEFAULT_LOGO_URL = os.getenv("MEDIAZION_LOGO_URL", "https://mediazion.eu/logo.png")
BRAND_HEX = os.getenv("MEDIAZION_BRAND_HEX", "0A7CFF")  # azul Mediazion
BRAND_RGB = (int(BRAND_Hex := BRAND_HEX, 16) >> 16 & 0xFF,
             int(BRAND_HEX, 16) >> 8 & 0xFF,
             int(BRAND_HEX, 16) & 0xFF)

class ActaIn(BaseModel):
    case_no: str = Field(..., description="Número/Referencia de expediente")
    date_iso: str = Field(..., description="Fecha ISO, p.ej. 2025-11-08")
    mediator_alias: str = Field(..., description="Alias público del mediador/a")
    parties: str = Field(..., description="Partes intervinientes / representación")
    summary: str = Field(..., description="Antecedentes / Hechos relevantes")
    agreements: str = Field(..., description="Acuerdos y compromisos / próximos pasos")
    confidentiality: Optional[bool] = True
    location: Optional[str] = "España"
    logo_url: Optional[str] = None
    logo_mode: Optional[str] = "normal"   # "normal" | "banner"
    logo_width_cm: Optional[float] = 9.0  # ancho del logo en cm (por defecto ~9 cm)

def _fetch_logo_bytes(url: Optional[str]) -> Optional[bytes]:
    try:
        u = url or DEFAULT_LOGO_URL
        with httpx.Client(timeout=10.0) as cli:
            r = cli.get(u)
            r.raise_for_status()
            return r.content
    except Exception:
        return None

def _p(doc: Document, text: str = "", *, bold=False, size=11, align=None, color: Optional[tuple[int,int,int]] = None):
    p = doc.add_paragraph()
    run = p.add_run(text.strip())
    if bold: run.bold = True
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor(*color)
    if align:
        p.alignment = align
    return p

def _brand_rule(doc: Document):
    # línea gruesa con color corporativo
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("─"*60)
    run.font.color.rgb = RGBColor(*BRAND_RGB)

@actas_router.post("/render_docx")
def render_acta_docx(body: ActaIn):
    # validar fecha
    try:
        d = dt.datetime.fromisoformat(body.date_iso)
        fecha_fmt = d.strftime("%d/%m/%Y")
    except Exception:
        raise HTTPException(400, "date_iso inválida. Use formato ISO, p.ej. 2025-11-08")

    # DOCX
    doc = Document()
    section = doc.sections[0]
    # márgenes un poco más limpios
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.8)
    section.right_margin = Inches(0.8)

    # Encabezado con LOGO destacado
    logo_bytes = _fetch_logo_bytes(body.logo_url)
    header = section.header
    header_p = header.paragraphs[0]
    header_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if logo_bytes:
        run = header_p.add_run()
        # ancho configurable (cm → pulgadas)
        width_inches = Inches((body.logo_width_cm or 9.0) / 2.54)
        run.add_picture(io.BytesIO(logo_bytes), width=width_inches)
    else:
        run = header_p.add_run("MEDIAZION")
        run.bold = True
        run.font.size = Pt(20)
        run.font.color.rgb = RGBColor(*BRAND_RGB)
    # barra corporativa bajo el header
    _brand_rule(doc)

    # Título y metadatos
    _p(doc, "ACTA DE SESIÓN DE MEDIACIÓN", bold=True, size=16, align=WD_ALIGN_PARAGRAPH.CENTER)
    _p(doc, f"Expediente: {body.case_no}", bold=True, size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    _p(doc, f"Lugar: {body.location} · Fecha: {fecha_fmt}", size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    _p(doc)  # espacio

    # Bloques
    _p(doc, f"Mediador/a: {body.mediator_alias}", bold=True, size=12)
    _p(doc, "Partes intervinientes:", bold=True, size=12)
    _p(doc, body.parties, size=11)
    _p(doc)

    _p(doc, "Antecedentes / Hechos:", bold=True, size=12)
    _p(doc, body.summary, size=11)
    _p(doc)

    _p(doc, "Acuerdos y compromisos:", bold=True, size=12)
    _p(doc, body.agreements, size=11)
    _p()

    if body.confidentiality:
        _p(doc, "Cláusula de confidencialidad", bold=True, size=12)
        _p(doc,
           "Las partes reconocen el carácter confidencial del proceso de mediación y se obligan a no divulgar la "
           "información obtenida, ni a requerir al mediador/a como testigo o perito, salvo obligación legal.",
           size=10)
        _p(doc)

    _p(doc, "Firmas:", bold=True, size=12)
    _p(doc, "______________________________      ______________________________", size=11)
    _p(doc, "Parte A                                          Parte B", size=10)
    _p(doc)
    _p(doc, "______________________________", size=11)
    _p(doc, "Mediador/a", size=10)

    # Pie de página con marca
    footer = section.footer
    f = footer.paragraphs[0]
    f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    f_run = f.add_run("MEDIAZION · Centro de Mediación y Resolución de Conflictos · https://mediazion.eu")
    f_run.font.size = Pt(9)
    f_run.font.color.rgb = RGBColor(120, 120, 120)

    # Guardar
    ts = dt.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fname = f"Acta_{body.case_no}_{ts}.docx".replace(" ", "_").replace("/", "-")
    out_path = os.path.join(UPLOAD_DIR, fname)
    try:
        doc.save(out_path)
    except Exception as e:
        raise HTTPException(500, f"No se pudo escribir el DOCX: {e}")

    return {"ok": True, "url": f"/uploads/{fname}"}
