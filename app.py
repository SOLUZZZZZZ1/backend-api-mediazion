# app.py — MEDIAZION backend (FastAPI + PostgreSQL + Stripe + Admin utils)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from utils_pg import ensure_db

# --- Routers obligatorios
from admin_routes import admin_router
from contact_routes import contact_router
from mediadores_routes import mediadores_router
from auth_routes import auth_router

# --- Routers opcionales (no fallar si no existen)
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

# Utilidades admin opcionales (purga/exists) y migración temporal
try:
    from admin_manage_routes import admin_manage
except Exception:
    admin_manage = None

try:
    from db_routes import db_router  # si lo tienes
except Exception:
    db_router = None

try:
    from migrate_routes import router as migrate_router  # endpoint temporal para migraciones
except Exception:
    migrate_router = None


def parse_origins():
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]

app = FastAPI(title="MEDIAZION Backend", version="3.2.1")

# Asegura esquema (usa DATABASE_URL de Render)
ensure_db();
