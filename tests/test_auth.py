from datetime import date

from core.permissions import resolve_tenant

TODAY = date(2026, 11, 3)
ROWS = [{"email": "Cliente@Empresa.com", "status": "ativo", "vencimento": "2027-01-01", "planilha_id": "S1"},
        {"email": "velho@x.com", "status": "ativo", "vencimento": "2020-01-01", "planilha_id": "S2"}]


def test_authorized_case_insensitive():
    d = resolve_tenant(ROWS, "cliente@empresa.com", [], TODAY)
    assert d.allowed and d.row["planilha_id"] == "S1"


def test_google_login_alone_is_not_enough():
    d = resolve_tenant(ROWS, "estranho@gmail.com", [], TODAY)
    assert not d.allowed and d.reason == "not_authorized"


def test_expired_blocked_and_unverified_blocked():
    assert resolve_tenant(ROWS, "velho@x.com", [], TODAY).reason == "expired"
    assert resolve_tenant(ROWS, "cliente@empresa.com", [], TODAY, email_verified=False).reason == "unverified"


def test_admin_flag_does_not_grant_data_access():
    d = resolve_tenant(ROWS, "admin@x.com", ["admin@x.com"], TODAY)
    assert d.is_admin and not d.allowed  # admin precisa de assinatura/planilha para ver dados de cliente


def test_empty_email_denied():
    assert not resolve_tenant(ROWS, "", [], TODAY).allowed
