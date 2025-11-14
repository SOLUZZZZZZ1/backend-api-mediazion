# ai_legal_chat_routes.py
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
import os

try:
    from openai import OpenAI
except:
    OpenAI = None

ai_legal_chat = APIRouter(prefix="/ai/legal", tags=["ia-legal-chat"])

class LegalIn(BaseModel):
    prompt: str

@ai_legal_chat.post("/chat")
def chat_legal(body: LegalIn, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "Missing token")

    if not OpenAI:
        raise HTTPException(500, "OpenAI client not available")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Eres un abogado experto en mediación en España..."
                },
                {"role": "user", "content": body.prompt}
            ]
        )
        return {"ok": True, "text": resp.choices[0].message.content}
    except Exception as e:
        raise HTTPException(500, f"Error IA Legal: {e}")
