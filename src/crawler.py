"""Coleta inicial, conservadora e auditável de páginas institucionais.

Uso: python -m src.crawler
Não conclui conformidade jurídica: registra evidências observadas.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "municipios.json"
OUTPUT = ROOT / "data" / "coletas.json"
HEADERS = {"User-Agent": "TransparenciaInteligenteMPRJ-POC/0.1 (pesquisa academica; requisicoes limitadas)"}
TIMEOUT = 15


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_public_http_url(url: str) -> bool:
    """Barreira básica contra endereços locais; não substitui proteção de rede."""
    from ipaddress import ip_address
    host = urlparse(url).hostname
    if urlparse(url).scheme not in {"https", "http"} or not host:
        return False
    if host.lower() == "localhost" or host.lower().endswith((".local", ".internal")):
        return False
    try:
        return ip_address(host).is_global
    except ValueError:
        return True


def collect_page(url: str, session: requests.Session | None = None) -> dict:
    """Coleta somente a URL informada, sem seguir links automaticamente."""
    evidence = {"url": url, "collected_at": utc_now(), "http_status": None,
                "title": None, "links": [], "error": None, "content_type": None}
    if not is_public_http_url(url):
        evidence["error"] = "URL não permitida"
        return evidence
    client = session or requests.Session()
    try:
        response = client.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False)
        evidence["http_status"] = response.status_code
        evidence["content_type"] = response.headers.get("content-type", "")
        if 300 <= response.status_code < 400:
            location = response.headers.get("location", "")
            target = urljoin(url, location)
            evidence["redirect_to"] = target if is_public_http_url(target) else None
            evidence["error"] = "Redirecionamento não seguido automaticamente"
            return evidence
        if response.status_code != 200:
            evidence["error"] = f"HTTP {response.status_code}"
            return evidence
        if "text/html" not in evidence["content_type"].lower():
            evidence["error"] = "Conteúdo não HTML"
            return evidence
        soup = BeautifulSoup(response.text[:2_000_000], "html.parser")
        evidence["title"] = soup.title.get_text(" ", strip=True) if soup.title else ""
        for anchor in soup.select("a[href]")[:2500]:
            href = urljoin(url, anchor.get("href", ""))
            if not is_public_http_url(href):
                continue
            label = anchor.get_text(" ", strip=True)[:180]
            evidence["links"].append({"text": label, "url": href})
        evidence["links_count"] = len(evidence["links"])
    except requests.RequestException as exc:
        evidence["error"] = f"Erro de conexão: {type(exc).__name__}"
    finally:
        if session is None:
            client.close()
    return evidence


def evaluate_initial(page: dict, portal_url: str | None = None) -> list[dict]:
    """Sinal técnico para 1.1; evidência candidata para 1.2.

    Status de 1.2 nunca é 'não atende' sem auditoria da renderização.
    """
    success = page["http_status"] == 200 and page["error"] is None
    out = [{
        "criterion_id": "1.1",
        "status": "atende" if success else "inconclusivo",
        "finding": "Página oficial acessível via HTTP" if success else "Não foi possível confirmar acesso",
        "evidence_url": page["url"], "evaluated_at": page["collected_at"],
        "limitation": "Verificação técnica de acesso; não comprova integralmente atendimento jurídico"
    }]
    matches = []
    for link in page.get("links", []):
        label = link["text"]
        address = link["url"]
        if re.search(r"transpar[eê]ncia", label, re.I) or (portal_url and address.rstrip("/") == portal_url.rstrip("/")):
            matches.append(link)
    out.append({
        "criterion_id": "1.2",
        "status": "inconclusivo",
        "finding": "Link candidato identificado; visibilidade na capa exige validação visual"
        if matches else "Link não identificado no HTML inicial; verificar conteúdo dinâmico",
        "evidence_url": page["url"],
        "candidate_links": matches[:10],
        "evaluated_at": page["collected_at"],
    })
    return out


def main() -> None:
    entities = json.loads(CONFIG.read_text(encoding="utf-8"))
    results = []
    for entity in entities:
        print(f"Coletando: {entity['nome']}")
        url = entity.get("site")
        if url:
            page = collect_page(url)
            criteria = evaluate_initial(page, entity.get("portal"))
        else:
            page = {"url": None, "collected_at": utc_now(), "error": "URL oficial pendente de confirmação", "http_status": None}
            criteria = []
        results.append({"entity": entity, "page": page, "criteria": criteria})
        time.sleep(1.0)  # evita rajadas entre entidades
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Resultado salvo em: {OUTPUT}")
    print("ATENÇÃO: resultados preliminares; critérios exigem revisão das evidências.")


if __name__ == "__main__":
    main()
