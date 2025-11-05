from fastapi import APIRouter, Query
import feedparser

news_router = APIRouter()

FEEDS = {
    "BOE": "https://www.boe.es/rss/boe.xml",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Poder-Judicial/Sala-de-Prensa/Ultimas-noticias.feed",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/"
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
def news(limit: int = Query(20, ge=1, le=100), source: str | None = None):
    items = []
    if source and source in FEEDS:
        items.extend(parse_feed(FEEDS[source], source, limit))
    else:
        per = max(1, limit // max(1, len(FEEDS)))
        for s, url in FEEDS.items():
            items.extend(parse_feed(url, s, per))
    return items[:limit]
