from decimal import Decimal
from src.adapters.geosiap import parse_brl, summarize


def test_parse_brl():
    assert parse_brl("R$ 4.800,00") == Decimal("4800.00")
    assert parse_brl("R$ 0,00") == Decimal("0.00")
    assert parse_brl("R$ -1.234,56") == Decimal("-1234.56")
    assert parse_brl("não informado") is None


def test_summarize_minimal():
    sample = {"empenhos": [{
        "id_empenho": "22503", "nr_empenho": "390", "ano_empenho": "2025",
        "vl_empenhado_per": "R$ 4.800,00", "vl_empenhado_acu": "R$ 4.800,00",
        "vl_liquidado_per": "R$ 4.800,00", "vl_liquidado_acu": "R$ 4.800,00",
        "vl_pago_per": "R$ 4.800,00", "vl_pago_acu": "R$ 4.800,00",
    }]}
    result = summarize(sample, source_sha256="abc")
    assert result["record_count"] == 1
    assert result["assessment_status"] == "evidencia_parcial"
    assert result["monetary_parseable_fields"]["vl_pago_per"] == 1
    assert "nome_razao" not in result


def test_empty_remains_inconclusive():
    assert summarize({"empenhos": []}, source_sha256="abc")["assessment_status"] == "inconclusivo"


def test_missing_marker_not_invalid():
    sample = {"empenhos": [{
        "id_empenho": "22503", "nr_empenho": "390", "ano_empenho": "2025",
        "vl_empenhado_per": "R$ 100,00", "vl_empenhado_acu": "R$ 100,00",
        "vl_liquidado_per": "-", "vl_liquidado_acu": "-",
        "vl_pago_per": "-", "vl_pago_acu": "-",
    }, {
        "id_empenho": "22504", "nr_empenho": "391", "ano_empenho": "2025",
        "vl_empenhado_per": "R$ 200,00", "vl_empenhado_acu": "R$ 200,00",
        "vl_liquidado_per": "R$ 0,00", "vl_liquidado_acu": "R$ 0,00",
        "vl_pago_per": "R$ 10,00", "vl_pago_acu": "R$ 10,00",
    }]}
    result = summarize(sample, source_sha256="abc")
    assert result["monetary_missing_counts"]["vl_pago_per"] == 1
    assert result["monetary_invalid_counts"]["vl_pago_per"] == 0
    assert result["monetary_zero_counts"]["vl_liquidado_per"] == 1
    assert result["assessment_status"] == "evidencia_parcial"


def test_unexpected_string_is_invalid_not_missing():
    sample = {"empenhos": [{
        "id_empenho": "1", "nr_empenho": "1", "ano_empenho": "2025",
        "vl_empenhado_per": "R$ 1,00", "vl_empenhado_acu": "R$ 1,00",
        "vl_liquidado_per": "indefinido", "vl_liquidado_acu": "R$ 1,00",
        "vl_pago_per": "R$ 1,00", "vl_pago_acu": "R$ 1,00",
    }]}
    result = summarize(sample, source_sha256="abc")
    assert result["monetary_invalid_counts"]["vl_liquidado_per"] == 1
    assert result["monetary_missing_counts"]["vl_liquidado_per"] == 0
    assert result["assessment_status"] == "inconclusivo"


def test_parse_missing_values():
    from src.adapters.geosiap import is_missing_money
    assert is_missing_money("-")
    assert is_missing_money("  ")
    assert is_missing_money(None)
    assert not is_missing_money("R$ 0,00")
    assert not is_missing_money("erro")
