"""Monta o contexto da sessão: stores isolados por cliente e serviços."""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from ai.gemini import GeminiClient
from core.config import LOCAL_TEST_MODE, get_setting
from core.permissions import assert_same_tenant
from integrations.storage import ADMIN_SCHEMA, TENANT_SCHEMA, BaseStore, MemoryStore
from services.campaign_service import CampaignService
from services.lead_service import LeadService


@dataclass(frozen=True)
class UserSession:
    email: str
    name: str
    is_admin: bool
    sheet_id: str
    plano: str = ""
    vencimento: str = ""
    limite: int = 0
    consumo: int = 0


@st.cache_resource(show_spinner=False)
def _gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials

    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _sheets_store(sheet_id: str, kind: str):
    from integrations.google_sheets import SheetsStore

    store = SheetsStore(_gspread_client(), sheet_id, TENANT_SCHEMA if kind == "tenant" else ADMIN_SCHEMA)
    store.ensure_schema()
    return store


@st.cache_resource(show_spinner=False)
def _memory_store(sheet_id: str, kind: str):
    return MemoryStore(TENANT_SCHEMA if kind == "tenant" else ADMIN_SCHEMA, sheet_id)


def get_admin_store() -> BaseStore:
    if LOCAL_TEST_MODE:
        return _memory_store("local-admin", "admin")
    sheet_id = get_setting("ADMIN_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("ADMIN_SHEET_ID não configurado nos Secrets.")
    return _sheets_store(str(sheet_id), "admin")


def get_tenant_store(session: UserSession) -> BaseStore:
    """O ID da planilha vem SEMPRE da assinatura validada no servidor — nunca de input do usuário."""
    store = _memory_store(session.sheet_id, "tenant") if LOCAL_TEST_MODE else _sheets_store(session.sheet_id, "tenant")
    assert_same_tenant(store.spreadsheet_id, session.sheet_id)
    return store


@dataclass
class Ctx:
    session: UserSession
    store: BaseStore
    admin_store: BaseStore
    leads: LeadService
    campaigns: CampaignService

    def gemini(self):
        return GeminiClient.from_settings(self.store)


def build_ctx(session: UserSession) -> Ctx:
    store = get_tenant_store(session)
    return Ctx(session, store, get_admin_store(), LeadService(store, session.email), CampaignService(store))
