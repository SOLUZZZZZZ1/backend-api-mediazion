# app.py — BACKEND LIMPIO Y FUNCIONAL PARA MEDIAZION

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

app = FastAPI(title="Mediazion Backend", version="1.0.0")

# --------------------------
# 1. CORS
# --------------------------
ALLOWED = [
    "https://mediazion.eu",
    "https://www.mediazion.eu",
    "https://*.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED,
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# --------------------------
# 2. STATIC /uploads
# --------------------------
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --------------------------
# 3. HEALTH CHECK
# --------------------------
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "service": "mediazion-backend"})


# --------------------------
# 4. ROUTERS (TODOS CORRECTOS)
# --------------------------

# AUTH
from auth_routes import auth_router
app.include_router(auth_router, prefix="/api", tags=["auth"])

# IA principal
from ai_routes import ai_router
app.include_router(ai_router, prefix="/api", tags=["ai"])

# IA legal (si existe)
try:
    from ai_legal_routes import ai_legal_router
    app.include_router(ai_legal_router, prefix="/api", tags=["ai-legal"])
except:
    pass

# VOCES / BLOG
try:
    from voces_routes import voces_router
    app.include_router(voces_router, prefix="/api", tags=["voces"])
except:
    pass

# CONTACTO
try:
    from contact_routes import contact_router
    app.include_router(contact_router, prefix="/api", tags=["contact"])
except:
    pass

# NEWS
try:
    from news_routes import news_router
    app.include_router(news_router, prefix="/api", tags=["news"])
except:
    pass

# ACTAS (DOCX)
try:
    from actas_routes import actas_router
    app.include_router(actas_router, prefix="/api", tags=["actas"])
except:
    pass

# UPLOAD
try:
    from upload_routes import upload_router
    app.include_router(upload_router, prefix="/api", tags=["upload"])
except:
    pass

# MIGRACIONES ADMIN
try:
    from migrate_routes import router as migrate_router
    app.include_router(migrate_router, prefix="/api/admin", tags=["admin"])
except:
    pass
