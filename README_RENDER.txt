MEDIAZION · Backend email (app.py + Nominalia SMTP)

Start Command (Render):
  uvicorn app:app --host 0.0.0.0 --port 10000

Environment Variables (Render):
  ALLOWED_ORIGINS=https://mediazion.eu,https://<tu-frontend>.vercel.app
  SMTP_HOST=authsmtp.securemail.pro
  SMTP_PORT=465
  SMTP_USER=info@mediazion.eu
  SMTP_PASS=<tu_contraseña>
  SMTP_TLS=false
  MAIL_FROM=info@mediazion.eu
  MAIL_TO=admin@mediazion.eu

Endpoints:
  GET /health     -> ok
  POST /contact   -> envía correo usando SMTP (Nominalia)
