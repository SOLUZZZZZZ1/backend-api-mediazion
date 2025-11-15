# news_routes.py — Actualidad MEDIAZION (BOE, Confilegal, CGPJ, LegalToday)
from fastapi import APIRouter, HTTPException, Query
import feedparser

news_router = APIRouter()

SOURCES = {
    "BOE": "https://www.boe.es/rss/boe_es.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Servicios/rss/Noticias.xml",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
}

@news_router.get("/news")
def list_news(q: str | None = Query(None, description="Filtro opcional, ej.: 'mediación'")):
    """
    Devuelve noticias recientes de varias fuentes jurídicas.
    - Si NO se pasa 'q', devuelve las últimas noticias (sin filtrar).
    - Si se pasa 'q', filtra por ese término en título / resumen.
    """
    try:
        search = (q or "").strip().lower()
        items = []

        for name, url in SOURCES.items():
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
                title = e.get("title", "") or ""
                summary = e.get("summary", "") or e.get("description", "") or ""
                link = e.get("link", "") or ""
                date = e.get("published", "") or e.get("updated", "") or ""

                blob = (title + " " + summary).lower()

                # Si hay término de búsqueda, filtramos por él
                if search:
                    if search not in blob:
                        continue

                items.append(
                    {
                        "title": title.strip(),
                        "summary": summary.strip(),
                        "url": link,
                        "date": date,
                        "source": name,
                    }
                )

        return {"ok": True, "items": items}

    except Exception as e:
        raise HTTPException(500, f"Error obteniendo noticias: {e}")
