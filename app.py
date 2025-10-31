# app.py
import os
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from pydantic import BaseModel, EmailStr
import uvicorn

try:
    import stripe  # pip install stripe
except Exception:
    stripe = None

# --- Configuración básica ---
DEFAULT_ALLOWED = "https://mediazion.eu,https://www.mediazion.eu"
ALLOWED_ORIGINS = [o.strip() for o in (os.getenv("ALLOWED_ORIGINS") or DEFAULT_ALLOWED).split(",") if o.strip()]

STRIPE_SECRET = os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY") or ""
if stripe and STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET

app = FastAPI(title="MEDIAZION API", version="0.1.0")

app.add_middleware(
    CORSMBWF := CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modelos básicos ---
class ContactIn(BaseModel):
    name: str
    email: EmailStr
    subject: str | None = None
    message: str

class SubscribeIn(BaseModel):
    email: EmailStr
    priceId: str

# --- Rutas básicas ---
@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend"}

@app.post("/contact")
async def contact(payload: ContactIn):
    # Aquí envías e-mail vía SMTP real o un servicio (Mailgun/Sendgrid/etc.)
    # De momento devolvemos OK para que tu frontend funcione.
    return {"ok": True, "received": payload.dict()}

@app.post("/subscribe")
async def subscribe(data: SubscribeIn):
    if not stripe or not STRIPE_SECRET:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET no configurada o lib stripe no instalada")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{
                "price": data.priceId,
                "quantity": 1,
            }],
            success_url="https://mediazion.eu/suscripcion/ok",
            cancel_url="https://mediazion.eu/suscripcion/cancel",
            customer_creation="always",
        )
        return {"ok": True, "url": session.url}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")), reload=False)
