# news_routes.py — Actualidad (BOE / Confilegal / LegalToday)
from fastapi import APIRouter, HTTPException
import feedparser

router = APIRouter(prefix="/news", tags=["news"])

SOURCES = {
    "BOE": "https://www.boe.es/rss/boe_es.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/"
}

@router.get("/")
def list_news():
    try:
        items = []
        for name, url in SOURCES.items():
            feed = feedparser.parse(url)
            for e in feed.entries[:8]:
                items.append({
                    "title": e.get("title"),
                    "summary": e.get("summary", ""),
                    "url": e.get("link"),
                    "date": e.get("published", ""),
                    "source": name
                })
        return {"ok": True, "items": items}
    except Exception as e:
        raise HTTPException(500, f"Error obteniendo noticias: {e}")
