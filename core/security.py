"""Segurança: proteção contra SSRF, robots.txt e saneamento de texto."""
from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests

USER_AGENT = "LeadHunterBot/1.0 (pesquisa comercial B2B; respeita robots.txt)"
MAX_BYTES = 600_000
BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "instance-data"}
BLOCKED_SUFFIXES = (".internal", ".local", ".localhost", ".lan", ".home")


class UnsafeURL(Exception):
    """URL recusada pelas regras de segurança."""


def _ip_is_public(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return bool(ip.is_global) and not ip.is_multicast


def assert_public_url(url: str) -> str:
    """Garante http(s), portas padrão e que TODOS os IPs resolvidos são públicos."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL("Somente http/https são permitidos.")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host in BLOCKED_HOSTS or host.endswith(BLOCKED_SUFFIXES):
        raise UnsafeURL("Host não permitido.")
    if parsed.username or parsed.password:
        raise UnsafeURL("URLs com credenciais não são permitidas.")
    if parsed.port not in (None, 80, 443):
        raise UnsafeURL("Porta não permitida.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL("O domínio não resolve.") from exc
    if not infos:
        raise UnsafeURL("O domínio não resolve.")
    for info in infos:
        if not _ip_is_public(info[4][0]):
            raise UnsafeURL("O endereço resolve para uma rede privada/interna.")
    return url


@dataclass
class FetchResult:
    url: str
    status: int
    content: bytes
    encoding: str


def safe_get(url: str, *, timeout: float = 8.0, max_redirects: int = 3, accept_any_text: bool = True) -> FetchResult:
    """GET seguro: revalida cada redirecionamento, limita tamanho e tipo de conteúdo."""
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"}
    current = url
    for _ in range(max_redirects + 1):
        assert_public_url(current)
        resp = requests.get(current, headers=headers, timeout=timeout, allow_redirects=False, stream=True)
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                raise UnsafeURL("Redirecionamento inválido.")
            current = urljoin(current, location)
            continue
        ctype = resp.headers.get("Content-Type", "").lower()
        if accept_any_text and not ("html" in ctype or "text" in ctype or ctype == ""):
            resp.close()
            raise UnsafeURL("Conteúdo não é HTML/texto.")
        data, size = [], 0
        for chunk in resp.iter_content(8192):
            size += len(chunk)
            data.append(chunk)
            if size > MAX_BYTES:
                break
        resp.close()
        return FetchResult(current, resp.status_code, b"".join(data)[:MAX_BYTES], resp.encoding or "utf-8")
    raise UnsafeURL("Redirecionamentos demais.")


def allowed_by_robots(url: str) -> bool:
    """Respeita o robots.txt do site. Se não for possível ler, assume permitido."""
    try:
        p = urlparse(url)
        robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
        res = safe_get(robots_url, timeout=5, max_redirects=2)
        if res.status_code >= 400:
            return True
        rp = robotparser.RobotFileParser()
        rp.parse(res.content.decode(res.encoding, errors="ignore").splitlines())
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def sanitize_text(text, max_len: int = 300) -> str:
    """Remove caracteres de controle, normaliza espaços e trunca."""
    if text is None:
        return ""
    text = _CTRL.sub(" ", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def safe_cell(value) -> str:
    """Evita injeção de fórmulas quando o dado for exportado para planilhas."""
    s = "" if value is None else str(value)
    return "'" + s if s[:1] in ("=", "+", "@") or (s[:1] == "-" and len(s) > 1 and not s[1].isdigit()) else s
