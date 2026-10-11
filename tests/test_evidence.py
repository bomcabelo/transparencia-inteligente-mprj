from src.evidence import extract_candidates, analyze, import_to_sqlite
from src.database import connect
import json


def fixture():
    return {'entity': 'Prefeitura Teste', 'discovery': {'pages': [{
        'url': 'https://exemplo.gov.br/', 'status': 200, 'title': 'Prefeitura',
        'text_excerpt': 'Página inicial', 'sha256': 'abc',
        'collected_at': '2026-10-11T10:00:00+00:00',
        'candidate_links': [
            {'text': 'Licitações', 'url': 'https://exemplo.gov.br/licitacoes'},
            {'text': 'Despesas', 'url': 'https://exemplo.gov.br/despesas'},
            {'text': 'Notícias', 'url': 'https://exemplo.gov.br/noticias'},
        ]}]}}


def test_collects_candidates_not_verdicts():
    rows = extract_candidates(fixture())
    assert any(r['criterion_id'] == '4.1' for r in rows)
    assert all(r['status'] == 'candidato' for r in rows)
    assert all(not r['legal_compliance_verified'] for r in rows)


def test_no_false_compliance_for_unavailable_site():
    assert extract_candidates({'entity': 'Teste', 'discovery': {'pages': [], 'errors': ['timeout']}}) == []


def test_analysis_export_and_sqlite_import_idempotent(tmp_path):
    source = tmp_path / 'discovery.json'
    target = tmp_path / 'evidences.json'
    db = tmp_path / 'test.db'
    source.write_text(json.dumps([fixture()]), encoding='utf-8')
    rows = analyze(source, target)
    assert target.exists() and rows[0]['candidate_count'] >= 2
    with connect(db) as conn:
        conn.execute('INSERT INTO entities(name,uf) VALUES (?,?)', ('Prefeitura Teste','RJ'))
    assert import_to_sqlite(rows, db) >= 2
    assert import_to_sqlite(rows, db) == 0
