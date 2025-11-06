# app.py — MEDIAZION backend (FastAPI + PostgreSQL + Stripe + Admin utils)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

# --- DB init (PostgreSQL)
from utils_pg import import_db as _db  # if your module is utils_pg and exposes ensure_db()
ensure_db = getattr(_db, "ensure_db", None) or getattr(_db, "ensure_db", None)
if ensure_db is None:
    # Fallback if import alias not needed
    from utils_pg import ensure_db as _ensure
    ensure_db = _ensure

# --- Routers (required)
from admin_routes import admin_router
from contact_routes import contact_router
from mediadores_module import mediadores_routes as mediadores_router  # if your file is mediadores_routes.py with "mediadores_router"
from auth_routes import auth_router

# If your mediadores router is defined as "mediadores_router", re-alias here:
try:
    from mediadores_routes import mediadores_router as _m_router
    mediadores_router = _m_router
except Exception:
    pass

# --- Optional routers
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


def parse_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="MEDIAZION Backend", version="3.2.1")

# Init DB
if callable(ensure_db):
    ensure_db()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=tuple(parse_origins()),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Static
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Health
@app.get("/health")
def health():
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.1"}

# Routers
app.include_router(admin_router,      prefix="/",          tags=["admin"])
app.include_router(contact_router,    prefix="",           tags=["contact"])
app.include_router(mediadores_router, prefix="",           tags=["mediadores"])
app.include_router(auth_router,       prefix="",           tags=["auth"])

if news_router is not None:
    app.include_router(news_router,   prefix="",           tags=["news"])

if upload_router is not None:
    app.include_router(upload_router, prefix="",           tags=["uploads"])

if stripe_router is not None:
    app.include_router(stripe_router, prefix="",           tags=["stripe"])  # exposes /stripe/...

if admin_manage is not None:
    app.include_router(admin_manage)  # /admin/mediadores/* (TEMPORAL – remove later)

if db_router is not None:
    app.include_router(db_router,     prefix="",           tags=["db"])

if migrate_router is not None:  # TEMPORAL – remove when done
    app.include_router(migrate_router, prefix="",          tags=["admin-migrate"])
