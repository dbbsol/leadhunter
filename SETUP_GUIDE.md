# Lead Hunter DBB — Guia de configuração completo

O código está pronto. O que falta são **contas e chaves externas** (que só você pode criar). Siga na ordem; ao final o `check_setup.py` confirma tudo.

## Checklist do que falta
| # | Item | Obrigatório | Tempo |
|---|---|---|---|
| 1 | Atualizar dependências (`Authlib` foi adicionado ao `requirements.txt`) | Sim | 1 min |
| 2 | Projeto no Google Cloud + Sheets API + conta de serviço | Sim | 10 min |
| 3 | Login Google (cliente OAuth) | Sim | 10 min |
| 4 | Planilha admin + planilha do cliente | Sim | 5 min |
| 5 | Preencher `secrets.toml` | Sim | 5 min |
| 6 | Cadastrar o cliente (`init_sheets.py`) | Sim | 1 min |
| 7 | Chave Gemini | Opcional (sem ela usa regras) | 3 min |
| 8 | GitHub + Streamlit Community Cloud | Para colocar online | 10 min |

Tudo é gratuito. Os comandos são para **PowerShell**, dentro da pasta do projeto.

---

## 1. Dependências e arquivo de segredos
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt     # agora inclui Authlib (exigido pelo login Google)
.\setup.ps1                              # cria .streamlit\secrets.toml já com cookie_secret gerado
```
O `secrets.toml` abre no VS Code. Você vai preenchê-lo nos passos seguintes. **Nunca** o envie ao GitHub (o `.gitignore` já bloqueia).

## 2. Google Cloud: projeto, Sheets API e conta de serviço
1. Acesse https://console.cloud.google.com e entre com a conta Google que será a "dona" do sistema.
2. Topo da página → seletor de projeto → **Novo projeto** → nome `lead-hunter` → Criar.
3. Menu ☰ → **APIs e serviços → Biblioteca** → procure **Google Sheets API** → **Ativar**.
4. Menu ☰ → **IAM e administrador → Contas de serviço → Criar conta de serviço**
   - Nome: `lead-hunter-sheets` → Criar e continuar → (pule papéis) → Concluir.
5. Clique na conta criada → aba **Chaves → Adicionar chave → Criar nova chave → JSON** → Criar. Um arquivo `.json` é baixado.
6. Com o terminal na pasta do projeto, rode (troque pelo caminho do seu arquivo):
   ```powershell
   python scripts\json_para_toml.py "C:\Users\SEU-USUARIO\Downloads\NOME-DO-ARQUIVO.json"
   ```
   O script cola a chave na seção `[gcp_service_account]` do `secrets.toml` sem erro de formatação.
7. Anote o `client_email` (ex.: `lead-hunter-sheets@lead-hunter-123.iam.gserviceaccount.com`). Você vai compartilhar as planilhas com ele.
8. Guarde o JSON num local seguro e **não o coloque na pasta do projeto**.

## 3. Login Google (OAuth)
1. Console → **APIs e serviços → Tela de permissão OAuth** (ou "Google Auth Platform").
   - Tipo de usuário: **Externo** → nome do app `Lead Hunter` → e-mail de suporte e de contato = o seu → Salvar.
   - Escopos: o padrão (`openid`, `email`, `profile`) basta.
   - **Usuários de teste**: enquanto o app estiver em "Teste", **adicione aqui o e-mail de cada pessoa que vai entrar** (você e o cliente). Para liberar qualquer e-mail, clique em "Publicar app" (para esses escopos básicos não exige verificação).
2. **Credenciais → Criar credenciais → ID do cliente OAuth → Aplicativo da Web**
   - Nome: `Lead Hunter Web`.
   - **URIs de redirecionamento autorizados** (adicione os dois):
     - `http://localhost:8501/oauth2callback`
     - `https://SEU-APP.streamlit.app/oauth2callback` (preencha depois do passo 8; pode voltar e editar)
   - Criar → copie **ID do cliente** e **Chave secreta do cliente**.
