# contact_routes.py — endpoint de contacto para MEDIAZION
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

contact_router = APIRouter()

class ContactIn(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

@contact_router.post("/contact")
def submit_contact(data: ContactIn):
    """
    Endpoint de contacto.
    - Valida los campos básicos.
    - Aquí puedes integrar: envío de email / guardar en BD / Slack, etc.
    """
    # TODO: integra tu lógica real (guardar en BD, enviar correo, etc.)
    return {"ok": True, "received": data.model_dump()}
