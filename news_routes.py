# news_routes.py — agrega fuentes reales (RSS) con feedparser
from fastapi import APIRouter, Query
import feedparser, time

news_router = APIRouter()

# Fuentes (añadimos las que quieras)
FEEDS = {
    "BOE": "https://www.boe.es/rss/boe.xml",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Poder-Judicial/Sala-de-Prensa/Ultimas-noticias.feed",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
    # "MINISTERIO_JUSTICIA": "https://www.mjusticia.gob.es/es/actualidad/rss"  # si existiera
}

def parse_feed(url, source, limit):
    d = feedparser.parse(url)
    out = []
    for e in d.entries[:limit]:
        out.append({
            "title": getattr(e, "title", ""),
            "summary": getattr(e, "summary", "")[:500],
            "url": getattr(e, "link", ""),
            "date": getattr(e, "published", "") or getattr(e, "updated", ""),
            "source": source,
            "tags": []
        })
    return out

@news_router.get("/news")
def news(limit: int = Query(20, ge=1, le=100), source: str | None = None, tag: str | None = None, q: str | None = None):
    items = []
    if source and source in FEEDS:
        items.extend(parse_feed(FEEDS[source], source, limit))
    else:
        # mezclar varias fuentes (máx limit por fuente para no desbordar)
        per = max(1, limit // max(1, len(FEEDS)))
        for s, url in FEEDS.items():
            items.extend(parse_feed(url, s, per))
        # si quedó corto, rellena con más de la primera fuente
        if len(items) < limit:
            extra = parse_feed(next(iter(FEEDS.values())), next(iter(FEEDS.keys())), limit - len(items))
            items.extend(extra)
    # filtro rápido por q
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i["title"] or "").lower() or ql in (i["summary"] or "").lower()]
    # recorta al límite total
    return items[:limit]
