"""Diagnóstico completo da configuração. Uso:  python check_setup.py
Verifica cada integração e diz exatamente o que corrigir."""
import sys
from datetime import date

import requests

from scripts._common import B, G, R, X, Y, explain_google_error, gspread_client, load_secrets

fails = warns = 0


def ok(msg, hint=""):
    print(f"{G}✔{X} {msg}")


def bad(msg, hint=""):
    global fails
    fails += 1
    print(f"{R}✘ {msg}{X}" + (f"\n    → {hint}" if hint else ""))


def warn(msg, hint=""):
    global warns
    warns += 1
    print(f"{Y}! {msg}{X}" + (f"\n    → {hint}" if hint else ""))


def section(t):
    print(f"\n{B}{t}{X}")


s = load_secrets()
ok("secrets.toml encontrado e legível")

# ---------- 1. Login Google ----------
section("1. Login Google (OIDC)")
auth = s.get("auth", {})
for k in ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url"):
    if not auth.get(k):
        bad(f"[auth] {k} ausente", "Veja SETUP_GUIDE.md, passo 3")
if "xxxx" in str(auth.get("client_id", "")).lower() or "xxxx" in str(auth.get("client_secret", "")).lower():
    bad("client_id / client_secret ainda são os valores de exemplo (xxxx)", "Crie o cliente OAuth no Google Cloud e cole os valores reais (SETUP_GUIDE.md, passo 3)")
elif auth.get("client_id") and not str(auth["client_id"]).endswith(".apps.googleusercontent.com"):
    bad("client_id não parece um ID de cliente OAuth do Google", "Deve terminar com .apps.googleusercontent.com")
if auth.get("cookie_secret") and (len(str(auth["cookie_secret"])) < 24 or "TROQUE" in str(auth["cookie_secret"])):
    bad("cookie_secret fraco ou ainda é o valor de exemplo", 'Gere: python -c "import secrets;print(secrets.token_urlsafe(32))"')
if auth.get("redirect_uri"):
    ru = str(auth["redirect_uri"])
    (ok if ru.endswith("/oauth2callback") else bad)(f"redirect_uri = {ru}", "" if ru.endswith("/oauth2callback") else "Deve terminar em /oauth2callback")
    if ru.startswith("http://") and "localhost" not in ru:
        bad("redirect_uri usa http fora do localhost", "Em produção use https://")
try:
    import authlib  # noqa: F401
    import httpx  # noqa: F401  (o st.login do Streamlit exige)
    ok("Authlib e httpx instalados (exigidos pelo st.login)")
except ImportError as exc:
    bad(f"Dependência do login ausente: {exc.name}", "pip install -r requirements.txt")
if auth.get("server_metadata_url"):
    try:
        r = requests.get(auth["server_metadata_url"], timeout=10)
        (ok if r.status_code == 200 else bad)(f"server_metadata_url responde {r.status_code}")
    except Exception as exc:
        bad(f"Não consegui acessar o Google OIDC ({type(exc).__name__})", "Verifique sua internet")

# ---------- 2. Conta de serviço ----------
section("2. Conta de serviço (acesso às planilhas)")
sa = s.get("gcp_service_account", {})
client_email = sa.get("client_email", "(client_email ausente)")
missing = [k for k in ("type", "project_id", "private_key", "client_email", "token_uri") if not sa.get(k)]
gc = None
if missing:
    bad(f"[gcp_service_account] faltando: {', '.join(missing)}", "Cole o conteúdo do JSON baixado no Google Cloud")
else:
    try:
        gc = gspread_client(s)
        ok(f"Credenciais carregadas — e-mail da conta de serviço: {B}{client_email}{X}")
        print("    (compartilhe cada planilha com esse e-mail como Editor)")
    except Exception as exc:
        bad("Chave da conta de serviço inválida", explain_google_error(exc, client_email))

# ---------- 3. Planilhas ----------
section("3. Planilhas Google")
admin_id = s.get("ADMIN_SHEET_ID")
admins = s.get("ADMIN_EMAILS") or []
(ok if admins else bad)(f"ADMIN_EMAILS = {admins}" if admins else "ADMIN_EMAILS vazio", "" if admins else "Coloque seu e-mail do Google")
rows = []
if not admin_id:
    bad("ADMIN_SHEET_ID ausente", "Crie a planilha admin e cole o ID (SETUP_GUIDE.md, passo 4)")
elif gc:
    try:
        from integrations.google_sheets import SheetsStore
        from integrations.storage import ADMIN_SCHEMA, TENANT_SCHEMA

        admin = SheetsStore(gc, admin_id, ADMIN_SCHEMA)
        created = admin.ensure_schema()
        ok("Planilha admin aberta" + (f" — abas criadas: {', '.join(created)}" if created else " — abas OK"))
        admin.append("CLIENTES", [{"email": "_ping", "nome": "teste"}])
        admin.delete("CLIENTES", "email", "_ping")
        ok("Escrita e leitura na planilha admin confirmadas")
        rows = admin.all("ASSINATURAS", fresh=True)
        if not rows:
            warn("ASSINATURAS está vazia", "Cadastre o cliente: python init_sheets.py add --email ... (SETUP_GUIDE.md, passo 5)")
        for r in rows:
            nome = r.get("email", "?")
            from core.permissions import check_subscription, parse_date
            good, why = check_subscription(r, date.today())
            if not good:
                warn(f"Assinatura de {nome} não libera acesso (motivo: {why})", "Ajuste status/vencimento/planilha_id")
                continue
            try:
                t = SheetsStore(gc, r["planilha_id"].strip(), TENANT_SCHEMA)
                t.ensure_schema()
                h = t.healthcheck()
                (ok if h["ok"] else bad)(f"Planilha do cliente {nome}: escrita/leitura {'OK' if h['ok'] else 'FALHOU'} ({h['latencia_s']}s)")
            except Exception as exc:
                bad(f"Planilha do cliente {nome} inacessível", explain_google_error(exc, client_email))
    except Exception as exc:
        bad("Falha ao acessar a planilha admin", explain_google_error(exc, client_email))

