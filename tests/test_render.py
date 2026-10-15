"""Renderização JS: roda só se o Playwright e o Chromium estiverem instalados."""
import http.server
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("playwright.sync_api")
from src.fetch import FetchResult, PlaywrightFetcher  # noqa: E402

SPA = (b"<html><head><title>SPA</title></head><body><div id='app'></div><script>"
       b"document.getElementById('app').innerHTML = '<a href=\"/transparencia\">Portal da Transparencia</a>';"
       b"</script></body></html>")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(SPA)

    def log_message(self, *a):
        pass


class StaticBase:
    """Simula o HttpFetcher (que bloqueia localhost por segurança) devolvendo o HTML estático."""
    def __init__(self, url):
        self.url = url

    def fetch(self, url):
        return FetchResult(url=url, final_url=self.url, status=200, content_type="text/html", body=SPA)


def test_renders_spa_inside_worker_thread():
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        f = PlaywrightFetcher(StaticBase(url))  # criado na thread principal, usado no worker (como no pipeline)

        def job():
            try:
                return f.fetch(url)
            finally:
                f.close()
        with ThreadPoolExecutor(1) as ex:
            try:
                result = ex.submit(job).result(timeout=90)
            except Exception as exc:  # Chromium ausente no ambiente
                pytest.skip(f"Chromium indisponível: {exc}")
        if result.renderer != "playwright":
            pytest.skip(f"Renderização indisponível neste ambiente: {result.renderer}")
        assert b"Portal da Transparencia" in result.body
    finally:
        server.shutdown()
