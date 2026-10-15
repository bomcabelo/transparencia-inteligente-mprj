"""Identificação do fornecedor/tecnologia do portal.

Muitos municípios usam os mesmos fornecedores de portal da transparência. Saber o
fornecedor permite (1) ativar adaptadores estruturados (ex.: API GeoSIAP), que são
mais confiáveis que leitura de HTML, e (2) agrupar falhas por tecnologia — quando
um fornecedor muda o layout, o efeito aparece em vários municípios ao mesmo tempo.
"""
from __future__ import annotations

import re

from src.page import Page, norm

SIGNATURES: list[tuple[str, str]] = [
    ("GeoSIAP", r"geosiap"),
    ("Betha", r"\bbetha\b|betha\.cloud"),
    ("IPM Atende.Net", r"atende\.net|ipm sistemas"),
    ("Fiorilli", r"fiorilli|scpi"),
    ("Elotech", r"elotech|oxy\.elotech"),
    ("Portal Fácil", r"portalfacil|portal facil"),
    ("e-Cidade/DBSeller", r"e-?cidade|dbseller"),
    ("Siplanweb", r"siplanweb"),
    ("Agili", r"\bagili\b|agilicloud|agili\.com"),  # não casar "agilidade"
    ("Instar", r"instar(?:\.com|\s+tecnologia)"),
    ("Governa/TCERJ", r"sistemagoverna|governa\b"),
    ("WordPress", r"wp-content|wordpress"),
    ("Joomla", r"joomla"),
    ("Drupal", r"drupal"),
    ("Liferay", r"liferay"),
    ("Plone", r"plone"),
]


CMS = {"WordPress", "Joomla", "Drupal", "Liferay", "Plone"}
# Fornecedores de PORTAL DA TRANSPARÊNCIA (não CMS): link para eles costuma ser o próprio portal.
VENDOR_URL = re.compile("|".join(p for n, p in SIGNATURES if n not in CMS), re.I)


def detect(pages: list[Page]) -> dict[str, list[str]]:
    """Retorna {fornecedor: [hosts onde foi observado]} usando domínio, meta generator e texto."""
    found: dict[str, set[str]] = {}
    for page in pages:
        probe = norm(" ".join([page.final_url, page.meta.get("generator", ""), page.title,
                               page.text[-3000:], " ".join(l["url"] for l in page.links[:300])]))
        for name, pattern in SIGNATURES:
            if re.search(pattern, probe):
                found.setdefault(name, set()).add(page.host)
    return {k: sorted(v) for k, v in found.items()}
