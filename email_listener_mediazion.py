"""
Mediazion · Email Listener IMAP
--------------------------------
Lee el buzón info@ (Nominalia) por IMAP, clasifica los correos con la
misma lógica que el formulario /contact y envía respuesta automática.

Se apoya en:
- ContactIn
- classify_contact
- build_auto_reply
- _send_mail

del módulo contact_routes.py

Config por variables de entorno (Render):

IMAP_HOST              -> p.ej. imap.securemail.pro
IMAP_PORT              -> normalmente 993
IMAP_USER              -> info@mediazion.eu
IMAP_PASS              -> contraseña del buzón
IMAP_SSL               -> "true"/"false"  (por defecto true)
IMAP_FOLDER            -> INBOX (por defecto)
IMAP_CHECK_INTERVAL    -> en segundos (por defecto 60)
EMAIL_MIN_CONFIDENCE   -> umbral de confianza para alta prioridad (por defecto 0.75)
EMAIL_PRIORITY_SUBJECT -> si no está vacío, añade un prefijo al asunto en alta prioridad

IMPORTANTE:
- Ejecutar esto como un "Worker" en Render, no como web.
- Comando sugerido: python email_listener_mediazion.py
"""

import os
import time
import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr

from contact_routes import ContactIn, classify_contact, build_auto_reply, _send_mail


IMAP_HOST = os.getenv("IMAP_HOST", "")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")
IMAP_SSL = str(os.getenv("IMAP_SSL", "true")).strip().lower() in ("1", "true", "yes", "on")
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")
CHECK_INTERVAL = int(os.getenv("IMAP_CHECK_INTERVAL", "60"))  # segundos

MIN_CONFIDENCE = float(os.getenv("EMAIL_MIN_CONFIDENCE", "0.75"))
PRIORITY_SUBJECT_PREFIX = os.getenv("EMAIL_PRIORITY_SUBJECT", "⚠️ [ALTA PRIORIDAD] ")


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    decoded_parts = decode_header(value)
    decoded_str = ""
    for part, enc in decoded_parts:
    
