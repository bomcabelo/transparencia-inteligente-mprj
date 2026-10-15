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
from src.fingerprint import VENDOR_URL, detect
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
    notes: list[str] = field(default_factory=list)  # decisões da coleta (fallbacks, avisos)

    def page(self, role: str) -> Page | None:
        target = self.site_url if role == "site" else self.portal_url
        if not target:
            return None
        key = _key(target)
        for p in self.pages:  # semente (depth 0) ou página já visitada antes de virar portal
            if key in (_key(p.url), _key(p.final_url)):
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
            "notas": self.notes,
        }

    @property
    def sufficient(self) -> bool:
        """Coleta suficiente para afirmar AUSÊNCIA de algo (e não só presença).

        Exige capa acessível, pelo menos 10 páginas válidas, coleta não abortada e, se há
        portal (cadastrado ou descoberto), que ele tenha sido alcançado.
        """
        h = self.health
        portal_reached = h["portal_ok"] is not False
        return h["site_ok"] and h["paginas_ok"] >= 10 and not self.aborted and portal_reached


def _key(url: str) -> str:
    url = urldefrag(url)[0]
    parts = urlsplit(url)
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}?{parts.query}"


_MULTI_SUFFIX = re.compile(r"\.(gov|leg|jus|mp|def|tc|com|org|net|edu)\.br$")
_STATE_GOV = re.compile(r"\.[a-z]{2}\.(gov|leg|jus|mp|def)\.br$")


def registrable_domain(url: str | None) -> str | None:
    """Domínio institucional: japeri.rj.gov.br, prefeitura.rio, prefeituracachoeiras.com.

    O crawler aceita qualquer subdomínio dele (site., portal., transparencia., esic.).
    Sem isso, um cadastro como portal.duquedecaxias.rj.gov.br descartaria links para
    duquedecaxias.rj.gov.br e transparencia.duquedecaxias.rj.gov.br.
    """
    host = _base_host(url)
    if not host:
        return None
    labels = host.split(".")
    keep = 4 if _STATE_GOV.search(host) else 3 if _MULTI_SUFFIX.search(host) else 2
    return ".".join(labels[-keep:]) if len(labels) >= keep else host


def _base_host(url: str | None) -> str | None:
    host = (urlsplit(url or "").hostname or "").lower()
    return host.removeprefix("www.") or None


def find_portal_link(home: Page, extra_pages: list[Page] | None = None) -> tuple[str | None, list[dict]]:
    """Melhor candidato a portal da transparência: na capa e, se preciso, nas demais páginas.

    Pontua rótulo "transparência", URL com "transparencia" e domínio de fornecedor de
    portal conhecido (Agili, Betha, IPM, Fiorilli, GeoSIAP...). Links da capa valem mais.
    Âncoras para a própria capa (ex.: "#transparencia") são ignoradas.
    """
    home_keys = {_key(home.url), _key(home.final_url)}
    best: dict[str, dict] = {}
    for page in [home] + list(extra_pages or []):
        for link in page.links:
            key = _key(link["url"])
            if key in home_keys:
                continue
            label, url = norm(link["text"]), norm(link["url"])
            score = 0
            if VENDOR_URL.search(urlsplit(link["url"]).hostname or "") and \
                    re.search(r"transpar|portal|receita|despesa|contas", f"{label} {url}"):
                score += 3
            if "portal da transparencia" in label:
                score += 5
            elif "transparencia" in label:
                score += 3
            if "transparencia" in url:
                score += 2
            if page is not home:
                score -= 1
            if score > 0 and score > best.get(key, {}).get("score", 0):
                best[key] = {**link, "score": score, "pagina": page.final_url}
    candidates = sorted(best.values(), key=lambda c: -c["score"])
    return (candidates[0]["url"] if candidates else None), candidates[:10]


_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")


def sitemap_urls(fetcher: Fetcher, roots: list[str], *, max_files: int = 8) -> list[str]:
    """URLs listadas nos sitemaps (robots.txt `Sitemap:` + caminhos usuais).

    Plano B quando o menu da capa é montado por JavaScript ou tem poucos links: o
    sitemap costuma listar todas as páginas do site, inclusive as de transparência.
    """
    queue, seen_files, urls = [], set(), []
    for root in roots:
        parts = urlsplit(root)
        origin = f"{parts.scheme}://{parts.netloc}"
        robots = fetcher.fetch(origin + "/robots.txt")
        if robots.status == 200:
            for line in robots.body.decode("utf-8", "ignore").splitlines():
                if line.lower().startswith("sitemap:"):
                    queue.append(line.split(":", 1)[1].strip())
        queue += [origin + p for p in SITEMAP_PATHS]
    while queue and len(seen_files) < max_files:
        url = queue.pop(0)
        if url in seen_files:
            continue
        seen_files.add(url)
        res = fetcher.fetch(url)
        if res.status != 200 or not res.body:
            continue
        for loc in _LOC.findall(res.body.decode("utf-8", "ignore")):
            (queue if loc.lower().endswith(".xml") else urls).append(loc)
    return list(dict.fromkeys(urls))


