"""Transforma dados do lead + site + CNPJ em evidências rastreáveis."""
from __future__ import annotations

from research.evidence import make


def build_evidences(lead: dict, site: dict | None = None, cnpj_data: dict | None = None) -> list[dict]:
    ev: list[dict] = []
    fonte_lead = lead.get("fonte_url") or lead.get("fonte") or "dados do lead"
    data_lead = lead.get("data_fonte") or None

    # ---- dados da fonte de descoberta ----
    if lead.get("telefone"):
        ev.append(make("fato", "telefone_publico", "Telefone público listado na fonte.", fonte_lead, data_lead))
    else:
        ev.append(make("nao_encontrado", "telefone_ausente", "Nenhum telefone foi encontrado na fonte consultada.", fonte_lead, data_lead))
    if lead.get("email"):
        ev.append(make("fato", "email_publico", "E-mail público listado na fonte.", fonte_lead, data_lead))
    if lead.get("horario"):
        ev.append(make("fato", "horario_informado", f"Horário de funcionamento informado: {lead['horario']}", fonte_lead, data_lead))
    if lead.get("endereco"):
        ev.append(make("fato", "endereco_informado", f"Endereço informado: {lead['endereco']}", fonte_lead, data_lead))

    # ---- site ----
    site_url = lead.get("site", "")
    if not site_url:
        ev.append(make("nao_encontrado", "site_ausente",
                       "Nenhum site próprio foi encontrado nas fontes consultadas. Isso não confirma que a empresa não tenha site.",
                       fonte_lead, data_lead))
    elif site is None:
        ev.append(make("fato", "site_informado", f"Site informado na fonte: {site_url}", fonte_lead, data_lead))
    elif not site.get("ok"):
        ev.append(make("nao_encontrado", "site_inacessivel",
                       f"Não foi possível analisar o site {site_url}: {site.get('erro','falha desconhecida')}",
                       site_url, site.get("data")))
    else:
        src, dt = site.get("url_final", site_url), site.get("data")
        ev.append(make("fato", "site_acessado", "Site acessado e página inicial analisada.", src, dt))
        if site.get("titulo"):
            ev.append(make("fato", "site_titulo", f"Título da página: {site['titulo']}", src, dt))
        if site.get("h1"):
            ev.append(make("fato", "site_h1", f"Título principal da página: {site['h1']}", src, dt))
        if not site.get("https"):
            ev.append(make("fato", "site_sem_https", "A página inicial é servida sem HTTPS.", src, dt))
        if not site.get("viewport"):
            ev.append(make("fato", "site_sem_mobile", "A página não declara viewport para celular (sinal de possível layout não adaptado).", src, dt))
        if not site.get("descricao"):
            ev.append(make("fato", "site_sem_descricao", "A página inicial não possui meta descrição (texto exibido em buscas).", src, dt))
        if not site.get("ctas"):
            ev.append(make("fato", "site_sem_cta", "Não identificamos chamadas para ação (ex.: agendar, orçamento, fale conosco) no texto da página inicial.", src, dt))
        else:
            ev.append(make("fato", "site_com_cta", "Chamadas para ação identificadas: " + ", ".join(site["ctas"]), src, dt))
        if site.get("whatsapp"):
            ev.append(make("fato", "whatsapp_no_site", "Link de WhatsApp encontrado no site.", src, dt))
        else:
            ev.append(make("fato", "site_sem_whatsapp", "Nenhum link de WhatsApp foi encontrado na página inicial.", src, dt))
        if site.get("form"):
            ev.append(make("fato", "site_com_formulario", "A página inicial possui formulário de contato.", src, dt))
        for rede, link in (site.get("redes") or {}).items():
            ev.append(make("fato", f"{rede}_no_site", f"Perfil de {rede} vinculado no site: {link}", src, dt))

    # ---- redes (sem scraping: apenas links públicos informados) ----
    has_insta = bool(lead.get("instagram")) or bool(site and (site.get("redes") or {}).get("instagram"))
    if lead.get("instagram"):
        ev.append(make("fato", "instagram_informado", f"Perfil de Instagram público informado na fonte: {lead['instagram']}", fonte_lead, data_lead))
    elif not has_insta:
        ev.append(make("nao_encontrado", "instagram_nao_informado",
                       "Nenhum perfil de Instagram foi encontrado na fonte nem no site (não foi feita busca em redes sociais).",
                       fonte_lead, data_lead))

    # ---- CNPJ (dados abertos da Receita via BrasilAPI) ----
    if cnpj_data:
        src = "Receita Federal (dados abertos via BrasilAPI)"
        if cnpj_data.get("situacao"):
            ev.append(make("fato", "cnpj_situacao", f"Situação cadastral do CNPJ: {cnpj_data['situacao']}", src))
        if cnpj_data.get("porte"):
            ev.append(make("fato", "cnpj_porte", f"Porte declarado: {cnpj_data['porte']}", src))
        if cnpj_data.get("cnae"):
            ev.append(make("fato", "cnpj_cnae", f"Atividade principal (CNAE): {cnpj_data['cnae']}", src))
        if cnpj_data.get("abertura"):
            ev.append(make("fato", "cnpj_abertura", f"Início da atividade: {cnpj_data['abertura']}", src))

    # ---- hipótese comercial de canal de contato ----
    if not lead.get("telefone") and not lead.get("email") and not (site and (site.get("whatsapp") or site.get("tel") or site.get("email"))):
        ev.append(make("hipotese", "canal_digital_nao_encontrado",
                       "Hipótese: pode haver dificuldade para um cliente encontrar um canal direto de contato (nenhum telefone, e-mail ou WhatsApp localizado).",
                       fonte_lead, data_lead))
    return ev
