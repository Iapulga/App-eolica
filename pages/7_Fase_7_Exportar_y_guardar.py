import html
import re

import numpy as np
import pandas as pd
import streamlit as st

from calculos_economicos import format_currency_amount, format_lcoe_value
from db import (
    cargar_config,
    exportar_proyecto_json_texto,
    guardar_config_values,
    guardar_proyecto,
    init_db,
)
from navigation import _icon_svg, render_dropdown_visibility_fix, render_sidebar_navigation
from reportes import get_project_context, get_report_context
from reportes.fase5_export_helpers import (
    HEAVY_EXPORT_STATE_KEY,
    INFORME_TECNICO_DOCX_STATE_KEY,
    INFORME_TECNICO_META_STATE_KEY,
    INFORME_TECNICO_PDF_STATE_KEY,
    RUNTIME_CONTEXT_STATE_KEY,
    build_basic_export_bundle,
    build_export_signature,
    build_figure_download_key,
    build_informe_tecnico_signature,
    dedupe_figure_export_artifacts,
    generate_heavy_export_artifacts,
    generate_informe_tecnico_exports,
    nombre_archivo_proyecto,
)

st.set_page_config(page_title="Fase 7 · Exportar y guardar", layout="wide")

init_db()
render_sidebar_navigation("pages/7_Fase_7_Exportar_y_guardar.py")


# -----------------------------------------------------------------------------
# Helpers visuales locales
# -----------------------------------------------------------------------------
def _escape(value) -> str:
    return html.escape("" if value is None else str(value))


def _safe_icon(name: str, size: int = 22, color: str = "#2563eb") -> str:
    try:
        return _icon_svg(name, size, color)
    except Exception:
        stroke = 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"'
        return (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'style="color:{color};display:block" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="12" cy="12" r="8" {stroke}/></svg>'
        )


def _has_value(value) -> bool:
    return value is not None and str(value).strip() not in {"", "None", "nan", "NaN"}


# Formato español: el código produce "1,234.5"; se muestra "1.234,5" (solo tokens numéricos).
_F7_NUM_RE = re.compile(r"\d[\d.,]*\d")
_F7_SWAP = str.maketrans({",": ".", ".": ","})


def _es(text) -> str:
    return _F7_NUM_RE.sub(lambda m: m.group(0).translate(_F7_SWAP), str(text)) if text else text


# _fmt_float y _f7_money devuelven formato US ('1,234.5'); la ficha KPI aplica _es() UNA vez
# al mostrar (aplicarlo dos veces deshacía el cambio).
def _fmt_float(value, decimals=2, suffix="") -> str:
    if not _has_value(value):
        return "N/D"
    try:
        return f"{float(value):,.{decimals}f}{suffix}"
    except Exception:
        return f"{value}{suffix}"


def _f7_money(value, unidad: str) -> str:
    """Moneda compacta del mockup: 'USD 19.63 M' / 'USD 449.9 k' → la ficha lo muestra como '19,63 M'."""
    if not _has_value(value):
        return "N/D"
    try:
        v = float(value)
    except Exception:
        return f"{unidad} {value}"
    if abs(v) >= 1e6:
        return f"{unidad} {v / 1e6:,.2f} M"
    if abs(v) >= 1e3:
        return f"{unidad} {v / 1e3:,.1f} k"
    return f"{unidad} {v:,.0f}"


def _f7_icono(icon: str, size: int = 22, color: str = "#d97706") -> str:
    """Emoji (mockup) si el icono no es ASCII; si no, el icono SVG de navigation."""
    if icon and not icon.isascii():
        return f'<span class="f7-emoji">{_escape(icon)}</span>'
    return _safe_icon(icon, size, color)


def _f7_plano_svg(df_layout) -> str:
    """Plano del parque (turbinas de Fase 4) con tooltip por turbina, escala y norte."""
    pts = []
    for i, (_, r) in enumerate(df_layout.iterrows()):
        try:
            pts.append((str(r.get("turbina_id") or f"T{i + 1}"), float(r["x_m"]), float(r["y_m"])))
        except (TypeError, ValueError, KeyError):
            continue
    if not pts:
        return ""
    W, H, L, R, T, B = 520.0, 230.0, 44.0, 44.0, 34.0, 40.0
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]
    dx, dy = max(max(xs) - min(xs), 1.0), max(max(ys) - min(ys), 1.0)
    esc = min((W - L - R) / dx, (H - T - B) / dy)
    if dx < 50 and dy < 50:
        esc = (W - L - R) / 400.0
    xc, yc = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def P(x, y):
        return L + (W - L - R) / 2 + (x - xc) * esc, T + (H - T - B) / 2 - (y - yc) * esc

    p = ['<svg viewBox="0 0 520 230" xmlns="http://www.w3.org/2000/svg">',
         '<rect x="6" y="6" width="508" height="218" rx="16" fill="#fffbeb" stroke="#fde68a"/>',
         '<g opacity=".6">' + "".join(f'<line x1="{gx}" y1="12" x2="{gx}" y2="218" stroke="#fef3c7"/>' for gx in range(60, 500, 60)) + "</g>"]
    for tid, x, y in pts:
        px, py = P(x, y)
        tip = _es(f"{tid} · x = {x:,.0f} m · y = {y:,.0f} m")
        p.append(f'<g style="cursor:help"><title>{_escape(tip)}</title>'
                 f'<circle cx="{px:.1f}" cy="{py:.1f}" r="11" fill="#d97706" opacity=".18"/>'
                 f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6.5" fill="#d97706" stroke="#fff" stroke-width="2"/>'
                 f'<text x="{px:.1f}" y="{py - 12:.1f}" text-anchor="middle" font-size="10" font-weight="900" fill="#92400e">{_escape(tid)}</text></g>')
    raw = (W - L - R) / esc / 4.0
    e = 10 ** np.floor(np.log10(raw)) if raw > 0 else 1.0
    lm = next((m * e for m in (5, 2, 1) if m * e <= raw), e)
    lpx = lm * esc
    p.append(f'<line x1="20" y1="208" x2="{20 + lpx:.1f}" y2="208" stroke="#78350f" stroke-width="2.4"/>'
             f'<text x="{20 + lpx / 2:.1f}" y="200" text-anchor="middle" font-size="9.5" font-weight="900" fill="#78350f">{_escape(_es(f"{lm:,.0f} m"))}</text>'
             '<g transform="translate(492,30)"><circle r="13" fill="#fff" stroke="#fde68a"/>'
             '<path d="M0,-8 L4.5,4 L0,1 L-4.5,4 Z" fill="#78350f"/>'
             '<text y="10.5" text-anchor="middle" font-size="7.5" font-weight="900" fill="#78350f">N</text></g></svg>')
    return "".join(p)


