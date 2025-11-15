# ai_legal_routes.py — IA Legal unificada (chat jurídico + buscador jurídico)
from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel
import feedparser
import os

# OpenAI
try:
    from openai import OpenAI
    HAS_OPENAI = True
except Exception:
    HAS_OPENAI = False

ai_legal = APIRouter(prefix="/ai/legal", tags=["ai-legal"])

# -----------------------------
#   NORMALIZADOR DE MENSAJES
# -----------------------------
def normalize_openai_content(content):
    """
    Convierte message.content del SDK 1.37+ en texto plano.
    - Puede ser string
    - Puede ser lista de objetos con {type, text}
    """
    if isinstance(content, str):
        return content

    out = []
    if isinstance(content, list):
        for part in content:
            try:
                if isinstance(part, dict):
                    # text simple
                    if "text" in part and isinstance(part["text"], str):
                        out.append(part["text"])
                    # text.value (cuando viene en subobjeto)
                    elif "text" in part and isinstance(part["text"], dict) and "value" in part["text"]:
                        out.append(part["text"]["value"])
                # fallback
                else:
                    out.append(str(part))
            except:
                pass

    return "\n".join(out).strip() if out else ""

# -----------------------------
#   CHAT JURÍDICO
# -----------------------------
class LegalChatIn(BaseModel):
    prompt: str

@ai_legal.post("/chat")
def legal_chat(body: LegalChatIn, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "Falta Authorization")

    if not HAS_OPENAI:
        raise HTTPException(500, "OpenAI no está disponible")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_msg = (
        "Eres una IA experta jurídica en mediación en España. "
        "Respondes de forma clara, prudente y bien estructurada. "
        "No sustituyes asesoramiento legal personal. "
        "Citas normativa solo si aplica, pero sin inventar nada."
    )

    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL_LEGAL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": body.prompt},
            ],
        )
        raw = resp.choices[0].message.content
        text = normalize_openai_content(raw)
        return {"ok": True, "text": text}
    except Exception as e:
        raise HTTPException(500, f"Error IA Legal: {e}")

# -----------------------------
#   BUSCADOR JURÍDICO
# -----------------------------
SOURCES = {
    "BOE": "https://www.boe.es/rss/boe_es.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Servicios/rss/Noticias.xml",
}

@ai_legal.get("/search")
def legal_search(q: str = Query(..., min_length=2)):
    try:
        term = q.lower().strip()
        items = []

        for name, url in SOURCES.items():
            feed = feedparser.parse(url)

            for e in feed.entries[:25]:
                title = e.get("title", "") or ""
                summary = e.get("summary", "") or e.get("description", "") or ""
                link = e.get("link", "") or ""
                date = e.get("published", "") or e.get("updated", "")

                blob = (title + " " + summary).lower()
                if term in blob:
                    items.append({
                        "title": title,
                        "summary": summary,
                        "url": link,
                        "date": date,
                        "source": name,
                    })

        return {"ok": True, "items": items}
    except Exception as e:
        raise HTTPException(500, f"Error en búsqueda legal: {e}")
