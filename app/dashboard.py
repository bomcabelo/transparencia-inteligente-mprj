"""Painel de conformidade — consome exclusivamente a API (não lê o banco).

Executar:  python iniciar.py   (sobe API e painel juntos)
       ou: streamlit run app/dashboard.py   (com a API já rodando em MPRJ_API_URL,
           padrão http://127.0.0.1:8000)
"""
import os
import sys
from pathlib import Path

# `streamlit run app/dashboard.py` põe só a pasta app/ no sys.path; a raiz do projeto é necessária
# para importar os módulos `app.*` (sem isto, a aba "Por entidade" falhava com ModuleNotFoundError).
ROOT = str(Path(__file__).resolve().parents[1])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import altair as alt
import pandas as pd
import requests
import streamlit as st

BASE = os.environ.get("MPRJ_API_URL", "http://127.0.0.1:8000").rstrip("/")
SERIES = "#3987e5"
STATUS = {  # cor + ícone + rótulo: o status nunca depende só da cor
    "atende": ("#0ca30c", "✅", "Atende"),
    "parcial": ("#fab219", "🟡", "Parcial"),
    "nao_atende": ("#d03b3b", "❌", "Não atende"),
    "inconclusivo": ("#8a8984", "❔", "Inconclusivo"),
    "nao_avaliado": ("#5b5a56", "·", "Não avaliado"),
    "nao_aplicavel": ("#5b5a56", "—", "Não aplicável"),
}

st.set_page_config(page_title="Transparência Inteligente — MPRJ", layout="wide", page_icon="🔎")


@st.cache_data(ttl=60)
def get(path: str, **params):
    res = requests.get(f"{BASE}{path}", params=params or None, timeout=20)
    res.raise_for_status()
    return res.json()


def label(status: str) -> str:
    _, icon, text = STATUS.get(status, ("", "", status))
    return f"{icon} {text}"


def pct(value) -> str:
    return "—" if value is None else f"{value:.1f}%".replace(".", ",")


st.title("Transparência Inteligente — MPRJ")
st.caption("Avaliação automatizada de portais de transparência com evidências auditáveis. "
           "Score = critérios conclusivos ponderados; o intervalo mostra o efeito dos inconclusivos.")

try:
    overview = get("/overview")
    entities = get("/entities")
except (requests.RequestException, ValueError) as exc:
    st.error("API indisponível. Execute em outro terminal: `python -m uvicorn api.main:app --reload`")
    st.caption(str(exc))
    st.stop()

if not overview["entidades_avaliadas"]:
    st.info("Nenhuma avaliação registrada. Rode `python -m src.pipeline run` (portais reais) ou "
            "`python -m src.demo` (dados sintéticos) e reinicie a API.")
    st.stop()

tab_geral, tab_ent, tab_cat = st.tabs(["Visão geral", "Por entidade", "Checklist e cobertura"])

