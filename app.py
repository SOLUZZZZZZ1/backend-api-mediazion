# app.py — Mediazion Backend (FastAPI) con todos los routers registrados
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os

# Opcional: si tienes un módulo db.py con pg_conn, no se usa aquí.
# from db import pg_conn

app = FastAPI(title="Mediazion Backend", version="1.2.0")

# CORS para Vercel y dominios propios
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "https://mediazion.vercel.app,https://www.mediazion.eu,https://mediazion.eu").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS] if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Salud
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "service": "mediazion-backend", "version": "1.2.0"})

# --- IMPORTS DE ROUTERS ---
from actas_routes import actas_router
from upload_routes import upload_router
from voces_routes import voces_router
from ai_routes import ai_router
from contact_routes import contact_router
from voces_routes import voces_router
from news_routes import voces_router as noticias_router
from auth_routes import auth_router

# Registros bajo /api
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(actas_router,  prefix="/api", tags=["actas"])
app.include_router(contact_router, prefix="/api", tags=["mail"])
app.include_router(voces_router,  prefix="/api", tags=["voces"])
app.include_router(noticias_router, prefix="/api", tags=["news"])
app.include_router(ai_roter,       prefix="/api", tags=["ai"])

# Si tienes un router de "status" de mediadores/usuarios, añádelo:
# from mediadores_routes import mediadores_router
# app.include_router(mediadores_router, prefix="/api", tags=["mediadores"])
