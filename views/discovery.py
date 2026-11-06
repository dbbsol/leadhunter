"""Descoberta: OpenStreetMap, importação CSV/XLSX e cadastro manual."""
import pandas as pd
import streamlit as st

from core.config import DEFAULT_LIMITS
from discovery.importers import ImportError_, auto_mapping, df_to_leads, read_table
from discovery.normalize import normalize_lead
from discovery.osm import SEGMENTS, DiscoveryError, filter_results, search_osm, usando_geoapify
from ui.components import empty_state, page_header
from views._common import campaign_picker


@st.dialog("Novo lead")
def new_lead_dialog(ctx):
    camps = ctx.campaigns.list()
    nome = st.text_input("Nome da empresa *")
    c1, c2 = st.columns(2)
    segmento = c1.text_input("Segmento")
    cidade = c2.text_input("Cidade")
    uf = c1.text_input("UF", max_chars=2)
    tel = c2.text_input("Telefone")
    site = c1.text_input("Site")
    insta = c2.text_input("Instagram")
    camp_names = {c["id"]: c["nome"] for c in camps}
    cid = st.selectbox("Campanha", ["__nova__"] + list(camp_names), format_func=lambda i: "Criar campanha 'Cadastro manual'" if i == "__nova__" else camp_names[i])
    if st.button("Salvar lead", type="primary"):
        if not nome.strip():
            st.error("Informe o nome da empresa.")
            return
        if cid == "__nova__":
            cid = ctx.campaigns.create("Cadastro manual", segmento or "Geral", cidade, uf.upper())["id"]
        res = ctx.leads.add_leads([{"nome": nome, "segmento": segmento, "cidade": cidade, "uf": uf, "telefone": tel, "site": site, "instagram": insta, "fonte": "manual", "fonte_id": ""}], cid)
        ctx.campaigns.refresh_counts(cid)
        if res["inseridos"]:
            st.success("Lead salvo.")
            st.rerun()
        else:
            st.warning(f"Não salvo: duplicado ({res['duplicados']}) ou na lista de supressão ({res['suprimidos']}).")


def _save_block(ctx, leads: list[dict], prefix: str, default_seg: str, default_city: str, default_uf: str):
    """Mostra prévia deduplicada e salva em uma campanha."""
    existing = ctx.leads.list()
    from discovery.normalize import dedupe
    norm = [normalize_lead(l) for l in leads]
    supp = ctx.leads.suppression_values()
    norm = [l for l in norm if not ctx.leads.is_suppressed(l, supp)]
    unique, dups = dedupe(norm, existing)
    st.markdown(f"**{len(leads)}** encontrados · **{len(unique)}** novos · **{len(dups)}** duplicados/suprimidos ignorados")
    if not unique:
        st.info("Nada novo para salvar: todas as empresas já existem ou estão na lista de supressão.")
        return
    df = pd.DataFrame(unique)[["nome", "segmento", "bairro", "telefone", "site", "instagram", "fonte"]]
    st.dataframe(df, width="stretch", hide_index=True)
    camps = ctx.campaigns.list()
    names = {c["id"]: c["nome"] for c in camps}
    c1, c2 = st.columns(2)
    cid = c1.selectbox("Salvar em", ["__nova__"] + list(names), format_func=lambda i: "Nova campanha" if i == "__nova__" else names[i], key=f"{prefix}_dest")
    nome = c2.text_input("Nome da nova campanha", value=f"{default_seg} - {default_city}".strip(" -"), key=f"{prefix}_nome", disabled=cid != "__nova__")
    objetivo = st.text_input("Objetivo da campanha", placeholder="Ex.: encontrar restaurantes com potencial para contratar marketing digital", key=f"{prefix}_obj", disabled=cid != "__nova__")
    if st.button("Salvar empresas na campanha", type="primary", key=f"{prefix}_save"):
        with st.spinner("Salvando no Google Sheets…"):
            camp = ctx.campaigns.create(nome, default_seg, default_city, default_uf, objetivo) if cid == "__nova__" else ctx.campaigns.get(cid)
            res = ctx.leads.add_leads(leads, camp["id"], int(camp.get("limite_empresas") or DEFAULT_LIMITS["limite_empresas_campanha"]))
            ctx.campaigns.refresh_counts(camp["id"])
        st.success(f"{res['inseridos']} empresa(s) salva(s). {res['duplicados']} duplicada(s), {res['suprimidos']} suprimida(s)"
                   + (f", {res['acima_do_limite']} acima do limite da campanha." if res["acima_do_limite"] else "."))
        st.session_state.pop(f"{prefix}_results", None)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_osm(segmento, cidade, uf, limite, tag):
    return search_osm(segmento, cidade, uf, limite, tag)


