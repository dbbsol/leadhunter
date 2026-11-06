from datetime import date

import pytest

from core.permissions import PermissionDenied, assert_same_tenant, check_subscription, quota_remaining, require_admin

TODAY = date(2026, 11, 3)
OK = {"email": "a@x.com", "status": "ativo", "vencimento": "2026-12-01", "planilha_id": "S1"}


def test_active_ok():
    assert check_subscription(OK, TODAY) == (True, "ok")


def test_suspended_expired_missing():
    assert check_subscription({**OK, "status": "suspenso"}, TODAY)[1] == "suspended"
    assert check_subscription({**OK, "vencimento": "2026-11-02"}, TODAY)[1] == "expired"
    assert check_subscription({**OK, "vencimento": "31/12/2026"}, TODAY)[0] is True
    assert check_subscription({**OK, "vencimento": ""}, TODAY)[1] == "expired"
    assert check_subscription({**OK, "planilha_id": ""}, TODAY)[1] == "no_sheet"
    assert check_subscription(None, TODAY)[1] == "not_authorized"


def test_expires_today_still_valid():
    assert check_subscription({**OK, "vencimento": "2026-11-03"}, TODAY)[0]


def test_tenant_isolation():
    assert_same_tenant("S1", "S1")
    with pytest.raises(PermissionDenied):
        assert_same_tenant("S2", "S1")
    with pytest.raises(PermissionDenied):
        assert_same_tenant("S1", "")


def test_admin_required():
    require_admin(True)
    with pytest.raises(PermissionDenied):
        require_admin(False)


def test_quota():
    assert quota_remaining(10, 3) == 7 and quota_remaining(10, 12) == 0 and quota_remaining("x", 1) == 0
