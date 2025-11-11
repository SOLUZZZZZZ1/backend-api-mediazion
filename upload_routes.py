# upload_routes.py — versión estable MEDIAZION (corrige subida de Word/PDF)
import os
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

upload_router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@upload_router.post("/file")
async def upload_file(file: UploadFile = File(...)):
    """
    Guarda un archivo subido (PDF/DOC/DOCX/TXT/MD) y devuelve su URL accesible desde /uploads.
    """
    try:
        filename = file.filename.replace(" ", "_")
        path = os.path.join(UPLOAD_DIR, filename)

        # Leer contenido y guardar en disco
        content = await file.read()
        with open(path, "wb") as f:
            f.write(content)

        # Respuesta estándar
        return JSONResponse({
            "ok": True,
            "filename": filename,
            "url": f"/uploads/{filename}"
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar archivo: {e}")
