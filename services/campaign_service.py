"""Campanhas e seus estados: PENDING, RUNNING, PAUSED, COMPLETED, FAILED."""
from __future__ import annotations

from core.config import DEFAULT_LIMITS, new_id, now_iso

STATES = ("PENDING", "RUNNING", "PAUSED", "COMPLETED", "FAILED")
ACTIVE = ("PENDING", "RUNNING", "PAUSED")
LABELS = {"PENDING": "Pendente", "RUNNING": "Em execução", "PAUSED": "Pausada", "COMPLETED": "Concluída", "FAILED": "Falhou"}


class CampaignService:
    def __init__(self, store):
        self.store = store

    def list(self) -> list[dict]:
        return sorted(self.store.all("CAMPANHAS"), key=lambda c: c.get("criado_em", ""), reverse=True)

    def get(self, cid: str) -> dict | None:
        return next((c for c in self.list() if c["id"] == cid), None)

    def create(self, nome, segmento, cidade, uf, objetivo="", limite_empresas=None, limite_investigacoes=None) -> dict:
        ts = now_iso()
        camp = {
            "id": new_id("cp"), "nome": nome.strip() or f"{segmento} - {cidade}", "segmento": segmento, "cidade": cidade, "uf": uf,
            "objetivo": objetivo, "status": "PENDING",
            "limite_empresas": int(limite_empresas or self.store.get_config("limite_empresas_campanha", DEFAULT_LIMITS["limite_empresas_campanha"])),
            "limite_investigacoes": int(limite_investigacoes or self.store.get_config("limite_investigacoes_campanha", DEFAULT_LIMITS["limite_investigacoes_campanha"])),
            "total_encontrados": 0, "investigados": 0, "nota": "", "criado_em": ts, "atualizado_em": ts,
        }
        self.store.append("CAMPANHAS", [camp])
        return camp

    def set_status(self, cid: str, status: str, nota: str = "") -> None:
        if status not in STATES:
            raise ValueError("Status inválido")
        self.store.upsert("CAMPANHAS", [{"id": cid, "status": status, "nota": nota, "atualizado_em": now_iso()}])

    def refresh_counts(self, cid: str) -> None:
        leads = [l for l in self.store.all("LEADS") if l.get("campanha_id") == cid]
        inv_ids = {i["lead_id"] for i in self.store.all("INVESTIGACOES")}
        done = sum(1 for l in leads if l["id"] in inv_ids)
        self.store.upsert("CAMPANHAS", [{"id": cid, "total_encontrados": len(leads), "investigados": done, "atualizado_em": now_iso()}])
