# ai_legal_routes.py — Modo experto jurídico (búsqueda en fuentes jurídicas públicas)
from fastapi import APIRouter, HTTPException, Query
import feedparser

ai_legal_router = APIRouter(prefix="/ai/legal", tags=["ai-legal"])

SOURCES = {
    "BOE": "https://www.boe.es/rss/boe_es.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Servicios/rss/Noticias.xml",
}

@ai_legal_router.get("/search")
def legal_search(q: str = Query(..., min_length=2, description="Término jurídico o tema (ej.: 'mediación civil')")):
    try:
        ql = q.lower().strip()
        items = []
        for name, url in SOURCES.items():
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
                title = e.get("title", "")
                summary = e.get("summary", "") or e.get("description", "")
                link = e.get("link", "")
                published = e.get("published", "") or e.get("updated", "")
                blob = (title + " " + summary).lower()
                if ql in blob:
                    items.append({
                        "title": title,
                        "summary": summary,
                        "url": link,
                        "date": published,
                        "source": name
                    })
        return {"ok": True, "count": len(items), "items": items}
    except Exception as e:
        raise HTTPException(500, f"Error en búsqueda legal: {e}")
