"""Catálogo de critérios a partir do checklistPortalTransp.xlsx.

O checklist é tratado como DADO versionado, não como código: a planilha original
fica em config/fonte/ e este módulo gera config/checklist.json, que é a fonte única
para aplicabilidade, classificação (essencial/obrigatória/recomendada) e peso.

Uso: python -m src.checklist --xlsx config/fonte/checklistPortalTransp.xlsx
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XLSX_DEFAULT = ROOT / "config" / "fonte" / "checklistPortalTransp.xlsx"
CATALOG = ROOT / "config" / "checklist.json"
METHODOLOGY = ROOT / "config" / "metodologia.json"

# Tipos de entidade suportados. A matriz comum vale para todos; matrizes
# específicas restringem a aplicabilidade.
ENTITY_TYPES = (
    "executivo_municipal", "executivo_estadual",
    "legislativo_municipal", "legislativo_estadual",
    "judiciario", "ministerio_publico", "tribunal_de_contas", "defensoria",
    "autarquia_fundacao", "empresa_estatal", "consorcio_publico",
)
EXECUTIVO = ["executivo_municipal", "executivo_estadual"]

SECTION_MARKERS = {
    "MATRIZ COMUM": ("comum", "INFORMAÇÕES PRIORITÁRIAS"),
    "TRANSPARÊNCIA ATIVA": (None, "TRANSPARÊNCIA ATIVA"),
    "TRANSPARÊNCIA PASSIVA": (None, "TRANSPARÊNCIA PASSIVA"),
    "BOAS PRÁTICAS": (None, "BOAS PRÁTICAS"),
    "MATRIZ ESPECÍFICA: PODER EXECUTIVO": ("poder_executivo", "MATRIZ ESPECÍFICA — PODER EXECUTIVO"),
}

# Classificação proposta (inspirada na lógica essencial/obrigatória/recomendada do
# PNTP/Atricon). Ajustável em config/metodologia.json sem alterar código.
ESSENCIAIS = {
    "1.1", "1.2", "1.3", "3.1", "3.2", "4.1", "4.3", "5.1", "5.6", "7.1", "7.2",
    "8.1", "8.2", "12.1", "15.1", "19.1", "19.3", "19.5", "20.1",
}
# Critérios que podem ser legitimamente inexistentes (ex.: não há obras paralisadas).
# Só viram "nao_aplicavel" com declaração negativa encontrada no portal — nunca por omissão.
PODE_SER_INEXISTENTE = re.compile(
    r"^(3\.(8|9|10|11|12)|4\.(8|9|10|11|12|13)|11\.4|13\.\d+|15\.(6|7))$"
)


def _clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_xlsx(path: Path) -> list[dict]:
    from openpyxl import load_workbook

    ws = load_workbook(path, read_only=True, data_only=True)["Quesitos"]
    matriz, secao = "comum", "INFORMAÇÕES PRIORITÁRIAS"
    grupo_id = grupo_nome = None
    fundamentacao_atual = ""
    items: list[dict] = []
    for row in ws.iter_rows(values_only=True):
        item, criterio, fund = (_clean(c) for c in (list(row) + [None] * 3)[:3])
        if not item and not criterio:
            continue
        upper = item.upper()
        if upper in SECTION_MARKERS:
            novo_matriz, nova_secao = SECTION_MARKERS[upper]
            matriz = novo_matriz or matriz
            secao = nova_secao
            continue
        if upper == "ITEM":
            continue
        if re.fullmatch(r"\d+\.", item):
            grupo_id, grupo_nome = item.rstrip("."), criterio
            fundamentacao_atual = ""
            if grupo_nome.upper() == "BOAS PRÁTICAS":
                secao = "BOAS PRÁTICAS"
            continue
        if not re.fullmatch(r"\d+\.\d+", item):
            continue
        # Células de fundamentação mescladas: herdar a última do grupo.
        if fund:
            fundamentacao_atual = fund
        aplicavel = list(ENTITY_TYPES) if matriz == "comum" else list(EXECUTIVO)
        if "(Executivo Municipal)" in criterio:
            aplicavel = ["executivo_municipal"]
        classificacao = ("essencial" if item in ESSENCIAIS else
                         "recomendada" if secao == "BOAS PRÁTICAS" else "obrigatoria")
        items.append({
            "id": item,
            "grupo_id": grupo_id,
            "grupo": grupo_nome,
            "secao": secao,
            "matriz": matriz,
            "descricao": criterio,
            "fundamentacao": fundamentacao_atual,
            "fundamentacao_herdada": not bool(fund),
            "classificacao": classificacao,
            "aplicavel_a": aplicavel,
            "pode_ser_inexistente": bool(PODE_SER_INEXISTENTE.match(item)),
        })
    return items


def build_catalog(xlsx: Path = XLSX_DEFAULT, output: Path = CATALOG) -> dict:
    raw = xlsx.read_bytes()
    catalog = {
        "versao": "checklist-" + hashlib.sha256(raw).hexdigest()[:12],
        "fonte": xlsx.name,
        "fonte_sha256": hashlib.sha256(raw).hexdigest(),
        "criterios": parse_xlsx(xlsx),
    }
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog


@lru_cache(maxsize=4)
def load_catalog(path: str | None = None) -> dict:
    catalog = json.loads(Path(path or CATALOG).read_text(encoding="utf-8"))
    catalog["por_id"] = {c["id"]: c for c in catalog["criterios"]}
    return catalog


@lru_cache(maxsize=4)
def load_methodology(path: str | None = None) -> dict:
    return json.loads(Path(path or METHODOLOGY).read_text(encoding="utf-8"))


def weight(criterion: dict, methodology: dict | None = None) -> float:
    m = methodology or load_methodology()
    override = m.get("pesos_por_criterio", {}).get(criterion["id"])
    return float(override if override is not None else m["pesos_por_classificacao"][criterion["classificacao"]])


def applicable(criterion: dict, entity_type: str) -> bool:
    return entity_type in criterion["aplicavel_a"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera config/checklist.json a partir da planilha")
    parser.add_argument("--xlsx", type=Path, default=XLSX_DEFAULT)
    parser.add_argument("--output", type=Path, default=CATALOG)
    args = parser.parse_args()
    catalog = build_catalog(args.xlsx, args.output)
    crits = catalog["criterios"]
    print(f"Critérios importados: {len(crits)} | versão {catalog['versao']}")
    for key in ("matriz", "classificacao"):
        counts: dict[str, int] = {}
        for c in crits:
            counts[c[key]] = counts.get(c[key], 0) + 1
        print(f"  por {key}: {counts}")


if __name__ == "__main__":
    main()
