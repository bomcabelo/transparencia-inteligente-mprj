"""Apresentação de evidências GeoSIAP apenas para o município selecionado."""
from __future__ import annotations

import streamlit as st
from app.geosiap_filtro import normalizar_municipio, filtrar_evidencias_por_municipio

LABELS = {
    'vl_empenhado_per': 'Empenhado (período)',
    'vl_liquidado_per': 'Liquidado (período)',
    'vl_pago_per': 'Pago (período)',
}


def render_geosiap(get, municipio_selecionado: dict) -> None:
    st.subheader('GeoSIAP — Evidências estruturadas')
    st.caption('Disponibilidade técnica de dados ≠ conformidade legal. Sem pontuação automática.')
    try:
        todas = get('/geosiap/evidences')
    except Exception as exc:
        st.warning(f'Não foi possível consultar as evidências GeoSIAP: {exc}')
        return

    evidencias = filtrar_evidencias_por_municipio(todas, municipio_selecionado)
    if not evidencias:
        st.info(f"Nenhuma evidência GeoSIAP disponível para {municipio_selecionado.get('name','este município')}.")
        return

    escolhida = st.selectbox(
        'Evidência GeoSIAP', evidencias,
        format_func=lambda e: f"{e['municipality']} — entidade {e['entity_id']} — {e['year_requested']} — #{e['id']}",
        key=f"geosiap_evidencia_municipio_{municipio_selecionado['id']}",
    )
    try:
        item = get(f"/geosiap/evidences/{escolhida['id']}")
    except Exception as exc:
        st.error(f'Falha ao carregar evidência: {exc}')
        return
    # Segunda verificação: não apresentar conteúdo de outra cidade se a API for inconsistente.
    if normalizar_municipio(item.get('municipality')) != normalizar_municipio(municipio_selecionado.get('name')):
        st.error('A evidência retornada não corresponde ao município selecionado.')
        return

    if item.get('criterion') == '3.1':
        from app.geosiap_receitas_painel import mostrar_receitas
        mostrar_receitas(item)
        return

    a, b, c = st.columns(3)
    a.metric('Registros analisados', item.get('record_count', 0))
    b.metric('Critério', item.get('criterion', '—'))
    c.metric('Evidência técnica', item.get('assessment_status', 'inconclusivo').replace('_', ' ').capitalize())
    st.warning('Parecer de conformidade legal: inconclusivo — requer validação adicional.')
    linhas = []
    for campo, rotulo in LABELS.items():
        linhas.append({
            'Campo': rotulo,
            'Interpretáveis': item.get('monetary_parseable_fields', {}).get(campo, 0),
            'Ausentes': item.get('monetary_missing_counts', {}).get(campo, 0),
            'Zeros': item.get('monetary_zero_counts', {}).get(campo, 0),
            'Formatos inválidos': item.get('monetary_invalid_counts', {}).get(campo, 0),
        })
    st.dataframe(linhas, use_container_width=True, hide_index=True)
    st.write('Justificativa:', item.get('assessment_reason', 'Não informada'))
    with st.expander('Rastreabilidade e limitações'):
        st.write('Município da evidência:', item.get('municipality'))
        st.write('Entidade GeoSIAP:', item.get('entity_id'))
        st.write('Exercício consultado:', item.get('year_requested'))
        st.write('Data do processamento (UTC):', item.get('processed_at_utc'))
        st.write('Hash SHA-256 do JSON original:')
        st.code(item.get('source_sha256', ''), language=None)
        st.write('Endpoint consultado:', item.get('endpoint'))
        st.write('Parâmetros da consulta:')
        st.json(item.get('request_parameters', {}))
        st.caption('A data apresentada é de processamento, não uma comprovação da data de publicação no portal.')
        for limitacao in item.get('limitations', []):
            st.write('•', limitacao)
