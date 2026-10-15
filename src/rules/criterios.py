"""Regras dos critérios implementados.

Seleção cobre os seis níveis de complexidade pedidos no desafio (item 13):
existência simples, navegação, dados estruturados, documentos, atualização e
interpretação semântica. A justificativa de cada escolha está em docs/CRITERIOS.md.
"""
from __future__ import annotations

import re
from datetime import date

from src.page import Page, norm
from src.rules.base import Context, Evidence, Result, absence, page_ev, rule

PHONE = r"\(?\b\d{2}\)?\s?\d{4,5}[-\s.]?\d{4}\b"
CEP = r"\b\d{5}-?\d{3}\b"
EMAIL = r"[\w.+-]+@[\w-]+(\.[\w-]+)+"
DATE = re.compile(r"\b([0-3]?\d)/([01]?\d)/((?:19|20)\d{2})\b")
MACHINE = {"csv", "xls", "ods", "json", "xml", "txt"}


def _institutional_pages(ctx: Context) -> list[Page]:
    """Capa, rodapé e páginas institucionais/de contato (onde ficam endereço e telefone)."""
    pages = [p for p in (ctx.site, ctx.portal) if p]
    pages += ctx.themed("institucional") + ctx.themed("ouvidoria")
    return list({p.final_url: p for p in pages}.values())


def _find_in_text(ctx: Context, cid: str, pages: list[Page], pattern: str, what: str,
                  confidence: float = 0.8) -> Result:
    for p in pages:
        snip = p.snippet(pattern, 80)
        if snip:
            return Result(cid, "atende", confidence, f"{what} encontrado(s) em '{p.title or p.final_url}'.",
                          [page_ev(p, snip, kind="texto", padrao=pattern)])
    return absence(ctx, cid, what, relevant=pages)


# ---------------------------------------------------------------- existência
@rule("1.1", complexidade="existencia", tecnica="http")
def r_1_1(ctx: Context) -> Result:
    """Sítio oficial e/ou portal da transparência acessível."""
    ev = [page_ev(p, f"HTTP {p.status}", kind="pagina") for p in (ctx.site, ctx.portal) if p]
    if ctx.site and ctx.portal:
        return Result("1.1", "atende", 0.95, "Sítio oficial e portal da transparência responderam (HTTP 200).", ev)
    if ctx.site or ctx.portal:
        which = "sítio oficial" if ctx.site else "portal da transparência"
        return Result("1.1", "atende", 0.85, f"Somente o {which} respondeu; o critério admite um ou outro.", ev)
    errs = [Evidence("ausencia", e["url"], detail=e) for e in ctx.collection.errors[:3]]
    return Result("1.1", "inconclusivo", 0.3, "Nenhum endereço respondeu nesta execução. Indisponibilidade "
                  "pontual não comprova inexistência; nova tentativa na próxima execução.", errs, needs_review=True)


@rule("2.4", complexidade="existencia", tecnica="regex")
def r_2_4(ctx: Context) -> Result:
    """Endereço: CEP ou logradouro com número."""
    pattern = rf"{CEP}|\b(rua|avenida|av\.|praca|estrada|rodovia|travessa)\s+[^,]{{3,60}},?\s*(n[oº°.]*\s*)?\d+"
    return _find_in_text(ctx, "2.4", _institutional_pages(ctx), pattern, "Endereço")


@rule("2.5", complexidade="existencia", tecnica="regex")
def r_2_5(ctx: Context) -> Result:
    """Telefone no formato brasileiro com DDD."""
    return _find_in_text(ctx, "2.5", _institutional_pages(ctx), PHONE, "Telefone")


@rule("2.6", complexidade="existencia", tecnica="regex")
def r_2_6(ctx: Context) -> Result:
    """Horário de atendimento."""
    pattern = (r"horario de (atendimento|funcionamento)|\b\d{1,2}\s?h(\d{2})?\s*(as|a|-|ate)\s*\d{1,2}\s?h"
               r"|\b\d{1,2}:\d{2}\s*(as|a|-|ate)\s*\d{1,2}:\d{2}")
    return _find_in_text(ctx, "2.6", _institutional_pages(ctx), pattern, "Horário de atendimento", 0.75)


