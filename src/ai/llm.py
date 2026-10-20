"""Camada opcional de IA para critérios que exigem interpretação de texto.

Onde a IA entra (e onde não entra):
- NÃO recebe a página inteira nem decide "o portal está em conformidade?";
- recebe só trechos pré-selecionados pelas regras (custo baixo e foco) e uma pergunta
  fechada sobre UM critério;
- precisa responder JSON com status, justificativa e uma CITAÇÃO LITERAL de um dos
  trechos; se a citação não existir no texto fornecido, a resposta é descartada
  (barreira contra alucinação);
- divergência entre regra e IA vira `inconclusivo` + revisão humana (ver rules.criterios._with_llm);
- respostas ficam em cache pelo hash do prompt: reprocessar não gera custo novo e o
  mesmo prompt sempre devolve a mesma decisão (rastreabilidade).

Desligada por padrão. Para ativar:
  MPRJ_LLM_PROVIDER=anthropic|openai  MPRJ_LLM_MODEL=<id do modelo>
  ANTHROPIC_API_KEY=... ou OPENAI_API_KEY=...   (opcional: MPRJ_LLM_MAX_CALLS=50)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Callable

import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "llm_cache"
VALID = {"atende", "parcial", "nao_atende", "inconclusivo"}

SYSTEM = (
    "Você é um auditor de transparência pública. Avalie SOMENTE o critério perguntado e SOMENTE "
    "com base nos trechos fornecidos. Não use conhecimento externo. Se os trechos não permitirem "
    "concluir, responda status 'inconclusivo'. Responda apenas um objeto JSON com as chaves: "
    'status ("atende"|"parcial"|"nao_atende"|"inconclusivo"), confianca (0 a 1), justificativa '
    "(até 2 frases), citacao (cópia LITERAL de até 200 caracteres de um dos trechos) e url "
    "(a url do trecho citado)."
)

Transport = Callable[[str, str], str]


def _ws(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


class LLMJudge:
    """Juiz de IA opcional para critérios semânticos (§11 da documentação).

    Recebe só trechos pré-filtrados, exige citação literal do texto (conferida contra os trechos),
    tem cache por hash do prompt e teto de chamadas por execução. Desligado por padrão.
    """
    def __init__(self, *, provider: str, model: str, transport: Transport | None = None,
                 api_key: str | None = None, max_calls: int = 50, cache_dir: Path | None = CACHE_DIR):
        self.provider, self.model, self.api_key = provider, model, api_key
        self.transport = transport or self._http_transport
        self.max_calls, self.calls, self.cache_dir = max_calls, 0, cache_dir
        self.log: list[dict] = []

    @classmethod
    def from_env(cls) -> "LLMJudge | None":
        """Cria o juiz a partir das variáveis de ambiente, ou None se a IA não estiver configurada."""
        provider = os.environ.get("MPRJ_LLM_PROVIDER", "").strip().lower()
        model = os.environ.get("MPRJ_LLM_MODEL", "").strip()
        if provider not in {"anthropic", "openai"} or not model:
            return None
        key = os.environ.get("ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY")
        if not key:
            return None
        return cls(provider=provider, model=model, api_key=key,
                   max_calls=int(os.environ.get("MPRJ_LLM_MAX_CALLS", "50")))

    # -- transporte HTTP -----------------------------------------------------
    def _http_transport(self, system: str, user: str) -> str:
        if self.provider == "anthropic":
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
                "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": self.model, "max_tokens": 600, "temperature": 0, "system": system,
                      "messages": [{"role": "user", "content": user}]})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json().get("content", []))
        r = requests.post("https://api.openai.com/v1/chat/completions", timeout=60,
                          headers={"Authorization": f"Bearer {self.api_key}"},
                          json={"model": self.model, "temperature": 0,
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    # -- julgamento ------------------------------------------------------------
    def judge(self, criterion_id: str, question: str, snippets: list[dict]) -> dict | None:
        """Pergunta ao modelo se os trechos atendem ao critério.

        Devolve o veredito validado, ou None quando não há resposta utilizável (teto atingido, erro,
        citação que não aparece nos trechos ou veredito inconclusivo). Toda chamada fica registrada
        em `self.log`.
        """
        user = json.dumps({"criterio": criterion_id, "pergunta": question,
                           "trechos": [{"url": s["url"], "texto": s["texto"][:1500]} for s in snippets[:6]]},
                          ensure_ascii=False)
        prompt_sha = hashlib.sha256(f"{self.model}\n{SYSTEM}\n{user}".encode()).hexdigest()
        raw = self._cache_get(prompt_sha)
        if raw is None:
            if self.calls >= self.max_calls:
                self.log.append({"criterio": criterion_id, "evento": "orcamento_esgotado"})
                return None
            self.calls += 1
            try:
                raw = self.transport(SYSTEM, user)
            except Exception as exc:  # falha da IA nunca derruba a avaliação
                self.log.append({"criterio": criterion_id, "evento": "erro", "tipo": type(exc).__name__})
                return None
            self._cache_put(prompt_sha, raw)
        verdict = self.validate(raw, snippets)
        self.log.append({"criterio": criterion_id, "prompt_sha256": prompt_sha,
                         "evento": "aceito" if verdict else "descartado"})
        if verdict is None or verdict["status"] == "inconclusivo":
            return None
        verdict.update({"modelo": f"{self.provider}:{self.model}", "prompt_sha256": prompt_sha})
        return verdict

    @staticmethod
    def validate(raw: str, snippets: list[dict]) -> dict | None:
        """Aceita só JSON bem-formado, status conhecido e citação literal presente nos trechos."""
        match = re.search(r"\{.*\}", raw or "", re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except ValueError:
            return None
        status = str(data.get("status", "")).strip().lower()
        quote = str(data.get("citacao", "")).strip()
        try:
            conf = float(data.get("confianca", 0))
        except (TypeError, ValueError):
            return None
        if status not in VALID or not 0 <= conf <= 1:
            return None
        if status != "inconclusivo":
            source = next((s for s in snippets if quote and _ws(quote) in _ws(s["texto"])), None)
            if source is None:
                return None  # citação inventada ou parafraseada
            data["url"] = source["url"]
        return {"status": status, "confianca": conf, "justificativa": str(data.get("justificativa", ""))[:400],
                "citacao": quote[:300], "url": data.get("url")}

    def _cache_get(self, key: str) -> str | None:
        if not self.cache_dir:
            return None
        path = self.cache_dir / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8"))["raw"] if path.exists() else None

    def _cache_put(self, key: str, raw: str) -> None:
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{key}.json").write_text(json.dumps({"model": self.model, "raw": raw},
                                                                  ensure_ascii=False), encoding="utf-8")
