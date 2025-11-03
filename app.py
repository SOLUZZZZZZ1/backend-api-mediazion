# app.py — FastAPI con PostgreSQL para MEDIAZION
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles

from utils_pg import ensure_db  # usa Postgres
from admin_routes import admin_router
from mediadores_routes import mediadores_router
from news_routes import news_router
from upload_routes import upload_router
from contact_routes import contact_router
from stripe_routes import router as stripe_router  # descomentar si ya lo tienes listo para PG

def parse_origins():
    raw = os.getenv("ALLOWED_ORIGINS", "https://mediazion.eu,https://www.mediazion.eu")
    return [o.strip() for o in raw.split(",")] if raw else []

app = FastAPI(title="MEDIAZION Backend", version="3.2.0")

# Crea tablas si no existen (Postgres)
ensure_db()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=tuple(parse_origins()),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# estáticos (si los usas)
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

from db_routes import db_router
# Routers
app.include_router(admin_router,      prefix="/admin", tags=["admin"])
app.include_router(mediadores_router, prefix="",       tags=["mediadores".replace("mediadores","mediadores")])
app.include_router(news_router,       prefix="",       tags=["news"])
app.include_router(upload_router,     prefix="",       tags=["uploads"])
app.include_router(contact_router)  # POST /contact
app.include_router(db_router, prefix="", tags=["db"])
app.include_router(stripe_router,  prefix="", tags=["stripe"])  # habilita cuando migres stripe a PG

@app.get("/files".replace("files","health"))
def health():
    return {"ok": True, "service": "mediazion-backend", "version": "3.2.0"}
