# actas_routes.py — generación DOCX
import os, io, datetime as dt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from docx import Document
from docx.shared import Inches
import httpx

actas_router = APIRouter()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class ActaIn(BaseModel):
    case_no: str
    date_iso: str
    mediator_alias: str
    parties: str
    summary: str
    agreements: str
    confidentiality: bool = True

@actas_router.post("/actas/render_docx")
def render_docx(body: ActaIn):
    doc = Document()
    # Logo
    try:
        with httpx.Client() as c:
            r = c.get("https://mediazion.eu/logo.png")
            if r.status_code == 200:
                doc.add_picture(io.BytesIO(r.content), width=Inches(2.5))
    except Exception:
        pass
    doc.add_heading("ACTA DE SESIÓN DE MEDIACIÓN", level=1)
    doc.add_paragraph(f"Expediente: {body.case_no}")
    doc.add_paragraph(f"Fecha: {body.date_iso}")
    doc.add_paragraph(f"Mediador/a: {body.mediator_alias}")
    doc.add_paragraph("Partes intervinientes:\n" + body.parties)
    doc.add_paragraph("Resumen:\n" + body.summary)
    doc.add_paragraph("Acuerdos:\n" + body.agreements)
    if body.confidentiality:
        doc.add_paragraph(
            "Cláusula de confidencialidad: Las partes reconocen el carácter confidencial del proceso de mediación."
        )

    fname = f"Acta_{body.case_no}_{dt.datetime.utcnow().strftime('%Y%m%d%H%M%S')}.docx"
    path = os.path.join(UPLOAD_DIR, fname)
    doc.save(path)
    return {"ok": True, "url": f"/uploads/{fname}"}
