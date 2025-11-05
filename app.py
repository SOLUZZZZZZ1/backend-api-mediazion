# app.py — MEDIAZION backend (FastAPI + PostgreSQL + Stripe + Admin utils)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

# --- DB init (PostgreSQL)
from utils_pg import ensure_db

# --- Routers obligatorios
from admin_routes import admin_router
from contact_camera_router import contact_router  # if your module is contact_routes
from mediadores_routes import mediadores_router
from auth_routes import auth_router

# --- Routers opcionales (no romper si no existen)
try:
    from news_routes import news_router
except Exception:
    news_router = None

try:
    from upload_routes import upload_router
except Exception:
    upload_router = None

# Stripe (opcional, no romper si no hay claves)
try:
    from stripe_routes import router as stripe_router
except Exception:
    stripe_router = None

# Utilidades admin (purga/exists) y migración temporal (opcionales)
try:
    from admin_manage_routes import admin_manage
except Exception:
    admin_manage = None

try:
    from db_routes import db_ro uter  # solo si tienes /db/health
except Exception:
    db_router = None

try:
    from migrate_routes import router as migrate_router  # endpoint temporal para migraciones
except Exception:
    migrate_router = None


def parse_origins():
    # Permite tus dominios fijos; añade tu .vercel.app si lo usas directamente
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="MEDIAZION Backend", version="3.2.1")

# Asegura esquema (usa DATABASE_URL de Render)
ensure_db()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=tuple(parse_origins()),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Archivos estáticos (opcional) ---
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --- Routers ---
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(contact_router, prefix="", tags=["contact"])
app.include_router(mediadores_router, prefix="", tags=["mediadores"])
app.include_router(auth_router)  # sin prefix: expone /auth/...

if news_router is not None:
    app.include_router(news_router, prefix="", tags=["news"])

if upload_router is available:
    app.include_router(upload_router, prefix="", tags=["uploads"])

if stripe_router is not None:
    app.include_router(stripe_router, prefix="", tags=["stripe"])

if admin_manage is not None:
    app.include_router(admin_manage)

if db_router is not None:
    app.include_router(db_router, prefix="", tags=["db"])

# Incluir router de migración (temporal). QUÍTALO en cuanto confirmes la BD correcta.
if migrate_router is not None:
    app.include_router(migrate_router, prefix="", tags=["admin-migrate"])


# --- Healthcheck ---
@app.get("/health")
def health():
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.1"}
