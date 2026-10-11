"""Persistência auditável de resumos GeoSIAP, sem armazenar credores."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import os
import sqlite3

DEFAULT_DB = Path(__file__).resolve().parents[1] / 'data' / 'transparencia.sqlite3'

def connect(db_path=None):
    path = Path(db_path or os.environ.get('MPRJ_DB_PATH', DEFAULT_DB))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS geosiap_evidence (
 id INTEGER PRIMARY KEY,
 municipality TEXT NOT NULL,
 entity_id INTEGER NOT NULL,
 year_requested INTEGER NOT NULL,
 source_sha256 TEXT NOT NULL,
 processed_at_utc TEXT NOT NULL,
 criterion TEXT NOT NULL,
 assessment_status TEXT NOT NULL,
 record_count INTEGER NOT NULL,
 summary_json TEXT NOT NULL,
 UNIQUE(municipality,entity_id,year_requested,source_sha256)
);
CREATE INDEX IF NOT EXISTS ix_geosiap_lookup
 ON geosiap_evidence(municipality,entity_id,year_requested,id);
"""

# Campos autorizados: o resumo não deve transportar registros individuais, nomes ou documentos.
FIELDS = (
 'platform','municipality','entity_id','year_requested','endpoint','request_parameters',
 'processed_at_utc','source_sha256','record_count','filled_fields',
 'monetary_parseable_fields','monetary_zero_counts','monetary_missing_counts',
 'monetary_invalid_counts','monetary_negative_counts','records_without_id_empenho',
 'years_observed','criterion','assessment_status','assessment_reason','limitations',
)


def sanitize(summary: dict) -> dict:
    if not isinstance(summary, dict):
        raise ValueError('O resumo deve ser um objeto JSON')
    for key in ('municipality','entity_id','year_requested','source_sha256',
                'processed_at_utc','criterion','assessment_status','record_count'):
        if key not in summary:
            raise ValueError(f'Campo obrigatório ausente: {key}')
    if summary.get('platform') != 'GeoSIAP':
        raise ValueError('Plataforma inválida')
    if summary['assessment_status'] not in ('evidencia_parcial','inconclusivo'):
        raise ValueError('Classificação técnica desconhecida')
    if not isinstance(summary['record_count'], int) or summary['record_count'] < 0:
        raise ValueError('Quantidade de registros inválida')
    return {key: summary[key] for key in FIELDS if key in summary}


def import_summary(path: str | Path, db_path: str | Path | None = None) -> tuple[int, bool]:
    summary = sanitize(json.loads(Path(path).read_text(encoding='utf-8-sig')))
    with connect(db_path) as db:
        db.executescript(CREATE_SQL)
        key = (summary['municipality'], int(summary['entity_id']),
               int(summary['year_requested']), summary['source_sha256'])
        existing = db.execute(
            '''SELECT id FROM geosiap_evidence WHERE municipality=? AND entity_id=?
               AND year_requested=? AND source_sha256=?''', key).fetchone()
        if existing:
            return existing['id'], False
        cur = db.execute('''INSERT INTO geosiap_evidence
            (municipality,entity_id,year_requested,source_sha256,processed_at_utc,
             criterion,assessment_status,record_count,summary_json)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (*key, summary['processed_at_utc'], summary['criterion'],
             summary['assessment_status'], summary['record_count'],
             json.dumps(summary, ensure_ascii=False)))
        return cur.lastrowid, True


def list_evidences(db_path: str | Path | None = None) -> list[dict]:
    with connect(db_path) as db:
        db.executescript(CREATE_SQL)
        rows = db.execute('''SELECT id,municipality,entity_id,year_requested,
          processed_at_utc,criterion,assessment_status,record_count,source_sha256
          FROM geosiap_evidence ORDER BY id DESC''').fetchall()
        return [dict(row) for row in rows]


def get_evidence(evidence_id: int, db_path: str | Path | None = None) -> dict | None:
    with connect(db_path) as db:
        db.executescript(CREATE_SQL)
        row = db.execute('SELECT summary_json FROM geosiap_evidence WHERE id=?',
                         (evidence_id,)).fetchone()
        return json.loads(row['summary_json']) if row else None


def main():
    parser = argparse.ArgumentParser(description='Importa resumo GeoSIAP no SQLite')
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--db', type=Path, default=None)
    args = parser.parse_args()
    identifier, created = import_summary(args.source, args.db)
    print('Evidência:', identifier)
    print('Situação:', 'importada' if created else 'já existente (sem duplicação)')

if __name__ == '__main__':
    main()
