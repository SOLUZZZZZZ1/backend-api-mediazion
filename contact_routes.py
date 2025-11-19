import os, smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formataddr
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Literal

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


# --------- CLASIFICACIÓN BÁSICA (versión 1) ---------
ContactType = Literal["mediador", "cliente", "otro"]

def classify_contact(body: ContactIn) -> tuple[ContactType, float]:
    """
    Versión 1: clasificación sencilla por palabras clave.
    Más adelante se puede sustituir por IA OpenAI sin tocar el resto.
    """
    text = f"{body.subject} {body.message}".lower()

    score_mediador = 0
    score_cliente = 0

    # Indicadores de mediador
    for kw in ["mediador", "mediación", "panel", "alta", "suscripción", "pro", "herramientas", "ia"]:
        if kw in text:
            score_mediador += 1

    # Indicadores de cliente
    for kw in ["conflicto", "problema", "disputa", "mi pareja", "mi ex", "vecino", "empresa", "trabajo", "laboral"]:
        if kw in text:
            score_cliente += 1

    # Si no hay casi contexto, lo marcamos como "otro"
    if score_mediador == 0 and score_cliente == 0:
        return "otro", 0.4

    if score_mediador > score_cliente:
        return "mediador", 0.7 + 0.05 * score_mediador
    if score_cliente > score_mediador:
        return "cliente", 0.7 + 0.05 * score_cliente

    # Empate raro → lo dejamos como "otro"
    return "otro", 0.5


def build_auto_reply(body: ContactIn, kind: ContactType) -> str:
    name = body.name.strip() or "Hola"

    if kind == "mediador":
        return f"""Hola {name},

¡Gracias por tu mensaje y por tu interés en Mediazion! 😊

Mediazion es un panel profesional para mediadores que incluye:

· IA Profesional (con visión para leer documentos e imágenes)
· IA Legal
· Generación de actas
· Gestión de casos y agenda
· Recursos y herramientas para tu práctica diaria
· Perfil profesional y visibilidad en nuestro directorio

Puedes darte de alta de forma gratuita aquí:
https://mediazion.eu/mediadores

Tras el alta, tendrás un periodo de prueba PRO en el que podrás usar todas las funciones del panel.
Si lo deseas, podemos agendar también una llamada breve para enseñarte el panel en directo.

Un saludo,
Mediazion
"""

    if kind == "cliente":
        return f"""Hola {name},

Gracias por escribirnos. Hemos recibido tu mensaje correctamente. 👋

Mediazion trabaja con una red de mediadores profesionales que pueden ayudarte
a gestionar conflictos de forma rápida y confidencial.

Para orientarte mejor, te agradeceríamos que nos cuentes, muy brevemente:
· Tipo de conflicto (familiar, vecinal, laboral, empresarial…)
· Ciudad o zona
· Si hay otras personas implicadas

Con esta información podremos derivarte al mediador adecuado o darte una primera orientación.

Un saludo,
Mediazion
"""

    # otro / prueba
    return f"""Hola {name},

Gracias por tu mensaje, confirmamos que nos ha llegado correctamente. ✅

Mediazion es una plataforma para mediadores y para personas que necesitan mediación:
· Si eres mediador, podemos darte acceso a un Panel PRO con IA, actas, agenda y gestión de casos.
· Si buscas ayuda para un conflicto concreto, podemos derivarte a un mediador de nuestra red.

Si nos indicas si eres mediador o cliente, podremos darte información más concreta.

Un saludo,
Mediazion
"""


@contact_router.post("/contact")
def contact(data: ContactIn):
    if not data.accept:
        raise HTTPException(400, "Debes aceptar la política de privacidad.")

    # Clasificar el mensaje
    kind, confidence = classify_contact(data)
    auto_reply_text = build_auto_reply(data, kind)
    # Lo envolvemos en HTML sencillo
    user_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial; white-space:pre-wrap">
{auto_reply_text}
    </div>
    """

    # Email interno para info@
    info_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Nuevo contacto desde la web:</p>
      <ul>
        <li><strong>Nombre:</strong> {data.name}</li>
        <li><strong>Email:</strong> {data.email}</li>
        <li><strong>Asunto:</strong> {data.subject}</li>
        <li><strong>Tipo detectado:</strong> {kind} (conf={confidence:.2f})</li>
      </ul>
      <p>{data.message}</p>
    </div>
    """

    # Envío con “soft-fail”: nunca tiramos 500 por el correo
    mail_user_sent = False
    mail_info_sent = False
    mail_error = ""

    try:
        # Auto-respuesta al usuario
        _send_mail(
            data.email,
            "Hemos recibido tu mensaje · MEDIAZION",
            user_html,
            data.name,
        )
        mail_user_sent = True

        # Copia interna para MEDIAZION
        _send_mail(
            MAIL_TO_DEFAULT,
            f"[Contacto] {data.subject} — {data.name} <{data.email}>",
            info_html,
            "MEDIAZION",
        )
        mail_info_sent = True
    except RuntimeError:
        # SMTP no configurado: devolvemos ok pero marcamos sent=False
        mail_error = "SMTP no configurado"
    except Exception as e:
        # Error de transporte (p.ej. 'Connection unexpectedly closed')
        mail_error = str(e)

    return {
        "ok": True,
        "sent_user": mail_user_sent,
        "sent_info": mail_info_sent,
        "mail_error": mail_error,
        "type": kind,
        "confidence": confidence,
    }
