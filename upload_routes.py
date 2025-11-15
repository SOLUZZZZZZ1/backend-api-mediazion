# upload_routes.py — Subida de archivos a S3 y devolución de URL pública

import os
import uuid
from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel
import boto3

upload_router = APIRouter(prefix="/upload", tags=["upload"])

S3_BUCKET = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-north-1")

if not S3_BUCKET:
    raise RuntimeError("Falta S3_BUCKET_NAME en las variables de entorno")

# Cliente S3
s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_TOKEN_ID") or os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)


class UploadResponse(BaseModel):
    ok: bool
    url: str


@upload_router.post("/file", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """
    Sube un archivo a S3 y devuelve una URL pública.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Falta nombre de archivo")

    try:
        # Generar nombre único
        ext = ""
        if "." in file.filename:
            _, ext = os.path.splitext(file.filename)

        key = f"uploads/{uuid.uuid4().hex}{ext}"

        # Subir el archivo a S3
        s3_client.upload_fileobj(
            file.file,
            S3_BUCKET,
            key,
            ExtraArgs={"ACL": "public-read", "ContentType": file.content_type},
        )

        # Construir URL pública estándar de S3
        url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{key}"

        return UploadResponse(ok=True, url=url)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al subir a S3: {str(e)}")
