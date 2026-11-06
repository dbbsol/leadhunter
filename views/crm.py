"""CRM: tabela, Kanban, atividades e lista de supressão."""
from datetime import date

import pandas as pd
import streamlit as st

from core.permissions import parse_date
from services.lead_service import STAGES
from ui.components import empty_state, html_block, kanban_html, page_header, pill
from views._common import campaign_picker, select_lead

PRIOS = ["Alta prioridade", "Média prioridade", "Baixa prioridade", "Baixa aderência"]


def _filters(ctx, leads):
    c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1.4])
    camps = {c["id"]: c["nome"] for c in ctx.campaigns.list()}
    camp = c1.selectbox("Campanha", ["__all__"] + list(camps), format_func=lambda i: "Todas" if i == "__all__" else camps[i])
    prio = c2.multiselect("Prioridade", PRIOS)
    stage = c3.multiselect("Etapa", STAGES)
    q = c4.text_input("Buscar", placeholder="Nome ou cidade")
    from discovery.normalize import norm_text
    return [l for l in leads if (camp == "__all__" or l.get("campanha_id") == camp) and (not prio or l.get("classificacao") in prio)
            and (not stage or l.get("etapa") in stage) and (not q or norm_text(q) in norm_text(f"{l['nome']} {l.get('cidade')}"))]


def _detail(ctx, lead):
    st.markdown(f"### {lead['nome']}")
    c1, c2 = st.columns(2)
    nova = c1.selectbox("Etapa", STAGES, index=STAGES.index(lead.get("etapa", "Encontrado")) if lead.get("etapa") in STAGES else 0, key=f"st_{lead['id']}")
    prox = c2.text_input("Próxima ação", value=lead.get("proxima_acao", ""), key=f"pa_{lead['id']}")
    d0 = parse_date(lead.get("proxima_acao_data"))
    data = c1.date_input("Data da próxima ação", value=d0, key=f"pd_{lead['id']}", format="DD/MM/YYYY")
    obs = c2.text_area("Observações", value=lead.get("observacoes", ""), key=f"ob_{lead['id']}", height=100)
    if st.button("Salvar alterações", type="primary", key=f"sv_{lead['id']}"):
        ctx.leads.update(lead["id"], proxima_acao=prox, proxima_acao_data=data.isoformat() if data else "", observacoes=obs)
        if nova != lead.get("etapa"):
            ctx.leads.set_stage(lead, nova)
        st.success("Salvo.")
        st.rerun()
    with st.expander("Registrar atividade"):
        t = st.selectbox("Tipo", ["contato", "ligação", "reunião", "nota"], key=f"ty_{lead['id']}")
        d = st.text_input("Descrição", key=f"de_{lead['id']}")
        if st.button("Registrar", key=f"rg_{lead['id']}") and d.strip():
            ctx.leads.log(lead["id"], t, d.strip())
            if t == "contato" and lead.get("etapa") in ("Abordagem preparada", "Qualificado", "Investigado"):
                ctx.leads.set_stage(lead, "Contato realizado")
            st.rerun()
    st.markdown("**Histórico**")
    hist = ctx.leads.activities(lead["id"])
    if hist:
        for a in hist[:15]:
            html_block(f'<div class="row"><div><div class="t">{a["descricao"][:120]}</div><div class="s">{a["data"][:16].replace("T"," ")} · {a["tipo"]}</div></div></div>')
    else:
        st.caption("Sem atividades registradas.")
    with st.expander("Excluir dados deste lead (LGPD)"):
        st.caption("Remove o lead, investigações, mensagens e atividades. Não adiciona à lista de supressão.")
        if st.checkbox("Confirmo a exclusão definitiva", key=f"cf_{lead['id']}") and st.button("Excluir lead", key=f"dl_{lead['id']}"):
            ctx.leads.delete_lead(lead["id"])
            st.rerun()


def render(ctx):
    page_header("Comercial", "Funil e", "CRM.", "Acompanhe cada lead da descoberta até a conversão. Quem pede para não ser contatado entra na lista de supressão.")
    leads = ctx.leads.list()
    if not leads:
        empty_state("◌", "Funil vazio", "Salve empresas em Descoberta para acompanhá-las aqui.")
    t1, t2, t3, t4 = st.tabs(["TABELA", "KANBAN", "ATIVIDADES", "LISTA DE SUPRESSÃO"])
    with t1:
        if leads:
            view = _filters(ctx, leads)
            df = pd.DataFrame([{"Empresa": l["nome"], "Etapa": l.get("etapa", ""), "Prioridade": l.get("classificacao") or l.get("triagem", ""), "Score": l.get("score", ""),
                                "Próxima ação": l.get("proxima_acao", ""), "Data": l.get("proxima_acao_data", ""), "Cidade": l.get("cidade", "")} for l in view])
            ev = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row")
            st.caption(f"{len(view)} lead(s). Selecione uma linha para editar.")
            rows = ev.selection.rows if ev and ev.selection else []
            if rows:
                lead = view[rows[0]]
                select_lead(lead["id"])
                _detail(ctx, lead)
    with t2:
        if leads:
            cols = {s: [l for l in leads if l.get("etapa") == s] for s in STAGES}
            html_block(kanban_html(cols))
            st.caption("Para mover um lead entre colunas, selecione-o na aba Tabela e altere a etapa.")
    with t3:
        acts = sorted(ctx.store.all("ATIVIDADES"), key=lambda a: a.get("data", ""), reverse=True)[:40]
        names = {l["id"]: l["nome"] for l in leads}
        if acts:
            for a in acts:
                html_block(f'<div class="row"><div><div class="t">{names.get(a["lead_id"], "Lead removido")}</div><div class="s">{a["descricao"][:140]}</div></div><div>{pill(a["tipo"])} <span class="muted" style="font-size:.8rem">{a["data"][:10]}</span></div></div>')
        else:
            empty_state("◌", "Sem atividades", "Registre contatos e notas na aba Tabela.")
    with t4:
        supp = ctx.store.all("SUPRESSAO")
        c1, c2, c3 = st.columns([1, 2, 2])
        tipo = c1.selectbox("Tipo", ["telefone", "email", "dominio", "cnpj", "nome"])
        valor = c2.text_input("Valor")
        motivo = c3.text_input("Motivo", placeholder="Ex.: pediu para não receber contato")
        if st.button("Adicionar à supressão", type="primary") and valor.strip():
            from discovery.normalize import norm_name, norm_phone
            v = norm_phone(valor) if tipo == "telefone" else norm_name(valor) if tipo == "nome" else valor
            ctx.leads.add_suppression(tipo, v or valor, motivo)
            st.rerun()
        if supp:
            st.dataframe(pd.DataFrame(supp)[["tipo", "valor", "motivo", "data"]], hide_index=True, width="stretch")
            rem = st.selectbox("Remover da lista", [""] + [f"{s['tipo']}:{s['valor']}" for s in supp])
            if rem and st.button("Remover"):
                sid = next(s["id"] for s in supp if f"{s['tipo']}:{s['valor']}" == rem)
                ctx.store.delete("SUPRESSAO", "id", sid)
                st.rerun()
        else:
            empty_state("☑", "Lista vazia", "Contatos adicionados aqui nunca mais serão prospectados.")
