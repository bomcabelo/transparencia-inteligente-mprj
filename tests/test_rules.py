from datetime import date

from src.collector import collect
from src.demo import build_portal
from src.engine import evaluate
from src.fetch import FixtureFetcher
from src.rules.base import REGISTRY

TODAY = date(2026, 10, 13)


def run(level=3, kind="executivo_municipal", pages=None):
    entity = {"id": "x", "nome": "X", "tipo": kind, "site": "https://x.demo.invalid", "portal": None}
    col = collect(entity, FixtureFetcher(pages if pages is not None else build_portal("x", level, TODAY)))
    return {r.criterion_id: r for r in evaluate(entity, col, today=TODAY)}, col


def test_mature_portal_meets_all_implemented_criteria():
    results, col = run(3)
    assert col.portal_source == "descoberto_na_capa"
    failing = {cid: r.status for cid, r in results.items() if cid in REGISTRY and r.status != "atende"}
    assert failing == {}


def test_every_conclusive_result_has_evidence_with_url():
    for level in (0, 1, 2, 3):
        results, _ = run(level)
        for r in results.values():
            if r.status in ("atende", "parcial"):
                assert r.evidences and all(e.url for e in r.evidences), r.criterion_id


def test_specific_findings_at_intermediate_level():
    results, _ = run(1)
    assert results["15.2"].status == "nao_atende"            # exige "motivo do pedido"
    assert "Motivo" in results["15.2"].finding
    assert results["4.1"].status == "parcial"                # falta coluna de liquidação
    assert results["4.5"].status == "parcial"                # só PDF
    assert results["4.6"].status == "nao_atende"             # 90 dias sem atualização
    assert results["1.2"].status == "atende"


def test_unreachable_portal_is_never_noncompliant():
    results, col = run(pages={})
    assert not col.health["site_ok"]
    assert {r.status for cid, r in results.items() if cid in REGISTRY} == {"inconclusivo"}


def test_dynamic_pages_yield_inconclusive_not_noncompliant():
    spa = '<html><head><title>Portal</title>' + '<script src="a.js"></script>' * 5 + '</head><body><div id="root"></div></body></html>'
    pages = {f"https://x.demo.invalid{p}": spa for p in ["", "/a", "/b"]}
    results, _ = run(pages=pages)
    assert results["4.1"].status == "inconclusivo"
    assert results["1.3"].status == "inconclusivo"


def test_not_applicable_for_other_entity_types():
    results, _ = run(2, kind="legislativo_municipal")
    assert results["19.5"].status == "nao_aplicavel"
    assert results["21.1"].status == "nao_aplicavel"
    assert results["1.1"].status == "atende"


def test_unimplemented_criteria_are_marked_not_evaluated():
    results, _ = run(3)
    assert results["7.1"].status == "nao_avaliado"


def test_registrable_domain_accepts_sibling_subdomains():
    from src.collector import registrable_domain
    assert registrable_domain("https://portal.duquedecaxias.rj.gov.br/") == "duquedecaxias.rj.gov.br"
    assert registrable_domain("https://site.ib.itaborai.rj.gov.br/") == "itaborai.rj.gov.br"
    assert registrable_domain("https://transparencia.prefeitura.rio/") == "prefeitura.rio"
    assert registrable_domain("https://www.prefeituracachoeiras.com/") == "prefeituracachoeiras.com"
    assert registrable_domain("https://japeri.geosiap.net.br/portal-transparencia") == "geosiap.net.br"


def test_crawler_follows_links_to_sibling_subdomain():
    home = '<html><title>Prefeitura</title><a href="https://duque.rj.gov.br/transparencia">Transparência</a></html>'
    pages = {"https://portal.duque.rj.gov.br": home,
             "https://duque.rj.gov.br/transparencia": "<html><title>Portal da Transparência</title></html>"}
    entity = {"id": "d", "nome": "D", "tipo": "executivo_municipal", "site": "https://portal.duque.rj.gov.br",
              "portal": None}
    col = collect(entity, FixtureFetcher(pages))
    assert col.portal_url == "https://duque.rj.gov.br/transparencia"
    assert len(col.ok_pages) == 2


def test_vendor_hosted_portal_does_not_open_other_municipalities():
    portal = ('<html><title>Portal da Transparência</title><a href="https://outra.vendor.net.br/despesas">Despesas</a>'
              '<a href="https://japeri.vendor.net.br/despesas">Despesas</a></html>')
    pages = {"https://japeri.rj.gov.br": '<html><a href="https://japeri.vendor.net.br">Portal da Transparência</a></html>',
             "https://japeri.vendor.net.br": portal,
             "https://japeri.vendor.net.br/despesas": "<html><title>Despesas</title></html>",
             "https://outra.vendor.net.br/despesas": "<html><title>Despesas de outra cidade</title></html>"}
    entity = {"id": "j", "nome": "J", "tipo": "executivo_municipal", "site": "https://japeri.rj.gov.br", "portal": None}
    f = FixtureFetcher(pages)
    collect(entity, f)
    assert "https://outra.vendor.net.br/despesas" not in f.calls
    assert "https://japeri.vendor.net.br/despesas" in f.calls


def test_sitemap_fallback_when_home_menu_is_not_in_html():
    home = '<html><title>Prefeitura</title><a href="#transparencia">Transparência</a></html>'
    sitemap = ("<urlset>" + "".join(f"<url><loc>https://p.rj.gov.br/{p}</loc></url>" for p in
               ["despesas", "receitas", "licitacoes", "contratos", "noticias/x", "e-sic", "ouvidoria",
                "lgpd", "dados-abertos", "planejamento-rgf", "servidores"]) + "</urlset>")
    pages = {"https://p.rj.gov.br": home,
             "https://p.rj.gov.br/sitemap.xml": (200, sitemap, "application/xml")}
    for p in ["despesas", "receitas", "licitacoes", "contratos", "e-sic", "ouvidoria", "lgpd", "dados-abertos",
              "planejamento-rgf", "servidores"]:
        pages[f"https://p.rj.gov.br/{p}"] = f"<html><title>{p}</title></html>"
    entity = {"id": "p", "nome": "P", "tipo": "executivo_municipal", "site": "https://p.rj.gov.br", "portal": None}
    f = FixtureFetcher(pages)
    col = collect(entity, f)
    assert col.portal_url is None                      # âncora "#transparencia" não é o portal
    assert len(col.ok_pages) == 11 and "https://p.rj.gov.br/noticias/x" not in f.calls
    assert any("Sitemap consultado" in n for n in col.notes) and any("JavaScript" in n for n in col.notes)
