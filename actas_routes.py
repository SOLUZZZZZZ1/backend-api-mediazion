# actas_routes.py — Generación de actas DOCX y PDF
from fastapi import APIRouter, HTTP_APIView, HTTPException
from pydantic import BaseModel
import os, datetime
from docx import Document
from docx.shared import Inches
from io import BytesIO
import requests

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except Exception:
    # Si no tienes reportlab aún, añade 'reportlab' a requirements.txt y vuelve a desplegar
    pass

actas_router = APIRouter(prefix="/actas", tags=["actas"])

UPLOAD_DIR = "uploads/actas"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class ActaIn(BaseModel):
    case_no: str
    date_iso: str
    mediator_alias: str
    parties: str
    summary: str
    agreements: str | None = None
    confidentiality: bool = True
    logo_url: str | None = None

def _now_stamp() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

# ---- DOCX ----
@actas_router.post("/render_docx")
def render_docx(data: ActaIn):
    try:
        doc = Document()
        # logo opcional
        if data.logo_url:
            try:
                img = requests.get(data.logo_url, timeout=5).content
                doc.add_picture(BytesIO(img), width=Inches(1.5))
            except Exception:
                pass
        doc.add_heading("Acta de Mediación", level=1)
        doc.add_paragraph(f"Expediente: {data.case_no}")
        doc.add_paragraph(f"Fecha: {data.date_iso}")
        doc.add_paragraph(f"Mediador/a: {data.mediator_alias}")
        doc.add_paragraph(f"Partes: {data.parties}")
        doc.add_heading("Resumen / Desarrollo", level=2)
        doc.add_paragraph(data.summary or "")
        doc.add_heading("Acuerdos alcanzados", level=2)
        doc.add_paragraph(data.agreements or "Sin acuerdos.")
        if data.confidentiality:
            doc.add_paragraph("\\nCláusula de confidencialidad: Las partes se comprometen a mantener la confidencialidad del proceso de mediación.")
        fname = f"acta_{data.case_no.replace(' ', '_')}_{_now_stamp()}.docx"
        out = os.path.join(UPLOAD_DIR, fname)
        doc.save(out)
        return {"ok": True, "url": f"/uploads/actas/{fname}"}
    except Exception as e:
        raise HTTPException(500, f"Error generando DOCX: {e}")

# ---- PDF ----
@actas_router.post("/render_pdf")
def render_pdf(data: ActaIn):
    try:
        fname = f"acta_{data.case_no.replace(' ', '_')}_{_now_stamp()}.pdf"
        out = os.path.join(UPLOAD_DIR, fname)

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(out, pagesize=A4)
        w, h = A4
        y = h - 80

        # Logo opcional
        if data.logo_url:
            try:
                img_bytes = BytesIO(requests.get(data.logo_url, timeout=5).content)
                c.drawImage(img_bytes, 40, y - 40, width=100, preserveAspectRatio=True, mask='auto')
                y -= 60
            } except:
                pass

        c.setFont("Helvetica-Bold", 16)
        c.drawString(150, y, "ACTA DE MEDIACIÓN")
        y -= 40
        c.setFont("Helvetica", 11)

        lines = [
            f"Expediente: {data.case_no}",
            f"Fecha: {data.date_iso}",
            f"Mediador/a: {data.mediator_alias}",
            f"Partes: {data.parties}",
            "",
            "RESUMEN / DESARROLLO:",
            data.cover or data.summary or "",
            "",
            "ACUERDOS ALCANZADOS:",
            data.agreements or "Sin acuerdos.",
        ]
        if data.confidentiality:
            lines.append("")
            lines.append("Cláusula de confidencialidad: Las partes se comprometen a mantener la confidencialidad del proceso.")

        for line in lines:
            for seg in line.split("\\n"):
                c.drawString(40, y, seg)
                y -= 18
                if y < 60:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y = h - 80
        c.save()

        return {"ok": True, "url": f"/uploads/actas/{fname}"}
    except Exception as e:
        raise HTTPException(500, f"Error generando PDF: {e}"


