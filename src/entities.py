"""Cadastro de entidades e inferência do tipo de entidade.

O tipo determina a matriz aplicável do checklist. Quando o cadastro não informa o
tipo, ele é inferido por regras explícitas (domínio e nome) com grau de confiança;
inferências com baixa confiança são sinalizadas para confirmação humana.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from src.checklist import ENTITY_TYPES

ROOT = Path(__file__).resolve().parents[1]
ENTITIES_FILE = ROOT / "config" / "municipios.json"

_TYPE_RULES = [
    # (regex sobre nome+domínio normalizado, tipo, confiança)
    (r"\bcamara\b|\.leg\.br|camaramunicipal|\bcm[a-z]+\.rj", "legislativo_municipal", 0.85),
    (r"\balerj\b|assembleia legislativa", "legislativo_estadual", 0.9),
    (r"\btribunal de contas\b|\btce\b|\btcm\b", "tribunal_de_contas", 0.9),
    (r"\bministerio publico\b|\bmp[a-z]{2}\.mp\.br|\.mp\.br", "ministerio_publico", 0.9),
    (r"\bdefensoria\b|\.def\.br", "defensoria", 0.9),
    (r"\btribunal de justica\b|\.jus\.br", "judiciario", 0.85),
    (r"\bconsorcio\b", "consorcio_publico", 0.7),
    (r"\b(instituto|fundacao|autarquia|previdencia)\b", "autarquia_fundacao", 0.6),
    (r"\b(companhia|empresa)\b", "empresa_estatal", 0.6),
    (r"\bprefeitura\b|\bmunicipio de\b|\.rj\.gov\.br|prefeitura\.", "executivo_municipal", 0.8),
    (r"\bgoverno do estado\b|\.rj\.gov\.br$", "executivo_estadual", 0.5),
]


def _norm(value: str) -> str:
    raw = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in raw if not unicodedata.combining(c)).casefold()


def infer_entity_type(name: str, url: str | None = None) -> tuple[str | None, float, str]:
    """Retorna (tipo, confiança, regra). Ordem das regras: do mais específico ao genérico."""
    host = urlsplit(url or "").hostname or ""
    text = f"{_norm(name)} {host}"
    for pattern, kind, confidence in _TYPE_RULES:
        if re.search(pattern, text):
            return kind, confidence, pattern
    return None, 0.0, "nenhuma regra"


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(value)).strip("-")


def normalize_entity(raw: dict) -> dict:
    entity = dict(raw)
    entity.setdefault("id", slugify(raw["nome"]))
    entity.setdefault("entidade", raw["nome"])
    entity.setdefault("municipio", raw["nome"])
    entity.setdefault("uf", "RJ")
    entity.setdefault("ativo", True)
    if not entity.get("tipo"):
        kind, conf, rule = infer_entity_type(entity["entidade"], entity.get("site"))
        entity["tipo"] = kind
        entity["tipo_inferido"] = {"confianca": conf, "regra": rule,
                                   "requer_confirmacao": conf < 0.8}
    if entity["tipo"] and entity["tipo"] not in ENTITY_TYPES:
        raise ValueError(f"Tipo de entidade desconhecido: {entity['tipo']}")
    return entity


def load_entities(path: Path | str = ENTITIES_FILE, only_active: bool = True) -> list[dict]:
    rows = [normalize_entity(r) for r in json.loads(Path(path).read_text(encoding="utf-8"))]
    return [r for r in rows if r["ativo"] or not only_active]
