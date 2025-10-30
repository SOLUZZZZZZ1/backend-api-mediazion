# news_routes.py
import os, time
from typing import Optional, Dict, Any, List
from fastapi import APIRouter
import httpx, feedparser
from dateutil import parser as dtparse

news_router = APIRouter()

# Intentos por orden
BOE_TRY = [
    "https://www.boe.es/rss/boe.xml",
    "https://www.boe.es/boe.atom",
    "https://www.boe.es/diario_boe/rss.php",
]
FEEDS = {
    "CONFILEGAL": ["https://confilegal.com/feed/"],
    "LEGALTODAY": ["https://www.legaltoday.com/feed/"],
    "BOE": BOE_TRY,
}

_CACHE = {"ts": 0.0, "items": []}
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "900"))

async def fetch_one(url: str) -> str:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent":"Mozilla/5.0 (MEDIAZION/1.0)"}) as s:
        r = await s.get(url); r.raise_for_status()
        return r.text

async def pull(source: str) -> List[Dict[str, Any]]:
    items = []
    for url in FEEDS[source]:
        try:
            xml = await fetch_one(url)
            feed = feedparser.parse(xml)
            for e in feed.entries[:50]:
                date = e.get("published") or e.get("updated")
                items.append({
                    "source": source,
                    "title": e.get("title","").strip(),
                    "summary": e.get("summary","").strip(),
                    "url": e.get("link","").strip(),
                    "date": (dtparse.parse(date).date().isoformat() if date else None)
                })
            if items: break  # con el primer feed válido del source basta
        except Exception as ex:
            print(f"[news] {source} fallback error {url}: {ex}")
            continue
    return items

@news_router.get("/news")
async def news(source: Optional[str] = None, q: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    now = time.time()
    global _CACHE
    if now - _CACHE["ts"] > CACHE_TTL or not _CACHE["items"]:
        items = []
        if source:
            items.extend(await pull(source))
        else:
            for src in FEEDS.keys():
                items.extend(await pull(src))
        items.sort(key=lambda x: x.get("date") or "", reverse=True)
        _CACHE = {"ts": now, "items": items}
    out = list(_CACHE["items"])
    if source: out = [i for i in out if i["source"].lower() == source.lower()]
    if q: out = [i for i in out if q.lower() in (i["title"]+" "+i["summary"]).lower()]
    return out[:max(1, min(limit, 200))]
