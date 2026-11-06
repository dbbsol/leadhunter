"""Cliente Gemini (REST, nível gratuito) com controle de cota diária, limite de entrada e erros claros."""
from __future__ import annotations

import json
import re

import requests

from core.config import DEFAULT_LIMITS, get_setting, today_iso

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_INPUT_CHARS = 6000


class GeminiError(Exception):
    pass


class QuotaExceeded(GeminiError):
    pass


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class GeminiClient:
    def __init__(self, api_key: str, model: str, store, daily_limit: int | None = None):
        self.api_key = api_key
        self.model = model
        self.store = store
        self.daily_limit = int(daily_limit or store.get_config("gemini_chamadas_dia", DEFAULT_LIMITS["gemini_chamadas_dia"]))
        self._key = f"gemini_calls_{today_iso()}"
        self.calls_today = int(float(store.get_config(self._key, 0) or 0))
        self._dirty = False

    @classmethod
    def from_settings(cls, store):
        key = get_setting("GEMINI_API_KEY")
        if not key:
            return None
        return cls(str(key), str(get_setting("GEMINI_MODEL", "gemini-2.5-flash")), store)

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.calls_today)

    def flush(self):
        if self._dirty:
            self.store.set_config(self._key, self.calls_today)
            self._dirty = False

    def generate_json(self, system: str, user: str, max_output_tokens: int = 1800) -> dict:
        if self.remaining <= 0:
            raise QuotaExceeded(f"Limite diário configurado de {self.daily_limit} chamadas Gemini atingido.")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user[:MAX_INPUT_CHARS]}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4, "maxOutputTokens": max_output_tokens},
        }
        try:
            r = requests.post(ENDPOINT.format(model=self.model), json=body, timeout=60,
                              headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
        except requests.RequestException as exc:
            raise GeminiError("Não foi possível falar com o Gemini agora (rede).") from exc
        self.calls_today += 1
        self._dirty = True
        if r.status_code == 429:
            raise QuotaExceeded("A cota gratuita do Gemini foi atingida. Tente mais tarde; o sistema usa análise por regras enquanto isso.")
        if r.status_code in (401, 403):
            raise GeminiError("Chave do Gemini inválida ou sem permissão. Verifique GEMINI_API_KEY nos Secrets.")
        if r.status_code != 200:
            raise GeminiError(f"O Gemini respondeu com erro {r.status_code}.")
        try:
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            return json.loads(text)
        except Exception as exc:
            raise GeminiError("O Gemini devolveu uma resposta fora do formato esperado.") from exc
