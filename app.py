# app.py — MEDIAZION backend (FastAPI + PostgreSQL + Stripe + Auth + Admin)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from utils_pg import ensure_db

# Routers principales (estos YA llevan su propio prefix en el archivo)
from admin_routes import admin_router               # prefix="/admin"
from contact_routes import contact_router           # prefix=""
from mediadores_routes import mediadores_router     # prefix="/mediadores"
from auth_routes import auth_router                 # prefix="/auth"

# Opcionales
try:
    from news_routes import news_router             # prefix=""
except Exception:
    news_router = None

try:
    from upload_routes import upload_router         # prefix="/upload" (o lo que tengas)
except Exception:
    upload_router = None

# Stripe (el router DEBE exponer prefix="/stripe" dentro de stripe_routes.py)
try:
    from stripe_routes import router as stripe_router  # prefix="/stripe" DENTRO del archivo
except Exception:
    stripe_router = None

# Utilidades admin y migración (opcionales)
try:
    from admin_manage_routes import admin_manage    # tiene su propio prefix
except Exception:
    admin_manage = None

try:
    from db_routes import db_router                 # si existe
except Exception:
    db_router = None

try:
    from migrate_routes import router as migrate_router  # temporal
except Exception:
    migrate_router = None


def parse_origins():
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="MEDIAZION Backend", version="3.2.1")

# Asegura esquema
ensure_db()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Health
@app.get("/health")
def health():
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.1"}

# Monta routers SIN repetir prefijos (ya vienen dentro de cada archivo)
app.include_router(admin_router)        # ya trae prefix="/admin"
app.include_router(contact_router)      # ""
app.include_router(mediadores_router)   # "/mediadores"
app.include_router(auth_router)         # "/auth"

if news_router:
    app.include_router(news_router)     # según tu archivo
if upload_router:
    app.include_router(upload_router)   # según tu archivo
if stripe_router:
    app.include_router(stripe_router)   # **debe exponer "/stripe/..." desde dentro**
if admin_manage:
    app.include_router(admin_manage)    # ya trae su prefix (p.ej. "/admin/mediadores")
if db_router:
    app.include_router(db_router)       # si existe
if migrate_router:
    app.include_router(migrate_router)  # temporal
