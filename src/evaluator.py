"""Triagem técnica dos critérios prioritários do checklist MPRJ.

Não comprova conformidade legal; registra indícios e mantém casos inconclusivos.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value or '') if not unicodedata.combining(c)).casefold()


def evaluate_page(page: dict, portal_url: str | None = None) -> list[dict]:
    links = page.get('links') or []
    ok = page.get('http_status') == 200 and not page.get('error')
    portal_links = [link for link in links if 'transparencia' in normalize(link.get('text', ''))
                    or 'transparencia' in normalize(link.get('url', ''))
                    or (portal_url and link.get('url', '').rstrip('/') == portal_url.rstrip('/'))]
    search_links = [link for link in links if re.search(r'\b(busca|pesquisa|pesquisar)\b', normalize(link.get('text', '')))]

    def finding(code: str, status: str, detail: str, evidence: list) -> dict:
        return {'criterion_id': code, 'status': status, 'finding': detail,
                'evidence_url': page.get('url'), 'evaluated_at': page.get('collected_at'),
                'technical_evidence': evidence[:10], 'method': 'screening_v1',
                'legal_compliance_verified': False, 'requires_human_review': True}

    return [
        finding('1.1', 'atende' if ok else 'inconclusivo',
                'Resposta HTTP 200 observada; somente disponibilidade técnica' if ok else
                'Disponibilidade não confirmada',
                [{'http_status': page.get('http_status'), 'error': page.get('error')}]),
        finding('1.2', 'inconclusivo',
                'Encontrado link candidato; visibilidade precisa de verificação visual' if portal_links else
                'Link não encontrado na amostra HTML; ausência não comprovada', portal_links),
        finding('1.3', 'inconclusivo',
                'Encontrado link candidato; funcionalidade de pesquisa não testada' if search_links else
                'Pesquisa não confirmada com base nos links coletados', search_links),
    ]


def sync_to_database(rows: list[dict]) -> int:
    """Atualiza critérios da coleta já armazenada, sem alterar seu horário."""
    from src.database import connect
    changed = 0
    with connect() as db:
        for row in rows:
            entity = db.execute('SELECT id FROM entities WHERE name=?', (row['entity']['nome'],)).fetchone()
            if entity is None:
                continue
            run = db.execute('SELECT id FROM evaluations WHERE entity_id=? AND collected_at=?',
                             (entity['id'], row['page'].get('collected_at'))).fetchone()
            if run is None:
                continue
            db.execute("DELETE FROM criteria_results WHERE evaluation_id=? AND criterion_id IN ('1.1','1.2','1.3')", (run['id'],))
            for c in row['criteria']:
                db.execute('INSERT INTO criteria_results (evaluation_id,criterion_id,status,finding,evidence_url,evidence_json) VALUES (?,?,?,?,?,?)',
                           (run['id'], c['criterion_id'], c['status'], c['finding'], c['evidence_url'], json.dumps(c, ensure_ascii=False)))
            changed += 1
    return changed


def process(source: Path, output: Path, update_db: bool = False) -> int:
    rows = json.loads(source.read_text(encoding='utf-8'))
    # Horário novo representa execução da análise, não novo acesso às páginas.
    for row in rows:
        row['criteria'] = evaluate_page(row['page'], row['entity'].get('portal'))
        row['page']['analysis_at'] = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    if update_db:
        print(f"Coletas existentes atualizadas no banco: {sync_to_database(rows)}")
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='data/coletas.json')
    parser.add_argument('--output', default='data/avaliacoes.json')
    parser.add_argument("--update-db", action="store_true")
    args = parser.parse_args()
    print(f'Municípios analisados: {process(Path(args.source), Path(args.output), args.update_db)}')
    print('Resultados preliminares: não representam certificação de conformidade.')
