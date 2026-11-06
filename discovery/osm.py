"""Descoberta de empresas: Geoapify Places (dados OpenStreetMap, com chave) ou Overpass (sem chave, instável)."""
from __future__ import annotations

import re
import time

import requests

from core.config import get_setting, now_iso

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

SEGMENTS: dict[str, list[str]] = {
    "Restaurantes": ["amenity=restaurant"],
    "Cafés e padarias": ["amenity=cafe", "shop=bakery"],
    "Bares e lanchonetes": ["amenity=bar", "amenity=fast_food", "amenity=pub"],
    "Academias": ["leisure=fitness_centre", "leisure=sports_centre"],
    "Clínicas e consultórios": ["amenity=clinic", "amenity=doctors"],
    "Odontologia": ["amenity=dentist"],
    "Salões de beleza e estética": ["shop=hairdresser", "shop=beauty"],
    "Lojas de roupas": ["shop=clothes"],
    "Pet shops e veterinárias": ["shop=pet", "amenity=veterinary"],
    "Imobiliárias": ["office=estate_agent"],
    "Advocacia": ["office=lawyer"],
    "Oficinas mecânicas": ["shop=car_repair"],
    "Hotéis e pousadas": ["tourism=hotel", "tourism=guest_house"],
    "Escolas e cursos": ["amenity=school", "amenity=language_school", "amenity=kindergarten"],
}
TAG_RE = re.compile(r"^[a-z_:]{1,30}=[A-Za-z0-9_:\-]{1,40}$")


class DiscoveryError(Exception):
    pass


def _ua() -> dict:
    contact = str(get_setting("NOMINATIM_CONTACT", "") or "").strip()
    if "@" not in contact or contact.endswith("example.com"):
        raise DiscoveryError("Configure NOMINATIM_CONTACT (seu e-mail) nos Secrets: o OpenStreetMap exige identificação e bloqueia pedidos anônimos.")
    return {"User-Agent": f"LeadHunterDBB/1.0 ({contact})", "Accept": "*/*"}


def geocode(cidade: str, uf: str) -> dict:
    params = {"city": cidade, "state": uf, "country": "Brasil", "format": "json", "limit": 1}
    try:
        r = requests.get(NOMINATIM, params=params, headers=_ua(), timeout=20)
    except requests.RequestException as exc:
        raise DiscoveryError(f"Nominatim inacessível ({type(exc).__name__}). Verifique sua internet.") from exc
    if r.status_code == 403:
        raise DiscoveryError("Nominatim recusou o pedido (403). Confira o NOMINATIM_CONTACT (e-mail válido) no secrets.toml.")
    if r.status_code != 200:
        raise DiscoveryError(f"O serviço de geocodificação (Nominatim) respondeu HTTP {r.status_code}.")
    try:
        data = r.json()
    except ValueError as exc:
        raise DiscoveryError("Nominatim devolveu uma resposta inválida.") from exc
    if not data:
        raise DiscoveryError(f"Não encontrei '{cidade} - {uf}' no OpenStreetMap. Confira o nome da cidade.")
    return data[0]


def build_query(tags: list[str], geo: dict, limit: int, force_bbox: bool = False) -> str:
    for t in tags:
        if not TAG_RE.match(t):
            raise DiscoveryError(f"Tag OSM inválida: {t}")
    if force_bbox:
        s, n, w, e = geo["boundingbox"]
        area, scope = "", f"({s},{w},{n},{e})"
    elif geo.get("osm_type") == "relation":
        area, scope = f"area({3600000000 + int(geo['osm_id'])})->.a;\n", "(area.a)"
    elif geo.get("osm_type") == "way":
        area, scope = f"area({2400000000 + int(geo['osm_id'])})->.a;\n", "(area.a)"
    else:
        s, n, w, e = geo["boundingbox"]
        area, scope = "", f"({s},{w},{n},{e})"
    parts = ""
    for k, v in (t.split("=", 1) for t in tags):
        for kind in ("node", "way"):
            parts += f'  {kind}{scope}["{k}"="{v}"]["name"];\n'
    return f"[out:json][timeout:25];\n{area}(\n{parts});\nout center tags {int(limit)};"


