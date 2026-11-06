"""Testes da busca via Geoapify (respostas simuladas; não usam rede nem a chave real)."""
import pytest

from discovery import osm


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        return self._payload


def _feature(name="Restaurante Bom", city="Porto Alegre", osm_type="w", osm_id=123, phone="+55 51 3333-4444", site="https://bom.com.br"):
    return {
        "type": "Feature",
        "properties": {
            "name": name, "city": city, "street": "Rua da Praia", "housenumber": "10", "suburb": "Centro Histórico",
            "lat": -30.03, "lon": -51.23, "place_id": "pid-" + name,
            "contact": {"phone": phone}, "website": site,
            "datasource": {"raw": {"osm_type": osm_type, "osm_id": osm_id, "opening_hours": "Mo-Su 11:00-23:00"}},
        },
        "geometry": {"type": "Point", "coordinates": [-51.23, -30.03]},
    }


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", "a" * 32)
    monkeypatch.setenv("NOMINATIM_CONTACT", "teste@gmail.com")
    osm._PLACE_ID_CACHE.clear()


def test_placeholder_nao_conta_como_chave(monkeypatch):
    monkeypatch.setenv("GEOAPIFY_API_KEY", "COLE_SUA_CHAVE_AQUI")
    assert osm._geoapify_key() == ""


def test_chave_valida(key):
    assert osm._geoapify_key() == "a" * 32


def test_parse_mapeia_campos_e_usa_id_osm():
    lead = osm.parse_geoapify_feature(_feature(), "Restaurantes", "Porto Alegre", "RS")
    assert lead["nome"] == "Restaurante Bom"
    assert lead["telefone"] == "+55 51 3333-4444"
    assert lead["site"] == "https://bom.com.br"
    assert lead["bairro"] == "Centro Histórico"
    assert lead["endereco"] == "Rua da Praia 10, Centro Histórico"
    assert lead["fonte"] == "openstreetmap" and lead["fonte_id"] == "way/123"
    assert lead["horario"] == "Mo-Su 11:00-23:00"


def test_parse_sem_id_osm_usa_place_id():
    f = _feature()
    f["properties"]["datasource"] = {}
    lead = osm.parse_geoapify_feature(f, "Restaurantes", "Porto Alegre", "RS")
    assert lead["fonte"] == "geoapify" and lead["fonte_id"] == "pid-Restaurante Bom"


def test_categorias_segmento_e_tag_personalizada():
    assert osm._categories_for("Restaurantes", "") == ["catering.restaurant"]
    assert osm._categories_for("", "shop=florist") == ["commercial.florist"]
    assert osm._categories_for("", "commercial.florist") == ["commercial.florist"]
    with pytest.raises(osm.DiscoveryError):
        osm._categories_for("", "shop=tag_que_nao_existe")
    with pytest.raises(osm.DiscoveryError):
        osm._categories_for("Segmento inexistente", "")


def test_todos_os_segmentos_do_overpass_tem_categoria_geoapify():
    assert set(osm.SEGMENTS) == set(osm.SEGMENT_CATEGORIES)


def test_busca_por_fronteira_exata(key, monkeypatch):
    chamadas = []

    def fake_get(url, params=None, **kw):
        chamadas.append((url, params))
        if url == osm.GEOAPIFY_GEOCODE:
            return FakeResp(200, {"results": [{"place_id": "CIDADE123"}]})
        return FakeResp(200, {"features": [_feature("A", osm_id=1), _feature("B", osm_id=2), _feature("A de novo", osm_id=1)]})

    monkeypatch.setattr(osm.requests, "get", fake_get)
    res = osm.search_osm("Restaurantes", "Porto Alegre", "RS", 10)
    assert [r["nome"] for r in res] == ["A", "B"]  # duplicata (mesmo id OSM) removida
    assert chamadas[-1][1]["filter"] == "place:CIDADE123"
    assert chamadas[-1][1]["categories"] == "catering.restaurant"


def test_fallback_caixa_filtra_cidades_vizinhas(key, monkeypatch):
    def fake_get(url, params=None, **kw):
        if url == osm.GEOAPIFY_GEOCODE:
            return FakeResp(200, {"results": []})  # sem place_id
        if url == osm.NOMINATIM:
            return FakeResp(200, [{"boundingbox": ["-30.27", "-29.93", "-51.28", "-51.01"], "osm_type": "relation", "osm_id": 242397}])
        assert params["filter"] == "rect:-51.28,-30.27,-51.01,-29.93"
        return FakeResp(200, {"features": [_feature("Daqui"), _feature("De Canoas", city="Canoas", osm_id=9)]})

    monkeypatch.setattr(osm.requests, "get", fake_get)
    res = osm.search_osm("Restaurantes", "Porto Alegre", "RS", 10)
    assert [r["nome"] for r in res] == ["Daqui"]


def test_place_id_recusado_cai_para_caixa(key, monkeypatch):
    def fake_get(url, params=None, **kw):
        if url == osm.GEOAPIFY_GEOCODE:
            return FakeResp(200, {"results": [{"place_id": "RUIM"}]})
        if url == osm.NOMINATIM:
            return FakeResp(200, [{"boundingbox": ["-30.27", "-29.93", "-51.28", "-51.01"]}])
        if params["filter"].startswith("place:"):
            return FakeResp(400, text="bad filter")
        return FakeResp(200, {"features": [_feature("Daqui")]})

    monkeypatch.setattr(osm.requests, "get", fake_get)
    assert [r["nome"] for r in osm.search_osm("Restaurantes", "Porto Alegre", "RS", 10)] == ["Daqui"]


@pytest.mark.parametrize("status,trecho", [(401, "recusou a chave"), (403, "recusou a chave"), (429, "Limite da Geoapify")])
def test_erros_de_chave_e_limite(key, monkeypatch, status, trecho):
    monkeypatch.setattr(osm.requests, "get", lambda url, params=None, **kw: FakeResp(status, {}))
    with pytest.raises(osm.DiscoveryError, match=trecho):
        osm.search_osm("Restaurantes", "Porto Alegre", "RS", 10)


def test_sem_chave_usa_overpass(monkeypatch):
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    monkeypatch.setenv("NOMINATIM_CONTACT", "teste@gmail.com")
    usado = {}
    monkeypatch.setattr(osm, "geocode", lambda c, u: {"osm_type": "relation", "osm_id": 1, "boundingbox": ["0", "1", "0", "1"]})
    monkeypatch.setattr(osm, "consultar", lambda tags, geo, limit: (usado.setdefault("ok", True) and {"elements": [{"type": "node", "id": 5, "tags": {"name": "Via Overpass"}}]}, False))
    res = osm.search_osm("Restaurantes", "Porto Alegre", "RS", 10)
    assert usado and res[0]["nome"] == "Via Overpass"


def test_overpass_build_query_bbox_e_area():
    geo = {"osm_type": "relation", "osm_id": 242397, "boundingbox": ["-30.27", "-29.93", "-51.28", "-51.01"]}
    assert "area(3600242397)" in osm.build_query(["amenity=restaurant"], geo, 5)
    assert "area(" not in osm.build_query(["amenity=restaurant"], geo, 5, force_bbox=True)
