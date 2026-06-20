import html

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


def _fmt_float(value, decimals=2, suffix="") -> str:
    if not _has_value(value):
        return "N/D"
    try:
        return f"{float(value):.{decimals}f}{suffix}"
    except Exception:
        return f"{value}{suffix}"


def _section_header(title: str, subtitle: str = "", icon: str = "chart", color: str = "#d97706") -> None:
    st.markdown(
        f"""
<div class="f7-section-header">
    <div class="f7-section-icon"><span class="f7-icon-soft">{_safe_icon(icon, 22, color)}</span></div>
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
.hero-card{position:relative;overflow:hidden;background:linear-gradient(180deg,#ffffff 0%,#f8fbff 100%);border:1px solid #cbd5e1;border-radius:20px;padding:22px 28px;margin-bottom:1rem;box-shadow:0 1px 4px rgba(15,23,42,.045);min-height:unset !important;height:auto !important}
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

if runtime_context:
    basic_bundle = build_basic_export_bundle(config, runtime_context)
    heavy_export_signature = build_export_signature(config, runtime_context, basic_bundle)
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
    <div class="hero-row">
        <div class="hero-icon">📦</div>
        <div>
            <div class="fase-hero-title">Fase 7 &middot; Exportar y guardar</div>
            <div class="fase-hero-subtitle">Guardado final del proyecto y exportaci&oacute;n de resultados e informes generados en Fase 5.</div>
        </div>
        <div class="hero-pills">
            <div class="hpill"><b>4 tipos</b><span>Reportes</span></div>
            <div class="hpill"><b>{'Listo' if heavy_exports_ready else 'Pendiente'}</b><span>Bankable</span></div>
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
        f'<div class="f7-kpi-icon">{_safe_icon(icon, size, color)}</div>'
        f'<div><div class="f7-kpi-label">{_escape(label)}</div>'
        f'<div class="f7-kpi-value">{_escape(value)}</div>'
        f'<div class="f7-kpi-sub">{_escape(sub)}</div></div></div>'
    )


with st.container(border=True, key="f7_card_exec_summary"):
    _section_header(
        "Resumen ejecutivo del escenario actual",
        "Indicadores clave antes de exportar",
        "chart",
        "#d97706",
    )
    main_kpis = [
        _kpi_tile("Método", str(config.get("f5_metodo_detalle") or config.get("f5_modo_estadistico") or "N/D"), "turbine-simple", "principal", "#8b5cf6"),
        _kpi_tile("AEP bruta", _fmt_float(bruto, 0, " MWh"), "bolt", "", "#7c3aed"),
        _kpi_tile("AEP neta", _fmt_float(neto, 0, " MWh"), "bolt", "", "#16a34a"),
        _kpi_tile("LCOE", format_lcoe_value(lcoe_kwh, unidad, "kWh") if _has_value(lcoe_kwh) else "N/D", "dollar", lcoe_sub, "#16a34a"),
        _kpi_tile("Turbinas", str(config.get("f5_n_turbinas") or config.get("f4_num_turbinas") or "N/D"), "turbine-simple", "", "#94a3b8"),
        _kpi_tile("Exportes enriquecidos", enriched_label, "file-text", "", "#16a34a"),
    ]
    st.markdown(f'<div class="f7-kpi-grid">{"".join(main_kpis)}</div>', unsafe_allow_html=True)


# =============================================================================
# RESUMEN DEL ESCENARIO ACTUAL (financiero y de planta)
# =============================================================================
def _summary_tile(label, value, icon="chart", color="#2563eb", size=22):
    return (
        f'<div class="f7-summary-card" style="--kc:{color}">'
        f'<div class="f7-sc-icon">{_safe_icon(icon, size, color)}</div>'
        f'<div><div class="f7-summary-label">{_escape(label)}</div>'
        f'<div class="f7-summary-value">{_escape(value)}</div></div></div>'
    )


with st.container(border=True, key="f7_card_scenario"):
    _section_header(
        "Resumen del escenario actual",
        "Estado financiero y de planta",
        "database",
        "#d97706",
    )
    summary_cards = [
        _summary_tile("FP bruto", _fmt_float(fpb, 1, " %"), "chart", "#2563eb"),
        _summary_tile("FP neto", _fmt_float(fpn, 1, " %"), "chart", "#16a34a"),
        _summary_tile("Potencia", _fmt_float(potencia_instalada, 1, " MW"), "turbine-simple", "#7c3aed"),
        _summary_tile("CAPEX", format_currency_amount(capex_total, unidad) if _has_value(capex_total) else "N/D", "dollar", "#d97706"),
        _summary_tile("OPEX anual", format_currency_amount(opex_total, unidad) if _has_value(opex_total) else "N/D", "dollar", "#d97706"),
        _summary_tile("VP costos", format_currency_amount(vp_costos, unidad) if _has_value(vp_costos) else "N/D", "dollar", "#94a3b8"),
    ]
    st.markdown(f'<div class="f7-summary-grid">{"".join(summary_cards)}</div>', unsafe_allow_html=True)

    st.markdown(
        f"""
<div class="f7-banner info">
    <span class="bx">🗂️</span>
    Modo base: {_escape(config.get('f5_moneda_base') or 'USD')} · moneda de visualización: {_escape(unidad)} · tasa COP: {float(config.get('f5_fx_rate_cop_per_usd') or 0):,.0f} · Última actualización: {_escape(config.get('f5_fx_timestamp') or 'manual')}
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
        "export",
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

    # Export tiles
    st.markdown(
        f"""
<div class="f7-export-grid">
    <div class="f7-export-tile" style="--xc:#dc2626">
        <div class="f7-export-top">
            <div class="f7-export-icon">📕</div>
            <div>
                <div class="f7-export-type">Informe PDF</div>
                <div class="f7-export-name">Ejecutivo</div>
                <div class="f7-export-desc">Resumen + análisis técnico.</div>
            </div>
        </div>
        <div class="xbtn">📄 Generar informe PDF</div>
    </div>
    <div class="f7-export-tile" style="--xc:#2563eb">
        <div class="f7-export-top">
            <div class="f7-export-icon">📘</div>
            <div>
                <div class="f7-export-type">Informe Word</div>
                <div class="f7-export-name">Técnico</div>
                <div class="f7-export-desc">Metodología completa, editable.</div>
            </div>
        </div>
        <div class="xbtn">📝 Exportar Word</div>
    </div>
    <div class="f7-export-tile" style="--xc:#16a34a">
        <div class="f7-export-top">
            <div class="f7-export-icon">📗</div>
            <div>
                <div class="f7-export-type">Excel / CSV</div>
                <div class="f7-export-name">Anexos</div>
                <div class="f7-export-desc">Tablas y datos detallados.</div>
            </div>
        </div>
        <div class="xbtn">📊 Exportar Excel/CSV</div>
    </div>
    <div class="f7-export-tile" style="--xc:#7c3aed">
        <div class="f7-export-top">
            <div class="f7-export-icon">🗄️</div>
            <div>
                <div class="f7-export-type">Datos JSON</div>
                <div class="f7-export-name">Proyecto</div>
                <div class="f7-export-desc">Respaldo completo de datos.</div>
            </div>
        </div>
        <div class="xbtn">🧾 Exportar JSON</div>
    </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # Functional buttons row
    exp1, exp2, exp3, exp4 = st.columns(4, gap="medium")

    with exp1:
        pdf_ok = bool(informe_tecnico_pdf_artifact and informe_tecnico_pdf_artifact.get("success"))
        if pdf_ok and not btn_disabled:
            st.download_button("📄 Generar informe PDF", data=informe_tecnico_pdf_artifact["pdf_bytes"], file_name=informe_tecnico_pdf_artifact.get("file_name", "informe_tecnico.pdf"), mime="application/pdf", use_container_width=True, icon=":material/download:", disabled=btn_disabled)
        else:
            if st.button("📄 Generar informe PDF", key="fase7_generar_informe_tecnico", use_container_width=True, icon=":material/download:", disabled=btn_disabled):
                with st.spinner("Generando informe técnico..."):
                    outputs = generate_informe_tecnico_exports(config, runtime_context)
                    outputs["pdf"]["source_signature"] = informe_tecnico_signature
                    outputs["docx"]["source_signature"] = informe_tecnico_signature
                    st.session_state[INFORME_TECNICO_PDF_STATE_KEY] = outputs["pdf"]
                    st.session_state[INFORME_TECNICO_DOCX_STATE_KEY] = outputs["docx"]
                    st.session_state[INFORME_TECNICO_META_STATE_KEY] = {"source_signature": informe_tecnico_signature, **outputs["meta"]}
                st.rerun()

    with exp2:
        docx_ok = bool(informe_tecnico_docx_artifact and informe_tecnico_docx_artifact.get("success"))
        if docx_ok and not btn_disabled:
            st.download_button("📝 Exportar Word", data=informe_tecnico_docx_artifact["docx_bytes"], file_name=informe_tecnico_docx_artifact.get("file_name", "informe_tecnico.docx"), mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True, icon=":material/download:", disabled=btn_disabled)
        else:
            st.download_button("📝 Exportar Word", data=b"", file_name="dummy.docx", use_container_width=True, icon=":material/download:", disabled=True, key="fase7_dummy_docx")

    with exp3:
        excel_data = basic_bundle["excel_bytes"] if not btn_disabled and basic_bundle else b""
        if st.download_button("📊 Exportar Excel/CSV", data=excel_data, file_name="fase5_resultados_completos.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, icon=":material/download:", disabled=btn_disabled):
            st.session_state["f7_show_excel_pro"] = True
        if st.session_state.get("f7_show_excel_pro"):
            excel_pro_data = basic_bundle.get("excel_pro_bytes", b"") if not btn_disabled and basic_bundle else b""
            pro_disabled = btn_disabled or not excel_pro_data
            st.download_button("Exportar Excel PRO (16 hojas bankable)", data=excel_pro_data, file_name="fase5_excel_PRO_bankable.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, icon=":material/star:", disabled=pro_disabled, help="Excel profesional estilo WAsP/WindPRO/OpenWind: Cover + ExecSummary + Site + WindRes + PowerCurve + Sectorial + LossWaterfall + PerWTG + Uncertainty P50/P90 + CAPEX/OPEX + CashFlow + Sensitivity + IEC SiteSuitability + Assumptions + Glossary + AuditManifest")

    with exp4:
        json_data = basic_bundle["report_manifest_json"].encode("utf-8") if not btn_disabled and basic_bundle else b""
        st.download_button("🧾 Exportar JSON", data=json_data, file_name="fase5_manifiesto_reporte.json", mime="application/json", use_container_width=True, icon=":material/download:", disabled=btn_disabled)

    # Link to Fase 5
    if btn_disabled:
        _go_col_left, _go_col_btn, _go_col_right = st.columns([1, 2, 1])
        with _go_col_btn:
            if st.button(
                "▶️ Ir a Fase 5 y activar exportaciones",
                key="fase7_goto_fase5_activar",
                use_container_width=True,
                type="primary",
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
            "document",
            "#d97706",
        )
        bc1, bc2 = st.columns(2, gap="small")
        with bc1:
            pdf_ok = bool(informe_tecnico_pdf_artifact and informe_tecnico_pdf_artifact.get("success"))
            if pdf_ok and not btn_disabled:
                st.download_button("📄 Generar informe técnico PDF", data=informe_tecnico_pdf_artifact["pdf_bytes"], file_name=informe_tecnico_pdf_artifact.get("file_name", "informe_tecnico.pdf"), mime="application/pdf", use_container_width=True, type="primary", key="f7_tecnico_pdf_dl")
            else:
                if st.button("📄 Generar informe técnico PDF", key="f7_tecnico_pdf_btn", use_container_width=True, type="primary", disabled=btn_disabled):
                    with st.spinner("Generando informe técnico..."):
                        outputs = generate_informe_tecnico_exports(config, runtime_context)
                        outputs["pdf"]["source_signature"] = informe_tecnico_signature
                        outputs["docx"]["source_signature"] = informe_tecnico_signature
                        st.session_state[INFORME_TECNICO_PDF_STATE_KEY] = outputs["pdf"]
                        st.session_state[INFORME_TECNICO_DOCX_STATE_KEY] = outputs["docx"]
                        st.session_state[INFORME_TECNICO_META_STATE_KEY] = {"source_signature": informe_tecnico_signature, **outputs["meta"]}
                    st.rerun()
        with bc2:
            docx_ok = bool(informe_tecnico_docx_artifact and informe_tecnico_docx_artifact.get("success"))
            if docx_ok and not btn_disabled:
                st.download_button("📝 Generar Word", data=informe_tecnico_docx_artifact["docx_bytes"], file_name=informe_tecnico_docx_artifact.get("file_name", "informe_tecnico.docx"), mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True, key="f7_tecnico_docx_dl")
            else:
                st.download_button("📝 Generar Word", data=b"", file_name="dummy.docx", use_container_width=True, disabled=True, key="f7_tecnico_dummy_docx")

        if informe_tecnico_meta.get("source_signature"):
            st.markdown('<div class="f7-pill ok">🟢 Última generación: hace 2 min</div>', unsafe_allow_html=True)

with col_bankable:
    with st.container(border=True, key="f7_card_bankable"):
        _section_header(
            "Reporte BANKABLE",
            "Para banca: P50/P90, IEC 61400-15-2, riesgos",
            "dollar",
            "#d97706",
        )

        from i18n_paises import get_country_profile, listar_idiomas, listar_paises

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            bk_project = st.text_input("Proyecto", value=config.get("project_name", "Wind Farm"), key="f7_bk_project")
            paises_options = listar_paises()
            pais_labels = [f"{c} — {n}" for c, n in paises_options]
            pais_default_code = config.get("f7_country_code", "OTRO")
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

        btn_bk1, btn_bk2 = st.columns(2, gap="small")
        with btn_bk1:
            if st.button("🏦 Generar reporte bankable", key="f7_btn_gen_bankable", use_container_width=True, type="primary"):
                try:
                    from reportes.bankable import construir_contexto_bankable, generar_reporte_bankable_bytes
                    with st.spinner(f"Generando reporte bankable en {idioma_sel_code.upper()}…"):
                        ctx_bk = construir_contexto_bankable(
                            config=config,
                            project_metadata={
                                "project_name": bk_project,
                                "autor": bk_autor,
                                "cliente": bk_cliente,
                                "country_code": pais_sel_code,
                                "country_nombre": perfil_pais["nombre"],
                            },
                        )
                        logo_bytes = logo_upload.getvalue() if logo_upload else None
                        docx_bytes = generar_reporte_bankable_bytes(ctx_bk, lang=idioma_sel_code, logo_bytes=logo_bytes)
                        guardar_config_values({
                            "f7_bankable_project_name": bk_project,
                            "f7_bankable_autor": bk_autor,
                            "f7_bankable_cliente": bk_cliente,
                            "f7_country_code": pais_sel_code,
                            "f7_report_lang": idioma_sel_code,
                        })
                        st.session_state["f7_bankable_docx_bytes"] = docx_bytes
                        st.success(f"Reporte generado ({len(docx_bytes)/1024:.1f} KB) en {idioma_sel_code.upper()} para {perfil_pais['nombre']}.")
                except Exception as exc:
                    st.error(f"Error generando reporte: {exc}")
        with btn_bk2:
            if st.session_state.get("f7_bankable_docx_bytes"):
                st.download_button(
                    "📥 Descargar DOCX",
                    data=st.session_state["f7_bankable_docx_bytes"],
                    file_name=f"{bk_project.replace(' ', '_')}_BANKABLE_{idioma_sel_code}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                    key="f7_dl_bankable",
                )


# =============================================================================
# EXPORTACIÓN GIS + GUARDADO FINAL (2 columnas)
# =============================================================================
col_gis, col_save = st.columns(2, gap="medium")

with col_gis:
    with st.container(border=True, key="f7_card_gis_export"):
        _section_header(
            "Exportación GIS",
            "Lleve el parque a Google Earth / QGIS",
            "globe",
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
                h_hub_gis = float(config.get("perfil_hhub") or 80)

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
                            gj = exportar_geojson_layout(df_layout_gis, lat_site_gis, lon_site_gis, nombre_gis)
                            st.session_state["f7_geojson_bytes"] = gj
                            st.success(f"GeoJSON: {len(gj)/1024:.1f} KB")
                        except Exception as exc:
                            st.error(f"GeoJSON error: {exc}")
                with gis_c3:
                    if st.button("📋 CSV coordenadas", key="f7_btn_csv_coords", use_container_width=True):
                        try:
                            csv_c = exportar_csv_coords(df_layout_gis, lat_site_gis, lon_site_gis)
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
            "database",
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
