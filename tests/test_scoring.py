from ai.scoring import WEIGHTS, classify, score_lead, triage
from research.digital_presence import build_evidences

LEAD = {"nome": "Casa do Sabor", "segmento": "Restaurantes", "cidade": "Porto Alegre", "uf": "RS", "telefone": "(51) 99999-1111",
        "endereco": "Rua A 10", "horario": "Mo-Su 11:00-23:00", "fonte": "openstreetmap", "fonte_url": "https://osm.org/node/1", "data_fonte": "2026-11-03T10:00:00-03:00"}


def test_weights_sum_100():
    assert sum(WEIGHTS.values()) == 100


def test_classify_boundaries():
    assert classify(80) == "Alta prioridade" and classify(79) == "Média prioridade"
    assert classify(60) == "Média prioridade" and classify(59) == "Baixa prioridade"
    assert classify(40) == "Baixa prioridade" and classify(39) == "Baixa aderência"


def test_score_has_justifications_and_caps():
    ev = build_evidences(LEAD)
    r = score_lead(LEAD, ev, "Restaurantes", "Porto Alegre")
    assert 0 <= r["score"] <= 100
    for c in r["criterios"]:
        assert c["pontos"] <= c["peso"]
    assert any(c["justificativas"] for c in r["criterios"])


def test_missing_site_is_hypothesis_not_fact():
    ev = build_evidences(LEAD)
    e = next(x for x in ev if x["chave"] == "site_ausente")
    assert e["tipo"] == "nao_encontrado"
    r = score_lead(LEAD, ev, "Restaurantes", "Porto Alegre")
    assert next(c for c in r["criterios"] if c["chave"] == "necessidade")["pontos"] >= 10
    assert next(c for c in r["criterios"] if c["chave"] == "oportunidades")["pontos"] == 0  # sem fatos de site


def test_confidence_separate_from_score():
    ev = build_evidences({"nome": "X", "segmento": "Restaurantes", "cidade": "Porto Alegre"})
    r = score_lead({"nome": "X", "segmento": "Restaurantes", "cidade": "Porto Alegre"}, ev, "Restaurantes", "Porto Alegre")
    assert r["confianca_nivel"] == "Baixa"


def test_site_facts_raise_opportunity_score():
    site = {"ok": True, "url_final": "https://x.com", "data": "2026-11-03", "https": False, "viewport": False, "descricao": "", "ctas": [], "whatsapp": False, "redes": {}, "titulo": "X", "h1": ""}
    lead = {**LEAD, "site": "https://x.com"}
    ev = build_evidences(lead, site)
    r = score_lead(lead, ev, "Restaurantes", "Porto Alegre")
    assert next(c for c in r["criterios"] if c["chave"] == "oportunidades")["pontos"] == 20
    assert r["confianca_nivel"] in ("Média", "Alta")


def test_triage_levels():
    t = triage({**LEAD, "email": "a@b.com", "site": "https://x.com"}, "Restaurantes", "Porto Alegre")
    assert t["prioridade"] == "Alta prioridade"
    assert triage({"nome": "Z"})["prioridade"] == "Não qualificado"
