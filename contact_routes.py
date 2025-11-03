import os, smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formataddr
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

contact_router = APIRouter()

class ContactIn(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

# --- Config (desde entorno) ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))  # 587 (TLS) por defecto
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
MAIL_FROM = os.getenv("MAIL_FROM", "info@mediazion.eu")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "MEDIAZION")
MAIL_TO_DEFAULT = os.getenv("MAIL_TO_DEFAULT", os.getenv("MAIL_TO", "info@mediazion.eu"))
MAIL_BCC = os.getenv("MAIL_BCC", "")  # opcional, coma-separado

def _send_mail(to_email: str, subject: str, html: str, to_name: str = ""):
    """
    Envío de correo con autodetección de modo seguro:
    - Si SMTP_PORT == 465 -> SSL implícito (smtplib.SMTP_SSL)
    - En cualquier otro puerto -> TLS explícito (STARTTLS)
    Lanza RuntimeError si faltan credenciales/host.
    """
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        raise RuntimeError("SMTP no configurado (SMTP_HOST/USER/PASS)")

    # Construir mensaje
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((MAIL_FROM_NAME, MAIL_FROM))
    msg["To"] = formataddr((to_name or to_email, to_email))

    # BCC (no va en cabecera; solo en envelope)
    bcc_list = [e.strip() for e in MAIL_BCC.split(",") if e.strip()] if MAIL_BCC else []
    rcpt = [to_email] + bcc_list

    context = ssl.create_default_context()

    # Conexión segura según puerto
    if SMTP_PORT == 465:
        # SSL implícito
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(MAIL_FROM, rcpt, msg.as_string())
    else:
        # STARTTLS
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(MAIL_FROM, rcpt, msg.as_string())

@contact_router.post("/contact")
def contact(data: ContactIn):
    """
    1) Acuse al solicitante
    2) Copia a info@ (MAIL_TO_DEFAULT)
    Si no hay SMTP configurado, devuelve {ok:true, sent:false} para no romper la UX.
    """
    # 1) Acuse al solicitante
    user_subject = "Hemos recibido tu solicitud · MEDIAZION"
    user_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Hola {data.name},</p>
      <p>Hemos recibido tu solicitud de contacto y te responderemos a la mayor brevedad.</p>
      <p><strong>Asunto:</strong> {data.subject}</p>
      <p><strong>Mensaje:</strong><br/>{data.message.replace(chr(10), '<br/>')}</p>
      <p style="margin-top:16px">Un saludo,<br/>Equipo MEDIAZION</p>
    </div>
    """

    # 2) Copia a info@
    info_subject = f"[Contacto] {data.subject} — {data.name} <{data.email}>"
    info_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Nuevo contacto desde la web:</p>
      <ul>
        <li><strong>Nombre:</strong> {data.name}</li>
        <li><strong>Email:</strong> {data.email}</li>
        <li><strong>Asunto:</strong> {data.subject}</li>
      </ul>
      <p><strong>Mensaje:</strong><br/>{data.message.replace(chr(10), '<br/>')}</p>
    </div>
    """

    try:
        _send_mail(data.email, user_subject, user_html, data.name)
        _send_mail(MAIL_TO_DEFAULT, info_subject, info_html, "MEDIAZION")
        sent = True
    except RuntimeError:
        # SMTP no configurado -> OK false pero no rompe
        sent = False
    except Exception as e:
        # Cualquier error real -> 500
        raise HTTPException(status_code=500, detail=f"Email error: {e}")

    return {"ok": True, "sent": sent}
