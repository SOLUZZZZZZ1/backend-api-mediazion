# stripe_routes.py — subscribe + webhook + confirm (marca trialing/active, envía correo de activación)
import os, json
from fastapi import APIRouter, HTTPException, Request
from db import pg_conn
import stripe

router = APIRouter(tags=["stripe"])

STRIPE_SECRET  = os.getenv("STRIPE_SECRET")
PRICE_ID       = os.getenv("STRIPE_PRICE_ID")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SUCCESS_URL    = os.getenv("SUB_SUCCESS_URL", "https://mediazion.eu/suscripcion/ok?session_id={CHECKOUT_SESSION_ID}")
CANCEL_URL     = os.getenv("SUB_CANCEL_URL",  "https://mediazion.eu/suscripcion/cancel")

if not STRIPE_SECRET:
    raise RuntimeError("STRIPE_SECRET no está definido")
stripe.api_key = STRIPE_SECRET

def _row_to_dict(cur, row):
    if row is None: return None
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}

def get_mediator(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                SELECT id, trial_used, subscription_status, status
                  FROM mediadores WHERE email=LOWER(%s)
            """, (email,))
            row = cur.fetchone()
            return _row_to_dict(cur, row)

def set_subscription(email: str, sub_id: str, subs_status: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                UPDATE mediadores
                   SET subscription_id=%s,
                       subscription_status=%s,
                       trial_used=CASE WHEN %s IN ('trialing','active') THEN TRUE ELSE trial_used END,
                       status='active'
                 WHERE email=LOWER(%s)
            """, (sub_id, subs_status, subs_status, email))
        cx.commit()

@router.post("/subscribe")
def subscribe(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    price = payload.get("priceId") or PRICE_ID
    if not email:  raise HTTPException(400, "Falta email")
    if not price:  raise HTTPException(500, "STRIPE_PRICE_ID no configurado")

    if not get_mediator(email):
        raise HTTPException(400, "Completa el alta antes de suscribirte.")

    try:
        # checkout sin cobrar aún (Stripe se encarga del trial si el price lo tiene)
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": price, "quantity": 1}],
            success_url=SUCCESS_LINK := SUCCESS_URL.replace("{CHECKOUT_SESSION_ID}", "{CHECKOUT_SESSION_ID}"),
            cancel_url=CANCEL_URL,
            allow_promotion_codes=True
        )
        return {"url": session["url"]}
    } except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {e.user_message or str(e)}")

@router.post("/stripe/webhook")
async def webhook(req: Request):
    payload = await req.body()
    try:
        event = (stripe.Webhook.construct_event(payload, req.headers.get("Stripe-Signature"), WEBHOOK_SECRET)
                 if WEBHOOK_SECRET else json.loads(payload))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    typ = event.get("type")
    obj = event.get("data", {}).get("object", {})

    try:
        if typ in ("customer.subscription.created", "customer.subscription.updated"):
            sub_id = obj.get("id")
            status = obj.get("status")  # trialing, active, past_due, canceled, etc.
            email = (obj.get("customer_email") or "")
            if not email and obj.get("customer"):
                try:
                    c = stripe.Customer.retrieve(obj["customer"])
                    email = (c.get("email") or "")
                except Exception:
                    email = ""
            if email and sub_id:
                subs = "active" if status == "active" else ("trialing" if status == "trialing" else status or "active")
                set_subscription(email.lower(), sub_id, subs)
        return {"received": True}
    except Exception as e:
        raise HTTPException(500, f"Webhook handling error: {e}")

@router.post("/stripe/confirm")
def confirm(payload: dict):
    """Confirma la primera suscripción al volver de /suscripcion/ok?session_id=... y envía correo de activación."""
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(400, "Falta session_id")
    try:
        sess = stripe.checkout.Session.retrieve(session_id, expand=["customer","subscription"])
        email = (sess.get("customer_details") or {}).get("email")
        if not email and sess.get("customer"):
            c = stripe.Customer.retrieve(sess["customer"])
            email = (c.get("email") or "")
        if not email:
            raise HTTPException(400, "No se encontró email en la sesión")
        sub = sess.get("subscription")
        sub_id = sub["id"] if isinstance(sub, dict) else sub
        s = stripe.Subscription.retrieve(sub_id)
        subs = "active" if s.get("status") == "active" else ("trialing" if s.get("status") == "trialing" else s.get("status") or "active")
        set_subscription(email.lower(), sub_id, subs)
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {e.user_message or str(e)}")

    # Correo de activación
    try:
        from contact_routes import _send_mail, MAIL_TO_DEFAULT
        html = f"""
        <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
          <p>¡Suscripción {subs}!</p>
          <p>Hemos actualizado tu suscripción en <strong>MEDIAZION</strong>.</p>
          <p>Id de suscripción: <code>{sub_id}</code></p>
          <p><a href="https://mediazion.eu/panel-mediador" style="display:inline-block;background:#0ea5e9;color:#fff;padding:10px 14px;border-radius:8px;text-decoration:none">Ir a mi panel</a></p>
        </div>
        """
        _send_mail(email, "Estado de suscripción · MEDIAZION", html, email)
        _send_mail(MAIL_TO_DEFAULT, f"[Suscripción {subs}] {email}", html, "MEDIAZION")
    except Exception:
        pass

    return {"ok": True, "email": email, "subscription_id": sub_id, "subscription_status": subs}