def _section_header(title: str, subtitle: str = "", icon: str = "chart", color: str = "#d97706") -> None:
    st.markdown(
        f"""
<div class="f7-section-header">
    <div class="f7-section-icon"><span class="f7-icon-soft">{_f7_icono(icon, 22, color)}</span></div>
    <div>
        <div class="f7-section-title">{_escape(title)}</div>
        {f'<div class="f7-section-subtitle">{_escape(subtitle)}</div>' if subtitle else ''}
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


def _divider(title: str, subtitle: str = "", emoji: str = "📦", color: str = "") -> None:
    dc = f'style="--dc:{color}"' if color else ""
    st.markdown(
        f"""
<div class="f7-divider" {dc}>
    <div class="dx">{emoji}</div>
    <div><b>{_escape(title)}</b><small>{_escape(subtitle)}</small></div>
    <div class="dline"></div>
</div>
""",
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# CSS local — Diseño SMA 2.0 Aurora para Fase 7
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
/* ════════ Fondo ════════ */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%) !important;
}

/* ════════ Hero card (gradiente del acento) ════════ */
.hero-card{position:relative;overflow:hidden;background:linear-gradient(118deg,#d97706 0%,#92400e 80%);border:none;border-radius:20px;padding:22px 28px;margin-bottom:1rem;box-shadow:0 22px 44px rgba(217,119,6,.32),inset 0 1px 0 rgba(255,255,255,.25);min-height:unset !important;height:auto !important}
.hero-card::after{content:"";position:absolute;inset:0;pointer-events:none;background:
  radial-gradient(circle at 86% 12%, rgba(255,255,255,.20) 0 54px, transparent 55px),
  radial-gradient(circle at 95% 70%, rgba(255,255,255,.12) 0 86px, transparent 87px),
  linear-gradient(180deg, rgba(255,255,255,.08), transparent 40%)}
.hero-row{display:flex;align-items:center;gap:18px;position:relative;z-index:2}
.hero-icon{width:62px;height:62px;border-radius:19px;background:rgba(255,255,255,.17);
  border:1.5px solid rgba(255,255,255,.4);display:flex;align-items:center;justify-content:center;font-size:31px;flex-shrink:0;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 8px 18px rgba(0,0,0,.12)}
.fase-hero-title{font-size:25px;line-height:1.08;font-weight:800;letter-spacing:-.025em;color:#fff;margin:0 0 4px 0;text-shadow:0 1px 2px rgba(0,0,0,.12)}
.fase-hero-subtitle{color:rgba(255,255,255,.94);font-size:12.5px;line-height:1.45;font-weight:400;max-width:840px;margin:0}
.hero-pills{display:flex;gap:9px;margin-left:auto;position:relative;z-index:2}
.hpill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4);border-radius:15px;padding:8px 15px;text-align:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.25)}
.hpill b{display:block;font-size:16.5px;letter-spacing:-.01em;color:#fff}
.hpill span{font-size:9px;opacity:.92;text-transform:uppercase;letter-spacing:.07em;font-weight:700;color:rgba(255,255,255,.9)}

/* ════════ Section headers ════════ */
.f7-section-header{display:flex;align-items:center;gap:13px;margin:6px 0 14px}
.f7-section-title{color:#0a2444;font-size:16.5px;font-weight:900;letter-spacing:-.02em}
.f7-section-subtitle{color:#5a6b85;font-size:11px;font-weight:600;margin-top:2px}
.f7-icon-soft{width:46px;height:46px;border-radius:14px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}

/* ════════ Dividers ════════ */
.f7-divider{display:flex;align-items:center;gap:13px;margin:26px 2px 14px}
.f7-divider .dx{width:42px;height:42px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:20px;
  background:linear-gradient(135deg, color-mix(in srgb, var(--dc,var(--ac)) 88%, #fff), var(--dc,var(--ac)));color:#fff;
  box-shadow:0 8px 18px color-mix(in srgb, var(--dc,var(--ac)) 35%, transparent)}
.f7-divider b{font-size:15.5px;letter-spacing:-.01em;display:block}
.f7-divider small{display:block;font-size:10.5px;color:#5a6b85;font-weight:700}
.f7-divider .dline{flex:1;height:2px;border-radius:2px;
  background:linear-gradient(90deg, color-mix(in srgb, var(--dc,var(--ac)) 45%, #fff), transparent)}

/* ════════ KPI Grid (6 columnas) ════════ */
.f7-kpi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:4px 0 10px}
.f7-kpi-card{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;display:flex;gap:12px;
  align-items:center;box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06);transition:box-shadow .18s}
.f7-kpi-card:hover{box-shadow:0 12px 26px rgba(15,45,90,.10)}
.f7-kpi-icon{width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;
  background:linear-gradient(135deg, color-mix(in srgb, var(--kc,var(--ac)) 17%, #fff), color-mix(in srgb, var(--kc,var(--ac)) 6%, #fff)) !important;
  border:1.5px solid color-mix(in srgb, var(--kc,var(--ac)) 38%, #fff) !important;
  box-shadow:0 5px 12px color-mix(in srgb, var(--kc,var(--ac)) 18%, transparent) !important}
.f7-kpi-label{font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.07em}
.f7-kpi-value{font-size:20px;font-weight:900;letter-spacing:-.025em;line-height:1.08;margin-top:3px;font-variant-numeric:tabular-nums;color:#0a2444}
.f7-kpi-sub{font-style:normal;font-size:10px;color:#5a6b85;margin-top:2.5px;font-weight:600}

/* ════════ Summary Grid (6 columnas) ════════ */
.f7-summary-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:10px 0 14px}
.f7-summary-card{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;display:flex;gap:12px;
  align-items:center;box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06);transition:box-shadow .18s}
.f7-summary-card:hover{box-shadow:0 12px 26px rgba(15,45,90,.10)}
.f7-sc-icon{width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;
  background:linear-gradient(135deg, color-mix(in srgb, var(--kc,var(--ac)) 17%, #fff), color-mix(in srgb, var(--kc,var(--ac)) 6%, #fff)) !important;
  border:1.5px solid color-mix(in srgb, var(--kc,var(--ac)) 38%, #fff) !important;
  box-shadow:0 5px 12px color-mix(in srgb, var(--kc,var(--ac)) 18%, transparent) !important}
.f7-summary-label{font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.07em}
.f7-summary-value{font-size:18px;font-weight:900;margin-top:5px;word-break:break-word;line-height:1.1;color:#0a2444}

/* ════════ Banners ════════ */
.f7-banner{display:flex;align-items:center;gap:12px;border-radius:15px;padding:12px 16px;font-weight:800;font-size:12.5px;margin:10px 0}
.f7-banner .bx{width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:18px;background:rgba(255,255,255,.7);flex-shrink:0}
.f7-banner.ok{background:linear-gradient(120deg,#f0fdf4,#fff);border:1.5px solid #86efac;color:#15803d}
.f7-banner.warn{background:linear-gradient(120deg,#fffbeb,#fff);border:1.5px solid #fde68a;color:#b45309}
.f7-banner.info{background:linear-gradient(120deg, color-mix(in srgb,var(--ac) 8%,#fff), #fff);
  border:1.5px solid color-mix(in srgb,var(--ac) 30%,#fff);color:var(--ac)}

/* ════════ Export tiles (4 columnas) ════════ */
.f7-export-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin:10px 0 4px}
.f7-export-tile{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:15px 14px 13px;display:flex;flex-direction:column;gap:12px;
  box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06);transition:box-shadow .18s}
.f7-export-tile:hover{box-shadow:0 12px 26px rgba(15,45,90,.10)}
.f7-export-top{display:flex;align-items:center;gap:12px}
.f7-export-icon{width:54px;height:54px;border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:26px;flex-shrink:0;
  background:linear-gradient(135deg, color-mix(in srgb, var(--xc) 18%, #fff), color-mix(in srgb, var(--xc) 7%, #fff));
  border:1.5px solid color-mix(in srgb, var(--xc) 40%, #fff);box-shadow:0 6px 14px color-mix(in srgb, var(--xc) 22%, transparent)}
.f7-export-type{font-size:8.5px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.08em}
.f7-export-name{font-size:15px;font-weight:900;letter-spacing:-.02em;margin-top:1px;color:#0a2444}
.f7-export-desc{font-size:10px;color:#5a6b85;font-weight:600;margin-top:2px;line-height:1.35}

/* ════════ Chips ════════ */
.f7-chips{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.f7-chip{padding:9px 15px;border-radius:999px;border:1.5px solid #cfe0f5;background:#fff;font-size:12px;font-weight:800;
  color:#5a6b85;display:flex;gap:7px;align-items:center;box-shadow:0 2px 6px rgba(11,36,71,.04);cursor:pointer;transition:all .18s}
.f7-chip:hover{border-color:var(--ac);color:var(--ac);background:color-mix(in srgb, var(--ac) 6%, #fff)}
.f7-chip.on{background:linear-gradient(120deg, color-mix(in srgb,var(--ac) 13%,#fff), color-mix(in srgb,var(--ac) 6%,#fff));
  border-color:var(--ac);color:var(--ac);box-shadow:0 6px 14px color-mix(in srgb,var(--ac) 18%,transparent)}

/* ════════ Pills ════════ */
.f7-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;font-size:10.5px;font-weight:800;border:1px solid;white-space:nowrap}
.f7-pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px color-mix(in srgb,currentColor 18%,transparent)}
.f7-pill.ok{color:#15803d;background:#f0fdf4;border-color:#bbf7d0}
.f7-pill.warn{color:#b45309;background:#fffbeb;border-color:#fde68a}

/* ════════ Upload zone ════════ */
.f7-upload{border:2px dashed color-mix(in srgb,var(--ac) 42%,#fff);
  background:linear-gradient(180deg, color-mix(in srgb,var(--ac) 5%,#fff), #fff);
  border-radius:18px;padding:24px;text-align:center}
.f7-upload .ui{width:58px;height:58px;margin:0 auto;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:27px;
  background:#fff;border:1.5px solid color-mix(in srgb,var(--ac) 30%,#fff);box-shadow:0 8px 18px color-mix(in srgb,var(--ac) 14%,transparent)}
.f7-upload b{display:block;font-size:13px;margin-top:9px;color:#0a2444}
.f7-upload span{font-size:10.5px;color:#5a6b85;font-weight:600}

/* ════════ Cards SMA 2.0 — Fase 7 ════════ */
.st-key-f7_card_header,
.st-key-f7_card_exec_summary,
.st-key-f7_card_scenario,
.st-key-f7_card_exports,
.st-key-f7_card_informe_tecnico,
.st-key-f7_card_bankable,
.st-key-f7_card_gis_export,
.st-key-f7_save_section {
    border: 1px solid #cbd5e1 !important;
    border-radius: 28px !important;
    background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
    box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    overflow: visible !important;
    box-sizing: border-box !important;
    margin-bottom: 16px !important;
}
.st-key-f7_card_header {
    border: 1.35px solid #cbd5e1 !important;
}
.st-key-f7_card_header div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_exec_summary div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_scenario div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_exports div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_informe_tecnico div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_bankable div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_gis_export div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_save_section div[data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
    box-shadow: none !important;
    border-radius: 28px !important;
    background: transparent !important;
    overflow: visible !important;
    box-sizing: border-box !important;
    padding: 1.1rem 1.2rem 1.1rem 1.2rem !important;
}

/* ════════ Export card button overrides ════════ */
.st-key-f7_card_exports [data-testid="stButton"]>button,
.st-key-f7_card_exports [data-testid="stDownloadButton"]>button{
    width:100%;background:#ffffff !important;border:1.5px solid #bfdbfe !important;color:#2563eb !important;
    border-radius:12px !important;font-weight:800 !important;min-height:40px !important;font-size:14px !important
}
.st-key-f7_card_exports [data-testid="stButton"]>button:hover,
.st-key-f7_card_exports [data-testid="stDownloadButton"]>button:hover{
    background:#eff6ff !important;border-color:#2563eb !important
}
.st-key-f7_card_exports [data-testid="stButton"]>button:disabled,
.st-key-f7_card_exports [data-testid="stDownloadButton"]>button:disabled{
    background:#f8fafc !important;border-color:#e2e8f0 !important;color:#94a3b8 !important
}

/* ════════ Save section button overrides ════════ */
.st-key-f7_save_section [data-testid="stButton"]>button[data-testid="stBaseButton-primary"]{
    background:linear-gradient(120deg,var(--ac),var(--ac2)) !important;border:none !important;color:#fff !important;
    box-shadow:0 8px 18px color-mix(in srgb,var(--ac) 30%,transparent) !important
}
.st-key-f7_save_section [data-testid="stDownloadButton"]>button{
    background:#fff !important;border:1.5px solid #86b7ff !important;color:#2563eb !important
}

/* ════════ Inputs ════════ */
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] div[data-baseweb="select"] > div{
    background:#fff !important;border-color:#cfe2f7 !important;color:#0a2444 !important
}
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button{
    border-radius:12px !important;min-height:42px !important;font-weight:800 !important
}

/* ════════ Columnas iguales para secciones pareadas ════════ */
div[data-testid="stHorizontalBlock"]:has(.st-key-f7_card_informe_tecnico),
div[data-testid="stHorizontalBlock"]:has(.st-key-f7_card_gis_export){
  align-items:stretch !important
}
div[data-testid="stHorizontalBlock"]:has(.st-key-f7_card_informe_tecnico) > div[data-testid="column"],
div[data-testid="stHorizontalBlock"]:has(.st-key-f7_card_gis_export) > div[data-testid="column"]{
  display:flex !important;flex-direction:column !important
}
.st-key-f7_card_informe_tecnico,
.st-key-f7_card_bankable,
.st-key-f7_card_gis_export,
.st-key-f7_save_section{
  flex:1 !important;display:flex !important;flex-direction:column !important
}
.st-key-f7_card_informe_tecnico > div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_bankable > div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_card_gis_export > div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f7_save_section > div[data-testid="stVerticalBlockBorderWrapper"]{
  flex:1 !important
}

/* ════════ Export tile button coloreado (cada tile usa --xc) ════════ */
.f7-export-tile .xbtn{margin-top:auto;text-align:center;border-radius:12px;padding:10px 8px;font-weight:800;font-size:12px;
  color:var(--xc);background:color-mix(in srgb, var(--xc) 8%, #fff);border:1.5px solid color-mix(in srgb, var(--xc) 38%, #fff);
  cursor:pointer;transition:all .18s}
.f7-export-tile .xbtn:hover{background:color-mix(in srgb, var(--xc) 14%, #fff);box-shadow:0 6px 14px color-mix(in srgb, var(--xc) 22%, transparent)}

/* ════════ Responsive ════════ */
@media(max-width:1200px){.f7-kpi-grid,.f7-summary-grid{grid-template-columns:repeat(3,1fr)}.f7-export-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.f7-kpi-grid,.f7-summary-grid{grid-template-columns:repeat(2,1fr)}.f7-export-grid{grid-template-columns:1fr}}
/* ════════ Aurora v2 (F7) ════════ */
.hero-card{border-radius:26px !important;margin:0 !important}
.hero-row{min-height:87px}
.hero-text{flex:1;min-width:0}
.f7-wind{position:absolute;left:-30px;top:0;bottom:0;width:58%;height:100%;opacity:.45;pointer-events:none;z-index:1}
.f7-wind path{stroke:rgba(255,255,255,.55);stroke-width:2;fill:none;stroke-dasharray:16 11;animation:f7windmove 2.6s linear infinite}
.f7-wind path:nth-child(2){animation-duration:3.4s;opacity:.7}
.f7-wind path:nth-child(3){animation-duration:4.2s;opacity:.5}
@keyframes f7windmove{to{stroke-dashoffset:-54}}
/* el hero NO va dentro de una card blanca (el st-key cae en el propio stVerticalBlock) */
#root .st-key-f7_card_header{background:transparent !important;border:none !important;box-shadow:none !important;padding:0 !important;
  border-radius:0 !important;min-height:0 !important;overflow:visible !important;margin-bottom:14px !important;gap:0 !important}
#root .st-key-f7_card_header::before{display:none !important}
/* Franja ámbar que sigue la curva: radio 27px = card 28px - 1px de borde (incluye Guardado final) */
#root div[data-testid="stVerticalBlock"]:is(.st-key-f7_card_exec_summary,.st-key-f7_card_scenario,.st-key-f7_card_exports,.st-key-f7_card_informe_tecnico,.st-key-f7_card_bankable,.st-key-f7_card_gis_export,.st-key-f7_save_section){position:relative !important}
#root div[data-testid="stVerticalBlock"]:is(.st-key-f7_card_exec_summary,.st-key-f7_card_scenario,.st-key-f7_card_exports,.st-key-f7_card_informe_tecnico,.st-key-f7_card_bankable,.st-key-f7_card_gis_export,.st-key-f7_save_section)::before{
  content:"" !important;position:absolute !important;top:0 !important;right:0 !important;bottom:0 !important;left:0 !important;height:auto !important;width:auto !important;
  z-index:5;pointer-events:none;display:block !important;
  background:linear-gradient(90deg,#d97706, color-mix(in srgb,#d97706 25%,#fff) 70%, transparent) !important;
  background-size:100% 4px !important;background-repeat:no-repeat !important;background-position:top left !important;
  -webkit-clip-path:inset(0 round 27px 27px 0 0) !important;clip-path:inset(0 round 27px 27px 0 0) !important}
/* Squircle ámbar de los encabezados + emojis */
.f7-icon-soft{background:linear-gradient(135deg, color-mix(in srgb,#d97706 16%,#fff), color-mix(in srgb,#d97706 7%,#fff));
  border:1.5px solid color-mix(in srgb,#d97706 35%,#fff);box-shadow:0 5px 12px color-mix(in srgb,#d97706 16%,transparent)}
.f7-emoji{font-size:23px;line-height:1;display:flex;align-items:center;justify-content:center}
/* Fichas de exportación con su botón real */
#root [class*="st-key-f7_xtile_"]{background:#fff !important;border:1px solid #d8e5f5 !important;border-radius:18px !important;
  padding:15px 14px 13px !important;box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06) !important;gap:12px !important}
#root .st-key-f7_xtile_pdf{--xc:#dc2626} #root .st-key-f7_xtile_docx{--xc:#2563eb}
#root .st-key-f7_xtile_excel{--xc:#16a34a} #root .st-key-f7_xtile_json{--xc:#7c3aed}
#root [class*="st-key-f7_xtile_"] [data-testid="stButton"] button,
#root [class*="st-key-f7_xtile_"] [data-testid="stDownloadButton"] button{
  color:var(--xc) !important;background:color-mix(in srgb,var(--xc) 8%,#fff) !important;border:1.5px solid color-mix(in srgb,var(--xc) 38%,#fff) !important;
  border-radius:12px !important;min-height:40px !important;font-size:12.5px !important;font-weight:800 !important;box-shadow:none !important}
#root [class*="st-key-f7_xtile_"] [data-testid="stButton"] button p,
#root [class*="st-key-f7_xtile_"] [data-testid="stDownloadButton"] button p{color:var(--xc) !important;font-weight:800 !important}
#root [class*="st-key-f7_xtile_"] button:disabled{opacity:.55 !important}
/* Streamlit pone margin-bottom:-16px al texto: el botón se montaba sobre la descripción */
#root [class*="st-key-f7_xtile_"] [data-testid="stMarkdownContainer"]{margin-bottom:0 !important}
#root [class*="st-key-f7_xtile_"] .f7-export-desc{min-height:2.7em}
/* Botones al pie de cada ficha: quedan alineados en las cuatro */
#root [class*="st-key-f7_xtile_"] > div[data-testid="stElementContainer"]:nth-child(2){margin-top:auto !important}
/* Botones principales en ámbar (acento F7) */
#root [data-testid="stButton"] button[kind="primary"],#root [data-testid="stDownloadButton"] button[kind="primary"]{
  background:linear-gradient(120deg,#d97706,#92400e) !important;border:none !important;color:#fff !important;
  box-shadow:0 10px 20px color-mix(in srgb,#d97706 32%,transparent), inset 0 1px 0 rgba(255,255,255,.28) !important}
#root [data-testid="stButton"] button[kind="primary"] p,#root [data-testid="stDownloadButton"] button[kind="primary"] p{color:#fff !important}
/* Parejas de cards y fichas: misma altura (stColumn es display:block por defecto) */
#root div[data-testid="stColumn"]:has(> div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > :is([class*="st-key-f7_card_"],.st-key-f7_save_section,[class*="st-key-f7_xtile_"])){
  display:flex !important;flex-direction:column !important}
#root div[data-testid="stColumn"]:has(> div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > :is([class*="st-key-f7_card_"],.st-key-f7_save_section,[class*="st-key-f7_xtile_"])) > div[data-testid="stVerticalBlock"]{
  flex:1 1 auto !important}
#root div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"]:has(> :is([class*="st-key-f7_card_"],.st-key-f7_save_section,[class*="st-key-f7_xtile_"])){
  flex:1 1 auto !important;display:flex !important;flex-direction:column !important}
#root div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > :is([class*="st-key-f7_card_"],.st-key-f7_save_section,[class*="st-key-f7_xtile_"]){
  flex:1 1 auto !important;height:auto !important;margin-bottom:0 !important}
#root div[data-testid="stHorizontalBlock"]:has(> div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] > div[data-testid="stLayoutWrapper"] > :is([class*="st-key-f7_card_"],.st-key-f7_save_section)){
  margin-bottom:16px !important}
/* Informe técnico: estado + qué usa */
.f7-sub{font-size:12px;font-weight:900;color:#0a2444;margin:12px 0 7px}
.f7-checks{display:flex;flex-direction:column;gap:7px}
.f7-checks div{display:flex;gap:9px;align-items:center;padding:9px 12px;border-radius:12px;font-size:12px;font-weight:800}
.f7-checks div.ok{background:#f0fdf4;border:1px solid #bbf7d0;color:#15803d}
.f7-checks div.pend{background:#fffbeb;border:1px solid #fde68a;color:#b45309}
.f7-inc{display:flex;flex-wrap:wrap;gap:8px}
.f7-inc span{padding:7px 12px;border-radius:999px;background:#fff;border:1.5px solid #fde68a;font-size:11.5px;font-weight:800;color:#92400e}
.f7-pill.ok,.f7-pill.warn{margin-top:8px}
/* GIS: formatos + plano */
.f7-gis-fmt{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:10px 0 6px}
.f7-gis-fmt span{text-align:center;padding:8px 6px;border-radius:12px;background:#fffbeb;border:1px solid #fde68a;font-size:11px;font-weight:700;color:#78350f}
.f7-fig{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:12px 14px;margin:8px 0;
  box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06)}
.f7-fig svg{display:block;width:100%;height:auto;max-width:640px;margin:0 auto}
.f7-gtitle{font-size:12px;font-weight:900;color:#0a2444;margin-bottom:7px}
/* Restaurar: una sola zona (la real) con borde ámbar; el bloque HTML queda como título */
.st-key-f7_save_section .f7-upload{border:none !important;background:none !important;padding:4px 0 0 !important;display:flex;align-items:center;gap:12px;text-align:left}
.st-key-f7_save_section .f7-upload .ui{margin:0 !important;width:44px;height:44px;font-size:21px}
.st-key-f7_save_section .f7-upload b{margin-top:0 !important}
.st-key-f7_save_section [data-testid="stFileUploaderDropzone"]{border:2px dashed color-mix(in srgb,#d97706 45%,#fff) !important;
  border-radius:16px !important;background:linear-gradient(180deg, color-mix(in srgb,#d97706 6%,#fff), #fff) !important}
</style>
""",
    unsafe_allow_html=True,
)
render_dropdown_visibility_fix()


