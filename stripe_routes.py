# stripe_routes.py — Checkout + Webhook (MEDIAZION)
import os, json, sqlite3
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
import stripe

router = APIRouter()

# ENV obligatorios
STRIPE_SECRET = os.getenv("STRIPE_SECRET", "")        # sk_...
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")    # price_...
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")  # whsec_...
TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "7"))        # días de prueba (0 = sin trial)
DB_PATH = os.getenv("DB_PATH", "mediazion.db")

if STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET

def _cx():
    cx = sqlite3.connect(DB_PATH); cx.row_factory = sqlite3.Row; return cx

def _get_mediador(email: str):
    with _cx() as cx:
        cur = cx.execute("SELECT * FROM mediadores WHERE lower(email)=lower(?)", (email.lower(),))
        row = cur.fetchone()
        return dict(row) if row else None

def _mark_trial_used(email: str):
    with _cx() as cx:
        cx.execute("UPDATE mediadores SET trial_used=1, trial_start=? WHERE lower(email)=lower(?)",
                   (datetime.utcnow().isoformat(), email.lower()))
        cx.commit()

def _save_subscription(email: str, sub_id: str):
    with _cx() as cx:
        cx.execute("UPDATE mediadores SET subscription_id=?, status='active' WHERE lower(email)=lower(?)",
                   (sub_id, email.lower()))
        cx.commit()

@router.post("/subscribe")
async def subscribe(payload: dict):
    """
    Crea sesión de Checkout de Stripe para suscripción.
    - Si el mediador no existe: 400 (primero debe hacer el alta).
    - Si no hay STRIPE_SECRET/PRICE_ID: 500.
    - Si no ha usado trial y TRIAL_DAYS>0: crea trial; si ya lo usó, sin trial.
    """
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Falta email")
    if not STRIPE_SECRET or not STRIPE_PRICE_ID:
        raise HTTPException(500, "Stripe no está configurado (STRIPE_SECRET / STRIPE_PRICE_ID)")

    m = _get_mediador(email)
    if not m:
        raise HTTPException(400, "Antes debes completar el alta de mediador.")

    apply_trial = (m.get("trial_used", 0) == 0) and TRIAL_DAYS > 0

    kwargs = dict(
        mode="subscription",
        customer_email=email,
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=os.getenv("SUCCESS_URL", "https://mediazion.eu/success?session_id={CHECKOUT_SESSION_ID}"),
        cancel_url=os.getenv("CANCEL_URL", "https://mediazion.eu/cancel"),
        metadata={"email": email}
    )
    if apply_trial:
        kwargs["subscription_data"] = {"trial_period_days": TRIAL_DAYS}

    try:
        session = stripe.checkout.Session.create(**kwargs)
        return {"url": session.url}
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {str(e)}")

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = (
            stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
            if STRIPE_WEBHOOK_SECRET else
            json.loads(payload)
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
                cx.execute("UPDATE mediadores SET status='canceled' WHERE lower(email)=lower(?)", (email.lower(),))
                cx.commit()

    return {"received": True}
