from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os, smtplib, ssl
from email.message import EmailMessage

app = FastAPI(title="MEDIAZION Backend (email)", version="1.0.0")

ALLOWED = os.getenv("ALLOWED_ORIGINS", "*")
allow_origins = [o.strip() for o in ALLOWED.split(",")] if ALLOWED and ALLOWED != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend"}

def send_email_smtp(subject: str, body: str, mail_from: str, mail_to: str):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    use_tls = os.getenv("SMTP_TLS", "false").lower() in ("1","true","yes")

    if not host or not user or not password or not mail_to:
        raise RuntimeError("SMTP not configured (missing host/user/pass or MAIL_TO).")

    msg = EmailMessage()
    msg["From"] = mail_from or user
    msg["To"] = mail_to
    msg["Subject"] = subject
    msg.set_content(body)

    if port == 465 and not use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.send_message(msg)

@app.post("/contact")
async def contact(req: Request):
    data = await req.json()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    subject = str(data.get("subject", "")).strip() or "Mensaje de contacto"
    message = str(data.get("message", "")).strip()

    if len(name) < 2 or "@" not in email or len(message) < 5:
        raise HTTPException(status_code=400, detail="Datos insuficientes.")

    mail_from = os.getenv("MAIL_FROM") or os.getenv("SMTP_USER")
    mail_to = os.getenv("MAIL_TO") or os.getenv("SMTP_USER")

    body = f"""Nuevo mensaje desde MEDIAZION
----------------------------------------
Nombre: {name}
Email:  {email}
Asunto: {subject}

Mensaje:
{message}
"""

    try:
        send_email_smtp(subject=f"[MEDIAZION] {subject}", body=body, mail_from=mail_from, mail_to=mail_to)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
