"""Triagem rápida e Lead Scoring 0–100 (determinístico, auditável e sem custo de IA)."""
from __future__ import annotations

from datetime import datetime

from discovery.normalize import norm_text

# Pesos exigidos: 20 + 15 + 25 + 20 + 10 + 10 = 100
WEIGHTS = {"aderencia": 20, "perfil": 15, "necessidade": 25, "oportunidades": 20, "contato": 10, "evidencias": 10}
NOMES = {
    "aderencia": "Aderência ao público-alvo",
    "perfil": "Perfil e potencial do negócio",
    "necessidade": "Necessidade potencial de marketing",
    "oportunidades": "Oportunidades na presença digital",
    "contato": "Facilidade de contato",
    "evidencias": "Qualidade e atualidade das evidências",
}
# Necessidade: lacunas de informação -> HIPÓTESES (não são fatos de problema)
NEED_WEIGHTS = {"site_ausente": 10, "instagram_nao_informado": 6, "canal_digital_nao_encontrado": 5, "site_inacessivel": 4}
# Oportunidades: FATOS observados no site
OPP_WEIGHTS = {"site_sem_cta": 6, "site_sem_whatsapp": 4, "site_sem_https": 4, "site_sem_mobile": 4, "site_sem_descricao": 3}
PORTE_POINTS = {"demais": 6, "epp": 5, "empresa de pequeno porte": 5, "me": 4, "microempresa": 4, "mei": 2}


def classify(score: float) -> str:
    if score >= 80:
        return "Alta prioridade"
    if score >= 60:
        return "Média prioridade"
    if score >= 40:
        return "Baixa prioridade"
    return "Baixa aderência"


def _segment_match(lead: dict, alvo: str) -> bool:
    a, b = norm_text(lead.get("segmento", "")), norm_text(alvo)
    return bool(a and b and (a in b or b in a or set(a.split()) & set(b.split())))


def _porte_points(porte: str) -> int:
    return PORTE_POINTS.get(norm_text(porte), 0)


def triage(lead: dict, alvo_segmento: str = "", alvo_cidade: str = "") -> dict:
    """Primeira avaliação barata: relevância + possibilidade de contato + sinais de perfil (0–100)."""
    pts, why = 0, []
    if _segment_match(lead, alvo_segmento or lead.get("segmento", "")) and lead.get("segmento"):
        pts += 25
        why.append("segmento compatível (+25)")
    if lead.get("cidade") and (not alvo_cidade or norm_text(lead["cidade"]) == norm_text(alvo_cidade)):
        pts += 15
        why.append("localização compatível (+15)")
    for field, p, label in (("telefone", 12, "telefone"), ("email", 6, "e-mail"), ("site", 8, "site"), ("instagram", 4, "Instagram")):
        if lead.get(field):
            pts += p
            why.append(f"{label} disponível (+{p})")
    if lead.get("endereco"):
        pts += 8
        why.append("endereço identificado (+8)")
    if lead.get("horario"):
        pts += 6
        why.append("horário informado (+6)")
    if lead.get("cnpj"):
        pts += 6
        why.append("CNPJ válido (+6)")
    pp = _porte_points(lead.get("porte", ""))
    if pp:
        pts += pp
        why.append(f"porte informado (+{pp})")
    pts = min(100, pts)
    prio = "Alta prioridade" if pts >= 70 else "Média prioridade" if pts >= 50 else "Baixa prioridade" if pts >= 30 else "Não qualificado"
    return {"prioridade": prio, "pontos": pts, "motivo": "; ".join(why) or "poucos dados disponíveis"}


def _by_key(evidences: list[dict]) -> dict:
    return {e["chave"]: e for e in evidences}


def score_lead(lead: dict, evidences: list[dict], alvo_segmento: str = "", alvo_cidade: str = "", now: datetime | None = None) -> dict:
    ev = _by_key(evidences)
    crit: dict[str, dict] = {k: {"chave": k, "nome": NOMES[k], "peso": WEIGHTS[k], "pontos": 0, "justificativas": []} for k in WEIGHTS}

    def add(k: str, pts: int, why: str):
        crit[k]["pontos"] += pts
        crit[k]["justificativas"].append(f"+{pts}: {why}")

    # 1. Aderência (20)
    if lead.get("segmento") and _segment_match(lead, alvo_segmento or lead.get("segmento", "")):
        add("aderencia", 14, "segmento compatível com o público-alvo da campanha")
    elif not lead.get("segmento"):
        crit["aderencia"]["justificativas"].append("0: segmento não informado")
    if lead.get("cidade") and (not alvo_cidade or norm_text(lead["cidade"]) == norm_text(alvo_cidade)):
        add("aderencia", 6, "empresa na localização-alvo")

    # 2. Perfil (15)
    if lead.get("endereco"):
        add("perfil", 3, "estabelecimento com endereço identificado")
    if lead.get("horario"):
        add("perfil", 3, "horário de funcionamento publicado (operação ativa)")
    if lead.get("cnpj") or "cnpj_situacao" in ev:
        add("perfil", 3, "CNPJ identificado")
    pp = _porte_points(lead.get("porte", "")) or (_porte_points(ev["cnpj_porte"]["texto"].split(":")[-1].strip()) if "cnpj_porte" in ev else 0)
    if pp:
        add("perfil", pp, "porte empresarial informado")
    if "site_acessado" in ev or lead.get("site"):
        add("perfil", 3, "possui site (negócio estruturado)")

    # 3. Necessidade potencial (25) — hipóteses por lacunas
    for k, w in NEED_WEIGHTS.items():
        if k in ev:
            add("necessidade", w, f"hipótese: {ev[k]['texto'][:90]}")
    # 4. Oportunidades observadas (20) — fatos no site
    for k, w in OPP_WEIGHTS.items():
        if k in ev:
            add("oportunidades", w, f"fato observado: {ev[k]['texto'][:90]}")

    # 5. Contato (10)
    for field, p, label in (("telefone", 4, "telefone público"), ("email", 2, "e-mail público"), ("site", 1, "site"), ("instagram", 1, "Instagram")):
        if lead.get(field):
            add("contato", p, label)
    if "whatsapp_no_site" in ev:
        add("contato", 2, "WhatsApp no site")

    # 6. Qualidade das evidências (10)
    fatos = [e for e in evidences if e["tipo"] == "fato" and e.get("fonte") and e.get("data")]
    if fatos:
        add("evidencias", min(10, 2 * len(fatos)), f"{len(fatos)} fato(s) observado(s) com fonte e data")

    for c in crit.values():
        c["pontos"] = min(c["pontos"], c["peso"])
    score = round(sum(c["pontos"] for c in crit.values()))

    # Confiança separada do score
    n_fatos = len(fatos)
    fontes = {e["fonte"] for e in fatos}
    conf = min(40, n_fatos * 6) + (30 if "site_acessado" in ev else 0) + min(20, len(fontes) * 10) + (10 if "site_inacessivel" not in ev else 0)
    conf = min(100, conf)
    nivel = "Alta" if conf >= 70 else "Média" if conf >= 40 else "Baixa"
    return {
        "score": score,
        "classificacao": classify(score),
        "confianca": conf,
        "confianca_nivel": nivel,
        "criterios": list(crit.values()),
    }
