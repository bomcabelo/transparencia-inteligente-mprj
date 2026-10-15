"""Motor de avaliação: aplica o catálogo inteiro a uma coleta.

Para cada critério do checklist, decide entre:
- `nao_aplicavel`  -> critério não pertence à matriz do tipo da entidade (não penaliza);
- `nao_avaliado`   -> aplicável, mas ainda sem regra automatizada (entra na cobertura, não no score);
- resultado da regra -> com evidências e confiança; abaixo da confiança mínima vira `inconclusivo`.
"""
from __future__ import annotations

import traceback
from datetime import date

from src.checklist import applicable, load_catalog, load_methodology
from src.collector import Collection
from src.rules import criterios  # noqa: F401  (registra as regras)
from src.rules.base import REGISTRY, Context, Result


def evaluate(entity: dict, collection: Collection, *, catalog: dict | None = None,
             methodology: dict | None = None, llm=None, extra_evidence: dict | None = None,
             today: date | None = None) -> list[Result]:
    catalog = catalog or load_catalog()
    methodology = methodology or load_methodology()
    # Data de referência = data da coleta: reprocessar no futuro produz o mesmo resultado.
    ref = today or date.fromisoformat((collection.finished_at or collection.started_at)[:10])
    ctx = Context(entity=entity, collection=collection, today=ref, methodology=methodology, llm=llm,
                  extra_evidence=extra_evidence or {})
    kind = entity.get("tipo")
    out: list[Result] = []
    for crit in catalog["criterios"]:
        cid = crit["id"]
        meta = REGISTRY.get(cid)
        if kind is None and crit["matriz"] != "comum":
            out.append(Result(cid, "nao_avaliado", 0.0, "Tipo de entidade não confirmado: matriz específica "
                              "não avaliada.", needs_review=True))
            continue
        if kind is not None and not applicable(crit, kind):
            out.append(Result(cid, "nao_aplicavel", 1.0, f"Critério da matriz '{crit['matriz']}' não se aplica "
                              f"a entidades do tipo '{kind}'."))
            continue
        if meta is None:
            out.append(Result(cid, "nao_avaliado", 0.0, "Critério sem regra automatizada nesta versão."))
            continue
        try:
            result = meta["func"](ctx)
        except Exception as exc:  # uma regra com defeito não derruba a avaliação inteira
            result = Result(cid, "inconclusivo", 0.0, f"Erro interno na regra: {type(exc).__name__}: {exc}",
                            needs_review=True)
            result.ai = {"traceback": traceback.format_exc(limit=3)}
        result.rule_version = f"{cid}@{meta['versao']}"
        if result.status in ("atende", "parcial", "nao_atende") and result.confidence < methodology["confianca_minima"]:
            result.finding = (f"[confiança {result.confidence:.0%} abaixo do mínimo; era '{result.status}'] "
                              + result.finding)
            result.status, result.needs_review = "inconclusivo", True
        out.append(result)
    return out
