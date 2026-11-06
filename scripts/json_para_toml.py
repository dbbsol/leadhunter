"""Cola a chave da conta de serviço (JSON do Google) dentro de .streamlit/secrets.toml.

Uso:  python scripts/json_para_toml.py "C:\\Users\\Dell\\Downloads\\crm-nutri-504315-xxxx.json"
Faz backup do secrets.toml antes e substitui só a seção [gcp_service_account].
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / ".streamlit" / "secrets.toml"
EXAMPLE = ROOT / ".streamlit" / "secrets.toml.example"

if len(sys.argv) != 2:
    sys.exit(__doc__)
src = Path(sys.argv[1].strip('"'))
if not src.exists():
    sys.exit(f"Arquivo não encontrado: {src}")
data = json.loads(src.read_text(encoding="utf-8"))
if data.get("type") != "service_account":
    sys.exit("Esse JSON não é de uma conta de serviço (esperado type = service_account).")

if not SECRETS.exists():
    shutil.copy(EXAMPLE, SECRETS)
    print("secrets.toml não existia: criado a partir do exemplo.")
else:
    shutil.copy(SECRETS, SECRETS.with_suffix(".toml.bak"))

text = SECRETS.read_text(encoding="utf-8-sig")
text = re.sub(r"\n?\[gcp_service_account\].*?(?=\n\[|\Z)", "", text, flags=re.S).rstrip() + "\n"
block = "\n[gcp_service_account]\n" + "".join(
    f"{k} = {json.dumps(data[k])}\n" for k in ("type", "project_id", "private_key_id", "private_key", "client_email", "client_id", "token_uri")
)
SECRETS.write_text(text + block, encoding="utf-8", newline="\n")
print("✔ Chave colada em .streamlit/secrets.toml")
print("  E-mail da conta de serviço (compartilhe as planilhas com ele):", data["client_email"])
print("  Agora mova o .json para fora de Downloads (ex.: Documentos\\chaves).")
