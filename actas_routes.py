# actas_routes.py — Generación de actas DOCX para Mediazion (sin depender de reportlab)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import datetime
from io import BytesIO

try:
    from docx import Document
    from docx.shared import Inches
except Exception as e:
    raise RuntimeError(f"Falta dependencia python-docx en el entorno: {e}")

import requests

actas_router = APIRouter()

# Carpeta donde guardamos las actas generadas
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

@actas_router.post("/render_docx")
def render_docx(body: ActaIn):
    """
    Genera un archivo DOCX con el contenido del acta y devuelve la URL para descargarlo.
    """
    try:
      # Crear documento
      doc = Document()

      # Insertar logo (si se proporciona URL válida)
      if body.logo_url:
          try:
              resp = requests.get(body.logo_url, timeout=5)
              resp.raise_for_status()
              image_stream = BytesIO(resp.content)
              doc.add_picture(image_stream, width=Inches(1.5))
          except Exception:
              # Si falla la descarga del logo, seguimos sin romper el acta
              pass

      # Encabezado
      doc.add_heading("ACTA DE MEDIACIÓN", level=1)
      doc.add_paragraph(f"Expediente: {body.case_no}")
      doc.add_paragraph(f"Fecha: {body.date_iso}")
      doc.add_paragraph(f"Mediador/a: {body.mediator_alias}")
      doc.add_paragraph(f"Partes: {body.parties}")

      # Contenido
      doc.add_heading("Resumen / Desarrollo", level=2)
      doc.add_paragraph(body.summary)

      doc.add_heading("Acuerdos alcanzados", level=2)
      doc.add_paragraph(body.agreements or "Sin acuerdos adicionales registrados.")

      if body.confidentiality:
          doc.add_paragraph(
              "Cláusula de confidencialidad: Las partes se comprometen a mantener la confidencialidad "
              "de la información intercambiada durante el proceso de mediación."
          )

      # Guardar el archivo en disco
      ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
      safe_case = body.case_no.replace(" ", "_")
      filename = f"Acta_{safe_case}_{ts}.docx"
      path = os.path.join(ACTAS_DIR, filename)
      doc.save(path)

      # Devolver URL relativa para que el frontend pueda descargarlo
      return {"ok": True, "url": f"/uploads/actas/{filename}"}

    except Exception as e:
      raise HTTPException(500, f"Error generando el acta: {str(e)}")

@actas_router.post("/render_pdf")
def render_pdf_stub():
    """
    Stub para PDF. De momento no generamos PDF porque no está instalada la librería reportlab.
    Cuando quieras, añadimos soporte real y la dependencia en requirements.txt.
    """
    raise HTTPException(501, "Generación de PDF no disponible en este entorno. Usa el DOCX.")