# ---------------------------------------------------------------- estrutura da página
@rule("1.2", complexidade="estrutural", tecnica="html_links")
def r_1_2(ctx: Context) -> Result:
    """Link para o portal da transparência na capa do sítio oficial."""
    home = ctx.site
    if not home:
        return Result("1.2", "inconclusivo", 0.3, "Capa do sítio oficial indisponível nesta execução.",
                      needs_review=True)
    links = [l for l in home.links if "transparencia" in norm(l["text"])]
    if links:
        shot = {"screenshot": home.screenshot_path} if home.screenshot_path else {}
        return Result("1.2", "atende", 0.9 if home.screenshot_path else 0.8,
                      f"A capa contém {len(links)} link(s) rotulado(s) 'Transparência'. "
                      + ("Screenshot anexado." if shot else "Destaque visual não verificado (sem renderização)."),
                      [Evidence("link", l["url"], home.title, l["text"], {"pagina": home.final_url, **shot})
                       for l in links[:5]])
    by_url = [l for l in home.links if "transparencia" in norm(l["url"])]
    if by_url:
        return Result("1.2", "parcial", 0.6, "Há link para a transparência na capa, mas sem rótulo textual "
                      "identificável (ex.: só ícone/imagem sem texto alternativo).",
                      [Evidence("link", l["url"], home.title, l["text"]) for l in by_url[:5]], needs_review=True)
    return absence(ctx, "1.2", "Link para o portal da transparência na capa", relevant=[home], confidence=0.7)


@rule("1.3", complexidade="estrutural", tecnica="html_forms")
def r_1_3(ctx: Context) -> Result:
    """Ferramenta de pesquisa de conteúdo (campo de busca) no sítio ou portal."""
    for p in [x for x in (ctx.site, ctx.portal) if x] + ctx.pages:
        for form in p.forms:
            for f in form["fields"]:
                probe = norm(" ".join([f["name"], f["type"], f["placeholder"], f["label"], form["role"],
                                       form["action"]]))
                if f["type"] == "search" or re.search(r"\b(q|s|busca\w*|pesquis\w*|search|termo|keyword)\b", probe):
                    return Result("1.3", "atende", 0.85, "Campo de pesquisa encontrado.",
                                  [page_ev(p, f"campo '{f['name'] or f['placeholder']}' ({f['type']})",
                                           kind="formulario", action=form["action"])])
    return absence(ctx, "1.3", "Campo de pesquisa de conteúdo",
                   relevant=[x for x in (ctx.site, ctx.portal) if x], confidence=0.65)


@rule("16.1", complexidade="estrutural", tecnica="html_breadcrumb")
def r_16_1(ctx: Context) -> Result:
    """Trilha de navegação (breadcrumb) nas páginas internas."""
    internal = [p for p in ctx.pages if p.depth >= 1]
    with_crumb = [p for p in internal if p.breadcrumb]
    if not internal:
        return Result("16.1", "inconclusivo", 0.3, "Nenhuma página interna coletada.", needs_review=True)
    share = len(with_crumb) / len(internal)
    if share >= 0.5:
        return Result("16.1", "atende", 0.8, f"Trilha presente em {len(with_crumb)}/{len(internal)} páginas internas.",
                      [page_ev(p, p.breadcrumb, kind="controle") for p in with_crumb[:3]])
    if with_crumb:
        return Result("16.1", "parcial", 0.65, f"Trilha presente só em {len(with_crumb)}/{len(internal)} "
                      "páginas internas.", [page_ev(p, p.breadcrumb, kind="controle") for p in with_crumb[:3]])
    return absence(ctx, "16.1", "Trilha de navegação", relevant=internal, confidence=0.65)


def _control(ctx: Context, cid: str, pattern: str, what: str) -> Result:
    roots = [p for p in (ctx.site, ctx.portal) if p]
    hits = [(p, c) for p in roots for c in p.controls if re.search(pattern, norm(c))]
    if hits:
        where = {p.final_url for p, _ in hits}
        status = "atende" if len(where) == len(roots) else "parcial"
        msg = f"{what} encontrado em {len(where)} de {len(roots)} página(s) inicial(is) (sítio/portal)."
        return Result(cid, status, 0.8 if status == "atende" else 0.7, msg,
                      [page_ev(p, c, kind="controle") for p, c in hits[:4]])
    return absence(ctx, cid, what, relevant=roots, confidence=0.65)