# ---------- 4. Gemini ----------
section("4. Gemini (opcional)")
key = s.get("GEMINI_API_KEY")
model = s.get("GEMINI_MODEL", "gemini-2.5-flash")
if not key:
    warn("GEMINI_API_KEY não configurada", "O sistema funciona com análise por regras. Para IA: aistudio.google.com → Get API key")
else:
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          headers={"x-goog-api-key": key}, timeout=30,
                          json={"contents": [{"parts": [{"text": "Responda apenas: ok"}]}], "generationConfig": {"maxOutputTokens": 20}})
        if r.status_code == 200:
            ok(f"Gemini respondeu (modelo {model})")
        elif r.status_code == 429:
            warn("Gemini: cota atingida (a chave é válida)", "Aguarde ou reduza o limite diário em Configurações")
        elif r.status_code == 404:
            bad(f"Modelo '{model}' não existe", "Veja os modelos disponíveis em aistudio.google.com e ajuste GEMINI_MODEL")
        elif r.status_code in (400, 401, 403):
            bad(f"Chave Gemini recusada (HTTP {r.status_code})", "Gere uma nova chave em aistudio.google.com")
        else:
            bad(f"Gemini retornou HTTP {r.status_code}")
    except Exception as exc:
        bad(f"Sem acesso ao Gemini ({type(exc).__name__})")

# ---------- 5. OpenStreetMap ----------
section("5. OpenStreetMap")
contact = s.get("NOMINATIM_CONTACT", "")
(ok if contact and "@" in contact else warn)(f"NOMINATIM_CONTACT = {contact or 'vazio'}", "" if contact else "Informe seu e-mail (política de uso do Nominatim)")
HEADERS = {"User-Agent": f"LeadHunterDBB/1.0 ({contact or 'sem-contato'})", "Accept": "*/*"}
if not contact or "@" not in contact:
    bad("Nominatim não testado: NOMINATIM_CONTACT vazio", "Preencha seu e-mail no secrets.toml; sem ele o OpenStreetMap devolve 403")
else:
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", params={"city": "Porto Alegre", "state": "RS", "country": "Brasil", "format": "json", "limit": 1},
                         headers=HEADERS, timeout=15)
        (ok if r.status_code == 200 and r.json() else bad)(f"Nominatim geocodificou Porto Alegre (HTTP {r.status_code})")
    except Exception as exc:
        bad(f"Nominatim inacessível ({type(exc).__name__})")
gkey = str(s.get("GEOAPIFY_API_KEY", "")).strip()
if not gkey or any(p in gkey.upper() for p in ("COLE", "SUA_CHAVE", "XXXX", "SEU_", "CHAVE_AQUI")):
    warn("GEOAPIFY_API_KEY vazia", "Sem ela a busca usa o Overpass público, que costuma ficar lotado. Crie a chave grátis em myprojects.geoapify.com")
else:
    try:
        r = requests.get("https://api.geoapify.com/v1/geocode/search", params={"text": "Porto Alegre, RS, Brasil", "type": "city", "limit": 1, "apiKey": gkey}, timeout=15)
        if r.status_code == 200:
            ok("Geoapify: chave válida")
        elif r.status_code in (401, 403):
            bad(f"Chave Geoapify recusada (HTTP {r.status_code})", "Copie a chave de novo em myprojects.geoapify.com → seu projeto → API Keys")
        elif r.status_code == 429:
            warn("Geoapify: limite diário atingido (a chave é válida)", "Volte amanhã")
        else:
            warn(f"Geoapify respondeu HTTP {r.status_code}")
    except Exception as exc:
        bad(f"Geoapify inacessível ({type(exc).__name__})")
try:
    r = requests.get("https://overpass-api.de/api/status", headers=HEADERS, timeout=15)
    (ok if r.status_code == 200 else warn)(f"Overpass respondeu HTTP {r.status_code}")
except Exception as exc:
    warn(f"Overpass inacessível ({type(exc).__name__})", "Só importa se você não usar a Geoapify")

# ---------- 6. BrasilAPI ----------
section("6. Consulta de CNPJ (opcional)")
try:
    r = requests.get("https://brasilapi.com.br/api/cnpj/v1/00000000000191", timeout=10)
    (ok if r.status_code == 200 else warn)(f"BrasilAPI HTTP {r.status_code}" + (" (limite de uso do serviço gratuito; tente mais tarde)" if r.status_code == 429 else ""))
except Exception:
    warn("BrasilAPI inacessível", "Opcional: o sistema segue sem ela")

print(f"\n{B}Resumo:{X} {R}{fails} erro(s){X}, {Y}{warns} aviso(s){X}")
print(f"{G}Tudo pronto! Rode: streamlit run app.py{X}" if not fails else f"{R}Corrija os itens com ✘ e rode de novo: python check_setup.py{X}")
sys.exit(1 if fails else 0)
