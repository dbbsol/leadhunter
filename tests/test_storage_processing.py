from ai.spin_selling import validate_spin
from core.config import jload
from integrations.storage import TENANT_SCHEMA, MemoryStore
from services.campaign_service import CampaignService
from services.lead_service import LeadService
from services.processing import run_batch


def make():
    s = MemoryStore(TENANT_SCHEMA, "t1")
    return s, LeadService(s, "u@x.com"), CampaignService(s)


RAW = [{"nome": "Pizzaria Alfa", "segmento": "Restaurantes", "cidade": "Porto Alegre", "uf": "RS", "telefone": "51988887777", "fonte": "t", "fonte_id": "1"},
       {"nome": "Bistrô Beta", "segmento": "Restaurantes", "cidade": "Porto Alegre", "uf": "RS", "email": "beta@x.com", "fonte": "t", "fonte_id": "2"}]


def test_upsert_idempotent_and_no_duplicates():
    s, ls, cs = make()
    c = cs.create("Teste", "Restaurantes", "Porto Alegre", "RS")
    r1 = ls.add_leads(RAW, c["id"])
    r2 = ls.add_leads(RAW, c["id"])
    assert r1["inseridos"] == 2 and r2["inseridos"] == 0 and r2["duplicados"] == 2


def test_suppression_blocks_readd_and_nao_contatar():
    s, ls, cs = make()
    c = cs.create("T", "Restaurantes", "Porto Alegre", "RS")
    ls.add_leads(RAW, c["id"])
    lead = ls.list()[0]
    ls.set_stage(lead, "Não contatar")
    ls.delete_lead(lead["id"])
    r = ls.add_leads(RAW, c["id"])
    assert r["suprimidos"] == 1


def test_batch_resume_and_no_repeat_ai(monkeypatch):
    s, ls, cs = make()
    c = cs.create("T", "Restaurantes", "Porto Alegre", "RS", limite_investigacoes=10)
    ls.add_leads(RAW, c["id"])
    for l in ls.list():
        ls.update(l["id"], etapa="Selecionado")
    s.set_config("tamanho_lote", 1)
    r1 = run_batch(s, c["id"], gemini=None, use_network=False)
    assert r1["processados"] == 1 and r1["status"] == "PAUSED" and r1["restantes"] == 1
    r2 = run_batch(s, c["id"], gemini=None, use_network=False)  # retoma
    assert r2["processados"] == 1 and r2["status"] == "COMPLETED"
    leads = ls.list()
    assert all(l["etapa"] in ("Qualificado", "Investigado") and l["score"] for l in leads)
    inv = s.all("INVESTIGACOES")
    assert len(inv) == 2 and jload(inv[0]["evidencias"])
    assert len(s.all("QUALIFICACAO")) == 2
    r3 = run_batch(s, c["id"], gemini=None, use_network=False)
    assert r3["processados"] == 0


def test_subscription_limit_stops():
    s, ls, cs = make()
    c = cs.create("T", "Restaurantes", "Porto Alegre", "RS")
    ls.add_leads(RAW, c["id"])
    for l in ls.list():
        ls.update(l["id"], etapa="Selecionado")
    r = run_batch(s, c["id"], gemini=None, subscription_remaining=1, use_network=False)
    assert r["processados"] == 1 and "assinatura" in r["motivo"]


def test_spin_validation_drops_unsupported_opportunities():
    ev = [{"tipo": "fato", "chave": "x", "texto": "t", "fonte": "f", "data": "d"}]
    out = validate_spin({"oportunidades": [{"titulo": "Inventada", "descricao": "d", "evidencia_ref": [99]},
                                           {"titulo": "Real", "descricao": "d", "evidencia_ref": [0]}]}, ev)
    assert [o["titulo"] for o in out["oportunidades"]] == ["Real"]


def test_osm_query_builder_and_parser():
    from discovery.osm import DiscoveryError, build_query, parse_element
    q = build_query(["amenity=restaurant"], {"osm_type": "relation", "osm_id": 1}, 50)
    assert "area(3600000001)" in q and 'out center tags 50' in q
    try:
        build_query(['amenity=x"];out;'], {"osm_type": "relation", "osm_id": 1}, 5)
        assert False
    except DiscoveryError:
        pass
    el = {"type": "node", "id": 7, "lat": -30.0, "lon": -51.0, "tags": {"name": "Z", "contact:phone": "+55 51 3333-4444", "website": "z.com", "addr:street": "Rua A"}}
    lead = parse_element(el, "Restaurantes", "Porto Alegre", "RS")
    assert lead["fonte_id"] == "node/7" and lead["telefone"] and lead["site"] == "z.com"


def test_overpass_fallback_and_errors(monkeypatch):
    import requests
    from discovery import osm

    calls = []

    class R:
        def __init__(self, code, payload=None, bad_json=False):
            self.status_code, self._p, self._bad = code, payload, bad_json

        def json(self):
            if self._bad:
                raise ValueError("x")
            return self._p

    seq = [R(406), R(200, bad_json=True), R(200, {"elements": [{"type": "node", "id": 1, "tags": {"name": "A"}}]})]

    def fake_post(url, **kw):
        calls.append(url)
        return seq[len(calls) - 1]

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(osm, "_ua", lambda: {"User-Agent": "t"})
    assert osm._overpass("q")["elements"][0]["id"] == 1 and len(calls) == 3

    monkeypatch.setattr(requests, "post", lambda *a, **k: R(500))
    try:
        osm._overpass("q")
        assert False
    except osm.DiscoveryError as exc:
        assert "HTTP 500" in str(exc)
