"""Orquestração: coleta -> sondas -> avaliação -> score -> persistência.

Exemplos:
  python -m src.pipeline run                       # todas as entidades ativas
  python -m src.pipeline run --entity japeri --entity rio-de-janeiro --workers 4
  python -m src.pipeline reevaluate --latest       # reaplica regras atuais às últimas coletas (sem rede)
  python -m src.pipeline reevaluate --assessment 12

Cada entidade é processada isoladamente: erro em uma não interrompe as outras.
A coleta roda em paralelo (threads, I/O bound); a escrita no banco é serial.
"""
from __future__ import annotations

import argparse
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from src import repository as repo
from src.ai.llm import LLMJudge
from src.checklist import load_catalog, load_methodology
from src.collector import Collection, collect
from src.engine import evaluate
from src.entities import load_entities
from src.fetch import Fetcher, HttpFetcher, utc_now
from src.rules.base import REGISTRY
from src.scoring import compute

log = logging.getLogger("pipeline")


def make_fetcher(methodology: dict) -> Fetcher:
    c = methodology["coleta"]
    base = HttpFetcher(delay=c["intervalo_segundos"], timeout=c["timeout_segundos"], max_bytes=c["max_bytes"],
                       retries=c["tentativas"], respect_robots=c["respeitar_robots"])
    if os.environ.get("MPRJ_RENDER_JS") == "1":
        try:
            from src.fetch import PlaywrightFetcher
            return PlaywrightFetcher(base, screenshot_dir=str(repo.SNAPSHOTS / "_screenshots"))
        except Exception as exc:  # Playwright ausente: segue sem renderização, e as regras sabem disso
            log.warning("Renderização JS indisponível (%s); usando HTTP simples", exc)
    return base


def assess(entity: dict, fetcher: Fetcher, *, methodology: dict, catalog: dict, llm=None,
           probes: bool = True) -> tuple[Collection, list, dict, list]:
    c = methodology["coleta"]
    col = collect(entity, fetcher, max_pages=c["max_paginas"], max_depth=c["max_profundidade"],
                  abort_after=c["falhas_consecutivas_para_abortar"])
    extra, probe_log = {}, []
    if probes and (col.health["site_ok"] or col.health.get("portal_ok")):
        from src.adapters.probes import run_probes
        try:
            extra, probe_log = run_probes(entity, col.vendors, date.fromisoformat(col.finished_at[:10]))
        except Exception as exc:  # sonda é complemento: falha nela não impede a avaliação por HTML
            probe_log = [{"erro": f"{type(exc).__name__}: {exc}"}]
    results = evaluate(entity, col, catalog=catalog, methodology=methodology, llm=llm, extra_evidence=extra)
    return col, results, compute(results, catalog=catalog, methodology=methodology), probe_log


def run(entity_ids: list[str] | None = None, *, workers: int = 3, trigger: str = "manual",
        fetcher_factory=None, db_path=None, entities: list[dict] | None = None, probes: bool = True) -> int:
    methodology, catalog = load_methodology(), load_catalog()
    pool = entities if entities is not None else load_entities()
    if entity_ids:
        pool = [e for e in pool if e["id"] in set(entity_ids)]
    llm = LLMJudge.from_env()
    factory = fetcher_factory or (lambda: make_fetcher(methodology))
    with repo.connect(db_path) as db:
        repo.sync_catalog(db, catalog, REGISTRY)
        run_id = repo.start_run(db, trigger, methodology["versao"], catalog["versao"], utc_now())
        ids = {e["id"]: repo.upsert_entity(db, e) for e in pool}
    ok = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(assess, e, factory(), methodology=methodology, catalog=catalog, llm=llm,
                             probes=probes): e for e in pool}
        for fut in as_completed(futures):
            entity = futures[fut]
            try:
                col, results, score, probe_log = fut.result()
            except Exception as exc:
                log.exception("Falha ao avaliar %s: %s", entity["id"], exc)
                continue
            with repo.connect(db_path) as db:
                aid = repo.save_assessment(db, run_id=run_id, entity_id=ids[entity["id"]], entity_slug=entity["id"],
                                           collection=col, results=results, score=score, evaluated_at=utc_now(),
                                           probes=probe_log, llm_log=llm.log if llm else None)
            ok += col.health["site_ok"] or bool(col.health.get("portal_ok"))
            log.info("%-22s score=%s [%s–%s] cobertura=%.0f%% páginas=%d -> assessment %d", entity["nome"],
                     score["score"], *score["score_intervalo"], 100 * score["cobertura_avaliacao"],
                     col.health["paginas_ok"], aid)
    with repo.connect(db_path) as db:
        repo.finish_run(db, run_id, utc_now(), len(pool), ok)
    return run_id


def reevaluate(assessment_ids: list[int], db_path=None) -> list[int]:
    """Reaplica as regras ATUAIS a coletas antigas, a partir dos snapshots (sem rede)."""
    methodology, catalog = load_methodology(), load_catalog()
    created = []
    with repo.connect(db_path) as db:
        repo.sync_catalog(db, catalog, REGISTRY)
        run_id = repo.start_run(db, "reprocessamento", methodology["versao"], catalog["versao"], utc_now())
        for aid in assessment_ids:
            row = db.execute("""SELECT a.entity_id, a.probes_json, e.* FROM assessments a JOIN entities e
                                ON e.id=a.entity_id WHERE a.id=?""", (aid,)).fetchone()
            col = repo.load_collection(db, aid)
            entity = {"id": row["slug"], "nome": row["name"], "tipo": row["tipo"], "site": row["site"],
                      "portal": row["portal"]}
            results = evaluate(entity, col, catalog=catalog, methodology=methodology)
            score = compute(results, catalog=catalog, methodology=methodology)
            created.append(repo.save_assessment(
                db, run_id=run_id, entity_id=row["entity_id"], entity_slug=row["slug"], collection=col,
                results=results, score=score, evaluated_at=utc_now(), kind="reprocessamento",
                source_assessment_id=aid))
        repo.finish_run(db, run_id, utc_now(), len(assessment_ids), len(created))
    return created


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pipeline de avaliação de portais de transparência")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="coletar e avaliar")
    r.add_argument("--entity", action="append", help="id da entidade (repetível); padrão: todas ativas")
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--trigger", default="manual")
    r.add_argument("--no-probes", action="store_true", help="não consultar APIs de fornecedores")
    rv = sub.add_parser("reevaluate", help="reprocessar coletas armazenadas com as regras atuais")
    rv.add_argument("--assessment", type=int, action="append")
    rv.add_argument("--latest", action="store_true", help="última coleta de cada entidade")
    args = parser.parse_args()
    if args.cmd == "run":
        run_id = run(args.entity, workers=args.workers, trigger=args.trigger, probes=not args.no_probes)
        print(f"Execução {run_id} concluída. API: uvicorn api.main:app | painel: streamlit run app/dashboard.py")
    else:
        ids = list(args.assessment or [])
        if args.latest:
            with repo.connect() as db:
                ids += [r["id"] for r in db.execute(
                    "SELECT MAX(id) id FROM assessments WHERE kind='coleta' GROUP BY entity_id")]
        print("Reprocessados:", reevaluate(ids))


if __name__ == "__main__":
    main()
