"""API de evidências coletadas. Nenhuma pontuação legal é inferida de HTTP 200."""
from fastapi import FastAPI, HTTPException
from src import database

app = FastAPI(title="Transparência Inteligente — MPRJ", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "phase": "evidence_storage"}


@app.get("/entities")
def list_entities() -> list[dict]:
    with database.connect() as db:
        return database.entities(db)


@app.get("/entities/{entity_id}")
def get_entity(entity_id: int) -> dict:
    with database.connect() as db:
        value = database.entity(db, entity_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Entidade não cadastrada")
    return value


@app.get("/entities/{entity_id}/evaluations/latest")
def latest_evaluation(entity_id: int) -> dict:
    with database.connect() as db:
        if database.entity(db, entity_id) is None:
            raise HTTPException(status_code=404, detail="Entidade não cadastrada")
        value = database.latest(db, entity_id)
    if value is None:
        raise HTTPException(status_code=404, detail="Nenhuma avaliação disponível")
    return value


@app.get("/entities/{entity_id}/evaluations/history")
def evaluation_history(entity_id: int) -> list[dict]:
    with database.connect() as db:
        if database.entity(db, entity_id) is None:
            raise HTTPException(status_code=404, detail="Entidade não cadastrada")
        return database.history(db, entity_id)


@app.get("/entities/{entity_id}/criteria")
def entity_criteria(entity_id: int) -> list[dict]:
    with database.connect() as db:
        if database.entity(db, entity_id) is None:
            raise HTTPException(status_code=404, detail="Entidade não cadastrada")
        value = database.latest(db, entity_id)
    return value["criteria"] if value else []
