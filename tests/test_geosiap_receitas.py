import json
import pytest
from src.adapters.geosiap_receitas import descrever, validar_parametros, parametros_cli, consultar, _contagem

DOC = {"paths": {"/execucao/receitas/proprias/receitas_proprias": {"get": {
    "summary": "Lista receitas próprias", "parameters": [
        {"name": "id_entidade", "in": "query", "required": True, "type": "integer"},
        {"name": "ano", "in": "query", "required": False, "type": "integer"}],
    "responses": {"200": {"schema": {"type": "object"}}}
}}}}


def test_descricao_extraida_do_swagger():
    d = descrever(DOC)
    assert d["parametros"][0]["nome"] == "id_entidade"
    assert d["respostas_documentadas"] == ["200"]


def test_parametro_obrigatorio_e_desconhecido():
    d = descrever(DOC)
    with pytest.raises(ValueError, match="obrigatórios"):
        validar_parametros(d, {"ano": "2025"})
    with pytest.raises(ValueError, match="não documentados"):
        validar_parametros(d, {"id_entidade": "10", "senha": "x"})
    validar_parametros(d, {"id_entidade": "10", "ano": "2025"})


def test_argumentos_cli():
    assert parametros_cli(["id_entidade=10", "ano=2025"]) == {"id_entidade": "10", "ano": "2025"}
    with pytest.raises(ValueError):
        parametros_cli(["id_entidade"])


def test_contagem_nao_expoe_valores():
    assert _contagem({"receitas": [{"valor": "R$ 10,00", "nome": "pessoa"}]}) == ("objeto com lista 'receitas'", 1, ["nome", "valor"])


class Resposta:
    def __init__(self, status, payload):
        self.status_code = status
        self.headers = {"Content-Type": "application/json"}
        self.url = "https://japeri.geosiap.net.br/portal-transparencia/api/execucao/receitas/proprias/receitas_proprias"
        self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def iter_content(self, chunk_size): yield json.dumps(self.payload).encode()


class Sessao:
    def __init__(self, status=200): self.status = status
    def get(self, url, **kwargs):
        assert kwargs["params"] == {"id_entidade": "10"}
        assert kwargs["stream"] is True
        return Resposta(self.status, {"receitas": [{"valor": "1", "credor": "Dado pessoal"}]})


def test_consulta_registra_metadados_sem_pessoa():
    saida = consultar(descrever(DOC), {"id_entidade": "10"}, session=Sessao())
    assert saida["quantidade_registros"] == 1
    assert saida["campos_observados"] == ["credor", "valor"]
    assert "Dado pessoal" not in json.dumps(saida)
    assert saida["status_avaliacao_legal"] == "inconclusivo"


def test_http_500_nao_e_falta_de_transparencia():
    saida = consultar(descrever(DOC), {"id_entidade": "10"}, session=Sessao(500))
    assert saida["resultado_tecnico"] == "falha_http"
    assert saida["status_avaliacao_legal"] == "inconclusivo"
