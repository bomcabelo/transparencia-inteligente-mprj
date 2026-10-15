"""Contrato das regras de avaliação.

Cada critério implementado é uma função pura `(Context) -> Result`, registrada com
metadados (complexidade, técnica, versão). Pureza + snapshots = reprodutibilidade:
a mesma coleta avaliada pela mesma versão de regra produz o mesmo resultado.

Princípios codificados aqui:
- presença exige evidência apontável (URL + trecho/elemento);
- ausência só vira `nao_atende` quando a coleta foi suficiente e a página relevante
  não depende de JavaScript não renderizado; caso contrário, `inconclusivo`;
- falha de acesso nunca é `nao_atende`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Callable

from src.collector import Collection
from src.page import Page
from src.themes import pages_for

STATUSES = ("atende", "parcial", "nao_atende", "nao_aplicavel", "inconclusivo", "nao_avaliado")


@dataclass
class Evidence:
    kind: str  # pagina | link | formulario | tabela | documento | texto | controle | api | ausencia | ia
    url: str | None
    title: str = ""
    snippet: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class Result:
    criterion_id: str
    status: str
    confidence: float
    finding: str
    evidences: list[Evidence] = field(default_factory=list)
    method: str = "regra"
    rule_version: str = ""
    needs_review: bool = False
    ai: dict | None = None

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"status inválido: {self.status}")
        self.confidence = round(max(0.0, min(1.0, self.confidence)), 2)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Context:
    entity: dict
    collection: Collection
    today: date
    methodology: dict
    llm: object | None = None  # src.ai.llm.LLMJudge | None
    extra_evidence: dict = field(default_factory=dict)  # evidências de adaptadores (ex.: API GeoSIAP)

    @property
    def pages(self) -> list[Page]:
        return self.collection.ok_pages

    @property
    def site(self) -> Page | None:
        p = self.collection.page("site")
        return p if p and p.status == 200 else None

    @property
    def portal(self) -> Page | None:
        p = self.collection.page("portal")
        return p if p and p.status == 200 else None

    def themed(self, theme: str, minimum: float = 3.0) -> list[Page]:
        return pages_for(self.pages, theme, minimum)


Rule = Callable[[Context], Result]
REGISTRY: dict[str, dict] = {}


def rule(criterion_id: str, *, complexidade: str, tecnica: str, versao: str = "1.0", semantico: bool = False):
    def decorator(func: Rule) -> Rule:
        REGISTRY[criterion_id] = {"func": func, "complexidade": complexidade, "tecnica": tecnica,
                                  "versao": versao, "semantico": semantico, "doc": (func.__doc__ or "").strip()}
        return func
    return decorator


def page_ev(page: Page, snippet: str = "", kind: str = "pagina", **detail) -> Evidence:
    return Evidence(kind=kind, url=page.final_url, title=page.title, snippet=snippet or "", detail=detail)


def absence(ctx: Context, cid: str, what: str, *, relevant: list[Page] | None = None,
            confidence: float = 0.6) -> Result:
    """Decide entre `nao_atende` e `inconclusivo` quando nada foi encontrado."""
    col = ctx.collection
    scope = relevant if relevant is not None else ctx.pages
    dynamic = [p for p in scope if p.looks_dynamic()]
    examined = [Evidence("ausencia", p.final_url, p.title, detail={"tema": dict(list(p.themes.items())[:3])})
                for p in scope[:8]]
    if not col.sufficient:
        return Result(cid, "inconclusivo", 0.3, f"Não encontrado: {what}. A coleta foi insuficiente "
                      f"({col.health['paginas_ok']} páginas válidas). Falha de acesso não é desconformidade.",
                      examined, needs_review=True)
    if dynamic and len(dynamic) >= max(1, len(scope) // 2):
        return Result(cid, "inconclusivo", 0.35, f"Não encontrado: {what}. As páginas relevantes dependem de "
                      "JavaScript não renderizado (ativar MPRJ_RENDER_JS=1).", examined, needs_review=True)
    return Result(cid, "nao_atende", confidence,
                  f"Não encontrado: {what}. Foram examinadas {len(ctx.pages)} páginas "
                  f"(temas cobertos: {', '.join(col.health['temas_cobertos']) or 'nenhum'}).",
                  examined, needs_review=confidence < 0.7)
