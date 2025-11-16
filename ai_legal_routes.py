# ai_legal_routes.py — IA Legal unificada (CHAT + BUSCADOR) con normalización OpenAI
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

# --------------------------------------
# NORMALIZAR RESPUESTA DEL MODELO
# --------------------------------------
def normalize_openai_content(content):
    """
    Convierte message.content del SDK nuevo (lista de bloques)
    en un string limpio para devolver al frontend.
    """
    # Caso antiguo: string directo
    if isinstance(content, str):
        return content.strip()

    result = []

    if isinstance(content, list):
        for part in content:
            # Ejemplo de part:
            # {"type":"text","text":{"value":"hola"}, ...}
            try:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        txt = part.get("text")
                        if isinstance(txt, str):
                            result.append(txt)
                        elif isinstance(txt, dict) and "value" in txt:
                            result.append(txt["value"])
            except:
                pass

    return "\n".join(result).strip() if result else ""

# --------------------------------------
# CHAT LEGAL
# --------------------------------------
class LegalChatIn(BaseModel):
    prompt: str

@ai_legal.post("/chat")
def legal_chat(body: LegalChatIn, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "Falta Authorization")

    if not HAS_OPENAI:
        raise HTTPException(500, "OpenAI no disponible")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(503, "Falta OPENAI_API_KEY")

    client = OpenAI(api_key=api_key)

    system = (
        "Eres una IA experta jurídica en mediación en España. "
        "Respondes de forma clara, estructurada y prudente. "
        "No inventes normativa ni hechos. No sustituyes asesoramiento de un abogado presencial."
    )

    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL_LEGAL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": body.prompt},
            ],
        )

        raw = resp.choices[0].message.content
        text = normalize_openai_content(raw)

        return {"ok": True, "text": text}

    except Exception as e:
        raise HTTPException(500, f"Error IA Legal: {e}")

# --------------------------------------
# BUSCADOR LEGAL (BOE, Confilegal, LegalToday, CGPJ)
# --------------------------------------
SOURCES = {
    "BOE": "https://www.boe.es/rss/boe_es.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Servicios/rss/Noticias.xml",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
}

@ai_legal.get("/search")
def legal_search(q: str = Query(..., min_length=2)):
    term = q.lower().strip()
    items = []

    try:
        for name, url in SOURCES.items():
            feed = feedparser.parse(url)

            for e in feed.entries[:30]:
                title = e.get("title", "") or ""
                summary = e.get("summary", "") or e.get("description", "") or ""
                link = e.get("link", "") or ""
                date = e.get("published", "") or e.get("updated", "")

                blob = (title + " " + summary).lower()

                if term in blob:
                    items.append(
                        {
                            "title": title.strip(),
                            "summary": summary.strip(),
                            "source": name,
                            "url": link,
                            "date": date,
                        }
                    )

        return {"ok": True, "items": items}

    except Exception as e:
        raise HTTPException(500, f"Error en búsqueda legal: {e}")
