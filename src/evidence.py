"""Etapa 6: indexação de indícios a partir do data/descoberta.json.

Os resultados são candidatos à revisão, não avaliações jurídicas de conformidade.
Uso: python -m src.evidence --source data/descoberta.json --update-db
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Correspondência exploratória com quesitos reais do checklistPortalTransp.xlsx.
# Não confundir termos semelhantes com comprovação de requisitos específicos.
RULES = {
    '3.1': {'description': 'Valores da receita pública arrecadada', 'terms': ('receita', 'arrecadacao')},
    '4.1': {'description': 'Número e o valor de empenho, liquidação e pagamento', 'terms': ('despesa', 'empenho', 'liquidacao', 'pagamento')},
    '7.2': {'description': 'Íntegra dos editais e demais documentos das licitações', 'terms': ('licitac', 'edital', 'pregao')},
    '8.2': {'description': 'Íntegra dos contratos e respectivos termos aditivos', 'terms': ('contrato', 'aditivo')},
}


def normalize(text: str) -> str:
    raw = unicodedata.normalize('NFKD', str(text or ''))
    return ''.join(c for c in raw if not unicodedata.combining(c)).casefold()


def matches(text: str, term: str) -> bool:
    return re.search(r'(?<!\w)' + re.escape(term) + r'\w*', normalize(text)) is not None


def extract_candidates(entry: dict) -> list[dict]:
    """Classifica evidências por tema sem alterar status jurídico de critérios."""
    discovery = entry.get('discovery') or {}
    found: list[dict] = []
    for page in discovery.get('pages', []):
        page_url = page.get('url') or ''
        if page.get('status') != 200 or not page_url:
            continue
        title = page.get('title') or ''
        excerpt = page.get('text_excerpt') or ''
        sources = [{'kind': 'page', 'url': page_url, 'label': title, 'snippet': excerpt[:300]}]
        for link in page.get('candidate_links', []):
            url = link.get('url') or ''
            if url.startswith(('https://', 'http://')):
                sources.append({'kind': 'link', 'url': url, 'label': str(link.get('text') or '')[:160], 'snippet': ''})
        for source in sources:
            searchable = ' '.join((source['label'], source['url']))
            # O texto integral da página não serve para afirmar critério: pode ser menu genérico.
            for code, rule in RULES.items():
                terms = [t for t in rule['terms'] if matches(searchable, t)]
                if not terms:
                    continue
                fingerprint = hashlib.sha256(f"{entry.get('entity')}|{code}|{source['kind']}|{source['url']}".encode()).hexdigest()
                found.append({
                    'evidence_id': fingerprint, 'entity': entry.get('entity'),
                    'criterion_id': code, 'criterion_description': rule['description'],
                    'source_url': source['url'], 'source_kind': source['kind'],
                    'source_page_url': page_url, 'page_sha256': page.get('sha256'),
                    'matched_terms': terms, 'label': source['label'],
                    'snippet': source['snippet'], 'collected_at': page.get('collected_at'),
                    'status': 'candidato', 'requires_human_review': True,
                    'legal_compliance_verified': False,
                })
    return list({x['evidence_id']: x for x in found}.values())


def analyze(source: Path, output: Path) -> list[dict]:
    entries = json.loads(source.read_text(encoding='utf-8'))
    result = []
    for entry in entries:
        items = extract_candidates(entry)
        result.append({'entity': entry.get('entity'), 'review_status': 'inconclusivo',
                       'candidate_count': len(items), 'evidences': items,
                       'analysis_at': datetime.now(timezone.utc).isoformat()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    return result


def import_to_sqlite(rows: list[dict], db_path: Path | None = None) -> int:
    from src.database import connect
    conn = connect(db_path)
    try:
        with conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS evidence_candidates (
                evidence_id TEXT PRIMARY KEY, entity_id INTEGER NOT NULL,
                criterion_id TEXT NOT NULL, source_url TEXT NOT NULL,
                source_page_url TEXT, source_kind TEXT,
                collected_at TEXT, evidence_json TEXT NOT NULL,
                FOREIGN KEY(entity_id) REFERENCES entities(id))''')
            count = 0
            for group in rows:
                entity = conn.execute('SELECT id FROM entities WHERE name=?', (group['entity'],)).fetchone()
                if entity is None:
                    continue
                for evidence in group['evidences']:
                    cursor = conn.execute('''INSERT OR IGNORE INTO evidence_candidates
                        (evidence_id, entity_id, criterion_id, source_url, source_page_url,
                         source_kind, collected_at, evidence_json)
                         VALUES (?,?,?,?,?,?,?,?)''', (
                        evidence['evidence_id'], entity['id'], evidence['criterion_id'],
                        evidence['source_url'], evidence['source_page_url'], evidence['source_kind'],
                        evidence['collected_at'], json.dumps(evidence, ensure_ascii=False)))
                    count += cursor.rowcount
        return count
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='data/descoberta.json')
    parser.add_argument('--output', default='data/evidencias.json')
    parser.add_argument('--update-db', action='store_true')
    args = parser.parse_args()
    rows = analyze(Path(args.source), Path(args.output))
    print('Municípios:', len(rows), '| evidências candidatas:', sum(r['candidate_count'] for r in rows))
    for row in rows:
        print(f"  {row['entity']}: {row['candidate_count']} candidatos")
    if args.update_db:
        print('Evidências novas persistidas:', import_to_sqlite(rows))
    print('Atenção: candidatos não equivalem a critérios atendidos.')


if __name__ == '__main__':
    main()
