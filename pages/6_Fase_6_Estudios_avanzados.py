import html
import json

import numpy as np
import pandas as pd
import streamlit as st

from db import (
    cargar_config,
    cargar_layout_parque,
    cargar_nasa_hourly,
    cargar_tabla_curva,
    guardar_config_values,
    init_db,
)
from navigation import _icon_svg, render_dropdown_visibility_fix, render_sidebar_navigation

st.set_page_config(page_title="Fase 6 · Estudios avanzados", layout="wide")

init_db()
render_sidebar_navigation("pages/6_Fase_6_Estudios_avanzados.py")


# -----------------------------------------------------------------------------
# Helpers visuales locales (mismo idioma que el resto de fases)
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


def _cfg_float(config: dict, key: str, default: float) -> float:
    try:
        raw = config.get(key)
        return float(raw) if _has_value(raw) else float(default)
    except (TypeError, ValueError):
        return float(default)


# Mapa nombre-de-icono-SVG → emoji del mockup 06_fase6 (card-heads y KPIs).
_F6_ICON_EMOJI = {
    "target": "🎯", "waves": "⛰️", "calendar": "🧊", "map-pin": "📍",
    "activity": "🔊", "clock": "🌒", "wind": "🦅", "globe": "🌱",
    "database": "📡", "bolt": "🔌", "layout": "🎯", "trending-down": "♻️",
    "table": "📋", "chart": "📊", "sigma": "σ", "snow": "🧊",
}


def _f6_emoji_for(icon: str) -> str:
    """Devuelve el emoji del mockup si el nombre está mapeado; si ya es glifo, lo deja."""
    if not icon:
        return ""
    if not icon.isascii():
        return icon
    return _F6_ICON_EMOJI.get(icon, icon)


def _section_header(title: str, subtitle: str = "", icon: str = "chart") -> None:
    """Card-head Aurora (idioma F3): squircle teal con emoji + título + subtítulo."""
    _render_card_header_native(title, _f6_emoji_for(icon), subtitle)


def _session_cached_result(state_key: str, signature: tuple, builder):
    """Cachea en session_state el resultado de un cómputo pesado, keyed por firma.

    Mismo patrón que Fase 5: el resultado sobrevive reruns y cambios de sección;
    se recomputa solo si la firma (inputs) cambia.
    """
    cached = st.session_state.get(state_key)
    if isinstance(cached, dict) and cached.get("signature") == signature:
        return cached["value"]
    value = builder()
    st.session_state[state_key] = {"signature": signature, "value": value}
    return value


# -----------------------------------------------------------------------------
# Backbone compartido: serie horaria del parque a altura de buje.
# Lo usan IEC, SCADA, curtailment e híbrido. SOLO se invoca dentro de handlers
# de botón — nunca a nivel de página.
# -----------------------------------------------------------------------------
def _serie_signature() -> tuple:
    from db import _db_cache_stamp

    return (
        _db_cache_stamp(),
        str(config.get("f5_base_viento") or "50 m"),
        str(config.get("f5_altura_deseada") or ""),
        str(config.get("f5_roughness_label") or ""),
        str(config.get("f5_dir_altura") or ""),
        str(config.get("f5_n_turbinas") or config.get("f4_num_turbinas") or "1"),
        str(config.get("f4_weighted_wake_loss_pct") or config.get("f5_wake_manual_pct") or "0"),
    )


def _construir_serie_horaria_parque():
    df_nasa = cargar_nasa_hourly()
    if df_nasa is None or len(df_nasa) == 0:
        return None
    from calculos import preparar_datos_curva
    from calculos_energia import calcular_aep_serie_horaria, construir_viento_analisis

    df_analisis, _meta = construir_viento_analisis(
        df_nasa,
        str(config.get("f5_base_viento") or "50 m"),
        _cfg_float(config, "f5_altura_deseada", _cfg_float(config, "perfil_hhub", 80.0)),
        str(config.get("f5_roughness_label") or "Grass / Césped"),
        str(config.get("f5_dir_altura") or "WD50M"),
    )
    if df_analisis is None or len(df_analisis) == 0:
        return None
    n_turbinas = max(1, int(_cfg_float(config, "f5_n_turbinas", _cfg_float(config, "f4_num_turbinas", 1.0))))
    wake_pct = _cfg_float(config, "f4_weighted_wake_loss_pct", _cfg_float(config, "f5_wake_manual_pct", 0.0))
    df_curva = preparar_datos_curva(cargar_tabla_curva())
    res = calcular_aep_serie_horaria(
        df_analisis,
        df_curva,
        n_turbinas,
        wake_mode="Manual",
        wake_manual_pct=wake_pct,
    )
    df_h = res["df_horario"].copy()
    if len(df_h) == 0:
        return None
    df_h["potencia_parque_MW"] = df_h["potencia_parque_W"] / 1e6
    return {
        "df_analisis": df_analisis,
        "df_horario": df_h,
        "aep_total_mwh": res["aep_total_mwh"],
        "n_turbinas": n_turbinas,
        "wake_pct": wake_pct,
    }


def _get_serie_horaria_parque():
    """Serie horaria de potencia del parque (modelo de Fase 5 simplificado).

    Aproximación documentada: pérdida de estela = promedio ponderado de Fase 4
    (constante para todas las horas), sin pérdidas globales adicionales.
    """
    return _session_cached_result("f6_serie_horaria", _serie_signature(), _construir_serie_horaria_parque)


_F6_SERIE_CAPTION = (
    "Serie horaria construida con la configuración de Fase 5 (modelo de perfil, altura, rugosidad) "
    "y pérdida de estela promedio de Fase 4. Aproximación para estudios — el AEP oficial es el de Fase 5."
)


