"""
Mediazion · Email Listener IMAP (versión simplificada y estable)
Lee el buzón info@ (Nominalia) por IMAP, clasifica el mensaje con la
misma lógica que /contact y envía una auto-respuesta.

Se apoya en:
- ContactIn
- classify_contact
- build_auto_reply
- _send_mail

del módulo contact_routes.py
"""

import os
import time
import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr
from email.message import Message

from contact_routes import ContactIn, classify_contact, build_auto_reply, _send_mail


# Config IMAP desde entorno (Render)
IMAP_HOST = os.getenv("IMAP_HOST", "")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_PASS = os.getenv("IMAP_PASS", "")
IMAP_SSL = str(os.getenv("IMAP_SSL", "true")).strip().lower() in ("1", "true", "yes", "on")
IMAP_FOLDER = os.getenv("IMAP_FOLDER", "INBOX")
CHECK_INTERVAL = int(os.getenv("IMAP_CHECK_INTERVAL", "60"))  # segundos

# Umbral fijo para considerar alta prioridad
MIN_CONFIDENCE = 0.75

# Prefijo opcional para el asunto en alta prioridad
PRIORITY_SUBJECT_PREFIX = os.getenv("EMAIL_PRIORITY_SUBJECT", "⚠️ [ALTA PRIORIDAD] ")


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    decoded_parts = decode_header(value)
    decoded_str = ""
    for part, enc in decoded_parts:
        if isinstance(part, bytes):
            decoded_str += part.decode(enc or "utf-8", errors="ignore")
        else:
            decoded_str += part
    return decoded_str


def _get_body_from_message(msg: Message) -> str:
    # Intentar texto plano primero
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8",
                        errors="ignore",
                    )
                except Exception:
                    continue
        # Si no hay text/plain, probamos con text/html
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "").lower()
            if ctype == "text/html" and "attachment" not in disp:
                try:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8",
                        errors="ignore",
                    )
                    # Conversión sencilla de <br> a saltos de línea
                    return (
                        html.replace("<br>", "\n")
                        .replace("<br/>", "\n")
                        .replace("<br />", "\n")
                    )
                except Exception:
                    continue
    else:
        if msg.get_content_type() == "text/plain":
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8",
                errors="ignore",
            )
    return ""


def process_unseen_messages() -> None:
    if not (IMAP_HOST and IMAP_USER and IMAP_PASS):
        print("[EmailListener] IMAP no configurado (IMAP_HOST/USER/PASS). Saliendo.")
        return

    print(
        f"[EmailListener] Conectando a IMAP {IMAP_HOST}:{IMAP_PORT} (SSL={IMAP_SSL})…"
    )

    if IMAP_SSL:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    else:
        imap = imaplib.IMAP4(IMAP_HOST, IMAP_PORT)

    imap.login(IMAP_USER, IMAP_PASS)
    imap.select(IMAP_FOLDER)

    status, data = imap.search(None, "UNSEEN")
    if status != "OK":
        print("[EmailListener] No se pudieron buscar mensajes UNSEEN")
        imap.logout()
        return

    ids = data[0].split()
    if not ids:
        print("[EmailListener] No hay mensajes nuevos (UNSEEN).")
        imap.logout()
        return

    print(f"[EmailListener] Encontrados {len(ids)} mensajes nuevos. Procesando…")

    for num in ids:
        status, msg_data = imap.fetch(num, "(RFC822)")
        if status != "OK":
            print(f"[EmailListener] No se pudo leer el mensaje {num!r}")
            continue

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        from_header = msg.get("From", "")
        from_name, from_email = parseaddr(from_header)
        from_name = from_name or from_email or "Amigo/a"

        # Evitar bucles: si el remitente somos nosotros mismos, saltar
        if not from_email or from_email.lower().endswith("@mediazion.eu"):
            imap.store(num, "+FLAGS", "\\Seen")
            continue

        subject_header = msg.get("Subject", "")
        subject = _decode_header_value(subject_header) or "(sin asunto)"

        body_text = _get_body_from_message(msg)
        if not body_text.strip():
            body_text = "(sin contenido)"

        print(f"[EmailListener] Procesando correo de {from_email}, asunto={subject!r}")

        # Crear un ContactIn "falso" con el contenido del correo
        contact = ContactIn(
            name=from_name,
            email=from_email,
            subject=subject,
            message=body_text,
            accept=True,  # nos ha escrito voluntariamente
        )

        try:
            kind, confidence = classify_contact(contact)
            auto_reply_text = build_auto_reply(contact, kind)

            # Alta prioridad: cliente y confianza alta
            is_high_priority = (kind == "cliente" and confidence >= MIN_CONFIDENCE)

            # Envolvemos en HTML sencillo (igual que en contact_routes)
            user_html = f"""
            <div style="font-family:system-ui,Segoe UI,Roboto,Arial; white-space:pre-wrap">
            {auto_reply_text}
            </div>
            """

            reply_subject = subject
            if is_high_priority and PRIORITY_SUBJECT_PREFIX:
                if not subject.startswith(PRIORITY_SUBJECT_PREFIX):
                    reply_subject = f"{PRIORITY_SUBJECT_PREFIX}{subject}"

            # Enviar respuesta automática al remitente
            try:
                _send_mail(
                    from_email,
                    reply_subject,
                    user_html,
                    from_name,
                )
                print(
                    f"[EmailListener] Respuesta enviada a {from_email} "
                    f"(tipo={kind}, conf={confidence:.2f}, alta={is_high_priority})"
                )
            except Exception as e:
                print(f"[EmailListener] Error enviando respuesta a {from_email}: {e}")

            # Marcar como visto para no reprocesarlo
            imap.store(num, "+FLAGS", "\\Seen")

        except Exception as e:
            print(f"[EmailListener] Error procesando mensaje {num!r}: {e}")
            imap.store(num, "+FLAGS", "\\Seen")

    imap.logout()
    print("[EmailListener] Ciclo completado.")


def main_loop() -> None:
    print("[EmailListener] Iniciando bucle de escucha IMAP…")
    while True:
        try:
            process_unseen_messages()
        except Exception as e:
            print(f"[EmailListener] Error general en el bucle: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main_loop()
