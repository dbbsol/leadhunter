"""Helpers compartilhados pelas telas."""
from __future__ import annotations

import streamlit as st

from services.campaign_service import LABELS


def campaign_picker(ctx, key: str, label: str = "Campanha", allow_all: bool = False):
    camps = ctx.campaigns.list()
    if not camps:
        return None, camps
    opts = {c["id"]: f"{c['nome']} · {LABELS.get(c['status'], c['status'])}" for c in camps}
    ids = list(opts)
    if allow_all:
        ids = ["__all__"] + ids
        opts["__all__"] = "Todas as campanhas"
    choice = st.selectbox(label, ids, format_func=lambda i: opts[i], key=key)
    return choice, camps


def current_lead_id() -> str | None:
    return st.session_state.get("lead_id")


def select_lead(lead_id: str) -> None:
    st.session_state["lead_id"] = lead_id


def lead_label(l: dict) -> str:
    extra = f" · {l['classificacao']}" if l.get("classificacao") else ""
    return f"{l.get('nome','?')} — {l.get('cidade','')}{extra}"
