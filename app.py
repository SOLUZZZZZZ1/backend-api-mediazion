# app.py — MEDIAZION backend bootstrap
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# --- CORS: orígenes permitidos ---
DEFAULT_ALLOWED = ["https://mediazion.eu", "https://www.mediazion.eu"]
_env = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [o.strip() for o in _env.split(",") if o.strip()] or DEFAULT_ALLOWED

app = FastAPI(title="MEDIAZION Backend", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers opcionales: si alguno no existe, no rompe el arranque ---
def _try_include(router_import, prefix: str = "", tags=None):
    try:
        router = router_import()
        if router:
            app.include_router(router, prefix=prefix, tags=tags or [])
    except Exception as e:
        # No frenamos el arranque por un router — revisa logs en Render
        print(f"[WARN] No se cargó router {router_import.__name__}: {e}")

# Wrappers ligeros para importar routers sólo si están
def _admin_router():
    from admin_routes import admin_router
    return admin_router

def _mediadores_router():
    from mediadores_routes import mediadores_router
    return mediadores_router

def _news_router():
    from news_routes import news_router
    return news_router

def _ai_router():
    from ai_routes import ai_router
    return ai_router

_try_include(_admin_router, prefix="/admin", tags=["admin"])
_try_include(_mediadores_router, prefix="", tags=["mediadores"])
_try_include(_news_router, prefix="", tags=["news"])
_try_include(_ai_router, prefix="/ai", tags=["ai"])

@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend", "version": "3.1.0"}
