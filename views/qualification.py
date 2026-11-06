"""Inteligência comercial: ficha detalhada do lead com score, evidências e SPIN."""
import pandas as pd
import streamlit as st

from core.config import jload
from research.evidence import ROTULOS
from services.processing import investigate_lead, persist_results
from ui.components import card_html, empty_state, esc, html_block, page_header, pill, prio_tone, ring, bar
from views._common import campaign_picker, current_lead_id, lead_label, select_lead

TONE = {"fato": "fact", "hipotese": "mid", "oportunidade": "hi", "nao_encontrado": ""}


def render(ctx):
    page_header("Análise", "Inteligência", "comercial.", "Cada recomendação está ligada a uma evidência com fonte e data. Fato observado, hipótese e informação não encontrada ficam sempre separados.")
    leads = [l for l in ctx.leads.list() if l.get("score")]
    if not leads:
        empty_state("◌", "Nenhum lead analisado", "Investigue empresas em Triagem e investigação para ver as fichas aqui.")
        return

    f1, f2, f3 = st.columns([2, 1, 1])
    q = f1.text_input("Buscar", placeholder="Nome, cidade ou segmento", label_visibility="collapsed")
    prio = f2.multiselect("Prioridade", ["Alta prioridade", "Média prioridade", "Baixa prioridade", "Baixa aderência"], placeholder="Prioridade")
    minscore = f3.slider("Score mínimo", 0, 100, 0)
    from discovery.normalize import norm_text
    view = [l for l in leads if (not q or norm_text(q) in norm_text(f"{l['nome']} {l.get('cidade')} {l.get('segmento')}"))
            and (not prio or l.get("classificacao") in prio) and float(l["score"]) >= minscore]
    view.sort(key=lambda l: -float(l["score"]))
    if not view:
        st.info("Nenhum lead com esses filtros.")
        return
    ids = [l["id"] for l in view]
    cur = current_lead_id() if current_lead_id() in ids else ids[0]
    chosen = st.selectbox("Lead", ids, index=ids.index(cur), format_func=lambda i: lead_label(next(l for l in view if l["id"] == i)))
    select_lead(chosen)
    lead = ctx.leads.get(chosen)
    qual = next((q for q in ctx.store.all("QUALIFICACAO") if q["lead_id"] == chosen), None)
    inv = next((i for i in ctx.store.all("INVESTIGACOES") if i["lead_id"] == chosen), None)
    if not (qual and inv):
        st.warning("Este lead ainda não tem investigação completa.")
        return
    evid, an, crit = jload(inv["evidencias"], []), jload(inv["analise"], {}), jload(qual["criterios"], [])

    score = float(qual["score"])
    tone = "var(--green)" if score >= 80 else "var(--amber)" if score >= 60 else "var(--coral)"
    links = " · ".join(x for x in [lead.get("site"), lead.get("instagram"), lead.get("telefone"), lead.get("email")] if x)
    html_block(f'<div class="card"><div style="display:flex;gap:1.4rem;align-items:center;flex-wrap:wrap">{ring(score, tone)}<div style="flex:1;min-width:240px">'
               f'<p class="lbl">{esc(lead.get("segmento",""))} · {esc(lead.get("cidade",""))}-{esc(lead.get("uf",""))}</p><h3 style="font-size:1.8rem;margin:.1rem 0">{esc(lead["nome"])}</h3>'
               f'{pill(qual["classificacao"], prio_tone(qual["classificacao"]))} {pill("Confiança " + qual["confianca_nivel"] + " (" + str(qual["confianca"]) + ")")} {pill("Origem: " + inv["origem_analise"][:24])}'
               f'<p class="muted" style="margin:.6rem 0 0;font-size:.85rem">{esc(links)}<br>Fonte: {esc(lead.get("fonte",""))} · investigado em {esc(inv["data"][:10])}</p></div></div></div>')
    st.write("")
    html_block(card_html("Por que este lead é uma oportunidade?", f'<p style="line-height:1.6">{esc(an.get("por_que_e_oportunidade",""))}</p>', "Resumo"))

    st.write("")
    t1, t2, t3, t4 = st.tabs(["OPORTUNIDADES", "EVIDÊNCIAS", "SCORE E CRITÉRIOS", "PERGUNTAS SPIN"])
    with t1:
        for o in an.get("oportunidades", []):
            refs = ", ".join(f"[{r}]" for r in o.get("evidencia_ref", []))
            html_block(f'<div class="card" style="margin-bottom:.7rem"><b>{esc(o["titulo"])}</b><p class="muted" style="margin:.3rem 0">{esc(o.get("descricao",""))}</p><span class="pill">evidências {refs}</span></div>')
        if not an.get("oportunidades"):
            st.info("Nenhuma oportunidade sustentada por evidências foi identificada. Revise manualmente antes de abordar.")
        st.markdown(f"**Próxima ação recomendada:** {an.get('proxima_acao','—')}")
    with t2:
        st.caption("Informação não encontrada **não** significa problema. Hipóteses não são fatos.")
        for i, e in enumerate(evid):
            html_block(f'<div class="row"><div><div class="t">[{i}] {esc(e["texto"])}</div><div class="s">{esc(e["fonte"][:90])} · {esc(e["data"][:10])}</div></div><div>{pill(ROTULOS[e["tipo"]], TONE[e["tipo"]])}</div></div>')
        for lim in jload(inv.get("limitacoes"), []):
            st.warning(lim)
    with t3:
        for c in crit:
            html_block(f'<div style="margin-bottom:.8rem"><div style="display:flex;justify-content:space-between"><span>{esc(c["nome"])}</span><b>{c["pontos"]}/{c["peso"]}</b></div>{bar(c["pontos"], c["peso"])}</div>')
            with st.expander("Por quê?"):
                for j in c["justificativas"] or ["Sem pontos: nenhuma evidência para este critério."]:
                    st.write("• " + j)
    with t4:
        for key, nome in (("situacao", "S · Situação"), ("problema", "P · Problema"), ("implicacao", "I · Implicação"), ("necessidade_beneficio", "N · Necessidade-benefício")):
            blk = an.get(key, {})
            items = blk.get("observacoes") or blk.get("hipoteses") or blk.get("valor_potencial") or []
            html_block(card_html(nome, "".join(f'<p class="muted" style="margin:.2rem 0">• {esc(x)}</p>' for x in items) + f'<p style="margin-top:.6rem"><b>“{esc(blk.get("pergunta",""))}”</b></p>'))
            st.write("")
        st.caption("Implicações e problemas são hipóteses até serem confirmados na conversa.")

    st.write("")
    c1, c2 = st.columns(2)
    if c1.button("Reinvestigar agora (ignora cache)", icon=":material/refresh:"):
        with st.spinner("Reinvestigando…"):
            camp = ctx.campaigns.get(lead.get("campanha_id"))
            g = ctx.gemini()
            r = investigate_lead(lead, campaign=camp, existing=inv, gemini=g, perfil_usuario=ctx.store.get_config("perfil_servico", ""), force=True)
            persist_results(ctx.store, [r])
            if g:
                g.flush()
        st.rerun()
    c2.caption("Para escrever a abordagem, abra o **Message Studio** — este lead já fica selecionado.")
