from src.checklist import ENTITY_TYPES, applicable, build_catalog, load_catalog, weight
from src.entities import infer_entity_type, load_entities


def test_catalog_reproduces_spreadsheet(tmp_path):
    catalog = build_catalog(output=tmp_path / "c.json")
    ids = [c["id"] for c in catalog["criterios"]]
    assert len(ids) == len(set(ids)) == 142
    assert catalog["versao"] == load_catalog()["versao"]  # o JSON versionado corresponde à planilha


def test_merged_legal_basis_is_inherited():
    c = load_catalog()["por_id"]
    assert c["2.2"]["fundamentacao"] == c["2.1"]["fundamentacao"]
    assert c["2.2"]["fundamentacao_herdada"] is True


def test_applicability_by_entity_type():
    c = load_catalog()["por_id"]
    assert applicable(c["1.1"], "legislativo_municipal")
    assert not applicable(c["19.5"], "legislativo_municipal")     # LOA: matriz do Executivo
    assert applicable(c["19.5"], "executivo_municipal")
    assert c["21.1"]["aplicavel_a"] == ["executivo_municipal"]   # "(Executivo Municipal)" no texto
    assert set(c["1.1"]["aplicavel_a"]) == set(ENTITY_TYPES)


def test_weights_follow_classification():
    c = load_catalog()["por_id"]
    assert weight(c["4.1"]) > weight(c["4.5"]) > weight(c["18.1"])  # essencial > obrigatória > recomendada


def test_entity_type_inference():
    assert infer_entity_type("Câmara Municipal de Japeri", "https://www.camarajaperi.rj.gov.br")[0] == \
        "legislativo_municipal"
    assert infer_entity_type("Prefeitura de Itaboraí", None)[0] == "executivo_municipal"
    assert all(e["tipo"] == "executivo_municipal" for e in load_entities())
