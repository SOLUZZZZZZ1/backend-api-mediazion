# stripe_routes.py — /stripe/subscribe + /stripe/confirm + /stripe/webhook
import os
from fastapi import APIRouter, HTTPException, Request
from db import pg_conn
import stripe

router = APIRouter()  # we'll register with prefix="" and put /stripe/* in paths

STRIPE_SECRET  = os.getenv("STRIPE_SECRET")
PRICE_ID       = os.getenv("STRIPE_PRICE_ID")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SUCCESS_URL    = os.getenv("SUB_SUCCESS_URL", "https://mediazion.eu/suscripcion/ok?session_id={CHECKOUT_SESSION_ID}")
CANCEL_URL     = os.getenv("SUB_CANCEL_URL", "https://mediazion.eu/suscripcion/cancel")

if not STRIPE_SECRET:
    raise RuntimeError("STRIPE_SECRET not configured")  # Explicit for envs without secret

# Stripe init
stripe.api_key = STRIPE_SECRET


def _row_to_dict(cur, row):
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}


def _get_mediator(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, subscription_id, subscription_status, trial_used
                FROM mediadores
                WHERE email = LOWER(%s)
                """,
                (email,),
            )
            return _row_to_dict(cur, cur.fetchone())


def _set_subscription(email: str, sub_id: str, subs_status: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(
                """
                UPDATE mediadores
                   SET subscription_id=%s,
                       subscription_status=%s,
                       trial_used = CASE WHEN %s IN ('trialing','active') THEN TRUE ELSE trial_used END,
                       status='active'
                 WHERE email = LOWER(%s)
                """,
                (sub_id, subs_status, subs_status, email),
            )
        cx.commit()


def _send_activation(email: str, sub_id: str, subs_status: str):
    try:
        from contact_routes import _send_mail, MAIL_TO_DEFAULT
        html = f"""
        <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
          <p>¡Suscripción {subs_status}!</p>
          <p>Tu suscripción en <strong>MEDIAZION</strong> está ahora <strong>{subs_status.upper()}</strong>.</p>
          <p>ID de suscripción: <code>{sub_id}</code></p>
          <p>
            <a href="https://mediazion.eu/personal" style="display:inline-block;background:#0a7cff;color:#fff;padding:10px 14px;border-radius:12px;text-decoration:none">
              Ir a mi panel
            </a>
          </p>
        </div>
        """
        _send_mail(email, "Estado de tu suscripción · MEDIAZION", html, email)
        _send_mail(MAIL_TO_DEFAULT, f"[Suscripción {subs_status}] {email}", html, "MEDIAZION")
    except Exception:
        # soft-fail, no 500
        pass


@router.post("/stripe/subscribe")
def subscribe(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "Falta email")
    if not PRICE_ID:
        raise HTTPException(500, "Falta STRIPE_PRICE_ID en variables de entorno")

    if not _get_mediator(email):
        raise HTTPException(400, "Completa el alta antes de suscribirte.")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": PRICE_ID, "quantity": 1}],
            success_url=SUCCESS_URL,  # must contain {CHECKOUT_SESSION_ID}
            cancel_url=CANCEL_URL,
            allow_promotion_codes=True,
        )
        return {"url": session["url"]}
    except stripe.error.StripeError as e:
        # user_message solo aparece en algunos errores
        detail = getattr(e, "user_message", None) or str(e)
        raise HTTPException(400, f"Stripe error: {detail}")


@router.post("/stripe/confirm")
def confirm(payload: dict):
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(400, "Falta session_id")

    try:
        sess = stripe.checkout.Session.retrieve(session_id, expand=["customer", "subscription"])
        email = (sess.get("customer_details") or {}).get("email")
        if not email and sess.get("customer"):
            cust = stripe.Customer.retrieve(sess["customer"])
            email = cust.get("email")

        if not email:
            raise HTTPException(400, "No se encontró email en la sesión")

        sub = sess.get("subscription")
        sub_id = sub["id"] if isinstance(sub, dict) else sub
        s = stripe.Subscription.retrieve(sub_id)
        status = s.get("status") or "active"
        subs = "active" if status == "active" else ("trialing" if status == "trialing" else status)

        _set_subscription(email.lower(), sub_id, subs)
        _send_activation(email, sub_id, subs)
        return {"ok": True, "email": email, "subscription_id": sub_id, "subscription_status": subs}
    except stripe.error.StripeError as e:
        detail = getattr(e, "user_message", None) or str(e)
        raise HTTPException(400, f"Stripe error: {detail}")


@router.post("/stripe/webhook")  # Webhook (configúralo en Stripe con /api/stripe/webhook)
async def webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    typ = event.get("type")
    obj = event.get("data", {}).get("object", {})

    try:
        if typ in ("customer.subscription.created", "customer.subscription.updated"):
            email = (obj.get("customer_email") or "")
            if not email and obj.get("customer"):
                c = stripe.Customer.retrieve(obj["customer"])
                email = (c.get("email") or "")
            sub_id = obj.get("id")
            status = obj.get("status") or "active"
            subs = "active" if status == "active" else ("trialing" if status == "trialing" else status)
            if email and sub_id:
                _set_subscription(email.lower(), sub_id, subs)
                _send_activation(email, sub_id, subs)
        elif typ == "customer.subscription.deleted":
            email = (obj.get("customer_email") or "")
            if not email and obj.get("customer"):
                c = stripe.Customer.retrieve(obj["customer"])
                email = (c.get("email") or "")
            if email:
                _set_subscription(email.lower(), obj.get("id") or "", "canceled")
    except Exception:
        # No romper el webhook si hay fallos suaves
        pass

    return {"received": True}
