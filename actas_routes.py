# actas_routes.py — generación de ACTAS en DOCX (simple y robusto)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
from datetime import datetime
from io import BytesIO

import requests
from docx import Document
from docx.shared import Inches

actas_router = APIRouter()

ACTAS_DIR = os.path.join("uploads", "actas")
os.makedirs(ACTAS_DIR, exist_ok=True)

class ActaIn(BaseModel):
    case_no: str
    date_iso: str
    mediator_alias: str
    parties: str
    summary: str
    agreements: Optional[str] = None
    confidentiality: Optional[bool] = True
    logo_url: Optional[str] = "https://mediazion.eu/logo.png"

@actas_router.post("/actas/render_docx")
def render_docx(body: ActaIn):
    try:
        doc = Document()

        # Logo opcional
        if body.logo_url:
            try:
                resp = requests.get(body.logo_url, timeout=5)
                resp.raise_for_status()
                image_stream = BytesIO(resp.content)
                doc.add_picture(image_stream, width=Inches(1.5))
            except Exception:
                # si falla el logo, no rompemos el acta
                pass

        doc.add_heading("ACTA DE MEDIACIÓN", level=1)
        doc.add_paragraph(f"Expediente: {body.case_no}")
        doc.add_paragraph(f"Fecha: {body.date_iso}")
        doc.add_paragraph(f"Mediador/a: {body.mediator_alias}")
        doc.add_paragraph(f"Partes: {body.parties}")

        doc.add_heading("Resumen / Contenido", level=2)
        doc.add_paragraph(body.summary)

        doc.add_heading("Acuerdos alcanzados", level=2)
        doc.add_paragraph(body.agreements or "Sin acuerdos adicionales registrados.")

        if body.confidentiality:
            doc.add_paragraph("")
            doc.add_paragraph(
                "Cláusula de confidencialidad: Las partes se comprometen a mantener la confidencialidad "
                "del proceso de mediación y de la información intercambiada."
            )

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_case = body.case_no.replace(" ", "_")
        filename = f"Acta_{safe_case}_{ts}.docx"
        path = os.path.join(ACTAS_DIR, filename)
        doc.save(path)

        return {"ok": True, "url": f"/uploads/actas/{filename}"}

    except Exception as e:
        raise HTTPException(500, f"Error generando el acta: {str(e)}")
