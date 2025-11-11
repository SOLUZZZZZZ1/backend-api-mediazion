# actas_routes.py — Generación de actas DOCX para Mediazion
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from docx import Document
from docx.shared import Inches
import os, datetime

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

@actas_router.post("/render_docx")
def render_docx(data: ActaIn):
    try:
        doc = Document()
        # Logo si existe
        if data.logo_url:
            try:
                import requests
                from io import BytesIO
                img_data = requests.get(data.logo_url, timeout=5).content
                doc.add_picture(BytesIO(img_data), width=Inches(1.5))
            except Exception:
                pass

        doc.add_heading("Acta de Mediación", level=1)
        doc.add_paragraph(f"Expediente: {data.case_no}")
        doc.add_paragraph(f"Fecha: {data.date_iso}")
        doc.add_paragraph(f"Mediador/a: {data.mediator_alias}")
        doc.add_paragraph(f"Partes: {data.parties}")
        doc.add_heading("Resumen / Desarrollo", level=2)
        doc.add_paragraph(data.summary)
        doc.add_heading("Acuerdos alcanzados", level=2)
        doc.add_paragraph(data.agreements or "Sin acuerdos adicionales registrados.")
        if data.confidentiality:
            doc.add_paragraph("\nCláusula de confidencialidad: Las partes se comprometen a mantener la confidencialidad de los acuerdos y la información intercambiada durante el proceso de mediación.")

        filename = f"acta_{data.case_no.replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        path = os.path.join(UPLOAD_DIR, filename)
        doc.save(path)

        return {"ok": True, "url": f"/uploads/actas/{filename}"}
    except Exception as e:
        raise HTTPException(500, f"Error generando DOCX: {e}")
