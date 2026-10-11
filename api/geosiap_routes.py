"""Rotas de leitura das evidências estruturadas GeoSIAP."""
from fastapi import APIRouter, HTTPException
from src.geosiap_storage import list_evidences, get_evidence

router = APIRouter(prefix='/geosiap', tags=['GeoSIAP'])

@router.get('/evidences')
def evidences() -> list[dict]:
    return list_evidences()

@router.get('/evidences/{evidence_id}')
def evidence(evidence_id: int) -> dict:
    result = get_evidence(evidence_id)
    if result is None:
        raise HTTPException(status_code=404, detail='Evidência não encontrada')
    return result