def render(ctx):
    page_header("Prospecção", "Encontre empresas", "reais.", "Pesquise no OpenStreetMap, importe suas listas ou cadastre manualmente. Duplicidades e contatos suprimidos são removidos automaticamente.")
    t1, t2, t3 = st.tabs(["OPENSTREETMAP", "IMPORTAR CSV/XLSX", "CADASTRO MANUAL"])

    with t1:
        with st.form("osm"):
            c1, c2, c3 = st.columns([2, 2, 1])
            seg = c1.selectbox("Segmento", list(SEGMENTS) + ["Personalizado (tag OSM)"])
            cidade = c2.text_input("Cidade", value="Porto Alegre")
            uf = c3.text_input("Estado (UF)", value="RS", max_chars=2)
            c4, c5, c6 = st.columns([2, 2, 1])
            bairro = c4.text_input("Bairro (opcional)")
            kws = c5.text_input("Palavras-chave no nome (separadas por vírgula)")
            qtd = c6.number_input("Quantidade", 10, 500, 100, step=10)
            c7, c8 = st.columns(2)
            site_f = c7.selectbox("Característica do negócio", ["todos", "sem site", "com site"])
            only_phone = c8.checkbox("Somente com telefone público", value=False)
            tag = st.text_input("Tag OSM personalizada (ex.: shop=florist)", disabled=False) if seg.startswith("Personalizado") else ""
            go = st.form_submit_button("Buscar empresas", type="primary", icon=":material/search:")
        if go:
            if not cidade.strip() or len(uf.strip()) != 2:
                st.error("Informe a cidade e a UF com 2 letras.")
            else:
                try:
                    with st.spinner("Consultando empresas… (pode levar até 1 minuto)"):
                        res = _cached_osm("" if seg.startswith("Personalizado") else seg, cidade.strip(), uf.strip().upper(), int(qtd), tag)
                    res = filter_results(res, bairro, kws, only_phone, site_f)
                    st.session_state["osm_results"] = {"leads": res, "seg": seg, "cidade": cidade.strip(), "uf": uf.strip().upper()}
                except DiscoveryError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Falha inesperada na busca ({type(exc).__name__}: {str(exc)[:200]}). Rode 'python scripts/testar_osm.py' para diagnosticar.")
        data = st.session_state.get("osm_results")
        if data:
            if data["leads"]:
                st.caption("Fonte: © colaboradores do OpenStreetMap (ODbL)" + (", via Geoapify" if usando_geoapify() else "") + ". Dados públicos de cadastro de estabelecimentos; podem estar incompletos.")
                _save_block(ctx, data["leads"], "osm", data["seg"], data["cidade"], data["uf"])
            else:
                empty_state("⌕", "Nenhuma empresa encontrada", "Tente outro segmento, remova filtros ou amplie a cidade. O OpenStreetMap pode ter poucos dados em alguns bairros.")
        else:
            empty_state("⌕", "Pronto para buscar", "Escolha segmento e cidade e clique em Buscar empresas.")

    with t2:
        up = st.file_uploader("Arquivo .csv ou .xlsx (até 5 MB, 5.000 linhas)", type=["csv", "xlsx"])
        if up:
            try:
                df = read_table(up.getvalue(), up.name)
            except ImportError_ as exc:
                st.error(str(exc))
                df = None
            if df is not None:
                mapping = auto_mapping(list(df.columns))
                st.markdown("**Mapeamento de colunas** (ajuste se necessário)")
                cols = ["(ignorar)"] + list(df.columns)
                new_map, grid = {}, st.columns(4)
                for i, field in enumerate(["nome", "segmento", "cidade", "uf", "telefone", "site", "email", "instagram", "cnpj", "endereco", "bairro", "porte"]):
                    cur = mapping.get(field, "(ignorar)")
                    sel = grid[i % 4].selectbox(field, cols, index=cols.index(cur), key=f"map_{field}")
                    if sel != "(ignorar)":
                        new_map[field] = sel
                if "nome" not in new_map:
                    st.error("Mapeie a coluna de nome da empresa.")
                else:
                    c1, c2, c3 = st.columns(3)
                    dseg = c1.text_input("Segmento padrão (se faltar na planilha)", key="imp_seg")
                    dcid = c2.text_input("Cidade padrão", key="imp_cid")
                    duf = c3.text_input("UF padrão", max_chars=2, key="imp_uf")
                    leads = df_to_leads(df, new_map, dcid, duf.upper(), dseg)
                    _save_block(ctx, leads, "imp", dseg or "Importação", dcid, duf.upper())
        else:
            empty_state("⇪", "Importe sua lista", "Aceitamos colunas como nome, telefone, site, cidade, CNPJ. O mapeamento é automático.")

    with t3:
        st.caption("Cadastre uma empresa específica que você já conhece.")
        if st.button("Abrir formulário de novo lead", icon=":material/add:"):
            new_lead_dialog(ctx)
