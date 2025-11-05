# app.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

# --- DB init (PostgreSQL) ---
from utils_pg import ensure_db  # crea tablas si no existen

# --- Routers principales ---
from admin_routes import admin_router
from contact_routes import contact_router

# Estos pueden no existir en algunos despliegues: importa con fallback
try:
    from mediadores_routes import mediadores_router
except Exception:
    mediadores_router = None

try:
    from news_routes import news_router
except Exception:
    news_router = None

try:
    from auth_routes import auth_router
except Exception:
    auth_routes = None

try:
    from upload_routes import upload_router
except Exception:
    upload_router = None

# Stripe es opcional: si faltan secrets, no bloquea el arranque
stripe_router = None
try:
    from stripe_routes import router as _stripe_router
    stripe_router = _stripe_router
except Exception:
    stripe_router = None

# Ruta de salud BD opcional
db_router = None
try:
    from db_routes import db_router as _db_router
    db_router = _db_router
except Exception:
    db_router = None

# Migrações temporales (endpoint para ejecutar la migración desde el backend)
# Este router es temporal: cuando confirmes, bórralo (y quita la inclusión más abajo).
migrate_router = None
try:
    from migrate_routes import router as _migrate_router
    migrate_router = _migrate_router
except Exception:
    migrate_router = None


def parse_origins():
    """
    Dominios explícitos permitidos (separados por coma) desde ALLOWED_ORIGINS.
    Deja en entorno, por ejemplo:
      https://mediazion.eu,https://www.mediazion.eu
    """
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="MEDIAZION Backend", version="3.2.1")

# Crea tablas si no existen (PostgreSQL)
# Nota: ensure_db() debe usar la variable DATABASE_URL de Render
ensure_db()

# --- CORS ---
# 1) Permite solo dominios fijos desde ALLOWED_ORIGINS
# 2) Además, permite cualquier subdominio *.vercel.app (para deploys sin tocar env)
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_origins(),
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

if mediadores_router is not None:
    app.include_router(mediadores_router, prefix="", tags=["mediadores"])

if news_router is not None:
    app.include_router(news_router, prefix="", tags=["news"])

if auth_router is not None:
    app.include_router(auth_router)

if upload_router is not None:
    app.include_router(upload_router, prefix="", tags=["uploads"])

if stripe_router is not None:
    app.include_router(stripe_router, prefix="", tags=["stripe"])

if db_router is not None:
    app.include_router(db_router, prefix="", tags=["db"])

# Incluimos el router de migración **solo si existe** (temporal)
if migrate_router is not None:
    app.include_router(migrate_router, prefix="", tags=["admin-migrate"])


@app.get("/health")
def health():
    # Nombre de servicio actualizado
    return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.1"}
