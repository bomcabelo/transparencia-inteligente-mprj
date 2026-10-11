"""Associação estrita de evidências ao município, sem dependência do dashboard."""
from __future__ import annotations
import unicodedata

def normalizar_municipio(nome: str) -> str:
    """Normaliza grafia, sigla UF e prefixos institucionais, sem aproximação difusa."""
    texto = str(nome or '').split('/')[0].strip()
    texto = ''.join(c for c in unicodedata.normalize('NFKD', texto)
                    if not unicodedata.combining(c)).casefold()
    for prefixo in ('prefeitura municipal de ', 'municipio de ', 'prefeitura de '):
        if texto.startswith(prefixo):
            texto = texto[len(prefixo):]
            break
    return ' '.join(texto.split())


def filtrar_evidencias_por_municipio(evidencias: list[dict], municipio: dict) -> list[dict]:
    """Associação exata pelo nome, evitando evidências de outra cidade."""
    nome = normalizar_municipio(municipio.get('name', ''))
    return [e for e in evidencias
            if normalizar_municipio(e.get('municipality', '')) == nome]

