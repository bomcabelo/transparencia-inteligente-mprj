"""Dashboard de evidências técnicas coletadas (não substitui auditoria humana)."""
import os
import requests
import streamlit as st

BASE = os.environ.get("MPRJ_API_URL", "http://127.0.0.1:8000").rstrip("/")
st.set_page_config(page_title="Transparência Inteligente — MPRJ", layout="wide")
st.title("Transparência Inteligente — MPRJ")
st.caption("Diagnóstico técnico preliminar • HTTP 200 não é certificado de conformidade")

def get(path):
    res = requests.get(f"{BASE}{path}", timeout=12)
    res.raise_for_status()
    return res.json()

try:
    entities = get("/entities")
except (requests.RequestException, ValueError) as exc:
    st.error("API indisponível. Execute: python -m uvicorn api.main:app --reload")
    st.caption(str(exc))
    st.stop()

st.metric("Municípios cadastrados", len(entities))
if not entities:
    st.info("Banco vazio. Importe a coleta: python -m src.database --source data/coletas.json")
    st.stop()

selected = st.selectbox("Município", entities, format_func=lambda e: e["name"])
try:
    history = get(f"/entities/{selected['id']}/evaluations/history")
except (requests.RequestException, ValueError) as exc:
    st.error(f"Erro ao consultar histórico: {exc}")
    st.stop()

st.metric("Coletas registradas", len(history))
if not history:
    st.warning("Ainda não há coletas registradas para este município.")
    st.stop()

try:
    latest = get(f"/entities/{selected['id']}/evaluations/latest")
except (requests.RequestException, ValueError) as exc:
    st.error(f"Erro ao consultar avaliação: {exc}")
    st.stop()

a, b, c = st.columns(3)
a.metric("Última resposta HTTP", str(latest.get("http_status") or "Sem resposta"))
b.metric("Critérios com indícios", len(latest.get("criteria", [])))
c.metric("Score de conformidade", "Não calculado")
st.write("URL analisada:", latest.get("url") or "Não cadastrada")
st.write("Data da coleta (UTC):", latest.get("collected_at"))
if latest.get("error"):
    st.warning(f"Ocorrência técnica: {latest['error']}")
st.info(latest.get("score_note", "Nenhuma conclusão jurídica automática."))

st.subheader("Critérios e evidências")
for criterion in latest.get("criteria", []):
    with st.expander(f"{criterion['criterion_id']} — {criterion['status']}"):
        st.write(criterion.get("finding", "Sem observações"))
        st.write("Evidência:", criterion.get("evidence_url") or "Não localizada")
        st.json(criterion.get("evidence", {}))

st.subheader("Histórico de coletas")
st.dataframe(history, use_container_width=True, hide_index=True)

# Integração GeoSIAP — Etapa 8
from app.geosiap_section import render_geosiap
render_geosiap(get, selected)
