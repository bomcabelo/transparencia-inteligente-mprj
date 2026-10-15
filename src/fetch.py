"""Camada de acesso HTTP: educada, limitada e auditável.

- respeita robots.txt (configurável) e um intervalo mínimo por domínio;
- segue redirecionamentos manualmente, validando cada salto (sem endereços internos);
- repete em 429/5xx/erros de rede com backoff exponencial e honra Retry-After;
- corta respostas acima do limite de bytes (marcando `truncated`);
- nunca transforma falha de acesso em "não atende": isso é decidido nas regras.

`FixtureFetcher` permite rodar o pipeline inteiro offline (testes e demonstração).
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from urllib import robotparser
from urllib.parse import urljoin, urlsplit

import requests

from src.crawler import is_public_http_url

USER_AGENT = os.environ.get(
    "MPRJ_USER_AGENT",
    "TransparenciaInteligenteMPRJ/1.0 (monitoramento de transparencia publica; contato: veja README)",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    content_type: str = ""
    body: bytes = b""
    error: str | None = None
    redirects: list[str] = field(default_factory=list)
    fetched_at: str = field(default_factory=utc_now)
    elapsed_ms: int | None = None
    truncated: bool = False
    renderer: str = "http"
    screenshot_path: str | None = None
    rate_limited: bool = False  # servidor sinalizou limite (429/503): não insistir

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.error is None

    @property
    def is_html(self) -> bool:
        return "html" in (self.content_type or "").lower()


class Fetcher(Protocol):
    def fetch(self, url: str) -> FetchResult: ...


class HttpFetcher:
    def __init__(self, *, delay: float = 1.0, timeout: float = 20, max_bytes: int = 3_000_000,
                 retries: int = 3, respect_robots: bool = True, session: requests.Session | None = None,
                 max_redirects: int = 5):
        self.delay, self.timeout, self.max_bytes = delay, timeout, max_bytes
        self.retries, self.respect_robots, self.max_redirects = retries, respect_robots, max_redirects
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT,
                                     "Accept-Language": "pt-BR,pt;q=0.9"})
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()

    # -- política de acesso ------------------------------------------------
    def _wait_turn(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._last_hit.get(host, -1e9) + self.delay)
            self._last_hit[host] = slot  # reserva o próximo horário (seguro entre threads)
            wait = slot - now
        if wait > 0:
            time.sleep(wait)

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = robotparser.RobotFileParser()
            try:
                resp = self.session.get(origin + "/robots.txt", timeout=self.timeout)
                if resp.status_code == 200 and "text" in resp.headers.get("content-type", "text"):
                    parser.parse(resp.text.splitlines())
                    self._robots[origin] = parser
                else:  # sem robots.txt (404) ou inacessível: acesso permitido
                    self._robots[origin] = None
            except requests.RequestException:
                self._robots[origin] = None
        parser = self._robots[origin]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    # -- requisição -----------------------------------------------------------
    def fetch(self, url: str) -> FetchResult:
        result = FetchResult(url=url)
        if not is_public_http_url(url):
            result.error = "url_nao_permitida"
            return result
        if not self.allowed(url):
            result.error = "bloqueado_por_robots_txt"
            return result
        current = url
        started = time.monotonic()
        for _hop in range(self.max_redirects + 1):
            response = self._get_with_retry(current, result)
            if response is None:
                return result
            if 300 <= response.status_code < 400 and response.headers.get("location"):
                target = urljoin(current, response.headers["location"])
                response.close()
                if not is_public_http_url(target):
                    result.error = "redirecionamento_para_url_nao_permitida"
                    return result
                result.redirects.append(target)
                current = target
                continue
            result.final_url = current
            result.status = response.status_code
            result.content_type = response.headers.get("content-type", "")
            chunks, size = [], 0
            try:
                for chunk in response.iter_content(65536):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > self.max_bytes:
                        result.truncated = True
                        break
            except requests.RequestException as exc:
                result.error = f"leitura_interrompida:{type(exc).__name__}"
            finally:
                response.close()
            result.body = b"".join(chunks)[: self.max_bytes]
            if result.status != 200 and not result.error:
                result.error = f"http_{result.status}"
            result.elapsed_ms = int((time.monotonic() - started) * 1000)
            return result
        result.error = "excesso_de_redirecionamentos"
        return result

    def _get_with_retry(self, url: str, result: FetchResult):
        host = urlsplit(url).hostname or ""
        for attempt in range(self.retries):
            self._wait_turn(host)
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=False, stream=True)
            except requests.RequestException as exc:
                result.error = f"erro_rede:{type(exc).__name__}"
                time.sleep(min(2 ** attempt, 8))
                continue
            if resp.status_code in (429, 503):
                # Limite de acesso (rate limit, firewall como Wordfence, manutenção). Insistir agrava o
                # bloqueio: só tenta de novo uma vez, e apenas se o servidor disser quando (Retry-After ≤ 30 s).
                retry_after = resp.headers.get("retry-after", "")
                resp.close()
                result.status, result.error = resp.status_code, f"limite_do_servidor_http_{resp.status_code}"
                result.rate_limited = True
                if attempt == 0 and retry_after.isdigit() and int(retry_after) <= 30:
                    time.sleep(int(retry_after))
                    continue
                return None
            if resp.status_code >= 500:  # erro transitório do servidor: backoff exponencial
                resp.close()
                result.status, result.error = resp.status_code, f"http_{resp.status_code}"
                time.sleep(min(2 ** attempt, 8))
                continue
            result.error, result.rate_limited = None, False
            return resp
        return None


class FixtureFetcher:
    """Fetcher em memória: {url: (status, conteúdo, content-type)} ou {url: html}."""

    def __init__(self, pages: dict[str, object], redirects: dict[str, str] | None = None):
        self.pages = {k.rstrip("/"): v for k, v in pages.items()}
        self.redirects = {k.rstrip("/"): v for k, v in (redirects or {}).items()}
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        result = FetchResult(url=url)
        key = url.rstrip("/")
        if key in self.redirects:
            result.redirects.append(self.redirects[key])
            key = self.redirects[key].rstrip("/")
        entry = self.pages.get(key)
        if entry is None:
            result.status, result.error = 404, "http_404"
            result.final_url = url
            return result
        if isinstance(entry, str):
            entry = (200, entry, "text/html; charset=utf-8")
        status, content, ctype = entry
        if isinstance(content, Exception):
            result.error = f"erro_rede:{type(content).__name__}"
            return result
        result.final_url = key
        result.status, result.content_type = status, ctype
        result.body = content.encode("utf-8") if isinstance(content, str) else content
        if status != 200:
            result.error = f"http_{status}"
        return result


class PlaywrightFetcher:
    """Renderiza JavaScript só quando o HTML estático vem "vazio" (opcional: `pip install playwright`).

    Ativado por MPRJ_RENDER_JS=1 ou por `"render_js": true` na entidade. Decisões:
    - o navegador é iniciado na PRIMEIRA chamada, na própria thread do worker (a API
      síncrona do Playwright não pode ser usada fora da thread em que foi criada);
    - só renderiza páginas com poucos links no HTML estático (SPA) e a primeira página
      (capa), que ganha screenshot como evidência visual; as demais seguem por HTTP;
    - espera `load` e, por até 10 s, a rede ficar ociosa (sites com polling nunca ficam);
    - qualquer falha de renderização mantém o conteúdo estático (nunca piora a coleta).
    """

    MIN_ANCHORS = 15

    def __init__(self, base: HttpFetcher, screenshot_dir: str | None = None):
        import playwright.sync_api  # noqa: F401  (falha cedo se a dependência opcional não existe)

        self.base = base
        self.screenshot_dir = screenshot_dir
        self._pw = self._browser = None
        self._first = True
        self.rendered = 0

    def _ensure_browser(self) -> None:
        if self._browser is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch()

    def needs_render(self, result: FetchResult) -> bool:
        return self._first or result.body.lower().count(b"<a ") < self.MIN_ANCHORS

    def fetch(self, url: str) -> FetchResult:
        result = self.base.fetch(url)  # política (robots, URL pública) e conteúdo estático
        if not result.ok or not result.is_html or not self.needs_render(result):
            return result
        first, self._first = self._first, False
        try:
            self._ensure_browser()
            page = self._browser.new_page(user_agent=USER_AGENT)
        except Exception as exc:
            result.renderer = f"http(render_indisponivel:{type(exc).__name__})"
            return result
        try:
            page.goto(result.final_url or url, wait_until="load", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass  # site com requisições contínuas: segue com o que já carregou
            result.body = page.content().encode("utf-8")
            result.renderer = "playwright"
            self.rendered += 1
            if self.screenshot_dir and first:
                import hashlib
                os.makedirs(self.screenshot_dir, exist_ok=True)
                name = hashlib.sha256(url.encode()).hexdigest()[:16] + ".png"
                path = os.path.join(self.screenshot_dir, name)
                page.screenshot(path=path, full_page=False)
                result.screenshot_path = path
        except Exception as exc:  # renderização é melhoria; conteúdo estático continua válido
            result.renderer = f"http(render_falhou:{type(exc).__name__})"
        finally:
            page.close()
        return result

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._pw.stop()
            self._browser = self._pw = None
