from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_on_empty_database(tmp_db):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["evaluations_executed"] == 0


def test_unknown_entity(tmp_db):
    assert client.get("/entities/999").status_code == 404


@pytest.fixture()
def seeded(tmp_db):
    from src.demo import seed
    seed(tmp_db, today=date(2026, 10, 13))
    return tmp_db


def test_entities_and_latest(seeded):
    ents = client.get("/entities").json()
    assert {"id", "name", "uf", "score", "classificacao"} <= set(ents[0])
    a = next(e for e in ents if e["slug"] == "demo-a")
    latest = client.get(f"/entities/{a['id']}/evaluations/latest").json()
    assert latest["score"] == 100.0 and latest["pontuacao"]["classificacao"] == "Elevado"
    crit = {c["criterion_id"]: c for c in latest["criteria"]}
    assert crit["4.1"]["evidences"][0]["url"].startswith("https://")


def test_history_diff_and_criterion_timeline(seeded):
    a = next(e for e in client.get("/entities").json() if e["slug"] == "demo-a")
    hist = client.get(f"/entities/{a['id']}/evaluations/history").json()
    assert [h["score"] for h in hist] == sorted(h["score"] for h in hist) and len(hist) == 3
    d = client.get(f"/entities/{a['id']}/evaluations/diff").json()
    assert d["melhoraram"] and not d["pioraram"]
    tl = client.get(f"/entities/{a['id']}/criteria/4.6/history").json()
    assert [t["status"] for t in tl] == ["nao_atende", "parcial", "atende"]
    crit = client.get(f"/entities/{a['id']}/criteria", params={"status": "atende"}).json()
    assert next(c for c in crit if c["criterion_id"] == "4.6")["atende_desde"].startswith("2026-10-13")


def test_overview_and_catalog(seeded):
    o = client.get("/overview").json()
    assert o["entidades_avaliadas"] == 4 and o["melhor"]["score"] >= o["pior"]["score"]
    assert sum(o["distribuicao_scores"].values()) == 4
    impl = client.get("/criteria", params={"implementado": True}).json()
    assert len(impl) == 27 and all(c["complexidade"] for c in impl)
