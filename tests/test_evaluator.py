from src.evaluator import evaluate_page


def test_http_200_is_technical_only():
    page = {'url': 'https://example.org', 'http_status': 200, 'error': None,
            'collected_at': '2026-10-11T12:00:00Z', 'links': []}
    result = evaluate_page(page)
    assert [r['status'] for r in result] == ['atende', 'inconclusivo', 'inconclusivo']
    assert all(r['legal_compliance_verified'] is False for r in result)


def test_failure_not_noncompliance():
    page = {'url': 'https://example.org', 'http_status': None, 'error': 'SSLError', 'links': []}
    assert all(r['status'] == 'inconclusivo' for r in evaluate_page(page))


def test_link_is_candidate_not_proof():
    page = {'url': 'https://example.org', 'http_status': 200, 'error': None,
            'links': [{'text': 'Portal da Transparência', 'url': 'https://example.org/transparencia'},
                      {'text': 'Pesquisa', 'url': 'https://example.org/busca'}]}
    r = evaluate_page(page)
    assert len(r[1]['technical_evidence']) == 1
    assert len(r[2]['technical_evidence']) == 1
    assert r[1]['status'] == r[2]['status'] == 'inconclusivo'