def parse_element(el: dict, segmento: str, cidade: str, uf: str) -> dict:
    tags = el.get("tags", {})
    center = el.get("center", {})
    street = tags.get("addr:street", "")
    num = tags.get("addr:housenumber", "")
    endereco = ", ".join(x for x in [f"{street} {num}".strip(), tags.get("addr:suburb", "")] if x)
    otype = el.get("type", "node")
    return {
        "nome": tags.get("name", ""),
        "segmento": segmento,
        "cidade": cidade,
        "uf": uf,
        "bairro": tags.get("addr:suburb") or tags.get("addr:neighbourhood", ""),
        "endereco": endereco,
        "telefone": tags.get("phone") or tags.get("contact:phone", ""),
        "site": tags.get("website") or tags.get("contact:website") or tags.get("url", ""),
        "email": tags.get("email") or tags.get("contact:email", ""),
        "instagram": tags.get("contact:instagram") or tags.get("instagram", ""),
        "horario": tags.get("opening_hours", ""),
        "cnpj": "",
        "fonte": "openstreetmap",
        "fonte_id": f"{otype}/{el.get('id')}",
        "fonte_url": f"https://www.openstreetmap.org/{otype}/{el.get('id')}",
        "data_fonte": now_iso(),
        "lat": el.get("lat") or center.get("lat") or "",
        "lon": el.get("lon") or center.get("lon") or "",
    }


def _overpass(query: str) -> dict:
    """Tenta cada servidor Overpass uma vez. Levanta DiscoveryError com o detalhe de cada um."""
    errors = []
    for url in OVERPASS_ENDPOINTS:
        host = url.split("/")[2]
        try:
            r = requests.post(url, data={"data": query}, headers=_ua(), timeout=(10, 40))
        except requests.RequestException as exc:
            errors.append(f"{host}: {type(exc).__name__}")
            continue
        if r.status_code != 200:
            errors.append(f"{host}: HTTP {r.status_code}")
            continue
        try:
            data = r.json()
        except ValueError:
            errors.append(f"{host}: resposta não é JSON (servidor sobrecarregado)")
            continue
        if "elements" not in data:
            errors.append(f"{host}: resposta sem dados")
            continue
        if data.get("remark") and not data["elements"]:
            errors.append(f"{host}: {str(data['remark'])[:80]}")
            continue
        return data
    raise DiscoveryError(" | ".join(errors))


def consultar(tags: list[str], geo: dict, limit: int) -> tuple[dict, bool]:
    """Tenta por área da cidade; se os servidores falharem, tenta por caixa de coordenadas.
    Devolve (dados, usou_bbox). Repete até 2 rodadas com pausa."""
    detalhes = ""
    for rodada in range(2):
        for bbox in (False, True):
            try:
                return _overpass(build_query(tags, geo, limit, force_bbox=bbox)), bbox
            except DiscoveryError as exc:
                detalhes = str(exc)
        if rodada == 0:
            time.sleep(10)
    raise DiscoveryError("Os servidores do OpenStreetMap (Overpass) não responderam agora. Detalhes: " + detalhes + ". Tente de novo em 1–2 minutos ou com menos resultados.")


# ---------------------------------------------------------------------------
# Geoapify Places (dados do OpenStreetMap servidos pela Geoapify; plano grátis com chave)
# ---------------------------------------------------------------------------
GEOAPIFY_PLACES = "https://api.geoapify.com/v2/places"
GEOAPIFY_GEOCODE = "https://api.geoapify.com/v1/geocode/search"

SEGMENT_CATEGORIES: dict[str, list[str]] = {
    "Restaurantes": ["catering.restaurant"],
    "Cafés e padarias": ["catering.cafe", "commercial.food_and_drink.bakery"],
    "Bares e lanchonetes": ["catering.bar", "catering.fast_food", "catering.pub"],
    "Academias": ["sport.fitness"],
    "Clínicas e consultórios": ["healthcare.clinic_or_praxis"],
    "Odontologia": ["healthcare.dentist"],
    "Salões de beleza e estética": ["service.beauty"],
    "Lojas de roupas": ["commercial.clothing"],
    "Pet shops e veterinárias": ["pet.shop", "pet.veterinary"],
    "Imobiliárias": ["office.estate_agent", "service.estate_agent"],
    "Advocacia": ["office.lawyer"],
    "Oficinas mecânicas": ["service.vehicle.repair.car"],
    "Hotéis e pousadas": ["accommodation.hotel", "accommodation.guest_house"],
    "Escolas e cursos": ["education.school", "education.language_school", "childcare.kindergarten"],
}

