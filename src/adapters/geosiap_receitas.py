"""Etapa 9.1: inspeciona Swagger e consulta opcionalmente receitas públicas GeoSIAP.

Sem --consultar, somente lê a especificação OpenAPI/Swagger.
Não determina conformidade legal. Não grava linhas individuais nem dados pessoais.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ORIGEM = "https://japeri.geosiap.net.br/portal-transparencia"
SWAGGER_URL = f"{ORIGEM}/api-docs/v1/swagger.json"
API_BASE = f"{ORIGEM}/api"
CAMINHO = "/execucao/receitas/proprias/receitas_proprias"
CABECALHOS = {"User-Agent": "TransparenciaInteligenteMPRJ-POC/0.1", "Accept": "application/json"}
LIMITE_BYTES = 5_000_000


def especificacao(*, arquivo: Path | None = None, session: Any = requests) -> dict:
    if arquivo is not None:
        doc = json.loads(arquivo.read_text(encoding="utf-8-sig"))
    else:
        resposta = session.get(SWAGGER_URL, headers=CABECALHOS, timeout=25)
        resposta.raise_for_status()
        doc = resposta.json()
    if not isinstance(doc, dict) or not isinstance(doc.get("paths"), dict):
        raise ValueError("Especificação Swagger inválida: campo 'paths' ausente")
    return doc


def descrever(doc: dict, caminho: str = CAMINHO) -> dict:
    operacao = doc.get("paths", {}).get(caminho, {}).get("get")
    if not isinstance(operacao, dict):
        raise ValueError(f"Endpoint GET não documentado: {caminho}")
    parametros = list(doc.get("paths", {}).get(caminho, {}).get("parameters", [])) + list(operacao.get("parameters", []))
    return {
        "endpoint": caminho,
        "descricao": operacao.get("summary") or operacao.get("description"),
        "parametros": [{"nome": p.get("name"), "local": p.get("in"), "obrigatorio": p.get("required", False),
                         "tipo": p.get("type"), "descricao": p.get("description", "")} for p in parametros],
        "respostas_documentadas": list(operacao.get("responses", {}).keys()),
        "schema_200": operacao.get("responses", {}).get("200", {}).get("schema", {}),
    }


def validar_parametros(descricao: dict, parametros: dict[str, str]) -> None:
    definidos = {x["nome"] for x in descricao["parametros"] if x["local"] == "query"}
    obrigatorios = {x["nome"] for x in descricao["parametros"] if x["local"] == "query" and x["obrigatorio"]}
    faltantes = sorted(obrigatorios - parametros.keys())
    desconhecidos = sorted(parametros.keys() - definidos)
    if faltantes:
        raise ValueError("Parâmetros obrigatórios ausentes: " + ", ".join(faltantes))
    if desconhecidos:
        raise ValueError("Parâmetros não documentados: " + ", ".join(desconhecidos))


def parametros_cli(valores: list[str]) -> dict[str, str]:
    resultado = {}
    for elemento in valores:
        nome, separador, valor = elemento.partition("=")
        if not separador or not nome.strip() or not valor.strip():
            raise ValueError("Use --param nome=valor (com valor não vazio)")
        if nome in resultado:
            raise ValueError(f"Parâmetro duplicado: {nome}")
        resultado[nome] = valor
    return resultado


def _contagem(payload: Any) -> tuple[str, int | None, list[str]]:
    if isinstance(payload, list):
        amostra = next((x for x in payload if isinstance(x, dict)), {})
        return "lista", len(payload), sorted(amostra.keys())
    if isinstance(payload, dict):
        candidatos = [(k, v) for k, v in payload.items() if isinstance(v, list)]
        if len(candidatos) == 1:
            campo, registros = candidatos[0]
            amostra = next((x for x in registros if isinstance(x, dict)), {})
            return f"objeto com lista '{campo}'", len(registros), sorted(amostra.keys())
        return "objeto", None, sorted(payload.keys())
    return type(payload).__name__, None, []


def consultar(descricao: dict, parametros: dict[str, str], *, session: Any = requests) -> dict:
    validar_parametros(descricao, parametros)
    url = API_BASE + descricao["endpoint"]
    momento = datetime.now(timezone.utc).isoformat()
    resumo = {
        "plataforma": "GeoSIAP", "municipio": "Japeri/RJ", "criterio_candidato": "3.1",
        "endpoint": descricao["endpoint"], "parametros": parametros, "consultado_em_utc": momento,
        "origem": url, "status_avaliacao_legal": "inconclusivo",
        "nota": "Diagnóstico técnico; não comprova integralidade, atualização ou conformidade legal."
    }
    try:
        with session.get(url, params=parametros, headers=CABECALHOS, timeout=45, stream=True) as resposta:
            resumo["http_status"] = resposta.status_code
            resumo["url_consultada"] = resposta.url
            resumo["tipo_conteudo"] = resposta.headers.get("Content-Type", "")
            if resposta.status_code != 200:
                resumo["resultado_tecnico"] = "falha_http"
                return resumo
            if "json" not in resumo["tipo_conteudo"].lower():
                resumo["resultado_tecnico"] = "tipo_inesperado"
                return resumo
            dados = bytearray()
            for bloco in resposta.iter_content(chunk_size=65536):
                dados.extend(bloco)
                if len(dados) > LIMITE_BYTES:
                    resumo["resultado_tecnico"] = "resposta_muito_grande"
                    return resumo
            resumo["sha256_resposta"] = hashlib.sha256(dados).hexdigest()
            try:
                payload = json.loads(dados.decode("utf-8-sig"))
            except (UnicodeError, ValueError):
                resumo["resultado_tecnico"] = "json_invalido"
                return resumo
            formato, contagem, chaves = _contagem(payload)
            resumo.update({"formato": formato, "quantidade_registros": contagem,
                           "campos_observados": chaves, "resultado_tecnico": "consulta_realizada"})
    except requests.RequestException as exc:
        resumo["resultado_tecnico"] = "falha_rede"
        resumo["erro_tipo"] = type(exc).__name__  # não incluir URLs com possíveis parâmetros privados
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspecionar e consultar receitas públicas GeoSIAP")
    parser.add_argument("--swagger-file", type=Path, help="Swagger JSON local (evita nova chamada)")
    parser.add_argument("--consultar", action="store_true", help="Executar GET público após verificar parâmetros")
    parser.add_argument("--param", action="append", default=[], help="Parâmetro documentado no formato nome=valor")
    parser.add_argument("--output", type=Path, default=Path("data/geosiap_japeri_receitas_diagnostico.json"))
    args = parser.parse_args()
    try:
        doc = especificacao(arquivo=args.swagger_file)
        info = descrever(doc)
        if not args.consultar:
            print(json.dumps(info, ensure_ascii=False, indent=2))
            print("Nenhuma consulta de receitas foi realizada. Verifique os parâmetros antes de usar --consultar.")
            return
        p = parametros_cli(args.param)
        resultado = consultar(info, p)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Status técnico:", resultado["resultado_tecnico"])
        print("HTTP:", resultado.get("http_status", "sem resposta"))
        print("Registros:", resultado.get("quantidade_registros", "não determinado"))
        print("Resumo salvo em:", args.output)
    except (ValueError, requests.RequestException, OSError) as exc:
        parser.exit(2, f"Erro: {exc}\n")


if __name__ == "__main__":
    main()
