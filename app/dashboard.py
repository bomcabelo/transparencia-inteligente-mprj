"""Dashboard inicial que consome a API REST FastAPI."""
import os

import requests
import streamlit as st

API_URL = os.getenv("MPRJ_API_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="Transparência Inteligente — MPRJ", layout="wide")
st.title("Transparência Inteligente — MPRJ")
st.caption("Prova de conceito • Fase inicial • Nenhuma conformidade foi aferida")

try:
    response = requests.get(f"{API_URL}/entities", timeout=10)
    response.raise_for_status()
    entities = response.json()
except (requests.RequestException, ValueError) as exc:
    st.error("Não foi possível consultar a API. Inicie com: uvicorn api.main:app --reload")
    st.caption(f"Detalhe técnico: {exc}")
    st.stop()

st.metric("Entidades cadastradas", len(entities))
if not entities:
    st.info(
        "Nenhuma entidade cadastrada ou avaliada. "
        "Os resultados serão apresentados após implementação da coleta, critérios e evidências."
    )
else:
    st.dataframe(entities, use_container_width=True)
