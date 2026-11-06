"""Métricas do dashboard calculadas apenas com dados reais."""
from __future__ import annotations

from collections import Counter
from datetime import date

from core.permissions import parse_date
from services.lead_service import CLOSED


def compute(leads, quals, invs, msgs, camps, acts, today: date) -> dict:
    inv_ids = {i["lead_id"] for i in invs}
    qualified = [q for q in quals if q.get("classificacao") != "Baixa aderência"]
    high = [q for q in quals if q.get("classificacao") == "Alta prioridade"]
    follow = [l for l in leads if l.get("etapa") in ("Contato realizado", "Em negociação")]
    msg_leads = {m["lead_id"] for m in msgs}
    active_camps = [c for c in camps if c.get("status") in ("PENDING", "RUNNING", "PAUSED")]

    by_day = Counter((l.get("criado_em") or "")[:10] for l in leads if l.get("criado_em"))
    days = sorted(by_day)
    evolution, cum = [], 0
    for d in days:
        cum += by_day[d]
        evolution.append({"data": d, "novos": by_day[d], "acumulado": cum})

    dist = Counter(q.get("classificacao", "") for q in quals)
    open_leads = [l for l in leads if l.get("etapa") not in CLOSED]
    overdue = [l for l in open_leads if (d := parse_date(l.get("proxima_acao_data"))) and d < today]
    due_today = [l for l in open_leads if (d := parse_date(l.get("proxima_acao_data"))) and d == today]
    pipeline = [l for l in open_leads if l.get("etapa") in ("Qualificado", "Abordagem preparada", "Contato realizado", "Em negociação")]

    health_parts = {}
    if pipeline:
        health_parts["Leads com próximo passo"] = round(100 * sum(1 for l in pipeline if l.get("proxima_acao")) / len(pipeline))
        contacted = [l for l in pipeline if l.get("etapa") in ("Contato realizado", "Em negociação")]
        if contacted:
            recent = {a["lead_id"] for a in acts if a.get("tipo") in ("contato", "etapa") and (parse_date(a.get("data")) or date.min) >= date.fromordinal(today.toordinal() - 7)}
            health_parts["Contato nos últimos 7 dias"] = round(100 * sum(1 for l in contacted if l["id"] in recent) / len(contacted))
        health_parts["Tarefas em dia"] = round(100 * (1 - len([l for l in pipeline if l in overdue]) / len(pipeline)))
    health = round(sum(health_parts.values()) / len(health_parts)) if health_parts else None

    return {
        "total": len(leads), "investigados": len(inv_ids), "qualificados": len(qualified), "alto": len(high),
        "acompanhamento": len(follow), "abordagens": len(msg_leads), "campanhas": len(camps), "campanhas_ativas": len(active_camps),
        "taxa": round(100 * len(qualified) / len(inv_ids)) if inv_ids else None,
        "evolution": evolution, "dist": dict(dist), "overdue": overdue, "due_today": due_today,
        "pipeline": pipeline, "health": health, "health_parts": health_parts, "active_camps": active_camps,
    }
