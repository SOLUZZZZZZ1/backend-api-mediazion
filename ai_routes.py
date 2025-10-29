# ai_routes.py
import os
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Header

try:
    from openai import OpenAI
    _HAS_OPENAI = True
except Exception:
    _HAS_OPENAI = False

ai_router = APIRouter()

def token_gate(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
    return {"ok": True}

@ai_router.post("/complete")
def ai_complete(prompt: str):
    if not _HAS_OPENAI or not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(503, "IA no disponible (falta OPENAI_API_KEY)")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL_GENERAL","gpt-4o-mini"),
        messages=[
            {"role":"system","content":"Eres el asistente institucional de MEDIAZION. Responde claro, amable y sin datos personales."},
            {"role":"user","content": prompt}
        ]
    )
    return {"ok": True, "text": resp.choices[0].message.content}

@ai_router.post("/assist")
def ai_assist(prompt: str, _=Depends(token_gate)):
    if not _HAS_OPENAI or not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(503, "IA no disponible (falta OPENAI_API_KEY)")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL_ASSIST","gpt-4o"),
        messages=[
            {"role":"system","content":"Asistente profesional de MEDIAZION. Redacta actas, resúmenes y comunicaciones con precisión y confidencialidad."},
            {"role":"user","content": prompt}
        ]
    )
    return {"ok": True, "text": resp.choices[0].message.content}
