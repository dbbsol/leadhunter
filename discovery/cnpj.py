"""Utilidades de CNPJ. Validação local + consulta opcional à BrasilAPI (dados abertos da Receita)."""
from __future__ import annotations

import re

import requests


def only_digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def is_valid_cnpj(value) -> bool:
    c = only_digits(value)
    if len(c) != 14 or len(set(c)) == 1:
        return False

    def dv(base: str, weights: list[int]) -> str:
        total = sum(int(d) * w for d, w in zip(base, weights))
        r = total % 11
        return "0" if r < 2 else str(11 - r)

    d1 = dv(c[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(c[:12] + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return c[12:] == d1 + d2


def format_cnpj(value) -> str:
    c = only_digits(value)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}" if len(c) == 14 else str(value or "")


def fetch_cnpj_brasilapi(cnpj: str, timeout: float = 8.0) -> dict | None:
    """Consulta opcional (serviço comunitário gratuito baseado nos dados abertos da Receita).
    Pode ficar indisponível ou limitar requisições: o sistema segue funcionando sem ela."""
    c = only_digits(cnpj)
    if not is_valid_cnpj(c):
        return None
    try:
        r = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{c}", timeout=timeout,
                         headers={"User-Agent": "LeadHunterBot/1.0"})
        if r.status_code != 200:
            return None
        d = r.json()
        return {
            "razao_social": d.get("razao_social"),
            "situacao": d.get("descricao_situacao_cadastral"),
            "abertura": d.get("data_inicio_atividade"),
            "porte": d.get("porte") or d.get("descricao_porte"),
            "cnae": d.get("cnae_fiscal_descricao"),
            "municipio": d.get("municipio"),
            "uf": d.get("uf"),
        }
    except Exception:
        return None
