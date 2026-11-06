"""Investigação (por lead) e processamento por lotes, com checkpoint após cada lote e retomada."""
from __future__ import annotations

import time
from datetime import datetime

from ai.gemini import GeminiError, QuotaExceeded, estimate_tokens
from ai.scoring import score_lead
from ai.spin_selling import SYSTEM, build_user_prompt, fallback_spin, validate_spin
from core.config import DEFAULT_LIMITS, jdump, jload, new_id, now, now_iso
from core.permissions import quota_remaining
from discovery.cnpj import fetch_cnpj_brasilapi
from research.digital_presence import build_evidences
from research.evidence import input_hash
from research.website import analyze_site

VALIDITY_DAYS = 30


def _fresh(inv: dict | None) -> bool:
    if not inv:
        return False
    try:
        age = now() - datetime.fromisoformat(inv["data"])
        return age.days < VALIDITY_DAYS
    except Exception:
        return False


def investigate_lead(lead: dict, *, campaign: dict | None = None, existing: dict | None = None, gemini=None,
                     perfil_usuario: str = "", force: bool = False, use_network: bool = True) -> dict:
    """Investiga um lead. Retorna linhas prontas para persistir + flags de uso."""
    site = analyze_site(lead["site"]) if (use_network and lead.get("site")) else None
    cnpj_data = fetch_cnpj_brasilapi(lead["cnpj"]) if (use_network and lead.get("cnpj")) else None
    evidences = build_evidences(lead, site, cnpj_data)
    h = input_hash(lead, evidences)

    reused = bool(existing and existing.get("input_hash") == h and _fresh(existing) and not force)
    ai_used = False
    quota_hit = False
    if reused:
        analysis = jload(existing["analise"], {})
        origem = existing.get("origem_analise", "regras")
        tokens = 0
    else:
        analysis, origem, tokens = None, "regras", 0
        if gemini is not None:
            try:
                prompt = build_user_prompt(lead, evidences, perfil_usuario)
                raw = gemini.generate_json(SYSTEM, prompt)
                analysis = validate_spin(raw, evidences)
                origem, ai_used = "gemini", True
                tokens = estimate_tokens(prompt) + estimate_tokens(jdump(raw))
            except QuotaExceeded as exc:
                quota_hit, origem = True, f"regras ({exc})"
            except GeminiError as exc:
                origem = f"regras ({exc})"
        if analysis is None:
            analysis = fallback_spin(lead, evidences)

    alvo_seg = (campaign or {}).get("segmento", "")
    alvo_cid = (campaign or {}).get("cidade", "")
    qual = score_lead(lead, evidences, alvo_seg, alvo_cid)
    ts = now_iso()
    limitacoes = [e["texto"] for e in evidences if e["chave"] in ("site_inacessivel",)]
    inv_row = {
        "id": (existing or {}).get("id") if reused else new_id("iv"), "lead_id": lead["id"], "data": (existing or {}).get("data", ts) if reused else ts,
        "input_hash": h, "origem_analise": origem, "evidencias": jdump(evidences), "analise": jdump(analysis),
        "limitacoes": jdump(limitacoes), "tokens_estimados": tokens,
    }
    qual_row = {"lead_id": lead["id"], "score": qual["score"], "classificacao": qual["classificacao"], "confianca": qual["confianca"],
                "confianca_nivel": qual["confianca_nivel"], "criterios": jdump(qual["criterios"]), "data": ts}
    novo_site = lead.get("site") or ""
    patch = {
        "id": lead["id"], "score": qual["score"], "classificacao": qual["classificacao"], "confianca": qual["confianca"],
        "etapa": "Qualificado" if qual["classificacao"] != "Baixa aderência" else "Investigado",
        "proxima_acao": analysis.get("proxima_acao", ""), "tentativas": 0, "erro": "", "site": novo_site,
        "atualizado_em": ts,
    }
    return {"inv_row": inv_row, "qual_row": qual_row, "lead_patch": patch, "reused": reused, "ai_used": ai_used, "quota_hit": quota_hit}