@rule("16.2", complexidade="estrutural", tecnica="html_controles")
def r_16_2(ctx: Context) -> Result:
    """Opção de alto contraste no sítio e no portal."""
    return _control(ctx, "16.2", r"contraste", "Controle de alto contraste")


@rule("16.3", complexidade="estrutural", tecnica="html_controles")
def r_16_3(ctx: Context) -> Result:
    """Ferramenta de redimensionamento de texto."""
    return _control(ctx, "16.3", r"\ba\+|\ba-|aumentar|diminuir|fonte|font-?size|zoom", "Redimensionamento de texto")


# ---------------------------------------------------------------- navegação
@rule("2.9", complexidade="navegacao", tecnica="links+formularios")
def r_2_9(ctx: Context) -> Result:
    """Canal 'Fale Conosco' (formulário eletrônico, e-mail ou telefone)."""
    for p in ctx.pages:
        for form in p.forms:
            names = norm(" ".join(f["name"] + " " + f["label"] for f in form["fields"]))
            if re.search(r"mensagem|assunto", names) and re.search(r"e-?mail", names):
                return Result("2.9", "atende", 0.85, "Formulário eletrônico de contato encontrado.",
                              [page_ev(p, form["text"][:200], kind="formulario", action=form["action"])])
    links = [(p, l) for p in ctx.pages for l in p.links
             if re.search(r"fale conosco|contato|ouvidoria", norm(l["text"]))]
    if links:
        return Result("2.9", "atende", 0.7, "Link para canal de contato encontrado; formulário não verificado "
                      "(pode estar em sistema externo).", [Evidence("link", l["url"], p.title, l["text"],
                                                             {"pagina": p.final_url}) for p, l in links[:3]])
    return absence(ctx, "2.9", "Canal 'Fale Conosco'")


def _sic_pages(ctx: Context) -> list[Page]:
    return [p for p in ctx.themed("sic") if re.search(r"e-?sic|pedido|solicita|informac", p.ntext)]


@rule("15.1", complexidade="navegacao", tecnica="links+formularios")
def r_15_1(ctx: Context) -> Result:
    """Possibilidade de pedido de informação eletrônico (e-SIC)."""
    links = [(p, l) for p in ctx.pages for l in p.links
             if re.search(r"e-?sic|pedido de (acesso a )?informac|solicitar informac|fazer (um )?pedido",
                          norm(l["text"] + " " + l["url"]))]
    pages = _sic_pages(ctx)
    forms = [(p, f) for p in pages for f in p.forms if len(f["fields"]) >= 2]
    if forms:
        p, f = forms[0]
        return Result("15.1", "atende", 0.9, "Formulário de pedido de informação encontrado.",
                      [page_ev(p, f["text"][:200], kind="formulario", campos=[x["name"] for x in f["fields"]])])
    if links:
        return Result("15.1", "atende", 0.75, "Link para sistema e-SIC encontrado; envio não testado "
                      "(o robô não submete pedidos).",
                      [Evidence("link", l["url"], p.title, l["text"], {"pagina": p.final_url}) for p, l in links[:3]])
    return absence(ctx, "15.1", "Acesso ao e-SIC")


# ---------------------------------------------------------------- dados estruturados
def _table_hits(pages: list[Page], groups: dict[str, str]) -> tuple[Page | None, dict, dict]:
    """Melhor tabela: a que cobre mais grupos de colunas (ex.: empenho/liquidação/pagamento)."""
    best = (None, {}, {})
    for p in pages:
        for t in p.tables:
            heads = norm(" | ".join(t["headers"] + [t["caption"]]))
            found = {g: bool(re.search(rx, heads)) for g, rx in groups.items()}
            if sum(found.values()) > sum(best[1].values()):
                best = (p, found, t)
    return best


