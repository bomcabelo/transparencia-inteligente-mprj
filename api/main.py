"""API REST dos resultados de conformidade.

Somente leitura: a API publica o que o pipeline produziu; não dispara coletas (isso é
papel do agendador/fila), o que mantém a API barata e previsível sob carga.
Documentação interativa: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from statistics import mean

from fastapi import FastAPI, HTTPException, Query

from src import database as legacy
from src import repository as repo

app = FastAPI(title="Transparência Inteligente — MPRJ", version="1.0.0",
              description="Avaliação automatizada e contínua de portais de transparência. "
                          "Cada status é acompanhado de evidências verificáveis; 'inconclusivo' "
                          "significa que o robô não conseguiu decidir — nunca que a entidade falhou.")


def _entity_or_404(db, entity_id: int) -> dict:
    value = repo.entity(db, entity_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Entidade não cadastrada")
    return value


@app.get("/health", tags=["Sistema"])
def health() -> dict:
    """Verifica se a API está no ar: total de avaliações gravadas e data da última execução."""
    with repo.connect() as db:
        n = db.execute("SELECT COUNT(*) n FROM assessments").fetchone()["n"]
        last = db.execute("SELECT MAX(finished_at) t FROM runs").fetchone()["t"]
    return {"status": "ok", "evaluations_executed": n, "ultima_execucao": last}


@app.get("/overview", tags=["Visão geral"])
def overview() -> dict:
    """Indicadores agregados da última avaliação de cada entidade."""
    with repo.connect() as db:
        ents = repo.entities(db)
        latest = {e["id"]: repo.latest_id(db, e["id"]) for e in ents}
        details = {eid: repo.assessment(db, aid, with_evidence=False) for eid, aid in latest.items() if aid}
    scored = [e for e in ents if e["score"] is not None]
    ranked = sorted((e for e in scored if e["comparavel"]), key=lambda e: -e["score"])
    bins = {f"{lo}-{lo + 19 if lo < 80 else 100}": 0 for lo in range(0, 100, 20)}
    for e in scored:
        lo = min(int(e["score"] // 20) * 20, 80)
        bins[f"{lo}-{lo + 19 if lo < 80 else 100}"] += 1
    totals: dict[str, int] = {}
    for d in details.values():
        for k, v in (d["pontuacao"] or {}).get("contagem", {}).items():
            totals[k] = totals.get(k, 0) + v
    cats: dict[str, list[float]] = {}
    for d in details.values():
        for c in (d["pontuacao"] or {}).get("categorias", []):
            cats.setdefault(c["categoria"], []).append(c["score"])
    return {
        "entidades_cadastradas": len(ents),
        "entidades_avaliadas": len(details),
        "entidades_com_score": len(scored),
        "score_medio": round(mean(e["score"] for e in scored), 1) if scored else None,
        "melhor": ranked[0] if ranked else None,
        "pior": ranked[-1] if ranked else None,
        "ranking": [{"id": e["id"], "nome": e["name"], "score": e["score"], "classificacao": e["classificacao"],
                     "cobertura": e["cobertura_avaliacao"], "comparavel": bool(e["comparavel"])} for e in
                    sorted(scored, key=lambda e: -e["score"])],
        "distribuicao_scores": bins,
        "criterios_por_status": totals,
        "media_por_categoria": sorted(({"categoria": k, "score_medio": round(mean(v), 1), "entidades": len(v)}
                                       for k, v in cats.items()), key=lambda c: c["score_medio"]),
    }


@app.get("/entities", tags=["Entidades"])
def list_entities() -> list[dict]:
    """Entidades cadastradas, com o resultado da avaliação mais recente."""
    with repo.connect() as db:
        return repo.entities(db)


@app.get("/entities/{entity_id}", tags=["Entidades"])
def get_entity(entity_id: int) -> dict:
    """Cadastro de uma entidade."""
    with repo.connect() as db:
        value = _entity_or_404(db, entity_id)
        value["avaliacoes"] = len(repo.history(db, entity_id))
    return value


@app.get("/entities/{entity_id}/evaluations/latest", tags=["Avaliações"])
def latest_evaluation(entity_id: int, evidencias: bool = True) -> dict:
    """Avaliação mais recente da entidade, com critérios e (opcionalmente) evidências."""
    with repo.connect() as db:
        _entity_or_404(db, entity_id)
        aid = repo.latest_id(db, entity_id)
        if aid is None:
            raise HTTPException(status_code=404, detail="Nenhuma avaliação disponível")
        return repo.assessment(db, aid, with_evidence=evidencias)


@app.get("/entities/{entity_id}/evaluations/history", tags=["Avaliações"])
def evaluation_history(entity_id: int) -> list[dict]:
    """Série histórica (score, intervalo, cobertura e classificação por execução)."""
    with repo.connect() as db:
        _entity_or_404(db, entity_id)
        return repo.history(db, entity_id)


@app.get("/entities/{entity_id}/evaluations/diff", tags=["Avaliações"])
def evaluation_diff(entity_id: int, de: int | None = Query(None), para: int | None = Query(None)) -> dict:
    """O que melhorou, piorou ou segue pendente entre duas avaliações (padrão: as duas últimas coletas)."""
    with repo.connect() as db:
        _entity_or_404(db, entity_id)
        runs = [h["id"] for h in repo.history(db, entity_id) if h["kind"] == "coleta"]
        if de is None or para is None:
            if len(runs) < 2:
                raise HTTPException(status_code=404, detail="São necessárias duas avaliações para comparar")
            de, para = runs[-2], runs[-1]
        own = {h["id"] for h in repo.history(db, entity_id)}
        if de not in own or para not in own:
            raise HTTPException(status_code=404, detail="Avaliação não pertence à entidade")
        return repo.diff(db, de, para)


@app.get("/entities/{entity_id}/evaluations/{assessment_id}", tags=["Avaliações"])
def get_evaluation(entity_id: int, assessment_id: int) -> dict:
    """Uma avaliação específica da entidade, com critérios e evidências."""
    with repo.connect() as db:
        _entity_or_404(db, entity_id)
        value = repo.assessment(db, assessment_id)
    if value is None or value["entity_id"] != entity_id:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada")
    return value


@app.get("/entities/{entity_id}/criteria", tags=["Critérios"])
def entity_criteria(entity_id: int, status: str | None = None) -> list[dict]:
    """Situação atual de cada critério, com evidências e data desde quando é atendido."""
    with repo.connect() as db:
        _entity_or_404(db, entity_id)
        aid = repo.latest_id(db, entity_id)
        if aid is None:
            return []
        since = repo.first_compliance(db, entity_id)
        items = repo.results(db, aid)
    for item in items:
        item["atende_desde"] = since.get(item["criterion_id"])
    return [i for i in items if status is None or i["status"] == status]


@app.get("/entities/{entity_id}/criteria/{criterion_id}/history", tags=["Critérios"])
def criterion_history(entity_id: int, criterion_id: str) -> list[dict]:
    """Linha do tempo de um critério na entidade."""
    with repo.connect() as db:
        _entity_or_404(db, entity_id)
        return repo.criterion_history(db, entity_id, criterion_id)


@app.get("/criteria", tags=["Critérios"])
def catalog(implementado: bool | None = None) -> list[dict]:
    """Catálogo do checklist (versão vigente), com aplicabilidade e situação da automação."""
    with repo.connect() as db:
        items = repo.criteria(db)
    return [c for c in items if implementado is None or bool(c["implementado"]) == implementado]


@app.get("/runs", tags=["Sistema"])
def list_runs(limit: int = 50) -> list[dict]:
    """Execuções do pipeline, da mais recente para a mais antiga."""
    with repo.connect() as db:
        return repo.runs(db, limit)


@app.get("/legacy/entities/{entity_id}/collections", tags=["Etapas anteriores"])
def legacy_collections(entity_id: int) -> list[dict]:
    """Coletas exploratórias das etapas 3–6 (mantidas para rastreabilidade)."""
    with legacy.connect() as db:
        return legacy.history(db, entity_id)


# Integração GeoSIAP — Etapa 8
from api.geosiap_routes import router as geosiap_router  # noqa: E402

app.include_router(geosiap_router)
