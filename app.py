# app.py — MEDIAZION backend (FastAPI + PostgreSQL + Stripe · unified routers)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

# ---------- DB bootstrap ----------
try:
    from utils_pg import ensure_db  # your utils_pg exposes ensure_db()
except Exception:
    ensure_db = None

def parse_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]

# ---------- App ----------
app = FastAPI(title="MEDIAZION Backend", version="3.2.5")

# Init DB softly (do not block startup)
if callable(ensure_db):
    try:
        ensure_db()
    except Exception:
        pass

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=tuple(parse_origins()),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Static files
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Health
@app.get("/health")
def health():
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.5"}

# ---------- API prefix aligned with frontend ----------
API_PREFIX = "/api"

# ---------- Core routers (import robustly, mount only if present) ----------
def _safe_include(router, *, prefix: str, tags: list[str] | None = None):
    if router is not None:
        app.include_router(router, prefix=prefix, tags=tags or [])

# Admin
try:
    from admin_routes import admin_router
except Exception:
    admin_router = None
_safe_include(admin_router, prefix=API_PREFIX, tags=["admin"])

# Contact
try:
    from contact_routes import contact_router
except Exception:
    contact_router = None
_safe_include(contact_router, prefix=API_PREFIX, tags=["contact"])

# Mediadores (try common module names)
mediadores_router = None
try:
    from mediadores_routes import mediadores_router as _mr
    mediadores_router = _mr
except Exception:
    try:
        from mediadores_module import mediadores_routes as _mr_alt
        mediadores_router = _mr_alt
    except Exception:
        mediadores_router = None
_safe_include(mediadores_router, prefix=API_PREFIX, tags=["mediadores"])

# Auth
try:
    from auth_routes import auth_router
except Exception:
    auth_router = None
_safe_include(auth_router, prefix=API_PREFIX, tags=["auth"])

# News (optional)
try:
    from news_routes import news_router
except Exception:
    news_router = None
_safe_include(news_router, prefix=API_PREFIX, tags=["news"])

# Uploads (optional)
try:
    from upload_routes import upload_router
except Exception:
    upload_router = None
_safe_include(upload_router, prefix=API_PREFIX, tags=["uploads"])

# ---------- Stripe (Subscriptions via Checkout) ----------
try:
    from stripe_routes import router as stripe_router  # exposes /stripe/subscribe|confirm|webhook
except Exception:
    stripe_router = None
_safe_include(stripe_router, prefix=API_PREFIX, tags=["stripe"])

# ---------- Payments (one-off PaymentIntents via Elements) ----------
# This is the router from the other implementation you shared. It's optional.
try:
    # If your file is named payments_routes.py and exposes "router"
    from payments_routes import router as payments_router
except Exception:
    payments_router = None
_safe_include(payments_router, prefix=API_PREFIX, tags=["payments"])

# ---------- Admin manage (temporary utilities) ----------
try:
    from admin_manage_routes import admin_manage
except Exception:
    admin_manage = None
_safe_include(admin_manage, prefix=API_PREFIX, tags=["admin-mediadores"])

# ---------- DB utilities / migrations (optional) ----------
try:
    from db_routes import db_router
except Exception:
    db_router = None
_safe_include(db_router, prefix=API_PREFIX, tags=["db"])

try:
    from migrate_routes import router as migrate_router
except Exception:
    migrate_router = None
_safe_include(migrate_router, prefix=API_PREFIX, tags=["admin-migrate"])
