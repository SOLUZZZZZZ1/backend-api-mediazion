# stripe_routes.py — Stripe Checkout + Webhook usando PostgreSQL
import os, json
from fastapi import APIRouter, HTTPException, Request
import stripe
from db import pg_conn  # <-- usa tu helper PG: DATABASE_URL en Render

router = APIRouter()

STRIPE_SECRET = os.getenv("STRIPE_SECRET")
PRICE_ID      = os.getenv("STRIPE_PRICE_ID")
TRIAL_DAYS    = int(os.getenv("TRIAL_DAYS", "7"))
WEBHOOK_SECRET= os.getenv("STRIPE_WEBHOOK_SECRET")

# URLs de retorno (puedes mantener tus SUB_SUCCESS_URL / SUB_CANCEL_URL)
SUCCESS_URL = os.getenv("SUB_SUCCESS_URL", "https://mediazion.eu/suscripcion/ok?session_id={CHECKOUT_SESSION_ID}")
CANCEL_URL  = os.getenv("SUB_CANCEL_URL",  "https://mediazion.eu/suscripcion/cancel")

if not STRIPE_SECRET:
    raise RuntimeError("STRIPE_SECRET no está definido")
stripe.api_key = STRIPE_SECRET

def get_mediator(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id, trial_used FROM mediadores WHERE email = LOWER(%s)", (email,))
            return cur.fetchone()

def ensure_mediator(email: str):
    """Crea registro mínimo (aprobado/activo) si no existe, para no bloquear el flujo."""
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                INSERT INTO mediadores (name,email,approved,status,subscription_status,trial_used)
                VALUES (%s, LOWER(%s), TRUE, 'active', 'none', FALSE)
                ON CONFLICT (email) DO NOTHING
            """, (email.split("@")[0].title(), email))
            cx.commit()

def set_subscription(email: str, subscription_id: str, trial_used: bool = True):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                UPDATE mediadores
                   SET subscription_id=%s,
                       trial_used=%s,
                       status='active'
                 WHERE email = LOWER(%s)
            """, (subscription_id, trial_used, email))
            cx.commit()

@router.post("/subscribe")
def subscribe(payload: dict):
    """
    Crea una sesión de Checkout para suscripción:
      - Si el mediador no existe → lo crea aprobado/activo (no bloquea).
      - Si no ha usado trial y TRIAL_DAYS>0 → aplica trial; si ya lo usó → sin trial (pago directo).
    """
    email = (payload.get("email") or "").strip().lower()
    price = payload.get("priceId") or PRICE_ID
    if not email:
        raise HTTPException(400, "Falta email")
    if not price:
        raise HTTPException(500, "STRIPE_PRICE_ID no configurado")

    row = get_mediator(email)
    if not row:
        ensure_mediator(email)
        trial_used = False
    else:
        # row es un dict-like gracias a RealDictCursor
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
        raise HTTPException(400, f"Stripe error: {str(e)}")

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

    # Alta/actualización de suscripción: marca trial_used y guarda subscription_id
    if typ in ("customer.subscription.created", "customer.subscription.updated"):
        email = obj.get("customer_email")
        if not email and obj.get("customer"):
            cust = stripe.Customer.retrieve(obj["customer"])
            email = (cust.get("email") or "").lower()
        if email:
            set_subscription(email, obj.get("id"), True)

    # Baja: marcar status cancelado (opcional)
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
