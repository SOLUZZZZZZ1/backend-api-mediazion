from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings, get_allowed_origins

from .payments import router as payments_router
from .mediadores_password_routes import router as mediadores_password_router
from .mediadores_routes import mediadores_router  # rutas PRO/BÁSICO + trial + directorio

app = FastAPI(title="MEDIAZION Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
  return {"ok": True, "service": "backend-api-mediazion-1", "version": "3.2.1"}

# Payments (Stripe) — si ya estaban en /api/payments dentro del router, lo dejamos igual
app.include_router(payments_router)

# 🔐 Cambio de contraseña de mediadores → ahora en /api/mediadores/change-password
app.include_router(mediadores_password_router, prefix="/api")

# 🟢 Estado PRO/BÁSICO + trial + directorio público → /api/mediadores/...
app.include_router(mediadores_router, prefix="/api")
