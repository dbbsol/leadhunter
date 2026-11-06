"""Triagem rápida (sem IA) e investigação profunda por lotes, com retomada."""
import pandas as pd
import streamlit as st

from ai.scoring import triage
from core.config import DEFAULT_LIMITS
from core.permissions import quota_remaining
from services.campaign_service import LABELS
from services.processing import run_batch
from ui.components import empty_state, html_block, kpi, page_header, pill
from views._common import campaign_picker

PRIOS = ["Alta prioridade", "Média prioridade", "Baixa prioridade", "Não qualificado"]


def _triage_tab(ctx, cid):
    leads = [l for l in ctx.leads.list() if l.get("campanha_id") == cid]
    camp = ctx.campaigns.get(cid)
    new = [l for l in leads if l.get("etapa") == "Encontrado"]
    if not leads:
        empty_state("◌", "Campanha vazia", "Salve empresas em Descoberta para triá-las aqui.")
        return
    c1, c2 = st.columns([1, 3])
    if c1.button("Calcular triagem", type="primary", icon=":material/bolt:", disabled=not new, help="Rápida, sem IA e sem custo."):
        rows = []
        for l in new:
            t = triage(l, camp.get("segmento", ""), camp.get("cidade", ""))
            rows.append({"id": l["id"], "triagem": t["prioridade"], "triagem_pontos": t["pontos"], "triagem_motivo": t["motivo"]})
        ctx.leads.bulk_update(rows)
        st.rerun()
    c2.caption("A triagem usa apenas dados já coletados. Nenhuma empresa é descartada automaticamente — você revisa e decide.")

    triaged = [l for l in leads if l.get("triagem") and l.get("etapa") in ("Encontrado", "Selecionado")]
    if not triaged:
        st.info("Clique em **Calcular triagem** para classificar as empresas encontradas.")
        return
    f1, f2 = st.columns([2, 1])
    show = f1.multiselect("Filtrar prioridade", PRIOS, default=PRIOS[:3])
    triaged = [l for l in triaged if l["triagem"] in show]
    df = pd.DataFrame([{"id": l["id"], "Investigar": l["etapa"] == "Selecionado", "Empresa": l["nome"], "Prioridade": l["triagem"],
                        "Pontos": int(float(l.get("triagem_pontos") or 0)), "Motivo": l.get("triagem_motivo", "")} for l in sorted(triaged, key=lambda x: -float(x.get("triagem_pontos") or 0))])
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["id", "Empresa", "Pontos", "Motivo"],
                            column_config={"id": None, "Prioridade": st.column_config.SelectboxColumn(options=PRIOS), "Investigar": st.column_config.CheckboxColumn()}, key=f"triage_{cid}")
    if st.button("Salvar seleção e revisão", icon=":material/check:"):
        rows = []
        for _, r in edited.iterrows():
            rows.append({"id": r["id"], "triagem": r["Prioridade"], "etapa": "Selecionado" if r["Investigar"] else "Encontrado"})
        ctx.leads.bulk_update(rows)
        st.success(f"{int(edited['Investigar'].sum())} empresa(s) selecionada(s) para investigação profunda.")
        st.rerun()


def _sub_row(ctx):
    return next((r for r in ctx.admin_store.all("ASSINATURAS", fresh=True) if r.get("email", "").lower() == ctx.session.email.lower()), None)


def _sub_left(ctx) -> int:
    row = _sub_row(ctx)
    return quota_remaining(row.get("limite_pesquisas"), row.get("consumo")) if row else 0


def _investigate_tab(ctx, cid):
    ctx.campaigns.refresh_counts(cid)
    camp = ctx.campaigns.get(cid)
    selected = [l for l in ctx.leads.list() if l.get("campanha_id") == cid and l.get("etapa") == "Selecionado"]
    gem = ctx.gemini()

    cols = st.columns(4)
    cols[0].markdown(kpi("Status", LABELS.get(camp["status"], camp["status"]), camp.get("nota", "")), unsafe_allow_html=True)
    cols[1].markdown(kpi("Aguardando", len(selected), "selecionadas"), unsafe_allow_html=True)
    cols[2].markdown(kpi("Investigadas", f"{camp.get('investigados', 0)}/{camp.get('limite_investigacoes', '')}", "limite da campanha"), unsafe_allow_html=True)
    cols[3].markdown(kpi("Gemini hoje", f"{gem.calls_today}/{gem.daily_limit}" if gem else "off", "chamadas" if gem else "usando regras"), unsafe_allow_html=True)
    st.caption(f"Pesquisas restantes na assinatura: **{_sub_left(ctx)}**. Sem chave Gemini, a análise usa regras (continua funcionando).")

    if not selected:
        empty_state("☐", "Nenhuma empresa selecionada", "Na aba Triagem, marque as empresas que valem uma investigação profunda.")
        return
    c1, c2 = st.columns(2)
    one = c1.button("Processar próximo lote", type="primary", icon=":material/play_arrow:")
    allb = c2.button("Processar até o limite", icon=":material/fast_forward:")
    if not (one or allb):
        return
    perfil = ctx.store.get_config("perfil_servico", "")
    total, res = 0, {"status": "RUNNING", "motivo": "", "processados": 0}
    with st.status("Investigando empresas…", expanded=True) as status:
        bar = st.progress(0.0)

        def progress(i, n, nome):
            bar.progress(min(1.0, i / max(n, 1)))
            st.write(f"✔ {nome}")

        while True:
            left = _sub_left(ctx)
            res = run_batch(ctx.store, cid, gemini=gem, subscription_remaining=left, perfil_usuario=perfil, on_progress=progress)
            total += res["processados"]
            if res["processados"]:
                row = _sub_row(ctx)
                ctx.admin_store.upsert("ASSINATURAS", [{"email": row["email"], "consumo": int(float(row.get("consumo") or 0)) + res["consumo"]}], key="email")
            if one or res["status"] in ("COMPLETED", "FAILED") or res["processados"] == 0 or res["motivo"]:
                break
        status.update(label=f"{total} empresa(s) investigada(s). {res.get('motivo', '')}", state="complete")
    if res.get("falhas"):
        st.warning(f"{res['falhas']} empresa(s) falharam e serão tentadas de novo (máx. 2 tentativas).")
    if res.get("motivo"):
        st.info(res["motivo"])
    if total:
        st.success("Pronto. Veja os resultados em **Inteligência**.")


def render(ctx):
    page_header("Prospecção", "Triagem e", "investigação.", "Primeiro uma triagem barata, sem IA. Depois você escolhe quem merece uma investigação profunda, com evidências e fontes.")
    cid, camps = campaign_picker(ctx, "inv_camp")
    if not cid:
        empty_state("◌", "Nenhuma campanha", "Crie uma campanha salvando empresas em Descoberta.")
        return
    t1, t2 = st.tabs(["1 · TRIAGEM RÁPIDA", "2 · INVESTIGAÇÃO PROFUNDA"])
    with t1:
        _triage_tab(ctx, cid)
    with t2:
        _investigate_tab(ctx, cid)
