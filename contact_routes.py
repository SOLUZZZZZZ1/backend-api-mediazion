import os, smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formataddr
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

# --- Soporte opcional para settings (config.py) ---
try:
    from config import settings  # pydantic_settings BaseSettings
except Exception:
    settings = None  # si no hay config.py, seguimos con os.environ

contact_router = APIRouter()

class ContactIn(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str
    accept: bool = False  # consentimiento RGPD

def _get(name: str, default=None):
    """
    Prioriza config.py (si existe) y después variables de entorno.
    Mapea nombres comunes: SMTP_* y mail_* definidos en config.py.
    """
    if settings is not None:
        # mapear claves típicas
        mapping = {
            "SMTP_HOST": getattr(settings, "smtp_host", None),
            "SMTP_PORT": getattr(settings, "smtp_port", None),
            "SMTP_USER": getattr(settings, "smtp_user", None),
            "SMTP_PASS": getattr(settings, "smtp_pass", None),
            "SMTP_TLS":  getattr(settings, "smtp_tls",  None),
            "MAIL_FROM": getattr(settings, "mail_from", None),
            "MAIL_TO_DEFAULT": getattr(settings, "mail_to", None),
        }
        if name in mapping and mapping[name] is not None:
            return mapping[name]
    # entorno
    val = os.getenv(name)
    return val if val is not None else default

SMTP_HOST = _get("SMTP_HOST", "")
SMTP_PORT = int(_get("SMTP_PORT", "587"))  # 465 = SSL implícito; 587 = STARTTLS
SMTP_USER = _get("SMTP_USER", "")
SMTP_PASS = _get("SMTP_PASS", "")
SMTP_TLS  = str(_get("SMTP_TLS", "true")).strip().lower() in ("1","true","yes","on")

MAIL_FROM       = _get("MAIL_FROM", "info@mediazion.eu")
MAIL_FROM_NAME  = _get("MAIL_FROM_NAME", "MEDIAZION")
MAIL_TO_DEFAULT = _get("MAIL_TO_DEFAULT", "info@mediazion.eu")
MAIL_BCC        = os.getenv("MAIL_BCC", "")  # solo desde entorno si se usa

def _send_mail(to_email: str, subject: str, html: str, to_name: str = ""):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        raise RuntimeError("SMTP no configurado (SMTP_HOST/USER/PASS)")

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((MAIL_FROM_NAME, MAIL_FROM))
    msg["To"] = formataddr((to_name or to_email, to_email))

    # BCC (no se añade en cabecera)
    bcc_list = [e.strip() for e in MAIL_BCC.split(",") if e.strip()] if MAIL_BCC else []
    rcpt = [to_email] + bcc_list

    context = ssl.create_default_context()

    # Reglas:
    #  - Puerto 465 => SSL implícito (SMTP_SSL), ignoramos STARTTLS
    #  - Cualquier otro puerto => STARTTLS si SMTP_TLS=true, si no, plano (no recomendado)
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(MAIL_FROM, rcpt, msg.as_string())
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_TLS:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(MAIL_FROM, rcpt, msg.as_string())

@contact_router.post("/contact")
def contact(data: ContactIn):
    if not data.accept:
        raise HTTPException(400, "Debes aceptar la política de privacidad.")

    user_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Hola {data.name},</p>
      <p>Hemos recibido tu solicitud y te responderemos pronto.</p>
      <p><strong>Asunto:</strong> {data.subject}</p>
      <p><strong>Mensaje:</strong><br/>{data.message}</p>
      <p>Equipo MEDIAZION</p>
    </div>
    """
    info_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Nuevo contacto desde la web:</p>
      <ul>
        <li><strong>Nombre:</strong> {data.name}</li>
        <li><strong>Email:</strong> {data.email}</li>
        <li><strong>Asunto:</strong> {data.subject}</li>
      </ul>
      <p>{data.message}</p>
    </div>
    """

    # Envío con “soft-fail”: nunca tiramos 500 por el correo
    mail_user_sent = False
    mail_info_sent = False
    mail_error = ""

    try:
        _send_mail(data.email, "Hemos recibido tu solicitud · MEDIAZION", user_html, data.name)
        mail_user_sent = True
        _send_mail(MAIL_TO_DEFAULT, f"[Contacto] {data.subject} — {data.name} <{data.email}>", info_html, "MEDIAZION")
        mail_info_sent = True
    except RuntimeError:
        # SMTP no configurado: devolvemos ok pero marcamos sent=False
        mail_error = "SMTP no configurado"
    except Exception as e:
        # Error de transporte (p.ej. 'Connection unexpectedly closed')
        mail_error = str(e)

    return {"ok": True, "sent_user": mail_user_sent, "sent_info": mail_info_sent, "mail_error": mail_error}
