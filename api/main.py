"""API inicial do desafio MPRJ.

A API é funcional, mas ainda não contém avaliações: respostas vazias são
intencionais até implementar a coleta e a persistência.
"""
from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="Transparência Inteligente — MPRJ",
    version="0.1.0",
    description="API inicial de monitoramento de portais públicos; nenhuma avaliação executada.",
)

ENTITIES: list[dict] = []


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "bootstrap", "evaluations_executed": 0}


@app.get("/entities")
def list_entities() -> list[dict]:
    return ENTITIES


@app.get("/entities/{entity_id}")
def get_entity(entity_id: int) -> dict:
    entity = next((e for e in ENTITIES if e.get("id") == entity_id), None)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entidade não cadastrada")
    return entity


@app.get("/entities/{entity_id}/evaluations/latest")
def latest_evaluation(entity_id: int) -> dict:
    raise HTTPException(status_code=404, detail="Nenhuma avaliação disponível")


@app.get("/entities/{entity_id}/evaluations/history")
def evaluation_history(entity_id: int) -> list[dict]:
    raise HTTPException(status_code=404, detail="Nenhuma avaliação disponível")


@app.get("/entities/{entity_id}/criteria")
def entity_criteria(entity_id: int) -> list[dict]:
    raise HTTPException(status_code=404, detail="Critérios ainda não cadastrados")
