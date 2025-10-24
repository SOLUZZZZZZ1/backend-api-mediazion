# app.py
import os
import stripe
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

STRIPE_SECRET = os.environ.get("STRIPE_SECRET")  # -> configurada en Render
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")  # para verificar webhooks

if not STRIPE_SECRET:
    raise RuntimeError("STRIPE_SECRET no configurada en variables de entorno")

stripe.api_key = STRIPE_SECRET

app = FastAPI()

# CORS - permite tu frontend en Vercel / dominio producción
origins = [
    "https://mediazion-frontend-1vejbucb3-soluzzzs-projects.vercel.app",
    "https://mediazion-frontend.vercel.app",
    "https://mediazion.eu",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CreateCheckoutRequest(BaseModel):
    price_cents: int  # o amount
    currency: str = "eur"
    description: str = "Compra Mediazion"

@app.post("/create-checkout-session")
async def create_checkout_session(body: CreateCheckoutRequest):
    try:
        # ejemplo con Stripe Checkout (más simple)
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": body.currency,
                    "product_data": {"name": body.description},
                    "unit_amount": body.price_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url="https://mediazion-frontend-1vejbucb3-soluzzzs-projects.vercel.app/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://mediazion-frontend-1vejbucb3-soluzzzs-projects.vercel.app/cancel",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Webhook endpoint (verificar firma)
@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        # en desarrollo (no recomendado en producción)
        try:
            event = stripe.Event.construct_from(await request.json(), stripe.api_key)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")

    # Maneja eventos que te interesen
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # Aquí guardas la orden, envías correo, etc.
        print("Pago completado para session:", session.get("id"))

    return {"ok": True}

# health / contacto etc ya existentes...