@rule("4.1", complexidade="dados_estruturados", tecnica="tabelas_html+api")
def r_4_1(ctx: Context) -> Result:
    """Número e valor de empenho, liquidação e pagamento."""
    groups = {"empenho": r"empenh", "liquidacao": r"liquida", "pagamento": r"\bpag(o|amento)"}
    pages = ctx.themed("despesa")
    page, found, table = _table_hits(pages, groups)
    api = ctx.extra_evidence.get("4.1")
    evs = [Evidence("api", api["url"], "API estruturada", api["resumo"], api)] if api else []
    if page and all(found.values()):
        return Result("4.1", "atende", 0.9, "Tabela de despesas com colunas de empenho, liquidação e pagamento.",
                      [page_ev(page, " | ".join(table["headers"])[:300], kind="tabela",
                               linhas=table["rows"], amostra=table["sample"][:2])] + evs)
    if api and api.get("ok"):
        return Result("4.1", "atende", 0.85, "API pública do portal expõe empenho, liquidação e pagamento.", evs)
    if page and any(found.values()):
        missing = [g for g, ok in found.items() if not ok]
        return Result("4.1", "parcial", 0.7, f"Tabela de despesas sem coluna(s): {', '.join(missing)}.",
                      [page_ev(page, " | ".join(table["headers"])[:300], kind="tabela")], needs_review=True)
    mentions = [p for p in pages if all(re.search(rx, p.ntext) for rx in groups.values())]
    if mentions:
        p = mentions[0]
        return Result("4.1", "inconclusivo", 0.45, "Página de despesas cita as três fases, mas os dados não "
                      "estão em tabela legível (provável consulta dinâmica).",
                      [page_ev(p, p.snippet(r"empenh") or "")], needs_review=True)
    return absence(ctx, "4.1", "Dados de empenho/liquidação/pagamento", relevant=pages or None)


@rule("3.1", complexidade="dados_estruturados", tecnica="tabelas_html+api")
def r_3_1(ctx: Context) -> Result:
    """Valores da receita pública arrecadada."""
    groups = {"receita": r"receita|natureza|rubrica|especificac|descri", "arrecadado": r"arrecadad|realizad"}
    pages = ctx.themed("receita")
    page, found, table = _table_hits(pages, groups)
    api = ctx.extra_evidence.get("3.1")
    evs = [Evidence("api", api["url"], "API estruturada", api["resumo"], api)] if api else []
    if page and all(found.values()):
        return Result("3.1", "atende", 0.9, "Tabela de receitas com valores arrecadados/realizados.",
                      [page_ev(page, " | ".join(table["headers"])[:300], kind="tabela",
                               linhas=table["rows"], amostra=table["sample"][:2])] + evs)
    if api and api.get("ok"):
        return Result("3.1", "atende", 0.85, "API pública do portal expõe receitas com valor arrecadado.", evs)
    mentions = [p for p in pages if re.search(r"arrecadad|realizad", p.ntext)]
    if mentions:
        p = mentions[0]
        return Result("3.1", "inconclusivo", 0.45, "Página de receitas cita arrecadação, mas sem tabela legível.",
                      [page_ev(p, p.snippet(r"arrecadad|realizad") or "")], needs_review=True)
    return absence(ctx, "3.1", "Receita arrecadada", relevant=pages or None)


def _formats(ctx: Context, cid: str, theme: str, label: str) -> Result:
    pages = ctx.themed(theme)
    docs = [(p, d) for p in pages for d in p.documents]
    exts = sorted({d["ext"] for _, d in docs})
    ev = [Evidence("documento", d["url"], p.title, d["text"], {"formato": d["ext"], "pagina": p.final_url})
          for p, d in docs[:6]]
    if len(exts) >= 2 and MACHINE & set(exts):
        return Result(cid, "atende", 0.85, f"Relatórios de {label} exportáveis em {', '.join(exts)}.", ev)
    if exts:
        return Result(cid, "parcial", 0.7, f"Exportação de {label} só em {', '.join(exts)}"
                      + ("" if MACHINE & set(exts) else " (nenhum formato legível por máquina)") + ".", ev)
    if not pages:
        return absence(ctx, cid, f"Página de {label}")
    return absence(ctx, cid, f"Exportação de relatórios de {label}", relevant=pages, confidence=0.6)


