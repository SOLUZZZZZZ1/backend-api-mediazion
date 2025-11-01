# stripe_routes.py — MEDIAZION · Stripe (suscripción y webhook)
import os, json, sqlite3
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
import stripe

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_SECRET")
PRICE_ID_ENV = os.getenv("STRIPE_PRICE_ID")
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "7"))
DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def _cx():
    cx = sqlite3.connect(DB_PATH)
    cx.row_factory = sqlite3.Row
    return cx

def _get_mediador(email: str):
    with _cx() as cx:
        cur = cx.execute("SELECT * FROM mediadores WHERE lower(email)=lower(?)", (email,))
        row = cur.fetchone()
        return dict(row) if row else None

def _mark_trial_used(email: str):
    with _cx() as cx:
        cx.execute(
            "UPDATE mediadores SET trial_used=1, trial_start=? WHERE lower(email)=lower(?)",
            (datetime.utcnow().isoformat(), email),
        )
        cx.commit()

def _save_subscription(email: str, sub_id: str):
    with _cx() as cx:
        cx.execute(
            "UPDATE mediadores SET subscription_id=?, status='active' WHERE lower(email)=lower(?)",
            (sub_id, email),
        )
        cx.commit()

@router.post("/subscribe")
async def subscribe(payload: dict):
    """Crea una sesión de Stripe Checkout con o sin periodo de prueba."""
    email = (payload.get("email") or "").strip().lower()
    price_id = payload.get("priceId") or PRICE_ID_ENV
    if not email:
        raise HTTPException(400, "Falta email")
    if not price_id:
        raise HTTPException(400, "Falta STRIPE_PRICE_ID en entorno")

    m = _get_mediador(email)
    if not m:
        raise HTTPException(400, "Antes debes completar el alta de mediador.")

    apply_trial = (m.get("trial_used", 0) == 0) and TRIAL_DAYS > 0
    args = dict(
        mode="subscription",
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=os.getenv(
            "SUCCESS_URL",
            "https://mediazion.eu/success?session_id={CHECKOUT_SESSION_ID}",
        ),
        cancel_url=os.getenv("CANCEL_URL", "https://mediazion.eu/cancel"),
        metadata={"email": email},
    )
    if apply_trial:
        args["subscription_data"] = {"trial_period_days": TRIAL_DAYS}

    try:
        session = stripe.checkout.Session.create(**args)
        return {"url": session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {str(e)}")

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """Webhook de Stripe: marca trial_used y estado de subscripción."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = (
            stripe.Webhook.construct_event(payload, sig, secret)
            if secret
            else json.loads(payload)
        )
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    t = event.get("type")
    data = event.get("data", {}).get("object", {})

    if t in ("customer.subscription.created", "customer.subscription.updated"):
        email = data.get("customer_email") or (data.get("customer_details") or {}).get("email")
        sub_id = data.get("id")
        if email:
            _save_subscription(email, sub_id)
            _mark_trial_used(email)

    if t == "customer.subscription.deleted":
        email = data.get("customer_email") or (data.get("customer_details") or {}).get("email")
        if email:
            with _cx() as cx:
                cx.execute(
                    "UPDATE mediadores SET status='canceled' WHERE lower(email)=lower(?)",
                    (email,),
                )
                cx.commit()

    return {"received": True}
