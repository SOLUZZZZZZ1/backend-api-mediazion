# contact_ai_routes.py — Clasificación básica + auto-respuesta para contactos web

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Literal
from contact_routes import _send_mail  # ya lo tienes para enviar correos

router = APIRouter()

class ContactIn(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

ContactType = Literal["mediador", "cliente", "otro"]


def classify_contact(body: ContactIn) -> tuple[ContactType, float]:
    """
    Versión 1: clasificación sencilla por palabras clave.
    Más adelante se puede sustituir por IA sin tocar el resto.
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


@router.post("/api/contact/auto")
def contact_auto(body: ContactIn):
    """
    Recibe un contacto desde la web, lo clasifica y envía una auto-respuesta.
    Devuelve el tipo detectado y un preview del texto enviado.
    """
    try:
        kind, confidence = classify_contact(body)
        reply_text = build_auto_reply(body, kind)

        # Enviar auto-respuesta al usuario
        # Usamos la misma función de envío que en contact_routes
        _send_mail(
            body.email,
            "Hemos recibido tu mensaje · Mediazion",
            reply_text,
            body.email,
        )

        # (Opcional) Podríamos enviar copia interna a vuestro email general

        return {
            "ok": True,
            "type": kind,
            "confidence": confidence,
            "auto_reply": reply_text,
        }
    except Exception as e:
        raise HTTPException(500, f"Error procesando contacto: {e}")
