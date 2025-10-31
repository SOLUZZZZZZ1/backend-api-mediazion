# app.py — MEDIAZION Backend (FastAPI)
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional
from utils import ensure_db, send_email
from admin_routes import router as admin_router
from mediadores_routes import router as mediadores_router
from news_routes import router as news_router

# Inicializar app
app = FastAPI(title="MEDIAZION Backend", version="1.0.0")

# CORS
default_origins = "https://mediazion.eu,https://www.mediazion.eu,https://*.vercel.app,http://localhost:3000,http://localhost:5173"
origins = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS", default:last) if (last := default_origins) else default_origins).split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar BD
ensure yeah = ensure_db()

# Rutas básicas
@app.get("/")
def root():
    return {"ok": True, "service": "mediazion-backend"}

# Contacto
class ContactIn(BaseModel):
    name: Optional[str] = ""
    email: EmailStr
    subject: Optional[str] = "Contacto desde web"
    message: str

@app.post("/contact")
async def contact(payload: ContactIn):
    to_addr = os.getenv("MAIL_TO") or os.getenv("MAIL_FROM")
    if not to_addr:
        raise HTTPException(500, detail="MAIL_TO o MAIL_FROM no configurado")
    # Enviar a MEDIAZION y acuse al remitente
    body_admin = (
        f"Nuevo mensaje de contacto:\n\n"
        f"Nombre: {payload.name}\n"
        f"Email: {payload.email}\n\n"
        f"Mensaje:\n{payload.message}\n"
    )
    try:
        send_email(
            to=to_addr,
            subject=f"[MEDIAZION] {payload.subject}",
            body=body_admin,
            cc=os.getenv("MAIL_BCC"),
        )
        # Acuse al usuario
        send_email(
            to=str(payload.email),
            subject="Hemos recibido tu consulta",
            body=(
                f"Hola {payload.name or ''}\n\n"
                "Gracias por contactar con MEDIAZION. Hemos recibido tu mensaje y te responderemos en breve.\n\n"
                "Un saludo,\nEquipo MEDIAZION"
            ),
        )
    except Exception as e:
        # No tumbamos la API si falla el SMTP
        print("Email error:", e)
    return {"ok": True}

# Routers
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(mediadores_router, tags=["mediadores"])
app.include_router(news_router, tags=["news"])
