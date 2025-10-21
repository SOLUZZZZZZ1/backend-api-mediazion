MEDIAZION · Frontend Contacto → Render API (v2)

1) Copia estos archivos en tu frontend:
   - src/lib/api.js
   - src/pages/Contacto.jsx
   - .env.local.example (opcional)

2) Crea `.env.local` en la raíz del frontend con:
   VITE_API_BASE=https://backend-api-mediazion-1.onrender.com

3) En Vercel → Project → Settings → Environment Variables:
   VITE_API_BASE = https://backend-api-mediazion-1.onrender.com
   (Production + Preview)

4) Build y despliega:
   npm run build
   vercel --prod --yes

5) Prueba en /contacto. Si sale “Enviado”, revisa tu buzón admin@mediazion.eu.
