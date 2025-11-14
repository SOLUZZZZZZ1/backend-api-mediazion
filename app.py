# app.py — Mediazion Backend (estable y completo)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

app = FastAPI(title="Mediazion Backend", version="1.3.1")

# ---------------- CORS ----------------
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

# -------------- STATIC /uploads --------------
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# -------------- HEALTH --------------
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "service": "mediazion-backend"})


# -------------- IMPORT ROUTERS --------------
from auth_routes import auth_router
from ai_routes import ai_router
from upload_routes import upload_router
from actas_routes import actas_router
from contact_routes import contact_router
from voces_routes import voces_router
from news_routes import news_router
from ai_legal_chat_routes import ai_legal_chat
from perfil_routes import perfil_router


try:
    from ai_legal_routes import ai_legal_router
except:
    ai_legal_router = None

try:
    from mediadores_routes import mediadores_router
except:
    mediadores_router = None

try:
    from migrate_routes import router as migrate_router
except:
    migrate_router = None


# -------------- REGISTER ROUTERS --------------
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(ai_router, prefix="/api/ai", tags=["ai"])
app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(actas_router, prefix="/api", tags=["actas"])
app.include_router(contact_router, prefix="/api", tags=["contact"])
app.include_router(perfil_router, prefix="/api", tags=["perfil"])
app.include_router(voces_router, prefix="/api", tags=["voces"])
app.include_router(news_router, prefix="/api", tags=["news"])
app.include_router(ai_legal_chat, prefix="/api")

if ai_legal_router:
    app.include_router(ai_legal_router, prefix="/api", tags=["ai-legal"])

if mediadores_router:
    app.include_router(mediadores_router, prefix="/api", tags=["mediadores"])

if migrate_router:
    app.include_router(migrate_router, prefix="/api/admin", tags=["admin"])
