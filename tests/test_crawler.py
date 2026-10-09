from src.crawler import collect_page, evaluate_initial, is_public_http_url


def test_url_validation():
    assert is_public_http_url("https://japeri.rj.gov.br/")
    assert not is_public_http_url("http://127.0.0.1:1234/")
    assert not is_public_http_url("file:///etc/passwd")


def test_reject_private_url_without_network():
    evidence = collect_page("http://localhost/admin")
    assert evidence["http_status"] is None
    assert evidence["error"] == "URL não permitida"


def test_html_link_is_candidate_not_proof():
    evidence = {
        "url": "https://prefeitura.exemplo.gov.br/",
        "http_status": 200,
        "error": None,
        "collected_at": "2026-10-09T00:00:00+00:00",
        "links": [{"text": "Portal da Transparência", "url": "https://transparencia.exemplo.gov.br/"}]
    }
    results = evaluate_initial(evidence)
    assert results[0]["criterion_id"] == "1.1"
    assert results[0]["status"] == "atende"
    assert results[1]["status"] == "inconclusivo"
    assert len(results[1]["candidate_links"]) == 1


def test_network_failure_never_means_noncompliance():
    evidence = {"url": "https://exemplo.gov.br", "http_status": None,
                "error": "Erro de conexão", "collected_at": "2026-10-09T00:00:00+00:00", "links": []}
    statuses = [c["status"] for c in evaluate_initial(evidence)]
    assert statuses == ["inconclusivo", "inconclusivo"]
