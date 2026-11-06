"""Componentes visuais (HTML escapado) no padrão visual DBB."""
from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
esc = html.escape
WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def inject_css() -> None:
    st.markdown(f"<style>{(ASSETS / 'styles.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def html_block(markup: str) -> None:
    st.markdown(markup.replace("\n", ""), unsafe_allow_html=True)


def eyebrow_date(dt) -> str:
    return f"{WEEKDAYS[dt.weekday()]}, {dt.day} de {MONTHS[dt.month - 1]}"


def greeting(dt) -> str:
    return "Bom dia" if dt.hour < 12 else "Boa tarde" if dt.hour < 18 else "Boa noite"


def page_header(eyebrow: str, title: str, accent: str = "", subtitle: str = "") -> None:
    acc = f' <span class="acc">{esc(accent)}</span>' if accent else ""
    sub = f'<p class="sub">{subtitle}</p>' if subtitle else ""
    html_block(f'<p class="eyebrow">{esc(eyebrow)}</p><h1 class="hero">{esc(title)}{acc}</h1>{sub}')


def kpi(label: str, value, hint: str = "", suffix: str = "") -> str:
    suf = f"<small>{esc(suffix)}</small>" if suffix else ""
    return f'<div class="card kpi"><p class="lbl">{esc(label)}</p><div class="v">{esc(str(value))}{suf}</div><div class="h">{esc(hint)}</div></div>'


def pill(text: str, tone: str = "") -> str:
    return f'<span class="pill {tone}">{esc(str(text))}</span>'


def prio_tone(classificacao: str) -> str:
    return {"Alta prioridade": "hi", "Média prioridade": "mid", "Baixa prioridade": "low"}.get(classificacao, "")


def ring(value: int | float, color: str = "var(--amber)") -> str:
    return f'<div class="ring" style="--p:{int(value)};--c:{color}"><div>{int(value)}</div></div>'


def bar(value: float, maximum: float) -> str:
    pct = 0 if not maximum else max(0, min(100, 100 * value / maximum))
    return f'<div class="bar"><i style="width:{pct:.0f}%"></i></div>'


def empty_state(icon: str, title: str, text: str) -> None:
    html_block(f'<div class="empty"><div class="ic">{esc(icon)}</div><b>{esc(title)}</b>{esc(text)}</div>')


def rows_html(items: list[tuple[str, str, str]]) -> str:
    """items: (titulo, subtitulo, badge_html)."""
    return "".join(f'<div class="row"><div><div class="t">{esc(t)}</div><div class="s">{esc(s)}</div></div><div>{b}</div></div>' for t, s, b in items)


def card_html(title: str, body: str, eyebrow: str = "") -> str:
    lb = f'<p class="lbl">{esc(eyebrow)}</p>' if eyebrow else ""
    return f'<div class="card">{lb}<h3>{esc(title)}</h3>{body}</div>'


def kanban_html(columns: dict[str, list[dict]]) -> str:
    out = []
    for stage, items in columns.items():
        cards = "".join(f'<div class="kcard">{esc(i.get("nome",""))}<small>{esc(i.get("classificacao","") or i.get("segmento",""))}</small></div>' for i in items[:30])
        out.append(f'<div class="kcol"><h4>{esc(stage)} · {len(items)}</h4>{cards or "<small class=muted>vazio</small>"}</div>')
    return f'<div class="kanban">{"".join(out)}</div>'


def login_screen(on_click) -> None:
    html_block('<div class="login"><div class="mark"></div><p class="eyebrow">Soluções empresariais</p><h1 class="hero">Lead <span class="acc">Hunter</span></h1>'
               '<p class="sub" style="margin-inline:auto">Encontre empresas com potencial, identifique oportunidades e prepare abordagens personalizadas.</p></div>')
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        st.button("Entrar com Google", type="primary", width="stretch", on_click=on_click, icon=":material/login:")


def blocked_screen(title: str, text: str, email: str = "", on_logout=None) -> None:
    html_block(f'<div class="login"><div class="mark" style="filter:grayscale(.7)"></div><h1 class="hero" style="font-size:2.2rem">{esc(title)}</h1>'
               f'<p class="sub" style="margin-inline:auto">{esc(text)}</p><p class="lbl">{esc(email)}</p></div>')
    if on_logout:
        _, mid, _ = st.columns([1, 1, 1])
        with mid:
            st.button("Sair e usar outra conta", width="stretch", on_click=on_logout)


def card_container(key: str):
    """Container nativo estilizado como card (para colocar widgets dentro)."""
    return st.container(key=f"card_{key}")