@rule("3.5", complexidade="dados_estruturados", tecnica="links_documentos")
def r_3_5(ctx: Context) -> Result:
    """Gravação de relatórios de receita em diversos formatos."""
    return _formats(ctx, "3.5", "receita", "receita")


@rule("4.5", complexidade="dados_estruturados", tecnica="links_documentos")
def r_4_5(ctx: Context) -> Result:
    """Gravação de relatórios de despesa em diversos formatos."""
    return _formats(ctx, "4.5", "despesa", "despesa")


@rule("18.3", complexidade="dados_estruturados", tecnica="links_documentos+texto")
def r_18_3(ctx: Context) -> Result:
    """Dados abertos legíveis por máquina com regras de utilização."""
    pages = ctx.themed("dados_abertos")
    data = [(p, d) for p in pages for d in p.documents if d["ext"] in MACHINE]
    apis = [(p, l) for p in pages for l in p.links if re.search(r"\bapi\b|swagger|ckan|/dataset", norm(l["url"]))]
    rules_page = next((p for p in pages if re.search(r"termos? de uso|licenca|regras de (uso|utilizacao)|"
                                                     r"creative commons|odbl", p.ntext)), None)
    ev = [Evidence("documento", d["url"], p.title, d["text"], {"formato": d["ext"]}) for p, d in data[:3]]
    ev += [Evidence("link", l["url"], p.title, l["text"]) for p, l in apis[:2]]
    if (data or apis) and rules_page:
        ev.append(page_ev(rules_page, rules_page.snippet(r"termos? de uso|licenca|regras de") or ""))
        return Result("18.3", "atende", 0.8, "Dados legíveis por máquina e regras de utilização publicadas.", ev)
    if data or apis:
        return Result("18.3", "parcial", 0.7, "Há dados legíveis por máquina, mas não foram localizadas as "
                      "regras de utilização.", ev)
    return absence(ctx, "18.3", "arquivos legíveis por máquina ou API em seção de dados abertos" if pages
                   else "seção de dados abertos", relevant=pages or None)


# ---------------------------------------------------------------- documentos
def _document(ctx: Context, cid: str, pattern: str, what: str, theme: str = "planejamento") -> Result:
    docs = [(p, d) for p in ctx.pages for d in p.documents
            if re.search(pattern, norm(d["text"] + " " + d["url"]))]
    years = sorted({int(y) for _, d in docs for y in re.findall(r"\b(20[0-3]\d)\b", d["text"] + d["url"])})
    if docs:
        detail = f" Exercícios identificados: {', '.join(map(str, years[-6:]))}." if years else ""
        return Result(cid, "atende", 0.85, f"{len(docs)} arquivo(s) de {what} encontrado(s).{detail}",
                      [Evidence("documento", d["url"], p.title, d["text"], {"formato": d["ext"],
                                "pagina": p.final_url}) for p, d in docs[:5]])
    links = [(p, l) for p in ctx.pages for l in p.links if re.search(pattern, norm(l["text"]))]
    if links:
        return Result(cid, "parcial", 0.55, f"Link para {what} encontrado, mas o arquivo não foi alcançado "
                      "(pode estar em consulta dinâmica ou página não coletada).",
                      [Evidence("link", l["url"], p.title, l["text"]) for p, l in links[:3]], needs_review=True)
    return absence(ctx, cid, what, relevant=ctx.themed(theme) or None, confidence=0.6)


@rule("12.1", complexidade="documentos", tecnica="links_documentos")
def r_12_1(ctx: Context) -> Result:
    """Relatório de Gestão Fiscal (RGF)."""
    return _document(ctx, "12.1", r"\brgf\b|gestao fiscal", "Relatório de Gestão Fiscal")


@rule("20.1", complexidade="documentos", tecnica="links_documentos")
def r_20_1(ctx: Context) -> Result:
    """Relatório Resumido da Execução Orçamentária (RREO)."""
    return _document(ctx, "20.1", r"\brreo\b|resumido da execucao", "RREO")


