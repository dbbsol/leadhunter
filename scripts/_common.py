"""Utilitários compartilhados pelos scripts de configuração (rodam fora do Streamlit)."""
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SECRETS = ROOT / ".streamlit" / "secrets.toml"

G, R, Y, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"


def load_secrets() -> dict:
    if not SECRETS.exists():
        sys.exit(f"{R}✘ Arquivo não encontrado:{X} {SECRETS}\n  Copie .streamlit/secrets.toml.example para .streamlit/secrets.toml e preencha.")
    try:
        return tomllib.loads(SECRETS.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        sys.exit(f"{R}✘ secrets.toml com erro de sintaxe:{X} {exc}\n  Dica: a private_key precisa estar entre aspas, em uma linha, com \\n literais.")


def gspread_client(secrets: dict):
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(dict(secrets["gcp_service_account"]), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds)


def explain_google_error(exc: Exception, client_email: str) -> str:
    text = str(exc)
    low = text.lower()
    if "has not been used" in low or "accessnotconfigured" in low or "api has not been enabled" in low:
        return "A Google Sheets API não está ativada no projeto. Ative em: console.cloud.google.com → APIs e serviços → Biblioteca → Google Sheets API → Ativar."
    if "spreadsheetnotfound" in type(exc).__name__.lower() or "404" in text or "not found" in low:
        return f"Planilha não encontrada. Confira o ID e compartilhe a planilha com {client_email} como Editor."
    if "403" in text or "permission" in low:
        return f"Sem permissão. Compartilhe a planilha com {client_email} como Editor."
    if "invalid_grant" in low or "jwt" in low or "private key" in low or "pem" in low:
        return "Chave privada inválida. Recopie o JSON da conta de serviço (a private_key deve manter os \\n)."
    return text[:200]
