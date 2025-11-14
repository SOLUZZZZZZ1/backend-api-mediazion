# upload_routes.py — versión compatible Render (usa /tmp)
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import uuid

upload_router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = "/tmp/mediazion_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@upload_router.post("/file")
async def upload_file(file: UploadFile = File(...)):
    try:
        ext = file.filename.split(".")[-1]
        newname = f"{uuid.uuid4()}.{ext}"
        path = os.path.join(UPLOAD_DIR, newname)
        content = await file.read()
        with open(path, "wb") as f:
            f.write(content)
        return {"ok": True, "url": f"/api/upload/get/{newname}"}
    except Exception as e:
        raise HTTPException(500, f"Error upload: {e}")

@upload_router.get("/get/{filename}")
def get_file(filename: str):
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(path)
