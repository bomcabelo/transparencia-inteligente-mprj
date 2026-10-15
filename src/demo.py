"""Portal SINTÉTICO para demonstração e testes ponta a ponta, sem acesso à internet.

Gera portais fictícios em quatro níveis de maturidade e simula três execuções
mensais, para que API e painel possam ser exercitados (histórico, evolução, diff,
critérios não aplicáveis). NENHUM dado aqui representa município real.

Uso:  python -m src.demo            (cria data/demo.sqlite3)
      set MPRJ_DB_PATH=data\\demo.sqlite3  (Windows)  |  export MPRJ_DB_PATH=data/demo.sqlite3
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from src import repository as repo
from src.checklist import load_catalog, load_methodology
from src.collector import collect
from src.engine import evaluate
from src.fetch import FixtureFetcher, utc_now
from src.rules.base import REGISTRY
from src.scoring import compute

ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / "data" / "demo.sqlite3"


def _layout(title: str, body: str, *, level: int, crumb: str = "", controls: bool = True) -> str:
    acc = ('<div class="barra-acessibilidade"><a href="#" title="Alto contraste">Contraste</a>'
           '<a href="#" title="Aumentar fonte">A+</a><a href="#" title="Diminuir fonte">A-</a>'
           '<a href="#" title="Acessibilidade">Acessibilidade</a></div>') if level >= 2 and controls else ""
    bc = f'<nav class="breadcrumb">Início › {crumb}</nav>' if level >= 2 and crumb else ""
    return f"""<!doctype html><html lang="pt-BR"><head><title>{title}</title>
