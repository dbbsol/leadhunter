"""Regras de autorização puras (sem Streamlit) — fáceis de testar.

Cada operação no backend deve passar por aqui: a decisão NUNCA vem do navegador.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


class PermissionDenied(Exception):
    pass


@dataclass(frozen=True)
class TenantDecision:
    allowed: bool
    reason: str  # ok | not_authorized | suspended | expired | no_sheet | unverified
    row: dict | None = None
    is_admin: bool = False


def parse_date(value) -> date | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def find_subscription(rows: list[dict], email: str) -> dict | None:
    email = (email or "").strip().lower()
    for row in rows:
        if str(row.get("email", "")).strip().lower() == email and email:
            return row
    return None


def check_subscription(row: dict | None, today: date) -> tuple[bool, str]:
    if not row:
        return False, "not_authorized"
    if str(row.get("status", "")).strip().lower() != "ativo":
        return False, "suspended"
    due = parse_date(row.get("vencimento"))
    if not due or due < today:
        return False, "expired"
    if not str(row.get("planilha_id", "")).strip():
        return False, "no_sheet"
    return True, "ok"


def resolve_tenant(rows: list[dict], email: str, admin_emails: list[str], today: date, email_verified: bool = True) -> TenantDecision:
    admins = {a.strip().lower() for a in (admin_emails or [])}
    admin = (email or "").strip().lower() in admins
    if not email_verified:
        return TenantDecision(False, "unverified", None, admin)
    row = find_subscription(rows, email)
    ok, reason = check_subscription(row, today)
    return TenantDecision(ok, reason, row if ok else None, admin)


def require_admin(is_admin: bool) -> None:
    if not is_admin:
        raise PermissionDenied("Ação restrita ao administrador.")


def assert_same_tenant(store_sheet_id: str, session_sheet_id: str) -> None:
    """Impede usar um store que não pertença ao cliente da sessão."""
    if not session_sheet_id or store_sheet_id != session_sheet_id:
        raise PermissionDenied("Acesso a dados de outro cliente bloqueado.")


def quota_remaining(limit, used) -> int:
    try:
        return max(0, int(float(limit or 0)) - int(float(used or 0)))
    except (TypeError, ValueError):
        return 0
