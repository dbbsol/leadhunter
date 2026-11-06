"""Importação de CSV/XLSX com mapeamento automático de colunas."""
from __future__ import annotations

import io

import pandas as pd

from core.security import safe_cell
from discovery.normalize import norm_text

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000

SYNONYMS = {
    "nome": ["nome", "empresa", "razao social", "razao_social", "nome fantasia", "fantasia", "name", "estabelecimento"],
    "segmento": ["segmento", "categoria", "ramo", "atividade", "cnae", "tipo"],
    "cidade": ["cidade", "municipio", "city"],
    "uf": ["uf", "estado", "state"],
    "bairro": ["bairro", "neighborhood"],
    "endereco": ["endereco", "logradouro", "rua", "address"],
    "telefone": ["telefone", "celular", "whatsapp", "fone", "phone", "contato"],
    "site": ["site", "website", "url", "pagina"],
    "email": ["email", "e-mail", "mail"],
    "instagram": ["instagram", "insta"],
    "cnpj": ["cnpj"],
    "porte": ["porte"],
}


class ImportError_(Exception):
    pass


def read_table(data: bytes, filename: str) -> pd.DataFrame:
    if len(data) > MAX_BYTES:
        raise ImportError_("Arquivo maior que 5 MB. Divida a lista em partes menores.")
    name = filename.lower()
    try:
        if name.endswith(".csv"):
            for enc in ("utf-8-sig", "latin-1"):
                try:
                    df = pd.read_csv(io.BytesIO(data), sep=None, engine="python", dtype=str, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ImportError_("Não consegui ler a codificação do CSV.")
        elif name.endswith((".xlsx", ".xlsm")):
            df = pd.read_excel(io.BytesIO(data), dtype=str, engine="openpyxl")
        else:
            raise ImportError_("Formato não suportado. Envie .csv ou .xlsx.")
    except ImportError_:
        raise
    except Exception as exc:
        raise ImportError_(f"Não consegui ler o arquivo: {exc}") from exc
    df = df.fillna("").head(MAX_ROWS)
    if df.empty:
        raise ImportError_("O arquivo não tem linhas de dados.")
    return df


def auto_mapping(columns: list[str]) -> dict[str, str]:
    """Retorna {campo_canônico: coluna_do_arquivo} usando sinônimos."""
    norm = {c: norm_text(c) for c in columns}
    mapping: dict[str, str] = {}
    for field, syns in SYNONYMS.items():
        for col, n in norm.items():
            if n in syns and col not in mapping.values():
                mapping[field] = col
                break
    return mapping


def df_to_leads(df: pd.DataFrame, mapping: dict[str, str], default_cidade="", default_uf="", default_segmento="", fonte="importacao") -> list[dict]:
    leads = []
    for i, row in df.iterrows():
        raw = {f: safe_cell(row[c]) if c in df.columns else "" for f, c in mapping.items()}
        raw["cidade"] = raw.get("cidade") or default_cidade
        raw["uf"] = raw.get("uf") or default_uf
        raw["segmento"] = raw.get("segmento") or default_segmento
        raw["fonte"] = fonte
        raw["fonte_id"] = f"linha-{i + 2}"
        if raw.get("nome"):
            leads.append(raw)
    return leads
