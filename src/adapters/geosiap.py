"""Adaptador GeoSIAP: avaliação técnica de campos de empenho sem expor credores.

Uso (a partir da raiz do repositório):
 python -m src.adapters.geosiap --source data/geosiap_japeri_empenhos_2025.json --output data/geosiap_japeri_resumo_2025.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = (
    "nr_empenho", "vl_empenhado_per", "vl_empenhado_acu",
    "vl_liquidado_per", "vl_liquidado_acu", "vl_pago_per", "vl_pago_acu",
)
MONEY_FIELDS = FIELDS[1:]
SOURCE_ENDPOINT = "/execucao/empenhos/empenhos"


def parse_brl(value: object) -> Decimal | None:
    """Converte valores monetários brasileiros, sem usar floats."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, Decimal)):
        return Decimal(str(value))
    if isinstance(value, float):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("R$", "").replace("\u00a0", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def is_missing_money(value: object) -> bool:
    """Marcadores de ausencia; nao presumir que representem zero."""
    return value is None or (isinstance(value, str) and value.strip() in ("", "-"))


def summarize(payload: dict, *, source_sha256: str, entity_id: int = 10, year: int = 2025) -> dict:
    items = payload.get("empenhos")
    if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
        raise ValueError("O JSON precisa conter 'empenhos' como lista de objetos")
    total = len(items)
    filled = {field: sum(x.get(field) is not None and str(x[field]).strip() != "" for x in items) for field in FIELDS}
    monetary_valid = {field: sum(parse_brl(x.get(field)) is not None for x in items) for field in MONEY_FIELDS}
    missing_money = {field: sum(is_missing_money(x.get(field)) for x in items) for field in MONEY_FIELDS}
    zero_counts = {field: sum(parse_brl(x.get(field)) == 0 for x in items) for field in MONEY_FIELDS}
    invalid_money = {field: total - monetary_valid[field] - missing_money[field] for field in MONEY_FIELDS}
    missing_id = sum(x.get("id_empenho") is None or str(x.get("id_empenho")).strip() == "" for x in items)
    years = dict(Counter(str(x.get("ano_empenho", "")) for x in items))
    # Nao somar campos de periodo e acumulado: podem representar a mesma quantia.
    # Checagem de >= 0 é apenas diagnostica: estornos podem gerar valores negativos legitimos.
    negatives = {field: sum((v := parse_brl(x.get(field))) is not None and v < 0 for x in items) for field in MONEY_FIELDS}
    return {
        "platform": "GeoSIAP",
        "municipality": "Japeri/RJ",
        "entity_id": entity_id,
        "year_requested": year,
        "endpoint": SOURCE_ENDPOINT,
        "request_parameters": {"id_entidade": entity_id, "ano": year},
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source_sha256,
        "record_count": total,
        "filled_fields": filled,
        "monetary_parseable_fields": monetary_valid,
        "monetary_zero_counts": zero_counts,
        "monetary_missing_counts": missing_money,
        "monetary_invalid_counts": invalid_money,
        "monetary_negative_counts": negatives,
        "records_without_id_empenho": missing_id,
        "years_observed": years,
        "criterion": "4.1",
        "assessment_status": (
            "evidencia_parcial"
            if (
                total > 0
                and filled["nr_empenho"] == total
                and missing_id == 0
                and years == {str(year): total}
                and all(monetary_valid[field] > 0 for field in MONEY_FIELDS)
            )
            else "inconclusivo"
        ),
        "assessment_reason": "Ha evidencia parcial de disponibilizacao de empenhos, liquidacoes e pagamentos para a entidade e o exercicio analisados; marcadores ausentes nao sao valores zero. Nao comprova cobertura integral, atualizacao nem conformidade legal.",
        "limitations": [
            "Amostra limitada a uma entidade e exercicio; nao extrapolar para todos os orgaos.",
            "Presenca de campo nao implica valor diferente de zero ou consistencia contabil.",
            "Sem prova de completude, periodicidade, correspondencia com portal e requisitos legais integrais.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera evidencias tecnicas GeoSIAP usando JSON local")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--entity-id", type=int, default=10)
    parser.add_argument("--year", type=int, default=2025)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    result = summarize(payload, source_sha256=hashlib.sha256(raw).hexdigest(), entity_id=args.entity_id, year=args.year)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Registros:", result["record_count"])
    print("Classificacao tecnica:", result["assessment_status"])
    print("Resumo salvo em:", args.output)


if __name__ == "__main__":
    main()
