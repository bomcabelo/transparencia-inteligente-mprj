"""Planilha de validação manual: robô × avaliador humano.

Exporta a última coleta de cada entidade (somente critérios aplicáveis e automatizados)
para um .xlsx com os resultados do robô já preenchidos. O avaliador confere cada linha
no portal e preenche as colunas amarelas; a aba "Métricas" calcula concordância,
falsos "não atende", falsos "atende", taxa de inconclusivos, kappa de Cohen e quebras
por critério e por município — tudo por fórmulas, recalculando à medida que se preenche.

Uso:
  python -m src.validacao                         # todas as entidades com avaliação
  python -m src.validacao --entity japeri --entity itaborai --saida data/validacao.xlsx
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src import repository as repo
from src.rules import criterios as _regras  # noqa: F401  (registra as regras)
from src.rules.base import REGISTRY

ROBO = ["atende", "parcial", "nao_atende", "inconclusivo"]
HUMANO = ["atende", "parcial", "nao_atende", "nao_aplicavel", "nao_verificavel"]
CAUSAS = ["Crawler não chegou à página", "Informação em sistema externo/consulta", "Conteúdo dinâmico (JavaScript)",
          "Regra: padrão não reconhecido", "Regra: falso indício", "Critério ambíguo", "Página indisponível", "Outro"]

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3864")
IN_FILL = PatternFill("solid", fgColor="FFF2CC")
ROBOT_FILL = PatternFill("solid", fgColor="EDEDED")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

COLS = [  # (cabeçalho, largura, grupo)
    ("Entidade", 24, "robo"), ("Avaliação nº", 10, "robo"), ("Data da coleta", 12, "robo"),
    ("Critério", 8, "robo"), ("Descrição do critério", 46, "robo"), ("Classificação", 12, "robo"),
    ("Status do robô", 13, "robo"), ("Confiança", 10, "robo"), ("Conclusão do robô", 46, "robo"),
    ("URL da evidência", 34, "robo"), ("Trecho da evidência", 40, "robo"),
    ("Status conferido", 15, "entrada"), ("URL onde conferiu", 30, "entrada"),
    ("Causa da divergência", 26, "entrada"), ("Observação", 30, "entrada"),
    ("Classe", 18, "formula"), ("Par conclusivo", 9, "formula"), ("Acerto exato", 9, "formula"),
]
C = {name: get_column_letter(i + 1) for i, (name, _, _) in enumerate(COLS)}


def _rows(db, slugs: list[str] | None) -> list[list]:
    rows = []
    for e in repo.entities(db):
        if slugs and e["slug"] not in slugs:
            continue
        aid = db.execute("SELECT id FROM assessments WHERE entity_id=? AND kind='coleta' "
                         "ORDER BY collected_at DESC, id DESC LIMIT 1", (e["id"],)).fetchone()
        if not aid:
            continue
        a = repo.assessment(db, aid["id"], with_evidence=True)
        for r in a["criteria"]:
            if r["criterion_id"] not in REGISTRY or r["status"] in ("nao_aplicavel", "nao_avaliado"):
                continue
            ev = next((x for x in r.get("evidences", []) if x.get("url")), {})
            rows.append([e["name"], a["id"], a["collected_at"][:10], r["criterion_id"], r["descricao"],
                         r["classificacao"], r["status"], r["confidence"], r["finding"], ev.get("url") or "",
                         (ev.get("snippet") or "")[:300]])
    return rows


def _header(ws, row: int, labels: list[str]) -> None:
    for i, label in enumerate(labels, 1):
        cell = ws.cell(row=row, column=i, value=label)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = H_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = BOX


def _instrucoes(wb: Workbook, n: int, origem: str) -> None:
    ws = wb.active
    ws.title = "Instruções"
    lines = [
        ("Validação manual dos resultados do robô", True),
        (f"Gerada em {date.today():%d/%m/%Y} a partir de: {origem}. Linhas: {n} (critérios aplicáveis e automatizados "
         "da última coleta de cada entidade).", False),
        ("", False),
        ("Como preencher (aba 'Avaliação')", True),
        ("1. Colunas cinza = resultado do robô (não editar). Colunas amarelas = suas entradas.", False),
        ("2. Abra a URL da evidência (ou navegue pelo portal) e verifique o critério como um avaliador faria.", False),
        ("3. 'Status conferido': escolha na lista — atende, parcial, nao_atende, nao_aplicavel ou nao_verificavel "
         "(use nao_verificavel quando nem você conseguir concluir, ex.: portal fora do ar).", False),
        ("4. Se discordar do robô, escolha a 'Causa da divergência' e descreva em 'Observação'.", False),
        ("5. As colunas 'Classe', 'Par conclusivo' e 'Acerto exato' e toda a aba 'Métricas' são calculadas sozinhas.", False),
        ("6. Depois de ajustar regras, registre o que mudou na aba 'Ajustes' e reexecute: "
         "python -m src.pipeline reevaluate --latest (sem acessar os portais) e gere nova planilha.", False),
        ("", False),
        ("Classes calculadas", True),
        ("Concordância: robô e você deram o mesmo status.", False),
        ("Falso não atende: robô disse nao_atende, mas a informação existe (o erro mais grave numa fiscalização).", False),
        ("Falso atende: robô disse atende, mas a informação não existe ou é insuficiente.", False),
        ("Divergência de grau: um disse parcial e o outro atende/nao_atende.", False),
        ("Inconclusivo: robô não decidiu — mede a cobertura, não a precisão.", False),
        ("Aplicabilidade / Não verificável: casos fora do cálculo de precisão.", False),
        ("", False),
        ("Linha de exemplo (formato esperado — não faz parte do cálculo)", True),
    ]
    for i, (text, bold) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=text)
        c.font = Font(name=FONT, bold=bold, size=13 if i == 1 else 10)
    ex_row = len(lines) + 1
    _header(ws, ex_row, [c[0] for c in COLS[:15]])
    example = ["Japeri", 12, "2026-10-14", "4.1", "Número e o valor de empenho, liquidação e pagamento", "essencial",
               "nao_atende", 0.6, "Não encontrado: dados de empenho/liquidação/pagamento...",
               "https://japeri.geosiap.net.br/portal-transparencia", "", "atende",
               "https://japeri.geosiap.net.br/portal-transparencia/despesas", "Informação em sistema externo/consulta",
               "Dados aparecem só após escolher o exercício no filtro."]
    for j, v in enumerate(example, 1):
        cell = ws.cell(row=ex_row + 1, column=j, value=v)
        cell.font = Font(name=FONT, size=10, color="7F7F7F", italic=True)
        cell.fill = IN_FILL if j >= 12 else ROBOT_FILL
    ws.column_dimensions["A"].width = 24
    for j in range(2, 16):
        ws.column_dimensions[get_column_letter(j)].width = 16


def _avaliacao(wb: Workbook, rows: list[list]) -> int:
    ws = wb.create_sheet("Avaliação")
    _header(ws, 1, [c[0] for c in COLS])
    last = max(2, len(rows) + 1)
    for i, row in enumerate(rows, 2):
        for j, v in enumerate(row, 1):
            cell = ws.cell(row=i, column=j, value=v)
            cell.fill, cell.border = ROBOT_FILL, BOX
            cell.font = Font(name=FONT, size=9)
            cell.alignment = Alignment(wrap_text=j in (5, 9, 11), vertical="top")
        ws.cell(row=i, column=8).number_format = "0%"
        if row[9]:
            ws.cell(row=i, column=10).hyperlink = row[9]
        for col in ("Status conferido", "URL onde conferiu", "Causa da divergência", "Observação"):
            cell = ws[f"{C[col]}{i}"]
            cell.fill, cell.border, cell.font = IN_FILL, BOX, Font(name=FONT, size=9)
        r, h = f"{C['Status do robô']}{i}", f"{C['Status conferido']}{i}"
        ws[f"{C['Classe']}{i}"] = (
            f'=IF({h}="","",IF({r}="inconclusivo","Inconclusivo",IF({h}="nao_aplicavel","Aplicabilidade",'
            f'IF({h}="nao_verificavel","Não verificável",IF({r}={h},"Concordância",'
            f'IF({r}="nao_atende","Falso não atende",IF({r}="atende","Falso atende","Divergência de grau")))))))')
        ws[f"{C['Par conclusivo']}{i}"] = (
            f'=IF(AND(OR({r}="atende",{r}="parcial",{r}="nao_atende"),'
            f'OR({h}="atende",{h}="parcial",{h}="nao_atende")),1,0)')
        ws[f"{C['Acerto exato']}{i}"] = f'=IF({C["Par conclusivo"]}{i}=1,IF({r}={h},1,0),"")'
        for col in ("Classe", "Par conclusivo", "Acerto exato"):
            ws[f"{C[col]}{i}"].font = Font(name=FONT, size=9)
            ws[f"{C[col]}{i}"].border = BOX
    for name, width, _ in COLS:
        ws.column_dimensions[C[name]].width = width
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = f"A1:{C['Acerto exato']}{last}"
    dv = DataValidation(type="list", formula1='"' + ",".join(HUMANO) + '"', allow_blank=True)
    dv.add(f"{C['Status conferido']}2:{C['Status conferido']}{last}")
    dv2 = DataValidation(type="list", formula1="=Listas!$A$1:$A$%d" % len(CAUSAS), allow_blank=True)
    dv2.add(f"{C['Causa da divergência']}2:{C['Causa da divergência']}{last}")
    ws.add_data_validation(dv)
    ws.add_data_validation(dv2)
    rng = f"{C['Classe']}2:{C['Classe']}{last}"
    for text, color in (("Concordância", "C6EFCE"), ("Falso não atende", "FFC7CE"), ("Falso atende", "FFC7CE"),
                        ("Divergência de grau", "FFEB9C")):
        ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{text}"'],
                                                      fill=PatternFill("solid", fgColor=color)))
    ws[f"{C['Status conferido']}1"].comment = Comment("Escolha na lista. nao_verificavel = você também não "
                                                      "conseguiu concluir.", "validacao")
    return last


def _metricas(wb: Workbook, last: int, entidades: list[str], criterios: list[str]) -> None:
    ws = wb.create_sheet("Métricas")
    A = "'Avaliação'!"
    rng = lambda col: f"{A}${C[col]}$2:${C[col]}${last}"  # noqa: E731
    R, H, K = rng("Status do robô"), rng("Status conferido"), rng("Classe")
    P, X, E, CR = rng("Par conclusivo"), rng("Acerto exato"), rng("Entidade"), rng("Critério")
    bold = Font(name=FONT, bold=True)
    ws["A1"], ws["A1"].font = "Métricas de validação (atualizam conforme a aba 'Avaliação' é preenchida)", \
        Font(name=FONT, bold=True, size=13)

    summary = [
        ("Linhas exportadas", f"=COUNTA({R})", "0", "Critérios aplicáveis e automatizados exportados"),
        ("Linhas conferidas", f"=COUNTIF({H},\"<>\")", "0", "Linhas com 'Status conferido' preenchido"),
        ("Progresso da conferência", "=IFERROR(B4/B3,0)", "0%", ""),
        ("Pares conclusivos", f"=SUM({P})", "0", "Robô e humano com atende/parcial/nao_atende"),
        ("Concordância exata", f"=IFERROR(SUM({X})/B6,\"—\")", "0.0%", "Acertos / pares conclusivos"),
        ("Falsos 'não atende'", f"=COUNTIF({K},\"Falso não atende\")", "0", "Erro mais grave: acusa ausência de informação existente"),
        ("Precisão do 'não atende'",
         f"=IFERROR(COUNTIFS({R},\"nao_atende\",{K},\"Concordância\")/COUNTIFS({R},\"nao_atende\",{P},1),\"—\")",
         "0.0%", "Dos 'não atende' do robô conferidos, quantos estavam certos"),
        ("Falsos 'atende'", f"=COUNTIF({K},\"Falso atende\")", "0", "Robô aceitou indício insuficiente"),
        ("Precisão do 'atende'",
         f"=IFERROR(COUNTIFS({R},\"atende\",{K},\"Concordância\")/COUNTIFS({R},\"atende\",{P},1),\"—\")",
         "0.0%", "Dos 'atende' do robô conferidos, quantos estavam certos"),
        ("Divergências de grau", f"=COUNTIF({K},\"Divergência de grau\")", "0", "Parcial × atende/não atende"),
        ("Taxa de inconclusivos (robô)", f"=IFERROR(COUNTIF({R},\"inconclusivo\")/B3,\"—\")", "0.0%",
         "Mede cobertura: quanto o robô não conseguiu decidir"),
        ("Inconclusivos que você resolveu", f"=COUNTIFS({R},\"inconclusivo\",{H},\"<>\")-COUNTIFS({R},"
         f"\"inconclusivo\",{H},\"nao_verificavel\")", "0", "Potencial de ganho com renderização JS/novas regras"),
        ("Kappa de Cohen", "", "0.00", "Concordância além do acaso nos pares conclusivos (>0,6 bom; >0,8 muito bom)"),
    ]
    _header(ws, 2, ["Indicador", "Valor", "Como ler"])
    ws.merge_cells("C2:H2")
    for i, (label, formula, fmt, note) in enumerate(summary, 3):
        ws.cell(row=i, column=1, value=label).font = Font(name=FONT)
        cell = ws.cell(row=i, column=2, value=formula)
        cell.number_format, cell.font = fmt, bold
        ws.cell(row=i, column=3, value=note).font = Font(name=FONT, size=9, color="595959")
        ws.merge_cells(start_row=i, start_column=3, end_row=i, end_column=8)

    # Matriz de confusão robô × humano
    row0 = 32
    ws.cell(row=row0, column=1, value="Matriz de confusão — linhas: robô; colunas: conferência humana").font = bold
    cols_h = ["atende", "parcial", "nao_atende", "Total (pares)", "nao_aplicavel", "nao_verificavel", "não conferido"]
    _header(ws, row0 + 1, ["Robô \\ Humano"] + cols_h)
    for i, rs in enumerate(ROBO):
        r = row0 + 2 + i
        ws.cell(row=r, column=1, value=rs).font = bold
        for j, hs in enumerate(["atende", "parcial", "nao_atende"]):
            ws.cell(row=r, column=2 + j, value=f'=COUNTIFS({R},"{rs}",{H},"{hs}")')
        ws.cell(row=r, column=5, value=f"=SUM(B{r}:D{r})" if rs != "inconclusivo" else "")
        ws.cell(row=r, column=6, value=f'=COUNTIFS({R},"{rs}",{H},"nao_aplicavel")')
        ws.cell(row=r, column=7, value=f'=COUNTIFS({R},"{rs}",{H},"nao_verificavel")')
        ws.cell(row=r, column=8, value=f'=COUNTIF({R},"{rs}")-COUNTIFS({R},"{rs}",{H},"<>")')
    tot = row0 + 2 + 3  # linha 37: totais por coluna só das linhas conclusivas do robô
    ws.cell(row=tot + 1, column=1, value="Total (pares)").font = bold
    for j in range(3):
        col = get_column_letter(2 + j)
        ws.cell(row=tot + 1, column=2 + j, value=f"=SUM({col}{row0 + 2}:{col}{row0 + 4})")
    # Kappa de Cohen (linha 15) a partir da matriz 3×3: (n·Σdiag − Σ linha·coluna) / (n² − Σ linha·coluna)
    a, b, c_, t = row0 + 2, row0 + 3, row0 + 4, tot + 1
    ws["B15"] = (f"=IFERROR((B6*(B{a}+C{b}+D{c_})-(E{a}*B{t}+E{b}*C{t}+E{c_}*D{t}))/"
                 f"(B6^2-(E{a}*B{t}+E{b}*C{t}+E{c_}*D{t})),\"—\")")
    for r in range(row0 + 2, tot + 2):
        for j in range(1, 9):
            ws.cell(row=r, column=j).border = BOX
            if j > 1:
                ws.cell(row=r, column=j).font = Font(name=FONT)

    def breakdown(start: int, title: str, key_range: str, keys: list[str]) -> int:
        ws.cell(row=start, column=1, value=title).font = bold
        _header(ws, start + 1, ["Item", "Linhas", "Conferidas", "Pares conclusivos", "Concordância",
                                "Falso não atende", "Falso atende", "Inconclusivos (robô)"])
        for i, key in enumerate(keys):
            r = start + 2 + i
            k = f'"{key}"'
            ws.cell(row=r, column=1, value=key).font = Font(name=FONT)
            ws.cell(row=r, column=2, value=f"=COUNTIF({key_range},{k})")
            ws.cell(row=r, column=3, value=f'=COUNTIFS({key_range},{k},{H},"<>")')
            ws.cell(row=r, column=4, value=f"=COUNTIFS({key_range},{k},{P},1)")
            ws.cell(row=r, column=5, value=f'=IFERROR(COUNTIFS({key_range},{k},{X},1)/D{r},"—")').number_format = "0%"
            ws.cell(row=r, column=6, value=f'=COUNTIFS({key_range},{k},{K},"Falso não atende")')
            ws.cell(row=r, column=7, value=f'=COUNTIFS({key_range},{k},{K},"Falso atende")')
            ws.cell(row=r, column=8, value=f'=COUNTIFS({key_range},{k},{R},"inconclusivo")')
            for j in range(1, 9):
                ws.cell(row=r, column=j).border = BOX
        return start + 3 + len(keys)

    nxt = breakdown(tot + 4, "Por critério (onde ajustar regras)", CR, criterios)
    breakdown(nxt + 1, "Por entidade", E, entidades)
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    for col in "DEFGH":
        ws.column_dimensions[col].width = 15
    ws.freeze_panes = "A3"


def _ajustes(wb: Workbook) -> None:
    ws = wb.create_sheet("Ajustes")
    _header(ws, 1, ["Data", "Critério", "Problema observado", "Ajuste feito", "Regra antes", "Regra depois",
                    "Efeito na concordância"])
    for col, w in zip("ABCDEFG", (12, 9, 40, 40, 12, 12, 22)):
        ws.column_dimensions[col].width = w
    for r in range(2, 30):
        for c in range(1, 8):
            ws.cell(row=r, column=c).fill = IN_FILL
            ws.cell(row=r, column=c).border = BOX


def _carry_over(wb: Workbook, previous: Path) -> dict:
    """Reaproveita a conferência humana de uma planilha anterior (mesma entidade + critério).

    O que o avaliador verificou no portal continua válido quando só o ROBÔ mudou (nova regra,
    reprocessamento). Linhas em que o status do robô mudou são destacadas para conferência rápida;
    as métricas do "depois" passam a ser calculadas sem refazer a validação.
    """
    from openpyxl import load_workbook

    old = load_workbook(previous)
    src = old["Avaliação"]
    idx = {name: i for i, (name, _, _) in enumerate(COLS)}
    answers = {}
    for row in src.iter_rows(min_row=2, values_only=True):
        if row and row[idx["Entidade"]]:
            answers[(row[idx["Entidade"]], str(row[idx["Critério"]]))] = row
    ws = wb["Avaliação"]
    changed_fill = PatternFill("solid", fgColor="BDD7EE")
    stats = {"reaproveitadas": 0, "status_robo_mudou": 0, "sem_correspondencia": 0}
    for r in range(2, ws.max_row + 1):
        key = (ws.cell(r, idx["Entidade"] + 1).value, str(ws.cell(r, idx["Critério"] + 1).value))
        prev = answers.get(key)
        if prev is None:
            stats["sem_correspondencia"] += 1
            continue
        if prev[idx["Status conferido"]]:
            stats["reaproveitadas"] += 1
        for col in ("Status conferido", "URL onde conferiu", "Causa da divergência", "Observação"):
            if prev[idx[col]] not in (None, ""):
                ws.cell(r, idx[col] + 1).value = prev[idx[col]]
        before, now = prev[idx["Status do robô"]], ws.cell(r, idx["Status do robô"] + 1).value
        if before != now:
            stats["status_robo_mudou"] += 1
            ws.cell(r, idx["Status do robô"] + 1).fill = changed_fill
            ws.cell(r, idx["Status do robô"] + 1).comment = Comment(f"Antes: {before}. Confira esta linha.", "validacao")
    if "Ajustes" in old.sheetnames:  # mantém o histórico de ajustes
        dst = wb["Ajustes"]
        for r, row in enumerate(old["Ajustes"].iter_rows(min_row=2, values_only=True), 2):
            for c, v in enumerate(row, 1):
                if v not in (None, ""):
                    dst.cell(r, c).value = v
    return stats


def export(output: Path, slugs: list[str] | None = None, db_path=None, previous: Path | None = None) -> int:
    with repo.connect(db_path) as db:
        rows = _rows(db, slugs)
    rows.sort(key=lambda r: (r[0], tuple(int(p) for p in r[3].split("."))))
    wb = Workbook()
    _instrucoes(wb, len(rows), str(db_path or "banco padrão"))
    last = _avaliacao(wb, rows)
    lists = wb.create_sheet("Listas")
    for i, c in enumerate(CAUSAS, 1):
        lists.cell(row=i, column=1, value=c)
    lists.sheet_state = "hidden"
    entidades = sorted({r[0] for r in rows})
    criterios = sorted({r[3] for r in rows}, key=lambda x: tuple(int(p) for p in x.split(".")))
    _metricas(wb, last, entidades, criterios)
    _ajustes(wb)
    wb.move_sheet("Métricas", offset=-2)
    if previous:
        stats = _carry_over(wb, previous)
        print(f"Conferência anterior: {stats['reaproveitadas']} respostas reaproveitadas; "
              f"{stats['status_robo_mudou']} linhas com status do robô alterado (em azul, para conferir); "
              f"{stats['sem_correspondencia']} linhas novas.")
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Gera planilha de validação manual robô × humano")
    p.add_argument("--entity", action="append", help="slug da entidade (repetível); padrão: todas")
    p.add_argument("--saida", type=Path, default=Path(f"data/validacao_{date.today():%Y%m%d}.xlsx"))
    p.add_argument("--anterior", type=Path, help="planilha já conferida: reaproveita as respostas humanas")
    a = p.parse_args()
    if a.anterior and a.anterior.resolve() == a.saida.resolve():
        p.error("--saida deve ser diferente de --anterior (para não apagar a conferência)")
    n = export(a.saida, a.entity, previous=a.anterior)
    print(f"{n} linhas exportadas para {a.saida}")


if __name__ == "__main__":
    main()
