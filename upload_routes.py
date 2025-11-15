# upload_routes.py — Subida de archivos a S3 y devolución de URL pública

import os
import uuid
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import boto3

# 👇 OJO: aquí SIN prefix. Lo añadimos luego en app.py
upload_router = APIRouter(tags=["upload"])

S3_BUCKET = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")

if not S3_BUCKET:
    raise RuntimeError("Falta S3_BUCKET_NAME en las variables de entorno")

# Cliente S3 (usa AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY del entorno)
s3_client = boto3.client("s3", region_name=AWS_REGION)


@upload_router.post("/upload/file")
async def upload_file(file: UploadFile = File(...)):
    """
    Endpoint real: POST /api/upload/file  (porque app.py usa prefix="/api")
    Sube un archivo a S3 y devuelve una URL pública.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No se recibió archivo")

    try:
        # Obtener extensión (si existe)
        _, ext = os.path.splitext(file.filename)
        ext = ext or ""

        # Nombre único dentro del bucket
        key = f"uploads/{uuid.uuid4().hex}{ext}"

        # Subir a S3 — SIN ACL (tu bucket tiene ACLs desactivadas)
        s3_client.upload_fileobj(
            file.file,
            S3_BUCKET,
            key,
            ExtraArgs={
                "ContentType": file.content_type or "application/octet-stream",
            },
        )

        # URL pública estándar de S3
        url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}"

        return JSONResponse({"ok": True, "url": url})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir a S3: {e}")
