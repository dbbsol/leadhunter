"""Painel: indicadores reais, evolução, melhores oportunidades e saúde do funil."""
import altair as alt
import pandas as pd
import streamlit as st

from core.config import now
from services.metrics import compute
from ui.components import card_html, eyebrow_date, empty_state, greeting, html_block, kpi, page_header, pill, prio_tone, ring, rows_html, esc
from views.discovery import new_lead_dialog


def render(ctx):
    leads, quals = ctx.leads.list(), ctx.store.all("QUALIFICACAO")
    invs, msgs = ctx.store.all("INVESTIGACOES"), ctx.store.all("MENSAGENS")
    camps, acts = ctx.campaigns.list(), ctx.store.all("ATIVIDADES")
    t = now()
    m = compute(leads, quals, invs, msgs, camps, acts, t.date())

    first = (ctx.session.name or "").split(" ")[0] or "olá"
    if m["total"]:
        sub = (f"Você tem <b>{len(m['overdue'])} tarefa(s) atrasada(s)</b> e {len(m['due_today'])} para hoje. "
               f"{len(m['pipeline'])} lead(s) ativos no funil e {m['qualificados']} qualificado(s).")
    else:
        sub = "Ainda não há leads. Comece buscando empresas em <b>Descoberta</b> ou importe uma lista."
    page_header(eyebrow_date(t), f"{greeting(t)},", first + ".", sub)

    c1, _ = st.columns([1, 5])
    with c1:
        if st.button("Novo lead", type="primary", icon=":material/add:", width="stretch"):
            new_lead_dialog(ctx)

    q = st.text_input("Buscar leads", placeholder="Buscar leads por nome, cidade, segmento…", label_visibility="collapsed")
    if q:
        from discovery.normalize import norm_text
        nq = norm_text(q)
        hits = [l for l in leads if nq in norm_text(f"{l.get('nome')} {l.get('cidade')} {l.get('segmento')}")][:8]
        if hits:
            html_block(card_html(f"{len(hits)} resultado(s)", rows_html([(l["nome"], f"{l.get('segmento','')} · {l.get('cidade','')}", pill(l.get("etapa", ""))) for l in hits])))
        else:
            st.caption("Nenhum lead encontrado para essa busca.")

    st.write("")
    cols = st.columns(4)
    cards = [("Empresas encontradas", m["total"], f"{m['campanhas']} campanha(s)", ""), ("Investigadas", m["investigados"], "análises concluídas", ""),
             ("Qualificados", m["qualificados"], "score ≥ 40", ""), ("Alto potencial", m["alto"], "score ≥ 80", "")]
    for col, (a, b, c, d) in zip(cols, cards):
        col.markdown(kpi(a, b, c, d), unsafe_allow_html=True)
    cols = st.columns(4)
    taxa = f"{m['taxa']}" if m["taxa"] is not None else "—"
    cards = [("Em acompanhamento", m["acompanhamento"], "contato ou negociação", ""), ("Abordagens preparadas", m["abordagens"], "leads com mensagem", ""),
             ("Campanhas ativas", m["campanhas_ativas"], f"de {m['campanhas']} no total", ""), ("Taxa de qualificação", taxa, "qualificados / investigados", "%" if m["taxa"] is not None else "")]
    for col, (a, b, c, d) in zip(cols, cards):
        col.markdown(kpi(a, b, c, d), unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([2, 1])
    with left:
        st.markdown('<p class="lbl">Evolução da prospecção</p>', unsafe_allow_html=True)
        if m["evolution"]:
            df = pd.DataFrame(m["evolution"])
            base = alt.Chart(df).encode(x=alt.X("data:T", title=None))
            chart = (base.mark_area(opacity=.25, color="#ff5a5f", line={"color": "#f5b95b"}).encode(y=alt.Y("acumulado:Q", title=None))
                     + base.mark_bar(color="#f5b95b", opacity=.6, size=10).encode(y="novos:Q")).properties(height=240).configure_view(strokeWidth=0).configure_axis(gridColor="#ffffff12", labelColor="#a39d98")
            st.altair_chart(chart, width="stretch")
        else:
            empty_state("◌", "Sem dados ainda", "A evolução aparece depois que você salvar as primeiras empresas.")
    with right:
        st.markdown('<p class="lbl">Distribuição por prioridade</p>', unsafe_allow_html=True)
        if m["dist"]:
            df = pd.DataFrame({"classe": list(m["dist"]), "qtd": list(m["dist"].values())})
            ch = alt.Chart(df).mark_bar(cornerRadiusEnd=6).encode(x=alt.X("qtd:Q", title=None), y=alt.Y("classe:N", title=None, sort="-x"),
                color=alt.Color("classe:N", legend=None, scale=alt.Scale(domain=["Alta prioridade", "Média prioridade", "Baixa prioridade", "Baixa aderência"], range=["#34d399", "#f5b95b", "#ff8a8d", "#6f6a66"]))
            ).properties(height=240).configure_view(strokeWidth=0).configure_axis(gridColor="#ffffff12", labelColor="#a39d98")
            st.altair_chart(ch, width="stretch")
        else:
            empty_state("◌", "Nada qualificado", "Investigue empresas para ver a distribuição.")

    a, b = st.columns(2)
    with a:
        best = sorted([l for l in leads if l.get("score")], key=lambda l: -float(l["score"]))[:6]
        body = rows_html([(l["nome"], f"{l.get('segmento','')} · {l.get('cidade','')}", pill(f"{l['score']} · {l.get('classificacao','')}", prio_tone(l.get("classificacao", "")))) for l in best]) if best else '<p class="muted">Sem leads qualificados ainda.</p>'
        html_block(card_html("Melhores oportunidades", body, "Ranking por score"))
        last = sorted(leads, key=lambda l: l.get("criado_em", ""), reverse=True)[:6]
        body = rows_html([(l["nome"], f"{l.get('segmento','')} · {l.get('cidade','')}", pill(l.get("etapa", ""))) for l in last]) if last else '<p class="muted">Nenhuma empresa encontrada ainda.</p>'
        st.write("")
        html_block(card_html("Últimas empresas encontradas", body, "Recentes"))
    with b:
        parts = m["health_parts"]
        if m["health"] is not None:
            tone = "var(--green)" if m["health"] >= 75 else "var(--amber)" if m["health"] >= 50 else "var(--coral)"
            label = "Saudável" if m["health"] >= 75 else "Atenção" if m["health"] >= 50 else "Crítico"
            lines = "".join(f'<div class="row"><span>{esc(k)}</span><b>{v}%</b></div>' for k, v in parts.items())
            body = f'<div style="display:flex;gap:1.2rem;align-items:center">{ring(m["health"], tone)}<div><div class="hero" style="font-size:2rem">{label}</div></div></div>{lines}'
        else:
            body = '<p class="muted">O diagnóstico aparece quando houver leads qualificados no funil.</p>'
        html_block(card_html("Saúde do funil", body, "Diagnóstico ativo"))
        nxt = sorted([l for l in leads if l.get("proxima_acao_data")], key=lambda l: l["proxima_acao_data"])[:5]
        body = rows_html([(l["nome"], l.get("proxima_acao", "") or "—", pill(l["proxima_acao_data"], "low" if l in m["overdue"] else "")) for l in nxt]) if nxt else '<p class="muted">Sem próximas atividades agendadas.</p>'
        st.write("")
        html_block(card_html("Próximas atividades", body, "Agenda"))
        body = rows_html([(c["nome"], f"{c.get('investigados',0)}/{c.get('total_encontrados',0)} investigadas", pill(c["status"])) for c in m["active_camps"][:5]]) if m["active_camps"] else '<p class="muted">Nenhuma campanha em andamento.</p>'
        st.write("")
        html_block(card_html("Campanhas em andamento", body, "Processamento"))
