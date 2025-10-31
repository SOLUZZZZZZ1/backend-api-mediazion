# news_routes.py
from fastapi import APIRouter, Query
import datetime
try:
    import feedparser
except Exception:
    feedparser = None
import requests

router = APIRouter()

@router.get("/news")
def news(source: str = Query(default=""), tag: str = Query(default=""), q: str = Query(default="")):
    """
    Devuelve noticias estructuradas: [{title, summary, url, date, source, tags: []}]
    Si no puede leer feeds, retorna lista vacía.
    """
    items = []

    feeds = []
    # Fuentes conocidas
    sources = {
        "CONFILEGAL": "https://confilegal.com/feed/",
        "LEGALTODAY": "https://www.legaltoday.com/feed/",
        "BOE": "https://boe.es/diario_boe/xml.php?id=BOE-S-2025",
        "CGPJ": "https://www.poderjudicial.es/cgpj/rss/ciudadanos.xml"
    }
    if source and source in sources:
        feeds = [sources[source]]
    else:
        feeds = list(sources.values())

    if feedparser:
        for url in feeds:
            try:
                d = feedparser.parse(url)
                for e in d.entries[:20]:
                    title = getattr(e, "title", "")
                    link = getattr(e, "link", "")
                    summary = getattr(e, "summary", "")
                    published = getattr(e, "published", "") or getattr(e, "updated", "")
                    if q and (q.lower() not in (title.lower() + " " + summary.lower())):
                        continue
                    items.append({
                        "title": title.strip(),
                        "summary": summary.strip(),
                        "url": link,
                        "date": published or "",
                        "source": d.feed.get("title", "Fuente"),
                        "short_source": d.feed.get("title", "Fuente"),
                        "tags": [tag] if tag else []
                    })
            except Exception as e:
                print("feed error", url, e)
    return items