# Tags OSM "personalizadas" mais comuns -> categoria Geoapify. Também vale digitar a categoria direto (ex.: commercial.florist).
OSM_TAG_TO_CATEGORY: dict[str, str] = {
    "shop=florist": "commercial.florist",
    "shop=bakery": "commercial.food_and_drink.bakery",
    "shop=butcher": "commercial.food_and_drink.butcher",
    "shop=supermarket": "commercial.supermarket",
    "shop=convenience": "commercial.convenience",
    "shop=jewelry": "commercial.jewelry",
    "shop=shoes": "commercial.clothing.shoes",
    "shop=books": "commercial.books",
    "shop=electronics": "commercial.elektronics",
    "shop=furniture": "commercial.furniture_and_interior",
    "shop=hairdresser": "service.beauty.hairdresser",
    "shop=beauty": "service.beauty",
    "shop=pet": "pet.shop",
    "shop=optician": "commercial.health_and_beauty.optician",
    "shop=car_repair": "service.vehicle.repair.car",
    "amenity=restaurant": "catering.restaurant",
    "amenity=cafe": "catering.cafe",
    "amenity=bar": "catering.bar",
    "amenity=pub": "catering.pub",
    "amenity=fast_food": "catering.fast_food",
    "amenity=pharmacy": "healthcare.pharmacy",
    "amenity=dentist": "healthcare.dentist",
    "amenity=clinic": "healthcare.clinic_or_praxis",
    "amenity=veterinary": "pet.veterinary",
    "amenity=school": "education.school",
    "amenity=language_school": "education.language_school",
    "amenity=kindergarten": "childcare.kindergarten",
    "amenity=driving_school": "education.driving_school",
    "amenity=bank": "service.financial.bank",
    "office=lawyer": "office.lawyer",
    "office=estate_agent": "office.estate_agent",
    "office=accountant": "office.accountant",
    "office=architect": "office.architect",
    "office=insurance": "office.insurance",
    "tourism=hotel": "accommodation.hotel",
    "tourism=guest_house": "accommodation.guest_house",
    "tourism=hostel": "accommodation.hostel",
    "leisure=fitness_centre": "sport.fitness",
}
CATEGORY_RE = re.compile(r"^[a-z_]+(\.[a-z_\-]+)*$")
_OSM_TYPES = {"n": "node", "w": "way", "r": "relation", "node": "node", "way": "way", "relation": "relation"}


def _geoapify_key() -> str:
    key = str(get_setting("GEOAPIFY_API_KEY", "") or "").strip()
    if not key or any(p in key.upper() for p in PLACEHOLDERS):
        return ""
    return key


def usando_geoapify() -> bool:
    return bool(_geoapify_key())


def _categories_for(segmento: str, custom_tag: str) -> list[str]:
    custom = (custom_tag or "").strip().lower()
    if not custom:
        cats = SEGMENT_CATEGORIES.get(segmento, [])
        if not cats:
            raise DiscoveryError("Escolha um segmento ou informe uma tag/categoria (ex.: shop=florist).")
        return cats
    if "=" in custom:
        cat = OSM_TAG_TO_CATEGORY.get(custom)
        if not cat:
            raise DiscoveryError(f"Não conheço a tag '{custom_tag}' para a busca atual. Digite a categoria da Geoapify (ex.: commercial.florist) ou use um segmento da lista.")
        return [cat]
    if not CATEGORY_RE.match(custom):
        raise DiscoveryError(f"Categoria inválida: {custom_tag}")
    return [custom]


