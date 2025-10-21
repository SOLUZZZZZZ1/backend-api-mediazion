MEDIAZION · Backend mínimo para Render (app.py)

Start Command en Render:
  uvicorn app:app --host 0.0.0.0 --port 10000

Build Command:
  pip install -r requirements.txt

Prueba:
  /health  → ok
  POST /contact  → eco JSON
