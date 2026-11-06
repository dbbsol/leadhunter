from discovery.normalize import dedupe, dedupe_keys, norm_domain, norm_phone, normalize_lead
from discovery.cnpj import is_valid_cnpj


def L(**k):
    return normalize_lead({"nome": "Bar do Zé", "cidade": "Porto Alegre", "uf": "RS", **k})


def test_phone_normalization():
    assert norm_phone("+55 (51) 99999-1111") == "51999991111"
    assert norm_phone("123") == ""


def test_domain_ignores_social():
    assert norm_domain("https://www.exemplo.com.br/x") == "exemplo.com.br"
    assert L(site="https://instagram.com/bar")["dominio"] == ""


def test_dedupe_by_phone_domain_cnpj_and_source():
    base = [{**L(telefone="51999991111", site="https://zé.com"), "id": "a"}]
    new = [L(nome="Outro nome", telefone="(51) 99999-1111"), L(nome="Outro 2", site="http://www.zé.com/"),
           L(nome="Novo", fonte="osm", fonte_id="node/1"), L(nome="Novo 2", fonte="osm", fonte_id="node/1")]
    uniq, dups = dedupe(new, base)
    assert len(uniq) == 1 and len(dups) == 3


def test_dedupe_cnpj():
    c = "11.222.333/0001-81"
    assert is_valid_cnpj(c)
    uniq, dups = dedupe([L(cnpj=c, nome="A"), L(cnpj="11222333000181", nome="B")], [])
    assert len(uniq) == 1 and len(dups) == 1


def test_name_city_address_requires_address():
    assert not any(k.startswith("nca:") for k in dedupe_keys(L()))
    assert any(k.startswith("nca:") for k in dedupe_keys(L(endereco="Rua A 1")))


def test_ids_unique():
    uniq, _ = dedupe([L(nome=f"E{i}", telefone=f"5199999{i:04d}") for i in range(20)], [])
    assert len({u["id"] for u in uniq}) == 20
