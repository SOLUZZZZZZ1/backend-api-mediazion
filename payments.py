from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import stripe
from .config import settings

router = APIRouter(prefix="/payments", tags=["payments"])

if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key

class CreateIntentIn(BaseModel):
    amount_eur: int = Field(..., gt=0, description="Importe en euros, entero (ej: 150 => 150 €)")
    description: str | None = None
    customer_email: str | None = None

@router.post("/create-intent")
def create_intent(payload: CreateIntentIn):
    if not settings.stripe_secret_key:
        raise HTTPException(500, "Stripe no está configurado en el backend")
    # PaymentIntent amount in cents
    amount_cents = payload.amount_eur * 100
    try:
        pi = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="eur",
            automatic_payment_methods={"enabled": True},
            description=payload.description or "MEDIAZION pago",
            receipt_email=payload.customer_email,
            statement_descriptor=settings.statement_descriptor[:22] if settings.statement_descriptor else "MEDIAZION",
        )
        return {"clientSecret": pi.client_secret}
    except Exception as e:
        raise HTTPException(400, f"Stripe error: {str(e)}")

class WebhookIn(BaseModel):
    # placeholder to allow raw body read
    pass

@router.post("/webhook")
async def stripe_webhook(request: Request):
    if not settings.stripe_webhook_secret:
        # If not set, accept all (useful in dev) – but log a warning
        raw = await request.body()
        try:
            event = stripe.Event.construct_from(await request.json(), stripe.api_key)
        except Exception:
            return {"received": True, "note": "no webhook secret set; event not verified"}
    else:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.stripe_webhook_secret,
            )
        except Exception as e:
            raise HTTPException(400, f"Webhook signature verification failed: {str(e)}")

    # Handle events
    if event["type"] == "payment_intent.succeeded":
        # You can update your DB here (mark as paid, store metadata, etc.)
        pass
    elif event["type"] == "payment_intent.payment_failed":
        pass

    return {"received": True}
