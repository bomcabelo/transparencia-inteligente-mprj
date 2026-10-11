from src.discovery import extract_html, same_origin


def test_html_extracts_candidate_links_and_text():
    html = '<html><head><title>Prefeitura</title></head><body><a href="/transparencia">Portal da Transparência</a><p>Contratos públicos</p><script>segredo</script></body></html>'
    result = extract_html('https://exemplo.gov.br/', html)
    assert result['title'] == 'Prefeitura'
    assert result['candidate_links'][0]['url'] == 'https://exemplo.gov.br/transparencia'
    assert 'Contratos públicos' in result['text_excerpt']
    assert 'segredo' not in result['text_excerpt']


def test_crawler_stays_on_same_origin():
    root = 'https://exemplo.gov.br/'
    assert same_origin('https://exemplo.gov.br/transparencia', root)
    assert not same_origin('https://outro.gov.br/transparencia', root)
    assert not same_origin('http://exemplo.gov.br/transparencia', root)
    assert not same_origin('https://exemplo.gov.br/documento.pdf', root)
