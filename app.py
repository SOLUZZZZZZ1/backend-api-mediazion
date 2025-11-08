# app.py — MEDIAZION backend (FastAPI) · todo bajo /api
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

try:
    from utils_pg import ensure_db
except Exception:
    ensure_db = None

app = FastAPI(title="MEDIAZION Backend", version="3.6.1")

if callable(ensure_db):
    try:
        ensure_db()
    except Exception:
        pass

def parse_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=tuple(parse_origins()),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# archivos subidos
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/health")
def health():
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.6.1"}

API_PREFIX = "/api"
def _safe_include(router, prefix: str, tags=None):
    if router is not None:
        app.include_router(router, prefix=prefix, tags=tags or [])

# ---- AUTH (arregla /api/auth/login)
try:
    from auth_routes import auth_router
except Exception:
    auth_router = None
_safe_include(auth_router, prefix=API_PREFIX, tags=["auth"])

# ---- UPLOAD (/api/upload/file)
try:
    from upload_routes import upload_router
except Exception:
    upload_router = None
_safe_include(upload_router, prefix=API_PREFIX, tags=["upload"])

# ---- PERFIL (/api/perfil, /api/perfil/public)
try:
    from perfil_routes import perfil_router
except Exception:
    perfil_router = None
_safe_include(perfil_router, prefix=API_PREFIX, tags=["perfil"])

# ---- VOCES (/api/voces)
try:
    from voces_routes import voces_router
except Exception:
    voces_router = None
_safe_include(voces_router, prefix=API_PREFIX, tags=["voces"])

# ---- ACTAS (/api/actas/render_docx)
try:
    from actas_routes import actas_router
except Exception:
    actas_router = None
_safe_include(actas_router, prefix=API_PREFIX, tags=["actas"])

# ---- IA (/api/ai/assist, /api/ai/assist_with)
try:
    from ai_routes import ai_router
except Exception:
    ai_router = None
if ai_router is not None:
    app.include_router(ai_router, prefix=f"{API_PREFIX}/ai", tags=["ai"])

# ---- STRIPE / PAYMENTS
try:
    from stripe_routes import router as stripe_router
except Exception:
    stripe_router = None
_safe_include(stripe_router, prefix=API_PREFIX, tags=["stripe"])

try:
    from payments_routes import router as payments_router
except Exception:
    payments_router = None
_safe_include(payments_router, prefix=API_PREFIX, tags=["payments"])

# ---- utilidades PRO opcionales
try:
    from plantillas_routes import plantillas_router
except Exception:
    plantillas_router = None
_safe_include(plantillas_router, prefix=API_PREFIX, tags=["plantillas"])

try:
    from casos_routes import casos_router
except Exception:
    casos_router = None
_safe_include(casos_router, prefix=API_PREFIX, tags=["casos"])

try:
    from agenda_routes import agenda_router
except Exception:
    agenda_router = None
_safe_include(agenda_router, prefix=API_PREFIX, tags=["agenda"])

# ---- MIGRACIONES admin
try:
    from migrate_routes import router as migrate_router
except Exception:
    migrate_router = None
_safe_include(migrate_router, prefix=API_PREFIX, tags=["admin-migrate"])

# (opcional) mediadores legacy (antiguos formularios sin /api)
try:
    from mediadores_routes import mediadores_router as _mr
except Exception:
    _mr = None
_safe_include(_mr, prefix=API_PREFIX, tags=["mediadores"])