@rule("19.1", complexidade="documentos", tecnica="links_documentos")
def r_19_1(ctx: Context) -> Result:
    """Lei do Plano Plurianual (PPA)."""
    return _document(ctx, "19.1", r"\bppa\b|plano plurianual", "PPA")


@rule("19.3", complexidade="documentos", tecnica="links_documentos")
def r_19_3(ctx: Context) -> Result:
    """Lei de Diretrizes Orçamentárias (LDO)."""
    return _document(ctx, "19.3", r"\bldo\b|diretrizes orcamentarias", "LDO")


@rule("19.5", complexidade="documentos", tecnica="links_documentos")
def r_19_5(ctx: Context) -> Result:
    """Lei Orçamentária Anual (LOA)."""
    return _document(ctx, "19.5", r"\bloa\b|lei orcamentaria anual", "LOA")


# ---------------------------------------------------------------- atualização e histórico
def _dates(page: Page, today: date) -> list[date]:
    out = []
    for d, m, y in DATE.findall(page.text):
        try:
            value = date(int(y), int(m), int(d))
        except ValueError:
            continue
        if date(2000, 1, 1) <= value <= today:
            out.append(value)
    return out


@rule("4.6", complexidade="atualizacao", tecnica="datas_no_conteudo")
def r_4_6(ctx: Context) -> Result:
    """Informações de despesa atualizadas (data mais recente observada x data da coleta)."""
    limits = ctx.methodology["atualizacao_dias"]["despesa"]
    pages = ctx.themed("despesa")
    dated = [(p, max(ds)) for p in pages if (ds := _dates(p, ctx.today))]
    if not dated:
        if not pages:
            return absence(ctx, "4.6", "Página de despesas")
        return Result("4.6", "inconclusivo", 0.35, "Páginas de despesa sem datas legíveis no HTML "
                      "(datas podem estar em consulta dinâmica).", [page_ev(p) for p in pages[:3]], needs_review=True)
    page, latest = max(dated, key=lambda x: x[1])
    age = (ctx.today - latest).days
    snip = page.snippet(re.escape(latest.strftime("%d/%m/%Y"))) or latest.isoformat()
    ev = [page_ev(page, snip, kind="texto", data_mais_recente=latest.isoformat(), dias=age)]
    if age <= limits["atende"]:
        return Result("4.6", "atende", 0.75, f"Registro mais recente de {latest:%d/%m/%Y} ({age} dias antes da coleta).", ev)
    if age <= limits["parcial"]:
        return Result("4.6", "parcial", 0.7, f"Registro mais recente de {latest:%d/%m/%Y} ({age} dias): "
                      f"acima de {limits['atende']} dias.", ev)
    return Result("4.6", "nao_atende", 0.65, f"Registro mais recente de {latest:%d/%m/%Y} ({age} dias): "
                  "informações desatualizadas.", ev, needs_review=True)


@rule("4.7", complexidade="atualizacao", tecnica="filtros_de_exercicio")
def r_4_7(ctx: Context) -> Result:
    """Histórico das despesas: consulta a exercícios anteriores."""
    pages = ctx.themed("despesa")
    years: set[int] = set()
    ev = []
    for p in pages:
        found = {int(y) for f in p.forms for y in re.findall(r"\b(20[0-3]\d)\b", f["text"])}
        found |= {int(y) for l in p.links for y in re.findall(r"^\s*(20[0-3]\d)\s*$", l["text"])}
        found = {y for y in found if y <= ctx.today.year}
        if found:
            years |= found
            ev.append(page_ev(p, f"exercícios disponíveis: {', '.join(map(str, sorted(found)))}", kind="formulario"))
    if len(years) >= 3:
        return Result("4.7", "atende", 0.8, f"Consulta a {len(years)} exercícios ({min(years)}–{max(years)}).", ev[:3])
    if years:
        return Result("4.7", "parcial", 0.65, f"Somente {len(years)} exercício(s) disponível(is).", ev[:3])
    if not pages:
        return absence(ctx, "4.7", "Página de despesas")
    return Result("4.7", "inconclusivo", 0.4, "Seletor de exercício não identificado no HTML.",
                  [page_ev(p) for p in pages[:3]], needs_review=True)


