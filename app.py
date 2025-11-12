# app.py — MEDIAZION Backend (FastAPI unificado)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

app = FastAPI(title="MEDIAZION Backend", version="3.6.2")

# --- CORS ---
def parse_origins():
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu,https://*.vercel.app")
    return [o.strip() for o in raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# --- uploads ---
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/health")
def health():
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.6.2"}

API_PREFIX = "/api"

def _safe_include(router, prefix=API_PREFIX, tags=None):
    if router is not None:
        app.include_router(router, prefix=prefix, tags=tags or [])

# --- AUTH ---
try:
    from auth_routes import auth_router
except Exception:
    auth_router = None
_safe_include(auth_router, tags=["auth"])

# --- UPLOAD ---
try:
    from upload_routes import upload_router
except Exception:
    upload_router = None
_safe_include(upload_router, tags=["upload"])

# --- PERFIL ---
try:
    from perfil_routes import perfil_router
except Exception:
    perfil_router = None
_safe_include(perfil_router, tags=["perfil"])

# --- ACTAS (DOCX/PDF) ---
try:
    from actas_routes import actas_router
except Exception:
    actas_router = None
_safe_include(actas_router, tags=["actas"])

# --- IA normal ---
try:
    from ai_routes import ai_router
except Exception:
    ai_router = None
_safe_include(ai_router, tags=["ai"])

# --- IA LEGAL (Modo experto jurídico) ---
try:
    from ai_legal_routes import ai_legal_router
except Exception:
    ai_legal_router = None
_safe_include(ai_legal_router, tags=["ai-legal"])

# --- CONTACTO ---
try:
    from contact_routes import contact_router
except Exception:
    contact_router = None
_safe_include(contact_router, tags=["contact"])

# --- NEWS / ACTUALIDAD ---
try:
    from news_routes import router as news_router
except Exception:
    news_router = None
_safe_include(news_router, tags=["news"])

# --- VOCES ---
try:
    from voces_routes import voces_router
except Exception:
    voces_router = None
_safe_include(voces_router, tags=["voces"])

# --- MIGRACIONES ADMIN ---
try:
    from migrate_routes import router as migrate_router
except Exception:
    migrate_router = None
_safe_include(migrate_router, tags=["admin-migrate"])

# --- STRIPE (opcional) ---
try:
    from stripe_routes import router as stripe_router
except Exception:
    stripe_router = None
_safe_include(stripe_router, tags=["stripe"])
