# MEDIAZION · Stripe (Tarjeta)

Este paquete añade **Stripe** al backend FastAPI:
- `POST /payments/create-intent` → Crea un PaymentIntent y devuelve `clientSecret`
- `POST /payments/webhook` → Recibe notificaciones de Stripe (pago OK / fallo)

## 1) Configurar Stripe
1. Crea/usa tu cuenta de Stripe y habilita pagos con tarjeta.
2. En **Developers → API keys**, copia:
   - `STRIPE_SECRET_KEY` (sk_test_... / sk_live_...)
   - `STRIPE_PUBLIC_KEY` (pk_test_... / pk_live_...)
3. En **Developers → Webhooks**, crea un endpoint (ej: `https://TU_BACKEND/payments/webhook`)
   - Selecciona eventos: `payment_intent.succeeded`, `payment_intent.payment_failed`
   - Copia `STRIPE_WEBHOOK_SECRET` (whsec_...)
4. Opcional: en **Settings → Branding**, configura el nombre público y el **statement descriptor** (máx 22 chars).
   También puedes fijarlo desde `.env` con `STATEMENT_DESCRIPTOR=MEDIAZION`.

## 2) Variables de entorno (.env)
Crea `.env` desde `.env.example` y rellena:
```
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STATEMENT_DESCRIPTOR=MEDIAZION
ALLOWED_ORIGINS=https://mediazion-frontend-xxxxx.vercel.app,https://mediazion.eu
```

## 3) Instalar y ejecutar
```
pip install -r requirements.txt
uvicorn app.main:app --reload
```
- `GET /health` → debe responder `{"ok": true, ...}`
- `POST /payments/create-intent` con `{"amount_eur": 150, "description":"Expediente #123"}` → devuelve `{ clientSecret }`

## 4) Frontend (Stripe Elements)
En tu frontend añade Stripe Elements y llama al backend para obtener el `clientSecret`:

```js
import { loadStripe } from '@stripe/stripe-js';
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js';

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLIC_KEY); // pk_test_...

async function createIntent(amountEUR, description, email){
  const res = await fetch('https://TU_BACKEND/payments/create-intent', {
    method: 'POST',
    headers: { 'Content-Type':'application/json' },
    body: JSON.stringify({ amount_eur: amountEUR, description, customer_email: email })
  });
  return res.json(); // { clientSecret }
}
```

Luego confirma el pago:
```js
const { clientSecret } = await createIntent(150, 'Expediente #123', 'cliente@email.com');
const stripe = useStripe();
const elements = useElements();
const result = await stripe.confirmCardPayment(clientSecret, {
  payment_method: { card: elements.getElement(CardElement) }
});
if (result.error) {
  // mostrar error
} else if (result.paymentIntent && result.paymentIntent.status === 'succeeded') {
  // éxito! mostrar confirmación
}
```

## 5) Webhook
Asegúrate de exponer `POST /payments/webhook` en internet (producción) y registrar ese endpoint en Stripe.  
- En local, usa `stripe cli` o `ngrok` para reenviar eventos.

## 6) ¿Pago a “un nombre” y cuenta concreta?
- El nombre que ve el cliente en el extracto lo define `STATEMENT_DESCRIPTOR` (máx 22 chars), y la **cuenta de Stripe receptora** del dinero es la que uses en `STRIPE_SECRET_KEY`.
- Si en el futuro necesitáis pagar a **varias cuentas** (p.ej., mediadores), entonces hay que activar **Stripe Connect** y usar `Transfers` o `Direct charges`. Podemos preparar esa versión cuando quieras.
