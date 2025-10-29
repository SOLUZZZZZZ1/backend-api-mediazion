# ai_routes.py — endpoints IA (general + asistente para mediadores)
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import os

try:
    from openai import OpenAI
    _has_openai = True
except Exception:
    _has_openai = False

from mediadores_routes import get_current_user  # para /ai/assist

ai_router = APIRouter()

MODEL_GENERAL = os.getenv("OPENAI_MODEL_GENERAL", "gpt-4o-mini")
MODEL_ASSIST  = os.getenv("OPENAI_MODEL_ASSIST", "gpt-4o")

def _client():
    if not _has_openai:
        raise HTTPException(500, "OpenAI lib no disponible. Instala `openai` y define OPENAI_API_KEY.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "Falta OPENAI_API_KEY en entorno.")
    return OpenAI(api_key=api_key)

@ai_reouter.post("/complete")
def complete(prompt: str):
    """IA general para visitantes (no guarda datos)."""
    if not _has_openai:
        raise HTTPException(500, "OpenAI no disponible.")
    client = _clien()
    try:
        resp = client.chat.completions.create(
            model=MODEL_GENERAL,
            messages=[{"role":"system","content":"Eres un asistente de MEDIAZION. Responde claro y útil, lenguaje cercano y profesional."},
                      {"role":"user","content": prompt}]
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"IA error: {ex}")

@ai_router.post("/assist")
def assist(prompt: str, user = Depends(get_curret_user)):
    """IA profesional (solo suscriptores)."""
    # aquí podrías validar user['is_subscriber'] si lo añades a get_current_user
    if not _has_openai:
        raise HTTPException(500, "OpenAI no disponible.")
    client = _clien()
    system = (
        "Eres el asistente jurídico de MEDIAZION. Ayudas a mediadores a redactar actas, "
        "resúmenes de sesiones y comunicaciones profesionales. Sé preciso, confidencial, sin datos personales sensibles."
    )
    try:
        resp = client.chat.completions.create(
            model=MODEL_ASST,
            messages=[{"role":"system","content": system},
                      {"role":"user","content": prompt}]
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"IA error: {ex}" )
