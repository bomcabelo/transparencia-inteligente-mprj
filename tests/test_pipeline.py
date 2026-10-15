from datetime import date

from src import repository as repo
from src.demo import build_portal
from src.fetch import FixtureFetcher
from src.pipeline import reevaluate, run


def entity(slug="mun"):
    return {"id": slug, "nome": slug.upper(), "entidade": slug, "tipo": "executivo_municipal",
            "municipio": slug, "site": f"https://{slug}.demo.invalid", "portal": None, "ativo": True}


def test_run_persists_history_and_reprocessing_is_reproducible(tmp_db):
    pages = build_portal("mun", 2, date.today())
    run(entities=[entity()], fetcher_factory=lambda: FixtureFetcher(pages), db_path=tmp_db, probes=False)
    pages3 = build_portal("mun", 3, date.today())
    run(entities=[entity()], fetcher_factory=lambda: FixtureFetcher(pages3), db_path=tmp_db, probes=False)
    with repo.connect(tmp_db) as db:
        hist = repo.history(db, 1)
        assert [h["kind"] for h in hist] == ["coleta", "coleta"]
        assert hist[1]["score"] > hist[0]["score"]
        d = repo.diff(db, hist[0]["id"], hist[1]["id"])
        assert {x["criterio"] for x in d["melhoraram"]} >= {"18.3", "19.1"} and not d["pioraram"]
        before = {r["criterion_id"]: r["status"] for r in repo.results(db, hist[1]["id"], False)}
        snaps = db.execute("SELECT COUNT(*) n FROM pages WHERE snapshot_path IS NOT NULL").fetchone()["n"]
        assert snaps > 0
    new_id = reevaluate([hist[1]["id"]], db_path=tmp_db)[0]  # sem rede: só snapshots
    with repo.connect(tmp_db) as db:
        after = {r["criterion_id"]: r["status"] for r in repo.results(db, new_id, False)}
        a = repo.assessment(db, new_id, False)
    assert after == before
    assert a["kind"] == "reprocessamento" and a["source_assessment_id"] == hist[1]["id"]


def test_one_failing_entity_does_not_stop_the_run(tmp_db):
    good = build_portal("ok", 3, date.today())
    run(entities=[entity("ok"), entity("fora")], fetcher_factory=lambda: FixtureFetcher(good),
        db_path=tmp_db, probes=False)
    with repo.connect(tmp_db) as db:
        rows = {e["slug"]: e for e in repo.entities(db)}
    assert rows["ok"]["score"] == 100.0
    assert rows["fora"]["score"] is None and rows["fora"]["collection_status"] == "falhou"
