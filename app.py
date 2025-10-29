# app.py — MEDIAZION (arranque principal)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from utils import ensure_db  # db(), sha256(), send_email(), etc. viven en utils.py
from admin_routes import admin_router
from ai_routes import ai_router
from mediadores_routes import mediadores_router
from news_routes import news_router

def parse_origins(raw: str | None) -> list[str]:
    if not raw:
        # dominios por defecto
        return [
            "https://mediazion.eu",
            "https://www.mediazion.eu",
        ]
    return [o.strip() for o in raw.split(",") if o.strip()]

# ---------------- App ----------------
app = FastAPI(title="MEDIAZION Backend", version="3.0.0")

# Asegura tablas/columnas
ensure_db()

# CORS
ALLOWED_ORIGINS = parse_origins(os.getenv("ALLOWED_ORIGINS"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static: uploads (fotos/CV)
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Routers (prefijos claros)
app.include_router(admin_router,      prefix="/admin",        tags=["admin"])
app.include_router(ai_router,         prefix="/ai",           tags=["ai"])
app.include_router(mediadores_router, prefix="",              tags=["mediadores"])
app.include_router(news_router,       prefix="",              tags=["news"])

# Salud
@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend", "version": "3.0.0"}