# -----------------------------------------------------------------------------
# Carga de configuración y contexto original
# -----------------------------------------------------------------------------
config = cargar_config()
project_context = get_project_context(config)
report_context = get_report_context(config)

runtime_context = st.session_state.get(RUNTIME_CONTEXT_STATE_KEY)
if runtime_context:
    runtime_context = dict(runtime_context)

heavy_exports_ready = False
heavy_exports_stale = False
cached_heavy_exports = None
basic_bundle = None
informe_tecnico_pdf_artifact = None
informe_tecnico_docx_artifact = None
informe_tecnico_meta = {}
BASIC_BUNDLE_STATE_KEY = "f7_basic_bundle_cache"

if runtime_context:
    # Excel, Excel PRO, CSV y JSON solo se recalculan si cambian los datos del proyecto.
    heavy_export_signature = build_export_signature(config, runtime_context)
    _bundle_cache = st.session_state.get(BASIC_BUNDLE_STATE_KEY)
    if _bundle_cache and _bundle_cache.get("signature") == heavy_export_signature:
        basic_bundle = _bundle_cache["bundle"]
    else:
        basic_bundle = build_basic_export_bundle(config, runtime_context)
        st.session_state[BASIC_BUNDLE_STATE_KEY] = {"signature": heavy_export_signature, "bundle": basic_bundle}
    cached_heavy_exports = st.session_state.get(HEAVY_EXPORT_STATE_KEY)
    heavy_exports_ready = bool(cached_heavy_exports and cached_heavy_exports.get("signature") == heavy_export_signature)
    heavy_exports_stale = bool(cached_heavy_exports and cached_heavy_exports.get("signature") != heavy_export_signature)

    informe_tecnico_signature = build_informe_tecnico_signature(config, runtime_context)
    informe_tecnico_pdf_artifact = st.session_state.get(INFORME_TECNICO_PDF_STATE_KEY)
    informe_tecnico_docx_artifact = st.session_state.get(INFORME_TECNICO_DOCX_STATE_KEY)
    informe_tecnico_meta = st.session_state.get(INFORME_TECNICO_META_STATE_KEY, {})

    if informe_tecnico_pdf_artifact and informe_tecnico_pdf_artifact.get("source_signature") != informe_tecnico_signature:
        st.session_state[INFORME_TECNICO_PDF_STATE_KEY] = None
        informe_tecnico_pdf_artifact = None
    if informe_tecnico_docx_artifact and informe_tecnico_docx_artifact.get("source_signature") != informe_tecnico_signature:
        st.session_state[INFORME_TECNICO_DOCX_STATE_KEY] = None
        informe_tecnico_docx_artifact = None
    if informe_tecnico_meta and informe_tecnico_meta.get("source_signature") != informe_tecnico_signature:
        st.session_state[INFORME_TECNICO_META_STATE_KEY] = {}
        informe_tecnico_meta = {}
