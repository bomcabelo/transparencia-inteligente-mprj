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