def persist_results(store, results: list[dict]) -> None:
    """Ordem importa: evidências → qualificação → lead. Se interromper antes do último passo, o lead
    continua 'Selecionado' e a retomada reaproveita a análise (hash igual) sem nova chamada de IA."""
    if not results:
        return
    store.upsert("INVESTIGACOES", [r["inv_row"] for r in results], key="id")
    store.upsert("QUALIFICACAO", [r["qual_row"] for r in results], key="lead_id")
    store.upsert("LEADS", [r["lead_patch"] for r in results], key="id")


def run_batch(store, campaign_id: str, *, gemini=None, subscription_remaining: int = 10**9, perfil_usuario: str = "",
              use_network: bool = True, on_progress=None) -> dict:
    """Processa UM lote da campanha. Pode ser chamado repetidamente (retoma de onde parou)."""
    from services.campaign_service import CampaignService

    cs = CampaignService(store)
    camp = cs.get(campaign_id)
    if not camp:
        raise ValueError("Campanha não encontrada.")
    if camp["status"] == "COMPLETED":
        return {"processados": 0, "motivo": "Campanha já concluída.", "restantes": 0, "status": "COMPLETED"}

    batch = int(store.get_config("tamanho_lote", DEFAULT_LIMITS["tamanho_lote"]))
    budget = float(store.get_config("tempo_lote_segundos", DEFAULT_LIMITS["tempo_lote_segundos"]))
    cs.set_status(campaign_id, "RUNNING")

    all_leads = store.all("LEADS")
    pending = [l for l in all_leads if l.get("campanha_id") == campaign_id and l.get("etapa") == "Selecionado" and int(float(l.get("tentativas") or 0)) < 2]
    limit_inv = int(float(camp.get("limite_investigacoes") or DEFAULT_LIMITS["limite_investigacoes_campanha"]))
    done_before = int(float(camp.get("investigados") or 0))
    allowed = min(batch, max(0, limit_inv - done_before), subscription_remaining)
    existing_inv = {i["lead_id"]: i for i in store.all("INVESTIGACOES")}

    results, failures, stop = [], [], ""
    t0 = time.time()
    for lead in pending[:allowed]:
        if time.time() - t0 > budget:
            stop = "Tempo máximo do lote atingido."
            break
        try:
            r = investigate_lead(lead, campaign=camp, existing=existing_inv.get(lead["id"]), gemini=gemini,
                                 perfil_usuario=perfil_usuario, use_network=use_network)
            results.append(r)
            if r["quota_hit"]:
                gemini = None  # não insiste na IA neste lote
            if on_progress:
                on_progress(len(results), min(len(pending), allowed), lead["nome"])
        except Exception as exc:  # um lead com falha não derruba o lote
            failures.append({"id": lead["id"], "tentativas": int(float(lead.get("tentativas") or 0)) + 1, "erro": f"{type(exc).__name__}: {exc}"[:200]})

    persist_results(store, results)
    if failures:
        store.upsert("LEADS", failures, key="id")
    if getattr(gemini, "flush", None):
        gemini.flush()
    cs.refresh_counts(campaign_id)

    new_done = done_before + len(results)
    remaining_leads = max(0, len(pending) - len(results) - len(failures))
    if new_done >= limit_inv and remaining_leads:
        stop = stop or "Limite de investigações da campanha atingido."
    if subscription_remaining <= len(results) and remaining_leads:
        stop = stop or "Limite de pesquisas da assinatura atingido."
    finished = remaining_leads == 0 or new_done >= limit_inv
    status = "COMPLETED" if finished else "PAUSED"
    if not results and failures and len(failures) == len(pending[:allowed]):
        status = "FAILED" if finished else "PAUSED"
    cs.set_status(campaign_id, status, stop)
    return {"processados": len(results), "falhas": len(failures), "reaproveitados": sum(1 for r in results if r["reused"]),
            "ia": sum(1 for r in results if r["ai_used"]), "restantes": remaining_leads, "status": status, "motivo": stop,
            "consumo": len(results)}
