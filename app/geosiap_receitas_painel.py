"""Painel específico para evidência técnica de receitas próprias (critério 3.1)."""
import streamlit as st


def mostrar_receitas(item: dict) -> None:
    a, b, c = st.columns(3)
    a.metric('Registros de receitas próprias', item.get('record_count', 0))
    b.metric('Campos identificados', len(item.get('fields_observed', [])))
    c.metric('Evidência técnica', item.get('assessment_status', 'inconclusivo').replace('_', ' ').capitalize())
    st.warning('Conformidade legal: inconclusiva. Evidência restrita a receitas próprias.')
    st.write('Justificativa:', item.get('assessment_reason', 'Não informada'))
    st.write('Campos essenciais identificados:', ', '.join(item.get('essential_fields_present', [])) or 'Nenhum')
    if item.get('essential_fields_missing'):
        st.warning('Campos essenciais não observados: ' + ', '.join(item['essential_fields_missing']))
    with st.expander('Campos observados'):
        st.write(', '.join(item.get('fields_observed', [])))
    with st.expander('Rastreabilidade e limitações — receitas'):
        st.write('Município:', item.get('municipality'))
        st.write('Entidade:', item.get('entity_id'))
        st.write('Exercício:', item.get('year_requested'))
        st.write('Data da consulta (UTC):', item.get('processed_at_utc'))
        st.write('Endpoint:', item.get('endpoint'))
        st.write('URL consultada:', item.get('source_url'))
        st.write('Parâmetros:')
        st.json(item.get('request_parameters', {}))
        st.write('SHA-256 da resposta original:')
        st.code(item.get('source_sha256', ''), language=None)
        for limite in item.get('limitations', []):
            st.write('•', limite)
