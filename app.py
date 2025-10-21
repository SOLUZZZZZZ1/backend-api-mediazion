from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import os, time, asyncio
import httpx, feedparser
from dateutil import parser as dateparser

app = FastAPI(title="MEDIAZION News API", version="1.0.0")

ALLOWED = os.getenv("ALLOWED_ORIGINS", "*")
allow_origins = [o.strip() for o in ALLOWED.split(",")] if ALLOWED and ALLOWED != "*" else ["*"]
app.add_middleware(
    CORSMiddleware, allow_origins=allow_origins,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

FEEDS = {
    "BOE": "https://www.boe.es/rss/boe_es.php",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Temas/Actualidad/rss/Actualidad",
    "MINISTERIO_JUSTICIA": "https://www.mjusticia.gob.es/es/actualidad/rss",
    "EURLEX_DOUE": "https://eur-lex.europa.eu/rss/es/index.html",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
}

KEYWORDS = [ "mediación", "mediador", "ADR", "resolución alternativa", "acuerdo", "conflicto" ]

_cache: Dict[str, Any] = {"items": [], "ts": 0}
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "900"))

async def fetch_feed(url: str) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        d = feedparser.parse(r.text)
    items: List[Dict[str, Any]] = []
    for e in d.entries[:30]:
        title = (getattr(e, "title", "") or "").strip()
        summary = (getattr(e, "summary", "") or "").strip()
        link = (getattr(e, "link", "") or "").strip()
        date_raw = getattr(e, "published", None) or getattr(e, "updated", None)
        date_iso = None
        if date_raw:
            try: date_iso = dateparser.parse(date_raw).date().isoformat()
            except: date_iso = None
        items.append({"title": title, "summary": summary, "url": link, "date": date_iso})
    return items

def matches_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in KEYWORDS)

def infer_tags(text: str) -> List[str]:
    t = (text or "").lower()
    tags = []
    mapping = {
        "civil": ["civil", "familia", "arrend", "vecinal"],
        "mercantil": ["mercantil", "societar", "empresa", "comercial"],
        "laboral": ["laboral", "empleo", "trabajo"],
        "penal": ["penal", "delito"],
        "internacional": ["ue", "europea", "internacional", "eur-lex", "doue"],
        "normativa": ["boe", "ley", "real decreto", "norma", "orden"],
        "jurisprudencia": ["sentencia", "ts", "tribunal", "cgpj"],
        "doctrina": ["artículo", "opinión", "análisis", "confilegal", "legaltoday"]
    }
    for tag, words in mapping.items():
        if any(w in t for w in words): tags.append(tag)
    if not tags: tags.append("general")
    return sorted(list(set(tags)))

async def load_all() -> List[Dict[str, Any]]:
    tasks = [fetch_feed(u) for u in FEEDS.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    aggregated: List[Dict[str, Any]] = []
    for (source, _), res in zip(FEEDS.items(), results):
        if isinstance(res, Exception): continue
        for item in res:
            blob = f"{item.get('title','')} {item.get('summary','')}"
            if matches_keywords(blob):
                aggregated.append({
                    "title": item["title"],
                    "summary": item["summary"],
                    "url": item["url"],
                    "date": item["date"],
                    "source": source,
                    "tags": infer_tags(item["title"] + " " + item["summary"])
                })
    aggregated.sort(key=lambda x: x["date"] or "", reverse=True)
    return aggregated[:120]

@app.get("/health")
def health(): return {"ok": True, "service": "mediazion-news"}

@app.get("/news")
async def news(source: str | None = None, tag: str | None = None, q: str | None = None, limit: int = 50):
    now = time.time()
    if now - _cache["ts"] > CACHE_TTL or not _cache["items"]:
        _cache["items"] = await load_all()
        _cache["ts"] = now
    items = list(_cache["items"])
    if source: items = [i for i in items if i["source"].lower() == source.lower()]
    if tag: items = [i for i in items if tag.lower() in [t.lower() for t in i.get("tags", [])]]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i["title"] or "").lower() or ql in (i["summary"] or "").lower()]
    return items[: max(1, min(limit, 200)) ]

@app.post("/tasks/news-refresh")
async def refresh():
    _cache["items"] = await load_all()
    _cache["ts"] = time.time()
    return {"ok": True, "count": len(_cache["items"])}