3. No `secrets.toml`, seção `[auth]`:
```toml
[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "(já gerado pelo setup.ps1)"
client_id = "xxxx.apps.googleusercontent.com"
client_secret = "GOCSPX-xxxx"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

## 4. Planilhas (dados)
Você precisa de **uma planilha admin** (sua) e **uma planilha por cliente**. O sistema cria as abas sozinho; as planilhas-modelo em `templates/` são opcionais.

1. https://sheets.google.com → **Planilha em branco** → renomeie para `LeadHunter_ADMIN`.
2. Clique em **Compartilhar** → cole o `client_email` da conta de serviço → papel **Editor** → desmarque "Notificar" → Enviar.
3. O **ID da planilha** é o trecho da URL entre `/d/` e `/edit`:
   `https://docs.google.com/spreadsheets/d/` **`1AbC...xyz`** `/edit`
4. Repita para o cliente: nova planilha `LeadHunter_CLIENTE_NomeDoCliente`, compartilhada **somente** com a conta de serviço (e com você, se quiser conferir). **Não deixe pública.**
5. No `secrets.toml`:
```toml
ADMIN_SHEET_ID = "ID_DA_PLANILHA_ADMIN"
ADMIN_EMAILS = ["seu-email@gmail.com"]
NOMINATIM_CONTACT = "seu-email@gmail.com"
GEOAPIFY_API_KEY = "sua-chave-da-geoapify"
```

**Como criar a chave da Geoapify (grátis, sem cartão):** acesse myprojects.geoapify.com → entre/cadastre-se → *Create a new project* → aba *API Keys* → copie a chave. O plano grátis dá 3.000 créditos por dia. Exige citar o OpenStreetMap/Geoapify como fonte (o app já mostra isso) e tem limites para uso comercial: confira os termos antes de vender o serviço. Depois rode `python -m scripts.testar_osm` para validar.

## 5. Cadastrar o cliente (assinatura)
```powershell
python init_sheets.py add --email cliente@gmail.com --nome "Maria Silva" --tenant-sheet-id ID_DA_PLANILHA_DO_CLIENTE --plano Pro --dias 30 --limite 300
```
Isso cria as abas/cabeçalhos da planilha do cliente e grava a assinatura. Cadastre também **o seu e-mail** (com uma planilha sua) para testar como cliente.

Gestão do dia a dia (sem abrir o app):
```powershell
python init_sheets.py listar
python init_sheets.py renovar   --email cliente@gmail.com --dias 30   # renova e zera o consumo
python init_sheets.py suspender --email cliente@gmail.com             # bloqueia no próximo acesso
python init_sheets.py reativar  --email cliente@gmail.com
```
Também dá para editar a aba `ASSINATURAS` direto no Google Sheets, ou no app em **Configurações → Administração**.
Formato de data: `AAAA-MM-DD` ou `DD/MM/AAAA`. Status: `ativo`, `suspenso` ou `cancelado`.

## 6. Gemini (opcional, recomendado)
1. https://aistudio.google.com → **Get API key → Create API key**.
2. `secrets.toml`:
```toml
GEMINI_API_KEY = "AIza..."
GEMINI_MODEL = "gemini-2.5-flash"
```
3. As cotas gratuitas mudam. Confira em aistudio.google.com e ajuste "Chamadas Gemini por dia" em **Configurações → Limites** (padrão 100). Sem chave, tudo funciona com análise por regras.

## 7. Verificar tudo
```powershell
python check_setup.py
```
Cada linha mostra ✔ ou ✘ com a correção. Quando terminar sem ✘:
```powershell
Remove-Item Env:LEAD_HUNTER_LOCAL_TEST -ErrorAction SilentlyContinue   # sai do modo de teste local
streamlit run app.py
```
Abra http://localhost:8501 → **Entrar com Google** → painel. Depois: Configurações → Conexão e testes → **Executar teste**.

