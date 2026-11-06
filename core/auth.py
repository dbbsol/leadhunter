"""Autenticação Google (OIDC nativo do Streamlit) + autorização por assinatura."""
from __future__ import annotations

import streamlit as st

from core.config import LOCAL_TEST_MODE, get_setting, today_iso
from core.permissions import parse_date, resolve_tenant
from services.context import UserSession, get_admin_store
from ui.components import blocked_screen, login_screen

REASONS = {
    "not_authorized": ("Acesso não autorizado", "Este e-mail não está na lista de clientes autorizados. Fale com o administrador para contratar ou liberar o acesso."),
    "suspended": ("Assinatura suspensa", "Sua assinatura está suspensa. Regularize com o administrador para voltar a usar o Lead Hunter."),
    "expired": ("Assinatura vencida", "O prazo da sua assinatura terminou. Renove com o administrador para continuar."),
    "no_sheet": ("Conta em configuração", "Sua conta ainda não tem uma planilha de dados vinculada. Fale com o administrador."),
    "unverified": ("E-mail não verificado", "O Google não confirmou a verificação deste e-mail. Entre com outra conta."),
}


def _identity() -> tuple[str, str, bool] | None:
    if LOCAL_TEST_MODE:
        return "dev@local.test", "Dev Local", True
    user = st.user
    if not getattr(user, "is_logged_in", False):
        return None
    return str(user.get("email", "")), str(user.get("name", "") or user.get("email", "")), bool(user.get("email_verified", False))


def require_session() -> UserSession:
    """Retorna a sessão autorizada ou interrompe a execução (st.stop) mostrando a tela adequada."""
    ident = _identity()
    if ident is None:
        login_screen(on_click=st.login)
        st.stop()
    email, name, verified = ident

    admins = list(get_setting("ADMIN_EMAILS", []) or [])
    if LOCAL_TEST_MODE:
        store = get_admin_store()
        if not store.all("ASSINATURAS"):
            store.append("ASSINATURAS", [{"email": email, "nome": name, "plano": "Local (teste)", "inicio": today_iso(),
                                          "vencimento": "2099-12-31", "status": "ativo", "limite_pesquisas": 9999, "consumo": 0, "planilha_id": "local-tenant"}])
        admins = [email]
    try:
        rows = get_admin_store().all("ASSINATURAS")
    except Exception as exc:
        blocked_screen("Não consegui validar seu acesso", "A planilha administrativa não respondeu. Tente novamente em instantes ou avise o administrador.")
        st.caption(f"Detalhe técnico: {type(exc).__name__}")
        st.stop()
    decision = resolve_tenant(rows, email, admins, parse_date(today_iso()), verified)

    if not decision.allowed:
        title, text = REASONS.get(decision.reason, REASONS["not_authorized"])
        blocked_screen(title, text, email=email, on_logout=None if LOCAL_TEST_MODE else st.logout)
        st.stop()
    row = decision.row
    return UserSession(
        email=email, name=name, is_admin=decision.is_admin, sheet_id=str(row["planilha_id"]).strip(),
        plano=str(row.get("plano", "")), vencimento=str(row.get("vencimento", "")),
        limite=int(float(row.get("limite_pesquisas") or 0)), consumo=int(float(row.get("consumo") or 0)),
    )
