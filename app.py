"""Lead Hunter DBB — ponto de entrada. Autentica, autoriza e roteia as telas."""
import streamlit as st

from core.config import APP_NAME, LOCAL_TEST_MODE, now
from ui.components import ASSETS, inject_css

st.set_page_config(page_title=f"{APP_NAME} · DBB", page_icon=":material/radar:", layout="wide", initial_sidebar_state="expanded")
inject_css()

from core.auth import require_session  # noqa: E402  (importa depois do CSS para a tela de login já estar estilizada)
from services.context import build_ctx  # noqa: E402
from views import crm, dashboard, discovery, investigation, message_studio, qualification, settings  # noqa: E402

session = require_session()
ctx = build_ctx(session)

if LOCAL_TEST_MODE:
    st.markdown('<div class="demo">MODO LOCAL DE TESTE — dados em memória, sem login Google. Não use em produção.</div>', unsafe_allow_html=True)


def p_dashboard(): dashboard.render(ctx)
def p_discovery(): discovery.render(ctx)
def p_investigation(): investigation.render(ctx)
def p_qualification(): qualification.render(ctx)
def p_messages(): message_studio.render(ctx)
def p_crm(): crm.render(ctx)
def p_settings(): settings.render(ctx)


pages = {
    "Comando": [st.Page(p_dashboard, title="Painel", icon=":material/dashboard:", url_path="painel", default=True)],
    "Prospecção": [
        st.Page(p_discovery, title="Descoberta", icon=":material/travel_explore:", url_path="descoberta"),
        st.Page(p_investigation, title="Triagem e investigação", icon=":material/manage_search:", url_path="investigacao"),
        st.Page(p_qualification, title="Inteligência", icon=":material/query_stats:", url_path="inteligencia"),
    ],
    "Comercial": [
        st.Page(p_messages, title="Message Studio", icon=":material/forum:", url_path="mensagens"),
        st.Page(p_crm, title="Funil e CRM", icon=":material/view_kanban:", url_path="crm"),
    ],
    "Sistema": [st.Page(p_settings, title="Configurações", icon=":material/settings:", url_path="configuracoes")],
}
st.logo(str(ASSETS / "logo.svg"), size="large")
nav = st.navigation(pages, position="sidebar")

with st.sidebar:
    stamp = now().strftime("%d/%m/%Y %H:%M")
    st.markdown(f'<div class="sb-foot"><span class="dot"></span>Salvo no Google Sheets<br>{session.email}<br>{session.plano or "Plano"} · vence {session.vencimento}</div>', unsafe_allow_html=True)
    if not LOCAL_TEST_MODE:
        st.button("Sair", on_click=st.logout, width="stretch", icon=":material/logout:")

nav.run()
