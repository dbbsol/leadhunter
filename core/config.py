"""Configuração central, leitura de segredos e utilitários básicos."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

APP_NAME = "Lead Hunter"
TZ = ZoneInfo("America/Sao_Paulo")

# Modo de TESTE LOCAL: dados em memória, sem login Google. Só liga com a variável de
# ambiente abaixo (nunca por secrets/URL/navegador). Não use em produção.
LOCAL_TEST_MODE = os.environ.get("LEAD_HUNTER_LOCAL_TEST") == "1"

DEFAULT_LIMITS = {
    "limite_empresas_campanha": 200,
    "limite_investigacoes_campanha": 50,
    "gemini_chamadas_dia": 100,
    "tempo_lote_segundos": 90,
    "tamanho_lote": 5,
}


def get_setting(name: str, default=None):
    """Lê de st.secrets (nível raiz) e, como alternativa, de variável de ambiente."""
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


def now() -> datetime:
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def today_iso() -> str:
    return now().date().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def jdump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def jload(text, default=None):
    if text in (None, ""):
        return default
    if not isinstance(text, str):
        return text
    try:
        return json.loads(text)
    except Exception:
        return default