<meta name="generator" content="PortalDemo 1.0"></head><body>{acc}{bc}<h1>{title}</h1>{body}
<footer>Prefeitura Exemplo — dados sintéticos</footer></body></html>"""


def build_portal(slug: str, level: int, today: date) -> dict[str, str]:
    """level 0..3: quanto maior, mais critérios atendidos."""
    site, portal = f"https://{slug}.demo.invalid", f"https://transparencia.{slug}.demo.invalid"
    d = lambda days: (today - timedelta(days=days)).strftime("%d/%m/%Y")  # noqa: E731
    pages: dict[str, str] = {}

    footer = ""
    if level >= 1:
        footer += "<p>Telefone: (21) 2345-6789</p>"
    if level >= 2:
        footer += ("<p>Endereço: Rua das Flores, 100 - Centro, CEP 20000-000</p>"
                   "<p>Horário de atendimento: 8h às 17h, de segunda a sexta</p>")
    search = '<form action="/busca" role="search"><input type="search" name="q" placeholder="Pesquisar"></form>' \
        if level >= 1 else ""
    transp = (f'<a href="{portal}">Portal da Transparência</a>' if level >= 1 else
              f'<a href="{portal}"><img src="/icone.png"></a>')
    pages[site] = _layout(f"Prefeitura {slug}", f"""{search}<nav>{transp}
        <a href="{site}/institucional">Institucional</a><a href="{site}/fale-conosco">Fale Conosco</a>
        <a href="{site}/noticias">Notícias</a></nav><p>Bem-vindo ao sítio oficial.</p>{footer}""", level=level)
    pages[f"{site}/noticias"] = _layout("Notícias", "<p>Notícias.</p>", level=level)
    inst = ("<h2>Competências e atribuições</h2>" + "<p>Compete à Secretaria de Fazenda planejar, coordenar e "
            "executar a política tributária e financeira do município, a arrecadação e a fiscalização.</p>" * 6
            if level >= 2 else "<p>Página em construção.</p>")
    pages[f"{site}/institucional"] = _layout("Institucional — Competências" if level >= 2 else "Institucional",
                                             inst + footer, level=level, crumb="Institucional")
    contact = ('<form action="/enviar"><label for="n">Nome</label><input id="n" name="nome">'
               '<label for="e">E-mail</label><input id="e" name="email" type="email">'
               '<label for="a">Assunto</label><input id="a" name="assunto">'
               '<label for="m">Mensagem</label><textarea id="m" name="mensagem"></textarea></form>'
               if level >= 3 else "<p>Envie e-mail para contato@exemplo.invalid</p>")
    pages[f"{site}/fale-conosco"] = _layout("Fale Conosco", contact + footer, level=level, crumb="Fale Conosco")

    links = "".join(f'<a href="{portal}/{p}">{t}</a>' for p, t in [
        ("despesas", "Despesas"), ("receitas", "Receitas"), ("planejamento", "Planejamento e Prestação de Contas"),
        ("esic", "e-SIC — Pedido de Informação"), ("lgpd", "Proteção de Dados Pessoais (LGPD)"),
        ("dados-abertos", "Dados Abertos")])
    pages[portal] = _layout("Portal da Transparência", search + f"<nav>{links}</nav>", level=level)

    # Despesas: dados estruturados + atualização + histórico + formatos
    cols = ["Empenho", "Data", "Credor", "Valor Empenhado", "Valor Pago"]
    if level >= 2:
        cols.insert(4, "Valor Liquidado")
    age = {0: 400, 1: 90, 2: 20, 3: 2}[level]
    rows = "".join(f"<tr><td>{n}/2026</td><td>{d(age + i)}</td><td>Fornecedor {n}</td>"
                   + "<td>R$ 1.000,00</td>" * (len(cols) - 3) + "</tr>" for i, n in enumerate(range(101, 104)))
    years = range(2022, today.year + 1) if level >= 2 else [today.year]
    select = '<form><label>Exercício</label><select name="ano">' + "".join(
        f"<option>{y}</option>" for y in years) + "</select></form>"
    exports = (f'<a href="{portal}/despesas.csv">Exportar CSV</a><a href="{portal}/despesas.xlsx">Exportar XLSX</a>'
               f'<a href="{portal}/despesas.pdf">Exportar PDF</a>' if level >= 2 else
               f'<a href="{portal}/despesas.pdf">Imprimir PDF</a>' if level == 1 else "")
    table = ("<table><tr>" + "".join(f"<th>{c}</th>" for c in cols) + f"</tr>{rows}</table>") if level >= 1 else ""
    pages[f"{portal}/despesas"] = _layout("Despesas — Execução Orçamentária", select + exports + table,
                                          level=level, crumb="Despesas")
    rec = ("<table><tr><th>Natureza da receita</th><th>Previsto</th><th>Arrecadado</th></tr>"
           "<tr><td>IPTU</td><td>R$ 10,00</td><td>R$ 8,00</td></tr></table>"
           f'<a href="{portal}/receitas.csv">Exportar CSV</a><a href="{portal}/receitas.pdf">PDF</a>'
           if level >= 1 else "<p>Em breve.</p>")
    pages[f"{portal}/receitas"] = _layout("Receitas", rec, level=level, crumb="Receitas")

    docs = []
    if level >= 1:
        docs.append(("loa-2026.pdf", "LOA 2026 — Lei Orçamentária Anual"))
    if level >= 2:
        docs += [("rgf-2026-q2.pdf", "RGF 2º quadrimestre 2026"), ("rgf-2025-q3.pdf", "RGF 3º quadrimestre 2025"),
                 ("rreo-2026-b4.pdf", "RREO 4º bimestre 2026")]
    if level >= 3:
        docs += [("ldo-2026.pdf", "LDO 2026"), ("ppa-2026-2029.pdf", "PPA 2026-2029")]
    pages[f"{portal}/planejamento"] = _layout("Planejamento e Prestação de Contas — Gestão Fiscal",
                                              "".join(f'<a href="{portal}/{f}">{t}</a>' for f, t in docs) or
                                              "<p>Sem documentos.</p>", level=level, crumb="Planejamento")

    motivo = ('<label for="mo">Motivo do pedido</label><input id="mo" name="motivo" required>' if level == 1 else "")
    form = (f'<form action="/esic/enviar"><label for="no">Nome</label><input id="no" name="nome" required>'
            f'<label for="em">E-mail</label><input id="em" name="email" required>{motivo}'
            f'<label for="pe">Pedido</label><textarea id="pe" name="pedido" required></textarea></form>'
            if level >= 1 else "")
    prazos = ("<p>O prazo de resposta é de 20 (vinte) dias, prorrogável por mais 10.</p>" if level >= 2 else "")
    prazos += "<p>Da negativa cabe recurso à autoridade hierarquicamente superior em 10 dias.</p>" if level >= 3 else ""
    pages[f"{portal}/esic"] = _layout("e-SIC — Serviço de Informação ao Cidadão",
                                      "<p>Faça seu pedido de acesso à informação.</p>" + form + prazos,
                                      level=level, crumb="e-SIC")
    lgpd = {0: "<p>Política de privacidade.</p>",
            1: "<p>Política de privacidade e proteção de dados pessoais.</p>",
            2: "<p>LGPD: o encarregado pelo tratamento de dados pessoais é designado por portaria.</p>",
            3: "<p>LGPD: encarregado pelo tratamento de dados pessoais: Maria Exemplo, e-mail "
               "encarregado@exemplo.invalid, telefone (21) 2345-0000.</p>"}[level]
    pages[f"{portal}/lgpd"] = _layout("Proteção de Dados Pessoais — LGPD", lgpd, level=level, crumb="LGPD")
    da = (f'<a href="{portal}/dados/despesas.csv">despesas.csv</a><a href="{portal}/dados/receitas.json">'
          'receitas.json</a><p>Termos de uso: licença Creative Commons CC-BY 4.0.</p>' if level >= 3 else
          "<p>Seção em implantação.</p>")
    pages[f"{portal}/dados-abertos"] = _layout("Dados Abertos", da, level=level, crumb="Dados Abertos")
    return pages


SCENARIO = [
    # (slug, nome, tipo, níveis nas execuções -60d, -30d, hoje)
    ("demo-a", "[DEMO] Município Exemplo A", "executivo_municipal", (1, 2, 3)),
    ("demo-b", "[DEMO] Município Exemplo B", "executivo_municipal", (0, 1, 1)),
    ("demo-c", "[DEMO] Município Exemplo C", "executivo_municipal", (2, 2, 3)),
    ("demo-camara", "[DEMO] Câmara Municipal Exemplo", "legislativo_municipal", (2, 2, 2)),
]


def seed(db_path: Path = DEMO_DB, today: date | None = None) -> None:
    today = today or date.today()
    catalog, methodology = load_catalog(), load_methodology()
    if Path(db_path).exists():
        Path(db_path).unlink()
    with repo.connect(db_path) as db:
        repo.sync_catalog(db, catalog, REGISTRY)
    for offset in (60, 30, 0):
        ref = today - timedelta(days=offset)
        stamp = datetime.combine(ref, time(3, 0), tzinfo=timezone.utc).isoformat()
        with repo.connect(db_path) as db:
            run_id = repo.start_run(db, "demonstracao", methodology["versao"], catalog["versao"], stamp)
            for slug, name, kind, levels in SCENARIO:
                level = levels[(60, 30, 0).index(offset)]
                entity = {"id": slug, "nome": name, "entidade": name, "tipo": kind, "municipio": "Exemplo",
                          "site": f"https://{slug}.demo.invalid", "portal": None, "ativo": True}
                col = collect(entity, FixtureFetcher(build_portal(slug, level, ref)), max_pages=30)
                col.started_at = col.finished_at = stamp
                for p in col.pages:
                    p.fetched_at = stamp
                results = evaluate(entity, col, catalog=catalog, methodology=methodology)
                score = compute(results, catalog=catalog, methodology=methodology)
                eid = repo.upsert_entity(db, entity)
                repo.save_assessment(db, run_id=run_id, entity_id=eid, entity_slug=slug, collection=col,
                                     results=results, score=score, evaluated_at=utc_now())
                print(f"{ref}  {name:<36} nível {level}  score={score['score']}  "
                      f"[{score['classificacao']}] cobertura={score['cobertura_avaliacao']:.0%}")
            repo.finish_run(db, run_id, stamp, len(SCENARIO), len(SCENARIO))


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera base de demonstração com portais sintéticos")
    parser.add_argument("--db", type=Path, default=DEMO_DB)
    args = parser.parse_args()
    seed(args.db)
    print(f"\nBase de demonstração: {args.db}\nDefina MPRJ_DB_PATH={args.db} antes de iniciar a API.")


if __name__ == "__main__":
    main()
