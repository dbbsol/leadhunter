"""Análise da página inicial de um site (somente leitura, com proteção SSRF e robots.txt)."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from core.config import now_iso
from core.security import UnsafeURL, allowed_by_robots, assert_public_url, safe_get, sanitize_text

CTA_WORDS = [
    "agende", "agendar", "reserve", "reservar", "orçamento", "orcamento", "fale conosco", "fale com",
    "entre em contato", "contato", "peça", "peca agora", "compre", "comprar", "solicite", "solicitar",
    "whatsapp", "ligue", "cadastre", "matricule", "experimente", "peça já", "faça seu pedido",
]
SOCIALS = {
    "instagram": r"instagram\.com/([A-Za-z0-9_.]+)",
    "facebook": r"facebook\.com/([A-Za-z0-9_.\-]+)",
    "linkedin": r"linkedin\.com/(?:company|in)/([A-Za-z0-9_.\-]+)",
    "tiktok": r"tiktok\.com/@([A-Za-z0-9_.]+)",
    "youtube": r"youtube\.com/(?:@|channel/|c/)([A-Za-z0-9_.\-]+)",
}


def analyze_site(url: str) -> dict:
    """Retorna dict com ok/erro e fatos observados na página inicial."""
    out: dict = {"ok": False, "url": url, "data": now_iso(), "erro": ""}
    try:
        assert_public_url(url)
        if not allowed_by_robots(url):
            out["erro"] = "O robots.txt do site não permite a coleta automatizada."
            return out
        res = safe_get(url)
    except UnsafeURL as exc:
        out["erro"] = f"Acesso bloqueado por segurança: {exc}"
        return out
    except Exception as exc:
        out["erro"] = f"Site inacessível ({type(exc).__name__})."
        return out
    if res.status_code >= 400:
        out["erro"] = f"O site respondeu com erro HTTP {res.status_code}."
        return out

    html = res.content.decode(res.encoding or "utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    hrefs = [a.get("href", "") for a in BeautifulSoup(html, "html.parser").find_all("a")]
    text = soup.get_text(" ", strip=True).lower()

    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    viewport = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    socials = {}
    for name, rx in SOCIALS.items():
        for h in hrefs:
            m = re.search(rx, h)
            if m and m.group(1).lower() not in ("sharer", "share", "p", "explore"):
                socials[name] = h
                break
    link_blob = " ".join(hrefs).lower()
    out.update({
        "ok": True,
        "url_final": res.url,
        "https": res.url.startswith("https://"),
        "titulo": sanitize_text(soup.title.string if soup.title and soup.title.string else "", 160),
        "descricao": sanitize_text(meta_desc.get("content") if meta_desc else "", 250),
        "h1": sanitize_text(soup.h1.get_text(" ", strip=True) if soup.h1 else "", 160),
        "viewport": bool(viewport),
        "whatsapp": ("wa.me" in link_blob) or ("api.whatsapp.com" in link_blob) or ("whatsapp" in text and "wa.me" in html.lower()),
        "tel": "tel:" in link_blob,
        "email": "mailto:" in link_blob,
        "form": bool(soup.find("form")),
        "ctas": sorted({w for w in CTA_WORDS if w in text})[:6],
        "redes": socials,
        "texto_chars": len(text),
    })
    return out
