import json
from pathlib import Path

from src.database import connect, import_collection, entities, history, latest, results


def test_import_preserves_evidence_and_is_idempotent(tmp_path: Path):
    sample = [{
        "entity": {"nome": "Município Teste", "uf": "RJ", "site": "https://teste.rj.gov.br/", "portal": None},
        "page": {"url": "https://teste.rj.gov.br/", "collected_at": "2026-10-09T19:00:00+00:00",
                 "http_status": 200, "error": None, "title": "Prefeitura", "links": []},
        "criteria": [
            {"criterion_id": "1.1", "status": "atende", "finding": "Página acessível",
             "evidence_url": "https://teste.rj.gov.br/", "limitation": "Não é avaliação legal"},
            {"criterion_id": "1.2", "status": "inconclusivo", "finding": "Sem comprovação visual",
             "candidate_links": [], "evidence_url": "https://teste.rj.gov.br/"}
        ],
    }]
    source, target = tmp_path / "coletas.json", tmp_path / "app.sqlite3"
    source.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    assert import_collection(source, target) == 1
    assert import_collection(source, target) == 0
    with connect(target) as db:
        eid = entities(db)[0]["id"]
        runs = history(db, eid)
        assert len(runs) == 1
        data = latest(db, eid)
        assert data["score"] is None
        assert len(data["criteria"]) == 2
        assert data["criteria"][1]["evidence"]["candidate_links"] == []
        assert len(results(db, runs[0]["id"])) == 2
