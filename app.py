# app.py — MEDIAZION backend (FastAPI + PostgreSQL + Stripe + Admin utils)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

# ---- DB init (PostgreSQL)
try:
    from utils_pg import ensure_db  # your utils_pg exposes ensure_db()
except Exception:
    ensure_db = None

# ---- Routers (required/primary)
# We try common module names and fall back gracefully to avoid hard crashes during import.
mediadores_router = None
try:
    # Preferred: mediadores_routes.py exports mediadores_router
    from mediadores_routes import mediadores_router as _mediadores_router
    mediadores_router = _mediadores_router
except Exception:
    try:
        # Alternate legacy: mediadores_module.py exports mediadores_routes (APIRouter)
        from mediadores_module import mediadores_routes as _mediadores_router_alt
        mediadores_router = _mediadores_router_alt
    except Exception:
        mediadores_router = None  # keep going; we'll just not mount it

try:
    from admin_routes import admin_router
except Exception:
    admin_router = None

try:
    from contact_routes import contact_router
except Exception:
    contact_router = None

try:
    from auth_routes import auth_router
except Exception:
    auth_router = None

# ---- Optional routers
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


app = FastAPI(title="MEDIAZION Backend", version="3.2.4")

# Init DB softly (don't block on bootstrap errors)
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
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.4"}

# ------ API prefix aligned with frontend ------
API_PREFIX = "/api"

# Mount routers only if they imported correctly
if admin_router is not None:
    app.include_router(admin_router, prefix=API_PREFIX, tags=["admin"])

if contact_router is not None:
    app.include_router(contact_router, prefix=API_PREFIX, tags=["contact"])

if mediadores_router is not None:
    app.include_router(mediadores_router, prefix=API_PREFIX, tags=["mediadores"])

if auth_router is not None:
    app.include_router(auth_router, prefix=API_PREFIX, tags=["auth"])

if news_router is not None:
    app.include_router(news_router, prefix=API_PREFIX, tags=["news"])

if upload_router is not None:
    app.include_router(upload_router, prefix=API_PREFIX, tags=["uploads"])

if stripe_router is not None:
    # /api/stripe/subscribe, /api/stripe/confirm, /api/stripe/webhook
    app.include_router(stripe_router, prefix=API_PREFIX, tags=["stripe"])

if admin_manage is not None:
    app.include_router(admin_manage, prefix=API_PREFIX)

if db_router is not None:
    app.include_router(db_router, prefix=API_PREFIX, tags=["db"])

if migrate_router is not None:
    app.include_router(migrate_router, prefix=API_PREFIX, tags=["admin-migrate"])