# ------------------------------------------------------------------ visão geral
with tab_geral:
    c = st.columns(5)
    c[0].metric("Entidades avaliadas", overview["entidades_avaliadas"])
    c[1].metric("Score médio", pct(overview["score_medio"]))
    best, worst = overview["melhor"], overview["pior"]
    c[2].metric("Melhor", pct(best["score"]) if best else "—", best["name"] if best else None, delta_color="off")
    c[3].metric("Pior", pct(worst["score"]) if worst else "—", worst["name"] if worst else None, delta_color="off")
    t = overview["criterios_por_status"]
    c[4].metric("Critérios atendidos / não atendidos", f"{t.get('atende', 0)} / {t.get('nao_atende', 0)}")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Ranking")
        rank = pd.DataFrame(overview["ranking"])
        if not rank.empty:
            rank["rótulo"] = rank["score"].map(pct)
            bars = alt.Chart(rank).mark_bar(color=SERIES, cornerRadiusEnd=4).encode(
                x=alt.X("score:Q", scale=alt.Scale(domain=[0, 105]), title="Score (%)"),
                y=alt.Y("nome:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320, labelOverlap=False)),
                tooltip=[alt.Tooltip("nome:N", title="Entidade"), alt.Tooltip("score:Q", title="Score"),
                         alt.Tooltip("classificacao:N", title="Classificação"),
                         alt.Tooltip("cobertura:Q", title="Cobertura", format=".0%"),
                         alt.Tooltip("comparavel:N", title="Comparável")])
            text = bars.mark_text(align="left", dx=4).encode(text="rótulo:N", color=alt.value("#c3c2b7"))
            st.altair_chart((bars + text).properties(height=max(140, 52 * len(rank))), use_container_width=True)
            low = rank[~rank["comparavel"]]
            if not low.empty:
                st.caption("⚠️ Cobertura baixa (comparação com ressalvas): " + ", ".join(low["nome"]))
    with right:
        st.subheader("Distribuição dos scores")
        dist = pd.DataFrame([{"faixa": k, "entidades": v} for k, v in overview["distribuicao_scores"].items()])
        st.altair_chart(alt.Chart(dist).mark_bar(color=SERIES, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("faixa:N", sort=None, title="Faixa de score (%)"),
            y=alt.Y("entidades:Q", title="Entidades", axis=alt.Axis(tickMinStep=1)),
            tooltip=["faixa", "entidades"]).properties(height=260), use_container_width=True)

    st.subheader("Desempenho médio por categoria")
    cats = pd.DataFrame(overview["media_por_categoria"])
    if not cats.empty:
        st.altair_chart(alt.Chart(cats).mark_bar(color=SERIES, cornerRadiusEnd=4).encode(
            x=alt.X("score_medio:Q", scale=alt.Scale(domain=[0, 100]), title="Score médio (%)"),
            y=alt.Y("categoria:N", sort="x", title=None, axis=alt.Axis(labelLimit=420)),
            tooltip=["categoria", "score_medio", "entidades"]).properties(height=30 * len(cats) + 40),
            use_container_width=True)

# ------------------------------------------------------------------ por entidade
with tab_ent:
    evaluated = [e for e in entities if e.get("ultima_avaliacao")]
    selected = st.selectbox("Entidade", evaluated, format_func=lambda e: e["name"])
    latest = get(f"/entities/{selected['id']}/evaluations/latest")
    history = pd.DataFrame(get(f"/entities/{selected['id']}/evaluations/history"))
    sc = latest["pontuacao"] or {}

    c = st.columns(5)
    c[0].metric("Score atual", pct(latest["score"]))
    c[1].metric("Classificação", sc.get("classificacao", "—"))
    lo, hi = sc.get("score_intervalo", [None, None])
    c[2].metric("Intervalo (inconclusivos 0→1)", f"{pct(lo)} – {pct(hi)}")
    c[3].metric("Cobertura da avaliação", f"{100 * sc.get('cobertura_avaliacao', 0):.0f}%")
    c[4].metric("Checklist automatizado", f"{100 * sc.get('cobertura_checklist', 0):.0f}%")
    st.caption(f"Coleta: {latest['collected_at']} · site: {latest['site_url']} · portal: {latest['portal_url']} "
               f"({latest['portal_source']}) · situação da coleta: {latest['collection_status']} · "
               f"fornecedor: {', '.join(latest.get('vendors') or {}) or 'não identificado'}")
    if sc.get("essenciais_pendentes"):
        st.warning("Critérios essenciais pendentes: " + ", ".join(sc["essenciais_pendentes"]))

    st.subheader("Evolução histórica")
    hist = history[history["kind"] == "coleta"].copy() if not history.empty else history
    if len(hist) >= 1:
        hist["data"] = pd.to_datetime(hist["collected_at"]).dt.strftime("%d/%m/%Y")
        st.markdown(" → ".join(pct(s) for s in hist["score"]))
        band = alt.Chart(hist).mark_area(opacity=0.18, color=SERIES).encode(
            x=alt.X("data:O", sort=None, title="Data da coleta", axis=alt.Axis(labelAngle=0)), y=alt.Y("score_min:Q", title="Score (%)", scale=alt.Scale(domain=[0, 100])),
            y2="score_max:Q")
        line = alt.Chart(hist).mark_line(color=SERIES, strokeWidth=2, point=alt.OverlayMarkDef(size=80, color=SERIES)
                                         ).encode(
            x=alt.X("data:O", sort=None), y="score:Q",
            tooltip=[alt.Tooltip("data:N", title="Data"), alt.Tooltip("score:Q", title="Score"),
                     alt.Tooltip("score_min:Q", title="Mínimo"), alt.Tooltip("score_max:Q", title="Máximo"),
                     alt.Tooltip("classificacao:N", title="Classificação"),
                     alt.Tooltip("cobertura_avaliacao:Q", title="Cobertura", format=".0%")])
        st.altair_chart((band + line).properties(height=260), use_container_width=True)
        st.caption("Linha: score. Faixa: intervalo entre considerar os inconclusivos como 'não atende' e como 'atende'.")
    if len(hist) >= 2:
        d = get(f"/entities/{selected['id']}/evaluations/diff")
        a, b, cc = st.columns(3)
        a.markdown("**✅ Corrigidos desde a coleta anterior**\n\n" +
                   ("\n".join(f"- {x['criterio']}: {label(x['de'])} → {label(x['para'])}" for x in d["melhoraram"])
                    or "_nenhum_"))
        b.markdown("**❌ Pioraram**\n\n" +
                   ("\n".join(f"- {x['criterio']}: {label(x['de'])} → {label(x['para'])}" for x in d["pioraram"])
                    or "_nenhum_"))
        cc.markdown("**🟡 Continuam pendentes**\n\n" +
                    (", ".join(x["criterio"] for x in d["pendentes"]) or "_nenhum_"))

    left, right = st.columns(2)
    cats = pd.DataFrame(sc.get("categorias", []))
    if not cats.empty:
        left.subheader("Melhores categorias")
        left.dataframe(cats.head(4), hide_index=True, use_container_width=True)
        right.subheader("Piores categorias")
        right.dataframe(cats.sort_values("score").head(4), hide_index=True, use_container_width=True)

    st.subheader("Critérios e evidências")
    crits = get(f"/entities/{selected['id']}/criteria")
    shown = [x for x in crits if x["status"] not in ("nao_avaliado", "nao_aplicavel")]
    options = ["nao_atende", "parcial", "inconclusivo", "atende"]
    chosen = st.multiselect("Status", options, default=["nao_atende", "parcial", "inconclusivo"], format_func=label)
    for item in [x for x in shown if x["status"] in chosen]:
        title = f"{label(item['status'])} · {item['criterion_id']} — {item['descricao'][:110]}"
        with st.expander(title):
            st.write(item["finding"])
            st.caption(f"Confiança: {100 * (item['confidence'] or 0):.0f}% · método: {item['method']} · regra: "
                       f"{item['rule_version']} · classificação: {item['classificacao']} · "
                       f"fundamentação: {item['fundamentacao']}"
                       + (f" · atende desde {item['atende_desde'][:10]}" if item.get("atende_desde") else "")
                       + (" · 🔍 requer revisão humana" if item["needs_review"] else ""))
            for ev in item.get("evidences", []):
                st.markdown(f"- **{ev['kind']}** · [{ev['title'] or ev['url']}]({ev['url']})"
                            + (f"\n  > {ev['snippet'][:300]}" if ev.get("snippet") else ""))
    na = [x for x in crits if x["status"] == "nao_aplicavel"]
    if na:
        st.caption(f"{len(na)} critério(s) não aplicável(is) ao tipo '{selected.get('tipo')}' — fora do score, "
                   "sem penalidade.")

    # Evidências estruturadas GeoSIAP (etapas 8–9), vinculadas ao município selecionado
    from app.geosiap_section import render_geosiap
    render_geosiap(lambda path: get(path), selected)

# ------------------------------------------------------------------ checklist
with tab_cat:
    catalog = pd.DataFrame(get("/criteria"))
    if not catalog.empty:
        total, impl = len(catalog), int(catalog["implementado"].sum())
        st.metric("Critérios automatizados", f"{impl} de {total}")
        st.caption("Critérios sem regra entram como 'não avaliado' (fora do score) e reduzem a cobertura "
                   "do checklist — a métrica deixa explícito o quanto do checklist já é verificado.")
        cols = ["id", "grupo", "descricao", "classificacao", "matriz", "implementado", "complexidade", "tecnica"]
        st.dataframe(catalog[cols], hide_index=True, use_container_width=True, height=520)
