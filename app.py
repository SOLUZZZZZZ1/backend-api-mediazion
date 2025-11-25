# ---------------------------------------------------------
# app.py — Backend Mediazion (versión ordenada por módulos)
# ---------------------------------------------------------

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles


# ---------------------------------------------------------
# APP BASE
# ---------------------------------------------------------
app = FastAPI(
    title="Mediazion Backend",
    version="1.4.0",
    description="Backend oficial de Mediazion — Mediación Profesional",
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------
ALLOWED_ORIGINS = [
    "https://mediazion.eu",
    "https://www.mediazion.eu",
    "https://*.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# ---------------------------------------------------------
# STATIC FILES (uploads)
# ---------------------------------------------------------
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "service": "mediazion-backend"})


# ---------------------------------------------------------
# IMPORT ROUTERS (orden profesional)
# ---------------------------------------------------------

# 🔹 Autenticación mediadores
from auth_routes import auth_router

# 🔹 IA general
from ai_routes import ai_router

# 🔹 IA Legal (opcional)
try:
    from ai_legal_routes import ai_legal
except:
    ai_legal = None

# 🔹 Subida de archivos
from upload_routes import upload_router

# 🔹 Actas DOCX/PDF
from actas_routes import actas_router

# 🔹 Contacto web
from contact_routes import contact_router

# 🔹 Blog / Voces
from voces_routes import voces_router

# 🔹 Noticias externas
from news_routes import news_router

# 🔹 Perfil del mediador
from perfil_routes import perfil_router

# 🔹 Registro de mediadores
from mediadores_register_routes import register_router

# 🔹 Cambio de contraseña mediadores
from mediadores_password_routes import router as mediadores_password_router

# 🔹 Agenda del mediador
from agenda_routes import agenda_router

# 🔹 Mediadores (estado PRO/BASIC, etc.)
try:
    from mediadores_routes import mediadores_router
except:
    mediadores_router = None

# 🔹 Stripe (suscripciones)
try:
    from stripe_routes import router as stripe_router
except:
    stripe_router = None

# 🔹 Migraciones y utilidades admin
try:
    from migrate_routes import router as migrate_router
except:
    migrate_router = None

# 🔹 Casos / expedientes
try:
    from casos_routes import casos_router
except:
    casos_router = None

# 🔹 Instituciones (registro institucional)
try:
    from instituciones_routes import instituciones_router
except:
    instituciones_router = None
from instituciones_casos_routes import router as instituciones_casos_router
from instituciones_actas_routes import router as instituciones_actas_router
from instituciones_agenda_routes import router as instituciones_agenda_router
from instituciones_api import router as instituciones_api_router

# 🔹 Instituciones · admin (NUEVO)
try:
    from instituciones_admin_routes import admin_instituciones_router
except:
    admin_instituciones_router = None
from instituciones_login_routes import router as instituciones_login_router


# ---------------------------------------------------------
# REGISTER ROUTERS (orden estable y limpio)
# ---------------------------------------------------------

# Autenticación mediadores
app.include_router(auth_router, prefix="/api", tags=["auth"])

# IA
app.include_router(ai_router, prefix="/api/ai", tags=["ai"])

# IA Legal
if ai_legal:
    app.include_router(ai_legal, prefix="/api", tags=["ai-legal"])

# Uploads
app.include_router(upload_router, prefix="/api", tags=["upload"])

# Actas
app.include_router(actas_router, prefix="/api", tags=["actas"])

# Contacto
app.include_router(contact_router, prefix="/api", tags=["contact"])

# Blog / Voces
app.include_router(voces_router, prefix="/api", tags=["voces"])

# Noticias externas
app.include_router(news_router, prefix="/api", tags=["news"])

# Perfil mediador
app.include_router(perfil_router, prefix="/api", tags=["perfil"])

# Registro mediadores
app.include_router(register_router, prefix="/api", tags=["mediadores"])

# Cambio contraseña mediadores
app.include_router(mediadores_password_router, prefix="/api", tags=["mediadores-password"])

# Agenda
app.include_router(agenda_router, prefix="/api", tags=["agenda"])

# Mediadores (estado, trial, PRO, etc.)
if mediadores_router:
    app.include_router(mediadores_router, prefix="/api", tags=["mediadores"])

# Stripe
if stripe_router:
    app.include_router(stripe_router, prefix="/api", tags=["stripe"])

# Migraciones / admin
if migrate_router:
    app.include_router(migrate_router, prefix="/api/admin", tags=["admin"])

# Casos / expedientes
if casos_router:
    app.include_router(casos_router, prefix="/api", tags=["casos"])

# Instituciones (público)
if instituciones_router:
    # OJO: el router ya tiene prefix="/instituciones"
    # Así la ruta final queda: /api/instituciones/registro
    app.include_router(instituciones_router, prefix="/api", tags=["instituciones"])
    app.include_router(instituciones_login_router)
    app.include_router(instituciones_casos_router)
    app.include_router(instituciones_actas_router)
    app.include_router(instituciones_agenda_router)
    app.include_router(instituciones_api_router)

# Instituciones · admin (NUEVO)
if admin_instituciones_router:
    app.include_router(
        admin_instituciones_router,
        prefix="/api",
        tags=["instituciones-admin"],
    )


# ---------------------------------------------------------
# END
# ---------------------------------------------------------
