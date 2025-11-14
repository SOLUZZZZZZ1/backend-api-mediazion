# news_routes.py — Actualidad real BOE + Confilegal + CGPJ + LegalToday
from fastapi import APIRouter, HTTPException
import feedparser

news_router = APIRouter()

SOURCES = {
    "BOE": "https://www.boe.es/rss/boe_es.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Servicios/rss/Noticias.xml",
    "LEGALTODAY": "https://www.legaltoday.com/feed/"
}

TERMS = ["mediación", "mediador", "acuerdo", "conflicto", "extrajudicial"]

@news_router.get("/news")
def list_news():
    items = []
    try:
        for name, url in SOURCES.items():
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
                title = e.get("title", "")
                summary = e.get("summary", "") or e.get("description", "")
                link = e.get("link", "")
                blob = (title + summary).lower()
                if any(t in blob for t in TERMS):
                    items.append({
                        "title": title,
                        "summary": summary,
                        "url": link,
                        "source": name
                    })
        return {"ok": True, "items": items}
    except Exception as e:
        raise HTTPException(500, str(e))