# ---------------------------------------------------------------- interpretação semântica
def _with_llm(ctx: Context, base: Result, criterion_text: str, pages: list[Page], focus: str) -> Result:
    """Combina regra + IA. A IA só é consultada quando a regra não decide (ou para confirmar
    uma negativa) e só recebe trechos pré-filtrados; a resposta precisa citar texto literal."""
    if ctx.llm is None or base.status in ("atende",) or not pages:
        return base
    snippets = []
    for p in pages[:4]:
        for m in re.finditer(focus, p.ntext):
            s = max(0, m.start() - 400)
            snippets.append({"url": p.final_url, "texto": p.text[s:m.end() + 600]})
            if len(snippets) >= 6:
                break
    if not snippets:
        return base
    verdict = ctx.llm.judge(base.criterion_id, criterion_text, snippets)
    if verdict is None:
        return base
    ai_ev = Evidence("ia", verdict["url"], "Trecho citado pela IA", verdict["citacao"],
                     {"modelo": verdict["modelo"], "prompt_sha256": verdict["prompt_sha256"]})
    if base.status == "inconclusivo":
        return Result(base.criterion_id, verdict["status"], min(verdict["confianca"], 0.75),
                      f"[IA] {verdict['justificativa']}", base.evidences + [ai_ev], method="regra+ia",
                      needs_review=True, ai=verdict)
    if verdict["status"] != base.status:  # divergência regra x IA -> revisão humana
        return Result(base.criterion_id, "inconclusivo", 0.4, f"Regra indicou '{base.status}', IA indicou "
                      f"'{verdict['status']}'. Encaminhado à revisão humana.", base.evidences + [ai_ev],
                      method="regra+ia", needs_review=True, ai=verdict)
    base.evidences.append(ai_ev)
    base.method, base.ai = "regra+ia", verdict
    base.confidence = min(0.9, base.confidence + 0.1)
    return base


@rule("15.2", complexidade="semantica", tecnica="formulario+ia", semantico=True)
def r_15_2(ctx: Context) -> Result:
    """e-SIC sem exigências que dificultem o acesso (documentos, firma, declaração, maioridade, motivo)."""
    pages = _sic_pages(ctx)
    forms = [(p, f) for p in pages for f in p.forms if len(f["fields"]) >= 2]
    barrier = r"reconhecid|firma|declarac|maioridade|maior de 18|motivo|justificativa|finalidade|comprovante"
    if forms:
        bad = [(p, f, x) for p, f in forms for x in f["fields"]
               if (x["type"] == "file" and x["required"]) or (x["required"] and re.search(barrier, norm(x["label"] + " " + x["name"])))]
        if bad:
            p, f, x = bad[0]
            base = Result("15.2", "nao_atende", 0.75, f"Campo obrigatório que dificulta o acesso: "
                          f"'{x['label'] or x['name']}' ({x['type']}).", [page_ev(p, f["text"][:200], kind="formulario")])
        else:
            p, f = forms[0]
            base = Result("15.2", "atende", 0.7, "Formulário do e-SIC sem campos obrigatórios restritivos "
                          f"({len(f['fields'])} campos).", [page_ev(p, ", ".join(x["label"] or x["name"]
                                                                                    for x in f["fields"])[:250],
                                                                    kind="formulario")])
    else:
        text_bar = [p for p in pages if re.search(rf"(exig|obrigatori|necessari)\w*.{{0,80}}({barrier})", p.ntext)]
        base = Result("15.2", "inconclusivo", 0.35, "Formulário do e-SIC não acessível ao robô (sistema externo ou "
                      "login). Exigências precisam de leitura do texto.", [page_ev(p) for p in (text_bar or pages)[:3]],
                      needs_review=True)
    return _with_llm(ctx, base, "A solicitação no e-SIC é simples, sem exigir documentos, firma reconhecida, "
                     "declaração de responsabilidade, maioridade ou motivo do pedido (cadastro prévio é permitido)?",
                     pages, r"e-?sic|pedido|solicita|cadastr|exig|document")


