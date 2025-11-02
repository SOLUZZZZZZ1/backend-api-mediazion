# MEDIAZION — Backend PostgreSQL (Render)

Archivos incluidos:
- db.py
- utils_pg.py
- mediadores_routes.py
- app.py

1) Copia estos archivos a `C:\MEDIAZION\backend-api` (sustituyendo los existentes donde aplique).
2) En Render → backend, define `DATABASE_URL` con TU External Database URL de Postgres (añade `?sslmode=require` si no está en la URL).
3) Añade también: `ADMIN_TOKEN`, `ALLOWED_ORIGINS`, `STRIPE_SECRET`, `STRIPE_PRICE_ID`, `TRIAL_DAYS`, `SMTP_*` si usas correo.
4) Asegúrate de tener `psycopg2-binary` en requirements.txt y haz **Deploy** con **Clear build cache**.
5) Prueba:
   - `GET /health`
   - `POST /mediadores/register`
   - `GET /mediadores/public`