# -----------------------------------------------------------------------------
# CSS local Aurora — paridad 06_fase6_estudios_avanzados.html (acento teal #0d9488)
# Idioma SMA 2.0: cards .st-key-f6_card_*  + helpers .aur-* compartidos con F3
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
:root{--f6-ac:#0d9488;--f6-ac2:#115e59;--f6-ink:#0b2447;--f6-sub:#5a6b85;--f6-line:#dce7f5;
  --f6-ok:#16a34a;--f6-warn:#d97706;--f6-bad:#dc2626;--f6-muted:#94a3b8;
  --f6-rlg:26px;--f6-rmd:18px;--f6-rsm:13px;
  --f6-shc:0 1px 2px rgba(11,36,71,.05), 0 10px 28px rgba(11,36,71,.08);
  --f6-sht:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06)}
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(1100px 420px at 90% -120px, color-mix(in srgb,#0d9488 16%,transparent), transparent 70%),
    radial-gradient(900px 500px at -150px 45%, color-mix(in srgb,#0d9488 7%,transparent), transparent 70%),
    linear-gradient(180deg,#f7fbff 0%, #eef5fd 60%, #f4f8fe 100%) !important;
}

/* ════════ Hero teal Aurora (paridad mockup) ════════ */
.f6-hero{position:relative;overflow:hidden;border-radius:26px;padding:22px 28px;color:#fff;
  background:linear-gradient(118deg,#0d9488 0%, #115e59 80%);
  box-shadow:0 22px 44px rgba(13,148,136,.32), inset 0 1px 0 rgba(255,255,255,.25);margin:0}
.f6-hero::after{content:"";position:absolute;inset:0;pointer-events:none;background:
  radial-gradient(circle at 86% 12%, rgba(255,255,255,.20) 0 54px, transparent 55px),
  radial-gradient(circle at 95% 70%, rgba(255,255,255,.12) 0 86px, transparent 87px),
  linear-gradient(180deg, rgba(255,255,255,.08), transparent 40%)}
.f6-wind{position:absolute;left:-30px;top:0;bottom:0;width:58%;height:100%;opacity:.45;pointer-events:none;z-index:1}
.f6-wind path{stroke:rgba(255,255,255,.55);stroke-width:2;fill:none;stroke-dasharray:16 11;animation:f6windmove 2.6s linear infinite}
.f6-wind path:nth-child(2){animation-duration:3.4s;opacity:.7}
.f6-wind path:nth-child(3){animation-duration:4.2s;opacity:.5}
@keyframes f6windmove{to{stroke-dashoffset:-54}}
.f6-hero-row{display:flex;align-items:center;gap:18px;position:relative;z-index:2}
.f6-hero-icon{width:62px;height:62px;border-radius:19px;background:rgba(255,255,255,.17);
  border:1.5px solid rgba(255,255,255,.4);display:flex;align-items:center;justify-content:center;font-size:31px;flex-shrink:0;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 8px 18px rgba(0,0,0,.12)}
.f6-hero-text{flex:1;min-width:0}
.f6-hero h1{margin:0;font-size:25px;font-weight:900;color:#fff;letter-spacing:-.025em;
  text-shadow:0 1px 2px rgba(0,0,0,.12);line-height:1.15}
.f6-hero p{margin:4px 0 0 0;font-size:12.5px;color:rgba(255,255,255,.94);font-weight:500;max-width:840px;line-height:1.45}
.f6-hero-pills{display:flex;gap:9px;margin-left:auto;flex-shrink:0;position:relative;z-index:2}
.f6-hpill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4);border-radius:15px;
  padding:8px 15px;text-align:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.25);color:#fff}
.f6-hpill b{display:block;font-size:16.5px;letter-spacing:-.01em}
.f6-hpill span{font-size:9px;opacity:.92;text-transform:uppercase;letter-spacing:.07em;font-weight:700}
/* El container del hero queda sin borde/padding: solo el f6-hero pintado */
.st-key-f6_card_header div[data-testid="stVerticalBlockBorderWrapper"]{border:none !important;background:transparent !important;padding:0 !important;box-shadow:none !important}
.st-key-f6_card_header{background:transparent !important;border:none !important;box-shadow:none !important;padding:0 !important;margin-bottom:14px !important}
.st-key-f6_card_header::before{display:none !important}

/* ════════ Card-head Aurora (squircle tintado + h2 + sub) ════════ */
.aur-card-head{display:flex;align-items:center;gap:13px;margin-bottom:14px}
.aur-cicon{width:46px;height:46px;border-radius:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;
  background:linear-gradient(135deg, color-mix(in srgb,#0d9488 16%,#fff), color-mix(in srgb,#0d9488 7%,#fff));
  border:1.5px solid color-mix(in srgb,#0d9488 35%,#fff);box-shadow:0 5px 12px color-mix(in srgb,#0d9488 16%,transparent)}
.aur-cicon svg{width:22px;height:22px}
.aur-cicon-emoji{font-size:23px;line-height:1;display:flex;align-items:center;justify-content:center}
.aur-card-head h2{margin:0;font-size:16.5px;font-weight:900;color:#0b2447;letter-spacing:-.02em}
.aur-card-head p{margin:2px 0 0;font-size:11px;color:#5a6b85;font-weight:600}

/* ════════ KPI Aurora (aro tintado + label/valor/sub) ════════ */
.aur-kpi{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;display:flex;gap:12px;align-items:center;
  box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06);min-height:74px;height:100%}
.aur-ki{width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;
  background:linear-gradient(135deg, color-mix(in srgb,var(--kc,#0d9488) 17%,#fff), color-mix(in srgb,var(--kc,#0d9488) 6%,#fff));
  border:1.5px solid color-mix(in srgb,var(--kc,#0d9488) 38%,#fff);box-shadow:0 5px 12px color-mix(in srgb,var(--kc,#0d9488) 18%,transparent)}
.aur-ki svg{width:24px;height:24px}
.aur-ki-emoji{font-size:22px;line-height:1;display:flex;align-items:center;justify-content:center}
.aur-kpi-copy{min-width:0}
.aur-kpi-copy small{display:block;font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.07em}
.aur-kpi-copy b{font-size:19px;letter-spacing:-.025em;line-height:1.08;display:block;margin-top:3px;color:#0b2447;font-variant-numeric:tabular-nums}
.aur-kpi-copy i{font-style:normal;font-size:10px;color:#5a6b85;display:block;margin-top:2.5px;font-weight:600;line-height:1.25}
.f6-kgrid{display:grid;grid-template-columns:repeat(var(--n,4),minmax(0,1fr));gap:12px;margin:6px 0 10px}
@media(max-width:1200px){.f6-kgrid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.f6-kgrid{grid-template-columns:1fr}}

/* ════════ Divider de sección (icono tintado + título + línea) ════════ */
.f6-divider{display:flex;align-items:center;gap:13px;margin:24px 2px 12px}
.f6-divider .dx{width:42px;height:42px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:20px;color:#fff;
  background:linear-gradient(135deg, color-mix(in srgb, var(--dc,#0d9488) 88%, #fff), var(--dc,#0d9488));
  box-shadow:0 8px 18px color-mix(in srgb, var(--dc,#0d9488) 35%, transparent)}
.f6-divider b{font-size:15.5px;letter-spacing:-.01em;display:block;color:#0b2447}
.f6-divider small{display:block;font-size:10.5px;color:#5a6b85;font-weight:700}
.f6-divider .dline{flex:1;height:2px;border-radius:2px;
  background:linear-gradient(90deg, color-mix(in srgb, var(--dc,#0d9488) 45%, #fff), transparent)}

/* ════════ Banners, badges, chips, frow, fig, upload, tabla, leyenda ════════ */
.f6-banner{display:flex;align-items:center;gap:12px;border-radius:15px;padding:12px 16px;font-weight:800;font-size:12.5px;margin:10px 0}
.f6-banner .bx{width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:18px;background:rgba(255,255,255,.7);flex-shrink:0}
.f6-banner.ok{background:linear-gradient(120deg,#f0fdf4,#fff);border:1.5px solid #86efac;color:#15803d}
.f6-banner.warn{background:linear-gradient(120deg,#fffbeb,#fff);border:1.5px solid #fde68a;color:#b45309}
.f6-banner.bad{background:linear-gradient(120deg,#fef2f2,#fff);border:1.5px solid #fecaca;color:#b91c1c}
.f6-banner.info{background:linear-gradient(120deg, color-mix(in srgb,#0d9488 8%,#fff), #fff);border:1.5px solid color-mix(in srgb,#0d9488 30%,#fff);color:#0d9488}
.f6-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;font-size:10.5px;font-weight:800;border:1px solid;white-space:nowrap}
.f6-pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px color-mix(in srgb,currentColor 18%,transparent)}
.f6-pill.ok{color:#15803d;background:#f0fdf4;border-color:#bbf7d0}
.f6-pill.warn{color:#b45309;background:#fffbeb;border-color:#fde68a}
.f6-pill.bad{color:#b91c1c;background:#fef2f2;border-color:#fecaca}
.f6-pill.info{color:#0d9488;background:color-mix(in srgb,#0d9488 8%,#fff);border-color:color-mix(in srgb,#0d9488 35%,#fff)}
.f6-fig{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06)}
.f6-fig svg{display:block;width:100%;height:auto}
.f6-gtitle{font-size:12px;font-weight:900;color:#0b2447;margin-bottom:7px;display:flex;align-items:center;gap:7px;letter-spacing:-.01em}
.f6-legend{display:flex;gap:13px;flex-wrap:wrap;font-size:10px;font-weight:800;color:#5a6b85;margin-top:9px;justify-content:center}
.f6-legend i{font-style:normal;display:inline-flex;align-items:center;gap:5px}
.f6-legend i::before{content:"";width:11px;height:11px;border-radius:4px;background:var(--lc);box-shadow:0 2px 5px color-mix(in srgb,var(--lc) 40%,transparent)}
.f6-tbl{width:100%;border-collapse:separate;border-spacing:0;border:1px solid #d8e5f5;border-radius:14px;overflow:hidden;font-size:11.5px}
.f6-tbl th{background:linear-gradient(180deg, color-mix(in srgb,#0d9488 9%,#fff), color-mix(in srgb,#0d9488 5%,#fff));
  color:#0b2447;text-align:left;padding:9px 12px;font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:900}
.f6-tbl td{padding:8px 12px;border-top:1px solid #eef4fb;font-weight:650;color:#0b2447}
.f6-tbl tr:nth-child(even) td{background:#fafcff}
.f6-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:750}
.f6-upload{border:2px dashed color-mix(in srgb,#0d9488 42%,#fff);
  background:linear-gradient(180deg, color-mix(in srgb,#0d9488 5%,#fff), #fff);
  border-radius:18px;padding:24px;text-align:center;margin:8px 0}
.f6-upload .ui{width:58px;height:58px;margin:0 auto;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:27px;
  background:#fff;border:1.5px solid color-mix(in srgb,#0d9488 30%,#fff);box-shadow:0 8px 18px color-mix(in srgb,#0d9488 14%,transparent)}
.f6-upload b{display:block;font-size:13px;margin-top:9px;color:#0b2447}
.f6-upload span{font-size:10.5px;color:#5a6b85;font-weight:600}

/* ════════ Cards backbone (las 13 cards mantienen su container st-key) ════════ */
.st-key-f6_card_secciones,
.st-key-f6_card_flow,
.st-key-f6_card_cold,
.st-key-f6_card_receptores,
.st-key-f6_card_scada,
.st-key-f6_card_curtail,
.st-key-f6_card_hibrido,
.st-key-f6_card_optim,
.st-key-f6_card_repower,
.st-key-f6_card_audit{
    position:relative !important;
    border:1px solid #d3e0f0 !important;
    border-radius:var(--f6-rlg) !important;
    background:linear-gradient(180deg,#fff,#fcfdff) !important;
    box-shadow:var(--f6-shc) !important;
    overflow:hidden !important;
    box-sizing:border-box !important;
    margin-bottom:16px !important;
}
.st-key-f6_card_iec,
.st-key-f6_card_ruido,
.st-key-f6_card_flicker,
.st-key-f6_card_aves,
.st-key-f6_card_lca{
    position:relative !important;
    border:1px solid #d3e0f0 !important;
    border-radius:var(--f6-rlg) !important;
    background:linear-gradient(180deg,#fff,#fcfdff) !important;
    box-shadow:var(--f6-shc) !important;
    overflow:visible !important;
    box-sizing:border-box !important;
    margin-bottom:16px !important;
}
/* Franja teal de 4px arriba (acento Aurora) */
.st-key-f6_card_secciones::before,
.st-key-f6_card_iec::before,
.st-key-f6_card_flow::before,
.st-key-f6_card_cold::before,
.st-key-f6_card_receptores::before,
.st-key-f6_card_ruido::before,
.st-key-f6_card_flicker::before,
.st-key-f6_card_aves::before,
.st-key-f6_card_lca::before,
.st-key-f6_card_scada::before,
.st-key-f6_card_curtail::before,
.st-key-f6_card_hibrido::before,
.st-key-f6_card_optim::before,
.st-key-f6_card_repower::before,
.st-key-f6_card_audit::before{
    content:"";position:absolute;left:0;right:0;top:0;height:4px;z-index:5;
    background:linear-gradient(90deg, var(--acl,#0d9488), color-mix(in srgb,var(--acl,#0d9488) 25%,#fff) 70%, transparent);
}
.st-key-f6_card_secciones div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_iec div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_flow div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_cold div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_receptores div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_ruido div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_flicker div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_aves div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_lca div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_scada div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_curtail div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_hibrido div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_optim div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_repower div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f6_card_audit div[data-testid="stVerticalBlockBorderWrapper"]{
    border:none !important;box-shadow:none !important;border-radius:var(--f6-rlg) !important;
    background:transparent !important;overflow:visible !important;box-sizing:border-box !important;
    padding:20px 22px 18px !important;
}

/* ════════ Selector de sección como CHIPS (5 chips horizontales) ════════ */
.st-key-f6_card_secciones [data-testid="stRadio"] > label,
.st-key-f6_card_secciones [data-testid="stWidgetLabel"]{display:none !important}
.st-key-f6_card_secciones [data-testid="stRadio"] [role="radiogroup"]{display:flex;gap:9px;flex-wrap:wrap;margin:2px 0}
.st-key-f6_card_secciones [data-testid="stRadio"] [role="radiogroup"] label{
  padding:9px 15px;border-radius:999px;border:1.5px solid #cfe0f5;background:#fff;font-size:12px;font-weight:800;
  color:#5a6b85;display:inline-flex;gap:7px;align-items:center;box-shadow:0 2px 6px rgba(11,36,71,.04);
  cursor:pointer;transition:all .15s;margin:0 !important}
.st-key-f6_card_secciones [data-testid="stRadio"] [role="radiogroup"] label:hover{border-color:#0d9488;color:#0d9488}
.st-key-f6_card_secciones [data-testid="stRadio"] [role="radiogroup"] label > div:first-child{display:none !important}
.st-key-f6_card_secciones [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked){
  background:linear-gradient(120deg, color-mix(in srgb,#0d9488 13%,#fff), color-mix(in srgb,#0d9488 6%,#fff));
  border-color:#0d9488;color:#0d9488;box-shadow:0 6px 14px color-mix(in srgb,#0d9488 18%,transparent)}
.st-key-f6_card_secciones [data-testid="stRadio"] [role="radiogroup"] label > div p{font-weight:800 !important;color:inherit !important;margin:0 !important}

/* ════════ Inputs Aurora (frow simulada en columnas reales de Streamlit) ════════ */
.st-key-f6_card_iec div[data-testid="stNumberInput"] input,
.st-key-f6_card_flow div[data-testid="stNumberInput"] input,
.st-key-f6_card_cold div[data-testid="stNumberInput"] input,
.st-key-f6_card_ruido div[data-testid="stNumberInput"] input,
.st-key-f6_card_flicker div[data-testid="stNumberInput"] input,
.st-key-f6_card_curtail div[data-testid="stNumberInput"] input,
.st-key-f6_card_hibrido div[data-testid="stNumberInput"] input,
.st-key-f6_card_optim div[data-testid="stNumberInput"] input,
.st-key-f6_card_repower div[data-testid="stNumberInput"] input{font-weight:800 !important;color:#0b2447 !important}

/* ════════ Botones — primary teal y ghost teal ════════ */
div[data-testid="stButton"]>button,div[data-testid="stDownloadButton"]>button{border-radius:13px !important;min-height:42px !important;font-weight:800 !important}
div[data-testid="stButton"]>button[kind="primary"]{
  background:linear-gradient(120deg,#0d9488,#115e59) !important;border:none !important;color:#fff !important;
  box-shadow:0 10px 20px color-mix(in srgb,#0d9488 35%,transparent), inset 0 1px 0 rgba(255,255,255,.28) !important}
div[data-testid="stButton"]>button[kind="primary"]:hover{filter:brightness(1.05)}

/* Helpers viejos compatibles (transición — se eliminan al rehacer cada sección) */
.f6-section-header{display:flex;align-items:center;gap:14px;margin:6px 0 16px}
.f6-section-title{color:#0a2444;font-size:21px;font-weight:900;letter-spacing:-.02em}
.f6-section-subtitle{color:#000000;font-size:13px;font-weight:400;margin-top:3px}
.f6-icon-soft{width:2.7rem;height:2.7rem;border-radius:999px;background:#eff6ff;border:1px solid #bfdbfe;color:#2563eb;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 8px 18px rgba(37,99,235,.08)}
.f6-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:10px 0 12px}
.f6-kpi-card{background:#ffffff;border:1px solid #c8dcfb;border-radius:24px;padding:16px 14px;box-shadow:0 8px 20px rgba(15,45,90,.06);display:flex;align-items:center;gap:14px;text-align:left;min-height:100px;overflow:hidden;transition:box-shadow .18s}
.f6-kpi-card:hover{box-shadow:0 12px 28px rgba(15,45,90,.10)}
.f6-kpi-icon{width:56px;height:56px;border-radius:999px;background:#eff6ff;border:1.5px solid #bfdbfe;display:inline-flex;align-items:center;justify-content:center;flex:0 0 56px;color:#2563eb;box-shadow:0 6px 16px rgba(37,99,235,.07)}
.f6-kpi-label{color:#5b6bb0;font-size:13.5px;font-weight:900;margin-bottom:5px;text-transform:uppercase;letter-spacing:.03em}
.f6-kpi-value{color:#0a2444;font-size:19px;font-weight:900;line-height:1.1;word-break:break-word;margin-bottom:3px}
.f6-kpi-sub{color:#000000;font-size:10.5px;font-weight:400;margin-top:2px;min-height:14px}
.f6-badge{display:inline-block;border-radius:999px;padding:5px 14px;font-size:13px;font-weight:800;border:1px solid transparent}
.f6-badge-ok{background:#f0fdf4;color:#15803d;border-color:#bbf7d0}
.f6-badge-warn{background:#fffbeb;color:#b45309;border-color:#fde68a}
.f6-badge-bad{background:#fef2f2;color:#b91c1c;border-color:#fecaca}
@media(max-width:1200px){.f6-kpi-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.f6-kpi-grid{grid-template-columns:1fr}}
</style>
""",
    unsafe_allow_html=True,
)
render_dropdown_visibility_fix()

# -----------------------------------------------------------------------------
# Helpers Aurora (mismo idioma que F3) — card-head, KPI, divider, banner
# -----------------------------------------------------------------------------
def _render_card_header_native(title: str, icon_name: str, subtitle: str = "") -> None:
    """Card-head Aurora: squircle tintado (emoji/glifo o SVG) + título + subtítulo."""
    if icon_name and (not icon_name.isascii() or len(icon_name) <= 2):
        icon_html = f'<span class="aur-cicon-emoji">{_escape(icon_name)}</span>'
    else:
        icon_html = _safe_icon(icon_name, 22, "#0d9488")
    sub = f"<p>{_escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="aur-card-head"><div class="aur-cicon">{icon_html}</div>'
        f"<div><h2>{_escape(title)}</h2>{sub}</div></div>",
        unsafe_allow_html=True,
    )


def _render_kpi_card_native(icon_name: str, label: str, value: str, sub: str = "", kc: str = "#0d9488") -> None:
    """KPI Aurora: aro tintado (emoji/glifo o SVG) + label + valor + subtítulo."""
    if icon_name and (not icon_name.isascii() or len(icon_name) <= 2):
        icon_html = f'<span class="aur-ki-emoji">{_escape(icon_name)}</span>'
    else:
        icon_html = _safe_icon(icon_name, 24, kc)
    sub_html = f"<i>{_escape(sub)}</i>" if sub else ""
    st.markdown(
        f'<div class="aur-kpi" style="--kc:{kc}"><div class="aur-ki">{icon_html}</div>'
        f'<div class="aur-kpi-copy"><small>{_escape(label)}</small><b>{_escape(value)}</b>{sub_html}</div></div>',
        unsafe_allow_html=True,
    )


def _render_section_divider(icon: str, title: str, subtitle: str = "", color: str = "#0d9488") -> None:
    """Divider de grupo de sección (icono cuadrado tintado + título + sublínea + línea)."""
    sub = f"<small>{_escape(subtitle)}</small>" if subtitle else ""
    st.markdown(
        f'<div class="f6-divider" style="--dc:{color}">'
        f'<div class="dx">{_escape(icon)}</div>'
        f'<div><b>{_escape(title)}</b>{sub}</div>'
        f'<div class="dline"></div></div>',
        unsafe_allow_html=True,
    )


def _render_banner(text: str, tono: str = "info", icon: str = "ℹ️") -> None:
    """Banner Aurora con icono + texto, tonos ok/warn/bad/info."""
    if tono not in {"ok", "warn", "bad", "info"}:
        tono = "info"
    st.markdown(
        f'<div class="f6-banner {tono}"><span class="bx">{_escape(icon)}</span>{_escape(text)}</div>',
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Configuración (solo lecturas cacheadas; NINGÚN cómputo a nivel de página)
# -----------------------------------------------------------------------------
config = cargar_config()

# -----------------------------------------------------------------------------
# Hero
# -----------------------------------------------------------------------------
_F6_SCORE_AUDIT = st.session_state.get("f6_audit_score_pct")
_score_label = f"{_F6_SCORE_AUDIT:.1f}".replace(".", ",") if isinstance(_F6_SCORE_AUDIT, (int, float)) else "—"

with st.container(border=True, key="f6_card_header"):
    st.markdown(
        f"""
<div class="f6-hero">
  <svg class="f6-wind" viewBox="0 0 600 190" preserveAspectRatio="none">
    <path d="M0 42 Q150 24 300 44 T600 34"/>
    <path d="M0 100 Q180 82 340 102 T600 92"/>
    <path d="M0 156 Q140 142 300 158 T600 150"/>
  </svg>
  <div class="f6-hero-row">
    <div class="f6-hero-icon">🔬</div>
    <div class="f6-hero-text">
      <h1>Fase 6 · Estudios avanzados</h1>
      <p>IEC, terreno, clima frío, ruido, flicker, avifauna, huella CO₂, SCADA, red, híbrido, optimización y pre-auditoría.</p>
    </div>
    <div class="f6-hero-pills">
      <div class="f6-hpill"><b>13</b><span>Estudios</span></div>
      <div class="f6-hpill"><b>5</b><span>Secciones</span></div>
      <div class="f6-hpill"><b>{_score_label}</b><span>Score audit</span></div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

# -----------------------------------------------------------------------------
# Selector de sección (render condicional plano — sin fragments)
# -----------------------------------------------------------------------------
_F6_SECCIONES = [
    "Sitio y cumplimiento",
    "Ambiental",
    "Operación y red",
    "Optimización y fin de vida",
    "Auditoría",
]
_F6_SECCION_ICONOS = {
    "Sitio y cumplimiento": "🗺️",
    "Ambiental": "🌿",
    "Operación y red": "⚡",
    "Optimización y fin de vida": "🎯",
    "Auditoría": "📋",
}

# Deep-link opcional: ?sec=<nombre de sección> abre la página en esa sección.
try:
    _sec_qp = str(st.query_params.get("sec") or "").strip().lower()
    _sec_idx = next(
        (i for i, s in enumerate(_F6_SECCIONES) if _sec_qp and _sec_qp in s.lower()),
        0,
    )
except (ValueError, AttributeError):
    _sec_idx = 0

with st.container(border=True, key="f6_card_secciones"):
    _render_card_header_native(
        "Secciones de estudio",
        "🧭",
        "Cinco grupos · cada estudio corre bajo demanda",
    )
    seccion = st.radio(
        "Sección de estudios",
        _F6_SECCIONES,
        index=_sec_idx,
        horizontal=True,
        key="f6_seccion",
        label_visibility="collapsed",
        format_func=lambda s: f"{_F6_SECCION_ICONOS.get(s, '')} {s}",
    )

# Paleta y plantilla común de las gráficas de esta fase (estilo SMA 2.0).
_F6_AZUL = "#2563eb"
_F6_VERDE = "#16a34a"
_F6_AMBAR = "#d97706"
_F6_ROJO = "#dc2626"
_F6_GRIS = "#94a3b8"


# Acento teal Aurora para las gráficas de esta fase (paridad mockup 06_fase6).
_F6_TEAL = "#0d9488"
_F6_TEAL2 = "#115e59"
_F6_COLORWAY = ["#0d9488", "#16a34a", "#2563eb", "#d97706", "#dc2626", "#7c3aed"]


def _f6_fig_layout(fig, titulo: str, altura: int = 380):
    fig.update_layout(
        height=altura,
        margin={"l": 10, "r": 10, "t": 42, "b": 10},
        title={"text": titulo, "font": {"size": 15, "color": "#0a2444"}},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#0a2444", "family": "Segoe UI, system-ui, sans-serif"},
        colorway=_F6_COLORWAY,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1.0},
    )
    fig.update_xaxes(gridcolor="#eef4fb", zerolinecolor="#dce7f5", linecolor="#dce7f5")
    fig.update_yaxes(gridcolor="#eef4fb", zerolinecolor="#dce7f5", linecolor="#dce7f5")
    return fig


# -----------------------------------------------------------------------------
# Secciones (placeholders — los estudios se cablean por sección)
# -----------------------------------------------------------------------------
def _kpi_html(cards: list[tuple], n: int | None = None) -> str:
    """Grid de KPIs Aurora (aros tintados). Cada card: (icono, label, value, sub)
    o (icono, label, value, sub, kc) para color de aro propio.
    """
    n = n if n else len(cards)
    parts = [f'<div class="f6-kgrid" style="--n:{n}">']
    for card in cards:
        icon, label, value, sub = card[0], card[1], card[2], card[3]
        kc = card[4] if len(card) > 4 else "#0d9488"
        emoji = _f6_emoji_for(icon)
        if emoji and (not emoji.isascii() or len(emoji) <= 2):
            icon_html = f'<span class="aur-ki-emoji">{_escape(emoji)}</span>'
        else:
            icon_html = _safe_icon(icon, 24, kc)
        sub_html = f"<i>{_escape(sub)}</i>" if sub else ""
        parts.append(
            f'<div class="aur-kpi" style="--kc:{kc}"><div class="aur-ki">{icon_html}</div>'
            f'<div class="aur-kpi-copy"><small>{_escape(label)}</small>'
            f'<b>{_escape(value)}</b>{sub_html}</div></div>'
        )
    parts.append("</div>")
    return "".join(parts)


# Iconos de banner por tono (paridad mockup .banner .bx)
_F6_BANNER_ICON = {"ok": "✅", "warn": "⚠️", "bad": "⚠️", "info": "ℹ️"}


def _badge_html(texto: str, tono: str = "ok") -> str:
    """Banner Aurora (icono + texto) — paridad mockup .banner."""
    if tono not in {"ok", "warn", "bad", "info"}:
        tono = "ok"
    icon = _F6_BANNER_ICON.get(tono, "ℹ️")
    return (
        f'<div class="f6-banner {tono}"><span class="bx">{icon}</span>'
        f"<span>{_escape(texto)}</span></div>"
    )


def _render_card_iec() -> None:
    import calculos_iec_site as iec

    with st.container(border=True, key="f6_card_iec"):
        _section_header(
            "Idoneidad del sitio (IEC 61400-1 Ed.4)",
            "V_ref, V_50, V_e1/V_e50 desde Weibull del sitio + turbulencia efectiva Frandsen por sector.",
            "target",
        )
        clase_decl = str(config.get("f5_iec_clase_declarada") or "II")
        turb_decl = str(config.get("f5_iec_turb_declarada") or "B")
        st.caption(
            f"Clase declarada en Fase 5: **{clase_decl}** · subclase TI **{turb_decl}**. "
            "Este estudio amplía la validación rápida de Fase 5 con velocidades extremas y Frandsen sectorial."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            n_vecinos = st.number_input(
                "Turbinas vecinas por sector", min_value=0, max_value=10,
                value=2, step=1, key="f6_iec_n_vecinos",
                help="N de turbinas que generan turbulencia de estela en el sector (Frandsen).",
            )
        with c2:
            dist_d = st.number_input(
                "Distancia entre turbinas (D)", min_value=1.0, max_value=20.0,
                value=_cfg_float(config, "f4_dx_D", 5.0), step=0.5, key="f6_iec_dist_d",
            )
        with c3:
            ct_iec = st.number_input(
                "Ct de la turbina", min_value=0.05, max_value=1.2,
                value=_cfg_float(config, "f4_ct", 0.8), step=0.05, key="f6_iec_ct",
            )

        if st.button("Evaluar idoneidad IEC", key="f6_iec_btn", type="primary"):
            with st.spinner("Calculando Weibull del sitio y TI sectorial…"):
                serie = _get_serie_horaria_parque()
                if serie is None:
                    st.session_state["f6_iec_result"] = {"error": "Sin serie de viento. Cargue datos NASA en Fase 2."}
                else:
                    from calculos import ajustar_weibull_por_momentos

                    df_a = serie["df_analisis"]
                    ws = pd.to_numeric(df_a["WS_ANALISIS"], errors="coerce")
                    k_site, c_site = ajustar_weibull_por_momentos(ws)
                    ti_dict = iec.ti_sectorial_observada(df_a)
                    frandsen = iec.site_suitability_summary_from_sectorial(
                        ti_dict, n_neighbors=int(n_vecinos), ct=float(ct_iec), distance_D=float(dist_d)
                    )
                    ti_eff = frandsen.get("ti_eff_max")
                    if ti_eff is None or ti_eff != ti_eff:
                        ti_eff = _cfg_float(config, "f5_ambient_ti", 0.14) * 1.1
                    summary = iec.site_suitability_summary(k_site, c_site, ti_eff)
                    st.session_state["f6_iec_result"] = {
                        "summary": summary,
                        "frandsen": frandsen,
                        "ti_dict": ti_dict,
                        "k": k_site,
                        "c": c_site,
                        "clase_decl": clase_decl,
                    }
            st.caption(_F6_SERIE_CAPTION)

        res = st.session_state.get("f6_iec_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        summary = res["summary"]
        st.markdown(
            _kpi_html([
                ("🏷️", "Clase IEC del sitio", str(summary.get("Clase IEC", "—")),
                 f"declarada: {res.get('clase_decl', '—')}", "#dc2626"),
                ("σ", "Subclase TI", str(summary.get("Subclase TI", "—")),
                 f"TI_eff(15) = {summary.get('TI_eff(15)', float('nan')):.3f}", "#d97706"),
                ("💨", "V_ave del sitio", f"{summary.get('V_ave (m/s)', float('nan')):.2f} m/s",
                 f"Weibull k={res.get('k', float('nan')):.2f}, c={res.get('c', float('nan')):.2f}", "#2563eb"),
                ("🌪️", "V_ref (50 años)", f"{summary.get('V_ref (m/s)', float('nan')):.2f} m/s",
                 f"V_50 = {summary.get('V_50 (m/s)', float('nan')):.2f} m/s", "#0d9488"),
            ]),
            unsafe_allow_html=True,
        )

        decl = res.get("clase_decl", "")
        if decl in iec.IEC_CLASS_LIMITS:
            checks = [
                summary.get(f"Clase {decl} — {param} (limite={lim})", "OK")
                for param, lim in iec.IEC_CLASS_LIMITS[decl].items()
            ]
            ok_decl = all(v == "OK" for v in checks)
            st.markdown(
                _badge_html(
                    f"El sitio {'CUMPLE' if ok_decl else 'EXCEDE'} los límites de la clase declarada {decl}",
                    "ok" if ok_decl else "bad",
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(_badge_html("Clase declarada S: requiere diseño específico del fabricante", "warn"), unsafe_allow_html=True)

        import plotly.graph_objects as go

        # Velocidades del sitio vs límites de cada clase IEC (visual de cumplimiento).
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            clases = list(iec.IEC_CLASS_LIMITS.keys())
            fig_lim = go.Figure()
            fig_lim.add_bar(
                x=clases, y=[iec.IEC_CLASS_LIMITS[c]["V_ave"] for c in clases],
                name="Límite V_ave", marker_color="#99f6e4",
            )
            fig_lim.add_bar(
                x=clases, y=[iec.IEC_CLASS_LIMITS[c]["V_ref"] for c in clases],
                name="Límite V_ref", marker_color="#5eead4",
            )
            v_ave_sitio = float(summary.get("V_ave (m/s)", float("nan")))
            v_ref_sitio = float(summary.get("V_ref (m/s)", float("nan")))
            fig_lim.add_hline(y=v_ave_sitio, line_dash="dash", line_color=_F6_VERDE,
                              annotation_text=f"V_ave sitio {v_ave_sitio:.1f}",
                              annotation_font_color=_F6_VERDE)
            fig_lim.add_hline(y=v_ref_sitio, line_dash="dash", line_color=_F6_ROJO,
                              annotation_text=f"V_ref sitio {v_ref_sitio:.1f}",
                              annotation_font_color=_F6_ROJO)
            fig_lim.update_layout(barmode="group", yaxis_title="m/s")
            st.plotly_chart(_f6_fig_layout(fig_lim, "Sitio vs límites de clase IEC", 380),
                            use_container_width=True, key="f6_iec_limites")
        with col_g2:
            ti_dict = res.get("ti_dict") or {}
            fr_sector = (res.get("frandsen") or {}).get("ti_eff_por_sector") or {}
            sectores = [s for s in ti_dict if ti_dict.get(s) == ti_dict.get(s)]
            if sectores:
                fig_ti = go.Figure()
                fig_ti.add_trace(go.Barpolar(
                    r=[ti_dict[s] for s in sectores], theta=sectores,
                    name="TI observada", marker_color=_F6_TEAL, opacity=0.78,
                ))
                fr_vals = [fr_sector.get(s) for s in sectores]
                if any(v == v for v in fr_vals if v is not None):
                    fig_ti.add_trace(go.Barpolar(
                        r=fr_vals, theta=sectores,
                        name="TI efectiva (Frandsen)", marker_color=_F6_TEAL2, opacity=0.5,
                    ))
                fig_ti.update_layout(polar={"radialaxis": {"tickfont": {"size": 9}}})
                st.plotly_chart(_f6_fig_layout(fig_ti, "Rosa de turbulencia por sector", 380),
                                use_container_width=True, key="f6_iec_rosa_ti")

        filas_lim = []
        for clase_id, limits in iec.IEC_CLASS_LIMITS.items():
            fila = {"Clase": clase_id}
            for param, lim in limits.items():
                fila[f"{param} límite (m/s)"] = lim
                fila[f"{param} estado"] = summary.get(f"Clase {clase_id} — {param} (limite={lim})", "—")
            filas_lim.append(fila)
        with st.expander("Tablas de detalle (límites por clase y TI por sector)"):
            st.dataframe(pd.DataFrame(filas_lim), hide_index=True, use_container_width=True)
            df_ti = pd.DataFrame({
                "Sector": list(ti_dict.keys()),
                "TI observada": [ti_dict.get(s) for s in ti_dict],
                "TI efectiva (Frandsen)": [fr_sector.get(s) for s in ti_dict],
            })
            st.dataframe(df_ti, hide_index=True, use_container_width=True)
        st.caption(
            "Estimadores rápidos (Tubino 2014, Frandsen). No sustituyen un site assessment certificado."
        )


def _render_card_flow() -> None:
    with st.container(border=True, key="f6_card_flow"):
        _section_header(
            "Flujo sobre terreno (modelo lineal Jackson-Hunt)",
            "Speedup orográfico aproximado sobre colinas suaves (pendientes < 15°). No sustituye WAsP/CFD.",
            "waves",
        )
        st.caption(
            "Suba la elevación del terreno como grid 2-D numérico: `.npy` o `.csv` sin encabezados "
            "(exportable desde QGIS como ASCII/CSV). El pipeline GeoTIFF/rasterio no está instalado."
        )
        dem_file = st.file_uploader("Grid de elevación (.csv / .npy)", type=["csv", "npy"], key="f6_flow_dem")
        c1, c2, c3 = st.columns(3)
        with c1:
            pixel_m = st.number_input(
                "Tamaño de celda (m)", min_value=1.0, max_value=1000.0,
                value=_cfg_float(config, "f6_flow_pixel_m", 30.0), step=1.0, key="f6_flow_pixel",
            )
        with c2:
            l_hill_in = st.number_input(
                "L_hill (m) — 0 = automático", min_value=0.0, max_value=10000.0,
                value=_cfg_float(config, "f6_flow_l_hill_m", 0.0), step=50.0, key="f6_flow_lhill",
                help="Longitud característica de las colinas. 0 lo estima desde el tamaño del grid.",
            )
        with c3:
            h_hub_flow = _cfg_float(config, "f5_altura_deseada", _cfg_float(config, "perfil_hhub", 80.0))
            st.metric("Altura de buje (Fase 5)", f"{h_hub_flow:.0f} m")

        if st.button("Calcular speedup orográfico", key="f6_flow_btn", type="primary", disabled=dem_file is None):
            import io

            import linear_flow_model as lfm

            try:
                if dem_file.name.lower().endswith(".npy"):
                    dem = np.load(io.BytesIO(dem_file.getvalue()), allow_pickle=False)
                else:
                    dem = pd.read_csv(io.BytesIO(dem_file.getvalue()), header=None).apply(
                        pd.to_numeric, errors="coerce"
                    ).to_numpy(dtype=float)
                dem = np.asarray(dem, dtype=float)
                if dem.ndim != 2 or min(dem.shape) < 5:
                    st.session_state["f6_flow_result"] = {"error": "El archivo no es un grid 2-D válido (mínimo 5×5 celdas)."}
                elif dem.size > 4_000_000:
                    st.session_state["f6_flow_result"] = {"error": f"Grid demasiado grande ({dem.shape[0]}×{dem.shape[1]}). Máximo ~4M celdas — reduzca la resolución."}
                else:
                    with st.spinner("Calculando campo de speedup…"):
                        l_hill = float(l_hill_in) if l_hill_in > 0 else lfm.estimar_L_hill_desde_dem(dem, float(pixel_m))
                        out = lfm.calcular_speedup_field_lineal(dem, float(pixel_m), h_hub_flow, l_hill)
                        df_layout = cargar_layout_parque()
                        df_turb = None
                        if df_layout is not None and len(df_layout) > 0:
                            df_turb = lfm.aplicar_speedup_lineal_a_turbinas(df_layout, out["speedup_field"])
                        st.session_state["f6_flow_result"] = {
                            "stats": out["stats"],
                            "speedup_field": out["speedup_field"],
                            "df_turb": df_turb,
                        }
                        guardar_config_values({
                            "f6_flow_pixel_m": float(pixel_m),
                            "f6_flow_l_hill_m": float(l_hill),
                        })
            except Exception as exc:
                st.session_state["f6_flow_result"] = {"error": f"No se pudo leer el grid: {exc}"}

        res = st.session_state.get("f6_flow_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        stats = res["stats"]
        st.markdown(
            _kpi_html([
                ("arrow", "Speedup medio", f"{stats.get('speedup_media', float('nan')):.3f}",
                 f"σ = {stats.get('speedup_std', float('nan')):.3f}"),
                ("activity", "Speedup máximo", f"{stats.get('speedup_max', float('nan')):.3f}",
                 f"mínimo = {stats.get('speedup_min', float('nan')):.3f}"),
                ("waves", "Pendiente p95", f"{stats.get('slope_p95_deg', float('nan')):.1f}°",
                 f"máxima = {stats.get('slope_max_deg', float('nan')):.1f}°"),
                ("target-height", "L_hill usado", f"{stats.get('L_hill_usado_m', float('nan')):,.0f} m",
                 f"buje = {stats.get('h_hub_usado_m', float('nan')):.0f} m"),
            ]),
            unsafe_allow_html=True,
        )
        if stats.get("slope_p95_deg", 0.0) > 15.0:
            st.markdown(
                _badge_html("Pendiente p95 > 15°: el modelo lineal NO es válido en este terreno — use CFD/WindNinja", "bad"),
                unsafe_allow_html=True,
            )

        import plotly.graph_objects as go

        field = res["speedup_field"]
        step = max(1, int(max(field.shape) / 400))
        fig = go.Figure(go.Heatmap(
            z=field[::step, ::step], zmid=1.0,
            colorscale=[[0, "#eff6ff"], [0.5, "#5eead4"], [1.0, "#0d9488"]],
            colorbar={"title": "Speedup"},
        ))
        fig.update_layout(
            height=420, margin={"l": 10, "r": 10, "t": 30, "b": 10},
            title={"text": "Campo de speedup orográfico", "font": {"size": 15, "color": "#0a2444"}},
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis={"scaleanchor": "x", "autorange": "reversed"},
        )
        st.plotly_chart(fig, use_container_width=True, key="f6_flow_heatmap")

        if res.get("df_turb") is not None:
            st.markdown("**Speedup por turbina** (layout de Fase 4, centrado en el grid):")
            st.dataframe(res["df_turb"], hide_index=True, use_container_width=True)


def _render_card_cold() -> None:
    with st.container(border=True, key="f6_card_cold"):
        _section_header(
            "Clima frío / icing (IEA Wind Task 19)",
            "Horas anuales con formación de hielo y derate del AEP neto.",
            "calendar",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            altitud = st.number_input(
                "Altitud del sitio (m)", min_value=0.0, max_value=6000.0,
                value=_cfg_float(config, "f5_altitud_sitio_m", 0.0), step=50.0, key="f6_cold_altitud",
            )
        with c2:
            severidad = st.selectbox(
                "Severidad del icing", ["ligera", "moderada", "severa"], index=1, key="f6_cold_severidad",
            )
        with c3:
            aep_base = st.number_input(
                "AEP neta base (MWh/año)", min_value=0.0,
                value=_cfg_float(config, "f5_aep_neta_total_mwh", 0.0), step=100.0, key="f6_cold_aep",
            )

        if st.button("Analizar clima frío", key="f6_cold_btn", type="primary"):
            import cold_climate

            with st.spinner("Analizando serie de temperatura…"):
                df_nasa = cargar_nasa_hourly()
                st.session_state["f6_cold_result"] = cold_climate.analizar_cold_climate_completo(
                    df_nasa, float(aep_base), altitud_m=float(altitud), severidad=str(severidad)
                )

        res = st.session_state.get("f6_cold_result")
        if not res:
            return
        if not res.get("aplica"):
            st.info(res.get("razon", "No aplica para este sitio."))
            return

        icing = res.get("icing", {})
        derate = res.get("derate", {})
        _criterios_es = {
            "T2M + WS50M + RH2M": "temperatura + viento + humedad",
            "T2M + WS50M (RH estimada)": "temperatura + viento (humedad estimada)",
            "estimacion_altitud_T2M_ausente": "estimación por altitud (sin temperatura)",
            "sin_datos": "sin datos",
        }
        criterio_txt = _criterios_es.get(str(icing.get("criterio_principal", "")), str(icing.get("criterio_principal", "")))
        st.markdown(
            _kpi_html([
                ("clock", "Horas de icing/año", f"{icing.get('horas_icing_anuales', 0):,}",
                 f"{icing.get('fraccion_anio_pct', 0.0):.1f}% del año"),
                ("trending-down", "Pérdida de AEP", f"{derate.get('perdida_aep_pct', 0.0):.2f}%",
                 f"{derate.get('aep_perdida_mwh', 0.0):,.0f} MWh/año"),
                ("bolt", "AEP corregida", f"{derate.get('aep_corregida_mwh', 0.0):,.0f} MWh/año",
                 f"severidad: {derate.get('severidad', '—')}"),
                ("info", "Criterio de detección", criterio_txt, derate.get("descripcion", "")),
            ]),
            unsafe_allow_html=True,
        )

        import plotly.graph_objects as go

        fig = go.Figure(go.Pie(
            labels=["AEP corregida", "Pérdida por icing"],
            values=[max(0.0, derate.get("aep_corregida_mwh", 0.0)), max(0.0, derate.get("aep_perdida_mwh", 0.0))],
            hole=0.62, marker={"colors": [_F6_VERDE, "#fbbf24"]},
            textinfo="label+percent",
        ))
        st.plotly_chart(_f6_fig_layout(fig, "Impacto del icing sobre el AEP neto", 330),
                        use_container_width=True, key="f6_cold_dona")


def _render_sitio_cumplimiento() -> None:
    _render_card_iec()
    _render_card_flow()
    _render_card_cold()


_RECEPTORES_DEFAULT = [
    {"receptor_id": "R1", "nombre": "Vivienda 1", "x_m": 800.0, "y_m": 0.0},
    {"receptor_id": "R2", "nombre": "Vivienda 2", "x_m": -600.0, "y_m": 400.0},
]


def _cargar_receptores_config() -> pd.DataFrame:
    raw = config.get("f6_receptores_json") or ""
    try:
        data = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        data = []
    if not data:
        data = _RECEPTORES_DEFAULT
    df = pd.DataFrame(data)
    for col, default in (("receptor_id", ""), ("nombre", ""), ("x_m", 0.0), ("y_m", 0.0)):
        if col not in df.columns:
            df[col] = default
    return df[["receptor_id", "nombre", "x_m", "y_m"]]


def _receptores_desde_df(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        rid = str(r.get("receptor_id") or "").strip()
        try:
            x = float(r.get("x_m"))
            y = float(r.get("y_m"))
        except (TypeError, ValueError):
            continue
        if not rid:
            continue
        out.append({"receptor_id": rid, "nombre": str(r.get("nombre") or rid), "x_m": x, "y_m": y})
    return out


def _render_card_receptores() -> pd.DataFrame:
    with st.container(border=True, key="f6_card_receptores"):
        _section_header(
            "Receptores sensibles",
            "Viviendas/edificaciones cercanas en coordenadas (m) relativas al centro del parque. Los usan los estudios de ruido y shadow flicker.",
            "map-pin",
        )
        df_rec = st.data_editor(
            _cargar_receptores_config(),
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="f6_receptores_editor",
            column_config={
                "receptor_id": st.column_config.TextColumn("ID"),
                "nombre": st.column_config.TextColumn("Nombre"),
                "x_m": st.column_config.NumberColumn("x (m)", format="%.0f"),
                "y_m": st.column_config.NumberColumn("y (m)", format="%.0f"),
            },
        )
        if st.button("Guardar receptores", key="f6_receptores_guardar"):
            guardar_config_values({"f6_receptores_json": json.dumps(_receptores_desde_df(df_rec))})
            st.success("Receptores guardados en el proyecto.")

        # Mapa interactivo: turbinas del layout (Fase 4) + receptores editados.
        df_layout = cargar_layout_parque()
        receptores = _receptores_desde_df(df_rec)
        if (df_layout is not None and len(df_layout)) or receptores:
            import plotly.graph_objects as go

            fig = go.Figure()
            if df_layout is not None and len(df_layout):
                fig.add_scatter(
                    x=df_layout["x_m"], y=df_layout["y_m"], mode="markers+text",
                    text=df_layout["turbina_id"], textposition="top center",
                    marker={"symbol": "x", "size": 13, "color": _F6_AZUL,
                            "line": {"width": 1, "color": "#1e3a8a"}},
                    name="Turbinas",
                )
            if receptores:
                fig.add_scatter(
                    x=[r["x_m"] for r in receptores], y=[r["y_m"] for r in receptores],
                    mode="markers+text",
                    text=[r["receptor_id"] for r in receptores], textposition="bottom center",
                    marker={"symbol": "circle", "size": 12, "color": _F6_ROJO,
                            "line": {"width": 1.5, "color": "#7f1d1d"}},
                    name="Receptores",
                )
            fig.update_layout(yaxis={"scaleanchor": "x", "title": "y (m)"}, xaxis={"title": "x (m)"})
            st.plotly_chart(_f6_fig_layout(fig, "Parque y receptores (coordenadas relativas)", 420),
                            use_container_width=True, key="f6_receptores_mapa")
        return df_rec


def _render_card_ruido(df_receptores: pd.DataFrame) -> None:
    with st.container(border=True, key="f6_card_ruido"):
        _section_header(
            "Ruido ISO 9613-2",
            "Nivel de presión sonora LpA en cada receptor: divergencia esférica + absorción atmosférica + efecto suelo.",
            "activity",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            lwa = st.number_input(
                "Potencia sonora LwA por turbina (dB(A))", min_value=80.0, max_value=120.0,
                value=_cfg_float(config, "f6_ruido_lwa_db", 105.0), step=0.5, key="f6_ruido_lwa",
                help="Típico turbina 2-4 MW: 104-108 dB(A). Dato del fabricante.",
            )
        with c2:
            lim_dia = st.number_input(
                "Límite diurno (dB(A))", min_value=30.0, max_value=80.0,
                value=_cfg_float(config, "f6_ruido_lim_diurno", 50.0), step=1.0, key="f6_ruido_dia",
            )
        with c3:
            lim_noche = st.number_input(
                "Límite nocturno (dB(A))", min_value=25.0, max_value=70.0,
                value=_cfg_float(config, "f6_ruido_lim_nocturno", 40.0), step=1.0, key="f6_ruido_noche",
            )
        with st.expander("Condiciones atmosféricas"):
            ca, cb = st.columns(2)
            with ca:
                temp_c = st.number_input("Temperatura (°C)", -20.0, 50.0, _cfg_float(config, "f5_temperatura_media_c", 20.0), 1.0, key="f6_ruido_temp")
            with cb:
                hum_pct = st.number_input("Humedad relativa (%)", 10.0, 100.0, 70.0, 5.0, key="f6_ruido_hum")

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            calc_tabla = st.button("Calcular LpA en receptores", key="f6_ruido_btn", type="primary")
        with col_b2:
            calc_mapa = st.button("Generar mapa de ruido", key="f6_ruido_mapa_btn",
                                  help="Grid de 900 receptores virtuales alrededor del parque (toma unos segundos).")

        h_hub = _cfg_float(config, "f5_altura_deseada", _cfg_float(config, "perfil_hhub", 80.0))
        df_layout = cargar_layout_parque()
        receptores = _receptores_desde_df(df_receptores)

        if calc_tabla or calc_mapa:
            import ruido_iso9613

            if df_layout is None or len(df_layout) == 0:
                st.session_state["f6_ruido_result"] = {"error": "Sin layout de turbinas. Defina el arreglo en Fase 4."}
            elif calc_tabla and not receptores:
                st.session_state["f6_ruido_result"] = {"error": "Agregue al menos un receptor en la tarjeta de arriba."}
            else:
                prev = st.session_state.get("f6_ruido_result") or {}
                if calc_tabla:
                    with st.spinner("Calculando propagación sonora…"):
                        df_lpa = ruido_iso9613.calcular_LpA_receptores(
                            df_layout, float(lwa), receptores,
                            altura_emisor=h_hub, temperatura_c=float(temp_c), humedad_pct=float(hum_pct),
                            limite_diurno_db=float(lim_dia), limite_nocturno_db=float(lim_noche),
                        )
                    prev = {**prev, "df": df_lpa, "error": None}
                    guardar_config_values({
                        "f6_ruido_lwa_db": float(lwa),
                        "f6_ruido_lim_diurno": float(lim_dia),
                        "f6_ruido_lim_nocturno": float(lim_noche),
                        "f5_ruido_max_db": float(df_lpa["lpA_db"].max()) if len(df_lpa) else "",
                    })
                if calc_mapa:
                    with st.spinner("Generando mapa de ruido (grid 30×30)…"):
                        df_grid = ruido_iso9613.crear_mapa_ruido_grid(
                            df_layout, float(lwa), grid_extent_m=2000, grid_resolution=30,
                            altura_emisor=h_hub, temperatura_c=float(temp_c), humedad_pct=float(hum_pct),
                        )
                    prev = {**prev, "grid": df_grid, "error": None}
                st.session_state["f6_ruido_result"] = prev

        res = st.session_state.get("f6_ruido_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        df_lpa = res.get("df")
        if df_lpa is not None and len(df_lpa):
            lp_max = float(df_lpa["lpA_db"].max())
            ok_dia = bool(df_lpa["cumple_diurno"].all())
            ok_noche = bool(df_lpa["cumple_nocturno"].all())
            st.markdown(
                _kpi_html([
                    ("activity", "LpA máximo", f"{lp_max:.1f} dB(A)",
                     f"receptor más expuesto de {len(df_lpa)}"),
                    ("info", "Límite diurno", f"{float(lim_dia):.0f} dB(A)", "CUMPLE" if ok_dia else "EXCEDE"),
                    ("clock", "Límite nocturno", f"{float(lim_noche):.0f} dB(A)", "CUMPLE" if ok_noche else "EXCEDE"),
                    ("map-pin", "Distancia mínima", f"{float(df_lpa['distancia_min_m'].min()):,.0f} m",
                     "turbina más cercana a un receptor"),
                ]),
                unsafe_allow_html=True,
            )
            st.markdown(
                _badge_html(
                    "Todos los receptores cumplen ambos límites" if (ok_dia and ok_noche)
                    else "Hay receptores que exceden algún límite — revise distancias o modo de operación reducido",
                    "ok" if (ok_dia and ok_noche) else "bad",
                ),
                unsafe_allow_html=True,
            )

            import plotly.graph_objects as go

            colores = [
                _F6_VERDE if (cd and cn) else (_F6_AMBAR if cd else _F6_ROJO)
                for cd, cn in zip(df_lpa["cumple_diurno"], df_lpa["cumple_nocturno"])
            ]
            fig_r = go.Figure(go.Bar(
                x=df_lpa["lpA_db"], y=df_lpa["nombre"], orientation="h",
                marker_color=colores, text=[f"{v:.1f}" for v in df_lpa["lpA_db"]],
                textposition="outside", name="LpA",
            ))
            fig_r.add_vline(x=float(lim_dia), line_dash="dash", line_color=_F6_AMBAR,
                            annotation_text=f"Diurno {float(lim_dia):.0f}", annotation_font_color=_F6_AMBAR)
            fig_r.add_vline(x=float(lim_noche), line_dash="dot", line_color=_F6_AZUL,
                            annotation_text=f"Nocturno {float(lim_noche):.0f}", annotation_font_color=_F6_AZUL)
            fig_r.update_layout(xaxis_title="LpA dB(A)", showlegend=False)
            st.plotly_chart(_f6_fig_layout(fig_r, "Nivel sonoro por receptor vs límites",
                                           max(300, 90 + 46 * len(df_lpa))),
                            use_container_width=True, key="f6_ruido_barras")

            df_show = df_lpa.rename(columns={
                "receptor_id": "Receptor", "nombre": "Nombre", "x_m": "x (m)", "y_m": "y (m)",
                "lpA_db": "LpA dB(A)", "cumple_diurno": "Diurno", "cumple_nocturno": "Nocturno",
                "distancia_min_m": "Dist. mín. (m)",
            })
            df_show["Diurno"] = df_show["Diurno"].map({True: "✅ Cumple", False: "❌ Excede"})
            df_show["Nocturno"] = df_show["Nocturno"].map({True: "✅ Cumple", False: "❌ Excede"})
            with st.expander("Tabla de detalle por receptor"):
                st.dataframe(df_show, hide_index=True, use_container_width=True)

        df_grid = res.get("grid")
        if df_grid is not None and len(df_grid):
            import plotly.graph_objects as go

            piv = df_grid.pivot_table(index="y_m", columns="x_m", values="lpA_db")
            fig = go.Figure(go.Heatmap(
                z=piv.values, x=piv.columns, y=piv.index,
                colorscale="YlOrRd", colorbar={"title": "dB(A)"},
            ))
            if df_layout is not None and len(df_layout):
                fig.add_scatter(
                    x=df_layout["x_m"], y=df_layout["y_m"], mode="markers",
                    marker={"symbol": "x", "size": 10, "color": "#1e3a8a"}, name="Turbinas",
                )
            fig.update_layout(height=460, margin={"l": 10, "r": 10, "t": 30, "b": 10},
                              title="Mapa de ruido LpA", yaxis={"scaleanchor": "x"})
            st.plotly_chart(fig, use_container_width=True, key="f6_ruido_heatmap")


def _render_card_flicker(df_receptores: pd.DataFrame) -> None:
    import importlib.util

    with st.container(border=True, key="f6_card_flicker"):
        _section_header(
            "Shadow flicker",
            "Horas anuales de parpadeo de sombra del rotor sobre cada receptor (límite habitual: 30 h/año).",
            "clock",
        )
        pvlib_ok = importlib.util.find_spec("pvlib") is not None
        if not pvlib_ok:
            st.warning("Este estudio necesita la posición solar de `pvlib`, que no está instalado.")
            st.caption("Sugerencia: `pip install pvlib` y reinicie la aplicación.")

        c1, c2, c3 = st.columns(3)
        with c1:
            lim_h = st.number_input(
                "Límite anual (h/año)", min_value=1.0, max_value=200.0,
                value=_cfg_float(config, "f6_flicker_limite_h", 30.0), step=1.0, key="f6_flicker_lim",
            )
        with c2:
            alt_rec = st.number_input("Altura del receptor (m)", 0.5, 30.0, 1.5, 0.5, key="f6_flicker_alt_rec")
        with c3:
            diametro = _cfg_float(config, "diametro", 100.0)
            h_hub = _cfg_float(config, "f5_altura_deseada", _cfg_float(config, "perfil_hhub", 80.0))
            st.metric("Rotor / buje (Fases 1 y 5)", f"Ø {diametro:.0f} m · {h_hub:.0f} m")

        if st.button("Calcular shadow flicker", key="f6_flicker_btn", type="primary", disabled=not pvlib_ok):
            import shadow_flicker

            receptores = _receptores_desde_df(df_receptores)
            df_layout = cargar_layout_parque()
            serie = _get_serie_horaria_parque()
            if df_layout is None or len(df_layout) == 0:
                st.session_state["f6_flicker_result"] = {"error": "Sin layout de turbinas. Defina el arreglo en Fase 4."}
            elif not receptores:
                st.session_state["f6_flicker_result"] = {"error": "Agregue al menos un receptor en la tarjeta de arriba."}
            elif serie is None:
                st.session_state["f6_flicker_result"] = {"error": "Sin serie de viento. Cargue datos NASA en Fase 2."}
            else:
                df_a = serie["df_analisis"]
                # Solo el último año (8760 h): la serie NASA abarca varios años y
                # el conteo del módulo no anualiza por sí mismo.
                df_a1 = df_a.tail(8760)
                with st.spinner("Calculando posición solar y sombras (último año de la serie)…"):
                    df_fl = shadow_flicker.calcular_horas_flicker_anual(
                        df_layout, receptores,
                        pd.to_datetime(df_a1["timestamp"], errors="coerce"),
                        df_a1["WS_ANALISIS"],
                        _cfg_float(config, "nasa_lat", 0.0), _cfg_float(config, "nasa_lon", 0.0),
                        diametro, h_hub, altura_receptor=float(alt_rec),
                        altitud_m=_cfg_float(config, "f5_altitud_sitio_m", 0.0),
                    )
                if df_fl is None or len(df_fl) == 0:
                    st.session_state["f6_flicker_result"] = {"error": "No se pudo calcular (¿pvlib instalado? ¿timestamps válidos?)."}
                else:
                    st.session_state["f6_flicker_result"] = {"df": df_fl, "lim": float(lim_h)}
                    guardar_config_values({
                        "f6_flicker_limite_h": float(lim_h),
                        "f5_flicker_max_h": float(df_fl["horas_flicker_anuales"].max()),
                    })

        res = st.session_state.get("f6_flicker_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        df_fl = res["df"]
        lim_usado = res.get("lim", 30.0)
        peor = df_fl.loc[df_fl["horas_flicker_anuales"].idxmax()]
        ok_todos = bool((df_fl["horas_flicker_anuales"] <= lim_usado).all())
        st.markdown(
            _kpi_html([
                ("clock", "Máximo anual", f"{int(peor['horas_flicker_anuales'])} h/año",
                 f"receptor {peor['receptor_id']}"),
                ("info", "Límite aplicado", f"{lim_usado:.0f} h/año",
                 "CUMPLEN todos" if ok_todos else "HAY EXCEDENCIAS"),
                ("layout", "Turbinas implicadas", str(int(peor["n_turbinas_contribuyen"])),
                 "en el receptor más afectado"),
                ("map-pin", "Receptores evaluados", str(len(df_fl)), ""),
            ]),
            unsafe_allow_html=True,
        )
        st.markdown(
            _badge_html(
                "Todos los receptores dentro del límite" if ok_todos
                else "Excedencias de flicker — considere shutdown programado en horas críticas",
                "ok" if ok_todos else "bad",
            ),
            unsafe_allow_html=True,
        )

        import plotly.graph_objects as go

        fig_f = go.Figure(go.Bar(
            x=df_fl["horas_flicker_anuales"], y=df_fl["nombre"], orientation="h",
            marker_color=[_F6_VERDE if h <= lim_usado else _F6_ROJO for h in df_fl["horas_flicker_anuales"]],
            text=[f"{int(h)} h" for h in df_fl["horas_flicker_anuales"]], textposition="outside",
        ))
        fig_f.add_vline(x=lim_usado, line_dash="dash", line_color=_F6_AMBAR,
                        annotation_text=f"Límite {lim_usado:.0f} h/año", annotation_font_color=_F6_AMBAR)
        fig_f.update_layout(xaxis_title="Horas de flicker al año", showlegend=False)
        st.plotly_chart(_f6_fig_layout(fig_f, "Shadow flicker por receptor",
                                       max(300, 90 + 46 * len(df_fl))),
                        use_container_width=True, key="f6_flicker_barras")

        df_show = df_fl.rename(columns={
            "receptor_id": "Receptor", "nombre": "Nombre", "x_m": "x (m)", "y_m": "y (m)",
            "horas_flicker_anuales": "Horas/año", "porcentaje_anio": "% del año",
            "n_turbinas_contribuyen": "Turbinas", "turbinas_contrib": "Cuáles",
            "cumple_limite_30h": "Cumple",
        })
        df_show["Cumple"] = df_show["Cumple"].map({True: "✅ Sí", False: "❌ No"})
        with st.expander("Tabla de detalle por receptor"):
            st.dataframe(df_show, hide_index=True, use_container_width=True)
        st.caption("Geometría simplificada (peor caso, sin nubosidad). " + _F6_SERIE_CAPTION)


def _render_card_aves() -> None:
    import bird_collision_band as bird

    with st.container(border=True, key="f6_card_aves"):
        _section_header(
            "Colisión de avifauna (Band 2007)",
            "Colisiones esperadas por especie según tasa de paso, geometría del rotor y probabilidad de evasión.",
            "wind",
        )
        raw = config.get("f6_aves_tabla_json") or ""
        try:
            data = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            data = []
        if data:
            df_aves_base = pd.DataFrame(data)
        else:
            df_aves_base = bird.get_aves_default_dataframe()
        if "n_aves_paso_anual" not in df_aves_base.columns:
            df_aves_base["n_aves_paso_anual"] = 100.0

        cols = ["especie", "n_aves_paso_anual", "longitud_m", "envergadura_m", "velocidad_vuelo_ms", "p_evasion"]
        df_aves_base = df_aves_base[[c for c in cols if c in df_aves_base.columns]]

        df_aves = st.data_editor(
            df_aves_base,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="f6_aves_editor",
            column_config={
                "especie": st.column_config.TextColumn("Especie"),
                "n_aves_paso_anual": st.column_config.NumberColumn("Pasos/año", format="%.0f",
                                                                   help="Aves observadas cruzando el parque por año"),
                "longitud_m": st.column_config.NumberColumn("Longitud (m)", format="%.2f"),
                "envergadura_m": st.column_config.NumberColumn("Envergadura (m)", format="%.2f"),
                "velocidad_vuelo_ms": st.column_config.NumberColumn("Vel. vuelo (m/s)", format="%.0f"),
                "p_evasion": st.column_config.NumberColumn("P. evasión", format="%.2f",
                                                           help="0.90-0.99 según especie (SNH)"),
            },
        )
        c1, c2 = st.columns(2)
        with c1:
            horas_op = st.number_input("Horas de operación/año", 1000.0, 8760.0, 8000.0, 100.0, key="f6_aves_horas_op")
        with c2:
            if st.button("Guardar tabla de especies", key="f6_aves_guardar"):
                guardar_config_values({"f6_aves_tabla_json": json.dumps(df_aves.to_dict("records"))})
                st.success("Tabla de especies guardada.")

        if st.button("Estimar colisiones anuales", key="f6_aves_btn", type="primary"):
            n_turbinas = max(1, int(_cfg_float(config, "f5_n_turbinas", _cfg_float(config, "f4_num_turbinas", 1.0))))
            diametro = _cfg_float(config, "diametro", 100.0)
            h_hub = _cfg_float(config, "f5_altura_deseada", _cfg_float(config, "perfil_hhub", 80.0))
            df_col = bird.estimar_colisiones_anuales_parque(
                df_aves, n_turbinas, diametro, h_hub, tiempo_operacion_h=float(horas_op),
            )
            if df_col is None or len(df_col) == 0:
                st.session_state["f6_aves_result"] = {"error": "Sin especies con pasos/año > 0."}
            else:
                st.session_state["f6_aves_result"] = {"df": df_col}

        res = st.session_state.get("f6_aves_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        df_col = res["df"]
        total = float(df_col["colisiones_parque_anio"].sum())
        peor_cat = "ALTO" if (df_col["riesgo_categoria"] == "ALTO").any() else (
            "MEDIO" if (df_col["riesgo_categoria"] == "MEDIO").any() else "BAJO"
        )
        st.markdown(
            _kpi_html([
                ("wind", "Colisiones parque", f"{total:.2f} aves/año", f"{len(df_col)} especies evaluadas"),
                ("info", "Riesgo máximo", peor_cat, "Band 2007, escala BAJO/MEDIO/ALTO"),
                ("layout", "Peor especie", str(df_col.loc[df_col["colisiones_parque_anio"].idxmax(), "especie"])[:40],
                 f"{float(df_col['colisiones_parque_anio'].max()):.2f} colisiones/año"),
                ("clock", "Operación", f"{float(horas_op):,.0f} h/año", ""),
            ]),
            unsafe_allow_html=True,
        )
        st.markdown(
            _badge_html(
                {"BAJO": "Riesgo de colisión BAJO", "MEDIO": "Riesgo MEDIO — considerar monitoreo",
                 "ALTO": "Riesgo ALTO — requiere plan de mitigación"}[peor_cat],
                {"BAJO": "ok", "MEDIO": "warn", "ALTO": "bad"}[peor_cat],
            ),
            unsafe_allow_html=True,
        )

        import plotly.graph_objects as go

        _col_riesgo = {"BAJO": _F6_VERDE, "MEDIO": _F6_AMBAR, "ALTO": _F6_ROJO}
        fig_a = go.Figure(go.Bar(
            x=df_col["colisiones_parque_anio"], y=df_col["especie"], orientation="h",
            marker_color=[_col_riesgo.get(r, _F6_GRIS) for r in df_col["riesgo_categoria"]],
            text=[f"{v:.2f}" for v in df_col["colisiones_parque_anio"]], textposition="outside",
        ))
        fig_a.update_layout(xaxis_title="Colisiones esperadas en el parque (aves/año)", showlegend=False)
        st.plotly_chart(_f6_fig_layout(fig_a, "Riesgo de colisión por especie (Band 2007)",
                                       max(300, 90 + 44 * len(df_col))),
                        use_container_width=True, key="f6_aves_barras")

        df_show = df_col.rename(columns={
            "especie": "Especie", "n_aves_paso_anual": "Pasos/año", "p_evasion": "P. evasión",
            "colisiones_turbina_anio": "Colisiones/turbina·año", "colisiones_parque_anio": "Colisiones/parque·año",
            "p_geometrica": "P. geométrica", "p_paso_altura_rotor": "P. altura rotor",
            "riesgo_categoria": "Riesgo",
        })
        with st.expander("Tabla de detalle por especie"):
            st.dataframe(df_show, hide_index=True, use_container_width=True)


def _render_card_lca() -> None:
    import lca_carbon

    with st.container(border=True, key="f6_card_lca"):
        _section_header(
            "Huella de carbono (LCA, ISO 14040)",
            "Emisiones de ciclo de vida del proyecto, CO₂ evitado frente a la red y payback de carbono.",
            "globe",
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            cap_mw = st.number_input("Capacidad (MW)", 0.0, 5000.0,
                                     _cfg_float(config, "f5_potencia_instalada_mw", 0.0), 1.0, key="f6_lca_cap")
        with c2:
            aep = st.number_input("AEP neta (MWh/año)", 0.0, 10_000_000.0,
                                  _cfg_float(config, "f5_aep_neta_total_mwh", 0.0), 100.0, key="f6_lca_aep")
        with c3:
            vida = st.number_input("Vida útil (años)", 5.0, 40.0,
                                   _cfg_float(config, "f5_vida_util_anios", 20.0), 1.0, key="f6_lca_vida")
        with c4:
            grid_opt = st.selectbox(
                "Red de comparación",
                ["Colombia (210 g/kWh)", "EE.UU. (380 g/kWh)", "UE (230 g/kWh)"],
                key="f6_lca_grid",
            )
        grid_factor = {"Colombia (210 g/kWh)": 210.0, "EE.UU. (380 g/kWh)": 380.0, "UE (230 g/kWh)": 230.0}[grid_opt]

        if cap_mw <= 0 or aep <= 0:
            st.info("Complete la Fase 5 (capacidad instalada y AEP neta) o escriba los valores arriba.")
            return

        res = lca_carbon.calcular_huella_carbono_proyecto(
            cap_mw, aep, vida_util_anios=vida, grid_emission_factor_g_kwh=grid_factor,
        )
        arboles = lca_carbon.calcular_co2_equivalente_arboles(res["co2_evitado_anual_tCO2eq"])
        st.markdown(
            _kpi_html([
                ("globe", "Huella del proyecto", f"{res['huella_g_kwh']:.1f} gCO₂eq/kWh",
                 "referencia eólica onshore: ~11"),
                ("trending-down", "CO₂ evitado", f"{res['co2_evitado_anual_tCO2eq']:,.0f} t/año",
                 f"{res['co2_evitado_lifetime_tCO2eq']:,.0f} t en {vida:.0f} años"),
                ("clock", "Payback de carbono", f"{res['payback_co2_anios']:.2f} años",
                 "tiempo en compensar el CO₂ de construcción"),
                ("waves", "Equivalente en árboles", f"{arboles['n_arboles_equivalentes_anuales']:,}",
                 f"≈ {arboles['hectareas_bosque_equivalentes']:,.0f} ha de bosque/año"),
            ]),
            unsafe_allow_html=True,
        )
        import plotly.graph_objects as go

        _comp_es = {
            "manufactura_turbina": "Manufactura turbinas", "transporte": "Transporte",
            "instalacion": "Instalación", "om_lifetime": "O&M (vida útil)",
            "transmision_local": "Transmisión local", "desmantelamiento": "Desmantelamiento",
        }
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            fig_d = go.Figure(go.Pie(
                labels=[_comp_es.get(k, k) for k in res["desglose_componentes"]],
                values=list(res["desglose_componentes"].values()),
                hole=0.58, textinfo="label+percent",
                marker={"colors": ["#1d4ed8", "#3b82f6", "#60a5fa", "#93c5fd", "#bfdbfe", "#dbeafe"]},
            ))
            st.plotly_chart(_f6_fig_layout(fig_d, "Desglose de la huella (gCO₂eq/kWh)", 360),
                            use_container_width=True, key="f6_lca_dona")
        with col_l2:
            df_alt = lca_carbon.comparar_vs_alternativas(res["huella_g_kwh"])
            es_proy = df_alt["Tecnología"].str.contains("referencia")
            fig_c = go.Figure(go.Bar(
                x=df_alt["gCO2eq/kWh"], y=df_alt["Tecnología"], orientation="h",
                marker_color=[_F6_VERDE if p else _F6_GRIS for p in es_proy],
                text=[f"{v:.0f}" for v in df_alt["gCO2eq/kWh"]], textposition="outside",
            ))
            fig_c.add_vline(x=res["huella_g_kwh"], line_dash="dash", line_color=_F6_VERDE,
                            annotation_text=f"Este proyecto {res['huella_g_kwh']:.1f}",
                            annotation_font_color=_F6_VERDE)
            fig_c.update_layout(xaxis={"type": "log", "title": "gCO₂eq/kWh (escala log)"}, showlegend=False)
            st.plotly_chart(_f6_fig_layout(fig_c, "Comparación con otras tecnologías", 360),
                            use_container_width=True, key="f6_lca_comparativa")

        with st.expander("Tablas de detalle"):
            st.dataframe(df_alt, hide_index=True, use_container_width=True)
            df_desglose = pd.DataFrame(
                [{"Componente": _comp_es.get(k, k), "gCO₂eq/kWh": v} for k, v in res["desglose_componentes"].items()]
            )
            st.dataframe(df_desglose, hide_index=True, use_container_width=True)


def _render_ambiental() -> None:
    df_receptores = _render_card_receptores()
    _render_card_ruido(df_receptores)
    _render_card_flicker(df_receptores)
    _render_card_aves()
    _render_card_lca()


def _n_years_serie(df_h: pd.DataFrame) -> float:
    n = len(df_h)
    return max(n / 8760.0, 1e-9) if n else 1.0


def _render_card_scada() -> None:
    with st.container(border=True, key="f6_card_scada"):
        _section_header(
            "Validación contra SCADA",
            "Compara la producción modelada con datos reales de operación: bias, RMSE y R² hora a hora.",
            "database",
        )
        st.caption(
            "Suba un CSV/Excel de SCADA con columnas `timestamp` y `P_kW` (o `P_MW`); "
            "opcional `turbine_id` (se agregan todas las turbinas por hora)."
        )
        scada_file = st.file_uploader("Archivo SCADA (.csv / .xlsx)", type=["csv", "xlsx", "xls"], key="f6_scada_file")

        df_scada = None
        if scada_file is not None:
            import validacion_scada

            try:
                df_scada = validacion_scada.importar_scada_csv(scada_file.getvalue(), scada_file.name)
                st.caption(
                    f"SCADA leído: {len(df_scada):,} filas · {df_scada['turbine_id'].nunique()} turbina(s) · "
                    f"{df_scada['timestamp'].min()} → {df_scada['timestamp'].max()}"
                )
            except ValueError as exc:
                st.error(str(exc))

        if st.button("Comparar contra el modelo", key="f6_scada_btn", type="primary", disabled=df_scada is None):
            import validacion_scada

            serie = _get_serie_horaria_parque()
            if serie is None:
                st.session_state["f6_scada_result"] = {"error": "Sin serie modelada. Cargue datos NASA en Fase 2."}
            else:
                with st.spinner("Alineando series y calculando métricas…"):
                    df_parque_real = validacion_scada.agregar_scada_a_parque_horario(df_scada)
                    res = validacion_scada.comparar_modelado_vs_real(serie["df_horario"], df_parque_real)
                st.session_state["f6_scada_result"] = res

        res = st.session_state.get("f6_scada_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return
        if not res.get("ok"):
            st.warning(f"{res.get('msg', 'Overlap insuficiente')} (n={res.get('n_samples', 0)}). "
                       "Verifique que las fechas del SCADA coincidan con la serie NASA.")
            return

        st.markdown(
            _kpi_html([
                ("activity", "R²", f"{res['r2']:.3f}", f"{res['n_samples']:,} horas comparadas"),
                ("trending-down", "Bias", f"{res['bias_MW']:+.2f} MW",
                 "real − modelo (negativo = modelo optimista)"),
                ("sigma", "RMSE", f"{res['rmse_MW']:.2f} MW", f"MAE = {res['mae_MW']:.2f} MW"),
                ("bolt", "Ratio de eficiencia", f"{res['efficiency_ratio']:.3f}",
                 f"energía real/modelo = {res['energia_real_MWh']:,.0f}/{res['energia_modelo_MWh']:,.0f} MWh"),
            ]),
            unsafe_allow_html=True,
        )
        tono = "ok" if 0.95 <= res["efficiency_ratio"] <= 1.05 else ("warn" if 0.90 <= res["efficiency_ratio"] <= 1.10 else "bad")
        st.markdown(
            _badge_html(f"Desviación modelo vs real: {(res['efficiency_ratio'] - 1) * 100:+.1f}%", tono),
            unsafe_allow_html=True,
        )

        import plotly.graph_objects as go

        dfc = res["df_compare"]
        muestras = dfc.sample(min(len(dfc), 3000), random_state=7) if len(dfc) > 3000 else dfc
        p_max = float(max(muestras["P_modelo_MW"].max(), muestras["P_real_MW"].max()))
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            fig = go.Figure()
            fig.add_scatter(x=muestras["P_modelo_MW"], y=muestras["P_real_MW"], mode="markers",
                            marker={"size": 5, "opacity": 0.35, "color": _F6_AZUL}, name="Horas")
            fig.add_scatter(x=[0, p_max], y=[0, p_max], mode="lines",
                            line={"dash": "dash", "color": _F6_ROJO}, name="1:1")
            fig.update_layout(xaxis_title="Modelo (MW)", yaxis_title="Real (MW)")
            st.plotly_chart(_f6_fig_layout(fig, "Potencia modelo vs real", 400),
                            use_container_width=True, key="f6_scada_scatter")
        with col_s2:
            fig_h = go.Figure(go.Histogram(
                x=dfc["residual_MW"], nbinsx=40, marker_color="#93c5fd",
                marker_line={"width": 1, "color": _F6_AZUL},
            ))
            fig_h.add_vline(x=0, line_color=_F6_GRIS)
            fig_h.add_vline(x=res["bias_MW"], line_dash="dash", line_color=_F6_ROJO,
                            annotation_text=f"bias {res['bias_MW']:+.2f} MW",
                            annotation_font_color=_F6_ROJO)
            fig_h.update_layout(xaxis_title="Residual real − modelo (MW)", yaxis_title="Horas")
            st.plotly_chart(_f6_fig_layout(fig_h, "Distribución de residuales", 400),
                            use_container_width=True, key="f6_scada_hist")
        st.caption(_F6_SERIE_CAPTION)


def _render_card_curtailment() -> None:
    with st.container(border=True, key="f6_card_curtail"):
        _section_header(
            "Curtailment de red",
            "Pérdidas por límite de inyección, recorte económico (precio < costo variable) y disponibilidad de la red.",
            "🔌",
        )
        pot_inst = _cfg_float(config, "f5_potencia_instalada_mw", 0.0)
        c1, c2, c3 = st.columns(3)
        with c1:
            cap_iny = st.number_input(
                "Capacidad de inyección (MW)", min_value=0.1, max_value=5000.0,
                value=_cfg_float(config, "f6_cap_inyeccion_mw", round(pot_inst * 0.8, 1) if pot_inst > 0 else 10.0),
                step=0.5, key="f6_curt_cap",
                help="Límite del punto de conexión (STN/SDL).",
            )
        with c2:
            disp_red = st.number_input(
                "Disponibilidad de red (%)", min_value=80.0, max_value=100.0,
                value=_cfg_float(config, "f6_disp_red_pct", 98.0), step=0.5, key="f6_curt_disp",
            )
        with c3:
            cv_usd = st.number_input(
                "Costo variable (USD/MWh)", min_value=0.0, max_value=100.0, value=5.0, step=1.0,
                key="f6_curt_cv", help="Si el precio de bolsa simulado cae por debajo, no se inyecta.",
            )

        if st.button("Simular curtailment", key="f6_curt_btn", type="primary"):
            import grid_curtailment

            serie = _get_serie_horaria_parque()
            if serie is None:
                st.session_state["f6_curt_result"] = {"error": "Sin serie de viento. Cargue datos NASA en Fase 2."}
            else:
                with st.spinner("Simulando restricciones de red sobre la serie horaria…"):
                    df_curt = grid_curtailment.construir_serie_curtailment_completa(
                        serie["df_horario"], float(cap_iny),
                        costo_variable_usd_mwh=float(cv_usd),
                        factor_disponibilidad_red_pct=float(disp_red),
                    )
                    kpis = grid_curtailment.calcular_kpis_curtailment(df_curt)
                df_mes = None
                if "timestamp" in df_curt.columns:
                    tmp = df_curt.copy()
                    tmp["timestamp"] = pd.to_datetime(tmp["timestamp"], errors="coerce")
                    tmp = tmp.dropna(subset=["timestamp"])
                    if len(tmp):
                        tmp["mes"] = tmp["timestamp"].dt.month
                        df_mes = tmp.groupby("mes")[
                            ["energia_recortada_capacity_MWh", "energia_recortada_economica_MWh",
                             "energia_recortada_downtime_MWh"]
                        ].sum() / _n_years_serie(df_curt)
                st.session_state["f6_curt_result"] = {"kpis": kpis, "df_mes": df_mes,
                                                      "n_years": _n_years_serie(df_curt)}
                guardar_config_values({
                    "f6_cap_inyeccion_mw": float(cap_iny),
                    "f6_disp_red_pct": float(disp_red),
                })

        res = st.session_state.get("f6_curt_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        kpis = res["kpis"]
        ny = res.get("n_years", 1.0)
        st.markdown(
            _kpi_html([
                ("bolt", "Energía inyectada", f"{kpis['energia_final_inyectada_MWh'] / ny:,.0f} MWh/año",
                 f"de {kpis['energia_bruta_MWh'] / ny:,.0f} MWh/año generables"),
                ("trending-down", "Recorte total", f"{kpis['pct_recorte_total']:.2f}%",
                 f"{kpis['energia_recortada_total_MWh'] / ny:,.0f} MWh/año perdidos"),
                ("layout", "Por capacidad", f"{kpis['pct_recorte_capacity']:.2f}%",
                 f"{int(kpis['horas_curtailed_capacity'] / ny):,} h/año limitadas"),
                ("info", "Económico + red", f"{kpis['pct_recorte_economico']:.2f}% + {kpis['pct_recorte_downtime']:.2f}%",
                 f"{int(kpis['horas_curtailed_economico'] / ny):,} h/año bajo costo variable"),
            ]),
            unsafe_allow_html=True,
        )
        st.caption("Precio de bolsa simulado (lognormal ~45 USD/MWh) — conecte datos XM reales para análisis fino.")

        import plotly.graph_objects as go

        ny_k = res.get("n_years", 1.0)
        col_c1, col_c2 = st.columns([1, 1.6])
        with col_c1:
            e_cap = kpis["pct_recorte_capacity"]
            e_eco = kpis["pct_recorte_economico"]
            e_red = kpis["pct_recorte_downtime"]
            fig_dona = go.Figure(go.Pie(
                labels=["Inyectada", "Recorte capacidad", "Recorte económico", "Recorte red"],
                values=[max(0.0, 100.0 - e_cap - e_eco - e_red), e_cap, e_eco, e_red],
                hole=0.6, textinfo="label+percent",
                marker={"colors": [_F6_VERDE, _F6_AZUL, _F6_AMBAR, _F6_ROJO]},
            ))
            st.plotly_chart(_f6_fig_layout(fig_dona, "Reparto de la energía generable", 380),
                            use_container_width=True, key="f6_curt_dona")
        with col_c2:
            if res.get("df_mes") is not None and len(res["df_mes"]):
                df_mes = res["df_mes"]
                meses_lbl = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
                fig = go.Figure()
                for col, nombre, color in (
                    ("energia_recortada_capacity_MWh", "Capacidad", _F6_AZUL),
                    ("energia_recortada_economica_MWh", "Económico", _F6_AMBAR),
                    ("energia_recortada_downtime_MWh", "Red caída", _F6_ROJO),
                ):
                    fig.add_bar(x=[meses_lbl[m - 1] for m in df_mes.index], y=df_mes[col], name=nombre,
                                marker_color=color)
                fig.update_layout(barmode="stack", yaxis_title="MWh/año")
                st.plotly_chart(_f6_fig_layout(fig, "Energía recortada por mes", 380),
                                use_container_width=True, key="f6_curt_bar")


def _render_card_hibrido() -> None:
    import importlib.util

    with st.container(border=True, key="f6_card_hibrido"):
        _section_header(
            "Planta híbrida (viento + solar + BESS)",
            "Barrido de capacidad solar complementaria sobre la misma conexión y dimensionado preliminar de baterías.",
            "🔋",
        )
        if importlib.util.find_spec("pvlib") is None:
            st.caption(
                "ℹ️ `pvlib` no está instalado: el perfil solar usa una aproximación sinusoidal. "
                "Para cielo claro real: `pip install pvlib`."
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            cap_iny_h = st.number_input(
                "Capacidad de inyección (MW)", min_value=0.1, max_value=5000.0,
                value=_cfg_float(config, "f6_cap_inyeccion_mw",
                                 round(_cfg_float(config, "f5_potencia_instalada_mw", 10.0) * 0.8, 1) or 10.0),
                step=0.5, key="f6_hib_cap",
            )
        with c2:
            solar_max = st.slider("Capacidad solar máxima a evaluar (MW)", 5, 200,
                                  50, 5, key="f6_hib_solar_max")
        with c3:
            bess_usd = st.number_input("Costo BESS (USD/kWh)", 50.0, 1000.0, 300.0, 25.0, key="f6_hib_bess")

        if st.button("Analizar planta híbrida", key="f6_hib_btn", type="primary"):
            import hybrid_plant

            serie = _get_serie_horaria_parque()
            if serie is None:
                st.session_state["f6_hib_result"] = {"error": "Sin serie de viento. Cargue datos NASA en Fase 2."}
            else:
                df_h = serie["df_horario"]
                with st.spinner("Barriendo capacidades solares sobre la serie horaria…"):
                    res_h = hybrid_plant.analizar_hibrido_completo(
                        df_h["potencia_parque_MW"].to_numpy(dtype=float),
                        float(cap_iny_h),
                        _cfg_float(config, "nasa_lat", 0.0), _cfg_float(config, "nasa_lon", 0.0),
                        capacidad_solar_max_mw=int(solar_max),
                        timestamps=pd.to_datetime(df_h["timestamp"], errors="coerce"),
                        costo_bess_usd_kwh=float(bess_usd),
                    )
                if not res_h:
                    st.session_state["f6_hib_result"] = {"error": "No se pudo ejecutar el barrido solar."}
                else:
                    res_h["n_years"] = _n_years_serie(df_h)
                    st.session_state["f6_hib_result"] = res_h

        res = st.session_state.get("f6_hib_result")
        if not res:
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        ny = res.get("n_years", 1.0)
        storage = res.get("storage") or {}
        st.markdown(
            _kpi_html([
                ("bolt", "Solar recomendado", f"{res['recomendacion_solar_mw']:.0f} MW",
                 "máxima inyección con curtailment < 10%"),
                ("activity", "Energía inyectada", f"{res['energia_inyectada_recomendada_MWh'] / ny:,.0f} MWh/año",
                 f"curtailment {res['curtailment_pct_recomendado']:.1f}%"),
                ("database", "BESS sugerido", f"{storage.get('capacidad_bess_MWh', 0.0):,.1f} MWh",
                 f"CAPEX ≈ {storage.get('capex_bess_usd', 0.0) / 1e6:,.1f} MUSD"),
                ("clock", "Energía desplazable", f"{storage.get('energia_potencial_shift_anual_MWh', 0.0) / ny:,.0f} MWh/año",
                 f"round-trip {storage.get('eficiencia_round_trip_pct', 0):.0f}%"),
            ]),
            unsafe_allow_html=True,
        )

        import plotly.graph_objects as go

        sweep = res["sweep_solar"]
        fig = go.Figure()
        fig.add_scatter(x=sweep["capacidad_solar_MW"], y=sweep["energia_inyectada_MWh"] / ny,
                        mode="lines+markers", name="Inyectada (MWh/año)", line={"color": "#2563eb"})
        fig.add_scatter(x=sweep["capacidad_solar_MW"], y=sweep["curtailment_pct"],
                        mode="lines+markers", name="Curtailment (%)", yaxis="y2",
                        line={"color": "#dc2626", "dash": "dot"})
        fig.add_vline(x=res["recomendacion_solar_mw"], line_dash="dash", line_color="#16a34a")
        fig.update_layout(
            height=400, margin={"l": 10, "r": 10, "t": 30, "b": 10},
            title="Barrido de capacidad solar",
            xaxis_title="Capacidad solar (MW)",
            yaxis={"title": "Energía inyectada (MWh/año)"},
            yaxis2={"title": "Curtailment (%)", "overlaying": "y", "side": "right"},
        )
        st.plotly_chart(fig, use_container_width=True, key="f6_hib_sweep")
        st.caption(_F6_SERIE_CAPTION)


def _render_operacion_red() -> None:
    _render_card_scada()
    _render_card_curtailment()
    _render_card_hibrido()


def _render_card_optimizador() -> None:
    with st.container(border=True, key="f6_card_optim"):
        _section_header(
            "Optimizador de layout (Differential Evolution)",
            "Busca posiciones de turbinas que maximizan el AEP usando el motor de estelas de 16 sectores como función objetivo.",
            "layout",
        )
        df_layout = cargar_layout_parque()
        if df_layout is None or len(df_layout) == 0:
            st.info("Defina primero el arreglo de turbinas en Fase 4.")
            return

        n_turb = len(df_layout)
        xs = df_layout["x_m"].astype(float)
        ys = df_layout["y_m"].astype(float)
        margen_x = max(200.0, (xs.max() - xs.min()) * 0.2)
        margen_y = max(200.0, (ys.max() - ys.min()) * 0.2)
        bounds_xy = ((float(xs.min() - margen_x), float(xs.max() + margen_x)),
                     (float(ys.min() - margen_y), float(ys.max() + margen_y)))

        c1, c2, c3 = st.columns(3)
        with c1:
            maxiter = st.slider("Iteraciones (maxiter)", 1, 30,
                                int(_cfg_float(config, "f6_opt_maxiter", 5.0)), 1, key="f6_opt_maxiter_w")
        with c2:
            popsize = st.slider("Población (popsize)", 4, 20, 6, 1, key="f6_opt_popsize")
        with c3:
            min_sp = st.slider("Separación mínima (D)", 2.0, 8.0, 3.0, 0.5, key="f6_opt_minsp")

        evals_est = popsize * 2 * n_turb * (maxiter + 1)
        st.warning(
            f"⏱️ Cada evaluación corre el motor de estelas completo (5-15 s). Con esta configuración son "
            f"~{evals_est:,} evaluaciones → puede tardar **muchos minutos u horas**. Empiece con valores bajos "
            f"y deje la ventana abierta. Área de búsqueda: x∈[{bounds_xy[0][0]:,.0f}, {bounds_xy[0][1]:,.0f}] m, "
            f"y∈[{bounds_xy[1][0]:,.0f}, {bounds_xy[1][1]:,.0f}] m ({n_turb} turbinas)."
        )

        if st.button("Optimizar layout", key="f6_opt_btn", type="primary"):
            import time as _time

            import layout_optimizer as lopt

            df_nasa = cargar_nasa_hourly()
            if df_nasa is None or len(df_nasa) == 0:
                st.session_state["f6_opt_result"] = {"error": "Sin datos NASA. Cargue la serie en Fase 2."}
            else:
                from calculos import preparar_datos_curva

                df_curva = preparar_datos_curva(cargar_tabla_curva())
                diametro = _cfg_float(config, "diametro", 100.0)
                ct = _cfg_float(config, "f4_ct", 0.8)
                kw = _cfg_float(config, "f4_kw", 0.075)
                ambient_ti = _cfg_float(config, "f5_ambient_ti", 0.10)
                h_hub = _cfg_float(config, "f5_altura_deseada", _cfg_float(config, "perfil_hhub", 80.0))
                try:
                    with st.status("Optimizando layout…", expanded=True) as status:
                        t0 = _time.perf_counter()
                        arr_orig = df_layout[["x_m", "y_m"]].to_numpy(dtype=float).flatten()
                        aep_orig = lopt.evaluar_aep_layout(
                            arr_orig, n_turb, df_curva, df_nasa, diametro, ct, kw,
                            ambient_ti=ambient_ti, h_hub=h_hub,
                        )
                        t_eval = _time.perf_counter() - t0
                        status.write(
                            f"AEP del layout actual: {aep_orig:,.0f} MWh/año · "
                            f"1 evaluación = {t_eval:.1f} s → estimado total ≈ {evals_est * t_eval / 60.0:,.0f} min"
                        )

                        def _cb(it, aep_it):
                            status.write(f"Generación {it}/{maxiter}: mejor AEP = {aep_it:,.0f} MWh/año")

                        df_opt, aep_opt, history = lopt.optimizar_layout_scipy(
                            n_turb, df_curva, df_nasa, diametro, ct, kw,
                            bounds_xy, min_spacing_D=float(min_sp), max_iter=int(maxiter),
                            ambient_ti=ambient_ti, h_hub=h_hub, popsize=int(popsize),
                            callback=_cb,
                        )
                        status.update(label="Optimización terminada", state="complete")
                    st.session_state["f6_opt_result"] = {
                        "df_opt": df_opt, "aep_opt": float(aep_opt), "aep_orig": float(aep_orig),
                        "history": history, "df_orig": df_layout.copy(),
                    }
                    guardar_config_values({"f6_opt_maxiter": int(maxiter)})
                except RuntimeError as exc:
                    st.session_state["f6_opt_result"] = {"error": f"{exc} — el optimizador requiere scipy."}

        res = st.session_state.get("f6_opt_result")
        if not res:
            return
        if res.get("error"):
            st.error(res["error"])
            return

        aep_o, aep_n = res["aep_orig"], res["aep_opt"]
        delta_pct = (aep_n - aep_o) / aep_o * 100.0 if aep_o > 0 else 0.0
        st.markdown(
            _kpi_html([
                ("layout", "AEP layout actual", f"{aep_o:,.0f} MWh/año", "según motor de estelas 16 sectores"),
                ("activity", "AEP optimizado", f"{aep_n:,.0f} MWh/año", ""),
                ("arrow", "Mejora", f"{delta_pct:+.2f}%", f"{aep_n - aep_o:+,.0f} MWh/año"),
                ("target", "Turbinas", str(len(res["df_opt"])), "mismo número que Fase 4"),
            ]),
            unsafe_allow_html=True,
        )

        import plotly.graph_objects as go

        hist = res.get("history") or {}
        col_a, col_b = st.columns(2)
        with col_a:
            if hist.get("iter"):
                fig_h = go.Figure(go.Scatter(x=hist["iter"], y=hist["best_aep"],
                                             mode="lines+markers", line={"color": "#2563eb"}))
                fig_h.update_layout(height=360, margin={"l": 10, "r": 10, "t": 30, "b": 10},
                                    title="Convergencia", xaxis_title="Generación",
                                    yaxis_title="Mejor AEP (MWh/año)")
                st.plotly_chart(fig_h, use_container_width=True, key="f6_opt_conv")
        with col_b:
            fig_m = go.Figure()
            fig_m.add_scatter(x=res["df_orig"]["x_m"], y=res["df_orig"]["y_m"], mode="markers+text",
                              text=res["df_orig"]["turbina_id"], textposition="top center",
                              marker={"size": 12, "color": "#94a3b8", "symbol": "circle"}, name="Actual")
            fig_m.add_scatter(x=res["df_opt"]["x_m"], y=res["df_opt"]["y_m"], mode="markers+text",
                              text=res["df_opt"]["turbina_id"], textposition="bottom center",
                              marker={"size": 12, "color": "#2563eb", "symbol": "x"}, name="Optimizado")
            fig_m.update_layout(height=360, margin={"l": 10, "r": 10, "t": 30, "b": 10},
                                title="Layout antes vs después", yaxis={"scaleanchor": "x"})
            st.plotly_chart(fig_m, use_container_width=True, key="f6_opt_map")

        st.dataframe(res["df_opt"], hide_index=True, use_container_width=True)
        nombre_esc = st.text_input("Nombre del escenario", value="Layout optimizado (DE)", key="f6_opt_nombre")
        if st.button("Guardar como escenario de Fase 4", key="f6_opt_guardar"):
            from db import guardar_escenario_parque

            guardar_escenario_parque(
                str(nombre_esc).strip() or "Layout optimizado (DE)",
                res["df_opt"],
                {"origen": "f6_optimizador", "maxiter": int(_cfg_float(config, "f6_opt_maxiter", 5.0))},
                {"aep_optimizado_mwh": aep_n, "aep_original_mwh": aep_o, "delta_pct": delta_pct},
            )
            st.success("Escenario guardado — compárelo en Fase 4 (el layout activo NO se modifica).")


def _render_card_repowering() -> None:
    import repowering_analysis as repo

    with st.container(border=True, key="f6_card_repower"):
        _section_header(
            "Fin de vida: decommission · repowering · life extension",
            "Comparación de NPV de los tres caminos al final de la vida útil del parque.",
            "trending-down",
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            cap_mw = st.number_input("Capacidad (MW)", 0.0, 5000.0,
                                     _cfg_float(config, "f5_potencia_instalada_mw", 0.0), 1.0, key="f6_rep_cap")
        with c2:
            aep = st.number_input("AEP actual (MWh/año)", 0.0, 10_000_000.0,
                                  _cfg_float(config, "f5_aep_neta_total_mwh", 0.0), 100.0, key="f6_rep_aep")
        with c3:
            tasa = st.number_input("Tasa de descuento (%)", 1.0, 25.0,
                                   _cfg_float(config, "f5_tasa_descuento_pct", 8.0), 0.5, key="f6_rep_tasa")
        with c4:
            ppa = st.number_input("Precio PPA (USD/MWh)", 10.0, 300.0,
                                  _cfg_float(config, "f5_precio_energia_mwh", 60.0), 1.0, key="f6_rep_ppa")

        if cap_mw <= 0 or aep <= 0:
            st.info("Complete la Fase 5 (capacidad y AEP) o escriba los valores arriba.")
            return

        df_esc, recomendado = repo.comparar_escenarios_fin_vida(cap_mw, aep, tasa, ppa)
        etiquetas = {"decommission": "Desmantelar", "repowering": "Repotenciar", "life_extension": "Extender vida"}
        st.markdown(
            _badge_html(f"Escenario recomendado por NPV: {etiquetas.get(recomendado, recomendado)}", "ok"),
            unsafe_allow_html=True,
        )
        df_show = df_esc.copy()
        df_show["Escenario"] = df_show["Escenario"].map(etiquetas).fillna(df_show["Escenario"])
        st.dataframe(
            df_show,
            hide_index=True,
            use_container_width=True,
            column_config={
                "CAPEX (USD)": st.column_config.NumberColumn(format="%.0f"),
                "AEP post (MWh/año)": st.column_config.NumberColumn(format="%.0f"),
                "FCF anual (USD)": st.column_config.NumberColumn(format="%.0f"),
                "NPV (USD)": st.column_config.NumberColumn(format="%.0f"),
            },
        )

        import plotly.graph_objects as go

        fig = go.Figure(go.Bar(
            x=[etiquetas.get(e, e) for e in df_esc["Escenario"]],
            y=df_esc["NPV (USD)"],
            marker_color=["#16a34a" if e == recomendado else "#94a3b8" for e in df_esc["Escenario"]],
        ))
        fig.update_layout(height=340, margin={"l": 10, "r": 10, "t": 30, "b": 10},
                          title="NPV por escenario (USD)")
        st.plotly_chart(fig, use_container_width=True, key="f6_rep_bar")
        st.caption(
            "Supuestos por defecto: decommission 40k USD/MW (scrap 15k), repowering 900k USD/MW con +30% AEP y 25 años, "
            "life extension 200k USD/MW con −5% AEP y 10 años."
        )


def _render_optimizacion() -> None:
    _render_card_optimizador()
    _render_card_repowering()


def _render_auditoria() -> None:
    import pre_audit_checklist as audit

    with st.container(border=True, key="f6_card_audit"):
        _section_header(
            "Pre-audit checklist (estilo DNV)",
            "Chequeo automático de calidad del análisis antes de pagar un auditor externo. Score ≥ 85 = listo.",
            "table",
        )
        cfg_fresh = cargar_config()
        ctx = audit.construir_contexto_desde_config_sma(cfg_fresh)
        # Glue de página: si la tabla de aves se guardó o se calculó en esta
        # sesión, el riesgo de colisión cuenta como evaluado.
        if cfg_fresh.get("f6_aves_tabla_json") or st.session_state.get("f6_aves_result"):
            ctx["bird_collision_evaluado"] = True

        df_audit = audit.ejecutar_pre_audit(ctx)
        score_res = audit.calcular_audit_score(df_audit)

        _readiness_es = {
            "READY FOR AUDITOR": "LISTO PARA AUDITOR",
            "MINOR GAPS": "BRECHAS MENORES",
            "NOT READY": "AÚN NO LISTO",
        }
        st.markdown(
            _kpi_html([
                ("target", "Score de auditoría", f"{score_res['score']:.1f} / 100",
                 _readiness_es.get(score_res.get("readiness_level", ""), score_res.get("readiness_level", ""))),
                ("info", "Criterios que cumplen", f"{score_res['n_pass']} de {score_res['n_total']}", ""),
                ("trending-down", "Criterios que fallan", str(score_res["n_fail"]),
                 "cerrar antes de enviar a auditor"),
                ("table", "Sin dato / manual", str(score_res["n_na_manual"]),
                 "cuentan medio punto"),
            ]),
            unsafe_allow_html=True,
        )
        st.progress(min(1.0, score_res["score"] / 100.0))
        tono = "ok" if score_res["score"] >= 85 else ("warn" if score_res["score"] >= 70 else "bad")
        st.markdown(_badge_html(score_res["msg"], tono), unsafe_allow_html=True)

        import plotly.graph_objects as go

        col_a1, col_a2 = st.columns([1.6, 1])
        with col_a1:
            cat_scores = score_res.get("scores_por_categoria") or {}
            if cat_scores:
                cats = list(cat_scores.keys())
                fig_cat = go.Figure()
                fig_cat.add_bar(
                    x=[audit.PESO_CATEGORIA.get(c, 0) for c in cats], y=cats, orientation="h",
                    name="Peso máximo", marker_color="#dbeafe",
                )
                fig_cat.add_bar(
                    x=[cat_scores[c] for c in cats], y=cats, orientation="h",
                    name="Obtenido", marker_color=_F6_AZUL,
                    text=[f"{cat_scores[c]:.1f}" for c in cats], textposition="outside",
                )
                fig_cat.update_layout(barmode="overlay", xaxis_title="Puntos")
                st.plotly_chart(_f6_fig_layout(fig_cat, "Puntaje por categoría", 360),
                                use_container_width=True, key="f6_audit_categorias")
        with col_a2:
            fig_p = go.Figure(go.Pie(
                labels=["Cumplen", "Fallan", "Sin dato / manual"],
                values=[score_res["n_pass"], score_res["n_fail"], score_res["n_na_manual"]],
                hole=0.6, textinfo="label+value",
                marker={"colors": [_F6_VERDE, _F6_ROJO, _F6_GRIS]},
            ))
            st.plotly_chart(_f6_fig_layout(fig_p, "Resultado de criterios", 360),
                            use_container_width=True, key="f6_audit_dona")

        df_show = df_audit.rename(columns={
            "id": "ID", "categoria": "Categoría", "criterio": "Criterio",
            "status": "Estado", "evidencia": "Evidencia",
        })
        df_show["Estado"] = df_show["Estado"].map(
            {"PASS": "✅ Cumple", "FAIL": "❌ Falla", "N/A": "➖ Sin dato", "MANUAL": "✍️ Manual"}
        ).fillna(df_show["Estado"])
        st.dataframe(df_show, hide_index=True, use_container_width=True)
        st.caption(
            "Los estudios de esta fase alimentan el checklist: ruido → EN02, shadow flicker → EN01, "
            "aves → EN03, IEC (validación de Fase 5) → IEC01/IEC03. Los ítems sociales son de verificación manual."
        )


_F6_DIVISORES = {
    "Sitio y cumplimiento": ("🗺️", "Idoneidad IEC · terreno · clima frío", "#0d9488"),
    "Ambiental": ("🌿", "Receptores · ruido · flicker · avifauna · huella CO₂", "#16a34a"),
    "Operación y red": ("⚡", "SCADA real · curtailment · planta híbrida", "#d97706"),
    "Optimización y fin de vida": ("🎯", "Layout óptimo · repotenciación", "#7c3aed"),
    "Auditoría": ("📋", "Pre-audit checklist estilo DNV", "#0b66c2"),
}
_div_emoji, _div_sub, _div_color = _F6_DIVISORES[seccion]
st.markdown(
    f'<div class="f6-divider" style="--dc:{_div_color}"><div class="dx">{_div_emoji}</div>'
    f'<div><b>{_escape(seccion)}</b><small>{_div_sub}</small></div><div class="dline"></div></div>',
    unsafe_allow_html=True,
)

if seccion == "Sitio y cumplimiento":
    _render_sitio_cumplimiento()
elif seccion == "Ambiental":
    _render_ambiental()
elif seccion == "Operación y red":
    _render_operacion_red()
elif seccion == "Optimización y fin de vida":
    _render_optimizacion()
else:
    _render_auditoria()
