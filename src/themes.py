"""Vocabulário temático do checklist.

Portais diferentes usam nomes diferentes para a mesma informação ("Despesas",
"Gastos", "Execução orçamentária", "Empenhos"...). Este dicionário é a camada que
normaliza nomenclaturas: orienta o crawler (quais links seguir primeiro) e as regras
(quais páginas examinar). É dado, não lógica: pode ser ampliado sem tocar nas regras.
"""
from __future__ import annotations

import re

from src.page import Page, norm

THEMES: dict[str, list[str]] = {
    "transparencia": [r"transparencia", r"acesso a informacao", r"\blai\b"],
    "receita": [r"receitas?", r"arrecadac", r"receita (prevista|arrecadada|orcada)"],
    "despesa": [r"despesas?", r"empenh", r"liquidac", r"pagamentos?", r"gastos", r"execucao orcamentaria",
                r"credor"],
    "licitacao": [r"licitac", r"pregao", r"edital", r"editais", r"compras", r"dispensa", r"inexigibilidade"],
    "contrato": [r"contratos?", r"aditivo", r"convenio"],
    "pessoal": [r"servidor", r"folha", r"remunerac", r"pessoal", r"recursos humanos", r"concurso"],
    "diarias": [r"diarias?", r"passagens"],
    "obras": [r"\bobras?\b", r"obras paralisadas"],
    "planejamento": [r"\bppa\b", r"\bldo\b", r"\bloa\b", r"plano plurianual", r"diretrizes orcamentarias",
                     r"lei orcamentaria", r"\brgf\b", r"\brreo\b", r"gestao fiscal", r"prestacao de contas",
                     r"balanco", r"contas de governo", r"relatorio resumido"],
    "sic": [r"e-?sic", r"\bsic\b", r"servico de informac", r"pedido de (acesso a )?informac",
            r"acesso a informacao", r"lei de acesso"],
    "ouvidoria": [r"ouvidoria", r"fale conosco", r"contato", r"carta de servicos"],
    "institucional": [r"institucional", r"estrutura organizacional", r"organograma", r"secretarias?",
                      r"competencias", r"atribuicoes", r"quem e quem", r"perguntas frequentes", r"\bfaq\b"],
    "lgpd": [r"lgpd", r"protecao de dados", r"dados pessoais", r"privacidade", r"encarregad"],
    "dados_abertos": [r"dados abertos", r"\bapi\b", r"open ?data", r"\bcsv\b"],
    "acessibilidade": [r"acessibilidade", r"alto contraste"],
}
_COMPILED = {k: [re.compile(p) for p in v] for k, v in THEMES.items()}


def score_text(value: str) -> dict[str, float]:
    text = norm(value)
    out = {}
    for theme, patterns in _COMPILED.items():
        hits = sum(1 for p in patterns if p.search(text))
        if hits:
            out[theme] = float(hits)
    return out


def link_themes(link: dict) -> dict[str, float]:
    """Texto do link pesa mais que a URL (URL costuma ter siglas e ids)."""
    label = score_text(link.get("text", ""))
    url = score_text(re.sub(r"[/_\-.?=&]+", " ", link.get("url", "")))
    return {t: label.get(t, 0) * 2 + url.get(t, 0) for t in set(label) | set(url)}


def classify_page(page: Page) -> dict[str, float]:
    """Tema da página: título, cabeçalhos, trilha e URL pesam mais que o corpo."""
    strong = " ".join([page.title, page.breadcrumb, " ".join(page.headings[:10]),
                       re.sub(r"[/_\-.?=&]+", " ", page.final_url)])
    scores = {t: 3 * s for t, s in score_text(strong).items()}
    for t, s in score_text(page.text[:20000]).items():
        scores[t] = scores.get(t, 0) + min(s, 2) * 0.5
    return {t: round(s, 2) for t, s in sorted(scores.items(), key=lambda kv: -kv[1])}


def pages_for(pages: list[Page], theme: str, minimum: float = 3.0) -> list[Page]:
    """Páginas cujo tema principal inclui `theme` (forte o bastante para servir de evidência)."""
    ranked = [p for p in pages if p.themes.get(theme, 0) >= minimum]
    return sorted(ranked, key=lambda p: -p.themes.get(theme, 0))
