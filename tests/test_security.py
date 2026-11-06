import pytest

from core.security import UnsafeURL, assert_public_url, safe_cell, sanitize_text


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/admin", "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/", "http://192.168.1.1/",
    "http://[::1]/", "http://metadata.google.internal/", "http://2130706433/", "ftp://example.com/", "file:///etc/passwd",
    "http://example.com:8080/", "http://user:pw@example.com/", "http://100.64.0.1/", "http://0.0.0.0/", "http://[::ffff:127.0.0.1]/",
])
def test_blocks_internal(url):
    with pytest.raises(UnsafeURL):
        assert_public_url(url)


def test_allows_public_ip_literal():
    assert assert_public_url("http://8.8.8.8/") == "http://8.8.8.8/"


def test_sanitize_and_formula_injection():
    assert sanitize_text("a\x00b\n\n c", 10) == "a b c"
    assert safe_cell("=HYPERLINK(1)").startswith("'")
    assert safe_cell("-12") == "-12"
