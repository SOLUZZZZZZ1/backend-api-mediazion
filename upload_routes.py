# upload_routes.py — subida local
import os
from fastapi import APIRouter, File, UploadFile, HTTPException

upload_router = APIRouter()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@upload_router.post("/upload/file")
async def upload_file(file: UploadFile = File(...)):
    try:
        path = os.path.join(UPLOAD_DIR, file.filename)
        with open(path, "wb") as f:
            f.write(await file.read())
        return {"ok": True, "url": f"/uploads/{file.filename}"}
    except Exception as e:
        raise HTTPException(500, f"Error al subir archivo: {e}")
