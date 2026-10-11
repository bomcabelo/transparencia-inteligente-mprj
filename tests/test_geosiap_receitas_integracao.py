import json
import pytest
from src.geosiap_receitas_integracao import converter_resumo_receitas, importar_receitas
from src.geosiap_storage import get_evidence, list_evidences


def exemplo():
    return {
      'plataforma':'GeoSIAP', 'municipio':'Japeri/RJ',
      'endpoint':'/execucao/receitas/proprias/receitas_proprias',
      'parametros':{'id_entidade':'10','ano':'2025','layout':'anual'},
      'consultado_em_utc':'2026-10-11T16:58:09+00:00',
      'sha256_resposta':'a'*64, 'http_status':200,
      'resultado_tecnico':'consulta_realizada', 'quantidade_registros':169,
      'campos_observados':['nivel','cd_plano_conta_rel','ds_plano_conta',
                           'vl_previsto','vl_atualizado','vl_total'],
      'url_consultada':'https://japeri.geosiap.net.br/portal-transparencia/api/execucao/receitas/proprias/receitas_proprias?id_entidade=10&ano=2025&layout=anual',
    }


def test_conversao_e_status():
    r=converter_resumo_receitas(exemplo())
    assert r['criterion']=='3.1' and r['assessment_status']=='evidencia_parcial'
    assert r['legal_assessment_status']=='inconclusivo'
    assert r['record_count']==169


def test_ausencia_campo_deixa_inconclusivo():
    obj=exemplo();obj['campos_observados'].remove('vl_total')
    assert converter_resumo_receitas(obj)['assessment_status']=='inconclusivo'


def test_idempotencia_e_privacidade(tmp_path):
    db=tmp_path/'teste.sqlite3'; entrada=tmp_path/'resumo.json'
    obj=exemplo();obj['nome_razao']='NÃO PERSISTIR';entrada.write_text(json.dumps(obj),encoding='utf-8')
    n,created=importar_receitas(entrada,db)
    n2,created2=importar_receitas(entrada,db)
    assert created and not created2 and n==n2
    assert len(list_evidences(db))==1
    salvo=get_evidence(n,db)
    assert salvo['criterion']=='3.1' and 'nome_razao' not in salvo
    assert len(salvo['fields_observed'])==6


def test_layout_inesperado():
    x=exemplo();x['parametros']['layout']='periodo'
    with pytest.raises(ValueError): converter_resumo_receitas(x)