else:
    heavy_export_signature = None
    informe_tecnico_signature = None

# Datos para KPIs
unidad = str(config.get("f5_moneda_visualizacion") or config.get("f5_unidad_monetaria") or "USD")
bruto = config.get("f5_aep_bruta_total_mwh")
neto = config.get("f5_aep_neta_total_mwh")
lcoe_kwh = config.get("f5_lcoe_display_kwh") or ((runtime_context or {}).get("economics", {}).get("lcoe_display_kwh"))
lcoe_mwh = config.get("f5_lcoe_display_mwh") or ((runtime_context or {}).get("economics", {}).get("lcoe_display_mwh"))
fpb = config.get("f5_factor_planta_bruto_pct")
fpn = config.get("f5_factor_planta_neto_pct")
potencia_instalada = config.get("f5_potencia_instalada_mw") or ((runtime_context or {}).get("economics", {}).get("base_metrics", {}).get("potencia_instalada_mw"))
capex_total = config.get("f5_capex_total_display") or ((runtime_context or {}).get("economics", {}).get("capex_total_display")) or config.get("f5_capex_total") or ((runtime_context or {}).get("economics", {}).get("capex_total"))
opex_total = config.get("f5_opex_total_anual_display") or ((runtime_context or {}).get("economics", {}).get("opex_total_anual_display")) or config.get("f5_opex_total_anual") or ((runtime_context or {}).get("economics", {}).get("opex_total_anual"))
vp_costos = config.get("f5_vp_costos_display") or ((runtime_context or {}).get("economics", {}).get("vp_costos_display")) or config.get("f5_vp_costos") or ((runtime_context or {}).get("economics", {}).get("vp_costos"))
enriched_label = "Listos" if heavy_exports_ready else ("Desactualizados" if heavy_exports_stale else "Pendientes")
lcoe_sub = format_lcoe_value(lcoe_mwh, unidad, "MWh") if _has_value(lcoe_mwh) else ""


