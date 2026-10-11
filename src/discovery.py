"""Explorador limitado de páginas HTML públicas para triagem de evidências.

Executar: python -m src.discovery
A descoberta NÃO produz declaração de conformidade legal.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlsplit

import requests
from bs4 import BeautifulSoup
from src.crawler import HEADERS, TIMEOUT, is_public_http_url

ROOT = Path(__file__).resolve().parents[1]
TERMS = ("transparencia", "licitacao", "contrato", "despesa", "receita", "pesquisa")
MAX_BYTES = 2_000_000


def normalize(value: str) -> str:
    return "".join(x for x in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(x)).casefold()


def same_origin(url: str, root: str) -> bool:
    a, b = urlsplit(url), urlsplit(root)
    return (is_public_http_url(url) and a.scheme == b.scheme and a.hostname == b.hostname
            and a.port == b.port and not re.search(r"\.(pdf|zip|docx?|xlsx?|csv|jpe?g|png)$", a.path, re.I))


def extract_html(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    candidates = []
    for tag in soup.select("a[href]")[:1200]:
        link = urldefrag(urljoin(url, tag.get("href", "")))[0]
        label = tag.get_text(" ", strip=True)[:160]
        if is_public_http_url(link) and any(term in normalize(label + " " + link) for term in TERMS):
            candidates.append({"text": label, "url": link})
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return {"title": title, "text_excerpt": " ".join(soup.stripped_strings)[:1500],
            "candidate_links": candidates[:50]}


def discover(root: str, max_pages: int = 4, delay: float = 1.0, session=None) -> dict:
    if not is_public_http_url(root) or not 1 <= max_pages <= 12 or delay < 0.5:
        raise ValueError("Origem, limite ou intervalo inválido")
    result = {"root": root, "collected_at": datetime.now(timezone.utc).isoformat(),
              "pages": [], "errors": [], "scope": "HTML da mesma origem; sem JavaScript"}
    pending, seen = deque([root]), set()
    client = session or requests.Session()
    try:
        while pending and len(result["pages"]) < max_pages:
            url = pending.popleft()
            if url in seen or not same_origin(url, root):
                continue
            seen.add(url)
            try:
                response = client.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=False)
                status = response.status_code
                ctype = response.headers.get("Content-Type", "").lower()
                body = response.content
                if status != 200 or "text/html" not in ctype or len(body) > MAX_BYTES:
                    result["errors"].append({"url": url, "status": status, "reason": "HTML indisponível ou acima do limite"})
                    continue
                extracted = extract_html(url, response.text)
                result["pages"].append({"url": url, "status": 200,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "collected_at": datetime.now(timezone.utc).isoformat(), **extracted})
                for item in extracted["candidate_links"]:
                    target = item["url"]
                    if same_origin(target, root) and target not in seen and target not in pending:
                        pending.append(target)
            except requests.RequestException as exc:
                result["errors"].append({"url": url, "reason": type(exc).__name__})
            if pending:
                time.sleep(delay)
    finally:
        if session is None:
            client.close()
    return result


def main():
    entries = json.loads((ROOT / "config" / "municipios.json").read_text(encoding="utf-8"))
    output = []
    for entry in entries:
        print("Explorando:", entry["nome"], flush=True)
        output.append({"entity": entry["nome"], "discovery": discover(entry["site"])})
    dest = ROOT / "data" / "descoberta.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Evidências registradas:", dest)


if __name__ == "__main__":
    main()
