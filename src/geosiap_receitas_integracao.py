"""Converte o resumo técnico de receitas em evidência GeoSIAP persistível.

Não armazena registros individuais, não soma linhas agregadas e não conclui conformidade legal.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from src.geosiap_storage import import_summary

EXPECTED_ENDPOINT = '/execucao/receitas/proprias/receitas_proprias'
FIELDS_ESSENCIAIS = {'nivel', 'cd_plano_conta_rel', 'ds_plano_conta', 'vl_previsto', 'vl_atualizado', 'vl_total'}


def converter_resumo_receitas(origem: dict) -> dict:
    if not isinstance(origem, dict):
        raise ValueError('Resumo de receitas deve ser um objeto JSON')
    if origem.get('plataforma') != 'GeoSIAP' or origem.get('endpoint') != EXPECTED_ENDPOINT:
        raise ValueError('Resumo não corresponde ao endpoint de receitas próprias GeoSIAP')
    params = origem.get('parametros')
    if not isinstance(params, dict) or params.get('layout') != 'anual':
        raise ValueError('Esta integração exige layout anual')
    try:
        id_entidade = int(params['id_entidade'])
        ano = int(params['ano'])
        quantidade = int(origem['quantidade_registros'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Identificador, ano ou quantidade de registros inválidos') from exc
    if id_entidade < 1 or not 1900 <= ano <= 2100 or quantidade < 0:
        raise ValueError('Parâmetros ou quantidade fora do intervalo permitido')
    campos = origem.get('campos_observados')
    if not isinstance(campos, list) or not all(isinstance(c, str) for c in campos):
        raise ValueError('Lista de campos observados inválida')
    sha = origem.get('sha256_resposta')
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdefABCDEF' for c in sha):
        raise ValueError('SHA-256 ausente ou inválido')
    if origem.get('municipio') != 'Japeri/RJ':
        raise ValueError('Município não reconhecido por este adaptador')
    if not origem.get('consultado_em_utc'):
        raise ValueError('Data de consulta ausente')
    presentes = sorted(set(campos) & FIELDS_ESSENCIAIS)
    ausentes = sorted(FIELDS_ESSENCIAIS - set(campos))
    sucesso = origem.get('http_status') == 200 and origem.get('resultado_tecnico') == 'consulta_realizada'
    parcial = sucesso and quantidade > 0 and not ausentes
    return {
        'platform': 'GeoSIAP',
        'municipality': 'Japeri/RJ',
        'entity_id': id_entidade,
        'year_requested': ano,
        'endpoint': EXPECTED_ENDPOINT,
        'request_parameters': {'id_entidade': id_entidade, 'ano': ano, 'layout': 'anual'},
        'processed_at_utc': origem['consultado_em_utc'],
        'source_sha256': sha.lower(),
        'record_count': quantidade,
        'criterion': '3.1',
        'assessment_status': 'evidencia_parcial' if parcial else 'inconclusivo',
        'assessment_reason': ('Foram encontrados registros e campos de classificação, previsão e arrecadação; '
                              'não há verificação do preenchimento por registro, abrangência, atualidade '
                              'ou conformidade legal.' if parcial else
                              'A consulta ou a estrutura disponível não foi suficiente para confirmar a evidência técnica parcial.'),
        'fields_observed': sorted(set(campos)),
        'essential_fields_present': presentes,
        'essential_fields_missing': ausentes,
        'http_status': origem.get('http_status'),
        'source_url': origem.get('url_consultada') or origem.get('origem'),
        'legal_assessment_status': 'inconclusivo',
        'limitations': [
            'Somente receitas próprias da entidade e do exercício informados.',
            'Campos presentes não significam valores preenchidos ou contabilmente consistentes.',
            'O resumo não inclui registros individuais: não calcular totais ou inferir integralidade.',
            'Linhas podem ter níveis de agregação diferentes; não somar sem identificar hierarquia.',
        ],
    }


def importar_receitas(caminho: str | Path, db_path: str | Path | None = None):
    origem = json.loads(Path(caminho).read_text(encoding='utf-8-sig'))
    resumo = converter_resumo_receitas(origem)
    # A função existente espera um caminho JSON; arquivo temporário em diretório seguro.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='mprj_receitas_') as pasta:
        arquivo = Path(pasta) / 'resumo.json'
        arquivo.write_text(json.dumps(resumo, ensure_ascii=False), encoding='utf-8')
        return import_summary(arquivo, db_path)


def main():
    parser = argparse.ArgumentParser(description='Importa resumo técnico de receitas próprias no SQLite')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--db', type=Path, default=None)
    args = parser.parse_args()
    codigo, novo = importar_receitas(args.source, args.db)
    print('Evidência:', codigo)
    print('Situação:', 'importada' if novo else 'já existente (sem duplicação)')


if __name__ == '__main__':
    main()
