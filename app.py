# app.py — MEDIAZION backend unificado (FastAPI + PostgreSQL + Stripe + Auth + Admin)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from utils_pg import ensure_db
from admin_routes import admin_router
from contact_routes import contact_router
from mediadores_routes import mediadores_router
from auth_routes import auth_router

# --- opcionales ---
try:
    from news_routes import news_router
except Exception:
    news_router = None

try:
    from upload_routes import upload_router
except Exception:
    upload_router = None

try:
    from stripe_routes import router as stripe_router
except Exception:
    stripe_router = None

try:
    from admin_manage_routes import admin_manage
except Exception:
    admin_manage = None

try:
    from db_routes import db_router
except Exception:
    db_router = None

try:
    from migrate_routes import router as migrate_router
except Exception:
    migrate_router = None


def parse_origins():
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]


# --- APP INIT ---
app = FastAPI(title="MEDIAZION Backend", version="3.2.1")

# crea tablas si no existen
ensure_db()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- STATIC ---
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --- ROUTERS ---
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(contact_router, prefix="", tags=["contact"])
app.include_router(mediadores_router, prefix="", tags=["mediadores"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])

if news_router:
    app.include_router(news_router, prefix="", tags=["news"])
if upload_router:
    app.include_router(upload_router, prefix="/upload", tags=["upload"])
if stripe_router:
    app.include_router(stripe_router, prefix="/stripe", tags=["stripe"])
if admin_manage:
    app.include_router(admin_manage, prefix="/admin", tags=["admin-manage"])
if db_router:
    app.include_router(db_router, prefix="/db", tags=["db"])
if migrate_router:
    app.include_router(migrate_router, prefix="/admin/migrate", tags=["migrate"])

# --- HEALTH ---
@app.get("/health")
def health():
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.1"}
