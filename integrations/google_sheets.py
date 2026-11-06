"""Google Sheets como armazenamento. Operações em lote, cache curto e backoff exponencial."""
from __future__ import annotations

import random
import time

import gspread
from gspread.exceptions import APIError
from gspread.utils import rowcol_to_a1

from integrations.storage import BaseStore, to_cell

RETRY_CODES = {429, 500, 502, 503, 504}


def with_backoff(fn, *args, tries: int = 6, **kwargs):
    """Repete em limites de cota/erros transitórios com espera exponencial."""
    delay = 1.0
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except APIError as exc:
            code = getattr(getattr(exc, "response", None), "status_code", 0)
            if code in RETRY_CODES and attempt < tries - 1:
                time.sleep(delay + random.random() * 0.4)
                delay *= 2
                continue
            raise


class SheetsStore(BaseStore):
    def __init__(self, client: gspread.Client, spreadsheet_id: str, schema: dict, cache_ttl: float = 20.0):
        self.schema = schema
        self.spreadsheet_id = spreadsheet_id
        self._ttl = cache_ttl
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._sh = with_backoff(client.open_by_key, spreadsheet_id)
        self._ws_cache: dict[str, gspread.Worksheet] = {}

    # ---------- estrutura ----------
    def ensure_schema(self) -> list[str]:
        """Cria abas/cabeçalhos que faltarem. Nunca apaga dados. Retorna o que foi criado."""
        created = []
        existing = {w.title: w for w in with_backoff(self._sh.worksheets)}
        for tab, headers in self.schema.items():
            ws = existing.get(tab)
            if ws is None:
                ws = with_backoff(self._sh.add_worksheet, title=tab, rows=1000, cols=max(len(headers), 8))
                with_backoff(ws.update, range_name="A1", values=[headers])
                created.append(tab)
            else:
                first = with_backoff(ws.row_values, 1)
                if first != headers:
                    if not first:
                        with_backoff(ws.update, range_name="A1", values=[headers])
                        created.append(tab)
                    else:
                        missing = [h for h in headers if h not in first]
                        if missing:  # só acrescenta colunas novas ao final
                            with_backoff(ws.update, range_name=rowcol_to_a1(1, len(first) + 1), values=[missing])
            self._ws_cache[tab] = ws
        return created

    def _ws(self, tab: str):
        if tab not in self._ws_cache:
            self._ws_cache[tab] = with_backoff(self._sh.worksheet, tab)
        return self._ws_cache[tab]

    def _sheet_headers(self, tab: str) -> list[str]:
        return self.schema[tab]

    # ---------- leitura ----------
    def all(self, tab, fresh=False):
        hit = self._cache.get(tab)
        if hit and not fresh and time.time() - hit[0] < self._ttl:
            return [dict(r) for r in hit[1]]
        values = with_backoff(self._ws(tab).get_all_values)
        if not values:
            rows: list[dict] = []
        else:
            headers = values[0]
            rows = [
                {h: (r[i] if i < len(r) else "") for i, h in enumerate(headers)}
                for r in values[1:] if any(c != "" for c in r)
            ]
        self._cache[tab] = (time.time(), rows)
        return [dict(r) for r in rows]

    # ---------- escrita (sempre em lote) ----------
    def append(self, tab, rows):
        if not rows:
            return
        headers = self.schema[tab]
        data = [[to_cell(r.get(h, "")) for h in headers] for r in rows]
        with_backoff(self._ws(tab).append_rows, data, value_input_option="RAW")
        self._cache.pop(tab, None)

    def upsert(self, tab, rows, key="id"):
        if not rows:
            return {"inserted": 0, "updated": 0}
        headers = self.schema[tab]
        ws = self._ws(tab)
        values = with_backoff(ws.get_all_values)
        sheet_headers = values[0] if values else headers
        kidx = sheet_headers.index(key)
        index: dict[str, tuple[int, dict]] = {}
        for n, r in enumerate(values[1:], start=2):
            if len(r) > kidx and r[kidx]:
                index[r[kidx]] = (n, {h: (r[i] if i < len(r) else "") for i, h in enumerate(sheet_headers)})
        updates, new_rows = [], {}
        for row in rows:
            k = to_cell(row.get(key, ""))
            clean = {h: to_cell(v) for h, v in row.items() if h in sheet_headers}
            if k in index:
                n, cur = index[k]
                cur.update(clean)
                updates.append({
                    "range": f"{rowcol_to_a1(n, 1)}:{rowcol_to_a1(n, len(sheet_headers))}",
                    "values": [[cur.get(h, "") for h in sheet_headers]],
                })
            elif k in new_rows:
                new_rows[k].update(clean)
            else:
                new_rows[k] = {h: "" for h in sheet_headers} | clean
        if updates:
            with_backoff(ws.batch_update, updates, value_input_option="RAW")
        if new_rows:
            with_backoff(ws.append_rows, [[r.get(h, "") for h in sheet_headers] for r in new_rows.values()], value_input_option="RAW")
        self._cache.pop(tab, None)
        return {"inserted": len(new_rows), "updated": len(updates)}

    def delete(self, tab, key, value):
        ws = self._ws(tab)
        values = with_backoff(ws.get_all_values)
        if not values or key not in values[0]:
            return 0
        kidx = values[0].index(key)
        targets = [n for n, r in enumerate(values[1:], start=2) if len(r) > kidx and r[kidx] == value]
        for n in sorted(targets, reverse=True):
            with_backoff(ws.delete_rows, n)
        self._cache.pop(tab, None)
        return len(targets)