@rule("15.4", complexidade="semantica", tecnica="texto")
def r_15_4(ctx: Context) -> Result:
    """Prazos de resposta e recurso e procedimento do pedido divulgados na seção do e-SIC."""
    pages = _sic_pages(ctx)
    prazo = [p for p in pages if re.search(r"\b(20|vinte)\s*\(?\w*\)?\s*dias", p.ntext)]
    recurso = [p for p in pages if re.search(r"recurso", p.ntext)]
    ev = [page_ev(p, p.snippet(r"\b(20|vinte)\s*\(?\w*\)?\s*dias") or "", kind="texto") for p in prazo[:2]]
    ev += [page_ev(p, p.snippet(r"recurso") or "", kind="texto") for p in recurso[:2]]
    if prazo and recurso:
        return Result("15.4", "atende", 0.75, "Prazo de resposta e possibilidade de recurso informados.", ev)
    if prazo or recurso:
        return Result("15.4", "parcial", 0.65, "Informa " + ("prazo de resposta" if prazo else "recurso")
                      + ", mas não " + ("o recurso." if prazo else "o prazo de resposta."), ev)
    return absence(ctx, "15.4", "Prazos e procedimento do e-SIC", relevant=pages or None)


@rule("18.1", complexidade="semantica", tecnica="texto+ia", semantico=True)
def r_18_1(ctx: Context) -> Result:
    """Encarregado pelo tratamento de dados pessoais (LGPD) identificado, com canal de contato."""
    pages = ctx.themed("lgpd", 1.5)
    near = r"encarregad[oa].{0,300}"
    for p in pages:
        m = re.search(near, p.ntext)
        if m:
            window = p.ntext[m.start(): m.end() + 200]
            contact = re.search(EMAIL, window) or re.search(PHONE, window)
            snip = p.snippet(r"encarregad[oa]", 200) or ""
            if contact:
                return Result("18.1", "atende", 0.8, "Encarregado (LGPD) identificado com canal de contato.",
                              [page_ev(p, snip, kind="texto")])
            base = Result("18.1", "parcial", 0.6, "Encarregado mencionado, sem e-mail/telefone próximo.",
                          [page_ev(p, snip, kind="texto")], needs_review=True)
            return _with_llm(ctx, base, "A página identifica o encarregado (DPO) pelo tratamento de dados "
                             "pessoais E informa um canal de comunicação (telefone e/ou e-mail)?",
                             pages, r"encarregad|dados pessoais|lgpd")
    base = absence(ctx, "18.1", "Identificação do encarregado (LGPD)", relevant=pages or None, confidence=0.55)
    return _with_llm(ctx, base, "A página identifica o encarregado (DPO) pelo tratamento de dados pessoais "
                     "E informa um canal de comunicação (telefone e/ou e-mail)?", pages,
                     r"lgpd|dados pessoais|privacidade|protecao de dados")


@rule("2.1", complexidade="semantica", tecnica="texto+ia", semantico=True)
def r_2_1(ctx: Context) -> Result:
    """Competências e/ou atribuições dos órgãos publicadas."""
    pages = ctx.themed("institucional", 1.5)
    hits = [p for p in pages if re.search(r"competencia|atribuic", norm(" ".join(p.headings + [p.title])))]
    if hits:
        p = hits[0]
        long_enough = len(p.text) > 600
        base = Result("2.1", "atende" if long_enough else "parcial", 0.75 if long_enough else 0.55,
                      "Página com título de competências/atribuições" + ("" if long_enough else " e pouco conteúdo") + ".",
                      [page_ev(p, p.snippet(r"competencia|atribuic", 200) or "", kind="texto")])
        return base if long_enough else _with_llm(ctx, base, "A página descreve as competências ou atribuições "
                                                  "do órgão/secretarias?", hits, r"competencia|atribuic")
    base = absence(ctx, "2.1", "Competências/atribuições", relevant=pages or None, confidence=0.55)
    return _with_llm(ctx, base, "A página descreve as competências ou atribuições do órgão/secretarias?",
                     pages, r"competencia|atribuic|finalidade|compete")
