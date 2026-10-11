from app.geosiap_filtro import filtrar_evidencias_por_municipio, normalizar_municipio


def test_normalizacao_nomes():
    assert normalizar_municipio('Japeri/RJ') == 'japeri'
    assert normalizar_municipio('Prefeitura Municipal de JAPERI') == 'japeri'
    assert normalizar_municipio('Itaboraí/RJ') == 'itaborai'


def test_apenas_evidencias_do_municipio():
    evidencias = [
        {'id': 1, 'municipality': 'Japeri/RJ'},
        {'id': 2, 'municipality': 'Itaboraí/RJ'},
        {'id': 3, 'municipality': 'Japeri/RJ'},
    ]
    assert [x['id'] for x in filtrar_evidencias_por_municipio(evidencias, {'name': 'Japeri'})] == [1, 3]
    assert filtrar_evidencias_por_municipio(evidencias, {'name': 'Cachoeiras de Macacu'}) == []


def test_uf_nao_gera_correspondencia_falsa():
    evidencias = [{'id': 1, 'municipality': 'Rio de Janeiro/RJ'}]
    assert filtrar_evidencias_por_municipio(evidencias, {'name': 'Japeri'}) == []
