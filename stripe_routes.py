# stripe_routes.py — Subscribe + Webhook + Confirm (envío de correo de activación)
import os, json
from fastapi import APIRouter, HTTPException, Request
from db import pg_conn
import stripe

router = APIRouter(tags=["stripe"])

# --- Config ---
STRIPE_SECRET  = os.getenv("STRIPE_SECRET")
PRICE_ID       = os.getenv("STRIPE_PRICE_ID")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
SUCCESS_URL    = os.getenv("SUB_SUCCESS_URL", "https://mediazion.eu/suscripcion/ok?session_id={CHECKOUT_SESSION_ID}")
CANCEL_URL     = os.getenv("SUB_CANCEL_URL",  "https://mediazion.eu/suscripcion/cancel")

if not STRIPE_SECRET:
    raise RuntimeError("STRIPE_SECRET no está definido")
stripe.api_key = STRIPE_SECRET

# --- Helpers BD ---
def _row_to_dict(cur, row):
    if not row: return None
    cols = [d[0] for d in cur.description]
    return {cols[i]: row[i] for i in range(len(cols))}

def get_mediator(email: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                SELECT id, subscription_id, subscription_status, trial_used
                  FROM mediadores WHERE email = LOWER(%s)
            """, (email,))
            return _row_to_dict(cur, cur.fetchone())

def set_subscription(email: str, sub_id: str, subs_status: str):
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                UPDATE mediadores
                   SET subscription_id=%s,
                       subscription_status=%s,
                       trial_used = CASE WHEN %s IN ('trialing','active') THEN TRUE ELSE trial_used END,
                       status='active'
                 WHERE email=LOWER(%s)
            """, (sub_id, subs_status, subs_status, email))
        cx.commit()

# --- Subscribe: llamado por el botón "Activar plan PRO" ---
@router.post("/subscribe")
def subscribe(payload: dict):
    email = (payload.get("email") or "").strip().lower()
    price = payload.get("priceId") or PRICE_ID
    if not email:
        raise HTTPException(400, "Falta email")
    if not price:
        raise HTTPException(500, "STRIPE_PRICE_ID no configurado")

    if not get_mediator(email):
        raise HTTPException(400, "Completa el alta antes de suscribirte.")

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": price, "quantity": 1}],
            allow_promotion_codes=True,
            success_url=SUCCESS_URL,  # incluye {CHECKOUT_SESSION_ID} en env
            cancel_url=CANCEL_URL,
        )
        return {"url": session["url"]}
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {e.user_message or str(e)}")

# --- Webhook: maneja checkout.session.completed y customer.subscription.* ---
@router.post("/stripe/webhook")
async def webhook(req: Request):
    payload = await req.body()
    try:
        event = (stripe.Webhook.construct_event(payload, req.headers.get("Stripe-Signature"), WEBHOOK_SECRET)
                 if WEBHOOK_SECRET else json.loads(payload))
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    typ = event.get("type")
    obj = event.get("data", {}).get("object", {})

    # 1) checkout.session.completed → asociamos email y subscription
    if typ == "checkout.session.completed":
        try:
            email = (obj.get("customer_details") or {}).get("email") or ""
            if not email and obj.get("customer"):
                c = stripe.Customer.retrieve(obj["customer"])
                email = (c.get("email") or "")
            sub = obj.get("subscription")
            sub_id = sub["id"] if isinstance(sub, dict) else sub
            status = "active"  # Stripe puede marcar trial en el price; confirmaremos abajo si es trialing
            try:
                s = stripe.Subscription.retrieve(sub_id)
                status = "trialing" if s.get("status") == "trialing" else ("active" if s.get("status") == "active" else s.get("status") or "active")
            except Exception:
                pass
            if email and sub_id:
                set_subscription(email.lower(), sub_id, status)
                _send_activation_email(email, status, sub_id)
        except Exception as e:
            # no romper el webhook; loguear
            print("Error en checkout.session.completed:", e)

    # 2) customer.subscription.created / updated / deleted
    if typ in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        try:
            sub_id = obj.get("id")
            status_raw = obj.get("status")  # trialing | active | past_due | canceled | ...
            status = "trialing" if status_raw == "trialing" else ("active" if status_raw == "active" else status_raw or "active")
            email = obj.get("customer_email") or ""
            if not email and obj.get("customer"):
                c = stripe.Customer.retrieve(obj["customer"])
                email = (c.get("email") or "")
            if email and sub_id:
                set_subscription(email.lower(), sub_id, status)
                if status in ("trialing","active"):
                    _send_activation_email(email, status, sub_id)
        except Exception as e:
            print("Error en customer.subscription.*:", e)

    return {"received": True}

# --- Confirm: llamado desde /suscripcion/ok cuando hay session_id (por si el webhook tarda) ---
@router.post("/stripe/confirm")
def confirm(payload: dict):
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(400, "Falta session_id")

    try:
        sess = stripe.checkout.Session.retrieve(session_id, expand=["customer","subscription"])
        email = (sess.get("customer_details") or {}).get("email") or ""
        if not email and sess.get("customer"):
            c = stripe.Customer.retrieve(sess["customer"])
            email = (c.get("email") or "")
        sub = sess.get("subscription")
        sub_id = sub["id"] if isinstance(sub, dict) else sub
        s = stripe.Subscription.retrieve(sub_id)
        status = "trialing" if s.get("status") == "trialing" else ("active" if s.get("status") == "active" else s.get("status") or "active")
        if email and sub_id:
            set_subscription(email.lower(), sub_id, status)
            _send_activation_email(email, status, sub_id)
    except stripe.error.StripeError as e:
        raise HTTPException(400, f"Stripe error: {e.user_message or str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Confirm error: {e}")

    return {"ok": True, "email": email, "subscription_id": sub_id, "subscription_status": status}

# --- Email de activación ---
def _send_activation_email(email: str, status: str, sub_id: str):
    try:
        from contact_routes import _send_mail, MAIL_TO_DEFAULT
        html = f"""
        <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
          <p>¡Suscripción {status}!</p>
          <p>Tu suscripción en <strong>MEDIAZION</strong> está ahora <strong>{status.upper()}</strong>.</p>
          <p>ID de suscripción: <code>{sub_id}</code></p>
          <p><a href="https://mediazion.eu/panel-mediador"
                style="display:inline-block;background:#0ea5e9;color:#fff;padding:10px 14px;border-radius:10px;text-decoration:none">
                Ir a mi panel
             </a></p>
        </div>
        """
        _send_mail(email, "¡Suscripción activada · MEDIAZION!", html, email)
        _send_mail(MAIL_TO_DEFAULT, f"[Suscripción {status}] {email}", html, "MEDIAZION")
    except Exception as e:
        print("Error enviando correo de activación:", e)
