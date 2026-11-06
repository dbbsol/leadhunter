"""Normalização de dados de empresas e chaves de deduplicação."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

from core.config import new_id, now_iso
from core.security import sanitize_text
from discovery.cnpj import is_valid_cnpj, only_digits

SOCIAL_HOSTS = {
    "instagram.com", "facebook.com", "fb.com", "linktr.ee", "wa.me", "api.whatsapp.com", "whatsapp.com",
    "linkedin.com", "tiktok.com", "youtube.com", "twitter.com", "x.com", "goo.gl", "g.page", "google.com",
    "ifood.com.br", "bit.ly", "beacons.ai",
}
LEGAL_SUFFIX = re.compile(r"\b(ltda|me|epp|eireli|mei|sa|s a|s/a)\b")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(text or "")) if unicodedata.category(c) != "Mn")


def norm_text(text) -> str:
    t = strip_accents(str(text or "")).lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def norm_name(text) -> str:
    return re.sub(r"\s+", " ", LEGAL_SUFFIX.sub(" ", norm_text(text))).strip()


def norm_phone(text) -> str:
    d = re.sub(r"\D", "", str(text or ""))
    if d.startswith("55") and len(d) >= 12:
        d = d[2:]
    d = d.lstrip("0")
    return d if len(d) in (10, 11) else ""


def norm_url(text) -> str:
    t = str(text or "").strip()
    if not t or " " in t:
        return ""
    if not re.match(r"^https?://", t, re.I):
        t = "https://" + t
    p = urlparse(t)
    return t if p.hostname and "." in p.hostname else ""


def norm_domain(url) -> str:
    u = norm_url(url)
    if not u:
        return ""
    host = (urlparse(u).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def dedupe_domain(url) -> str:
    """Domínio usável como chave (ignora redes sociais e encurtadores)."""
    d = norm_domain(url)
    return "" if d in SOCIAL_HOSTS or any(d.endswith("." + h) for h in SOCIAL_HOSTS) else d


def norm_email(text) -> str:
    t = str(text or "").strip().lower()
    return t if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", t) else ""


def norm_instagram(text) -> str:
    t = str(text or "").strip()
    if not t:
        return ""
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", t)
    handle = m.group(1) if m else t.lstrip("@")
    handle = handle.strip("/ ")
    return f"https://instagram.com/{handle}" if re.match(r"^[A-Za-z0-9_.]{1,30}$", handle) else ""


def normalize_lead(raw: dict) -> dict:
    """Converte um registro bruto (OSM, CSV, manual) no formato canônico do LEADS."""
    cnpj = only_digits(raw.get("cnpj"))
    lead = {
        "nome": sanitize_text(raw.get("nome"), 160),
        "segmento": sanitize_text(raw.get("segmento"), 80),
        "cidade": sanitize_text(raw.get("cidade"), 80),
        "uf": sanitize_text(raw.get("uf"), 2).upper(),
        "bairro": sanitize_text(raw.get("bairro"), 80),
        "endereco": sanitize_text(raw.get("endereco"), 200),
        "telefone": sanitize_text(raw.get("telefone"), 40),
        "site": norm_url(raw.get("site")),
        "cnpj": cnpj if is_valid_cnpj(cnpj) else "",
        "email": norm_email(raw.get("email")),
        "instagram": norm_instagram(raw.get("instagram")),
        "horario": sanitize_text(raw.get("horario"), 120),
        "porte": sanitize_text(raw.get("porte"), 30),
        "fonte": sanitize_text(raw.get("fonte"), 40) or "manual",
        "fonte_id": sanitize_text(raw.get("fonte_id"), 80),
        "fonte_url": sanitize_text(raw.get("fonte_url"), 200),
        "data_fonte": raw.get("data_fonte") or now_iso(),
        "lat": str(raw.get("lat") or ""),
        "lon": str(raw.get("lon") or ""),
    }
    lead["telefone_norm"] = norm_phone(lead["telefone"])
    lead["dominio"] = dedupe_domain(lead["site"])
    return lead


def dedupe_keys(lead: dict) -> list[str]:
    keys = []
    if lead.get("cnpj"):
        keys.append("cnpj:" + only_digits(lead["cnpj"]))
    dom = dedupe_domain(lead.get("site") or lead.get("dominio"))
    if dom:
        keys.append("dom:" + dom)
    tel = lead.get("telefone_norm") or norm_phone(lead.get("telefone"))
    if tel:
        keys.append("tel:" + tel)
    if lead.get("fonte") and lead.get("fonte_id"):
        keys.append(f"src:{lead['fonte']}:{lead['fonte_id']}")
    nome, cid, end = norm_name(lead.get("nome")), norm_text(lead.get("cidade")), norm_text(lead.get("endereco"))
    if nome and cid and end:
        keys.append(f"nca:{nome}|{cid}|{end}")
    return keys


def dedupe(new_leads: list[dict], existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separa (únicos, duplicados). Também remove duplicidades dentro do próprio lote."""
    seen: dict[str, str] = {}
    for e in existing:
        for k in dedupe_keys(e):
            seen[k] = e.get("id", "")
    unique, dups = [], []
    for lead in new_leads:
        keys = dedupe_keys(lead)
        hit = next((k for k in keys if k in seen), None)
        if hit:
            dups.append({**lead, "_duplicado_por": hit})
            continue
        lead.setdefault("id", new_id("ld"))
        for k in keys:
            seen[k] = lead["id"]
        unique.append(lead)
    return unique, dups
