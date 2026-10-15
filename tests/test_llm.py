import json

from src.ai.llm import LLMJudge
from src.rules.base import Context, Result
from src.rules.criterios import _with_llm

SNIPPETS = [{"url": "https://x/esic", "texto": "Para registrar o pedido é obrigatório anexar cópia do RG e "
                                               "declaração de responsabilidade assinada."}]


def judge(answer: str, **kw):
    return LLMJudge(provider="anthropic", model="teste", transport=lambda s, u: answer, cache_dir=None, **kw)


def test_accepts_literal_quote():
    ans = json.dumps({"status": "nao_atende", "confianca": 0.9, "justificativa": "Exige documentos.",
                      "citacao": "obrigatório anexar cópia do RG"})
    v = judge(ans).judge("15.2", "pergunta", SNIPPETS)
    assert v["status"] == "nao_atende" and v["url"] == "https://x/esic" and len(v["prompt_sha256"]) == 64


def test_rejects_invented_quote_and_bad_json():
    ans = json.dumps({"status": "atende", "confianca": 0.9, "justificativa": "ok", "citacao": "pedido simples"})
    assert judge(ans).judge("15.2", "p", SNIPPETS) is None
    assert judge("não sei").judge("15.2", "p", SNIPPETS) is None
    assert judge(json.dumps({"status": "talvez", "confianca": 2})).judge("15.2", "p", SNIPPETS) is None


def test_budget_and_cache(tmp_path):
    calls = []
    ans = json.dumps({"status": "nao_atende", "confianca": 0.8, "justificativa": "x", "citacao": "cópia do RG"})
    j = LLMJudge(provider="openai", model="m", transport=lambda s, u: calls.append(1) or ans,
                 cache_dir=tmp_path, max_calls=1)
    assert j.judge("15.2", "p", SNIPPETS) and j.judge("15.2", "p", SNIPPETS)  # 2ª vem do cache
    assert len(calls) == 1
    assert j.judge("15.2", "outra pergunta", SNIPPETS) is None                 # orçamento esgotado
    assert j.log[-1]["evento"] == "orcamento_esgotado"


class FakePage:
    final_url, text, title = "https://x/esic", SNIPPETS[0]["texto"], "e-SIC"
    ntext = "para registrar o pedido e obrigatorio anexar copia do rg e declaracao"


def test_rule_and_ai_disagreement_goes_to_human_review():
    ans = json.dumps({"status": "atende", "confianca": 0.9, "justificativa": "x", "citacao": "registrar o pedido"})
    ctx = Context(entity={}, collection=None, today=None, methodology={}, llm=judge(ans))
    base = Result("15.2", "nao_atende", 0.7, "regra")
    out = _with_llm(ctx, base, "pergunta", [FakePage()], r"pedido")
    assert out.status == "inconclusivo" and out.needs_review and out.method == "regra+ia"


def test_ai_fills_inconclusive_with_capped_confidence():
    ans = json.dumps({"status": "nao_atende", "confianca": 0.99, "justificativa": "x", "citacao": "cópia do RG"})
    ctx = Context(entity={}, collection=None, today=None, methodology={}, llm=judge(ans))
    out = _with_llm(ctx, Result("15.2", "inconclusivo", 0.3, "regra"), "p", [FakePage()], r"pedido")
    assert out.status == "nao_atende" and out.confidence == 0.75 and out.evidences[-1].kind == "ia"


def test_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv("MPRJ_LLM_PROVIDER", raising=False)
    assert LLMJudge.from_env() is None