def parse_geoapify_feature(feat: dict, segmento: str, cidade: str, uf: str) -> dict:
    p = feat.get("properties") or {}
    raw = (p.get("datasource") or {}).get("raw") or {}
    contact = p.get("contact") or {}
    coords = (feat.get("geometry") or {}).get("coordinates") or ["", ""]
    street = p.get("street") or ""
    num = p.get("housenumber") or ""
    suburb = p.get("suburb") or p.get("district") or raw.get("addr:suburb") or ""
    endereco = ", ".join(x for x in [f"{street} {num}".strip(), suburb] if x) or p.get("address_line2", "")
    osm_type = _OSM_TYPES.get(str(raw.get("osm_type", "")).lower())
    osm_id = raw.get("osm_id")
    if osm_type and osm_id:
        fonte, fonte_id, fonte_url = "openstreetmap", f"{osm_type}/{osm_id}", f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    else:
        fonte, fonte_id, fonte_url = "geoapify", str(p.get("place_id", "")), ""
    return {
        "nome": p.get("name", ""),
        "segmento": segmento,
        "cidade": cidade,
        "uf": uf,
        "bairro": suburb,
        "endereco": endereco,
        "telefone": contact.get("phone") or raw.get("phone") or raw.get("contact:phone") or "",
        "site": p.get("website") or contact.get("website") or raw.get("website") or raw.get("contact:website") or raw.get("url") or "",
        "email": contact.get("email") or raw.get("email") or raw.get("contact:email") or "",
        "instagram": raw.get("contact:instagram") or raw.get("instagram") or "",
        "horario": p.get("opening_hours") or raw.get("opening_hours") or "",
        "cnpj": "",
        "fonte": fonte,
        "fonte_id": fonte_id,
        "fonte_url": fonte_url,
        "data_fonte": now_iso(),
        "lat": p.get("lat") or coords[1],
        "lon": p.get("lon") or coords[0],
    }


class GeoapifyBadRequest(DiscoveryError):
    """HTTP 400 da Geoapify (filtro ou categoria rejeitados)."""


_PLACE_ID_CACHE: dict[str, str] = {}
PLACEHOLDERS = ("COLE", "SUA_CHAVE", "XXXX", "SEU_", "CHAVE_AQUI")


def _geoapify_place_id(cidade: str, uf: str, key: str) -> str:
    """Pede à Geoapify o ID da fronteira da cidade (filtro exato, sem pegar cidades vizinhas)."""
    ck = f"{cidade}|{uf}".lower()
    if ck in _PLACE_ID_CACHE:
        return _PLACE_ID_CACHE[ck]
    try:
        r = requests.get(
            GEOAPIFY_GEOCODE,
            params={"text": f"{cidade}, {uf}, Brasil", "type": "city", "format": "json", "limit": 1, "lang": "pt", "apiKey": key},
            timeout=(10, 20),
        )
        if r.status_code in (401, 403):
            raise DiscoveryError("A Geoapify recusou a chave (HTTP %d). Confira GEOAPIFY_API_KEY no secrets.toml (sem espaços, entre aspas)." % r.status_code)
        if r.status_code == 429:
            raise DiscoveryError("Limite da Geoapify atingido (HTTP 429). Aguarde alguns minutos ou volte amanhã (o plano grátis tem limite diário).")
        if r.status_code != 200:
            return ""
        results = r.json().get("results") or []
        pid = str(results[0].get("place_id", "")) if results else ""
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return ""
    if pid:
        _PLACE_ID_CACHE[ck] = pid
    return pid


def _geoapify_get(params: dict) -> list[dict]:
    last = ""
    for _ in range(2):
        try:
            r = requests.get(GEOAPIFY_PLACES, params=params, timeout=(10, 40))
        except requests.RequestException as exc:
            last = type(exc).__name__
            time.sleep(2)
            continue
        if r.status_code in (401, 403):
            raise DiscoveryError("A Geoapify recusou a chave (HTTP %d). Confira GEOAPIFY_API_KEY no secrets.toml (sem espaços, entre aspas)." % r.status_code)
        if r.status_code == 429:
            raise DiscoveryError("Limite da Geoapify atingido (HTTP 429). Aguarde alguns minutos ou volte amanhã (o plano grátis tem limite diário).")
        if r.status_code == 400:
            raise GeoapifyBadRequest(f"A Geoapify rejeitou a busca (HTTP 400): {r.text[:200]}")
        if r.status_code != 200:
            last = f"HTTP {r.status_code}"
            time.sleep(2)
            continue
        try:
            return r.json().get("features", [])
        except ValueError:
            last = "resposta inválida"
    raise DiscoveryError(f"A Geoapify não respondeu agora ({last}). Tente de novo em instantes.")