### Roteiro de aceite (faça antes de mostrar ao cliente)
1. Entrar com o e-mail do cliente → vê o painel. ✔
2. Entrar com um e-mail **não cadastrado** → "Acesso não autorizado". ✔
3. `suspender` o cliente → "Assinatura suspensa". `reativar`. ✔
4. Descoberta: Restaurantes / Porto Alegre / RS → salvar numa campanha → conferir as linhas na aba `LEADS` da planilha do cliente.
5. Reiniciar o app (Ctrl+C, `streamlit run app.py`) → os dados continuam lá. ✔
6. Triagem → selecionar → investigar → Inteligência → Message Studio → aprovar.
7. Fechar a aba no meio de um lote e reabrir → "Processar próximo lote" retoma.

## 8. Colocar online (GitHub + Streamlit Community Cloud)
```powershell
git init
git add .
git status          # CONFIRA: secrets.toml NÃO pode aparecer
git commit -m "Lead Hunter DBB"
```
1. Crie um repositório **privado** em https://github.com/new (`lead-hunter-dbb`) e siga as instruções "push an existing repository" (`git remote add origin ...`, `git push -u origin main`).
2. https://share.streamlit.io → entre com o GitHub → **Create app** → repositório, branch `main`, arquivo `app.py`.
3. **Advanced settings → Secrets**: cole **todo** o conteúdo do `secrets.toml`, trocando `redirect_uri` por `https://SEU-APP.streamlit.app/oauth2callback`.
4. Volte ao Google Cloud (passo 3) e adicione essa URL nos redirecionamentos autorizados.
5. Deploy. Se o repositório for privado, autorize o acesso do Streamlit ao GitHub quando pedir.

---

## Problemas comuns
| Mensagem / sintoma | Causa | Solução |
|---|---|---|
| `Google Sheets API has not been used...` | API desativada | Passo 2.3 |
| `403` / `PERMISSION_DENIED` / planilha não encontrada | Planilha não compartilhada | Compartilhe com o `client_email` como Editor |
| Login: `redirect_uri_mismatch` | URL diferente da cadastrada | Passo 3.2: igualdade exata, com `/oauth2callback` |
| Login: "app não verificado / acesso bloqueado" | Seu e-mail não é usuário de teste | Passo 3.1: adicione em Usuários de teste ou publique o app |
| `ModuleNotFoundError: authlib` ou `httpx`; tela "Internal Server Error" ao clicar em Entrar com Google | Dependência do login ausente | `pip install -r requirements.txt` (ou `pip install httpx Authlib`) |
| "Acesso não autorizado" para você mesmo | Seu e-mail não está em `ASSINATURAS` | `init_sheets.py add` com o seu e-mail |
| "Conta em configuração" | `planilha_id` vazio na assinatura | Preencha a coluna `planilha_id` |
| `429` do Sheets | >60 gravações/min | O sistema repete sozinho; divida campanhas grandes |
| Busca: "A Geoapify recusou a chave" | Chave errada, com espaço ou sem aspas | Copie de novo em myprojects.geoapify.com e cole entre aspas em `GEOAPIFY_API_KEY` |
| Busca: "Limite da Geoapify atingido" | Passou dos créditos diários do plano grátis | Aguarde até o dia seguinte |
| Busca: "servidores do OpenStreetMap (Overpass) não responderam" | `GEOAPIFY_API_KEY` vazia: o app usa o Overpass público, que fica lotado | Preencha a chave da Geoapify |
| Gemini "cota atingida" | Limite gratuito | O sistema continua por regras; aguarde ou reduza o uso |
| `private_key` dá erro de PEM | Quebras de linha perdidas | Mantenha uma linha só com `\n` literais, entre aspas |

## Segurança: lembretes
- Nunca versione `secrets.toml` nem o JSON da conta de serviço. Se vazarem, revogue a chave no Google Cloud e gere outra.
- Mantenha as planilhas privadas, compartilhadas só com a conta de serviço (e com você).
- Backup: Configurações → Backup (ZIP de CSVs) e o histórico de versões do Google Sheets.
- Antes de vender: revise com seu jurídico os termos de uso e a base legal (LGPD) descritos em Configurações → LGPD.
