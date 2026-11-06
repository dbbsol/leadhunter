"""Modelo de evidência: separa fato observado, hipótese, oportunidade e informação não encontrada."""
from __future__ import annotations

import hashlib

from core.config import now_iso

TIPOS = ("fato", "hipotese", "oportunidade", "nao_encontrado")
ROTULOS = {
    "fato": "Fato observado",
    "hipotese": "Hipótese",
    "oportunidade": "Oportunidade potencial",
    "nao_encontrado": "Não encontrado",
}


def make(tipo: str, chave: str, texto: str, fonte: str, data: str | None = None) -> dict:
    assert tipo in TIPOS
    return {"tipo": tipo, "chave": chave, "texto": texto, "fonte": fonte, "data": data or now_iso()}


def input_hash(lead: dict, evidences: list[dict]) -> str:
    """Hash estável (ignora datas) para evitar reanalisar/cobrar IA do mesmo conteúdo."""
    base = "|".join(sorted(f"{e['chave']}:{e['texto']}" for e in evidences))
    base += f"#{lead.get('nome','')}#{lead.get('segmento','')}#{lead.get('cidade','')}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def ai_payload(lead: dict, evidences: list[dict], max_chars: int = 5000) -> str:
    """Texto enxuto enviado à IA: sem dados pessoais desnecessários (sem telefone/e-mail)."""
    lines = [
        f"EMPRESA: {lead.get('nome','')}",
        f"SEGMENTO: {lead.get('segmento','')}",
        f"LOCAL: {lead.get('bairro','')} {lead.get('cidade','')}-{lead.get('uf','')}".strip(),
        "EVIDÊNCIAS:",
    ]
    for i, e in enumerate(evidences):
        lines.append(f"[{i}] ({e['tipo']}) {e['texto']} | fonte: {e['fonte']}")
    return "\n".join(lines)[:max_chars]