def collect(entity: dict, fetcher: Fetcher, *, max_pages: int = 40, max_depth: int = 3,
            abort_after: int = 5) -> Collection:
    site, portal = entity.get("site"), entity.get("portal")
    col = Collection(entity_id=entity["id"], site_url=site, portal_url=portal)
    site_domain = registrable_domain(site)

    def scope(url: str | None) -> str | None:
        """Domínio da prefeitura inteiro; portal em domínio de fornecedor só pelo host exato
        (evita entrar no portal de outro município hospedado pelo mesmo fornecedor)."""
        dom = registrable_domain(url)
        return dom if dom == site_domain or url == site else _base_host(url)

    allowed = {h for h in (scope(site), scope(portal)) if h}
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
                allowed.add(scope(portal))
    if col.portal_url and _key(col.portal_url) not in seen:
        visit(col.portal_url, 0)

    def crawl() -> None:
        while queue and len(col.pages) < max_pages:
            if consecutive_failures >= abort_after:
                col.aborted = f"{consecutive_failures} falhas consecutivas: coleta interrompida (circuit breaker)"
                break
            _, _, url, depth = heapq.heappop(queue)
            if _key(url) in seen:
                continue
            visit(url, depth)

    crawl()
    home = col.page("site")
    home = home if home and home.status == 200 else None
    if home and len(home.links) < 40:
        col.notes.append(f"Capa com só {len(home.links)} links no HTML: menu provavelmente montado por "
                         "JavaScript (considere render_js=true para esta entidade).")
    def adopt_portal(source: str) -> None:
        """Procura o portal em todas as páginas já coletadas e, se achar, passa a navegá-lo."""
        if col.portal_url or not home or home.status != 200:
            return
        url, cands = find_portal_link(home, [p for p in col.ok_pages if p is not home])
        if url:
            col.portal_url, col.portal_source = url, source
            allowed.add(scope(url))
            col.notes.append(f"Portal encontrado em {cands[0].get('pagina', home.final_url)}: {url}")
            visit(url, 0)
            crawl()

    adopt_portal("descoberto_no_site")
    # Plano B: navegação não alcançou o mínimo -> usar sitemaps, com diversidade.
    if not col.aborted and len(col.ok_pages) < 10 and len(col.pages) < max_pages and site:
        roots = [u for u in dict.fromkeys([site, col.portal_url]) if u]
        found = [u for u in sitemap_urls(fetcher, roots) if allowed_host(u) and not SKIP.search(u)
                 and not DOC_EXT.search(u)]
        picked, per_theme, posts = [], {}, 0
        ranked = []
        for u in found:
            themes = link_themes({"text": "", "url": u})
            if not themes:
                continue
            slug = urlsplit(u).path.rstrip("/").rsplit("/", 1)[-1]
            if slug.count("-") > 5 or re.search(r"/20\d\d/|\d{4,}", urlsplit(u).path):
                posts += 1  # cara de notícia/post (título longo ou data/número no caminho)
                continue
            depth = urlsplit(u).path.strip("/").count("/")
            ranked.append((sum(themes.values()) / (1 + slug.count("-") / 3 + depth / 2),
                           max(themes, key=themes.get), u))
        for priority, theme, u in sorted(ranked, key=lambda x: -x[0]):
            if per_theme.get(theme, 0) < 3:  # no máximo 3 URLs por tema: cobre mais temas
                per_theme[theme] = per_theme.get(theme, 0) + 1
                picked.append(u)
                push(u, 1, priority)
        col.notes.append(f"Sitemap consultado: {len(found)} URLs no domínio; {posts} descartadas por parecerem "
                         f"notícias; {len(picked)} selecionadas ({', '.join(sorted(per_theme))}).")
        crawl()
        adopt_portal("descoberto_via_sitemap")

    col.vendors = detect(col.ok_pages)
    col.finished_at = utc_now()
    return col
