# Lead Hunter DBB

Inteligência comercial e prospecção B2B assistida por IA, para social medias, agências e consultores.
Stack 100% gratuita: Python · Streamlit · Google Sheets · Gemini (nível gratuito) · OpenStreetMap via Geoapify (Overpass como reserva) · GitHub · Streamlit Community Cloud.

> **Para configurar Google, planilhas, Gemini e deploy, siga o `SETUP_GUIDE.md`** e valide com `python check_setup.py`.

## O que já funciona (as 7 etapas)
| Etapa | Entrega |
|---|---|
| 1 Fundação | Login Google (OIDC), autorização por assinatura, painel, Google Sheets com teste de leitura/escrita |
| 2 Descoberta | OpenStreetMap (Geoapify Places; Overpass como reserva sem chave), importação CSV/XLSX, normalização e deduplicação (CNPJ, domínio, telefone, fonte, nome+cidade+endereço) |
| 3 Triagem e investigação | Triagem sem IA, seleção humana, análise de site (anti-SSRF + robots.txt), evidências com fonte e data, lotes retomáveis |
| 4 Inteligência | Score 0–100 com pesos do briefing, confiança separada, SPIN Selling, oportunidades ligadas a evidências |
| 5 Message Studio | 7 tipos de texto, 4 canais, 5 estilos, copiar, aprovação humana |
| 6 CRM | 10 etapas, atividades, próxima ação, Kanban, lista de supressão, exclusão LGPD |
| 7 Testes e deploy | 47 testes automatizados, backup ZIP, este guia |

Sem chave Gemini o sistema continua funcionando: a análise SPIN e as mensagens usam regras determinísticas.

## Arquitetura
```
app.py                 roteia telas; só roda depois de require_session()
core/                  config, auth (OIDC), permissions (regras puras), security (SSRF, sanitização)
integrations/          storage.py (esquema + contrato), google_sheets.py (lote, cache, backoff)
discovery/             osm.py, importers.py, normalize.py (dedupe), cnpj.py
research/              website.py, digital_presence.py, evidence.py
ai/                    gemini.py (cota), spin_selling.py, scoring.py, message_generator.py
services/              lead_service, campaign_service, processing (lotes), metrics, context
views/                 dashboard, discovery, investigation, qualification, message_studio, crm, settings
ui/ + assets/          componentes HTML escapados, styles.css, logo.svg
tests/                 auth, permissões, segurança, scoring, dedupe, armazenamento/processamento
```
(A pasta `views/` substitui `pages/` do briefing: `pages/` ativaria o roteador automático do Streamlit e ignoraria a autenticação.)

### Isolamento entre clientes
- **Planilha admin** (você): abas `CLIENTES` e `ASSINATURAS` (e-mail, nome, plano, início, vencimento, status, limite_pesquisas, consumo, **planilha_id**).
- **Uma planilha por cliente**: `CAMPANHAS, LEADS, INVESTIGACOES, QUALIFICACAO, MENSAGENS, ATIVIDADES, SUPRESSAO, CONFIGURACOES`.
- O `planilha_id` vem **somente** da linha de assinatura validada no servidor; o navegador nunca informa IDs. `assert_same_tenant` confere antes de cada acesso.
- Login Google sozinho não libera nada: o e-mail precisa estar em `ASSINATURAS` com status `ativo`, vencimento válido e planilha vinculada.
- As credenciais da conta de serviço ficam só em `st.secrets` (servidor). O cliente nunca as vê: ele autentica com a conta Google dele; quem lê a planilha é o servidor.

## Configuração (Windows PowerShell)

### 1. Ambiente
```powershell
cd lead_hunter_ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest -q
```

### 2. Teste local imediato (sem Google, dados em memória)
```powershell
$env:LEAD_HUNTER_LOCAL_TEST="1"
streamlit run app.py
```
Aparece a faixa "MODO LOCAL DE TESTE". Nunca defina essa variável em produção.

