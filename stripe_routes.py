# stripe_routes.py — Stripe Checkout + Webhook (PostgreSQL robusto)
import os, json
from fastapi import APIRouter, HTTPException, Request
import stripe
from db import pg_conn

router = APIRouter()

STRIPE_SECRET  = os.getenv("STRIPE_SECRET")
PRICE_ID       = os.getenv("STRIPE_PRICE_ID")
TRIAL_DAYS     = int(os.getenv("TRIAL_DAYS", "7"))
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SUCCESS_URL    = os.getenv("SUB_SUCCESS_URL", "https://mediazion.eu/suscripcion/ok?session_id={CHECKOUT_SESSION_ID}")
CANCEL_URL     = os.getenv("SUB_CANCEL_URL",  "https://mediazion.eu/suscripcion/cancel")

if not STRIPE_SECRET:
    raise RuntimeError("STRIPE_SECRET no está definido")
stripe.api_key = STRIPE_SECRET


def _row_to_dict(row, cols):
    """Convierte filas de psycopg2 (tupla) a dict"""
    if row is None:
        return None
    return {cols[i]: row[i] for i in range(len(cols))}


def get_mediator(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                SELECT id, trial_used, approved, status, phone, provincia, especialidad
                FROM mediadores WHERE email = LOWER(%s)
            """, (email,))
            row = cur.fetchone()
            if row:
                cols = [d[0] for d in cur.description]
                return _row_to_dict(row, cols)
            return None


@router.post("/subscribe")
def subscribe(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    price = payload.get("priceId") or PRICE_ID
    if not email:
        raise HTTPException(400, "Falta email")
    if not price:
        raise HTTPException(500, "STRIPE_PRICE_ID no configurado")

    row = get_mediator(email)
    if not row:
        raise HTTPException(400, "Completa tu alta de mediador antes de suscribirte.")

    # Validar datos mínimos
    missing = [k for k in ("phone", "provincia", "especialidad") if not (row.get(k) or "").strip()]
    if missing:
        raise HTTPException(400, f"Faltan datos en el alta: {', '.join(missing)}")

    trial_used = bool(row.get("trial_used"))
    allow_trial = (not trial_used) and TRIAL_DAYS > 0

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": price, "quantity": 1}],
            subscription_data={"trial_period_days": TRIAL_DAYS} if allow_trial else {},
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            metadata={"email": email},
        )
        return {"url": session["url"]}
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {e.user_message or str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Subscribe error: {e}")


@router.post("/stripe/webhook")
async def webhook(req: Request):
    payload = await req.body()
    try:
        if WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, req.headers.get("Stripe-Signature"), WEBHOOK_SECRET)
        else:
            event = json.loads(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    typ = event.get("type")
    obj = event.get("data", {}).get("object", {})

    if typ in ("customer.subscription.created", "customer.subscription.updated"):
        email = obj.get("customer_email")
        if not email and obj.get("customer"):
            cust = stripe.Customer.retrieve(obj["customer"])
            email = (cust.get("email") or "").lower()
        if email:
            with pg_conn() as cx:
                with cx.cursor() as cur:
                    cur.execute("""
                        UPDATE mediadores
                           SET subscription_id=%s, trial_used=TRUE, status='active'
                         WHERE email = LOWER(%s)
                    """, (obj.get("id"), email))
                    cx.commit()

    if typ == "customer.subscription.deleted":
        email = obj.get("customer_email")
        if not email and obj.get("customer"):
            cust = stripe.Customer.retrieve(obj["customer"])
            email = (cust.get("email") or "").lower()
        if email:
            with pg_conn() as cx:
                with cx.cursor() as cur:
                    cur.execute("UPDATE mediadores SET status='canceled' WHERE email=LOWER(%s)", (email,))
                    cx.commit()

    return {"received": True}
