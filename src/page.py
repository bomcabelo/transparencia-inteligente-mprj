"""Extração estruturada de uma página HTML em um snapshot auditável.

O snapshot guarda o que as regras precisam (texto, links, formulários, tabelas,
trilha de navegação, controles de acessibilidade, documentos) e o hash do HTML
original, permitindo reprocessar avaliações sem recoletar o portal.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup

DOC_EXT = re.compile(r"\.(pdf|csv|xlsx?|ods|odt|docx?|json|xml|zip|txt|rtf)(?:$|\?)", re.I)
MAX_TEXT = 300_000


def route_fragment(url: str) -> str:
    """Fragmento que é ROTA de aplicação SPA ("#/despesas", "#!/receitas"), ou "" se for âncora comum."""
    frag = urldefrag(url)[1]
    return frag if frag.startswith(("/", "!/")) else ""


def clean_url(url: str) -> str:
    """Remove âncoras de página ("#topo"), mas preserva rotas de SPA ("#/despesas").

    Portais como o GeoSIAP usam roteamento por hash: sem isso, todos os links do menu
    colapsam na mesma URL e o robô nunca chega às seções de receita e despesa.
    """
    base, frag = urldefrag(url)
    return f"{base}#{frag}" if frag.startswith(("/", "!/")) else base


def norm(value: str) -> str:
    """Minúsculas e sem acentos, para comparar termos com grafias diferentes."""
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in raw if not unicodedata.combining(c)).casefold()


@dataclass
class Page:
    """Representação estruturada de uma página: texto, links, formulários, tabelas, documentos,
    trilha de navegação e controles de acessibilidade. É sobre ela que as regras trabalham.
    """
    url: str
    final_url: str
    status: int | None
    fetched_at: str
    sha256: str = ""
    title: str = ""
    lang: str = ""
    text: str = ""
    headings: list[str] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    breadcrumb: str = ""
    controls: list[str] = field(default_factory=list)
    documents: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    script_count: int = 0
    depth: int = 0
    renderer: str = "http"
    error: str | None = None
    snapshot_path: str | None = None
    screenshot_path: str | None = None
    themes: dict = field(default_factory=dict)

    @property
    def ntext(self) -> str:
        """Texto normalizado (sem acentos, minúsculo), para buscas por expressão regular."""
        if not hasattr(self, "_ntext"):
            object.__setattr__(self, "_ntext", norm(self.text))
        return self._ntext  # type: ignore[attr-defined]

    @property
    def host(self) -> str:
        """Host da URL final da página."""
        return urlsplit(self.final_url or self.url).hostname or ""

    def looks_dynamic(self) -> bool:
        """Heurística de SPA: muito script e pouco texto -> conteúdo depende de JavaScript."""
        return len(self.text) < 400 and self.script_count >= 3

    def snippet(self, pattern: str, width: int = 140) -> str | None:
        """Trecho literal do texto original ao redor do primeiro match (regex sobre texto normalizado)."""
        match = re.search(pattern, self.ntext)
        if not match:
            return None
        # norm() preserva o comprimento para caracteres latinos comuns; ajuste defensivo.
        start, end = max(0, match.start() - width), min(len(self.text), match.end() + width)
        return re.sub(r"\s+", " ", self.text[start:end]).strip()

    def to_dict(self) -> dict:
        """Representação serializável, sem o texto integral."""
        data = asdict(self)
        data.pop("text")
        return data


def _text(tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()


def _label_for(soup, field_tag) -> str:
    fid = field_tag.get("id")
    if fid:
        label = soup.find("label", attrs={"for": fid})
        if label:
            return _text(label)
    parent = field_tag.find_parent("label")
    return _text(parent) if parent else ""


def parse_html(*, url: str, final_url: str | None, status: int | None, fetched_at: str,
               body: bytes, depth: int = 0, renderer: str = "http") -> Page:
    """Converte o HTML bruto em `Page`.

    Extrai título, texto, cabeçalhos, links (com rotas de SPA preservadas), formulários, tabelas,
    links para documentos, controles de acessibilidade e trilha de navegação (por classe CSS,
    "Você está aqui" ou separadores » e ›).
    """
    page = Page(url=url, final_url=final_url or url, status=status, fetched_at=fetched_at,
                sha256=hashlib.sha256(body).hexdigest(), depth=depth, renderer=renderer)
    soup = BeautifulSoup(body, "html.parser")
    base = page.final_url
    page.title = _text(soup.title) if soup.title else ""
    html_tag = soup.find("html")
    page.lang = (html_tag.get("lang") or "") if html_tag else ""
    for meta in soup.find_all("meta"):
        key = meta.get("name") or meta.get("property")
        if key and meta.get("content") and key.lower() in {"description", "generator", "keywords", "og:site_name"}:
            page.meta[key.lower()] = meta["content"][:300]
    page.script_count = len(soup.find_all("script"))

    # Controles de acessibilidade e trilha antes de remover elementos de navegação.
    for tag in soup.find_all(["a", "button", "span", "li", "div"]):
        attrs = " ".join(str(tag.get(a) or "") for a in ("title", "aria-label", "class", "id", "accesskey"))
        own = _text(tag) if len(tag.get_text()) < 60 else ""
        probe = norm(f"{own} {attrs}")
        if re.search(r"contraste|aumentar (a )?fonte|diminuir (a )?fonte|tamanho (da )?fonte|"
                     r"fonte normal|\ba\+|\ba-\b|acessibilidade|vlibras|libras|font-?size|zoom", probe):
            page.controls.append(f"{own} [{attrs.strip()[:80]}]".strip())
    page.controls = list(dict.fromkeys(page.controls))[:40]
    crumbs = soup.select('[class*="breadcrumb" i], [id*="breadcrumb" i], [aria-label*="breadcrumb" i], '
                         '[class*="trilha" i], [class*="migalha" i], nav[aria-label*="caminho" i]')
    if crumbs:
        page.breadcrumb = _text(crumbs[0])[:300]
    else:
        m = re.search(r"voc[eê] est[aá] (aqui|em)\s*:?\s*(.{0,160})", soup.get_text(" "), re.I)
        if m:
            page.breadcrumb = re.sub(r"\s+", " ", m.group(0))[:200]
        else:  # trilha sem classe CSS, só com separadores: "Painel COVID-19 » Despesas Realizadas"
            # O separador pode estar num elemento próprio (<span>»</span>): sobe até 3 níveis.
            for node in soup.find_all(string=re.compile(r"[»›]")):
                el, found = node.parent, None
                for _ in range(3):
                    if el is None:
                        break
                    text = _text(el)
                    parts = [x for x in re.split(r"\s*[»›]\s*", text) if x.strip()]
                    if len(text) >= 200:
                        break
                    if len(parts) >= 2 and len(text) > 5:
                        found = text
                        break
                    el = el.parent
                if found:
                    page.breadcrumb = found
                    break

    for tag in soup.select("a[href]")[:3000]:
        href = clean_url(urljoin(base, tag.get("href", "").strip()))
        if not href.startswith(("http://", "https://")):
            continue
        label = _text(tag)[:200] or (tag.get("title") or tag.get("aria-label") or "")[:200]
        img = tag.find("img")
        if not label and img is not None:
            label = (img.get("alt") or img.get("title") or "")[:200]
        item = {"text": label, "url": href}
        page.links.append(item)
        if DOC_EXT.search(href):
            ext = DOC_EXT.search(href).group(1).lower()
            page.documents.append({**item, "ext": "xls" if ext == "xlsx" else ext})
    # Botões de exportação sem link direto (ex.: "Exportar CSV") também contam como indício.
    for tag in soup.find_all(["button", "input"]):
        label = _text(tag) or tag.get("value") or tag.get("title") or ""
        m = re.search(r"\b(csv|xlsx?|pdf|json|xml|ods|txt)\b", norm(label))
        if m and re.search(r"export|baixar|download|gerar|salvar|imprimir", norm(label)):
            page.documents.append({"text": label[:120], "url": base, "ext": m.group(1).replace("xlsx", "xls"),
                                   "kind": "botao"})

    for form in soup.find_all("form")[:30]:
        fields = []
        for f in form.find_all(["input", "select", "textarea"]):
            ftype = (f.get("type") or f.name).lower()
            if ftype in {"hidden", "submit", "button", "image", "reset"}:
                continue
            fields.append({"name": f.get("name") or f.get("id") or "", "type": ftype,
                           "placeholder": f.get("placeholder") or "", "label": _label_for(soup, f)[:120],
                           "required": f.has_attr("required") or f.get("aria-required") == "true"})
        page.forms.append({"action": urljoin(base, form.get("action") or ""),
                           "method": (form.get("method") or "get").lower(),
                           "role": form.get("role") or "", "fields": fields,
                           "text": _text(form)[:300]})
    # Campos de busca fora de <form> (comum em portais JS).
    for f in soup.select('input[type="search"], input[name="q"], input[name="s"], input[name*="busca" i], '
                         'input[placeholder*="pesquis" i], input[placeholder*="busca" i]'):
        if not f.find_parent("form"):
            page.forms.append({"action": base, "method": "get", "role": "search-loose", "text": "",
                               "fields": [{"name": f.get("name") or "", "type": (f.get("type") or "text").lower(),
                                           "placeholder": f.get("placeholder") or "", "label": "", "required": False}]})

    for table in soup.find_all("table")[:40]:
        headers = [_text(th) for th in table.find_all("th")][:40]
        rows = table.find_all("tr")
        if not headers and rows:
            headers = [_text(td) for td in rows[0].find_all("td")][:40]
        sample = [[_text(td)[:80] for td in r.find_all("td")][:15] for r in rows[1:4]]
        caption = _text(table.caption) if table.caption else ""
        page.tables.append({"headers": headers, "rows": len(rows), "sample": sample, "caption": caption})

    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    page.headings = [_text(h)[:200] for h in soup.find_all(["h1", "h2", "h3"])][:80]
    page.text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:MAX_TEXT]
    return page
