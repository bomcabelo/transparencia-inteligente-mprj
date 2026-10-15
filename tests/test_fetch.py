from src.fetch import HttpFetcher


class Resp:
    def __init__(self, status, headers=None, body=b"", text=""):
        self.status_code, self.headers, self._body, self.text = status, headers or {}, body, text

    def iter_content(self, n):
        yield self._body

    def close(self):
        pass


class Session:
    def __init__(self, routes):
        self.routes, self.headers, self.calls = routes, {}, []

    def get(self, url, **kw):
        self.calls.append(url)
        return self.routes.get(url, Resp(404))


def fetcher(routes, **kw):
    return HttpFetcher(delay=0, retries=1, session=Session(routes), **kw)


def test_robots_txt_is_respected():
    f = fetcher({"https://p.gov.br/robots.txt": Resp(200, {"content-type": "text/plain"},
                                                     text="User-agent: *\nDisallow: /privado")})
    assert f.fetch("https://p.gov.br/privado/x").error == "bloqueado_por_robots_txt"


def test_redirect_to_internal_address_is_blocked():
    f = fetcher({"https://p.gov.br/": Resp(302, {"location": "http://127.0.0.1/admin"})}, respect_robots=False)
    assert f.fetch("https://p.gov.br/").error == "redirecionamento_para_url_nao_permitida"


def test_redirect_followed_and_size_limit():
    f = fetcher({"https://p.gov.br/": Resp(301, {"location": "/novo"}),
                 "https://p.gov.br/novo": Resp(200, {"content-type": "text/html"}, body=b"x" * 50)},
                respect_robots=False, max_bytes=10)
    r = f.fetch("https://p.gov.br/")
    assert r.ok and r.final_url == "https://p.gov.br/novo" and r.truncated and len(r.body) == 10


def test_rate_limit_is_not_retried_without_retry_after():
    s = Session({"https://p.gov.br/": Resp(503)})
    f = HttpFetcher(delay=0, retries=3, session=s, respect_robots=False)
    r = f.fetch("https://p.gov.br/")
    assert r.rate_limited and r.error == "limite_do_servidor_http_503"
    assert s.calls.count("https://p.gov.br/") == 1  # não insiste


def test_collection_stops_on_rate_limit_and_skips_sitemap():
    from src.collector import collect
    from src.fetch import FetchResult

    class Limited:
        def __init__(self):
            self.calls = []

        def fetch(self, url):
            self.calls.append(url)
            if url.endswith("/a"):
                return FetchResult(url=url, status=503, error="limite_do_servidor_http_503", rate_limited=True)
            body = '<html><title>Despesas</title><a href="/a">Despesas</a><a href="/b">Receitas</a></html>'
            return FetchResult(url=url, final_url=url, status=200, content_type="text/html", body=body.encode())

    f = Limited()
    col = collect({"id": "x", "nome": "X", "site": "https://x.rj.gov.br/", "portal": None}, f)
    assert col.aborted and "HTTP 503" in col.aborted
    assert f.calls[-1].endswith("/a")  # nenhum acesso depois do 503 (nem sitemap, nem outras páginas)
