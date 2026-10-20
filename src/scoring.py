"""Metodologia de pontuação (detalhada em docs/DOCUMENTACAO_TECNICA.md §6).

score      = 100 × Σ(peso × valor) / Σ(peso)   sobre critérios aplicáveis e CONCLUSIVOS
intervalo  = [score se todo inconclusivo fosse 0 ; score se todo inconclusivo fosse 1]
cobertura  = peso conclusivo / peso avaliado  (quanto do que foi testado teve resposta)
checklist  = peso avaliado / peso aplicável   (quanto do checklist já é automatizado)

Valores: atende=1, parcial=0,5, não atende=0. `nao_aplicavel`, `inconclusivo` e
`nao_avaliado` ficam fora do denominador — assim não se penaliza a entidade por
requisito que não é seu nem por falha do robô; a incerteza aparece no intervalo e
na cobertura, em vez de ser escondida dentro do número.
"""
from __future__ import annotations

from src.checklist import load_catalog, load_methodology, weight
from src.rules.base import Result


def _bucket() -> dict:
    return {"num": 0.0, "den": 0.0, "atende": 0, "parcial": 0, "nao_atende": 0}


def compute(results: list[Result | dict], *, catalog: dict | None = None,
            methodology: dict | None = None) -> dict:
    """Calcula o score de uma avaliação a partir dos resultados por critério (§6 da documentação).

    - `nao_aplicavel` sai do cálculo; `nao_avaliado` entra só na cobertura do checklist.
    - `inconclusivo` não entra no score pontual, mas define o intervalo: mínimo (inconclusivos = 0)
      e máximo (inconclusivos = 1).
    - Score = média ponderada (atende 1, parcial 0,5, não atende 0; pesos por classificação).
    - Abaixo de `cobertura_minima_para_score` não há score pontual, só o intervalo.

    Args:
        results: resultados do motor (`Result` ou dicionários com `criterion_id` e `status`).
        catalog, methodology: padrão = arquivos em `config/`.

    Returns:
        Dicionário com score, intervalo, média simples, coberturas, `comparavel` (entra no ranking),
        classificação, essenciais pendentes, contagem por status, score por categoria e versões.
    """
    catalog = catalog or load_catalog()
    m = methodology or load_methodology()
    values = m["valor_por_status"]
    by_id = catalog["por_id"]
    rows = [r.to_dict() if isinstance(r, Result) else r for r in results]

    counts: dict[str, int] = {}
    num = den = evaluated_w = applicable_w = inconclusive_w = 0.0
    simple: list[float] = []
    groups: dict[str, dict] = {}
    essential_gaps: list[str] = []
    for r in rows:
        status = r["status"]
        counts[status] = counts.get(status, 0) + 1
        crit = by_id[r["criterion_id"]]
        w = weight(crit, m)
        if status == "nao_aplicavel":
            continue
        applicable_w += w
        if status == "nao_avaliado":
            continue
        evaluated_w += w
        if status == "inconclusivo":
            inconclusive_w += w
            continue
        v = values[status]
        num, den = num + w * v, den + w
        simple.append(v)
        g = groups.setdefault(f"{crit['grupo_id']}. {crit['grupo']}", _bucket())
        g["num"] += w * v
        g["den"] += w
        g[status] += 1
        if crit["classificacao"] == "essencial" and status != "atende":
            essential_gaps.append(r["criterion_id"])

    coverage = round(den / evaluated_w, 3) if evaluated_w else 0.0
    # Com pouca cobertura, a média de poucos critérios não representa a entidade:
    # publica-se o intervalo, mas não um score pontual (evita "100%" com 1 critério).
    insufficient = coverage < m.get("cobertura_minima_para_score", 0)
    score = round(100 * num / den, 1) if den and not insufficient else None
    lower = round(100 * num / evaluated_w, 1) if evaluated_w else None
    upper = round(100 * (num + inconclusive_w) / evaluated_w, 1) if evaluated_w else None
    categories = sorted(({"categoria": k, "score": round(100 * v["num"] / v["den"], 1),
                          "atende": v["atende"], "parcial": v["parcial"], "nao_atende": v["nao_atende"]}
                         for k, v in groups.items() if v["den"]), key=lambda c: -c["score"])
    return {
        "score": score,
        "score_intervalo": [lower, upper],
        "media_simples": round(100 * sum(simple) / len(simple), 1) if simple else None,
        "cobertura_avaliacao": coverage,
        "cobertura_checklist": round(evaluated_w / applicable_w, 3) if applicable_w else 0.0,
        "comparavel": coverage >= m["cobertura_minima_para_ranking"],
        "classificacao": "Cobertura insuficiente" if insufficient and den else classify(score, essential_gaps, m),
        "essenciais_pendentes": essential_gaps,
        "contagem": counts,
        "categorias": categories,
        "metodologia": m["versao"],
        "checklist": catalog["versao"],
    }


def classify(score: float | None, essential_gaps: list[str], m: dict) -> str:
    """Faixa de classificação do score (`metodologia.json`, `faixas`, em ordem decrescente).

    Uma faixa com `exige_essenciais` só é atribuída se nenhum critério essencial estiver pendente:
    um score alto com essencial pendente cai para a faixa seguinte.
    """
    if score is None:
        return "Sem avaliação conclusiva"
    for band in m["faixas"]:
        if score >= band["minimo"] and not (band["exige_essenciais"] and essential_gaps):
            return band["nome"]
    return m["faixas"][-1]["nome"]
