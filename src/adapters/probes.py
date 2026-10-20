"""Sondas estruturadas por fornecedor (adaptadores).

Quando o fingerprint identifica um fornecedor com API pública documentada, a sonda
consulta a API e devolve evidências estruturadas que as regras usam como fonte
preferencial (mais confiável que HTML). Hoje: GeoSIAP (receitas e empenhos).
Novos fornecedores = nova função registrada em PROBES, sem alterar as regras.
"""
from __future__ import annotations

from datetime import date

import requests

from src.adapters import geosiap_receitas as geo

EMPENHOS = "/execucao/empenhos/empenhos"
CAMPOS_4_1 = {"nr_empenho", "vl_empenhado_per", "vl_liquidado_per", "vl_pago_per"}
CAMPOS_3_1 = {"ds_plano_conta", "vl_previsto", "vl_total"}


def _probe_geosiap(entity: dict, year: int, session=requests) -> tuple[dict, list[dict]]:
    cfg = entity.get("geosiap") or {}
    if not cfg.get("id_entidade"):
        return {}, [{"sonda": "GeoSIAP", "erro": "id_entidade não cadastrado"}]
    evidence, log = {}, []
    try:
        doc = geo.especificacao(session=session)
    except Exception as exc:
        return {}, [{"sonda": "GeoSIAP", "erro": f"swagger indisponível: {type(exc).__name__}"}]
    for cid, path, needed in (("3.1", geo.CAMINHO, CAMPOS_3_1), ("4.1", EMPENHOS, CAMPOS_4_1)):
        try:
            info = geo.descrever(doc, path)
            params = {"id_entidade": str(cfg["id_entidade"]), "ano": str(year)}
            if any(p["nome"] == "layout" for p in info["parametros"]):
                params["layout"] = "anual"
            out = geo.consultar(info, params, session=session)
        except Exception as exc:  # parâmetros mudaram, endpoint removido etc.
            log.append({"sonda": "GeoSIAP", "criterio": cid, "erro": f"{type(exc).__name__}: {exc}"})
            continue
        fields = set(out.get("campos_observados") or [])
        ok = out.get("resultado_tecnico") == "consulta_realizada" and (out.get("quantidade_registros") or 0) > 0 \
            and needed <= fields
        evidence[cid] = {"ok": ok, "url": out.get("url_consultada") or out.get("origem"),
                         "resumo": f"{out.get('quantidade_registros')} registros; campos: "
                                   f"{', '.join(sorted(fields & needed)) or 'nenhum dos esperados'}",
                         "sha256": out.get("sha256_resposta"), "http_status": out.get("http_status"),
                         "campos_ausentes": sorted(needed - fields), "consultado_em": out.get("consultado_em_utc")}
        log.append({"sonda": "GeoSIAP", "criterio": cid, "resultado": out.get("resultado_tecnico")})
    return evidence, log


PROBES = {"GeoSIAP": _probe_geosiap}


def run_probes(entity: dict, vendors: dict, ref: date) -> tuple[dict, list[dict]]:
    """Consulta APIs públicas dos fornecedores de portal detectados (hoje: GeoSIAP).

    Returns:
        (evidências por critério, log das consultas). As evidências complementam a análise do HTML.
    """
    evidence, log = {}, []
    for vendor, probe in PROBES.items():
        if vendor in vendors or (vendor == "GeoSIAP" and entity.get("geosiap")):
            ev, lg = probe(entity, ref.year)
            evidence.update(ev)
            log.extend(lg)
    return evidence, log
