# news_routes.py
import os, time
from typing import Optional, Dict, Any, List
from fastapi import APIRouter
import httpx, feedparser
from dateutil import parser as dtparse

news_router = APIRouter()

FEEDS = {
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
    "BOE": "https://www.boe.es/rss/boe.xml",
}

_CACHE = {"ts": 0.0, "items": []}
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "900"))

async def fetch(url: str) -> str:
    async with httpx.AsyncClient(timeout=20) as s:
        r = await s.get(url); r.raise_for_status()
        return r.text

@news_router.get("/news")
async def news(source: Optional[str] = None, q: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    now = time.time()
    global _CACHE
    if now - _CACHE["ts"] > CACHE_TTL or not _CACHE["items"]:
        items = []
        for name, url in FEEDS.items():
            try:
                xml = await fetch(url)
                feed = feedparser.parse(xml)
                for e in feed.entries[:50]:
                    date = e.get("published") or e.get("updated")
                    items.append({
                        "source": name,
                        "title": e.get("title",""),
                        "summary": e.get("summary",""),
                        "url": e.get("link",""),
                        "date": (dtparse.parse(date).date().isoformat() if date else None)
                    })
            except Exception as ex:
                print("[news]", name, ex)
        items.sort(key=lambda x: x.get("date") or "", reverse=True)
        _CACHE = {"ts": now, "items": items}
    out = list(_CACHE["items"])
    if source: out = [i for i in out if i["source"].lower() == source.lower()]
    if q: out = [i for i in out if q.lower() in (i["title"]+" "+i["summary"]).lower()]
    return out[:max(1, min(limit, 200))]