# =============================================================================
# HERO
# =============================================================================
with st.container(border=True, key="f7_card_header"):
    st.markdown(
        f"""
<div class="hero-card">
    <svg class="f7-wind" viewBox="0 0 600 190" preserveAspectRatio="none"><path d="M0 42 Q150 24 300 44 T600 34"/><path d="M0 100 Q180 82 340 102 T600 92"/><path d="M0 156 Q140 142 300 158 T600 150"/></svg>
    <div class="hero-row">
        <div class="hero-icon">📦</div>
        <div class="hero-text">
            <div class="fase-hero-title">Fase 7 &middot; Exportar y guardar</div>
            <div class="fase-hero-subtitle">Guardado final del proyecto y exportaci&oacute;n de resultados e informes generados en Fase 5.</div>
        </div>
        <div class="hero-pills">
            <div class="hpill"><b>4 tipos</b><span>Reportes</span></div>
            <div class="hpill"><b>{'Listo' if st.session_state.get('f7_bankable_result') else 'Pendiente'}</b><span>Bankable</span></div>
            <div class="hpill"><b>KML+ZIP</b><span>GIS</span></div>
        </div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# RESUMEN EJECUTIVO DEL ESCENARIO ACTUAL
# =============================================================================
def _kpi_tile(label, value, icon="chart", sub="", color="#2563eb", size=22):
    return (
        f'<div class="f7-kpi-card" style="--kc:{color}">'
        f'<div class="f7-kpi-icon">{_f7_icono(icon, size, color)}</div>'
        f'<div><div class="f7-kpi-label">{_escape(label)}</div>'
        f'<div class="f7-kpi-value">{_escape(_es(value))}</div>'
        f'<div class="f7-kpi-sub">{_escape(_es(sub))}</div></div></div>'
    )


with st.container(border=True, key="f7_card_exec_summary"):
    _section_header(
        "Resumen ejecutivo del escenario actual",
        "Indicadores clave antes de exportar",
        "📊",
        "#d97706",
    )
    main_kpis = [
        _kpi_tile("Método", str(config.get("f5_metodo_detalle") or config.get("f5_modo_estadistico") or "N/D"), "🧮", "principal", "#2563eb"),
        _kpi_tile("AEP bruta", _fmt_float(bruto, 0, " MWh"), "⚡", "", "#7c3aed"),
        _kpi_tile("AEP neta", _fmt_float(neto, 0, " MWh"), "🔋", "", "#16a34a"),
        _kpi_tile("LCOE", format_lcoe_value(lcoe_kwh, unidad, "kWh") if _has_value(lcoe_kwh) else "N/D", "📉", lcoe_sub, "#16a34a"),
        _kpi_tile("Turbinas", str(config.get("f5_n_turbinas") or config.get("f4_num_turbinas") or "N/D"), "🌀", "", "#94a3b8"),
        _kpi_tile("Exportes enriquecidos", enriched_label, "📦", "", "#16a34a" if heavy_exports_ready else "#d97706"),
    ]
    st.markdown(f'<div class="f7-kpi-grid">{"".join(main_kpis)}</div>', unsafe_allow_html=True)


# =============================================================================
# RESUMEN DEL ESCENARIO ACTUAL (financiero y de planta)
# =============================================================================
def _summary_tile(label, value, icon="chart", color="#2563eb", size=22):
    return (
        f'<div class="f7-summary-card" style="--kc:{color}">'
        f'<div class="f7-sc-icon">{_f7_icono(icon, size, color)}</div>'
        f'<div><div class="f7-summary-label">{_escape(label)}</div>'
        f'<div class="f7-summary-value">{_escape(_es(value))}</div></div></div>'
    )


with st.container(border=True, key="f7_card_scenario"):
    _section_header(
        "Resumen del escenario actual",
        "Estado financiero y de planta",
        "📋",
        "#d97706",
    )
    summary_cards = [
        _summary_tile("FP bruto", _fmt_float(fpb, 1, " %"), "📊", "#2563eb"),
        _summary_tile("FP neto", _fmt_float(fpn, 1, " %"), "📈", "#16a34a"),
        _summary_tile("Potencia", _fmt_float(potencia_instalada, 1, " MW"), "🏭", "#7c3aed"),
        _summary_tile("CAPEX", _f7_money(capex_total, unidad), "🏗️", "#d97706"),
        _summary_tile("OPEX anual", _f7_money(opex_total, unidad), "🧾", "#d97706"),
        _summary_tile("VP costos", _f7_money(vp_costos, unidad), "💰", "#94a3b8"),
    ]
    st.markdown(f'<div class="f7-summary-grid">{"".join(summary_cards)}</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
<div class="f7-banner info">
    <span class="bx">🗂️</span>
    Modo base: {_escape(config.get('f5_moneda_base') or 'USD')} · moneda de visualización: {_escape(unidad)} · tasa COP: {_es(format(float(config.get('f5_fx_rate_cop_per_usd') or 0), ',.0f'))} · Última actualización: {_escape(config.get('f5_fx_timestamp') or 'manual')}
</div>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# EXPORTACIÓN DE RESULTADOS
# =============================================================================
with st.container(border=True, key="f7_card_exports"):
    _section_header(
        "Exportación de resultados",
        "Reportes con los resultados de Fase 5.",
        "📤",
        "#d97706",
    )

    btn_disabled = not (runtime_context and basic_bundle)

    if btn_disabled:
        _f5_results_in_config = (
            config.get("f5_aep_bruta_total_mwh") is not None
            and config.get("f5_aep_neta_total_mwh") is not None
        )
        _msg = (
            "Los resultados existen en la base del proyecto pero esta sesión aún no "
            "los ha cargado. Pulse el botón para regenerar el cálculo de Fase 5 "
            "(toma unos segundos) y volver a Fase 7 con las exportaciones activas."
            if _f5_results_in_config
            else "Primero ejecute el cálculo en Fase 5 (botón «Aplicar configuración»). "
                 "Luego regrese a Fase 7 y las exportaciones quedarán habilitadas."
        )
        st.markdown(
            f"""<div class="f7-banner warn"><span class="bx">⚠️</span>Si cambió datos, regrese a Fase 5 y reactive las exportaciones para refrescar el contexto</div>""",
            unsafe_allow_html=True,
        )

    # Fichas de exportación: la ficha y su botón REAL van en la misma tarjeta (sin fila duplicada).
    def _f7_tile_head(emoji, tipo, nombre, desc):
        st.markdown(
            f'<div class="f7-export-top"><div class="f7-export-icon">{emoji}</div><div>'
            f'<div class="f7-export-type">{tipo}</div><div class="f7-export-name">{nombre}</div>'
            f'<div class="f7-export-desc">{desc}</div></div></div>',
            unsafe_allow_html=True,
        )

    exp1, exp2, exp3, exp4 = st.columns(4, gap="medium")
    nombre_archivos = (runtime_context or {}).get("project_name_default") or config.get("project_name") or "proyecto"
    _MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    _MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def _generar_informe_tecnico():
        """El informe técnico se genera una sola vez en los dos formatos (PDF + Word)."""
        with st.spinner("Generando el informe técnico (PDF + Word)…"):
            outputs = generate_informe_tecnico_exports(config, runtime_context)
            outputs["pdf"]["source_signature"] = informe_tecnico_signature
            outputs["docx"]["source_signature"] = informe_tecnico_signature
            st.session_state[INFORME_TECNICO_PDF_STATE_KEY] = outputs["pdf"]
            st.session_state[INFORME_TECNICO_DOCX_STATE_KEY] = outputs["docx"]
            st.session_state[INFORME_TECNICO_META_STATE_KEY] = {"source_signature": informe_tecnico_signature, **outputs["meta"]}
        st.rerun()

    pdf_ok = bool(informe_tecnico_pdf_artifact and informe_tecnico_pdf_artifact.get("success"))
    docx_ok = bool(informe_tecnico_docx_artifact and informe_tecnico_docx_artifact.get("success"))

    with exp1:
        with st.container(key="f7_xtile_pdf"):
            _f7_tile_head("📕", "Informe PDF", "Técnico", "Informe técnico completo. Se genera junto con el Word.")
            if pdf_ok and not btn_disabled:
                st.download_button("📄 Descargar PDF", data=informe_tecnico_pdf_artifact["pdf_bytes"], file_name=informe_tecnico_pdf_artifact.get("file_name", "informe_tecnico.pdf"), mime="application/pdf", use_container_width=True, icon=":material/download:")
            elif st.button("📄 Generar PDF", key="fase7_generar_informe_tecnico", use_container_width=True, icon=":material/play_arrow:", disabled=btn_disabled):
                _generar_informe_tecnico()
            if informe_tecnico_pdf_artifact and not pdf_ok and informe_tecnico_pdf_artifact.get("message"):
                st.markdown(f'<div class="f7-banner warn"><span class="bx">⚠️</span>{_escape(informe_tecnico_pdf_artifact["message"])}</div>', unsafe_allow_html=True)

    with exp2:
        with st.container(key="f7_xtile_docx"):
            _f7_tile_head("📘", "Informe Word", "Técnico", "El mismo informe, editable. Se genera junto con el PDF.")
            if docx_ok and not btn_disabled:
                st.download_button("📝 Descargar Word", data=informe_tecnico_docx_artifact["docx_bytes"], file_name=informe_tecnico_docx_artifact.get("file_name", "informe_tecnico.docx"), mime=_MIME_DOCX, use_container_width=True, icon=":material/download:")
            elif st.button("📝 Generar Word", key="fase7_generar_informe_word", use_container_width=True, icon=":material/play_arrow:", disabled=btn_disabled):
                _generar_informe_tecnico()

    with exp3:
        with st.container(key="f7_xtile_excel"):
            _f7_tile_head("📗", "Excel", "Datos y PRO", "Datos: tablas para trabajar. PRO: informe completo con gráficas.")
            excel_data = basic_bundle["excel_bytes"] if not btn_disabled and basic_bundle else b""
            excel_pro_data = (basic_bundle.get("excel_pro_bytes") or b"") if not btn_disabled and basic_bundle else b""
            st.download_button("📊 Excel de datos (5 hojas)", data=excel_data, file_name=nombre_archivo_proyecto(nombre_archivos, "datos", "xlsx"), mime=_MIME_XLSX, use_container_width=True, disabled=btn_disabled, key="fase7_dl_excel", help="Tablas de resultados de la Fase 5 para trabajar los datos: resumen, pérdidas, energía por sector, metadatos y manifiesto.")
            st.download_button("⭐ Excel PRO (17 hojas)", data=excel_pro_data, file_name=nombre_archivo_proyecto(nombre_archivos, "excel_pro", "xlsx"), mime=_MIME_XLSX, use_container_width=True, disabled=btn_disabled or not excel_pro_data, key="fase7_dl_excel_pro", help="Informe completo en Excel, con gráficas: portada, resumen ejecutivo, sitio y turbina, recurso eólico, curva de potencia, energía por sector, pérdidas, AEP por turbina, incertidumbre, economía, flujo de caja, sensibilidad, idoneidad IEC, supuestos, glosario, perfil diurno y estacional, y manifiesto.")

    with exp4:
        with st.container(key="f7_xtile_json"):
            _f7_tile_head("🗄️", "Datos JSON", "Resultados", "Resultados y datos del proyecto (el respaldo está en «Guardado final»).")
            json_data = basic_bundle["report_manifest_json"].encode("utf-8") if not btn_disabled and basic_bundle else b""
            st.download_button("🧾 Exportar JSON", data=json_data, file_name=nombre_archivo_proyecto(nombre_archivos, "resultados", "json"), mime="application/json", use_container_width=True, icon=":material/download:", disabled=btn_disabled)

    # Link to Fase 5
    if btn_disabled:
        _go_col_btn, _go_col_right = st.columns([1.1, 3])
        with _go_col_btn:
            if st.button(
                "Ir a Fase 5 y activar exportaciones",
                key="fase7_goto_fase5_activar",
                use_container_width=True,
                icon=":material/play_arrow:",
            ):
                try:
                    st.switch_page("pages/5_Fase_5_AEP_bruta_y_neta.py")
                except Exception:
                    st.info("Abra la pestaña «Fase 5 · AEP bruta y neta» en la barra lateral.")

    # Extra exports in expander
    if not btn_disabled:
        if informe_tecnico_meta.get("master_source_used"):
            st.info(f"Base canónica activa: `{informe_tecnico_meta.get('master_source_name', 'informe_tecnico.docx')}`")
        elif informe_tecnico_meta.get("master_warning"):
            st.warning(informe_tecnico_meta["master_warning"])

        with st.expander("Exportaciones adicionales: CSV sectorial, LaTeX y figuras"):
            a1, a2 = st.columns(2)
            with a1:
                st.download_button("Descargar CSV sectorial", data=basic_bundle["csv_bytes"], file_name="fase5_resultados_sectoriales.csv", mime="text/csv", use_container_width=True, icon=":material/download:")
            with a2:
                st.download_button("Descargar esqueleto LaTeX (.tex)", data=basic_bundle["latex_skeleton"].encode("utf-8"), file_name="fase5_esqueleto_reporte.tex", mime="application/x-tex", use_container_width=True, icon=":material/download:")

            if heavy_exports_stale:
                st.info("Las exportaciones enriquecidas fueron generadas con una configuración anterior.")
            elif heavy_exports_ready:
                st.success("Las exportaciones enriquecidas están listas.")
            else:
                st.info("Las exportaciones enriquecidas aún no han sido preparadas.")

            if st.button("Preparar o actualizar exportaciones enriquecidas", key="fase7_preparar_exportes", use_container_width=True, icon=":material/refresh:"):
                with st.spinner("Preparando figuras exportables y pack de anexos..."):
                    export_state = generate_heavy_export_artifacts(config, runtime_context, basic_bundle)
                    export_state["signature"] = heavy_export_signature
                    st.session_state[HEAVY_EXPORT_STATE_KEY] = export_state
                st.rerun()

            cached_heavy_exports = st.session_state.get(HEAVY_EXPORT_STATE_KEY)
            if cached_heavy_exports and cached_heavy_exports.get("signature") == heavy_export_signature:
                deduped_artifacts = dedupe_figure_export_artifacts(cached_heavy_exports.get("figure_export_artifacts"))
                figuras_export_df = pd.DataFrame([{"id": item.get("id", ""), "titulo": item.get("title", ""), "estado": item.get("status", ""), "formato": item.get("export_format", ""), "archivo": item.get("file_name", "")} for item in deduped_artifacts])
                st.dataframe(figuras_export_df, use_container_width=True)
                for idx, item in enumerate(deduped_artifacts):
                    path = item.get("path")
                    if not path:
                        continue
                    content = cached_heavy_exports.get("combined_figure_files", {}).get(path)
                    if content is None:
                        continue
                    st.download_button(f"Descargar {item.get('title', 'figura')} ({str(item.get('export_format', '')).upper()})", data=content, file_name=item.get("file_name", "figura_exportada"), mime=item.get("mime_type", "application/octet-stream"), key=build_figure_download_key(item, idx), use_container_width=True, icon=":material/download:")

                general_appendix_pack = cached_heavy_exports.get("general_appendix_pack", {"appendix_entries": [], "table_entries": []})
                for entry in general_appendix_pack.get("appendix_entries", []):
                    st.markdown(f"- `{entry['path']}`")
                for entry in general_appendix_pack.get("table_entries", []):
                    st.markdown(f"- `{entry['path']}`")
                st.download_button("Descargar pack de anexos LaTeX", data=cached_heavy_exports.get("general_appendix_pack_zip", b""), file_name="fase5_pack_anexos_general.zip", mime="application/zip", use_container_width=True, icon=":material/download:")


# =============================================================================
# INFORME TÉCNICO + REPORTE BANKABLE (2 columnas)
# =============================================================================
col_tecnico, col_bankable = st.columns(2, gap="medium")

with col_tecnico:
    with st.container(border=True, key="f7_card_informe_tecnico"):
        _section_header(
            "Informe técnico",
            "PDF/Word con figuras y metodología",
            "📑",
            "#d97706",
        )
        st.markdown(
            '<div class="f7-banner info"><span class="bx">⬆️</span>Un solo informe en dos formatos: se genera y se '
            'descarga en las fichas «Informe PDF» e «Informe Word» de «Exportación de resultados».</div>',
            unsafe_allow_html=True,
        )
        _gen_ok = bool(pdf_ok or docx_ok)
        _checks = (
            ("Resultados de Fase 5 cargados en esta sesión", not btn_disabled),
            ("Informe generado en esta sesión (PDF + Word)", _gen_ok),
        )
        st.markdown(
            '<div class="f7-sub">✅ Estado</div><div class="f7-checks">'
            + "".join(f'<div class="{"ok" if ok else "pend"}"><span>{"✅" if ok else "⏳"}</span>{_escape(t)}</div>' for t, ok in _checks)
            + '</div><div class="f7-sub">📑 Qué usa el informe</div><div class="f7-inc">'
            + "".join(f"<span>{e} {t}</span>" for e, t in (
                ("⚡", "Resultados de la Fase 5"), ("🖼️", "Figuras"), ("📐", "Metodología"), ("📝", "Editable en Word")))
            + "</div>",
            unsafe_allow_html=True,
        )
        if btn_disabled:
            st.markdown('<div class="f7-banner warn"><span class="bx">⚠️</span>Active las exportaciones en la Fase 5 para generar el informe.</div>',
                        unsafe_allow_html=True)

with col_bankable:
    with st.container(border=True, key="f7_card_bankable"):
        _section_header(
            "Reporte BANKABLE",
            "Para banca: P50/P90, IEC 61400-15-2, riesgos",
            "🏛️",
            "#d97706",
        )

        from i18n_paises import (
            get_country_profile,
            inferir_pais_por_coordenadas,
            listar_idiomas,
            listar_paises,
        )

        pais_sitio = inferir_pais_por_coordenadas(config.get("nasa_lat"), config.get("nasa_lon"))
        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            bk_project = st.text_input("Proyecto", value=config.get("f7_bankable_project_name") or config.get("project_name") or "Proyecto eólico", key="f7_bk_project")
            paises_options = listar_paises()
            pais_labels = [f"{c} — {n}" for c, n in paises_options]
            pais_default_code = config.get("f7_country_code") or pais_sitio or "OTRO"
            idx_pais = next((i for i, (c, _) in enumerate(paises_options) if c == pais_default_code), len(paises_options) - 1)
            pais_sel_label = st.selectbox("País", pais_labels, index=idx_pais, key="f7_country_label")
            pais_sel_code = pais_sel_label.split(" — ")[0]
        with col_b2:
            bk_autor = st.text_input("Autor", value=config.get("f7_bankable_autor", ""), key="f7_bk_autor")
            idiomas_options = listar_idiomas()
            idioma_labels = [f"{c} — {n}" for c, n in idiomas_options]
            idioma_default = config.get("f7_report_lang", "es")
            idx_idioma = next((i for i, (c, _) in enumerate(idiomas_options) if c == idioma_default), 0)
            idioma_sel_label = st.selectbox("Idioma", idioma_labels, index=idx_idioma, key="f7_report_lang_label")
            idioma_sel_code = idioma_sel_label.split(" — ")[0]
        with col_b3:
            bk_cliente = st.text_input("Cliente", value=config.get("f7_bankable_cliente", ""), key="f7_bk_cliente")
            logo_upload = st.file_uploader("Logo", type=["png", "jpg", "jpeg"], key="f7_bk_logo", help="subir imagen…")

        perfil_pais = get_country_profile(pais_sel_code)
        if pais_sitio and pais_sitio != pais_sel_code:
            st.markdown(
                f'<div class="f7-banner warn"><span class="bx">⚠️</span>Las coordenadas del sitio están en '
                f'{_escape(get_country_profile(pais_sitio)["nombre"])}, pero el informe usará {_escape(perfil_pais["nombre"])} '
                f'(marco regulatorio, WACC y límites de ruido de ese país).</div>',
                unsafe_allow_html=True,
            )

        resultado_bk = st.session_state.get("f7_bankable_result") or {}
        btn_bk1, btn_bk2, btn_bk3 = st.columns([1.4, 1, 1], gap="small")
        with btn_bk1:
            if st.button("🏦 Generar reporte bankable", key="f7_btn_gen_bankable", use_container_width=True, type="primary"):
                try:
                    from reportes.bankable import construir_contexto_bankable, generar_reporte_bankable
                    with st.spinner(f"Generando el reporte bankable en {idioma_sel_code.upper()} (Word + PDF)…"):
                        ctx_bk = construir_contexto_bankable(
                            config=config,
                            runtime_context=runtime_context,
                            project_metadata={
                                "project_name": bk_project,
                                "autor": bk_autor,
                                "cliente": bk_cliente,
                                "country_code": pais_sel_code,
                            },
                        )
                        logo_bytes = logo_upload.getvalue() if logo_upload else None
                        resultado_bk = generar_reporte_bankable(ctx_bk, lang=idioma_sel_code, logo_bytes=logo_bytes, exportar_pdf=True)
                        resultado_bk.update({"lang": idioma_sel_code, "pais": perfil_pais["nombre"]})
                        guardar_config_values({
                            "f7_bankable_project_name": bk_project,
                            "f7_bankable_autor": bk_autor,
                            "f7_bankable_cliente": bk_cliente,
                            "f7_country_code": pais_sel_code,
                            "f7_report_lang": idioma_sel_code,
                        })
                        st.session_state["f7_bankable_result"] = resultado_bk
                except Exception as exc:
                    st.error(f"Error generando el reporte: {exc}")
        _base_bk = resultado_bk.get("nombre_base") or "reporte_bankable"
        with btn_bk2:
            st.download_button(
                "📥 Word",
                data=resultado_bk.get("docx_bytes") or b"",
                file_name=f"{_base_bk}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="f7_dl_bankable",
                disabled=not resultado_bk.get("docx_bytes"),
            )
        with btn_bk3:
            st.download_button(
                "📥 PDF",
                data=resultado_bk.get("pdf_bytes") or b"",
                file_name=f"{_base_bk}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="f7_dl_bankable_pdf",
                disabled=not resultado_bk.get("pdf_bytes"),
            )
        if resultado_bk:
            _detalle = f"Último reporte: {str(resultado_bk.get('lang', '')).upper()} · {resultado_bk.get('pais', '')}."
            if not resultado_bk.get("con_word"):
                _detalle += " " + str(resultado_bk.get("mensaje") or "")
            st.caption(_detalle)


# =============================================================================
# EXPORTACIÓN GIS + GUARDADO FINAL (2 columnas)
# =============================================================================
col_gis, col_save = st.columns(2, gap="medium")

with col_gis:
    with st.container(border=True, key="f7_card_gis_export"):
        _section_header(
            "Exportación GIS",
            "Lleve el parque a Google Earth / QGIS",
            "🌍",
        )

        try:
            from db import cargar_layout_parque
            from reportes.gis_export import (
                exportar_csv_coords,
                exportar_geojson_layout,
                exportar_kml_layout,
                exportar_zip_paquete_gis,
            )

            df_layout_gis = cargar_layout_parque()
            lat_site_gis = float(config.get("nasa_lat") or 0)
            lon_site_gis = float(config.get("nasa_lon") or 0)

            if len(df_layout_gis) == 0 or abs(lat_site_gis) < 0.01:
                st.info("Necesita layout del parque (Fase 4) + lat/lon del sitio (Fase 2) configurados.")
            else:
                nombre_gis = (config.get("project_name") or "WindFarm").replace(" ", "_")
                diametro_gis = float(config.get("diametro") or 100)
                h_hub_gis = float(config.get("f5_altura_deseada") or config.get("perfil_hhub") or 80)

                # Botones en línea (como en el diseño de referencia)
                gis_c1, gis_c2, gis_c3, gis_c4 = st.columns(4, gap="small")
                with gis_c1:
                    if st.button("🌐 KML", key="f7_btn_kml", use_container_width=True):
                        try:
                            kml = exportar_kml_layout(df_layout_gis, lat_site_gis, lon_site_gis,
                                                        nombre_parque=nombre_gis,
                                                        diametro_rotor=diametro_gis, altura_buje=h_hub_gis)
                            st.session_state["f7_kml_bytes"] = kml
                            st.success(f"KML: {len(kml)/1024:.1f} KB")
                        except Exception as exc:
                            st.error(f"KML error: {exc}")
                with gis_c2:
                    if st.button("🗺️ GeoJSON", key="f7_btn_geojson", use_container_width=True):
                        try:
                            gj = exportar_geojson_layout(df_layout_gis, lat_site_gis, lon_site_gis, nombre_gis,
                                                         diametro_rotor=diametro_gis, altura_buje=h_hub_gis)
                            st.session_state["f7_geojson_bytes"] = gj
                            st.success(f"GeoJSON: {len(gj)/1024:.1f} KB")
                        except Exception as exc:
                            st.error(f"GeoJSON error: {exc}")
                with gis_c3:
                    if st.button("📋 CSV coordenadas", key="f7_btn_csv_coords", use_container_width=True):
                        try:
                            csv_c = exportar_csv_coords(df_layout_gis, lat_site_gis, lon_site_gis,
                                                        diametro_rotor=diametro_gis, altura_buje=h_hub_gis)
                            st.session_state["f7_csv_coords_bytes"] = csv_c
                            st.success(f"CSV: {len(csv_c)/1024:.1f} KB")
                        except Exception as exc:
                            st.error(f"CSV error: {exc}")
                with gis_c4:
                    if st.button("🗜️ ZIP GIS completo", key="f7_btn_zip_gis", use_container_width=True, type="primary"):
                        try:
                            zip_b = exportar_zip_paquete_gis(df_layout_gis, lat_site_gis, lon_site_gis, nombre_gis,
                                                              diametro_rotor=diametro_gis, altura_buje=h_hub_gis)
                            st.session_state["f7_zip_gis_bytes"] = zip_b
                            st.success(f"ZIP: {len(zip_b)/1024:.1f} KB")
                        except Exception as exc:
                            st.error(f"ZIP error: {exc}")

                st.markdown(
                    '<div class="f7-gis-fmt"><span>🌐 <b>KML</b> · Google Earth</span><span>🗺️ <b>GeoJSON</b> · QGIS / web</span>'
                    '<span>📋 <b>CSV</b> · Excel</span><span>🗜️ <b>ZIP</b> · todo junto</span></div>',
                    unsafe_allow_html=True,
                )
                _plano = _f7_plano_svg(df_layout_gis)
                if _plano:
                    st.markdown(
                        f'<div class="f7-fig"><div class="f7-gtitle">🗺️ Layout que se exportará · {len(df_layout_gis)} turbinas '
                        f'· centro {_es(f"{lat_site_gis:.4f}")}, {_es(f"{lon_site_gis:.4f}")}</div>{_plano}</div>',
                        unsafe_allow_html=True,
                    )
                dl_cols = st.columns(2)
                with dl_cols[0]:
                    if st.session_state.get("f7_kml_bytes"):
                        st.download_button("⬇ .kml", data=st.session_state["f7_kml_bytes"],
                                           file_name=f"{nombre_gis}.kml", mime="application/vnd.google-earth.kml+xml",
                                           use_container_width=True, key="f7_dl_kml")
                    if st.session_state.get("f7_geojson_bytes"):
                        st.download_button("⬇ .geojson", data=st.session_state["f7_geojson_bytes"],
                                           file_name=f"{nombre_gis}.geojson", mime="application/geo+json",
                                           use_container_width=True, key="f7_dl_geojson")
                with dl_cols[1]:
                    if st.session_state.get("f7_csv_coords_bytes"):
                        st.download_button("⬇ coords.csv", data=st.session_state["f7_csv_coords_bytes"],
                                           file_name=f"{nombre_gis}_coords.csv", mime="text/csv",
                                           use_container_width=True, key="f7_dl_csv_coords")
                    if st.session_state.get("f7_zip_gis_bytes"):
                        st.download_button("⬇ paquete GIS .zip", data=st.session_state["f7_zip_gis_bytes"],
                                           file_name=f"{nombre_gis}_GIS.zip", mime="application/zip",
                                           use_container_width=True, key="f7_dl_zip_gis")
        except ImportError as ie:
            st.warning(f"GIS export requiere `simplekml`. Instalar: `pip install simplekml`. Error: {ie}")


with col_save:
    with st.container(border=True, key="f7_save_section"):
        _section_header(
            "Guardado final del proyecto",
            "Guarde en la base de datos o descargue el archivo del proyecto.",
            "💾",
        )

        nombre_proyecto = st.text_input(
            "Nombre del proyecto",
            value=str(config.get("project_name") or "Proyecto_eolico_1"),
        )

        if runtime_context:
            runtime_context["project_name_default"] = nombre_proyecto

        save_c1, save_c2 = st.columns(2, gap="medium")
        with save_c1:
            if st.button("💾 Guardar proyecto en la base de datos", use_container_width=True, type="primary"):
                try:
                    guardar_config_values({"project_name": nombre_proyecto})
                    guardar_proyecto(nombre_proyecto)
                    st.success(f"Proyecto '{nombre_proyecto}' guardado correctamente en la base de datos.")
                except Exception as e:
                    st.error(f"No pude guardar el proyecto: {e}")
        with save_c2:
            try:
                proyecto_json = exportar_proyecto_json_texto()
                st.download_button("📤 Descargar proyecto (.json)", data=proyecto_json.encode("utf-8"), file_name=f"{nombre_proyecto}.json", mime="application/json", use_container_width=True)
            except Exception as e:
                st.error(f"No pude preparar el archivo del proyecto: {e}")

        # Upload zone for restoring project
        st.markdown(
            """
<div class="f7-upload">
    <div class="ui">♻️</div>
    <b>Restaurar proyecto desde .json</b>
    <span>arrastre el archivo aquí o haga clic en Upload</span>
</div>
""",
            unsafe_allow_html=True,
        )

        uploaded_json = st.file_uploader(
            "Restaurar proyecto desde .json",
            type=["json"],
            key="f7_restore_upload",
            label_visibility="collapsed",
        )
        if uploaded_json is not None:
            try:
                import json
                from db import importar_proyecto_desde_json_texto
                raw = uploaded_json.getvalue().decode("utf-8")
                importar_proyecto_desde_json_texto(raw)
                st.success("Proyecto restaurado correctamente. Recargue la página para ver los datos actualizados.")
            except Exception as exc:
                st.error(f"Error restaurando proyecto: {exc}")

        st.markdown(
            '<div class="f7-banner ok"><span class="bx">✅</span>Todo lo guardado podrá restaurarse desde Inicio</div>',
            unsafe_allow_html=True,
        )
