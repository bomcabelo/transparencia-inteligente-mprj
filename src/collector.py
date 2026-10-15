"""Crawler focado: visita primeiro os links mais prováveis de conter os temas do checklist.

Em vez de varrer o site inteiro (caro e lento em escala), usa uma fila de prioridade:
a prioridade de um link vem do vocabulário temático (src/themes.py) e ganha bônus
quando cobre um tema ainda não visitado. Com isso, ~40 páginas por entidade bastam
para cobrir os temas avaliados, mantendo o custo previsível (5.000 portais × 40 páginas).
"""
from __future__ import annotations

import heapq
import itertools
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urlsplit

from src.fetch import Fetcher, FetchResult, utc_now
from src.fingerprint import detect
from src.page import DOC_EXT, Page, norm, parse_html
from src.themes import THEMES, classify_page, link_themes

SKIP = re.compile(r"(noticia|galeria|evento|agenda|video|foto|login|logout|wp-admin|feed|rss|"
                  r"facebook|instagram|twitter|youtube|whatsapp|linkedin|tiktok|flickr|"
                  r"javascript:|mailto:|tel:|\.(jpe?g|png|gif|svg|mp4|mp3|webp)$)", re.I)


@dataclass
class Collection:
    entity_id: str
    site_url: str | None
    portal_url: str | None
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    portal_source: str = "cadastro"
    pages: list[Page] = field(default_factory=list)
    raw: dict[str, bytes] = field(default_factory=dict)  # sha256 -> HTML original
    errors: list[dict] = field(default_factory=list)
    aborted: str | None = None
    vendors: dict = field(default_factory=dict)

    def page(self, role: str) -> Page | None:
        target = self.site_url if role == "site" else self.portal_url
        if not target:
            return None
        key = target.rstrip("/")
        for p in self.pages:
            if p.depth == 0 and (p.url.rstrip("/") == key):
                return p
        return None

    @property
    def ok_pages(self) -> list[Page]:
        return [p for p in self.pages if p.status == 200 and not p.error]

    @property
    def health(self) -> dict:
        site, portal = self.page("site"), self.page("portal")
        covered = sorted({t for p in self.ok_pages for t, s in p.themes.items() if s >= 3})
        return {
            "site_ok": bool(site and site.status == 200),
            "portal_ok": bool(portal and portal.status == 200) if self.portal_url else None,
            "paginas_ok": len(self.ok_pages),
            "paginas_com_erro": len(self.errors),
            "paginas_dinamicas": sum(p.looks_dynamic() for p in self.ok_pages),
            "temas_cobertos": covered,
            "temas_nao_encontrados": sorted(set(THEMES) - set(covered)),
            "abortada": self.aborted,
        }

    @property
    def sufficient(self) -> bool:
        """Coleta suficiente para afirmar AUSÊNCIA de algo (e não só presença)."""
        h = self.health
        return h["site_ok"] and h["paginas_ok"] >= 5 and not self.aborted


def _key(url: str) -> str:
    url = urldefrag(url)[0]
    parts = urlsplit(url)
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}?{parts.query}"


def _base_host(url: str | None) -> str | None:
    host = (urlsplit(url or "").hostname or "").lower()
    return host.removeprefix("www.") or None


def find_portal_link(home: Page) -> tuple[str | None, list[dict]]:
    candidates = []
    for link in home.links:
        label, url = norm(link["text"]), norm(link["url"])
        score = 0
        if "portal da transparencia" in label:
            score += 5
        elif "transparencia" in label:
            score += 3
        if "transparencia" in url:
            score += 2
        if score:
            candidates.append({**link, "score": score})
    candidates.sort(key=lambda c: -c["score"])
    return (candidates[0]["url"] if candidates else None), candidates[:10]


def collect(entity: dict, fetcher: Fetcher, *, max_pages: int = 40, max_depth: int = 3,
            abort_after: int = 5) -> Collection:
    site, portal = entity.get("site"), entity.get("portal")
    col = Collection(entity_id=entity["id"], site_url=site, portal_url=portal)
    allowed = {h for h in (_base_host(site), _base_host(portal)) if h}
    counter = itertools.count()
    queue: list = []
    seen: set[str] = set()
    covered: set[str] = set()
    consecutive_failures = 0

    def allowed_host(url: str) -> bool:
        host = _base_host(url) or ""
        return any(host == h or host.endswith("." + h) for h in allowed)

    def push(url: str, depth: int, priority: float) -> None:
        if _key(url) not in seen:
            heapq.heappush(queue, (-priority, next(counter), url, depth))

    def visit(url: str, depth: int) -> Page | None:
        nonlocal consecutive_failures
        seen.add(_key(url))
        result: FetchResult = fetcher.fetch(url)
        if not result.ok or not result.is_html:
            consecutive_failures += 0 if result.status == 404 else 1
            col.errors.append({"url": url, "status": result.status, "error": result.error or
                               f"conteudo_nao_html:{result.content_type}", "at": result.fetched_at})
            if depth == 0:  # páginas-semente ficam registradas mesmo com erro (evidência de indisponibilidade)
                page = Page(url=url, final_url=result.final_url or url, status=result.status,
                            fetched_at=result.fetched_at, error=result.error or "conteudo_nao_html", depth=0)
                col.pages.append(page)
            return None
        consecutive_failures = 0
        page = parse_html(url=url, final_url=result.final_url, status=result.status,
                          fetched_at=result.fetched_at, body=result.body, depth=depth,
                          renderer=result.renderer)
        page.screenshot_path = result.screenshot_path
        page.themes = classify_page(page)
        col.raw[page.sha256] = result.body
        col.pages.append(page)
        covered.update(t for t, s in page.themes.items() if s >= 3)
        if depth < max_depth:
            for link in page.links:
                href = link["url"]
                if SKIP.search(href) or DOC_EXT.search(href) or not allowed_host(href):
                    continue
                themes = link_themes(link)
                if not themes:
                    continue
                priority = sum(s * (2 if t not in covered else 1) for t, s in themes.items()) - depth
                push(href, depth + 1, priority)
        return page

    if site:
        home = visit(site, 0)
        if home and not portal:
            portal, candidates = find_portal_link(home)
            if portal:
                col.portal_url, col.portal_source = portal, "descoberto_na_capa"
                allowed.add(_base_host(portal))
    if col.portal_url and _key(col.portal_url) not in seen:
        visit(col.portal_url, 0)

    while queue and len(col.pages) < max_pages:
        if consecutive_failures >= abort_after:
            col.aborted = f"{consecutive_failures} falhas consecutivas: coleta interrompida (circuit breaker)"
            break
        _, _, url, depth = heapq.heappop(queue)
        if _key(url) in seen:
            continue
        visit(url, depth)

    col.vendors = detect(col.ok_pages)
    col.finished_at = utc_now()
    return col
