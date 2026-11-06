"""Esquema das planilhas e contrato de armazenamento (Sheets ou memória de teste)."""
from __future__ import annotations

import csv
import io
import time
import zipfile

from core.config import now_iso

LEAD_FIELDS = [
    "id", "campanha_id", "nome", "segmento", "cidade", "uf", "bairro", "endereco", "telefone",
    "telefone_norm", "site", "dominio", "cnpj", "email", "instagram", "horario", "porte",
    "fonte", "fonte_id", "fonte_url", "data_fonte", "lat", "lon", "etapa", "triagem",
    "triagem_pontos", "triagem_motivo", "score", "classificacao", "confianca", "proxima_acao",
    "proxima_acao_data", "observacoes", "tentativas", "erro", "criado_em", "atualizado_em",
]

TENANT_SCHEMA = {
    "CAMPANHAS": ["id", "nome", "segmento", "cidade", "uf", "objetivo", "status", "limite_empresas",
                  "limite_investigacoes", "total_encontrados", "investigados", "nota", "criado_em", "atualizado_em"],
    "LEADS": LEAD_FIELDS,
    "INVESTIGACOES": ["id", "lead_id", "data", "input_hash", "origem_analise", "evidencias", "analise",
                      "limitacoes", "tokens_estimados"],
    "QUALIFICACAO": ["lead_id", "score", "classificacao", "confianca", "confianca_nivel", "criterios", "data"],
    "MENSAGENS": ["id", "lead_id", "canal", "estilo", "objetivo", "conteudo", "status", "criado_em"],
    "ATIVIDADES": ["id", "lead_id", "tipo", "descricao", "data", "usuario"],
    "SUPRESSAO": ["id", "tipo", "valor", "motivo", "data"],
    "CONFIGURACOES": ["chave", "valor", "atualizado_em"],
}

ADMIN_SCHEMA = {
    "CLIENTES": ["email", "nome", "empresa", "criado_em"],
    "ASSINATURAS": ["email", "nome", "plano", "inicio", "vencimento", "status", "limite_pesquisas", "consumo", "planilha_id"],
}


def to_cell(value) -> str:
    """Converte qualquer valor para texto de célula (limite do Sheets: 50.000 caracteres)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)[:45000]


class BaseStore:
    """Contrato mínimo. Implementações: SheetsStore (produção) e MemoryStore (testes)."""

    schema: dict
    spreadsheet_id: str

    def all(self, tab: str, fresh: bool = False) -> list[dict]:
        raise NotImplementedError

    def append(self, tab: str, rows: list[dict]) -> None:
        raise NotImplementedError

    def upsert(self, tab: str, rows: list[dict], key: str = "id") -> dict:
        raise NotImplementedError

    def delete(self, tab: str, key: str, value: str) -> int:
        raise NotImplementedError

    # ---- utilidades derivadas ----
    def get_config(self, key: str, default=None):
        for row in self.all("CONFIGURACOES"):
            if row.get("chave") == key:
                return row.get("valor", default)
        return default

    def set_config(self, key: str, value) -> None:
        self.upsert("CONFIGURACOES", [{"chave": key, "valor": to_cell(value), "atualizado_em": now_iso()}], key="chave")

    def healthcheck(self) -> dict:
        """Teste real de escrita + leitura (fresca) na planilha."""
        token = f"ok-{int(time.time())}"
        t0 = time.time()
        self.set_config("_healthcheck", token)
        back = None
        for row in self.all("CONFIGURACOES", fresh=True):
            if row.get("chave") == "_healthcheck":
                back = row.get("valor")
        return {"ok": back == token, "latencia_s": round(time.time() - t0, 2), "escrito": token, "lido": back}

    def export_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for tab, headers in self.schema.items():
                out = io.StringIO()
                w = csv.writer(out)
                w.writerow(headers)
                for row in self.all(tab, fresh=True):
                    w.writerow([row.get(h, "") for h in headers])
                zf.writestr(f"{tab}.csv", out.getvalue())
        return buf.getvalue()


class MemoryStore(BaseStore):
    """Armazenamento em memória — SOMENTE para testes e modo local de teste."""

    def __init__(self, schema: dict, spreadsheet_id: str = "memory"):
        self.schema = schema
        self.spreadsheet_id = spreadsheet_id
        self._data = {tab: [] for tab in schema}

    def all(self, tab, fresh=False):
        return [dict(r) for r in self._data[tab]]

    def append(self, tab, rows):
        headers = self.schema[tab]
        for r in rows:
            self._data[tab].append({h: to_cell(r.get(h, "")) for h in headers})

    def upsert(self, tab, rows, key="id"):
        headers = self.schema[tab]
        idx = {r.get(key): r for r in self._data[tab]}
        ins = upd = 0
        for r in rows:
            k = to_cell(r.get(key, ""))
            if k in idx:
                idx[k].update({h: to_cell(v) for h, v in r.items() if h in headers})
                upd += 1
            else:
                new = {h: to_cell(r.get(h, "")) for h in headers}
                self._data[tab].append(new)
                idx[k] = new
                ins += 1
        return {"inserted": ins, "updated": upd}

    def delete(self, tab, key, value):
        before = len(self._data[tab])
        self._data[tab] = [r for r in self._data[tab] if r.get(key) != value]
        return before - len(self._data[tab])
