"""Message Studio: abordagens SPIN personalizadas, sempre com aprovação humana."""
import streamlit as st

from ai.message_generator import CANAIS, ESTILOS, check_safety, generate
from core.config import jdump, jload, new_id, now_iso
from ui.components import empty_state, page_header
from views._common import current_lead_id, lead_label, select_lead


def _block(label: str, key: str, text: str):
    st.markdown(f'<p class="lbl">{label}</p>', unsafe_allow_html=True)
    st.session_state.setdefault(key, text)
    st.code(st.session_state[key], language=None, wrap_lines=True)  # botão de copiar nativo
    with st.expander("Editar"):
        st.text_area(label, key=key, label_visibility="collapsed", height=130)


def render(ctx):
    page_header("Comercial", "Message", "Studio.", "Mensagens consultivas baseadas em evidências reais. Nada é enviado automaticamente: você revisa, aprova e copia.")
    leads = [l for l in ctx.leads.list() if l.get("score")]
    if not leads:
        empty_state("✎", "Sem leads analisados", "Investigue empresas primeiro: as mensagens usam as evidências encontradas.")
        return
    ids = [l["id"] for l in leads]
    cur = current_lead_id() if current_lead_id() in ids else ids[0]
    lid = st.selectbox("Lead", ids, index=ids.index(cur), format_func=lambda i: lead_label(next(l for l in leads if l["id"] == i)))
    select_lead(lid)
    lead = next(l for l in leads if l["id"] == lid)
    if lead.get("etapa") == "Não contatar" or ctx.leads.is_suppressed(lead):
        st.error("Este lead está na lista de supressão / Não contatar. Não prepare novas abordagens.")
        return
    inv = next((i for i in ctx.store.all("INVESTIGACOES") if i["lead_id"] == lid), None)
    if not inv:
        st.warning("Sem investigação para este lead.")
        return
    evid, an = jload(inv["evidencias"], []), jload(inv["analise"], {})

    c1, c2, c3 = st.columns(3)
    canal = c1.selectbox("Canal", CANAIS)
    estilo = c2.selectbox("Estilo", ESTILOS)
    nome_user = c3.text_input("Seu nome", value=ctx.store.get_config("nome_profissional", ""))
    servico = st.text_input("O que você oferece", value=ctx.store.get_config("perfil_servico", ""), placeholder="Ex.: gestão de redes sociais e tráfego pago para restaurantes")
    objetivo = st.text_input("Objetivo comercial", placeholder="Ex.: agendar um diagnóstico gratuito de 15 minutos")

    saved = [m for m in ctx.store.all("MENSAGENS") if m["lead_id"] == lid]
    if st.button("Gerar abordagem", type="primary", icon=":material/auto_awesome:"):
        with st.spinner("Preparando mensagens…"):
            g = ctx.gemini()
            content, origem = generate(lead, an, evid, canal, estilo, objetivo, nome_user, servico, g)
            if g:
                g.flush()
        for k in list(st.session_state):
            if k.startswith("msg_"):
                del st.session_state[k]
        st.session_state["msg_draft"] = {"content": content, "origem": origem, "canal": canal, "estilo": estilo, "objetivo": objetivo, "lead": lid}
        ctx.store.set_config("nome_profissional", nome_user)
        ctx.store.set_config("perfil_servico", servico)

    draft = st.session_state.get("msg_draft")
    if not draft or draft["lead"] != lid:
        if saved:
            st.caption(f"{len(saved)} abordagem(ns) já salva(s) para este lead. Gere uma nova para editar.")
        else:
            empty_state("✎", "Nenhuma abordagem ainda", "Escolha canal e estilo e clique em Gerar abordagem.")
        return

    c = draft["content"]
    st.caption(f"Origem: {draft['origem']} · Revise tudo antes de enviar.")
    if draft["canal"] == "E-mail":
        _block("Assunto", "msg_assunto", c.get("assunto", ""))
    _block("1 · Primeira abordagem", "msg_primeira", c["primeira_abordagem"])
    _block("2 · Pergunta de abertura", "msg_abertura", c["pergunta_abertura"])
    _block("3 · Mensagem consultiva", "msg_consultiva", c["mensagem_consultiva"])
    _block("4 · Perguntas SPIN (use 1 ou 2 por vez)", "msg_spin", "\n".join(f"• {q}" for q in c["perguntas_spin"]))
    _block("5 · Sugestão de diagnóstico", "msg_diag", c["sugestao_diagnostico"])
    _block("6 · Follow-up", "msg_follow", c["followup"])
    st.markdown('<p class="lbl">7 · Respostas para objeções</p>', unsafe_allow_html=True)
    for o in c["objecoes"]:
        with st.expander(o.get("objecao", "")):
            st.code(o.get("resposta", ""), language=None, wrap_lines=True)

    final_text = " ".join(st.session_state.get(k, "") for k in ("msg_primeira", "msg_consultiva", "msg_follow"))
    for f in check_safety(final_text):
        st.warning("Atenção: " + f)
    ok = st.checkbox("Revisei o conteúdo e aprovo esta abordagem para uso manual")
    if st.button("Salvar abordagem aprovada", type="primary", disabled=not ok):
        c2 = dict(c)
        c2.update({"primeira_abordagem": st.session_state["msg_primeira"], "pergunta_abertura": st.session_state["msg_abertura"],
                   "mensagem_consultiva": st.session_state["msg_consultiva"], "sugestao_diagnostico": st.session_state["msg_diag"], "followup": st.session_state["msg_follow"]})
        ctx.store.append("MENSAGENS", [{"id": new_id("ms"), "lead_id": lid, "canal": draft["canal"], "estilo": draft["estilo"], "objetivo": draft["objetivo"],
                                        "conteudo": jdump(c2), "status": "aprovada", "criado_em": now_iso()}])
        if lead.get("etapa") in ("Encontrado", "Selecionado", "Investigado", "Qualificado"):
            ctx.leads.set_stage(lead, "Abordagem preparada")
        ctx.leads.log(lid, "mensagem", f"Abordagem aprovada ({draft['canal']}, {draft['estilo']})")
        st.success("Abordagem salva e lead movido para 'Abordagem preparada'. Copie e envie manualmente.")
