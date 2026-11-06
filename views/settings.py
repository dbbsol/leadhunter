"""Configurações: teste de conexão, limites, perfil, backup, LGPD e área administrativa."""
from datetime import date

import pandas as pd
import streamlit as st

from core.config import DEFAULT_LIMITS, LOCAL_TEST_MODE, get_setting, today_iso
from core.permissions import PermissionDenied, require_admin
from ui.components import page_header


def render(ctx):
    page_header("Sistema", "Configurações", "", "Conexão com o Google Sheets, limites gratuitos, backup e informações de privacidade.")
    tabs = ["CONEXÃO E TESTES", "LIMITES", "PERFIL COMERCIAL", "BACKUP", "LGPD"] + (["ADMINISTRAÇÃO"] if ctx.session.is_admin else [])
    T = st.tabs(tabs)

    with T[0]:
        st.markdown("**Teste de leitura e escrita** na planilha deste cliente.")
        if st.button("Executar teste", type="primary", icon=":material/network_check:"):
            try:
                r = ctx.store.healthcheck()
                (st.success if r["ok"] else st.error)(f"Escrita e leitura {'confirmadas' if r['ok'] else 'FALHARAM'} · {r['latencia_s']} s")
            except Exception as exc:
                st.error(f"Falha ao acessar a planilha ({type(exc).__name__}). Confirme se ela foi compartilhada com a conta de serviço como Editor.")
        st.write(f"Gemini: {'chave configurada' if get_setting('GEMINI_API_KEY') else 'sem chave — usando análise por regras'}")
        st.caption("As credenciais ficam só nos Secrets do servidor. O navegador nunca as recebe.")

    with T[1]:
        st.caption("Os planos gratuitos têm cotas variáveis: confira em aistudio.google.com e ajuste abaixo.")
        vals = {k: int(float(ctx.store.get_config(k, v))) for k, v in DEFAULT_LIMITS.items()}
        labels = {"limite_empresas_campanha": "Empresas por campanha", "limite_investigacoes_campanha": "Investigações por campanha",
                  "gemini_chamadas_dia": "Chamadas Gemini por dia", "tempo_lote_segundos": "Tempo máximo por lote (s)", "tamanho_lote": "Empresas por lote"}
        new = {k: st.number_input(labels[k], 1, 5000, v, key=f"lim_{k}") for k, v in vals.items()}
        if st.button("Salvar limites"):
            for k, v in new.items():
                ctx.store.set_config(k, v)
            st.success("Limites salvos.")

    with T[2]:
        nome = st.text_input("Seu nome", value=ctx.store.get_config("nome_profissional", ""))
        serv = st.text_area("O que você oferece (usado nas análises e mensagens)", value=ctx.store.get_config("perfil_servico", ""), height=100)
        if st.button("Salvar perfil"):
            ctx.store.set_config("nome_profissional", nome)
            ctx.store.set_config("perfil_servico", serv)
            st.success("Perfil salvo.")

    with T[3]:
        st.caption("Exporta todas as abas da sua planilha em CSV (zip). Guarde em local seguro: contém dados de empresas.")
        if st.button("Preparar backup"):
            st.session_state["backup"] = ctx.store.export_zip()
        if st.session_state.get("backup"):
            st.download_button("Baixar backup (.zip)", st.session_state["backup"], file_name=f"backup_leadhunter_{today_iso()}.zip", mime="application/zip", icon=":material/download:")
        st.caption("Recuperação: no Google Sheets use Arquivo › Histórico de versões; os CSVs servem para restaurar abas específicas.")

    with T[4]:
        st.markdown("""
**Finalidade:** prospecção comercial B2B de empresas, com dados de contato empresariais publicamente divulgados.
**Base legal (a validar com seu jurídico):** legítimo interesse (LGPD art. 7º, IX), com teste de balanceamento, transparência e opção de oposição.
**Boas práticas aplicadas:** coleta mínima · fonte e data registradas · nenhuma mensagem enviada sem aprovação humana · lista de supressão · exclusão por lead (aba Funil e CRM) · sem coleta de dados sensíveis · sem raspagem de redes sociais · respeito a robots.txt.
Dados públicos não autorizam qualquer uso comercial: identifique-se na abordagem e atenda pedidos de não contato imediatamente.""")

    if ctx.session.is_admin:
        with T[5]:
            _admin(ctx)


def _admin(ctx):
    try:
        require_admin(ctx.session.is_admin)
    except PermissionDenied:
        st.error("Acesso negado.")
        return
    st.markdown("**Assinaturas** — edite status, vencimento e limites. Mudanças valem no próximo acesso do cliente.")
    rows = ctx.admin_store.all("ASSINATURAS", fresh=True)
    cols = ["email", "nome", "plano", "inicio", "vencimento", "status", "limite_pesquisas", "consumo", "planilha_id"]
    df = pd.DataFrame(rows or [], columns=cols)
    edited = st.data_editor(df, num_rows="dynamic", width="stretch", hide_index=True,
                            column_config={"status": st.column_config.SelectboxColumn(options=["ativo", "suspenso", "cancelado"])})
    if st.button("Salvar assinaturas", type="primary"):
        clean = [r for r in edited.fillna("").to_dict("records") if str(r.get("email", "")).strip()]
        for r in clean:
            r["email"] = str(r["email"]).strip().lower()
        ctx.admin_store.upsert("ASSINATURAS", clean, key="email")
        st.success("Assinaturas salvas.")
    st.divider()
    st.markdown("**Inicializar a planilha de um cliente**")
    st.caption("Crie uma planilha vazia no Google Sheets, compartilhe com o e-mail da conta de serviço (Editor) e cole o ID aqui.")
    sid = st.text_input("ID da planilha do cliente")
    if st.button("Criar abas e cabeçalhos") and sid.strip():
        if LOCAL_TEST_MODE:
            st.info("Modo local: nada a criar.")
        else:
            try:
                from integrations.google_sheets import SheetsStore
                from integrations.storage import TENANT_SCHEMA
                from services.context import _gspread_client
                created = SheetsStore(_gspread_client(), sid.strip(), TENANT_SCHEMA).ensure_schema()
                st.success(f"Estrutura pronta. Abas criadas/preenchidas: {', '.join(created) or 'nenhuma (já existiam)'}")
            except Exception as exc:
                st.error(f"Não consegui acessar a planilha ({type(exc).__name__}). Verifique o compartilhamento.")