### 3. Google Cloud (uma vez)
1. console.cloud.google.com → novo projeto → ative **Google Sheets API**.
2. **Conta de serviço**: IAM → Contas de serviço → criar → Chaves → JSON. Copie os campos para `[gcp_service_account]` em `secrets.toml`.
3. **Login de usuários**: APIs e serviços → Tela de consentimento OAuth (Externo, modo teste ou produção) → Credenciais → ID do cliente OAuth (Aplicativo da Web). URIs de redirecionamento: `http://localhost:8501/oauth2callback` e `https://SEU-APP.streamlit.app/oauth2callback`.
4. Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha (`[auth]`, `ADMIN_SHEET_ID`, `ADMIN_EMAILS`, `GEMINI_API_KEY`, `NOMINATIM_CONTACT`, `GEOAPIFY_API_KEY`). Gere o `cookie_secret` com: `python -c "import secrets;print(secrets.token_urlsafe(32))"`.

### 4. Planilhas
1. Crie a **planilha admin** vazia, compartilhe com o `client_email` da conta de serviço (Editor), coloque o ID em `ADMIN_SHEET_ID`. As abas são criadas no primeiro acesso.
2. Em `ASSINATURAS`, adicione seu cliente (e o seu e-mail para testar): `email, nome, plano, inicio, vencimento (AAAA-MM-DD), status=ativo, limite_pesquisas, consumo=0, planilha_id`.
3. Crie uma planilha para cada cliente, compartilhe com a conta de serviço e cole o ID em `planilha_id`. No app: Configurações → Administração → "Criar abas e cabeçalhos".
4. Configurações → Conexão e testes → **Executar teste** (grava e lê de volta).

### 5. Gemini (opcional)
Crie a chave em aistudio.google.com e coloque em `GEMINI_API_KEY`. O limite diário é configurável em Configurações → Limites (confira a cota gratuita vigente do modelo).

### 6. Deploy no Streamlit Community Cloud
Repositório GitHub (o `.gitignore` já exclui `secrets.toml`) → share.streamlit.io → New app → `app.py` → Advanced settings → cole o conteúdo do `secrets.toml` em Secrets. Ajuste o `redirect_uri` para a URL final.

## Segurança já implementada
- SSRF: só http/https, portas 80/443, todos os IPs resolvidos precisam ser públicos (bloqueia loopback, redes privadas, link-local/metadata, CGNAT), redirecionamentos revalidados, limite de 600 KB, só HTML/texto, respeita robots.txt.
- Conteúdo de sites vai à IA como dado delimitado (`<dados>`), sem telefone/e-mail, com instrução de ignorar comandos embutidos (defesa em profundidade contra prompt injection).
- Todo HTML de interface escapa dados vindos de fontes externas. Planilha gravada em modo RAW (sem execução de fórmulas).
- Chaves só em Secrets; chave Gemini enviada por cabeçalho, nunca na URL.

## Limitações honestas
- **Não testado contra serviços reais neste ambiente**: login Google, Google Sheets, Gemini, Nominatim, Geoapify/Overpass e BrasilAPI dependem das suas credenciais e rede. Foram testados: toda a lógica (47 testes), o parser/construtor de consultas OSM e a busca via Geoapify com respostas simuladas (14 testes em `tests/test_geoapify.py`) e as telas em modo local. Faça o roteiro da seção 4 antes de apresentar ao cliente.
- Dados da Receita: os arquivos abertos têm vários GB; o MVP aceita CNPJ em listas importadas e, se houver CNPJ, consulta a BrasilAPI (serviço comunitário, pode limitar). Se falhar, segue sem.
- OpenStreetMap tem cobertura irregular de telefone/site; é ponto de partida, não cadastro completo.
- Geoapify: plano grátis com 3.000 créditos/dia e exigência de atribuição; confira os termos para uso comercial. Sem `GEOAPIFY_API_KEY` o app cai no Overpass público, que costuma ficar lotado.
- Instagram/redes: o sistema só registra links públicos informados na fonte ou no site. Não há raspagem.
- Streamlit processa lotes de forma síncrona: se a aba fechar no meio, o progresso do último lote salvo permanece e "Processar" retoma de onde parou.
- Google Sheets limita ~60 gravações/min por usuário; o sistema grava em lote e usa backoff, mas campanhas muito grandes devem ser divididas.
- Atualizações simultâneas na mesma linha: vence a última gravação.