def _search_geoapify(segmento: str, cidade: str, uf: str, limit: int, custom_tag: str) -> list[dict]:
    from discovery.normalize import norm_text

    key = _geoapify_key()
    cats = _categories_for(segmento, custom_tag)
    base = {"categories": ",".join(cats), "lang": "pt", "apiKey": key}

    feats, exact = [], False
    pid = _geoapify_place_id(cidade, uf, key)
    if pid:
        try:
            feats = _geoapify_get({**base, "filter": f"place:{pid}", "limit": min(limit, 500)})
            exact = True
        except GeoapifyBadRequest:
            exact = False  # ID não serviu como filtro: cai para a caixa de coordenadas
    if not exact:
        geo = geocode(cidade, uf)
        s, n, w, e = geo["boundingbox"]  # Nominatim: [sul, norte, oeste, leste]
        feats = _geoapify_get({**base, "filter": f"rect:{w},{s},{e},{n}", "limit": min(limit * 2, 500)})  # Geoapify: lon1,lat1,lon2,lat2

    label = segmento if not custom_tag else f"OSM {custom_tag}"
    out, seen = [], set()
    for f in feats:
        p = f.get("properties") or {}
        if not p.get("name"):
            continue
        if not exact and p.get("city") and norm_text(p["city"]) != norm_text(cidade):
            continue  # caixa de coordenadas pega vizinhas (Canoas, Viamão...)
        lead = parse_geoapify_feature(f, label, cidade, uf)
        k = (lead["fonte"], lead["fonte_id"]) if lead["fonte_id"] else (lead["nome"], lead["endereco"])
        if k in seen:
            continue
        seen.add(k)
        out.append(lead)
        if len(out) >= limit:
            break
    return out


def search_osm(segmento: str, cidade: str, uf: str, limit: int = 100, custom_tag: str = "") -> list[dict]:
    if _geoapify_key():
        return _search_geoapify(segmento, cidade, uf, min(max(int(limit), 1), 500), custom_tag)
    tags = [custom_tag.strip()] if custom_tag.strip() else SEGMENTS.get(segmento, [])
    if not tags:
        raise DiscoveryError("Escolha um segmento ou informe uma tag OSM (ex.: shop=florist).")
    geo = geocode(cidade, uf)
    data, usou_bbox = consultar(tags, geo, min(max(int(limit), 1), 500))
    label = segmento if not custom_tag else f"OSM {custom_tag}"
    from discovery.normalize import norm_text

    out = []
    for e in data.get("elements", []):
        t = e.get("tags", {})
        if not t.get("name"):
            continue
        if usou_bbox and t.get("addr:city") and norm_text(t["addr:city"]) != norm_text(cidade):
            continue  # a caixa de coordenadas pega vizinhas; descarta as que declaram outra cidade
        out.append(parse_element(e, label, cidade, uf))
    return out


def filter_results(leads: list[dict], bairro: str = "", keywords: str = "", only_phone: bool = False, site_filter: str = "todos") -> list[dict]:
    from discovery.normalize import norm_text

    out = []
    kws = [norm_text(k) for k in keywords.split(",") if k.strip()]
    for l in leads:
        if bairro and norm_text(bairro) not in norm_text(l.get("bairro", "") + " " + l.get("endereco", "")):
            continue
        if kws and not any(k in norm_text(l.get("nome", "")) for k in kws):
            continue
        if only_phone and not l.get("telefone"):
            continue
        if site_filter == "sem site" and l.get("site"):
            continue
        if site_filter == "com site" and not l.get("site"):
            continue
        out.append(l)
    return out
