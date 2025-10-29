# news_routes.py — feed de actualidad para MEDIAZION
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
import time, os
import httpx
import feedparser
from dateutil import parser as dtparse

news_router = APIRouter()

FEEDS = {
    "CONFILEGAL": "https://confilegal.com/feed/",
    "BOE": "https://www.boe.es/diario_boe/xml.php?id=BOE",
    "BOE-BO": "https://www.boe.es/boe.atom",
}
NEWS_CACHE = {"at": 0.0, "items": []}
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL") or 900)

async def _fetch(url: str):
    async with httpx.AsyncClient(timeout=20) as s:
        r = await s.get(url)
        r.raise_for_status()
        return r.text

@news_router.get("/news")
async def news(
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    tag: str | None = Query(default=None)
):
    now = time.time()
    global NEWS_CACHE
    if now - NEWS_CACHE["at"] > CACHE_TTL:
        items = []
        for name, url in FEEDS.items():
            try:
                xml = await _fetch(url)
                feed = feedparser.parse(xml)
                for e in feed.entries[:50]:
                    title = e.get("title", "")
                    summary = e.get("summary", "")
                    date = e.get("published") or e.get("updated")
                    date_iso = dtparse.parse(date).strftime("%Y-%m-%d") if date else None
                    items.append({
                        "source": name,
                        "title": title,
                        "summary": summary,
                        "date": date_iso,
                        "url": e.get("link", "")
                    })
            except Exception as ex:
                print(f"[news] {name} error: {ex}")
        # filtrar por query/tag opcional
        if q:
            ql = q.lower()
            items = [it for it in items if ql in (it["title"] + " " + it["summary"]).lower()]
        if source:
            items = [it for it in items if it["source"].lower() == source.lower()]
        # ordenar por fecha desc
        items.sort(key=lambda z: z.get("date") or "", reverse=True)
        NEWS_CACHE = {"at": now, "items": items}
    return {"ok": True, "items": NEWS_CACHE["items"]}
