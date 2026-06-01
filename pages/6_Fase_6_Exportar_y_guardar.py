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

st.set_page_config(page_title="Fase 6 · Exportar y guardar", layout="wide")

init_db()
render_sidebar_navigation("pages/6_Fase_6_Exportar_y_guardar.py")


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


def _kpi_card(label: str, value: str, icon: str = "chart", sub: str = "", tone: str = "blue") -> str:
    return (
        f'<div class="f6-kpi-card f6-tone-{tone}">'
        f'<div class="f6-kpi-icon">{_safe_icon(icon, 22)}</div>'
        '<div class="f6-kpi-text">'
        f'<div class="f6-kpi-label">{_escape(label)}</div>'
        f'<div class="f6-kpi-value">{_escape(value)}</div>'
        f'<div class="f6-kpi-sub">{_escape(sub)}</div>'
        '</div>'
        '</div>'
    )


def _section_header(title: str, subtitle: str = "", icon: str = "chart") -> None:
    st.markdown(
        f"""
<div class="f6-section-header">
    <div class="f6-section-icon">{_safe_icon(icon, 21)}</div>
    <div>
        <div class="f6-section-title">{_escape(title)}</div>
        {f'<div class="f6-section-subtitle">{_escape(subtitle)}</div>' if subtitle else ''}
    </div>
</div>
""",
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# CSS local
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%) !important;
}
.st-key-f6_card_header,.st-key-f6_card_main{
border-radius:18px !important;border: 1px solid #cbd5e1 !important;background:linear-gradient(180deg,#ffffff 0%,#f9fbff 100%) !important;box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;overflow:visible !important}
.st-key-f6_card_header{border:1.35px solid #cbd5e1 !important;border-radius:28px !important;background:linear-gradient(180deg,#ffffff 0%,#fbfdff 100%) !important}
.st-key-f6_card_header div[data-testid="stVerticalBlockBorderWrapper"]{background:#f8fbff !important;border:2px solid #aebcd2 !important;border-radius:18px !important;box-shadow:0 0 0 1px rgba(148,163,184,.35),0 6px 14px rgba(15,23,42,.13),0 2px 6px rgba(37,99,235,.10) !important;padding:1.05rem 1.05rem .95rem 1.05rem !important;min-height:unset !important;height:auto !important}
.st-key-f6_card_main div[data-testid="stVerticalBlockBorderWrapper"]{border:none !important;border-radius:18px !important;box-shadow:none !important;padding:.86rem .98rem 1rem .98rem !important}
.hero-card{position:relative;overflow:hidden;background:linear-gradient(180deg,#ffffff 0%,#f8fbff 100%);border: 1px solid #cbd5e1;border-radius:20px;padding:1.45rem 1.55rem 1.35rem 1.55rem;margin-bottom:1rem;box-shadow: 0 1px 4px rgba(15, 23, 42, 0.045);min-height:unset !important;height:auto !important}
.hero-card::after{content:"";position:absolute;right:-10px;top:-8px;width:260px;max-width:260px;height:140px;max-height:140px;background:radial-gradient(circle at 78% 25%,rgba(147,197,253,.28) 0 18px,transparent 19px),radial-gradient(circle at 56% 18%,rgba(191,219,254,.30) 0 26px,transparent 27px);opacity:.9;pointer-events:none}
.fase-hero-title{font-size:2.1rem;line-height:1.05;font-weight:800;color:#1e3a8a;margin:0 0 .28rem 0;position:relative;z-index:2}
.fase-hero-subtitle{color:#000000;font-size:.94rem;line-height:1.42;font-weight:400;max-width:74rem;margin:0;position:relative;z-index:2}
.f6-ref-summary-intro{display:flex;align-items:center;gap:14px;background:#f0f6ff;border:1px solid #c8dcfb;border-radius:16px;padding:.85rem 1rem;margin:0 0 10px 0;position:relative;z-index:1}
.f6-ref-summary-intro-title{font-size:15px;font-weight:900;color:#0a2444;display:flex;align-items:center;gap:12px}
.f6-ref-summary-intro-sub{font-size:12.5px;color:#000000;margin-top:3px}
.f6-ref-icon-soft{width:2.7rem;height:2.7rem;border-radius:999px;background:#eff6ff;border:1px solid #bfdbfe;color:#2563eb;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 8px 18px rgba(37,99,235,.08)}
.f6-ref-section-header{display:flex;align-items:center;gap:14px;margin:6px 0 16px}
.f6-ref-section-title{color:#0a2444;font-size:21px;font-weight:900;letter-spacing:-.02em}
.f6-ref-section-subtitle{color:#000000;font-size:13px;font-weight:400;margin-top:3px}
.f6-ref-kpi-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin:10px 0 12px}
.f6-ref-kpi-card{background:#ffffff;border:1px solid #c8dcfb;border-radius:24px;padding:16px 14px;box-shadow:0 8px 20px rgba(15,45,90,.06);display:flex;align-items:center;gap:14px;text-align:left;min-height:105px;overflow:hidden;transition:box-shadow .18s}
.f6-ref-kpi-card:hover{box-shadow:0 12px 28px rgba(15,45,90,.10)}
.f6-ref-kpi-icon{width:62px;height:62px;border-radius:999px;background:#eff6ff;border:1.5px solid #bfdbfe;display:inline-flex;align-items:center;justify-content:center;flex:0 0 62px;color:#2563eb;box-shadow:0 6px 16px rgba(37,99,235,.07)}
.f6-ref-kpi-label{color:#5b6bb0;font-size:15px;font-weight:900;margin-bottom:6px;text-transform:uppercase;letter-spacing:.03em}
.f6-ref-kpi-value{color:#0a2444;font-size:19px;font-weight:900;line-height:1.1;word-break:break-word;margin-bottom:4px}
.f6-ref-kpi-sub{color:#000000;font-size:10.5px;font-weight:400;margin-top:2px;min-height:14px}
.f6-ref-summary-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:10px 0 14px}
.f6-ref-summary-card{background:#ffffff;border:1px solid #c8dcfb;border-radius:18px;padding:16px 14px;display:flex;align-items:center;gap:12px;min-height:94px;box-shadow:0 4px 12px rgba(15,45,90,.04)}
.f6-ref-sc-icon{width:62px;height:62px;border-radius:999px;background:#eff6ff;border:1.5px solid #bfdbfe;display:inline-flex;align-items:center;justify-content:center;flex:0 0 62px;color:#2563eb;box-shadow:0 6px 16px rgba(37,99,235,.07)}
.f6-ref-summary-label{color:#5b6bb0;font-size:15px;font-weight:900;text-transform:uppercase;letter-spacing:.03em}
.f6-ref-summary-value{color:#0a2444;font-size:18px;font-weight:900;margin-top:5px;word-break:break-word;line-height:1.1}
.f6-ref-context-text{color:#000000;font-size:13px;font-weight:400;margin:0 0 12px 0;padding-top:4px}
.f6-ref-context-strip{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;background:#f0f6ff;border:1px solid #c8dcfb;border-radius:14px;padding:14px 18px;color:#000000;font-size:13px;font-weight:400;margin:0 0 16px}
.f6-ref-export-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:12px 0 0}
.f6-ref-export-card{background:#ffffff;border:1px solid #c8dcfb;border-radius:24px;padding:22px 20px 72px;box-shadow:0 8px 20px rgba(15,45,90,.06);display:flex;flex-direction:column;gap:12px;min-height:155px;overflow:hidden;transition:box-shadow .18s}
.f6-ref-export-card:hover{box-shadow:0 12px 28px rgba(15,45,90,.10)}
.f6-ref-export-top{display:flex;align-items:center;gap:16px}
.f6-ref-export-icon{width:66px;height:66px;border-radius:18px;display:inline-flex;align-items:center;justify-content:center;flex:0 0 66px;font-size:22px;font-weight:900}
.f6-ref-export-icon-pdf{background:#fef2f2;color:#dc2626;border:1px solid #fecaca}
.f6-ref-export-icon-word{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}
.f6-ref-export-icon-excel{background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0}
.f6-ref-export-icon-json{background:#f5f3ff;color:#7c3aed;border:1px solid #ddd6fe}
.f6-ref-export-title{color:#0a2444;font-size:15px;font-weight:900;margin-bottom:4px;line-height:1.2}
.f6-ref-export-desc{color:#000000;font-size:12px;font-weight:400;line-height:1.35}
.f6-ref-export-btn{display:block;width:100%;margin-top:auto;padding:12px 0;border-radius:14px;border:1.5px solid #bfdbfe;background:#f8fbff;color:#2563eb;font-size:13.5px;font-weight:800;text-align:center;cursor:pointer;transition:all .18s}
.f6-ref-export-btn:hover{background:#eff6ff;border-color:#2563eb}
.f6-ref-save-card{background:#ffffff;border:1px solid #c8dcfb;border-radius:22px;padding:24px 26px;box-shadow:0 8px 20px rgba(15,45,90,.06);margin-bottom:16px}
.f6-ref-save-title{color:#0a2444;font-size:18px;font-weight:900;margin-bottom:6px;display:flex;align-items:center;gap:10px}
.f6-ref-save-sub{color:#000000;font-size:13px;font-weight:400;margin-bottom:18px}
.f6-ref-alert{background:#fffbeb;border:1px solid #fde68a;color:#78350f;border-radius:16px;padding:14px 16px;font-weight:700;margin:12px 0 16px;font-size:13.5px}
.st-key-f6_card_exec_summary,.st-key-f6_card_scenario,.st-key-f6_card_exports,.st-key-f6_save_section,.st-key-f6_card_bankable,.st-key-f6_card_gis_export{border-radius:28px !important;border:1px solid #d9e8fb !important;background:#ffffff !important;box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;overflow:visible !important;margin-bottom:16px !important}
.st-key-f6_card_exec_summary div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_scenario div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_exports div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_save_section div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_bankable div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_gis_export div[data-testid="stVerticalBlockBorderWrapper"]{border:none !important;border-radius:28px !important;box-shadow:none !important;padding:1.1rem 1.2rem 1.1rem 1.2rem !important}
.st-key-f6_save_section [data-testid="stButton"]>button{background:#dc2626 !important;border-color:#dc2626 !important;color:#fff !important}
.st-key-f6_save_section [data-testid="stButton"]>button:hover{background:#b91c1c !important}
.st-key-f6_save_section [data-testid="stDownloadButton"]>button{background:#fff !important;border:1.5px solid #86b7ff !important;color:#2563eb !important}
div[data-testid="stButton"] > button,div[data-testid="stDownloadButton"] > button{border-radius:12px !important;min-height:42px !important;font-weight:800 !important}
div[data-testid="stTextInput"] input,div[data-testid="stSelectbox"] div[data-baseweb="select"] > div{background:#fff !important;border-color:#cfe2f7 !important;color:#0a2444 !important}
.st-key-f6_save_section [data-testid="stTextInput"]{margin-bottom:16px !important}
.st-key-f6_card_exports div[data-testid="stHorizontalBlock"]{margin-top:-52px;padding:0 12px;position:relative;z-index:10}
/* La fila del botón "Ir a Fase 5" NO debe heredar el margin-top negativo (ese
   -52px es para que los botones de descarga se monten sobre las tarjetas). Con
   el margen negativo, al hacer zoom 150% el texto de arriba envuelve en más
   líneas y el botón terminaba tapándolo. margin-top:0 lo deja fluir natural
   debajo del aviso → estable en 100% y 150%. */
.st-key-f6_card_exports div[data-testid="stHorizontalBlock"]:has(.st-key-fase6_goto_fase5_activar){margin-top:0 !important}
.st-key-f6_card_exports [data-testid="stButton"]>button, .st-key-f6_card_exports [data-testid="stDownloadButton"]>button{width:100%;background:#ffffff !important;border:1.5px solid #bfdbfe !important;color:#2563eb !important;border-radius:12px !important;font-weight:800 !important;min-height:40px !important;font-size:14px !important}
.st-key-f6_card_exports [data-testid="stButton"]>button:hover, .st-key-f6_card_exports [data-testid="stDownloadButton"]>button:hover{background:#eff6ff !important;border-color:#2563eb !important}
.st-key-f6_card_exports [data-testid="stButton"]>button:disabled, .st-key-f6_card_exports [data-testid="stDownloadButton"]>button:disabled{background:#f8fafc !important;border-color:#e2e8f0 !important;color:#000000 !important}
@media(max-width:1200px){.f6-ref-kpi-grid,.f6-ref-summary-grid{grid-template-columns:repeat(3,1fr)}.f6-ref-export-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.f6-ref-kpi-grid,.f6-ref-summary-grid{grid-template-columns:repeat(2,1fr)}.f6-ref-export-grid{grid-template-columns:1fr}}

/* =========================================================
   FORZADO FINAL: estilo SMA 2.0 para cards grandes - Fase 6
   ========================================================= */
.st-key-f6_card_header,
.st-key-f6_card_main,
.st-key-f6_card_exec_summary,
.st-key-f6_card_scenario,
.st-key-f6_card_exports,
.st-key-f6_save_section,
.st-key-f6_card_bankable,
.st-key-f6_card_gis_export {
    border: 1px solid #cbd5e1 !important;
    border-radius: 28px !important;
    background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
    box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    overflow: visible !important;
    box-sizing: border-box !important;
}
.st-key-f6_card_header {
    border: 1.35px solid #cbd5e1 !important;
    border-radius: 28px !important;
}

.st-key-f6_card_header div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_main div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_exec_summary div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_scenario div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_exports div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_save_section div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_bankable div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_gis_export div[data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
    box-shadow: none !important;
    border-radius: 28px !important;
    background: transparent !important;
    overflow: visible !important;
    box-sizing: border-box !important;
}
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

# Hero y resumen ejecutivo
# -----------------------------------------------------------------------------
_F6_ILLUST = '''<svg viewBox="0 0 300 130" width="300" height="130" xmlns="http://www.w3.org/2000/svg" style="display:block">
<defs><linearGradient id="fg1" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#dbeafe" stop-opacity=".3"/><stop offset="100%" stop-color="#eff6ff" stop-opacity=".15"/></linearGradient></defs>
<path d="M0 100 Q70 78 140 88 T300 72 V130 H0Z" fill="url(#fg1)"/>
<g stroke="#93c5fd" stroke-width="1.1" fill="none" opacity=".65"><line x1="160" y1="88" x2="160" y2="38"/><circle cx="160" cy="36" r="2.8" fill="#93c5fd"/><line x1="160" y1="36" x2="151" y2="20"/><line x1="160" y1="36" x2="174" y2="22"/><line x1="160" y1="36" x2="156" y2="52"/></g>
<g stroke="#93c5fd" stroke-width="1" fill="none" opacity=".45"><line x1="220" y1="80" x2="220" y2="45"/><circle cx="220" cy="43" r="2.2" fill="#93c5fd"/><line x1="220" y1="43" x2="213" y2="31"/><line x1="220" y1="43" x2="230" y2="33"/><line x1="220" y1="43" x2="218" y2="56"/></g>
<g stroke="#93c5fd" stroke-width=".9" fill="none" opacity=".35"><line x1="265" y1="75" x2="265" y2="50"/><circle cx="265" cy="48" r="1.8" fill="#93c5fd"/><line x1="265" y1="48" x2="260" y2="39"/><line x1="265" y1="48" x2="272" y2="40"/><line x1="265" y1="48" x2="263" y2="58"/></g>
<g stroke="#bfdbfe" stroke-width=".7" opacity=".45"><path d="M120 42 Q150 38 180 42" fill="none"/><path d="M150 30 Q180 26 210 30" fill="none"/></g>
<g fill="#bfdbfe" opacity=".25"><circle cx="250" cy="25" r="1.3"/><circle cx="260" cy="18" r="1"/><circle cx="275" cy="28" r=".9"/><circle cx="240" cy="16" r=".8"/></g>
</svg>'''

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
enriched_label = "Listas" if heavy_exports_ready else ("Desactualizadas" if heavy_exports_stale else "Pendientes")
lcoe_sub = format_lcoe_value(lcoe_mwh, unidad, "MWh") if _has_value(lcoe_mwh) else ""

with st.container(border=True, key="f6_card_header"):
    st.markdown(
        """
<div class="hero-card">
    <div class="fase-hero-title">Fase 6 &middot; Exportar y guardar</div>
    <div class="fase-hero-subtitle">Esta fase centraliza el guardado final del proyecto y la exportaci&oacute;n de resultados e informes generados en Fase 5.</div>
</div>
""",
        unsafe_allow_html=True,
    )

exec_summary_card = st.container(border=True, key="f6_card_exec_summary")
exec_summary_card.markdown(
    f"""
<div class="f6-ref-summary-intro">
    <div class="f6-ref-summary-intro-title"><span class="f6-ref-icon-soft">{_safe_icon("chart", 14)}</span>Resumen ejecutivo del escenario actual</div>
    <div class="f6-ref-summary-intro-sub">Revise los principales indicadores del proyecto antes de exportar o guardar los resultados.</div>
</div>
""",
    unsafe_allow_html=True,
)

# KPI principales (6 columnas)
def _ref_kpi(label, value, icon="chart", sub="", color="#2563eb", size=42):
    return (f'<div class="f6-ref-kpi-card"><div class="f6-ref-kpi-icon" style="color:{color}; border-color:{color}40; background-color:{color}10;">{_safe_icon(icon, size, color)}</div>'
            f'<div><div class="f6-ref-kpi-label">{_escape(label)}</div>'
            f'<div class="f6-ref-kpi-value">{_escape(value)}</div>'
            f'<div class="f6-ref-kpi-sub">{_escape(sub)}</div></div></div>')

main_kpis = [
    _ref_kpi("Método principal", str(config.get("f5_metodo_detalle") or config.get("f5_modo_estadistico") or "N/D"), "turbine-simple", color="#8b5cf6"),
    _ref_kpi("AEP bruta", _fmt_float(bruto, 2, " MWh/año"), "bolt", "MWh/año", color="#f59e0b"),
    _ref_kpi("AEP neta", _fmt_float(neto, 2, " MWh/año"), "bolt", "MWh/año", color="#10b981"),
    _ref_kpi("LCOE", format_lcoe_value(lcoe_kwh, unidad, "kWh") if _has_value(lcoe_kwh) else "N/D", "dollar", lcoe_sub, color="#0ea5e9"),
    _ref_kpi("Número de turbinas", str(config.get("f5_n_turbinas") or config.get("f4_num_turbinas") or "N/D"), "turbine-simple", color="#6366f1"),
    _ref_kpi("Exportaciones enriquecidas", enriched_label, "file-text", color="#ec4899"),
]
exec_summary_card.markdown(f'<div class="f6-ref-kpi-grid">{"".join(main_kpis)}</div>', unsafe_allow_html=True)

# Resumen del escenario actual
scenario_card = st.container(border=True, key="f6_card_scenario")
scenario_card.markdown(
    f'<div class="f6-ref-section-header"><span class="f6-ref-icon-soft">{_safe_icon("database", 18)}</span><div><div class="f6-ref-section-title">Resumen del escenario actual</div></div></div>',
    unsafe_allow_html=True,
)

def _ref_summary(label, value, icon="chart", color="#2563eb", size=42):
    return f'<div class="f6-ref-summary-card"><div class="f6-ref-sc-icon" style="color:{color}; border-color:{color}40; background-color:{color}10;">{_safe_icon(icon, size, color)}</div><div><div class="f6-ref-summary-label">{_escape(label)}</div><div class="f6-ref-summary-value">{_escape(value)}</div></div></div>'

summary_cards = [
    _ref_summary("FP bruto", _fmt_float(fpb, 2, "%"), "turbine-simple", color="#8b5cf6"),
    _ref_summary("FP neto", _fmt_float(fpn, 2, "%"), "turbine-simple", color="#6366f1"),
    _ref_summary("Potencia instalada", _fmt_float(potencia_instalada, 3, " MW"), "turbine-simple", color="#0ea5e9"),
    _ref_summary("CAPEX total", format_currency_amount(capex_total, unidad) if _has_value(capex_total) else "N/D", "bar-chart", color="#10b981"),
    _ref_summary("OPEX anual total", format_currency_amount(opex_total, unidad) if _has_value(opex_total) else "N/D", "dollar", color="#f59e0b"),
    _ref_summary("VP costos", format_currency_amount(vp_costos, unidad) if _has_value(vp_costos) else "N/D", "chart", color="#ec4899"),
]
scenario_card.markdown(f'<div class="f6-ref-summary-grid">{"".join(summary_cards)}</div>', unsafe_allow_html=True)

scenario_card.markdown(
    f"""
<div class="f6-ref-context-text"><strong>Contexto de reporte:</strong> {_escape(report_context['report_style_label'])} ({_escape(project_context['mode_label'])}, perfil: {_escape(project_context['profile_label'])})</div>
<div class="f6-ref-context-strip">
    <span style="margin-right:4px;display:inline-flex;align-items:center;color:#3b82f6">{_safe_icon("calendar", 16)}</span>
    <span>Moneda base: {_escape(config.get('f5_moneda_base') or 'USD')}</span>
    <span style="color:#cbd5e1;margin:0 4px">|</span>
    <span>Moneda de visualización: {_escape(unidad)}</span>
    <span style="color:#cbd5e1;margin:0 4px">|</span>
    <span>Tasa COP/USD: {float(config.get('f5_fx_rate_cop_per_usd') or 0):.4f}</span>
    <span style="color:#cbd5e1;margin:0 4px">|</span>
    <span>Última actualización: {_escape(config.get('f5_fx_timestamp') or 'N/D')}</span>
</div>
""",
    unsafe_allow_html=True,
)

# Exportación de resultados (4 cards visuales)
# -----------------------------------------------------------------------------
export_card = st.container(border=True, key="f6_card_exports")
export_card.markdown(
    f'<div class="f6-ref-section-header"><span class="f6-ref-icon-soft">{_safe_icon("export", 18)}</span><div><div class="f6-ref-section-title">Exportación de resultados</div><div class="f6-ref-section-subtitle">Genera informes e informes técnicos con los resultados del proyecto.</div></div></div>',
    unsafe_allow_html=True,
)
# Botones funcionales de exportación
btn_disabled = not (runtime_context and basic_bundle)

if btn_disabled:
    # Si Fase 5 ya tiene resultados persistidos en config pero el runtime_context
    # de sesión está vacío (p. ej. el usuario abre F6 tras cargar un proyecto
    # guardado sin pasar primero por F5), guiamos con un botón directo en lugar
    # del warning pasivo previo.
    _f5_results_in_config = (
        config.get("f5_aep_bruta_total_mwh") is not None
        and config.get("f5_aep_neta_total_mwh") is not None
    )
    _msg = (
        "Los resultados existen en la base del proyecto pero esta sesión aún no "
        "los ha cargado. Pulse el botón para regenerar el cálculo de Fase 5 "
        "(toma unos segundos) y volver a Fase 6 con las exportaciones activas."
        if _f5_results_in_config
        else "Primero ejecute el cálculo en Fase 5 (botón «Aplicar configuración»). "
             "Luego regrese a Fase 6 y las exportaciones quedarán habilitadas."
    )
    export_card.markdown(
        f'<div style="color: #b45309; background:#fff7ed; border:1px solid #fed7aa; '
        f'border-radius:10px; padding:10px 14px; font-size:13.5px; font-weight:600; '
        f'margin:6px 0 12px 0;">⚠ Exportaciones inactivas. {_msg}</div>',
        unsafe_allow_html=True,
    )
    _go_col_left, _go_col_btn, _go_col_right = export_card.columns([1, 2, 1])
    with _go_col_btn:
        if st.button(
            "Ir a Fase 5 y activar exportaciones",
            key="fase6_goto_fase5_activar",
            use_container_width=True,
            type="primary",
            icon=":material/play_arrow:",
        ):
            try:
                st.switch_page("pages/5_Fase_5_AEP_bruta_y_neta.py")
            except Exception:
                # Fallback si switch_page no disponible (Streamlit antiguo)
                st.info("Abra la pestaña «Fase 5 · AEP bruta y neta» en la barra lateral.")

# Cards visuales siempre presentes
export_card.markdown(
    f"""
<div class="f6-ref-export-grid">
    <div class="f6-ref-export-card">
        <div class="f6-ref-export-top">
            <div class="f6-ref-export-icon f6-ref-export-icon-pdf">
                <div style="position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;">
                    {_safe_icon('file', 42, '#dc2626')}
                    <div style="position:absolute;top:54%;left:50%;transform:translate(-50%, -50%);font-size:12px;font-weight:900;color:#dc2626;letter-spacing:-0.5px;">PDF</div>
                </div>
            </div>
            <div><div class="f6-ref-export-title">Informe PDF</div>
            <div class="f6-ref-export-desc">Resumen ejecutivo y resultados principales.</div></div>
        </div>
    </div>
    <div class="f6-ref-export-card">
        <div class="f6-ref-export-top">
            <div class="f6-ref-export-icon f6-ref-export-icon-word">
                <div style="position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;">
                    {_safe_icon('file', 42, '#2563eb')}
                    <div style="position:absolute;top:54%;left:50%;transform:translate(-50%, -50%);font-size:15px;font-weight:900;color:#2563eb;">W</div>
                </div>
            </div>
            <div><div class="f6-ref-export-title">Informe Word</div>
            <div class="f6-ref-export-desc">Documento editable con tablas y gráficos.</div></div>
        </div>
    </div>
    <div class="f6-ref-export-card">
        <div class="f6-ref-export-top">
            <div class="f6-ref-export-icon f6-ref-export-icon-excel">
                <div style="position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;">
                    {_safe_icon('file', 42, '#16a34a')}
                    <div style="position:absolute;top:54%;left:50%;transform:translate(-50%, -50%);font-size:15px;font-weight:900;color:#16a34a;">X</div>
                </div>
            </div>
            <div><div class="f6-ref-export-title">Excel / CSV</div>
            <div class="f6-ref-export-desc">Datos tabulares para análisis adicional.</div></div>
        </div>
    </div>
    <div class="f6-ref-export-card">
        <div class="f6-ref-export-top">
            <div class="f6-ref-export-icon f6-ref-export-icon-json">
                <div style="position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;">
                    {_safe_icon('file', 42, '#7c3aed')}
                    <div style="position:absolute;top:54%;left:50%;transform:translate(-50%, -50%);font-size:12px;font-weight:900;color:#7c3aed;letter-spacing:-1px;">&lt;/&gt;</div>
                </div>
            </div>
            <div><div class="f6-ref-export-title">Datos JSON</div>
            <div class="f6-ref-export-desc">Exportación completa de datos del proyecto.</div></div>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)


exp1, exp2, exp3, exp4 = export_card.columns(4, gap="medium")

with exp1:
    pdf_ok = bool(informe_tecnico_pdf_artifact and informe_tecnico_pdf_artifact.get("success"))

    if pdf_ok and not btn_disabled:
        st.download_button("Exportar PDF", data=informe_tecnico_pdf_artifact["pdf_bytes"], file_name=informe_tecnico_pdf_artifact.get("file_name", "informe_tecnico.pdf"), mime="application/pdf", use_container_width=True, icon=":material/download:", disabled=btn_disabled)
    else:
        if st.button("Generar Informe PDF", key="fase6_generar_informe_tecnico", use_container_width=True, icon=":material/download:", disabled=btn_disabled):
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
        st.download_button("Exportar Word", data=informe_tecnico_docx_artifact["docx_bytes"], file_name=informe_tecnico_docx_artifact.get("file_name", "informe_tecnico.docx"), mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True, icon=":material/download:", disabled=btn_disabled)
    else:
        st.download_button("Exportar Word", data=b"", file_name="dummy.docx", use_container_width=True, icon=":material/download:", disabled=True, key="fase6_dummy_docx")

with exp3:
    excel_data = basic_bundle["excel_bytes"] if not btn_disabled and basic_bundle else b""
    if st.download_button("Exportar Excel/CSV", data=excel_data, file_name="fase5_resultados_completos.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, icon=":material/download:", disabled=btn_disabled):
        # Revela el botón Excel PRO solo después de pulsar "Exportar Excel/CSV".
        st.session_state["f6_show_excel_pro"] = True
    if st.session_state.get("f6_show_excel_pro"):
        excel_pro_data = basic_bundle.get("excel_pro_bytes", b"") if not btn_disabled and basic_bundle else b""
        pro_disabled = btn_disabled or not excel_pro_data
        st.download_button("Exportar Excel PRO (16 hojas bankable)", data=excel_pro_data, file_name="fase5_excel_PRO_bankable.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, icon=":material/star:", disabled=pro_disabled, help="Excel profesional estilo WAsP/WindPRO/OpenWind: Cover + ExecSummary + Site + WindRes + PowerCurve + Sectorial + LossWaterfall + PerWTG + Uncertainty P50/P90 + CAPEX/OPEX + CashFlow + Sensitivity + IEC SiteSuitability + Assumptions + Glossary + AuditManifest")

with exp4:
    json_data = basic_bundle["report_manifest_json"].encode("utf-8") if not btn_disabled and basic_bundle else b""
    st.download_button("Exportar JSON", data=json_data, file_name="fase5_manifiesto_reporte.json", mime="application/json", use_container_width=True, icon=":material/download:", disabled=btn_disabled)

# Exportaciones adicionales en expanders
if not btn_disabled:
    if informe_tecnico_meta.get("master_source_used"):
        export_card.info(f"Base canónica activa: `{informe_tecnico_meta.get('master_source_name', 'informe_tecnico.docx')}`")
    elif informe_tecnico_meta.get("master_warning"):
        export_card.warning(informe_tecnico_meta["master_warning"])

    with export_card.expander("Exportaciones adicionales: CSV sectorial, LaTeX y figuras"):
        a1, a2 = st.columns(2)
        with a1:
            st.download_button("Descargar CSV sectorial", data=basic_bundle["csv_bytes"], file_name="fase5_resultados_sectoriales.csv", mime="text/csv", use_container_width=True, icon=":material/download:")
        with a2:
            st.download_button("Descargar esqueleto LaTeX (.tex)", data=basic_bundle["latex_skeleton"].encode("utf-8"), file_name="fase5_esqueleto_reporte.tex", mime="application/x-tex", use_container_width=True, icon=":material/download:")

        # Exportaciones enriquecidas
        if heavy_exports_stale:
            st.info("Las exportaciones enriquecidas fueron generadas con una configuración anterior.")
        elif heavy_exports_ready:
            st.success("Las exportaciones enriquecidas están listas.")
        else:
            st.info("Las exportaciones enriquecidas aún no han sido preparadas.")

        if st.button("Preparar o actualizar exportaciones enriquecidas", key="fase6_preparar_exportes", use_container_width=True, icon=":material/refresh:"):
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

with st.container(border=True, key="f6_save_section"):
    st.markdown(
        f'<div class="f6-ref-section-header"><span class="f6-ref-icon-soft">{_safe_icon("database", 18)}</span><div><div class="f6-ref-section-title">Guardado final del proyecto</div><div class="f6-ref-section-subtitle">Guarda el proyecto en la base de datos o descarga el archivo del proyecto.</div></div></div>',
        unsafe_allow_html=True,
    )

    nombre_proyecto = st.text_input(
        "Nombre del proyecto",
        value=str(config.get("project_name") or "Proyecto_eolico_1"),
    )

    if runtime_context:
        runtime_context["project_name_default"] = nombre_proyecto

    save_c1, save_c2 = st.columns(2, gap="medium")
    with save_c1:
        if st.button("Guardar proyecto en la base de datos", use_container_width=True, type="primary"):
            try:
                guardar_config_values({"project_name": nombre_proyecto})
                guardar_proyecto(nombre_proyecto)
                st.success(f"Proyecto '{nombre_proyecto}' guardado correctamente en la base de datos.")
            except Exception as e:
                st.error(f"No pude guardar el proyecto: {e}")
    with save_c2:
        try:
            proyecto_json = exportar_proyecto_json_texto()
            st.download_button("Descargar proyecto (.json)", data=proyecto_json.encode("utf-8"), file_name=f"{nombre_proyecto}.json", mime="application/json", use_container_width=True)
        except Exception as e:
            st.error(f"No pude preparar el archivo del proyecto: {e}")


# C7 + i18n - Reporte BANKABLE multi-país, multi-idioma, con branding
with st.container(border=True, key="f6_card_bankable"):
    st.markdown("### 📑 Reporte BANKABLE (multi-país · multi-idioma)")
    st.caption("Informe estructurado 30-50 páginas: cover + TOC + executive + P50/P90 + IEC + ambiental + económico (WACC/DSCR/PPA país-específico) + risk register + apéndices. Disclaimer obligatorio incluido.")

    from i18n_paises import get_country_profile, listar_idiomas, listar_paises

    col_b1, col_b2, col_b3 = st.columns([1.2, 1.2, 1])
    with col_b1:
        bk_project = st.text_input("Nombre del proyecto", value=config.get("project_name", "Wind Farm"), key="f6_bk_project")
        bk_autor = st.text_input("Autor / Consultor", value=config.get("f6_bankable_autor", ""), key="f6_bk_autor")
    with col_b2:
        bk_cliente = st.text_input("Cliente / Promotor", value=config.get("f6_bankable_cliente", ""), key="f6_bk_cliente")
        paises_options = listar_paises()
        pais_labels = [f"{c} — {n}" for c, n in paises_options]
        pais_default_code = config.get("f6_country_code", "OTRO")
        idx_pais = next((i for i, (c, _) in enumerate(paises_options) if c == pais_default_code), len(paises_options) - 1)
        pais_sel_label = st.selectbox("País del proyecto", pais_labels, index=idx_pais, key="f6_country_label")
        pais_sel_code = pais_sel_label.split(" — ")[0]
    with col_b3:
        idiomas_options = listar_idiomas()
        idioma_labels = [f"{c} — {n}" for c, n in idiomas_options]
        idioma_default = config.get("f6_report_lang", "es")
        idx_idioma = next((i for i, (c, _) in enumerate(idiomas_options) if c == idioma_default), 0)
        idioma_sel_label = st.selectbox("Idioma reporte", idioma_labels, index=idx_idioma, key="f6_report_lang_label")
        idioma_sel_code = idioma_sel_label.split(" — ")[0]
        logo_upload = st.file_uploader("Logo cliente (PNG/JPG, opcional)", type=["png", "jpg", "jpeg"], key="f6_bk_logo")

    # Mostrar perfil país detectado
    perfil_pais = get_country_profile(pais_sel_code)
    st.info(f"**País:** {perfil_pais['nombre']} · **Moneda local:** {perfil_pais['currency']} · "
            f"**WACC típico:** {perfil_pais['wacc_tipico_pct']}% · "
            f"**Tax rate:** {perfil_pais['tax_rate_pct']}% · "
            f"**Mecanismo regulatorio:** {perfil_pais['mecanismo_descripcion']}")

    if st.button("Generar reporte bankable (DOCX)", key="f6_btn_gen_bankable", use_container_width=True, type="primary"):
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
                    "f6_bankable_project_name": bk_project,
                    "f6_bankable_autor": bk_autor,
                    "f6_bankable_cliente": bk_cliente,
                    "f6_country_code": pais_sel_code,
                    "f6_report_lang": idioma_sel_code,
                })
                st.session_state["f6_bankable_docx_bytes"] = docx_bytes
                st.success(f"Reporte generado ({len(docx_bytes)/1024:.1f} KB) en {idioma_sel_code.upper()} para {perfil_pais['nombre']}.")
        except Exception as exc:
            st.error(f"Error generando reporte: {exc}")

    if st.session_state.get("f6_bankable_docx_bytes"):
        st.download_button(
            "⬇ Descargar informe bankable (.docx)",
            data=st.session_state["f6_bankable_docx_bytes"],
            file_name=f"{bk_project.replace(' ', '_')}_BANKABLE_{idioma_sel_code}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            key="f6_dl_bankable",
        )


# GIS Export — KML/GeoJSON/CSV/ZIP
with st.container(border=True, key="f6_card_gis_export"):
    st.markdown("### 🗺️ GIS Export (KML Google Earth · GeoJSON · CSV coords)")
    st.caption("Cierra gap vs WindPRO/OpenWind: exporta layout en formatos GIS estándar para QGIS, Google Earth, ArcGIS, AutoCAD.")

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

            col_g1, col_g2, col_g3, col_g4 = st.columns(4)
            with col_g1:
                if st.button("📍 KML (Google Earth)", key="f6_btn_kml", use_container_width=True):
                    try:
                        kml = exportar_kml_layout(df_layout_gis, lat_site_gis, lon_site_gis,
                                                    nombre_parque=nombre_gis,
                                                    diametro_rotor=diametro_gis, altura_buje=h_hub_gis)
                        st.session_state["f6_kml_bytes"] = kml
                        st.success(f"KML: {len(kml)/1024:.1f} KB")
                    except Exception as exc:
                        st.error(f"KML error: {exc}")
            with col_g2:
                if st.button("🌐 GeoJSON", key="f6_btn_geojson", use_container_width=True):
                    try:
                        gj = exportar_geojson_layout(df_layout_gis, lat_site_gis, lon_site_gis, nombre_gis)
                        st.session_state["f6_geojson_bytes"] = gj
                        st.success(f"GeoJSON: {len(gj)/1024:.1f} KB")
                    except Exception as exc:
                        st.error(f"GeoJSON error: {exc}")
            with col_g3:
                if st.button("📊 CSV coords", key="f6_btn_csv_coords", use_container_width=True):
                    try:
                        csv_c = exportar_csv_coords(df_layout_gis, lat_site_gis, lon_site_gis)
                        st.session_state["f6_csv_coords_bytes"] = csv_c
                        st.success(f"CSV: {len(csv_c)/1024:.1f} KB")
                    except Exception as exc:
                        st.error(f"CSV error: {exc}")
            with col_g4:
                if st.button("📦 ZIP completo (KML+GeoJSON+CSV)", key="f6_btn_zip_gis", use_container_width=True):
                    try:
                        zip_b = exportar_zip_paquete_gis(df_layout_gis, lat_site_gis, lon_site_gis, nombre_gis,
                                                          diametro_rotor=diametro_gis, altura_buje=h_hub_gis)
                        st.session_state["f6_zip_gis_bytes"] = zip_b
                        st.success(f"ZIP: {len(zip_b)/1024:.1f} KB")
                    except Exception as exc:
                        st.error(f"ZIP error: {exc}")

            dl_cols = st.columns(4)
            with dl_cols[0]:
                if st.session_state.get("f6_kml_bytes"):
                    st.download_button("⬇ .kml", data=st.session_state["f6_kml_bytes"],
                                       file_name=f"{nombre_gis}.kml", mime="application/vnd.google-earth.kml+xml",
                                       use_container_width=True, key="f6_dl_kml")
            with dl_cols[1]:
                if st.session_state.get("f6_geojson_bytes"):
                    st.download_button("⬇ .geojson", data=st.session_state["f6_geojson_bytes"],
                                       file_name=f"{nombre_gis}.geojson", mime="application/geo+json",
                                       use_container_width=True, key="f6_dl_geojson")
            with dl_cols[2]:
                if st.session_state.get("f6_csv_coords_bytes"):
                    st.download_button("⬇ coords.csv", data=st.session_state["f6_csv_coords_bytes"],
                                       file_name=f"{nombre_gis}_coords.csv", mime="text/csv",
                                       use_container_width=True, key="f6_dl_csv_coords")
            with dl_cols[3]:
                if st.session_state.get("f6_zip_gis_bytes"):
                    st.download_button("⬇ paquete GIS .zip", data=st.session_state["f6_zip_gis_bytes"],
                                       file_name=f"{nombre_gis}_GIS.zip", mime="application/zip",
                                       use_container_width=True, key="f6_dl_zip_gis")
    except ImportError as ie:
        st.warning(f"GIS export requiere `simplekml`. Instalar: `pip install simplekml`. Error: {ie}")


