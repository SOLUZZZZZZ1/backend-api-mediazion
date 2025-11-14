# news_routes.py — Actualidad MEDIAZION (noticias en tiempo real)

from fastapi import APIRouter, Query, HTTPException
import feedparser

news_router = APIRouter()

SOURCES = {
    "BOE": "https://www.boe.es/rss/boe_es.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Servicios/rss/Noticias.xml",
}

DEFAULT_TERMS = ["mediación", "conflicto", "acuerdo", "extrajudicial", "mediador"]


@news_router.get("/news")
def list_news(
    q: str | None = Query(None, description="Filtro opcional, por ejemplo: 'mediación familiar'")
):
    """
    Devuelve noticias recientes de BOE, Confilegal, LegalToday y CGPJ.
    Si no se pasa 'q', se filtra automáticamente por temas de mediación.
    """
    try:
        term = (q or "").strip().lower()
        items = []

        for name, url in SOURCES.items():
            feed = feedparser.parse(url)

            for e in feed.entries[:30]:
                title = e.get("title", "") or ""
                summary = e.get("summary", "") or e.get("description", "") or ""
                link = e.get("link", "") or ""
                published = e.get("published", "") or e.get("updated", "") or ""

                blob = (title + " " + summary).lower()

                if term:
                    # Buscar lo que el usuario pida
                    if term not in blob:
                        continue
                else:
                    # Temas relacionados con mediación
                    if not any(t in blob for t in DEFAULT_TERMS):
                        continue

                items.append({
                    "title": title.strip(),
                    "summary": summary.strip(),
                    "url": link,
                    "date": published,
                    "source": name,
                })

        return {
            "ok": True,
            "count": len(items),
            "items": items
        }

    except Exception as e:
        raise HTTPException(500, f"Error obteniendo noticias: {e}")
