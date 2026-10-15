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


def make_fetcher(methodology: dict, entity: dict | None = None) -> Fetcher:
    c = methodology["coleta"]
    base = HttpFetcher(delay=c["intervalo_segundos"], timeout=c["timeout_segundos"], max_bytes=c["max_bytes"],
                       retries=c["tentativas"], respect_robots=c["respeitar_robots"])
    if os.environ.get("MPRJ_RENDER_JS") == "1" or (entity or {}).get("render_js"):
        try:
            from src.fetch import PlaywrightFetcher
            return PlaywrightFetcher(base, screenshot_dir=str(repo.SNAPSHOTS / "_screenshots"))
        except Exception as exc:  # Playwright ausente: segue sem renderização, e as regras sabem disso
            log.warning("Renderização JS indisponível (%s); usando HTTP simples", exc)
    return base


def assess(entity: dict, fetcher: Fetcher, *, methodology: dict, catalog: dict, llm=None,
           probes: bool = True) -> tuple[Collection, list, dict, list]:
    c = methodology["coleta"]
    try:
        col = collect(entity, fetcher, max_pages=c["max_paginas"], max_depth=c["max_profundidade"],
                      abort_after=c["falhas_consecutivas_para_abortar"])
    finally:
        if hasattr(fetcher, "close"):  # fecha o navegador na mesma thread que o abriu
            fetcher.close()
    if getattr(fetcher, "rendered", 0):
        col.notes.append(f"{fetcher.rendered} página(s) renderizada(s) com JavaScript (Playwright).")
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
    def factory(entity: dict) -> Fetcher:
        return fetcher_factory() if fetcher_factory else make_fetcher(methodology, entity)
    with repo.connect(db_path) as db:
        repo.sync_catalog(db, catalog, REGISTRY)
        run_id = repo.start_run(db, trigger, methodology["versao"], catalog["versao"], utc_now())
        ids = {e["id"]: repo.upsert_entity(db, e) for e in pool}
    ok = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(assess, e, factory(e), methodology=methodology, catalog=catalog, llm=llm,
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


def diagnose(slug: str, db_path=None) -> None:
    """Mostra o que o robô viu na última coleta da entidade (para investigar coletas fracas)."""
    from src.collector import registrable_domain
    with repo.connect(db_path) as db:
        row = db.execute("""SELECT a.id FROM assessments a JOIN entities e ON e.id=a.entity_id
                            WHERE e.slug=? AND a.kind='coleta' ORDER BY a.collected_at DESC, a.id DESC LIMIT 1""",
                         (slug,)).fetchone()
        if row is None:
            print(f"Nenhuma coleta para '{slug}'.")
            return
        a = repo.assessment(db, row["id"], with_evidence=False)
        col = repo.load_collection(db, row["id"])
    h = a["saude_coleta"] or {}
    print(f"Avaliação {a['id']} — coleta {a['collected_at']} — situação: {a['collection_status']}")
    print(f"  site:   {a['site_url']}  (domínio aceito: {registrable_domain(a['site_url'])})")
    print(f"  portal: {a['portal_url']}  [{a['portal_source']}]  (domínio aceito: {registrable_domain(a['portal_url'])})")
    print(f"  páginas válidas: {h.get('paginas_ok')}  erros: {h.get('paginas_com_erro')}  "
          f"dinâmicas (JS): {h.get('paginas_dinamicas')}  fornecedor: {', '.join(a['vendors'] or {}) or '—'}")
    print(f"  temas encontrados: {', '.join(h.get('temas_cobertos') or []) or 'nenhum'}")
    for note in h.get("notas") or []:
        print(f"  NOTA: {note}")
    print(f"  score: {a['score']}  intervalo: [{a['score_min']}–{a['score_max']}]  cobertura: {a['cobertura_avaliacao']}")
    print("\n  Páginas coletadas:")
    for p in col.pages:
        themes = ", ".join(list(p.themes)[:3]) if p.themes else ""
        flag = " [JS?]" if p.status == 200 and p.looks_dynamic() else ""
        print(f"   {p.status or '—':>4} d{p.depth} {len(p.links):>4} links  {p.final_url[:80]}  {themes}{flag}"
              + (f"  ERRO={p.error}" if p.error else ""))
    home = col.page("site")
    if home and home.links:
        hosts: dict[str, int] = {}
        for link in home.links:
            host = (link["url"].split("/")[2] if "://" in link["url"] else "")
            hosts[host] = hosts.get(host, 0) + 1
        print("\n  Links da capa por domínio (os de fora do domínio aceito não são seguidos):")
        for host, n in sorted(hosts.items(), key=lambda kv: -kv[1])[:12]:
            print(f"   {n:>4}  {host}")
    if col.errors:
        print("\n  Erros:")
        for e in col.errors[:10]:
            print(f"   {e.get('status')}  {e.get('error')}  {e.get('url')}")


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
    dg = sub.add_parser("diagnostico", help="mostrar o que o robô viu na última coleta de uma entidade")
    dg.add_argument("--entity", required=True)
    args = parser.parse_args()
    if args.cmd == "diagnostico":
        diagnose(args.entity)
        return
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
