# Mediazion — Backend Fixes (PostgreSQL)

Incluye:
- `contact_routes.py` con **SSL (465)** y **TLS (587)** automático.
- `db.py` para **PostgreSQL** con `pg_conn()` (psycopg v3 o psycopg2).
- `app.py` con **Stripe habilitado** (router activado) y ruta `/health`.
- `db_routes.py` con `/db/health` para comprobar la conexión a BD.
- Requisitos en `requirements.txt`.

## Variables de entorno mínimas

```
ADMIN_TOKEN=...
ALLOWED_ORIGINS=https://mediazion.eu,https://www.mediazion.eu,https://TU_FRONT.vercel.app

# PostgreSQL
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# SMTP
SMTP_HOST=authsmtp.securemail.pro
SMTP_USER=info@mediazion.eu
SMTP_PASS=********
SMTP_PORT=465          # o 587
MAIL_FROM=info@mediazion.eu
MAIL_FROM_NAME=MEDIAZION
MAIL_TO_DEFAULT=info@mediazion.eu
MAIL_BCC=archivo@mediazion.eu

# Stripe
STRIPE_SECRET=sk_live_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
SUB_SUCCESS_URL=https://mediazion.eu/suscripcion/ok?session_id={CHECKOUT_SESSION_ID}
SUB_CANCEL_URL=https://mediazion.eu/suscripcion/cancel
TRIAL_DAYS=7

# OpenAI (si usas IA)
OPENAI_API_KEY=...
```

## Arranque local

```bash
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## Comprobaciones

- `/health` → debe devolver `{"ok": true}`
- `/db/health` → `{"ok": true, "db": true}` si la DB responde.
- `POST /contact` con JSON de prueba → debe enviar emails (465 SSL o 587 TLS).
- `POST /subscribe` → debe devolver `{"url": "https://checkout.stripe.com/..."}` con STRIPE_* reales.
- `POST /stripe/webhook` → configura endpoint en Stripe dashboard con el secreto correspondiente.