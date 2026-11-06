"""Regras de negócio de leads: inserção sem duplicidade, supressão, etapas e atividades."""
from __future__ import annotations

from core.config import new_id, now_iso
from discovery.normalize import dedupe, dedupe_keys, normalize_lead, norm_name, norm_phone

STAGES = ["Encontrado", "Selecionado", "Investigado", "Qualificado", "Abordagem preparada", "Contato realizado",
          "Em negociação", "Convertido", "Perdido", "Não contatar"]
CLOSED = {"Convertido", "Perdido", "Não contatar"}


class LeadService:
    def __init__(self, store, user_email: str = ""):
        self.store = store
        self.user = user_email

    # ---------- leitura ----------
    def list(self) -> list[dict]:
        return self.store.all("LEADS")

    def get(self, lead_id: str) -> dict | None:
        return next((l for l in self.list() if l["id"] == lead_id), None)

    # ---------- supressão ----------
    def suppression_values(self) -> set[str]:
        return {f"{r['tipo']}:{r['valor']}" for r in self.store.all("SUPRESSAO")}

    def is_suppressed(self, lead: dict, supp: set[str] | None = None) -> bool:
        supp = supp if supp is not None else self.suppression_values()
        cands = []
        if lead.get("cnpj"):
            cands.append("cnpj:" + lead["cnpj"])
        if lead.get("dominio"):
            cands.append("dominio:" + lead["dominio"])
        tel = lead.get("telefone_norm") or norm_phone(lead.get("telefone"))
        if tel:
            cands.append("telefone:" + tel)
        if lead.get("email"):
            cands.append("email:" + lead["email"].lower())
        if lead.get("nome"):
            cands.append("nome:" + norm_name(lead["nome"]))
        return any(c in supp for c in cands)

    def add_suppression(self, tipo: str, valor: str, motivo: str = "") -> None:
        valor = valor.strip().lower() if tipo in ("email", "dominio") else valor.strip()
        if not valor:
            return
        if f"{tipo}:{valor}" in self.suppression_values():
            return
        self.store.append("SUPRESSAO", [{"id": new_id("sp"), "tipo": tipo, "valor": valor, "motivo": motivo, "data": now_iso()}])

    def suppress_lead(self, lead: dict, motivo: str) -> None:
        for tipo, val in (("cnpj", lead.get("cnpj")), ("dominio", lead.get("dominio")), ("telefone", lead.get("telefone_norm")),
                          ("email", lead.get("email")), ("nome", norm_name(lead.get("nome")))):
            if val:
                self.add_suppression(tipo, val, motivo)

    # ---------- inserção ----------
    def add_leads(self, raw_leads: list[dict], campanha_id: str, limite_empresas: int | None = None) -> dict:
        existing = self.list()
        supp = self.suppression_values()
        normalized = [normalize_lead(r) for r in raw_leads]
        allowed = [l for l in normalized if not self.is_suppressed(l, supp)]
        suppressed = len(normalized) - len(allowed)
        unique, dups = dedupe(allowed, existing)
        if limite_empresas is not None:
            room = max(0, limite_empresas - len([l for l in existing if l.get("campanha_id") == campanha_id]))
            truncated = max(0, len(unique) - room)
            unique = unique[:room]
        else:
            truncated = 0
        ts = now_iso()
        for l in unique:
            l.update({"campanha_id": campanha_id, "etapa": "Encontrado", "criado_em": ts, "atualizado_em": ts, "tentativas": "0"})
        self.store.append("LEADS", unique)
        return {"inseridos": len(unique), "duplicados": len(dups), "suprimidos": suppressed, "acima_do_limite": truncated,
                "ids": [l["id"] for l in unique]}

    # ---------- atualização ----------
    def update(self, lead_id: str, **fields) -> None:
        fields["id"] = lead_id
        fields["atualizado_em"] = now_iso()
        self.store.upsert("LEADS", [fields], key="id")

    def bulk_update(self, rows: list[dict]) -> None:
        ts = now_iso()
        self.store.upsert("LEADS", [{**r, "atualizado_em": ts} for r in rows], key="id")

    def set_stage(self, lead: dict, etapa: str, nota: str = "") -> None:
        if etapa not in STAGES:
            raise ValueError("Etapa inválida")
        self.update(lead["id"], etapa=etapa)
        self.log(lead["id"], "etapa", f"{lead.get('etapa','')} → {etapa}" + (f" — {nota}" if nota else ""))
        if etapa == "Não contatar":
            self.suppress_lead(lead, "Marcado como Não contatar")

    # ---------- atividades ----------
    def log(self, lead_id: str, tipo: str, descricao: str) -> None:
        self.store.append("ATIVIDADES", [{"id": new_id("at"), "lead_id": lead_id, "tipo": tipo, "descricao": descricao,
                                          "data": now_iso(), "usuario": self.user}])

    def activities(self, lead_id: str | None = None) -> list[dict]:
        rows = self.store.all("ATIVIDADES")
        rows = [r for r in rows if not lead_id or r["lead_id"] == lead_id]
        return sorted(rows, key=lambda r: r.get("data", ""), reverse=True)

    # ---------- exclusão (LGPD) ----------
    def delete_lead(self, lead_id: str) -> None:
        for tab, key in (("LEADS", "id"), ("INVESTIGACOES", "lead_id"), ("QUALIFICACAO", "lead_id"),
                         ("MENSAGENS", "lead_id"), ("ATIVIDADES", "lead_id")):
            self.store.delete(tab, key, lead_id)
