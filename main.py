from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings, get_allowed_origins

from .payments import router as payments_router

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


# Payments (Stripe)
app.include_router(payments_router)
