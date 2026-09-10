import html
import json
import re

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


# Localización ES de números: el código produce formato US (','=miles, '.'=decimal);
# el mockup usa ES (' .'=miles, ','=decimal). Intercambia separadores SOLO en tokens
# numéricos bien formados (no toca "IEC 61400-1", "ISO 14040", etc.).
_F6_NUM_RE = re.compile(r"\d[\d.,]*\d")
_F6_SWAP = str.maketrans({",": ".", ".": ","})


def _es_num(text: str) -> str:
    if not text:
        return text
    return _F6_NUM_RE.sub(lambda m: m.group(0).translate(_F6_SWAP), str(text))


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
/* ════════ Aurora v2 (F6) ════════ */
/* mismo alto de hero que F1-F5 (131px) */
.f6-hero-row{min-height:87px}
/* Franja de acento: una banda de 4px no se puede redondear (asomaba recta en las esquinas).
   El ::before cubre todo el card, el color va solo en los 4px de arriba y el clip-path lo recorta
   a la forma del card. Radio 25px = card 26px - 1px de borde. */
#root div[data-testid="stVerticalBlock"][class*="st-key-f6_card_"]:not(.st-key-f6_card_header)::before{
  top:0 !important;right:0 !important;bottom:0 !important;left:0 !important;height:auto !important;width:auto !important;
  background:linear-gradient(90deg, var(--acl,#0d9488), color-mix(in srgb,var(--acl,#0d9488) 25%,#fff) 70%, transparent) !important;
  background-size:100% 4px !important;background-repeat:no-repeat !important;background-position:top left !important;
  -webkit-clip-path:inset(0 round 25px 25px 0 0) !important;clip-path:inset(0 round 25px 25px 0 0) !important;
  border-radius:0 !important;pointer-events:none !important}
/* Ambiental = acento verde del mockup (franja + squircle del card-head) */
.st-key-f6_card_receptores,.st-key-f6_card_ruido,.st-key-f6_card_flicker,.st-key-f6_card_aves,.st-key-f6_card_lca{--acl:#16a34a}
.st-key-f6_card_receptores .aur-cicon,.st-key-f6_card_ruido .aur-cicon,.st-key-f6_card_flicker .aur-cicon,
.st-key-f6_card_aves .aur-cicon,.st-key-f6_card_lca .aur-cicon{
  background:linear-gradient(135deg, color-mix(in srgb,#16a34a 16%,#fff), color-mix(in srgb,#16a34a 7%,#fff)) !important;
  border-color:color-mix(in srgb,#16a34a 35%,#fff) !important;box-shadow:0 5px 12px color-mix(in srgb,#16a34a 16%,transparent) !important}
/* Figuras SVG inline */
.f6-fig{margin:8px 0}
.f6-fig svg text{font-family:'Segoe UI Variable Display','Segoe UI',system-ui,sans-serif}
.f6-bar,.f6-rec,.f6-tb,.f6-seg{cursor:help}
.f6-bar:hover rect:first-of-type{filter:brightness(1.1) saturate(1.1)}
.f6-seg:hover{filter:brightness(1.08)}
.f6-fig rect:hover{stroke:#0b2447;stroke-width:.6}
.f6-spin{animation:f6sp 5s linear infinite}
@keyframes f6sp{to{transform:rotate(360deg)}}
.f6-pulse{animation:f6pulse 2.2s ease-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes f6pulse{0%{transform:scale(.7);opacity:.75}100%{transform:scale(1.7);opacity:0}}
.f6-wave{animation:f6wave 1.8s ease-in-out infinite}
@keyframes f6wave{0%,100%{opacity:.25}50%{opacity:1}}
.f6-blink{animation:f6blink .9s steps(2,jump-none) infinite}
@keyframes f6blink{50%{opacity:.15}}
.f6-flow{stroke-dashoffset:0;animation:f6flow 1.6s linear infinite}
@keyframes f6flow{to{stroke-dashoffset:-26}}
/* "¿Cómo se calcula?" */
.f6-how{background:linear-gradient(180deg, color-mix(in srgb,#16a34a 5%,#fff), #fff);
  border:1.5px dashed color-mix(in srgb,#16a34a 38%,#fff);border-radius:18px;padding:12px 14px;margin:10px 0 4px}
.f6-how-t{font-size:12px;font-weight:900;color:#15803d;margin-bottom:6px;letter-spacing:-.01em}
.f6-how svg{display:block;width:100%;height:auto}
.f6-how svg text{font-family:'Segoe UI Variable Display','Segoe UI',system-ui,sans-serif}
.f6-how p{margin:6px 0 0;font-size:11px;color:#5a6b85;font-weight:600;line-height:1.45}
.f6-pills{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 4px}
/* Operación y red = acento ámbar del mockup (franja + squircle del card-head) */
.st-key-f6_card_scada,.st-key-f6_card_curtail,.st-key-f6_card_hibrido{--acl:#d97706}
.st-key-f6_card_scada .aur-cicon,.st-key-f6_card_curtail .aur-cicon,.st-key-f6_card_hibrido .aur-cicon{
  background:linear-gradient(135deg, color-mix(in srgb,#d97706 16%,#fff), color-mix(in srgb,#d97706 7%,#fff)) !important;
  border-color:color-mix(in srgb,#d97706 35%,#fff) !important;box-shadow:0 5px 12px color-mix(in srgb,#d97706 16%,transparent) !important}
.st-key-f6_card_scada [data-testid="stFileUploaderDropzone"]{
  border:2px dashed color-mix(in srgb,#d97706 45%,#fff) !important;border-radius:18px !important;
  background:linear-gradient(180deg, color-mix(in srgb,#d97706 6%,#fff), #fff) !important}
.f6-how.amb{border-color:color-mix(in srgb,#d97706 40%,#fff);background:linear-gradient(180deg, color-mix(in srgb,#d97706 5%,#fff), #fff)}
.f6-how.amb .f6-how-t{color:#b45309}
.f6-charge{animation:f6charge 2.4s ease-in-out infinite}
@keyframes f6charge{0%,100%{opacity:.2}50%{opacity:1}}
/* Optimización y fin de vida = acento violeta del mockup (franja + squircle del card-head) */
.st-key-f6_card_optim,.st-key-f6_card_repower{--acl:#7c3aed}
.st-key-f6_card_optim .aur-cicon,.st-key-f6_card_repower .aur-cicon{
  background:linear-gradient(135deg, color-mix(in srgb,#7c3aed 16%,#fff), color-mix(in srgb,#7c3aed 7%,#fff)) !important;
  border-color:color-mix(in srgb,#7c3aed 35%,#fff) !important;box-shadow:0 5px 12px color-mix(in srgb,#7c3aed 16%,transparent) !important}
.f6-how.vio{border-color:color-mix(in srgb,#7c3aed 38%,#fff);background:linear-gradient(180deg, color-mix(in srgb,#7c3aed 5%,#fff), #fff)}
.f6-how.vio .f6-how-t{color:#6d28d9}
/* Fichas de escenario de fin de vida */
.f6-escs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:8px 0 4px}
.f6-esc{background:#fff;border:1.5px solid #e2e8f0;border-radius:16px;padding:12px 10px;text-align:center;
  box-shadow:0 1px 2px rgba(11,36,71,.04),0 6px 16px rgba(11,36,71,.06)}
.f6-esc.rec{border-color:#16a34a;background:linear-gradient(180deg,#f0fdf4,#fff);box-shadow:0 8px 18px rgba(22,163,74,.16)}
.f6-esc-i{font-size:24px;line-height:1.1}
.f6-esc b{display:block;font-size:12.5px;color:#0b2447;margin-top:4px;font-weight:900}
.f6-esc-v{display:block;font-size:17px;font-weight:900;color:#0b2447;margin-top:4px;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.f6-esc.rec .f6-esc-v{color:#15803d}
.f6-esc small{font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.06em}
.f6-esc i{display:block;font-style:normal;font-size:10px;color:#5a6b85;font-weight:600;margin-top:4px;line-height:1.3}
.f6-esc.rec::after{content:"🏆 Recomendado";display:inline-block;margin-top:6px;font-size:9.5px;font-weight:900;color:#15803d;
  background:#dcfce7;border-radius:999px;padding:2px 9px}
/* Auditoría: tarjetas de acción, cabecera por categoría y columna de ID */
.f6-acc{display:flex;gap:12px;align-items:center;background:#fff;border:1.5px solid #fecaca;border-left:5px solid #dc2626;
  border-radius:14px;padding:10px 14px;margin:8px 0;box-shadow:0 2px 8px rgba(220,38,38,.06)}
.f6-acc-x{font-size:17px;flex-shrink:0}
.f6-acc b{display:block;color:#0b2447;font-size:12.5px;font-weight:900}
.f6-acc small{display:block;color:#5a6b85;font-size:10.5px;font-weight:700;margin-top:2px}
.f6-acc-d{margin-left:auto;flex-shrink:0}
.f6-audit-tbl tr.f6-tcat td{background:linear-gradient(90deg, color-mix(in srgb,#0d9488 11%,#fff), #fff) !important;
  font-weight:900;color:#0f766e;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;padding:8px 12px}
.f6-audit-tbl td.id{font-family:ui-monospace,Consolas,monospace;font-weight:800;color:#475569;white-space:nowrap}
.f6-audit-tbl td:nth-child(3){white-space:nowrap}
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
    sub_html = f"<i>{_escape(_es_num(sub))}</i>" if sub else ""
    st.markdown(
        f'<div class="aur-kpi" style="--kc:{kc}"><div class="aur-ki">{icon_html}</div>'
        f'<div class="aur-kpi-copy"><small>{_escape(label)}</small><b>{_escape(_es_num(value))}</b>{sub_html}</div></div>',
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
      <div class="f6-hpill"><b>{_score_label}</b><span>Puntaje audit.</span></div>
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
        sub_html = f"<i>{_escape(_es_num(sub))}</i>" if sub else ""
        parts.append(
            f'<div class="aur-kpi" style="--kc:{kc}"><div class="aur-ki">{icon_html}</div>'
            f'<div class="aur-kpi-copy"><small>{_escape(label)}</small>'
            f'<b>{_escape(_es_num(value))}</b>{sub_html}</div></div>'
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


# -----------------------------------------------------------------------------
# Ambiental · gráficos SVG Aurora (paridad mockup 06_fase6). SVG inline (sin
# iframe): el tamaño se ajusta solo y cada barra/celda/punto trae <title> →
# tooltip nativo al pasar el cursor.
# -----------------------------------------------------------------------------
_F6_AZUL_T = "#2563eb"
_F6_AZUL_OSC = "#1e3a8a"
_F6_YLORRD = ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#fd8d3c", "#fc4e2a", "#e31a1c", "#b10026"]


def _svg_t(text) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _f6_fig_html(titulo: str, svg: str, leyenda=None) -> str:
    """Contenedor .f6-fig (título + SVG + leyenda opcional [(texto, color)])."""
    ley = ""
    if leyenda:
        ley = '<div class="f6-legend">' + "".join(
            f'<i style="--lc:{c}">{_escape(t)}</i>' for t, c in leyenda
        ) + "</div>"
    return f'<div class="f6-fig"><div class="f6-gtitle">{_escape(titulo)}</div>{svg}{ley}</div>'


def _f6_nombre_corto(nombre, n: int = 18) -> str:
    """'Coragyps atratus (Zopilote)' → 'Zopilote'; recorta nombres largos."""
    s = str(nombre or "")
    m = re.search(r"\(([^)]+)\)\s*$", s)
    if m:
        s = m.group(1)
    return s if len(s) <= n else s[: n - 1] + "…"


def _f6_nice_floor(v: float) -> float:
    """Mayor número 'redondo' (1/2/5 × 10^k) que no supera v (barra de escala)."""
    if not np.isfinite(v) or v <= 0:
        return 1.0
    e = 10 ** np.floor(np.log10(v))
    for m in (5, 2, 1):
        if m * e <= v:
            return float(m * e)
    return float(e)


def _f6_color_escala(t: float, stops=_F6_YLORRD) -> str:
    t = min(1.0, max(0.0, float(t))) * (len(stops) - 1)
    i = int(np.floor(t))
    if i >= len(stops) - 1:
        return stops[-1]
    f = t - i
    a = [int(stops[i][k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(stops[i + 1][k:k + 2], 16) for k in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(a[j] + (b[j] - a[j]) * f) for j in range(3))


def _f6_hbars_svg(filas, lineas=(), unidad: str = "", log: bool = False, decimales: int = 0,
                  ancho: float = 380.0) -> str:
    """Barras horizontales del mockup. filas=[(etiqueta, valor, color, tooltip)],
    lineas=[(valor, color, etiqueta, dasharray)] = límites verticales.
    ancho = ancho del lienzo SVG: 380 encaja en media columna con texto legible."""
    n = max(1, len(filas))
    fila_h = max(30.0, min(64.0, 170.0 / n))
    bar_h = round(fila_h * 0.62, 1)
    top = 32.0 if lineas else 12.0
    alto = int(top + n * fila_h + 10)
    x0, x1 = 112.0, ancho - 58.0
    vals = [float(v) for _, v, _, _ in filas if np.isfinite(float(v))]
    vals += [float(v) for v, *_ in lineas]
    vmax = max(vals + [1e-9])
    if log:
        pos = [v for v in vals if v > 0] or [1.0]
        lo = float(np.floor(np.log10(min(pos))))
        hi = float(np.ceil(np.log10(vmax * 1.05)))
        hi = hi if hi > lo else lo + 1.0

        def sx(v):
            v = max(float(v), 10 ** lo)
            return x0 + (np.log10(v) - lo) / (hi - lo) * (x1 - x0)
    else:
        tope = vmax * 1.12

        def sx(v):
            return x0 + max(0.0, float(v)) / tope * (x1 - x0)

    p = [f'<svg viewBox="0 0 {ancho:.0f} {alto}" xmlns="http://www.w3.org/2000/svg">']
    for i, (etq, val, col, tip) in enumerate(filas):
        yc = top + i * fila_h + fila_h / 2
        y = yc - bar_h / 2
        w = max(3.0, sx(val) - x0)
        txt = _es_num(f"{float(val):,.{decimales}f}") + (f" {unidad}" if unidad else "")
        p.append(
            f'<g class="f6-bar"><title>{_svg_t(tip)}</title>'
            f'<text x="{x0 - 8:.0f}" y="{yc + 4:.1f}" text-anchor="end" font-size="12" font-weight="800" fill="#475569">{_svg_t(_f6_nombre_corto(etq, 15))}</text>'
            f'<rect x="{x0}" y="{y:.1f}" width="{w:.1f}" height="{bar_h}" rx="8" fill="{col}"/>'
            f'<rect x="{x0}" y="{y:.1f}" width="{w:.1f}" height="{min(8.0, bar_h / 3):.1f}" rx="4" fill="#fff" opacity=".25"/>'
            f'<text x="{x0 + w + 6:.1f}" y="{yc + 4:.1f}" font-size="11.5" font-weight="900" fill="#0b2447">{_svg_t(txt)}</text></g>'
        )
    for k, (v, col, etq, dash) in enumerate(lineas):
        x = sx(v)
        p.append(
            f'<g><title>{_svg_t(etq)}</title>'
            f'<line x1="{x:.1f}" y1="{top - 4:.1f}" x2="{x:.1f}" y2="{alto - 4}" stroke="{col}" stroke-width="2.4" stroke-dasharray="{dash}"/>'
            f'<text x="{x:.1f}" y="{12 + 12 * (k % 2)}" text-anchor="middle" font-size="10" font-weight="900" fill="{col}">{_svg_t(etq)}</text></g>'
        )
    p.append("</svg>")
    return "".join(p)


def _f6_donut_svg(segmentos, centro_valor: str, centro_etq: str) -> str:
    """Dona del mockup. segmentos=[(etiqueta, valor, color)]."""
    total = sum(max(0.0, float(v)) for _, v, _ in segmentos) or 1.0
    cx, cy, r, sw = 150.0, 122.0, 82.0, 30.0
    circ = 2 * np.pi * r
    p = [
        '<svg viewBox="0 0 300 244" xmlns="http://www.w3.org/2000/svg">',
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#eef4fb" stroke-width="{sw}"/>',
    ]
    off = 0.0
    for etq, v, col in segmentos:
        frac = max(0.0, float(v)) / total
        dash = frac * circ
        if dash <= 0:
            continue
        pct = _es_num(f"{frac * 100:.1f}")
        p.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-width="{sw}" '
            f'stroke-dasharray="{dash:.2f} {circ - dash:.2f}" stroke-dashoffset="{-off:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" class="f6-seg"><title>{_svg_t(etq)}: {pct} %</title></circle>'
        )
        off += dash
    p.append(
        f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="25" font-weight="900" fill="#0b2447">{_svg_t(centro_valor)}</text>'
        f'<text x="{cx}" y="{cy + 24}" text-anchor="middle" font-size="10.5" font-weight="800" fill="#64748b">{_svg_t(centro_etq)}</text>'
        "</svg>"
    )
    return "".join(p)


def _f6_turbina_svg(x: float, y: float, etiqueta: str, tip: str, s: float = 1.0,
                    color: str = _F6_AZUL_T, oscuro: str = _F6_AZUL_OSC) -> str:
    """Aerogenerador del mockup (torre + 3 palas que giran)."""
    return (
        f'<g class="f6-tb"><title>{_svg_t(tip)}</title>'
        f'<g transform="translate({x:.1f},{y:.1f}) scale({s})">'
        f'<line x1="0" y1="0" x2="0" y2="-26" stroke="{oscuro}" stroke-width="3.4" stroke-linecap="round"/>'
        '<g class="f6-spin" style="transform-origin:0px -26px">'
        f'<path d="M0,-26 L0,-44 L3,-31 Z" fill="{color}"/>'
        f'<path d="M0,-26 L15.6,-17 L4.2,-23.4 Z" fill="{color}"/>'
        f'<path d="M0,-26 L-15.6,-17 L-4.2,-23.4 Z" fill="{color}"/></g>'
        f'<circle cx="0" cy="-26" r="3.4" fill="{oscuro}"/></g>'
        f'<text x="{x:.1f}" y="{y + 14 * s + 1:.1f}" text-anchor="middle" font-size="9.5" font-weight="900" fill="{oscuro}">{_svg_t(etiqueta)}</text></g>'
    )


def _f6_casa_svg(x: float, y: float, s: float = 1.0) -> str:
    return (
        f'<g transform="translate({x:.1f},{y:.1f}) scale({s})">'
        '<path d="M-15,0 V-15 L0,-27 L15,-15 V0 Z" fill="#fff" stroke="#b91c1c" stroke-width="2.2" stroke-linejoin="round"/>'
        '<path d="M-19,-13 L0,-30 L19,-13" fill="none" stroke="#dc2626" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        '<rect x="-4.5" y="-10" width="9" height="10" rx="1.5" fill="#fecaca"/></g>'
    )


def _f6_parque_receptores_svg(df_layout, receptores):
    """Vista en planta (mockup 'Parque y receptores'): paisaje + turbinas reales
    (Fase 4) + receptores, distancia a la turbina más cercana, escala y norte.
    Devuelve (svg, [(receptor_id, nombre, turbina_id, distancia_m)])."""
    turb = []
    if df_layout is not None and len(df_layout):
        for i, (_, r) in enumerate(df_layout.iterrows()):
            try:
                turb.append((str(r.get("turbina_id") or f"T{i + 1}"), float(r["x_m"]), float(r["y_m"])))
            except (TypeError, ValueError, KeyError):
                continue
    recs = [(r["receptor_id"], r["nombre"], float(r["x_m"]), float(r["y_m"])) for r in receptores]
    xs = [t[1] for t in turb] + [r[2] for r in recs]
    ys = [t[2] for t in turb] + [r[3] for r in recs]
    if not xs:
        return "", []
    W, H = 560.0, 300.0
    L, R, T, B = 46.0, 46.0, 62.0, 48.0
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    dx, dy = max(xmax - xmin, 1.0), max(ymax - ymin, 1.0)
    esc = min((W - L - R) / dx, (H - T - B) / dy)
    if dx < 50 and dy < 50:
        esc = (W - L - R) / 400.0
    xc, yc = (xmin + xmax) / 2, (ymin + ymax) / 2
    cxp, cyp = L + (W - L - R) / 2, T + (H - T - B) / 2

    def P(x, y):
        return cxp + (x - xc) * esc, cyp - (y - yc) * esc

    p = [
        '<svg viewBox="0 0 560 300" xmlns="http://www.w3.org/2000/svg">',
        '<rect x="8" y="8" width="544" height="284" rx="18" fill="#f2faf3"/>',
        '<path d="M8 216 Q168 180 308 210 T552 186 V292 H8 Z" fill="#dcf1de"/>',
        '<path d="M8 58 Q224 88 392 54 T552 78" fill="none" stroke="#bfdbfe" stroke-width="11" opacity=".75" stroke-linecap="round"/>',
        '<ellipse cx="470" cy="84" rx="58" ry="32" fill="#e9f5ea"/>',
        '<g opacity=".5">' + "".join(
            f'<line x1="{gx}" y1="14" x2="{gx}" y2="286" stroke="#e3eee4" stroke-width="1"/>' for gx in range(60, 540, 60)
        ) + "</g>",
    ]
    # Distancia de cada receptor a la turbina más cercana (línea discontinua + etiqueta)
    dists = []
    for rid, nombre, rx, ry in recs:
        if not turb:
            continue
        tid, tx, ty = min(turb, key=lambda t: (t[1] - rx) ** 2 + (t[2] - ry) ** 2)
        d = float(np.hypot(tx - rx, ty - ry))
        dists.append((rid, nombre, tid, d))
        (ax, ay), (bx, by) = P(rx, ry), P(tx, ty)
        p.append(
            f'<g><title>{_svg_t(f"{rid} → {tid}: {d:,.0f} m".replace(",", "."))}</title>'
            f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#f87171" stroke-width="1.6" stroke-dasharray="5 5" opacity=".8"/>'
            f'<text x="{(ax + bx) / 2:.1f}" y="{(ay + by) / 2 - 5:.1f}" text-anchor="middle" font-size="9" font-weight="900" '
            f'fill="#b91c1c" stroke="#fff" stroke-width="3" paint-order="stroke">{_svg_t(f"{d:,.0f} m".replace(",", "."))}</text></g>'
        )
    # Tamaño del aerogenerador según la separación real en pantalla (evita que se monten
    # unos sobre otros cuando las turbinas están muy juntas o en fila).
    s_tb = 1.0
    if len(turb) > 1:
        pts = [P(tx, ty) for _, tx, ty in turb]
        dmin = min(
            float(np.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
            for i in range(len(pts)) for j in range(i + 1, len(pts))
        )
        s_tb = float(min(1.0, max(0.45, dmin / 58.0)))
    for tid, tx, ty in turb:
        px, py = P(tx, ty)
        tip = f"{tid} · x = {tx:,.0f} m · y = {ty:,.0f} m".replace(",", ".")
        p.append(_f6_turbina_svg(px, py, tid, tip, s_tb))
    for rid, nombre, rx, ry in recs:
        px, py = P(rx, ry)
        near = next((f"\nTurbina más cercana: {t} a {d:,.0f} m".replace(",", ".") for r_, _, t, d in dists if r_ == rid), "")
        tip = f"{rid} · {nombre}\nx = {rx:,.0f} m · y = {ry:,.0f} m".replace(",", ".") + near
        p.append(
            f'<g class="f6-rec"><title>{_svg_t(tip)}</title><g transform="translate({px:.1f},{py:.1f})">'
            '<circle r="14" fill="none" stroke="#dc2626" stroke-width="1.6" opacity=".45"/>'
            '<circle r="14" fill="none" stroke="#dc2626" stroke-width="1.6" class="f6-pulse"/>'
            '<circle r="9" fill="#dc2626"/><circle r="3.4" fill="#fff"/>'
            f'<text x="0" y="25" text-anchor="middle" font-size="9.5" font-weight="900" fill="#b91c1c">{_svg_t(rid)}</text></g></g>'
        )
    # Barra de escala + norte
    lm = _f6_nice_floor((W - L - R) / esc / 4.0)
    lpx = lm * esc
    p.append(
        f'<g><line x1="24" y1="276" x2="{24 + lpx:.1f}" y2="276" stroke="#334155" stroke-width="2.4"/>'
        f'<line x1="24" y1="271" x2="24" y2="281" stroke="#334155" stroke-width="2"/>'
        f'<line x1="{24 + lpx:.1f}" y1="271" x2="{24 + lpx:.1f}" y2="281" stroke="#334155" stroke-width="2"/>'
        f'<text x="{24 + lpx / 2:.1f}" y="268" text-anchor="middle" font-size="9.5" font-weight="900" fill="#334155">{_svg_t(f"{lm:,.0f} m".replace(",", "."))}</text></g>'
        '<g transform="translate(528,34)"><circle r="15" fill="#fff" stroke="#cbd5e1"/>'
        '<path d="M0,-10 L5,4 L0,1 L-5,4 Z" fill="#0b2447"/>'
        '<text y="12" text-anchor="middle" font-size="8.5" font-weight="900" fill="#0b2447">N</text></g>'
        "</svg>"
    )
    return "".join(p), dists


def _f6_mapa_ruido_svg(df_grid, df_layout, receptores, lim_dia: float, lim_noche: float) -> str:
    """Mapa de ruido LpA (grid del módulo ISO 9613-2) como SVG con tooltip por celda."""
    piv = df_grid.pivot_table(index="y_m", columns="x_m", values="lpA_db")
    xs = piv.columns.to_numpy(dtype=float)
    ys = piv.index.to_numpy(dtype=float)
    Z = piv.to_numpy(dtype=float)
    if len(xs) < 2 or len(ys) < 2 or not np.isfinite(Z).any():
        return ""
    X0, Y0, S = 16.0, 12.0, 400.0
    dxm, dym = xs[1] - xs[0], ys[1] - ys[0]
    x_lo, x_hi = xs[0] - dxm / 2, xs[-1] + dxm / 2
    y_lo, y_hi = ys[0] - dym / 2, ys[-1] + dym / 2

    def P(x, y):
        return X0 + (x - x_lo) / (x_hi - x_lo) * S, Y0 + (y_hi - y) / (y_hi - y_lo) * S

    zmin, zmax = float(np.nanmin(Z)), float(np.nanmax(Z))
    rng = (zmax - zmin) or 1.0
    cw, ch = S / len(xs), S / len(ys)
    p = [
        '<svg viewBox="0 0 520 424" xmlns="http://www.w3.org/2000/svg">',
        '<defs><linearGradient id="f6ruidograd" x1="0" y1="1" x2="0" y2="0">'
        + "".join(f'<stop offset="{k / (len(_F6_YLORRD) - 1):.3f}" stop-color="{c}"/>' for k, c in enumerate(_F6_YLORRD))
        + "</linearGradient></defs>",
        f'<rect x="{X0 - 1}" y="{Y0 - 1}" width="{S + 2}" height="{S + 2}" rx="10" fill="#fff" stroke="#d8e5f5"/>',
    ]
    for j, yv in enumerate(ys):
        for i, xv in enumerate(xs):
            z = Z[j, i]
            if not np.isfinite(z):
                continue
            px, py = P(xv - dxm / 2, yv + dym / 2)
            tip = _es_num(f"x = {xv:,.0f} m · y = {yv:,.0f} m\nLpA = {z:.1f} dB(A)")
            p.append(
                f'<rect x="{px:.1f}" y="{py:.1f}" width="{cw + 0.5:.1f}" height="{ch + 0.5:.1f}" '
                f'fill="{_f6_color_escala((z - zmin) / rng)}"><title>{_svg_t(tip)}</title></rect>'
            )
    if df_layout is not None and len(df_layout):
        for i, (_, r) in enumerate(df_layout.iterrows()):
            try:
                tx, ty = float(r["x_m"]), float(r["y_m"])
            except (TypeError, ValueError, KeyError):
                continue
            px, py = P(tx, ty)
            tid = str(r.get("turbina_id") or f"T{i + 1}")
            p.append(
                f'<g><title>{_svg_t(tid)}</title><path d="M{px - 5:.1f},{py - 5:.1f} L{px + 5:.1f},{py + 5:.1f} '
                f'M{px + 5:.1f},{py - 5:.1f} L{px - 5:.1f},{py + 5:.1f}" stroke="#1e3a8a" stroke-width="2.6" stroke-linecap="round"/></g>'
            )
    for rc in receptores:
        rx, ry = float(rc["x_m"]), float(rc["y_m"])
        if not (x_lo <= rx <= x_hi and y_lo <= ry <= y_hi):
            continue
        px, py = P(rx, ry)
        p.append(
            f'<g><title>{_svg_t(rc["receptor_id"] + " · " + str(rc["nombre"]))}</title>'
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="#dc2626" stroke="#fff" stroke-width="2"/>'
            f'<text x="{px:.1f}" y="{py - 9:.1f}" text-anchor="middle" font-size="9.5" font-weight="900" fill="#7f1d1d" '
            f'stroke="#fff" stroke-width="3" paint-order="stroke">{_svg_t(rc["receptor_id"])}</text></g>'
        )
    # Escala de color con marcas de los límites
    lx, ly, lh = 438.0, Y0, S
    p.append(
        f'<rect x="{lx}" y="{ly}" width="16" height="{lh}" rx="6" fill="url(#f6ruidograd)" stroke="#d8e5f5"/>'
        f'<text x="{lx + 22}" y="{ly + 9}" font-size="10" font-weight="900" fill="#0b2447">{_svg_t(_es_num(f"{zmax:.0f}"))} dB</text>'
        f'<text x="{lx + 22}" y="{ly + lh}" font-size="10" font-weight="900" fill="#0b2447">{_svg_t(_es_num(f"{zmin:.0f}"))} dB</text>'
    )
    for v, col, etq in ((lim_dia, "#d97706", "día"), (lim_noche, "#2563eb", "noche")):
        if zmin <= v <= zmax:
            yy = ly + lh - (v - zmin) / rng * lh
            p.append(
                f'<line x1="{lx - 4}" y1="{yy:.1f}" x2="{lx + 20}" y2="{yy:.1f}" stroke="{col}" stroke-width="2.4"/>'
                f'<text x="{lx + 22}" y="{yy + 3.5:.1f}" font-size="9" font-weight="900" fill="{col}">{_svg_t(_es_num(f"{v:.0f}"))} {etq}</text>'
            )
    p.append("</svg>")
    return "".join(p)


def _f6_como_se_calcula(tipo: str) -> str:
    """Esquema explicativo '¿Cómo se calcula?' de cada estudio ambiental."""
    if tipo == "ruido":
        ondas = "".join(
            f'<path d="M{70 + r * 0.82:.1f},{79 - r * 0.57:.1f} A{r},{r} 0 0 1 {70 + r * 0.82:.1f},{79 + r * 0.57:.1f}" '
            f'fill="none" stroke="#0d9488" stroke-width="2.6" stroke-linecap="round" class="f6-wave" style="animation-delay:{k * 0.45:.2f}s"/>'
            for k, r in enumerate((40, 70, 100, 130))
        )
        svg = (
            '<svg viewBox="0 0 560 160" xmlns="http://www.w3.org/2000/svg">'
            '<text x="300" y="20" text-anchor="middle" font-size="13" font-weight="900" fill="#0b2447">LpA = LwA − A<tspan font-size="9">div</tspan> − A<tspan font-size="9">atm</tspan> − A<tspan font-size="9">suelo</tspan></text>'
            + ondas + _f6_turbina_svg(70, 118, "LwA", "Fuente: potencia sonora de la turbina", 1.5)
            + _f6_casa_svg(482, 122, 1.25)
            + '<text x="482" y="78" text-anchor="middle" font-size="10" font-weight="900" fill="#b91c1c">LpA</text>'
            '<line x1="96" y1="138" x2="456" y2="138" stroke="#94a3b8" stroke-width="1.6" stroke-dasharray="6 5"/>'
            '<text x="276" y="153" text-anchor="middle" font-size="9.5" font-weight="800" fill="#64748b">distancia turbina → vivienda</text>'
            '<g font-size="9.5" font-weight="900">'
            '<rect x="216" y="44" width="116" height="20" rx="10" fill="#f0fdfa" stroke="#99f6e4"/><text x="274" y="58" text-anchor="middle" fill="#0f766e">A div · distancia</text>'
            '<rect x="216" y="70" width="116" height="20" rx="10" fill="#f0fdfa" stroke="#99f6e4"/><text x="274" y="84" text-anchor="middle" fill="#0f766e">A atm · aire</text>'
            '<rect x="216" y="96" width="116" height="20" rx="10" fill="#f0fdfa" stroke="#99f6e4"/><text x="274" y="110" text-anchor="middle" fill="#0f766e">A suelo · terreno</text>'
            "</g></svg>"
        )
        txt = ("El sonido de cada turbina (LwA) pierde energía al viajar: se reparte en una esfera cada vez mayor, "
               "el aire lo absorbe y el terreno lo amortigua. Se suman todas las turbinas y se compara con los límites de día y de noche.")
    elif tipo == "flicker":
        rayos = "".join(
            f'<line x1="{60 + 24 * np.cos(a):.1f}" y1="{46 + 24 * np.sin(a):.1f}" x2="{60 + 32 * np.cos(a):.1f}" y2="{46 + 32 * np.sin(a):.1f}" '
            'stroke="#f59e0b" stroke-width="2.6" stroke-linecap="round"/>'
            for a in np.linspace(0, 2 * np.pi, 9)[:-1]
        )
        svg = (
            '<svg viewBox="0 0 560 160" xmlns="http://www.w3.org/2000/svg">'
            + rayos + '<circle cx="60" cy="46" r="18" fill="#fbbf24"/>'
            '<line x1="78" y1="54" x2="470" y2="112" stroke="#fbbf24" stroke-width="2" stroke-dasharray="4 5" opacity=".9"/>'
            '<g class="f6-blink"><path d="M300,84 L470,112 L470,132 L300,100 Z" fill="#334155" opacity=".22"/></g>'
            + _f6_turbina_svg(270, 136, "", "Rotor en movimiento", 1.9)
            + _f6_casa_svg(482, 134, 1.25)
            + '<text x="60" y="96" text-anchor="middle" font-size="10" font-weight="900" fill="#b45309">Sol bajo</text>'
            '<text x="370" y="30" text-anchor="middle" font-size="11.5" font-weight="900" fill="#0b2447">Sombra intermitente sobre la vivienda</text>'
            '<text x="370" y="46" text-anchor="middle" font-size="9.5" font-weight="800" fill="#64748b">límite habitual: 30 h/año</text>'
            "</svg>"
        )
        txt = ("Cuando el sol está bajo y queda detrás del rotor girando, las palas proyectan una sombra que parpadea "
               "sobre la vivienda. Se cuentan las horas del año en que ocurre (sol sobre el horizonte y turbina operando).")
    elif tipo == "aves":
        svg = (
            '<svg viewBox="0 0 560 160" xmlns="http://www.w3.org/2000/svg">'
            '<circle cx="280" cy="82" r="50" fill="#f0fdf4" stroke="#86efac" stroke-width="2" stroke-dasharray="6 5"/>'
            + _f6_turbina_svg(280, 158, "", "Área barrida por el rotor", 2.4)
            + '<path d="M34,40 Q180,70 280,82 T530,56" fill="none" stroke="#d97706" stroke-width="2.4" stroke-dasharray="7 6" class="f6-flow"/>'
            '<text x="34" y="36" font-size="22">🦅</text>'
            '<text x="444" y="112" text-anchor="middle" font-size="10" font-weight="900" fill="#15803d">área barrida</text>'
            '<text x="120" y="126" text-anchor="middle" font-size="10" font-weight="900" fill="#b45309">trayectoria de vuelo</text>'
            '<text x="280" y="16" text-anchor="middle" font-size="11.5" font-weight="900" fill="#0b2447">colisiones = pasos/año × P(cruzar el rotor) × P(impacto) × (1 − evasión)</text>'
            "</svg>"
        )
        txt = ("Modelo de Band (2007): de las aves que cruzan el parque, se estima cuántas pasan por el área barrida "
               "a la altura del rotor y la probabilidad de impacto según su tamaño y velocidad; la evasión reduce el resultado.")
    else:  # lca
        etapas = [("🏭", "Fabricación"), ("🚚", "Transporte"), ("🏗️", "Instalación"), ("⚙️", "Operación"), ("♻️", "Desmantelar")]
        g = []
        for k, (ico, etq) in enumerate(etapas):
            x = 64 + k * 108
            if k:
                g.append(f'<path d="M{x - 76},62 L{x - 34},62" stroke="#86efac" stroke-width="3" stroke-linecap="round" class="f6-flow"/>'
                         f'<path d="M{x - 40},56 L{x - 32},62 L{x - 40},68" fill="none" stroke="#16a34a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')
            g.append(f'<circle cx="{x}" cy="62" r="27" fill="#f0fdf4" stroke="#86efac" stroke-width="2"/>'
                     f'<text x="{x}" y="70" text-anchor="middle" font-size="22">{ico}</text>'
                     f'<text x="{x}" y="108" text-anchor="middle" font-size="10" font-weight="900" fill="#15803d">{etq}</text>')
        svg = (
            '<svg viewBox="0 0 560 150" xmlns="http://www.w3.org/2000/svg">' + "".join(g)
            + '<text x="280" y="138" text-anchor="middle" font-size="11" font-weight="900" fill="#0b2447">'
            "huella (gCO₂eq/kWh) = emisiones de todo el ciclo ÷ energía generada en la vida útil</text></svg>"
        )
        txt = ("Análisis de ciclo de vida (ISO 14040): se suman las emisiones de fabricar, transportar, instalar, operar "
               "y desmantelar el parque, y se reparten entre toda la energía que produce. Se compara con la red eléctrica.")
    return f'<div class="f6-how"><div class="f6-how-t">💡 ¿Cómo se calcula?</div>{svg}<p>{_escape(txt)}</p></div>'


def _render_card_receptores() -> pd.DataFrame:
    with st.container(border=True, key="f6_card_receptores"):
        _section_header(
            "Receptores sensibles",
            "Viviendas y edificaciones cercanas (coordenadas en m respecto al centro del parque) · las usan ruido y parpadeo de sombra",
            "map-pin",
        )
        col_tab, col_map = st.columns([1.0, 1.3], gap="medium")
        with col_tab:
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
            st.caption("Añada filas con el ＋ de la tabla y edite nombre y coordenadas directamente.")
            if st.button("💾 Guardar receptores", key="f6_receptores_guardar"):
                guardar_config_values({"f6_receptores_json": json.dumps(_receptores_desde_df(df_rec))})
                st.success("Receptores guardados en el proyecto.")

        # Vista en planta: turbinas del layout (Fase 4) + receptores editados.
        df_layout = cargar_layout_parque()
        receptores = _receptores_desde_df(df_rec)
        with col_map:
            svg, dists = _f6_parque_receptores_svg(df_layout, receptores)
            if svg:
                st.markdown(
                    _f6_fig_html(
                        "Parque y receptores · vista en planta",
                        svg,
                        [("Turbina", _F6_AZUL_T), ("Receptor", _F6_ROJO), ("Distancia a la turbina más cercana", "#f87171")],
                    ),
                    unsafe_allow_html=True,
                )
                if dists:
                    pills = "".join(
                        f'<span class="f6-pill info">{_escape(rid)} · {_escape(_es_num(f"{d:,.0f}"))} m a {_escape(tid)}</span>'
                        for rid, _, tid, d in dists
                    )
                    st.markdown(f'<div class="f6-pills">{pills}</div>', unsafe_allow_html=True)
            else:
                st.markdown(
                    _badge_html("Sin turbinas ni receptores: defina el arreglo en la Fase 4 y añada receptores en la tabla.", "info"),
                    unsafe_allow_html=True,
                )
        return df_rec


def _render_card_ruido(df_receptores: pd.DataFrame) -> None:
    with st.container(border=True, key="f6_card_ruido"):
        _section_header(
            "Ruido · ISO 9613-2",
            "Nivel sonoro LpA en cada receptor frente a los límites de día y de noche",
            "activity",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            lwa = st.number_input(
                "LwA turbina dB(A)", min_value=80.0, max_value=120.0,
                value=_cfg_float(config, "f6_ruido_lwa_db", 105.0), step=0.5, key="f6_ruido_lwa",
                help="Potencia sonora por turbina. Típico turbina 2-4 MW: 104-108 dB(A). Dato del fabricante.",
            )
        with c2:
            lim_dia = st.number_input(
                "Límite diurno dB(A)", min_value=30.0, max_value=80.0,
                value=_cfg_float(config, "f6_ruido_lim_diurno", 50.0), step=1.0, key="f6_ruido_dia",
            )
        with c3:
            lim_noche = st.number_input(
                "Límite nocturno dB(A)", min_value=25.0, max_value=70.0,
                value=_cfg_float(config, "f6_ruido_lim_nocturno", 40.0), step=1.0, key="f6_ruido_noche",
            )
        with st.expander("🌡️ Condiciones atmosféricas"):
            ca, cb = st.columns(2)
            with ca:
                temp_c = st.number_input("Temperatura (°C)", -20.0, 50.0, _cfg_float(config, "f5_temperatura_media_c", 20.0), 1.0, key="f6_ruido_temp")
            with cb:
                hum_pct = st.number_input("Humedad relativa (%)", 10.0, 100.0, 70.0, 5.0, key="f6_ruido_hum")

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            calc_tabla = st.button("🔊 Calcular LpA en receptores", key="f6_ruido_btn", type="primary", use_container_width=True)
        with col_b2:
            calc_mapa = st.button("🗺️ Generar mapa de ruido", key="f6_ruido_mapa_btn", use_container_width=True,
                                  help="Malla de 900 receptores virtuales alrededor del parque (tarda unos segundos).")

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
                    with st.spinner("Generando mapa de ruido (malla 30×30)…"):
                        df_grid = ruido_iso9613.crear_mapa_ruido_grid(
                            df_layout, float(lwa), grid_extent_m=2000, grid_resolution=30,
                            altura_emisor=h_hub, temperatura_c=float(temp_c), humedad_pct=float(hum_pct),
                        )
                    prev = {**prev, "grid": df_grid, "error": None}
                st.session_state["f6_ruido_result"] = prev

        res = st.session_state.get("f6_ruido_result")
        if not res:
            st.markdown(_f6_como_se_calcula("ruido"), unsafe_allow_html=True)
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
                    ("🔊", "LpA máximo", f"{lp_max:.1f} dB(A)", f"receptor más expuesto de {len(df_lpa)}", _F6_ROJO if not (ok_dia and ok_noche) else _F6_VERDE),
                    ("☀️", "Límite diurno", f"{float(lim_dia):.0f} dB(A)", "CUMPLE" if ok_dia else "EXCEDE", _F6_AMBAR),
                    ("🌙", "Límite nocturno", f"{float(lim_noche):.0f} dB(A)", "CUMPLE" if ok_noche else "EXCEDE", _F6_AZUL),
                    ("📍", "Distancia mínima", f"{float(df_lpa['distancia_min_m'].min()):,.0f} m",
                     "turbina más cercana a un receptor"),
                ], n=2),
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
            filas = []
            for _, r in df_lpa.iterrows():
                cd, cn = bool(r["cumple_diurno"]), bool(r["cumple_nocturno"])
                col = _F6_VERDE if (cd and cn) else (_F6_AMBAR if cd else _F6_ROJO)
                tip = _es_num(
                    f"{r['receptor_id']} · {r['nombre']}\nLpA = {float(r['lpA_db']):.1f} dB(A)\n"
                    f"Día: {'cumple' if cd else 'excede'} · Noche: {'cumple' if cn else 'excede'}\n"
                    f"Turbina más cercana: {float(r['distancia_min_m']):,.0f} m"
                )
                filas.append((r["nombre"], float(r["lpA_db"]), col, tip))
            svg = _f6_hbars_svg(
                filas,
                lineas=[(float(lim_dia), _F6_AMBAR, f"Día {float(lim_dia):.0f}", "8 6"),
                        (float(lim_noche), _F6_AZUL, f"Noche {float(lim_noche):.0f}", "3 5")],
                decimales=1,
            )
            st.markdown(
                _f6_fig_html("LpA por receptor · dB(A)", svg,
                             [("Cumple día y noche", _F6_VERDE), ("Solo cumple de día", _F6_AMBAR), ("Excede", _F6_ROJO)]),
                unsafe_allow_html=True,
            )

            df_show = df_lpa.rename(columns={
                "receptor_id": "Receptor", "nombre": "Nombre", "x_m": "x (m)", "y_m": "y (m)",
                "lpA_db": "LpA dB(A)", "cumple_diurno": "Diurno", "cumple_nocturno": "Nocturno",
                "distancia_min_m": "Dist. mín. (m)",
            })
            df_show["Diurno"] = df_show["Diurno"].map({True: "✅ Cumple", False: "❌ Excede"})
            df_show["Nocturno"] = df_show["Nocturno"].map({True: "✅ Cumple", False: "❌ Excede"})
            with st.expander("📋 Tabla de detalle por receptor"):
                st.dataframe(df_show, hide_index=True, use_container_width=True)

        df_grid = res.get("grid")
        if df_grid is not None and len(df_grid):
            svg_mapa = _f6_mapa_ruido_svg(df_grid, df_layout, receptores, float(lim_dia), float(lim_noche))
            if svg_mapa:
                st.markdown(
                    _f6_fig_html("Mapa de ruido LpA · pase el cursor para ver cada punto", svg_mapa,
                                 [("Turbina", _F6_AZUL_OSC), ("Receptor", _F6_ROJO)]),
                    unsafe_allow_html=True,
                )
        with st.expander("💡 ¿Cómo se calcula?"):
            st.markdown(_f6_como_se_calcula("ruido"), unsafe_allow_html=True)


def _render_card_flicker(df_receptores: pd.DataFrame) -> None:
    import importlib.util

    with st.container(border=True, key="f6_card_flicker"):
        _section_header(
            "Parpadeo de sombra (shadow flicker)",
            "Horas al año de sombra intermitente del rotor sobre cada receptor",
            "clock",
        )
        pvlib_ok = importlib.util.find_spec("pvlib") is not None
        if not pvlib_ok:
            st.warning("Este estudio necesita la posición solar de `pvlib`, que no está instalado.")
            st.caption("Sugerencia: `pip install pvlib` y reinicie la aplicación.")

        c1, c2 = st.columns(2)
        with c1:
            lim_h = st.number_input(
                "Límite anual (h/año)", min_value=1.0, max_value=200.0,
                value=_cfg_float(config, "f6_flicker_limite_h", 30.0), step=1.0, key="f6_flicker_lim",
            )
        with c2:
            alt_rec = st.number_input("Altura del receptor (m)", 0.5, 30.0, 1.5, 0.5, key="f6_flicker_alt_rec")
        diametro = _cfg_float(config, "diametro", 100.0)
        h_hub = _cfg_float(config, "f5_altura_deseada", _cfg_float(config, "perfil_hhub", 80.0))
        st.markdown(
            f'<div class="f6-pills"><span class="f6-pill info">🌀 Rotor Ø {_escape(_es_num(f"{diametro:.0f}"))} m (Fase 1)</span>'
            f'<span class="f6-pill info">🗼 Buje a {_escape(_es_num(f"{h_hub:.0f}"))} m (Fase 5)</span></div>',
            unsafe_allow_html=True,
        )

        if st.button("🌗 Calcular parpadeo de sombra", key="f6_flicker_btn", type="primary", disabled=not pvlib_ok,
                     use_container_width=True):
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
            st.markdown(_f6_como_se_calcula("flicker"), unsafe_allow_html=True)
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
                ("🌗", "Máximo anual", f"{int(peor['horas_flicker_anuales'])} h/año",
                 f"receptor {peor['receptor_id']}", _F6_VERDE if ok_todos else _F6_ROJO),
                ("⏱️", "Límite aplicado", f"{lim_usado:.0f} h/año",
                 "CUMPLEN todos" if ok_todos else "HAY EXCEDENCIAS", _F6_AMBAR),
                ("🌀", "Turbinas implicadas", str(int(peor["n_turbinas_contribuyen"])),
                 "en el receptor más afectado", _F6_AZUL),
                ("📍", "Receptores evaluados", str(len(df_fl)), ""),
            ], n=2),
            unsafe_allow_html=True,
        )
        st.markdown(
            _badge_html(
                f"Todos los receptores dentro del límite de {lim_usado:.0f} h/año" if ok_todos
                else "Excedencias de parpadeo — considere parada programada en las horas críticas",
                "ok" if ok_todos else "bad",
            ),
            unsafe_allow_html=True,
        )
        filas = []
        for _, r in df_fl.iterrows():
            hh = float(r["horas_flicker_anuales"])
            tip = _es_num(
                f"{r['receptor_id']} · {r['nombre']}\n{hh:.0f} h/año ({float(r.get('porcentaje_anio', 0) or 0):.2f} % del año)\n"
                f"Turbinas que la causan: {int(r['n_turbinas_contribuyen'])}"
            )
            filas.append((r["nombre"], hh, _F6_VERDE if hh <= lim_usado else _F6_ROJO, tip))
        svg = _f6_hbars_svg(filas, lineas=[(float(lim_usado), _F6_AMBAR, f"Límite {lim_usado:.0f} h", "8 6")], unidad="h")
        st.markdown(
            _f6_fig_html("Parpadeo por receptor · h/año", svg, [("Dentro del límite", _F6_VERDE), ("Excede", _F6_ROJO)]),
            unsafe_allow_html=True,
        )

        df_show = df_fl.rename(columns={
            "receptor_id": "Receptor", "nombre": "Nombre", "x_m": "x (m)", "y_m": "y (m)",
            "horas_flicker_anuales": "Horas/año", "porcentaje_anio": "% del año",
            "n_turbinas_contribuyen": "Turbinas", "turbinas_contrib": "Cuáles",
            "cumple_limite_30h": "Cumple",
        })
        df_show["Cumple"] = df_show["Cumple"].map({True: "✅ Sí", False: "❌ No"})
        with st.expander("📋 Tabla de detalle por receptor"):
            st.dataframe(df_show, hide_index=True, use_container_width=True)
        with st.expander("💡 ¿Cómo se calcula?"):
            st.markdown(_f6_como_se_calcula("flicker"), unsafe_allow_html=True)
        st.caption("Geometría simplificada (peor caso, sin nubosidad). " + _F6_SERIE_CAPTION)


def _render_card_aves() -> None:
    import bird_collision_band as bird

    with st.container(border=True, key="f6_card_aves"):
        _section_header(
            "Colisión de avifauna · Band 2007",
            "Colisiones esperadas por especie según su paso, el tamaño del rotor y la evasión",
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
            st.markdown('<div style="height:1.75rem"></div>', unsafe_allow_html=True)
            if st.button("💾 Guardar tabla de especies", key="f6_aves_guardar", use_container_width=True):
                guardar_config_values({"f6_aves_tabla_json": json.dumps(df_aves.to_dict("records"))})
                st.success("Tabla de especies guardada.")

        if st.button("🦅 Estimar colisiones anuales", key="f6_aves_btn", type="primary", use_container_width=True):
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
            st.markdown(_f6_como_se_calcula("aves"), unsafe_allow_html=True)
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        df_col = res["df"]
        total = float(df_col["colisiones_parque_anio"].sum())
        peor_cat = "ALTO" if (df_col["riesgo_categoria"] == "ALTO").any() else (
            "MEDIO" if (df_col["riesgo_categoria"] == "MEDIO").any() else "BAJO"
        )
        _col_riesgo = {"BAJO": _F6_VERDE, "MEDIO": _F6_AMBAR, "ALTO": _F6_ROJO}
        st.markdown(
            _kpi_html([
                ("🦅", "Colisiones parque", f"{total:.2f} aves/año", f"{len(df_col)} especies evaluadas"),
                ("⚠️", "Riesgo máximo", peor_cat, "escala BAJO / MEDIO / ALTO", _col_riesgo.get(peor_cat, _F6_GRIS)),
                ("🪶", "Especie más expuesta", _f6_nombre_corto(df_col.loc[df_col["colisiones_parque_anio"].idxmax(), "especie"], 22),
                 f"{float(df_col['colisiones_parque_anio'].max()):.2f} colisiones/año", _F6_AMBAR),
                ("⏱️", "Operación", f"{float(horas_op):,.0f} h/año", "", _F6_AZUL),
            ], n=2),
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
        filas = []
        for _, r in df_col.iterrows():
            v = float(r["colisiones_parque_anio"])
            tip = _es_num(
                f"{r['especie']}\nColisiones en el parque: {v:.2f} aves/año\n"
                f"Por turbina: {float(r.get('colisiones_turbina_anio', 0) or 0):.3f} aves/año\n"
                f"P. evasión: {float(r.get('p_evasion', 0) or 0):.2f} · Riesgo {r['riesgo_categoria']}"
            )
            filas.append((r["especie"], v, _col_riesgo.get(r["riesgo_categoria"], _F6_GRIS), tip))
        svg = _f6_hbars_svg(filas, decimales=2)
        st.markdown(
            _f6_fig_html("Colisiones esperadas · aves/año", svg,
                         [("Riesgo bajo", _F6_VERDE), ("Medio", _F6_AMBAR), ("Alto", _F6_ROJO)]),
            unsafe_allow_html=True,
        )

        df_show = df_col.rename(columns={
            "especie": "Especie", "n_aves_paso_anual": "Pasos/año", "p_evasion": "P. evasión",
            "colisiones_turbina_anio": "Colisiones/turbina·año", "colisiones_parque_anio": "Colisiones/parque·año",
            "p_geometrica": "P. geométrica", "p_paso_altura_rotor": "P. altura rotor",
            "riesgo_categoria": "Riesgo",
        })
        with st.expander("📋 Tabla de detalle por especie"):
            st.dataframe(df_show, hide_index=True, use_container_width=True)
        with st.expander("💡 ¿Cómo se calcula?"):
            st.markdown(_f6_como_se_calcula("aves"), unsafe_allow_html=True)


def _render_card_lca() -> None:
    import lca_carbon

    with st.container(border=True, key="f6_card_lca"):
        _section_header(
            "Huella de carbono · ACV ISO 14040",
            "Emisiones de todo el ciclo de vida, CO₂ evitado frente a la red y retorno de carbono",
            "globe",
        )
        c1, c2 = st.columns(2)
        with c1:
            cap_mw = st.number_input("Capacidad (MW)", 0.0, 5000.0,
                                     _cfg_float(config, "f5_potencia_instalada_mw", 0.0), 1.0, key="f6_lca_cap")
        with c2:
            aep = st.number_input("AEP neta (MWh/año)", 0.0, 10_000_000.0,
                                  _cfg_float(config, "f5_aep_neta_total_mwh", 0.0), 100.0, key="f6_lca_aep")
        c3, c4 = st.columns(2)
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
            st.markdown(_badge_html("Complete la Fase 5 (capacidad instalada y AEP neta) o escriba los valores arriba.", "info"),
                        unsafe_allow_html=True)
            st.markdown(_f6_como_se_calcula("lca"), unsafe_allow_html=True)
            return

        res = lca_carbon.calcular_huella_carbono_proyecto(
            cap_mw, aep, vida_util_anios=vida, grid_emission_factor_g_kwh=grid_factor,
        )
        arboles = lca_carbon.calcular_co2_equivalente_arboles(res["co2_evitado_anual_tCO2eq"])
        st.markdown(
            _kpi_html([
                ("🌱", "Huella del proyecto", f"{res['huella_g_kwh']:.1f} gCO₂eq/kWh",
                 "referencia eólica terrestre: ~11", _F6_VERDE),
                ("🌍", "CO₂ evitado", f"{res['co2_evitado_anual_tCO2eq']:,.0f} t/año",
                 f"{res['co2_evitado_lifetime_tCO2eq']:,.0f} t en {vida:.0f} años", _F6_VERDE),
                ("⏳", "Retorno de carbono", f"{res['payback_co2_anios']:.2f} años",
                 "tiempo en compensar el CO₂ de construcción", _F6_AMBAR),
                ("🌳", "Equivalente en árboles", f"{arboles['n_arboles_equivalentes_anuales']:,}",
                 f"≈ {arboles['hectareas_bosque_equivalentes']:,.0f} ha de bosque/año", "#15803d"),
            ], n=2),
            unsafe_allow_html=True,
        )

        _comp_es = {
            "manufactura_turbina": "Manufactura turbinas", "transporte": "Transporte",
            "instalacion": "Instalación", "om_lifetime": "O&M (vida útil)",
            "transmision_local": "Transmisión local", "desmantelamiento": "Desmantelamiento",
        }
        _cols_d = ["#0d9488", "#16a34a", "#5eead4", "#86efac", "#2dd4bf", "#bbf7d0"]
        segs = [
            (_comp_es.get(k, k), float(v), _cols_d[i % len(_cols_d)])
            for i, (k, v) in enumerate(res["desglose_componentes"].items())
        ]
        st.markdown(
            _f6_fig_html(
                "Desglose de la huella · gCO₂eq/kWh",
                _f6_donut_svg(segs, _es_num(f"{res['huella_g_kwh']:.1f}"), "gCO₂eq/kWh"),
                [(e, c) for e, _, c in segs],
            ),
            unsafe_allow_html=True,
        )

        df_alt = lca_carbon.comparar_vs_alternativas(res["huella_g_kwh"])
        filas = [("Este proyecto", float(res["huella_g_kwh"]), _F6_VERDE,
                  _es_num(f"Este proyecto: {res['huella_g_kwh']:.1f} gCO₂eq/kWh"))]
        for _, r in df_alt.sort_values("gCO2eq/kWh").iterrows():
            ref = "referencia" in str(r["Tecnología"])
            filas.append((
                str(r["Tecnología"]).replace(" (referencia)", " (ref.)"),
                float(r["gCO2eq/kWh"]),
                "#5eead4" if ref else _F6_GRIS,
                _es_num(f"{r['Tecnología']}: {float(r['gCO2eq/kWh']):.0f} gCO₂eq/kWh"),
            ))
        st.markdown(
            _f6_fig_html("Comparación con otras tecnologías · gCO₂eq/kWh (escala log)",
                         _f6_hbars_svg(filas, log=True),
                         [("Este proyecto", _F6_VERDE), ("Eólica terrestre (ref.)", "#5eead4"), ("Otras tecnologías", _F6_GRIS)]),
            unsafe_allow_html=True,
        )

        with st.expander("📋 Tablas de detalle"):
            st.dataframe(df_alt, hide_index=True, use_container_width=True)
            df_desglose = pd.DataFrame(
                [{"Componente": _comp_es.get(k, k), "gCO₂eq/kWh": v} for k, v in res["desglose_componentes"].items()]
            )
            st.dataframe(df_desglose, hide_index=True, use_container_width=True)
        with st.expander("💡 ¿Cómo se calcula?"):
            st.markdown(_f6_como_se_calcula("lca"), unsafe_allow_html=True)


def _render_ambiental() -> None:
    df_receptores = _render_card_receptores()
    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        _render_card_ruido(df_receptores)
    with col_b:
        _render_card_flicker(df_receptores)
    col_c, col_d = st.columns(2, gap="medium")
    with col_c:
        _render_card_aves()
    with col_d:
        _render_card_lca()


def _n_years_serie(df_h: pd.DataFrame) -> float:
    n = len(df_h)
    return max(n / 8760.0, 1e-9) if n else 1.0


# -----------------------------------------------------------------------------
# Operación y red · gráficos SVG Aurora (paridad mockup 06_fase6, acento ámbar).
# Mismo idioma que Ambiental: SVG inline + <title> = tooltip nativo.
# -----------------------------------------------------------------------------
_F6_MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _f6_ticks(lo: float, hi: float, n: int = 5) -> list:
    """Marcas 'redondas' (1/2/2,5/5 × 10^k) entre lo y hi."""
    span = float(hi) - float(lo)
    if not np.isfinite(span) or span <= 0:
        return [float(lo)]
    raw = span / n
    e = 10 ** np.floor(np.log10(raw))
    step = next(m * e for m in (1, 2, 2.5, 5, 10) if m * e >= raw)
    start = np.ceil(float(lo) / step) * step
    return [float(v) for v in np.arange(start, float(hi) + step * 0.5, step) if v <= float(hi) + 1e-9]


def _f6_fmt(v: float) -> str:
    a = abs(float(v))
    if a >= 1000:
        s = f"{v:,.0f}"
    elif a >= 10:
        s = f"{v:.0f}"
    elif a >= 1:
        s = f"{v:.1f}"
    elif a == 0:
        s = "0"
    else:
        s = f"{v:.2f}"
    return _es_num(s)


def _f6_frame(W, H, L, R, T, B, xlo, xhi, ylo, yhi, xlabel="", ylabel="", x_ticks=True):
    """Lienzo con rejilla, ejes y números. Devuelve (partes, sx, sy); el llamador cierra </svg>."""
    xspan = (float(xhi) - float(xlo)) or 1.0
    yspan = (float(yhi) - float(ylo)) or 1.0

    def sx(v):
        return L + (float(v) - float(xlo)) / xspan * (W - L - R)

    def sy(v):
        return H - B - (float(v) - float(ylo)) / yspan * (H - T - B)

    p = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">']
    for t in _f6_ticks(ylo, yhi, 5):
        y = sy(t)
        p.append(
            f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="#eef4fb" stroke-width="1.2"/>'
            f'<text x="{L - 6}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10.5" font-weight="700" fill="#94a3b8">{_f6_fmt(t)}</text>'
        )
    if x_ticks:
        for t in _f6_ticks(xlo, xhi, 6):
            p.append(
                f'<text x="{sx(t):.1f}" y="{H - B + 15}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#94a3b8">{_f6_fmt(t)}</text>'
            )
    p.append(
        f'<line x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}" stroke="#c4d4e8" stroke-width="1.6"/>'
        f'<line x1="{L}" y1="{T - 6}" x2="{L}" y2="{H - B}" stroke="#c4d4e8" stroke-width="1.6"/>'
    )
    if xlabel:
        p.append(
            f'<text x="{(L + W - R) / 2:.1f}" y="{H - 5}" text-anchor="middle" font-size="11" font-weight="800" fill="#64748b">{_svg_t(xlabel)}</text>'
        )
    if ylabel:
        ym = (T + H - B) / 2
        p.append(
            f'<text x="13" y="{ym:.1f}" text-anchor="middle" font-size="11" font-weight="800" fill="#64748b" '
            f'transform="rotate(-90 13 {ym:.1f})">{_svg_t(ylabel)}</text>'
        )
    return p, sx, sy


def _f6_scatter_svg(x, y) -> str:
    """Potencia modelo vs real (cada punto una hora) + línea 1:1."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    if not len(x):
        return ""
    hi = float(max(x.max(), y.max(), 1e-6)) * 1.05
    lo = float(min(0.0, x.min(), y.min()))
    p, sx, sy = _f6_frame(380, 320, 50, 14, 16, 42, lo, hi, lo, hi, "Modelo (MW)", "Real (MW)")
    p.append(
        '<g fill="#d97706" fill-opacity=".30">'
        + "".join(f'<circle cx="{sx(a):.1f}" cy="{sy(b):.1f}" r="2.3"/>' for a, b in zip(x, y))
        + "</g>"
    )
    p.append(
        f'<g><title>Línea 1:1 · modelo perfecto</title><line x1="{sx(lo):.1f}" y1="{sy(lo):.1f}" x2="{sx(hi):.1f}" '
        f'y2="{sy(hi):.1f}" stroke="#dc2626" stroke-width="2.2" stroke-dasharray="6 5"/></g>'
        f'<text x="{sx(hi) - 4:.1f}" y="{sy(hi) + 16:.1f}" text-anchor="end" font-size="11" font-weight="900" fill="#dc2626">1:1</text>'
        "</svg>"
    )
    return "".join(p)


def _f6_hist_svg(vals, bias: float) -> str:
    """Histograma de residuales (real − modelo) con línea en 0 y en el bias."""
    v = np.asarray(vals, dtype=float)
    v = v[np.isfinite(v)]
    if not len(v):
        return ""
    counts, edges = np.histogram(v, bins=40)
    top = float(counts.max()) * 1.14 or 1.0
    p, sx, sy = _f6_frame(380, 320, 50, 14, 28, 42, float(edges[0]), float(edges[-1]), 0, top,
                          "Residual real − modelo (MW)", "Horas")
    for c, a, b in zip(counts, edges[:-1], edges[1:]):
        if c <= 0:
            continue
        x0, x1, yy = sx(a), sx(b), sy(c)
        tip = _es_num(f"{a:.2f} a {b:.2f} MW: {int(c):,} horas")
        p.append(
            f'<rect x="{x0 + 0.6:.1f}" y="{yy:.1f}" width="{max(1.0, x1 - x0 - 1.2):.1f}" height="{sy(0) - yy:.1f}" rx="2" '
            f'fill="#fcd34d" stroke="#d97706" stroke-width=".8"><title>{_svg_t(tip)}</title></rect>'
        )
    for xv, col, etq, dash in ((0.0, "#64748b", "", "none"),
                               (float(bias), "#dc2626", _es_num(f"sesgo {bias:+.2f} MW"), "6 5")):
        if edges[0] <= xv <= edges[-1]:
            xx = sx(xv)
            p.append(f'<line x1="{xx:.1f}" y1="20" x2="{xx:.1f}" y2="{sy(0):.1f}" stroke="{col}" stroke-width="2" stroke-dasharray="{dash}"/>')
            if etq:
                p.append(f'<text x="{xx:.1f}" y="15" text-anchor="middle" font-size="10.5" font-weight="900" fill="{col}">{_svg_t(etq)}</text>')
    p.append("</svg>")
    return "".join(p)


def _f6_barras_mes_svg(df_mes, series) -> str:
    """Barras apiladas por mes. series=[(columna, nombre, color)]."""
    cols = [c for c, _, _ in series]
    tot = df_mes[cols].sum(axis=1)
    top = float(tot.max()) * 1.15 if len(tot) and float(tot.max()) > 0 else 1.0
    W, H, L, R, T, B = 380, 250, 50, 10, 16, 34
    p, sx, sy = _f6_frame(W, H, L, R, T, B, 0, 12, 0, top, "", "MWh/año", x_ticks=False)
    w = (sx(1) - sx(0)) * 0.64
    for m in df_mes.index:
        i = int(m) - 1
        if not 0 <= i < 12:
            continue
        xc = sx(i + 0.5)
        acc = 0.0
        for col, nombre, color in series:
            val = float(df_mes.loc[m, col])
            if val <= 0:
                continue
            y1, y0 = sy(acc + val), sy(acc)
            tip = _es_num(f"{_F6_MESES[i]} · {nombre}: {val:,.1f} MWh/año")
            p.append(
                f'<rect x="{xc - w / 2:.1f}" y="{y1:.1f}" width="{w:.1f}" height="{max(0.6, y0 - y1):.1f}" fill="{color}">'
                f"<title>{_svg_t(tip)}</title></rect>"
            )
            acc += val
    for i in range(12):
        p.append(
            f'<text x="{sx(i + 0.5):.1f}" y="{H - B + 15}" text-anchor="middle" font-size="10" font-weight="800" fill="#64748b">{_F6_MESES[i]}</text>'
        )
    p.append("</svg>")
    return "".join(p)


def _f6_barrido_svg(x, e_iny, curt, x_rec: float) -> str:
    """Barrido solar: energía inyectada (eje izq., ámbar) y curtailment % (eje der., rojo)."""
    x = np.asarray(x, dtype=float)
    e = np.asarray(e_iny, dtype=float)
    c = np.asarray(curt, dtype=float)
    if len(x) < 2:
        return ""
    # Lienzo ancho: la card híbrida ocupa todo el ancho (texto legible sin agigantarse).
    W, H, L, R, T, B = 900, 300, 84, 70, 32, 46
    e_hi = float(np.nanmax(e)) * 1.12 or 1.0
    c_hi = max(float(np.nanmax(c)) * 1.15, 1.0)
    p, sx, sy = _f6_frame(W, H, L, R, T, B, float(x.min()), float(x.max()), 0, e_hi,
                          "Capacidad solar añadida (MW)", "Energía inyectada (MWh/año)")

    def sy2(v):
        return H - B - float(v) / c_hi * (H - T - B)

    for t in _f6_ticks(0, c_hi, 5):
        p.append(f'<text x="{W - R + 7}" y="{sy2(t) + 3.5:.1f}" font-size="10.5" font-weight="700" fill="#f87171">{_f6_fmt(t)} %</text>')
    ym = (T + H - B) / 2
    p.append(
        f'<text x="{W - 8}" y="{ym:.1f}" text-anchor="middle" font-size="11" font-weight="800" fill="#dc2626" '
        f'transform="rotate(90 {W - 8} {ym:.1f})">Curtailment (%)</text>'
    )
    pts_e = " L".join(f"{sx(a):.1f},{sy(b):.1f}" for a, b in zip(x, e))
    p.append(
        f'<path d="M{pts_e} L{sx(x[-1]):.1f},{H - B} L{sx(x[0]):.1f},{H - B} Z" fill="#d97706" opacity=".10"/>'
        f'<path d="M{pts_e}" fill="none" stroke="#d97706" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    pts_c = " L".join(f"{sx(a):.1f},{sy2(b):.1f}" for a, b in zip(x, c))
    p.append(f'<path d="M{pts_c}" fill="none" stroke="#dc2626" stroke-width="2.6" stroke-dasharray="7 5" stroke-linecap="round"/>')
    xr = sx(x_rec)
    p.append(
        f'<line x1="{xr:.1f}" y1="{T - 8}" x2="{xr:.1f}" y2="{H - B}" stroke="#16a34a" stroke-width="2.4" stroke-dasharray="5 4"/>'
        f'<text x="{xr:.1f}" y="{T - 12}" text-anchor="middle" font-size="11" font-weight="900" fill="#15803d">'
        f'{_svg_t(_es_num(f"Recomendado {x_rec:.0f} MW"))}</text>'
    )
    for a, b, cc in zip(x, e, c):
        tip = _es_num(f"Solar {a:.0f} MW\nInyectada {b:,.0f} MWh/año\nCurtailment {cc:.1f} %")
        p.append(
            f'<g class="f6-bar"><title>{_svg_t(tip)}</title>'
            f'<circle cx="{sx(a):.1f}" cy="{sy(b):.1f}" r="4.2" fill="#fff" stroke="#d97706" stroke-width="2.6"/>'
            f'<circle cx="{sx(a):.1f}" cy="{sy2(cc):.1f}" r="3.4" fill="#fff" stroke="#dc2626" stroke-width="2.2"/></g>'
        )
    p.append("</svg>")
    return "".join(p)


def _f6_torre_red_svg(x: float, y: float, s: float = 1.0) -> str:
    """Torre de alta tensión (celosía) para los esquemas de red."""
    return (
        f'<g transform="translate({x:.1f},{y:.1f}) scale({s})" fill="none" stroke="#475569" stroke-width="2" stroke-linejoin="round">'
        '<path d="M-12,0 L-3,-46 L3,-46 L12,0"/><path d="M-9,-14 L9,-14 M-6,-30 L6,-30 M-10,-5 L6,-30 M10,-5 L-6,-30"/>'
        '<path d="M-20,-38 L20,-38 M-16,-44 L16,-44"/></g>'
    )


def _f6_esquema_operacion(tipo: str) -> str:
    """Esquemas '¿Cómo se valida/calcula?' de Operación y red (tono ámbar)."""
    if tipo == "scada":
        xs = np.linspace(40, 330, 30)
        mod = 92 - 42 * np.sin((xs - 40) / 290 * 2 * np.pi) - 10 * np.sin((xs - 40) / 45)
        real = mod + 9 * np.sin((xs - 40) / 23) + 4
        pm = " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, mod))
        pr = " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, real))
        svg = (
            '<svg viewBox="0 0 560 160" xmlns="http://www.w3.org/2000/svg">'
            '<line x1="36" y1="140" x2="336" y2="140" stroke="#c4d4e8" stroke-width="1.6"/>'
            '<line x1="36" y1="24" x2="36" y2="140" stroke="#c4d4e8" stroke-width="1.6"/>'
            f'<path d="M{pm}" fill="none" stroke="#0d9488" stroke-width="3" stroke-linecap="round"/>'
            f'<path d="M{pr}" fill="none" stroke="#d97706" stroke-width="2.6" stroke-dasharray="6 5" class="f6-flow"/>'
            '<text x="186" y="156" text-anchor="middle" font-size="10" font-weight="800" fill="#64748b">horas</text>'
            '<text x="44" y="20" font-size="10" font-weight="900" fill="#0f766e">— modelo</text>'
            '<text x="116" y="20" font-size="10" font-weight="900" fill="#b45309">- - real (SCADA)</text>'
            '<g font-size="10" font-weight="900">'
            '<rect x="356" y="26" width="192" height="26" rx="13" fill="#fffbeb" stroke="#fde68a"/>'
            '<text x="452" y="43" text-anchor="middle" fill="#b45309">R² · ¿sigue la misma forma?</text>'
            '<rect x="356" y="62" width="192" height="26" rx="13" fill="#fffbeb" stroke="#fde68a"/>'
            '<text x="452" y="79" text-anchor="middle" fill="#b45309">Sesgo · error medio (real − modelo)</text>'
            '<rect x="356" y="98" width="192" height="26" rx="13" fill="#fffbeb" stroke="#fde68a"/>'
            '<text x="452" y="115" text-anchor="middle" fill="#b45309">RMSE · error típico hora a hora</text>'
            "</g></svg>"
        )
        titulo = "💡 ¿Cómo se valida?"
        txt = ("Se alinean por hora la potencia que predice el modelo (Fases 2–5) y la medida en el parque. "
               "Si el ratio real/modelo está entre 0,95 y 1,05 el modelo es fiable; fuera de eso conviene recalibrar.")
    elif tipo == "curtail":
        svg = (
            '<svg viewBox="0 0 560 160" xmlns="http://www.w3.org/2000/svg">'
            + _f6_turbina_svg(56, 138, "Parque", "Producción del parque", 1.4)
            + '<path d="M84,112 L236,112" stroke="#fbbf24" stroke-width="4" stroke-dasharray="8 7" class="f6-flow"/>'
            '<rect x="238" y="88" width="78" height="48" rx="10" fill="#fff" stroke="#d97706" stroke-width="2.2"/>'
            '<text x="277" y="108" text-anchor="middle" font-size="10" font-weight="900" fill="#b45309">Conexión</text>'
            '<text x="277" y="124" text-anchor="middle" font-size="9.5" font-weight="800" fill="#64748b">límite MW</text>'
            '<path d="M318,112 L452,112" stroke="#16a34a" stroke-width="4" stroke-dasharray="8 7" class="f6-flow"/>'
            + _f6_torre_red_svg(486, 140, 1.1)
            + '<text x="486" y="156" text-anchor="middle" font-size="10" font-weight="900" fill="#475569">Red</text>'
            '<g font-size="10" font-weight="900">'
            '<rect x="20" y="10" width="170" height="26" rx="13" fill="#eff6ff" stroke="#bfdbfe"/>'
            '<text x="105" y="27" text-anchor="middle" fill="#1d4ed8">⚡ Capacidad: supera el límite</text>'
            '<rect x="196" y="10" width="170" height="26" rx="13" fill="#fffbeb" stroke="#fde68a"/>'
            '<text x="281" y="27" text-anchor="middle" fill="#b45309">💲 Económico: precio &lt; costo</text>'
            '<rect x="372" y="10" width="170" height="26" rx="13" fill="#fef2f2" stroke="#fecaca"/>'
            '<text x="457" y="27" text-anchor="middle" fill="#b91c1c">🚧 Red: no disponible</text>'
            "</g></svg>"
        )
        titulo = "💡 ¿Cómo se calcula?"
        txt = ("Hora a hora se recorta la energía que no cabe en la conexión, la que se vendería por debajo del costo "
               "variable (precio de bolsa simulado) y la que se pierde cuando la red no está disponible.")
    else:  # hibrido
        panel = (
            '<g transform="translate(158,132)">'
            '<path d="M-30,0 L-18,-30 L30,-30 L18,0 Z" fill="#1e40af" stroke="#1e3a8a" stroke-width="1.6"/>'
            '<path d="M-26,-10 L22,-10 M-22,-20 L26,-20 M-6,0 L6,-30 M10,0 L22,-30 M-22,0 L-10,-30" stroke="#93c5fd" stroke-width="1.2"/>'
            '<line x1="0" y1="0" x2="0" y2="8" stroke="#475569" stroke-width="3"/></g>'
            '<circle cx="182" cy="58" r="11" fill="#fbbf24"/>'
        )
        bateria = (
            '<g transform="translate(252,100)">'
            '<rect x="-24" y="-24" width="48" height="40" rx="7" fill="#fff" stroke="#16a34a" stroke-width="2.4"/>'
            '<rect x="-8" y="-30" width="16" height="6" rx="2" fill="#16a34a"/>'
            '<rect x="-17" y="4" width="34" height="7" rx="2" fill="#16a34a" class="f6-charge"/>'
            '<rect x="-17" y="-6" width="34" height="7" rx="2" fill="#16a34a" class="f6-charge" style="animation-delay:.4s"/>'
            '<rect x="-17" y="-16" width="34" height="7" rx="2" fill="#16a34a" class="f6-charge" style="animation-delay:.8s"/></g>'
        )
        svg = (
            '<svg viewBox="0 0 620 160" xmlns="http://www.w3.org/2000/svg">'
            + _f6_turbina_svg(62, 136, "Viento", "Parque eólico", 1.4) + panel + bateria
            + '<text x="158" y="152" text-anchor="middle" font-size="9.5" font-weight="900" fill="#1e3a8a">Solar</text>'
            '<text x="252" y="136" text-anchor="middle" font-size="9.5" font-weight="900" fill="#15803d">BESS</text>'
            '<path d="M88,104 Q260,40 382,96" fill="none" stroke="#60a5fa" stroke-width="3" stroke-dasharray="7 6" class="f6-flow"/>'
            '<path d="M188,110 Q290,80 382,100" fill="none" stroke="#fbbf24" stroke-width="3" stroke-dasharray="7 6" class="f6-flow"/>'
            '<path d="M278,98 L382,104" fill="none" stroke="#4ade80" stroke-width="3" stroke-dasharray="7 6" class="f6-flow"/>'
            '<circle cx="404" cy="102" r="22" fill="#fffbeb" stroke="#d97706" stroke-width="2.4"/>'
            '<text x="404" y="109" text-anchor="middle" font-size="18">⚡</text>'
            '<text x="404" y="142" text-anchor="middle" font-size="9.5" font-weight="900" fill="#b45309">Punto de conexión</text>'
            '<path d="M428,102 L520,102" stroke="#d97706" stroke-width="4" stroke-dasharray="8 7" class="f6-flow"/>'
            + _f6_torre_red_svg(552, 130, 1.1)
            + '<text x="552" y="148" text-anchor="middle" font-size="9.5" font-weight="900" fill="#475569">Red</text>'
            '<text x="310" y="20" text-anchor="middle" font-size="12" font-weight="900" fill="#0b2447">'
            "Viento + solar comparten la misma conexión; la batería guarda lo que no cabe</text>"
            "</svg>"
        )
        titulo = "💡 ¿Cómo funciona?"
        txt = ("Se prueba añadir cada vez más potencia solar sobre la misma conexión: al principio casi todo se inyecta; "
               "a partir de cierto tamaño crece el recorte. Se recomienda el mayor solar con recorte menor al 10 % y "
               "se dimensiona una batería para desplazar la energía recortada.")
    return f'<div class="f6-how amb"><div class="f6-how-t">{titulo}</div>{svg}<p>{_escape(txt)}</p></div>'


def _render_card_scada() -> None:
    with st.container(border=True, key="f6_card_scada"):
        _section_header(
            "Validación contra SCADA",
            "Producción modelada frente a la real del parque, hora a hora",
            "🗄️",
        )
        st.markdown(
            '<div class="f6-pills"><span class="f6-pill warn">📑 CSV o Excel</span>'
            '<span class="f6-pill warn">columnas timestamp + P_kW (o P_MW)</span>'
            '<span class="f6-pill info">turbine_id opcional</span></div>',
            unsafe_allow_html=True,
        )
        scada_file = st.file_uploader("Archivo SCADA (.csv / .xlsx)", type=["csv", "xlsx", "xls"], key="f6_scada_file")

        df_scada = None
        if scada_file is not None:
            import validacion_scada

            try:
                df_scada = validacion_scada.importar_scada_csv(scada_file.getvalue(), scada_file.name)
                st.caption(
                    _es_num(f"SCADA leído: {len(df_scada):,} filas · {df_scada['turbine_id'].nunique()} turbina(s) · ")
                    + f"{df_scada['timestamp'].min()} → {df_scada['timestamp'].max()}"
                )
            except ValueError as exc:
                st.error(str(exc))

        if st.button("📊 Comparar contra el modelo", key="f6_scada_btn", type="primary", disabled=df_scada is None,
                     use_container_width=True):
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
            st.markdown(_f6_esquema_operacion("scada"), unsafe_allow_html=True)
            return
        if res.get("error"):
            st.warning(res["error"])
            return
        if not res.get("ok"):
            st.warning(f"{res.get('msg', 'Solapamiento insuficiente')} (n={res.get('n_samples', 0)}). "
                       "Verifique que las fechas del SCADA coincidan con la serie NASA.")
            return

        r2 = float(res["r2"])
        st.markdown(
            _kpi_html([
                ("R²", "R²", f"{r2:.3f}", f"{res['n_samples']:,} horas comparadas",
                 _F6_VERDE if r2 >= 0.8 else (_F6_AMBAR if r2 >= 0.6 else _F6_ROJO)),
                ("Δ", "Sesgo", f"{res['bias_MW']:+.2f} MW", "real − modelo (negativo = modelo optimista)", _F6_AMBAR),
                ("σ", "RMSE", f"{res['rmse_MW']:.2f} MW", f"MAE = {res['mae_MW']:.2f} MW", _F6_AZUL),
                ("⚖️", "Ratio de eficiencia", f"{res['efficiency_ratio']:.3f}",
                 f"energía real/modelo = {res['energia_real_MWh']:,.0f}/{res['energia_modelo_MWh']:,.0f} MWh", "#0d9488"),
            ], n=2),
            unsafe_allow_html=True,
        )
        tono = "ok" if 0.95 <= res["efficiency_ratio"] <= 1.05 else ("warn" if 0.90 <= res["efficiency_ratio"] <= 1.10 else "bad")
        st.markdown(
            _badge_html(_es_num(f"Desviación modelo vs real: {(res['efficiency_ratio'] - 1) * 100:+.1f} %"), tono),
            unsafe_allow_html=True,
        )

        dfc = res["df_compare"]
        muestras = dfc.sample(min(len(dfc), 1500), random_state=7) if len(dfc) > 1500 else dfc
        st.markdown(
            _f6_fig_html("Potencia modelo vs real · cada punto es una hora",
                         _f6_scatter_svg(muestras["P_modelo_MW"], muestras["P_real_MW"]),
                         [("Horas comparadas", _F6_AMBAR), ("1:1 = modelo perfecto", _F6_ROJO)]),
            unsafe_allow_html=True,
        )
        st.markdown(
            _f6_fig_html("Distribución de residuales · pase el cursor por cada barra",
                         _f6_hist_svg(dfc["residual_MW"], float(res["bias_MW"])),
                         [("Horas por intervalo de error", "#fcd34d"), ("Sesgo medio", _F6_ROJO)]),
            unsafe_allow_html=True,
        )
        with st.expander("💡 ¿Cómo se valida?"):
            st.markdown(_f6_esquema_operacion("scada"), unsafe_allow_html=True)
        st.caption(_F6_SERIE_CAPTION)


def _render_card_curtailment() -> None:
    with st.container(border=True, key="f6_card_curtail"):
        _section_header(
            "Curtailment de red",
            "Energía que no se puede inyectar: límite de conexión, precio y disponibilidad de la red",
            "🔌",
        )
        pot_inst = _cfg_float(config, "f5_potencia_instalada_mw", 0.0)
        c1, c2, c3 = st.columns(3)
        with c1:
            cap_iny = st.number_input(
                "Cap. inyección (MW)", min_value=0.1, max_value=5000.0,
                value=_cfg_float(config, "f6_cap_inyeccion_mw", round(pot_inst * 0.8, 1) if pot_inst > 0 else 10.0),
                step=0.5, key="f6_curt_cap",
                help="Capacidad de inyección: límite del punto de conexión (STN/SDL).",
            )
        with c2:
            disp_red = st.number_input(
                "Disp. red (%)", min_value=80.0, max_value=100.0,
                value=_cfg_float(config, "f6_disp_red_pct", 98.0), step=0.5, key="f6_curt_disp",
                help="Disponibilidad de la red: % del tiempo en que la red puede recibir energía.",
            )
        with c3:
            cv_usd = st.number_input(
                "Costo variable (USD/MWh)", min_value=0.0, max_value=100.0, value=5.0, step=1.0,
                key="f6_curt_cv", help="Si el precio de bolsa simulado cae por debajo, no se inyecta.",
            )

        if st.button("🔌 Simular curtailment", key="f6_curt_btn", type="primary", use_container_width=True):
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
            st.markdown(_f6_esquema_operacion("curtail"), unsafe_allow_html=True)
            return
        if res.get("error"):
            st.warning(res["error"])
            return

        kpis = res["kpis"]
        ny = res.get("n_years", 1.0)
        st.markdown(
            _kpi_html([
                ("⚡", "Energía inyectada", f"{kpis['energia_final_inyectada_MWh'] / ny:,.0f} MWh/año",
                 f"de {kpis['energia_bruta_MWh'] / ny:,.0f} MWh/año generables", _F6_VERDE),
                ("✂️", "Recorte total", f"{kpis['pct_recorte_total']:.2f} %",
                 f"{kpis['energia_recortada_total_MWh'] / ny:,.0f} MWh/año perdidos", _F6_ROJO),
                ("🔌", "Por capacidad", f"{kpis['pct_recorte_capacity']:.2f} %",
                 f"{int(kpis['horas_curtailed_capacity'] / ny):,} h/año limitadas", _F6_AZUL),
                ("💲", "Económico + red", f"{kpis['pct_recorte_economico']:.2f} % + {kpis['pct_recorte_downtime']:.2f} %",
                 f"{int(kpis['horas_curtailed_economico'] / ny):,} h/año bajo costo variable", _F6_AMBAR),
            ], n=2),
            unsafe_allow_html=True,
        )
        e_cap = kpis["pct_recorte_capacity"]
        e_eco = kpis["pct_recorte_economico"]
        e_red = kpis["pct_recorte_downtime"]
        segs = [
            ("Inyectada", max(0.0, 100.0 - e_cap - e_eco - e_red), _F6_VERDE),
            ("Recorte por capacidad", e_cap, _F6_AZUL),
            ("Recorte económico", e_eco, _F6_AMBAR),
            ("Red no disponible", e_red, _F6_ROJO),
        ]
        st.markdown(
            _f6_fig_html("Reparto de la energía generable",
                         _f6_donut_svg(segs, _es_num(f"{kpis['pct_recorte_total']:.1f} %"), "recorte total"),
                         [(e, c) for e, _, c in segs]),
            unsafe_allow_html=True,
        )
        if res.get("df_mes") is not None and len(res["df_mes"]):
            series = [
                ("energia_recortada_capacity_MWh", "Capacidad", _F6_AZUL),
                ("energia_recortada_economica_MWh", "Económico", _F6_AMBAR),
                ("energia_recortada_downtime_MWh", "Red caída", _F6_ROJO),
            ]
            st.markdown(
                _f6_fig_html("Energía recortada por mes · MWh/año", _f6_barras_mes_svg(res["df_mes"], series),
                             [(n, c) for _, n, c in series]),
                unsafe_allow_html=True,
            )
        st.caption("Precio de bolsa simulado (lognormal ~45 USD/MWh) — conecte datos XM reales para un análisis fino.")
        with st.expander("💡 ¿Cómo se calcula?"):
            st.markdown(_f6_esquema_operacion("curtail"), unsafe_allow_html=True)


def _render_card_hibrido() -> None:
    import importlib.util

    with st.container(border=True, key="f6_card_hibrido"):
        _section_header(
            "Planta híbrida · viento + solar + BESS",
            "Cuánta potencia solar cabe en la misma conexión y qué batería conviene",
            "🔆",
        )
        st.markdown(_f6_esquema_operacion("hibrido"), unsafe_allow_html=True)
        if importlib.util.find_spec("pvlib") is None:
            st.caption(
                "ℹ️ `pvlib` no está instalado: el perfil solar usa una aproximación sinusoidal. "
                "Para cielo claro real: `pip install pvlib`."
            )
        c1, c2, c3 = st.columns(3)
        with c1:
            cap_iny_h = st.number_input(
                "Cap. inyección (MW)", min_value=0.1, max_value=5000.0,
                value=_cfg_float(config, "f6_cap_inyeccion_mw",
                                 round(_cfg_float(config, "f5_potencia_instalada_mw", 10.0) * 0.8, 1) or 10.0),
                step=0.5, key="f6_hib_cap",
                help="Capacidad de inyección del punto de conexión compartido.",
            )
        with c2:
            solar_max = st.slider("Solar máxima a evaluar (MW)", 5, 200,
                                  50, 5, key="f6_hib_solar_max")
        with c3:
            bess_usd = st.number_input("Costo BESS (USD/kWh)", 50.0, 1000.0, 300.0, 25.0, key="f6_hib_bess")

        if st.button("🔆 Analizar planta híbrida", key="f6_hib_btn", type="primary", use_container_width=True):
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
                        # DatetimeIndex (no Series): pvlib.get_clearsky falla con una Series de fechas
                        # en pandas reciente ("Addition/subtraction of integers ... DatetimeArray").
                        timestamps=pd.DatetimeIndex(pd.to_datetime(df_h["timestamp"], errors="coerce")),
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
                ("☀️", "Solar recomendado", f"{res['recomendacion_solar_mw']:.0f} MW",
                 "máxima inyección con curtailment < 10 %" if float(res["curtailment_pct_recomendado"]) < 10.0
                 else "ningún tamaño baja del 10 % de recorte: máxima inyección", _F6_AMBAR),
                ("⚡", "Energía inyectada", f"{res['energia_inyectada_recomendada_MWh'] / ny:,.0f} MWh/año",
                 f"curtailment {res['curtailment_pct_recomendado']:.1f} %", _F6_VERDE),
                ("🔋", "BESS sugerido", f"{storage.get('capacidad_bess_MWh', 0.0):,.1f} MWh",
                 f"CAPEX ≈ {storage.get('capex_bess_usd', 0.0) / 1e6:,.1f} MUSD", _F6_AZUL),
                ("🔁", "Energía desplazable", f"{storage.get('energia_potencial_shift_anual_MWh', 0.0) / ny:,.0f} MWh/año",
                 f"eficiencia ida y vuelta {storage.get('eficiencia_round_trip_pct', 0):.0f} %", "#0d9488"),
            ]),
            unsafe_allow_html=True,
        )
        sweep = res["sweep_solar"]
        st.markdown(
            _f6_fig_html(
                "Barrido solar · inyección vs curtailment (pase el cursor por cada punto)",
                _f6_barrido_svg(sweep["capacidad_solar_MW"], sweep["energia_inyectada_MWh"] / ny,
                                sweep["curtailment_pct"], float(res["recomendacion_solar_mw"])),
                [("Energía inyectada (MWh/año)", _F6_AMBAR), ("Curtailment (%)", _F6_ROJO), ("Solar recomendado", _F6_VERDE)],
            ),
            unsafe_allow_html=True,
        )
        st.caption(_F6_SERIE_CAPTION)


def _render_operacion_red() -> None:
    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        _render_card_scada()
    with col_b:
        _render_card_curtailment()
    _render_card_hibrido()


# -----------------------------------------------------------------------------
# Optimización y fin de vida · gráficos SVG Aurora (paridad mockup 06_fase6,
# acento violeta). Mismo idioma que Ambiental / Operación: SVG inline + <title>.
# -----------------------------------------------------------------------------
_F6_VIOLETA = "#7c3aed"
_F6_VIOLETA_OSC = "#4c1d95"


def _f6_convergencia_svg(it, best) -> str:
    """Mejor AEP por generación del Differential Evolution."""
    it = np.asarray(it, dtype=float)
    b = np.asarray(best, dtype=float)
    if not len(it):
        return ""
    lo, hi = float(np.nanmin(b)), float(np.nanmax(b))
    pad = (hi - lo) * 0.25 or max(abs(hi) * 0.01, 1.0)
    x_lo, x_hi = (float(it.min()), float(it.max())) if len(it) > 1 else (0.0, float(it[0]) + 1.0)
    p, sx, sy = _f6_frame(380, 260, 64, 16, 18, 40, x_lo, x_hi, lo - pad, hi + pad, "Generación", "Mejor AEP (MWh/año)")
    pts = " L".join(f"{sx(a):.1f},{sy(v):.1f}" for a, v in zip(it, b))
    if len(it) > 1:
        p.append(
            f'<path d="M{pts} L{sx(it[-1]):.1f},{sy(lo - pad):.1f} L{sx(it[0]):.1f},{sy(lo - pad):.1f} Z" fill="{_F6_VIOLETA}" opacity=".09"/>'
            f'<path d="M{pts}" fill="none" stroke="{_F6_VIOLETA}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    for a, v in zip(it, b):
        tip = _es_num(f"Generación {a:.0f}\nMejor AEP {v:,.0f} MWh/año")
        p.append(
            f'<g class="f6-bar"><title>{_svg_t(tip)}</title>'
            f'<circle cx="{sx(a):.1f}" cy="{sy(v):.1f}" r="4" fill="#fff" stroke="{_F6_VIOLETA}" stroke-width="2.6"/></g>'
        )
    p.append("</svg>")
    return "".join(p)


def _f6_layout_antes_despues_svg(df_orig, df_opt) -> str:
    """Plano del layout actual (gris) y optimizado (violeta) con flecha de desplazamiento."""
    def _pts(df):
        out = []
        for i, (_, r) in enumerate(df.iterrows()):
            try:
                out.append((str(r.get("turbina_id") or f"T{i + 1}"), float(r["x_m"]), float(r["y_m"])))
            except (TypeError, ValueError, KeyError):
                continue
        return out

    o, n = _pts(df_orig), _pts(df_opt)
    xs = [t[1] for t in o + n]
    ys = [t[2] for t in o + n]
    if not xs:
        return ""
    W, H = 380.0, 310.0
    L, R, T, B = 30.0, 30.0, 44.0, 40.0
    dx, dy = max(max(xs) - min(xs), 1.0), max(max(ys) - min(ys), 1.0)
    esc = min((W - L - R) / dx, (H - T - B) / dy)
    xc, yc = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def P(x, y):
        return L + (W - L - R) / 2 + (x - xc) * esc, T + (H - T - B) / 2 - (y - yc) * esc

    p = [
        '<svg viewBox="0 0 380 310" xmlns="http://www.w3.org/2000/svg">',
        '<defs><marker id="f6arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">'
        f'<path d="M0,0 L10,5 L0,10 z" fill="{_F6_VIOLETA}"/></marker></defs>',
        '<rect x="6" y="6" width="368" height="298" rx="16" fill="#faf5ff" stroke="#ede9fe"/>',
    ]
    for k in range(min(len(o), len(n))):
        (ax, ay), (bx, by) = P(o[k][1], o[k][2]), P(n[k][1], n[k][2])
        d = float(np.hypot(n[k][1] - o[k][1], n[k][2] - o[k][2]))
        if np.hypot(bx - ax, by - ay) > 10:
            p.append(
                f'<g><title>{_svg_t(_es_num(f"{o[k][0]} se movió {d:,.0f} m"))}</title>'
                f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="#a78bfa" stroke-width="2" '
                'stroke-dasharray="5 4" marker-end="url(#f6arrow)"/></g>'
            )
    for tid, x, y in o:
        px, py = P(x, y)
        tip = _es_num(f"{tid} · posición actual\nx = {x:,.0f} m · y = {y:,.0f} m")
        p.append(
            f'<g class="f6-rec"><title>{_svg_t(tip)}</title><circle cx="{px:.1f}" cy="{py:.1f}" r="7" fill="#fff" stroke="#94a3b8" stroke-width="2.2"/>'
            f'<text x="{px:.1f}" y="{py - 11:.1f}" text-anchor="middle" font-size="9.5" font-weight="900" fill="#64748b">{_svg_t(tid)}</text></g>'
        )
    s_tb = 0.8
    if len(n) > 1:
        pts = [P(x, y) for _, x, y in n]
        dmin = min(float(np.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
                   for i in range(len(pts)) for j in range(i + 1, len(pts)))
        s_tb = float(min(0.8, max(0.4, dmin / 60.0)))
    for k, (tid, x, y) in enumerate(n):
        px, py = P(x, y)
        mov = ""
        if k < len(o):
            mov = _es_num(f"\nse movió {float(np.hypot(x - o[k][1], y - o[k][2])):,.0f} m")
        tip = _es_num(f"{tid} · posición optimizada\nx = {x:,.0f} m · y = {y:,.0f} m") + mov
        p.append(_f6_turbina_svg(px, py, tid, tip, s_tb, color=_F6_VIOLETA, oscuro=_F6_VIOLETA_OSC))
    lm = _f6_nice_floor((W - L - R) / esc / 4.0)
    lpx = lm * esc
    p.append(
        f'<g><line x1="18" y1="292" x2="{18 + lpx:.1f}" y2="292" stroke="#334155" stroke-width="2.4"/>'
        f'<line x1="18" y1="287" x2="18" y2="297" stroke="#334155" stroke-width="2"/>'
        f'<line x1="{18 + lpx:.1f}" y1="287" x2="{18 + lpx:.1f}" y2="297" stroke="#334155" stroke-width="2"/>'
        f'<text x="{18 + lpx / 2:.1f}" y="284" text-anchor="middle" font-size="9.5" font-weight="900" fill="#334155">{_svg_t(_es_num(f"{lm:,.0f} m"))}</text></g>'
        '<g transform="translate(352,30)"><circle r="14" fill="#fff" stroke="#ddd6fe"/>'
        '<path d="M0,-9 L5,4 L0,1 L-5,4 Z" fill="#0b2447"/>'
        '<text y="11" text-anchor="middle" font-size="8" font-weight="900" fill="#0b2447">N</text></g>'
        "</svg>"
    )
    return "".join(p)


def _f6_vbars_svg(filas, unidad: str = "MUSD", escala: float = 1e6) -> str:
    """Barras verticales (admite negativos). filas=[(etiqueta, valor, color, tooltip)]."""
    vals = [float(v) / escala for _, v, _, _ in filas]
    if not vals:
        return ""
    lo, hi = min(0.0, min(vals)), max(0.0, max(vals))
    pad = (hi - lo) * 0.2 or 1.0
    lo_p, hi_p = lo - (pad if lo < 0 else 0.0), hi + pad
    # Lienzo algo más ancho: la card de fin de vida es más ancha que las de Ambiental.
    W, H, L, R, T, B = 520, 300, 60, 14, 18, 42
    p, sx, sy = _f6_frame(W, H, L, R, T, B, 0, len(filas), lo_p, hi_p, "", unidad, x_ticks=False)
    y0 = sy(0)
    p.append(f'<line x1="{L}" y1="{y0:.1f}" x2="{W - R}" y2="{y0:.1f}" stroke="#94a3b8" stroke-width="1.6"/>')
    w = (sx(1) - sx(0)) * 0.56
    for i, ((etq, _, col, tip), vv) in enumerate(zip(filas, vals)):
        xc = sx(i + 0.5)
        y1, y2 = sy(max(vv, 0.0)), sy(min(vv, 0.0))
        h = max(1.5, y2 - y1)
        yv = y1 - 7 if vv >= 0 else y2 + 15
        p.append(
            f'<g class="f6-bar"><title>{_svg_t(tip)}</title>'
            f'<rect x="{xc - w / 2:.1f}" y="{y1:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="{col}"/>'
            f'<rect x="{xc - w / 2:.1f}" y="{y1:.1f}" width="{w:.1f}" height="{min(9.0, h / 3):.1f}" rx="5" fill="#fff" opacity=".25"/>'
            f'<text x="{xc:.1f}" y="{yv:.1f}" text-anchor="middle" font-size="11.5" font-weight="900" fill="#0b2447">{_svg_t(_es_num(f"{vv:,.2f}"))}</text>'
            f'<text x="{xc:.1f}" y="{H - 12}" text-anchor="middle" font-size="11" font-weight="800" fill="#475569">{_svg_t(etq)}</text></g>'
        )
    p.append("</svg>")
    return "".join(p)


def _f6_esquema_optim(tipo: str) -> str:
    """Esquemas '¿Cómo funciona? / ¿Cómo se decide?' (tono violeta)."""
    if tipo == "optim":
        pasos = [("🧬", "Población de layouts"), ("🔀", "Mezclar y mutar"), ("🌪️", "Evaluar AEP con estelas"), ("🏆", "Quedarse con el mejor")]
        g = []
        for k, (ico, etq) in enumerate(pasos):
            x = 70 + k * 140
            if k:
                g.append(f'<path d="M{x - 104},60 L{x - 38},60" stroke="#c4b5fd" stroke-width="3" stroke-linecap="round" class="f6-flow" stroke-dasharray="7 6"/>'
                         f'<path d="M{x - 44},54 L{x - 36},60 L{x - 44},66" fill="none" stroke="{_F6_VIOLETA}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')
            g.append(f'<circle cx="{x}" cy="60" r="28" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="2"/>'
                     f'<text x="{x}" y="69" text-anchor="middle" font-size="23">{ico}</text>'
                     f'<text x="{x}" y="106" text-anchor="middle" font-size="10" font-weight="900" fill="#5b21b6">{etq}</text>')
        svg = (
            '<svg viewBox="0 0 560 160" xmlns="http://www.w3.org/2000/svg">' + "".join(g)
            + f'<path d="M490,118 Q280,168 70,118" fill="none" stroke="{_F6_VIOLETA}" stroke-width="2.4" stroke-dasharray="6 5" class="f6-flow"/>'
            f'<path d="M78,126 L68,118 L80,112" fill="none" stroke="{_F6_VIOLETA}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'
            '<text x="280" y="154" text-anchor="middle" font-size="10" font-weight="900" fill="#6d28d9">se repite en cada generación</text>'
            "</svg>"
        )
        titulo = "💡 ¿Cómo funciona?"
        txt = ("Differential Evolution prueba muchos layouts a la vez, los combina entre sí y se queda con los que "
               "producen más energía, respetando la separación mínima entre turbinas. El layout activo de la Fase 4 "
               "no se modifica: el resultado se puede guardar como escenario y compararlo allí.")
    else:
        ramas = [
            (32, "🏚️", "Desmantelar", "retirar el parque y vender la chatarra", "#64748b"),
            (82, "🔄", "Repotenciar", "turbinas nuevas: +30 % AEP, 25 años más", "#16a34a"),
            (132, "⏳", "Extender vida", "reforzar las actuales: +10 años, −5 % AEP", "#2563eb"),
        ]
        g = []
        for y, ico, etq, sub, col in ramas:
            g.append(f'<path d="M236,82 C272,82 272,{y} 306,{y}" fill="none" stroke="{col}" stroke-width="2.6" stroke-dasharray="6 5" class="f6-flow"/>'
                     f'<rect x="308" y="{y - 20}" width="244" height="40" rx="12" fill="#fff" stroke="{col}" stroke-opacity=".45" stroke-width="1.6"/>'
                     f'<text x="324" y="{y + 7}" font-size="18">{ico}</text>'
                     f'<text x="350" y="{y - 2}" font-size="11" font-weight="900" fill="{col}">{etq}</text>'
                     f'<text x="350" y="{y + 12}" font-size="9.5" font-weight="700" fill="#64748b">{sub}</text>')
        svg = (
            '<svg viewBox="0 0 560 160" xmlns="http://www.w3.org/2000/svg">'
            '<line x1="24" y1="82" x2="226" y2="82" stroke="#c4b5fd" stroke-width="8" stroke-linecap="round"/>'
            f'<line x1="24" y1="82" x2="226" y2="82" stroke="{_F6_VIOLETA}" stroke-width="3" stroke-dasharray="7 6" class="f6-flow"/>'
            + _f6_turbina_svg(70, 70, "", "Parque en operación", 1.0, color=_F6_VIOLETA, oscuro=_F6_VIOLETA_OSC)
            + '<text x="120" y="108" text-anchor="middle" font-size="10" font-weight="900" fill="#5b21b6">operación</text>'
            f'<circle cx="232" cy="82" r="9" fill="{_F6_VIOLETA}"/><circle cx="232" cy="82" r="3.5" fill="#fff"/>'
            '<text x="210" y="122" text-anchor="middle" font-size="10" font-weight="900" fill="#0b2447">fin de vida</text>'
            '<text x="210" y="135" text-anchor="middle" font-size="9" font-weight="700" fill="#64748b">(≈ 20-25 años)</text>'
            + "".join(g) + "</svg>"
        )
        titulo = "💡 ¿Cómo se decide?"
        txt = ("Al final de la vida útil se comparan tres caminos con el mismo criterio financiero: el VPN (valor "
               "presente de los flujos de caja, descontados con la tasa indicada). Se recomienda el que deja más valor.")
    return f'<div class="f6-how vio"><div class="f6-how-t">{titulo}</div>{svg}<p>{_escape(txt)}</p></div>'


def _render_card_optimizador() -> None:
    with st.container(border=True, key="f6_card_optim"):
        _section_header(
            "Optimizador de layout · Differential Evolution",
            "Mueve las turbinas buscando el mayor AEP con el motor de estelas de 16 sectores",
            "🧬",
        )
        df_layout = cargar_layout_parque()
        if df_layout is None or len(df_layout) == 0:
            st.markdown(_badge_html("Defina primero el arreglo de turbinas en Fase 4.", "info"), unsafe_allow_html=True)
            st.markdown(_f6_esquema_optim("optim"), unsafe_allow_html=True)
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
            maxiter = st.slider("Iteraciones", 1, 30,
                                int(_cfg_float(config, "f6_opt_maxiter", 5.0)), 1, key="f6_opt_maxiter_w",
                                help="Generaciones del algoritmo (maxiter).")
        with c2:
            popsize = st.slider("Población", 4, 20, 6, 1, key="f6_opt_popsize",
                                help="Layouts que se prueban por generación (popsize).")
        with c3:
            min_sp = st.slider("Separación mín. (D)", 2.0, 8.0, 3.0, 0.5, key="f6_opt_minsp",
                               help="Distancia mínima entre turbinas, en diámetros de rotor.")

        evals_est = popsize * 2 * n_turb * (maxiter + 1)
        st.markdown(
            _badge_html(
                _es_num(f"Cada evaluación corre el motor de estelas completo (5-15 s): ~{evals_est:,} evaluaciones, "
                        "puede tardar muchos minutos. Empiece con valores bajos y deje la ventana abierta."),
                "warn",
            ),
            unsafe_allow_html=True,
        )
        st.caption(_es_num(
            f"Área de búsqueda: x ∈ [{bounds_xy[0][0]:,.0f}, {bounds_xy[0][1]:,.0f}] m · "
            f"y ∈ [{bounds_xy[1][0]:,.0f}, {bounds_xy[1][1]:,.0f}] m · {n_turb} turbinas"
        ))

        if st.button("🧬 Optimizar layout", key="f6_opt_btn", type="primary", use_container_width=True):
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
                        status.write(_es_num(
                            f"AEP del layout actual: {aep_orig:,.0f} MWh/año · "
                            f"1 evaluación = {t_eval:.1f} s → estimado total ≈ {evals_est * t_eval / 60.0:,.0f} min"
                        ))

                        def _cb(it, aep_it):
                            status.write(_es_num(f"Generación {it}/{maxiter}: mejor AEP = {aep_it:,.0f} MWh/año"))

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
            st.markdown(_f6_esquema_optim("optim"), unsafe_allow_html=True)
            return
        if res.get("error"):
            st.error(res["error"])
            return

        aep_o, aep_n = res["aep_orig"], res["aep_opt"]
        delta_pct = (aep_n - aep_o) / aep_o * 100.0 if aep_o > 0 else 0.0
        st.markdown(
            _kpi_html([
                ("⚡", "AEP layout actual", f"{aep_o:,.0f} MWh/año", "motor de estelas 16 sectores", _F6_GRIS),
                ("🚀", "AEP optimizado", f"{aep_n:,.0f} MWh/año", f"{delta_pct:+.2f} % vs actual", _F6_VERDE),
                ("📈", "Mejora", f"{delta_pct:+.2f} %", f"{aep_n - aep_o:+,.0f} MWh/año", _F6_VIOLETA),
                ("🌀", "Turbinas", str(len(res["df_opt"])), "mismo número que Fase 4", _F6_AZUL),
            ], n=2),
            unsafe_allow_html=True,
        )
        st.markdown(
            _badge_html(
                _es_num(f"El layout optimizado produce {delta_pct:+.2f} % de energía") if delta_pct > 0.01
                else "El layout actual ya es muy bueno: la optimización no encontró una mejora apreciable",
                "ok" if delta_pct > 0.01 else "info",
            ),
            unsafe_allow_html=True,
        )
        hist = res.get("history") or {}
        if hist.get("iter"):
            st.markdown(
                _f6_fig_html("Convergencia · mejor AEP por generación", _f6_convergencia_svg(hist["iter"], hist["best_aep"])),
                unsafe_allow_html=True,
            )
        st.markdown(
            _f6_fig_html("Layout antes → después · pase el cursor por cada turbina",
                         _f6_layout_antes_despues_svg(res["df_orig"], res["df_opt"]),
                         [("Posición actual", _F6_GRIS), ("Posición optimizada", _F6_VIOLETA), ("Desplazamiento", "#a78bfa")]),
            unsafe_allow_html=True,
        )
        with st.expander("📋 Coordenadas del layout optimizado"):
            st.dataframe(res["df_opt"], hide_index=True, use_container_width=True)
        nombre_esc = st.text_input("Nombre del escenario", value="Layout optimizado (DE)", key="f6_opt_nombre")
        if st.button("💾 Guardar como escenario de Fase 4", key="f6_opt_guardar", use_container_width=True):
            from db import guardar_escenario_parque

            guardar_escenario_parque(
                str(nombre_esc).strip() or "Layout optimizado (DE)",
                res["df_opt"],
                {"origen": "f6_optimizador", "maxiter": int(_cfg_float(config, "f6_opt_maxiter", 5.0))},
                {"aep_optimizado_mwh": aep_n, "aep_original_mwh": aep_o, "delta_pct": delta_pct},
            )
            st.success("Escenario guardado — compárelo en Fase 4 (el layout activo NO se modifica).")
        with st.expander("💡 ¿Cómo funciona?"):
            st.markdown(_f6_esquema_optim("optim"), unsafe_allow_html=True)


def _render_card_repowering() -> None:
    import repowering_analysis as repo

    with st.container(border=True, key="f6_card_repower"):
        _section_header(
            "Fin de vida · repotenciación",
            "Desmantelar, repotenciar o extender la vida: cuál deja más valor (VPN)",
            "♻️",
        )
        c1, c2 = st.columns(2)
        with c1:
            cap_mw = st.number_input("Capacidad (MW)", 0.0, 5000.0,
                                     _cfg_float(config, "f5_potencia_instalada_mw", 0.0), 1.0, key="f6_rep_cap")
        with c2:
            aep = st.number_input("AEP actual (MWh/año)", 0.0, 10_000_000.0,
                                  _cfg_float(config, "f5_aep_neta_total_mwh", 0.0), 100.0, key="f6_rep_aep")
        c3, c4 = st.columns(2)
        with c3:
            tasa = st.number_input("Tasa de descuento (%)", 1.0, 25.0,
                                   _cfg_float(config, "f5_tasa_descuento_pct", 8.0), 0.5, key="f6_rep_tasa")
        with c4:
            ppa = st.number_input("Precio PPA (USD/MWh)", 10.0, 300.0,
                                  _cfg_float(config, "f5_precio_energia_mwh", 60.0), 1.0, key="f6_rep_ppa",
                                  help="Precio de venta de la energía en el contrato (PPA).")

        if cap_mw <= 0 or aep <= 0:
            st.markdown(_badge_html("Complete la Fase 5 (capacidad y AEP) o escriba los valores arriba.", "info"),
                        unsafe_allow_html=True)
            st.markdown(_f6_esquema_optim("repower"), unsafe_allow_html=True)
            return

        df_esc, recomendado = repo.comparar_escenarios_fin_vida(cap_mw, aep, tasa, ppa)
        etiquetas = {"decommission": "Desmantelar", "repowering": "Repotenciar", "life_extension": "Extender vida"}
        iconos = {"decommission": "🏚️", "repowering": "🔄", "life_extension": "⏳"}
        colores = {"decommission": _F6_GRIS, "repowering": _F6_AZUL, "life_extension": _F6_AZUL}
        st.markdown(
            _badge_html(f"Recomendado por VPN: {etiquetas.get(recomendado, recomendado).upper()}", "ok"),
            unsafe_allow_html=True,
        )

        def _musd(v) -> str:
            return _es_num(f"{float(v) / 1e6:,.2f}") + " MUSD"

        tiles, filas = [], []
        for _, r in df_esc.iterrows():
            e = r["Escenario"]
            etq = etiquetas.get(e, str(e))
            rec = e == recomendado
            vida = float(r.get("Vida adicional (años)", 0) or 0)
            tiles.append(
                f'<div class="f6-esc{" rec" if rec else ""}"><div class="f6-esc-i">{iconos.get(e, "•")}</div>'
                f"<b>{_escape(etq)}</b><span class=\"f6-esc-v\">{_escape(_musd(r['NPV (USD)']))}</span><small>VPN</small>"
                f"<i>CAPEX {_escape(_musd(r['CAPEX (USD)']))}"
                + (f" · +{_escape(_es_num(f'{vida:.0f}'))} años" if vida > 0 else "")
                + "</i></div>"
            )
            tip = _es_num(
                f"{etq}\nVPN: {float(r['NPV (USD)']) / 1e6:,.2f} MUSD\nCAPEX: {float(r['CAPEX (USD)']) / 1e6:,.2f} MUSD\n"
                f"AEP posterior: {float(r.get('AEP post (MWh/año)', 0) or 0):,.0f} MWh/año\n"
                f"Flujo de caja anual: {float(r.get('FCF anual (USD)', 0) or 0) / 1e6:,.2f} MUSD\nVida adicional: {vida:.0f} años"
            )
            filas.append((etq, float(r["NPV (USD)"]), _F6_VERDE if rec else colores.get(e, _F6_GRIS), tip))
        st.markdown(f'<div class="f6-escs">{"".join(tiles)}</div>', unsafe_allow_html=True)
        st.markdown(
            _f6_fig_html("VPN por escenario · MUSD", _f6_vbars_svg(filas),
                         [("Recomendado", _F6_VERDE), ("Otras opciones", _F6_AZUL), ("Desmantelar", _F6_GRIS)]),
            unsafe_allow_html=True,
        )

        df_show = df_esc.copy()
        df_show["Escenario"] = df_show["Escenario"].map(etiquetas).fillna(df_show["Escenario"])
        df_show = df_show.rename(columns={"NPV (USD)": "VPN (USD)", "FCF anual (USD)": "Flujo de caja anual (USD)"})
        with st.expander("📋 Tabla de escenarios"):
            st.dataframe(
                df_show,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "CAPEX (USD)": st.column_config.NumberColumn(format="%.0f"),
                    "AEP post (MWh/año)": st.column_config.NumberColumn(format="%.0f"),
                    "Flujo de caja anual (USD)": st.column_config.NumberColumn(format="%.0f"),
                    "VPN (USD)": st.column_config.NumberColumn(format="%.0f"),
                },
            )
        st.caption(
            "Supuestos por defecto: desmantelar 40k USD/MW (chatarra 15k), repotenciar 900k USD/MW con +30 % AEP "
            "y 25 años, extender vida 200k USD/MW con −5 % AEP y 10 años."
        )
        with st.expander("💡 ¿Cómo se decide?"):
            st.markdown(_f6_esquema_optim("repower"), unsafe_allow_html=True)


def _render_optimizacion() -> None:
    col_a, col_b = st.columns(2, gap="medium")
    with col_a:
        _render_card_optimizador()
    with col_b:
        _render_card_repowering()


# -----------------------------------------------------------------------------
# Auditoría · checklist previo estilo DNV (paridad mockup 06_fase6). Solo capa
# visual: el cálculo (pre_audit_checklist) no cambia; los textos se muestran en
# español con los mapas de abajo.
# -----------------------------------------------------------------------------
_F6_AUDIT_CAT_ES = {
    "Data Quality": "Calidad de datos", "Wake": "Estelas", "IEC 61400-1": "IEC 61400-1",
    "Económico": "Económico", "Ambiental": "Ambiental", "Social": "Social",
}
_F6_AUDIT_CAT_ICO = {
    "Data Quality": "🛰️", "Wake": "🌪️", "IEC 61400-1": "🛡️", "Económico": "💰", "Ambiental": "🌿", "Social": "🤝",
}
_F6_AUDIT_CRIT_ES = {
    "DQ01": "≥ 3 años de datos satelitales NASA POWER",
    "DQ02": "Torre meteorológica con ≥ 12 meses de solape",
    "DQ03": "MCP R² ≥ 0,85 (satélite ↔ torre)",
    "DQ04": "Recuperación de datos de la torre ≥ 90 %",
    "DQ05": "Temperatura T2M de NASA disponible (densidad real)",
    "WK01": "Modelo de estela de referencia (py_wake DTU o WAsP)",
    "WK02": "Comparación de ≥ 2 modelos de estela",
    "WK03": "Separación mínima entre turbinas ≥ 3D",
    "IEC01": "Idoneidad del sitio completa y conforme",
    "IEC02": "V_ref a 50 años calculada (Gumbel)",
    "IEC03": "TI a 15 m/s ≤ límite de la categoría",
    "EC01": "DSCR mínimo ≥ 1,3",
    "EC02": "WACC desglosado calculado",
    "EC03": "P90 bancario calculado (Monte Carlo)",
    "EC04": "TIR > WACC (proyecto viable)",
    "EN01": "Parpadeo de sombra < 30 h/año en todo receptor",
    "EN02": "Ruido ≤ 50 dB(A) diurno residencial",
    "EN03": "Riesgo de colisión de aves evaluado",
    "SO01": "Consulta previa Wayuu documentada (manual)",
    "SO02": "Mesa de diálogo activa con comunidades (manual)",
}
# Dónde se resuelve cada criterio dentro de la app
_F6_AUDIT_DONDE = {
    "DQ01": "Fase 2 · datos NASA", "DQ02": "Fase 2 · torre + MCP", "DQ03": "Fase 2 · torre + MCP",
    "DQ04": "Fase 2 · torre + MCP", "DQ05": "Fase 5 · densidad mensual",
    "WK01": "Fase 4/5 · modelo de estela", "WK02": "Fase 4/5 · modelo de estela", "WK03": "Fase 4 · separación",
    "IEC01": "Fase 5 · validación IEC", "IEC02": "F6 · Sitio y cumplimiento", "IEC03": "Fase 5 · validación IEC",
    "EC01": "Fase 5 · economía", "EC02": "Fase 5 · economía", "EC03": "Fase 5 · Monte Carlo", "EC04": "Fase 5 · economía",
    "EN01": "F6 · Ambiental (parpadeo)", "EN02": "F6 · Ambiental (ruido)", "EN03": "F6 · Ambiental (aves)",
    "SO01": "documentos del proyecto", "SO02": "documentos del proyecto",
}
_F6_AUDIT_ESTADO = {"PASS": ("ok", "Cumple"), "FAIL": ("bad", "Falla"), "N/A": ("info", "Sin dato"), "MANUAL": ("warn", "Manual")}
_F6_AUDIT_CAT_COL = ["#0d9488", "#14b8a6", "#2563eb", "#d97706", "#16a34a", "#7c3aed"]


def _f6_audit_evidencia(ev) -> str:
    """'valor=0.2 no cumple >= 3' → 'valor 0,2 · no cumple ≥ 3' (solo presentación)."""
    s = str(ev or "").replace("True", "sí").replace("False", "no")
    ops = {">=": "≥", "<=": "≤", "==": "=", ">": ">", "<": "<"}
    s = re.sub(r"valor=(\S+) no cumple (>=|<=|==|>|<) (\S+)",
               lambda m: f"valor {m.group(1)} · no cumple {ops[m.group(2)]} {m.group(3)}", s)
    s = re.sub(r"valor=(\S+)", r"valor \1", s)
    return _es_num(s)


def _f6_gauge_svg(score: float, etiqueta: str) -> str:
    """Medidor semicircular 0-100 con zonas (roja < 70, ámbar 70-85, verde ≥ 85) y aguja."""
    cx, cy, r, sw = 150.0, 150.0, 108.0, 22.0
    v = min(100.0, max(0.0, float(score)))
    col = _F6_VERDE if v >= 85 else (_F6_AMBAR if v >= 70 else _F6_ROJO)

    def pt(val, rr):
        a = np.pi * (1.0 - val / 100.0)
        return cx + rr * np.cos(a), cy - rr * np.sin(a)

    def arco(v0, v1, color, ancho, op=1.0):
        (x0, y0), (x1, y1) = pt(v0, r), pt(v1, r)
        return (f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" stroke="{color}" '
                f'stroke-width="{ancho}" stroke-linecap="butt" opacity="{op}"/>')

    p = ['<svg viewBox="0 0 300 222" xmlns="http://www.w3.org/2000/svg">',
         arco(0, 70, "#fecaca", sw), arco(70, 85, "#fde68a", sw), arco(85, 100, "#bbf7d0", sw)]
    if v > 0.2:
        p.append(arco(0, v, col, sw * 0.62))
    for t in (0, 70, 85, 100):
        x, y = pt(t, r + 22)
        p.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-size="10.5" font-weight="900" fill="#64748b">{t}</text>')
    # Aguja corta y textos DEBAJO del eje: así la aguja nunca tapa el número.
    nx, ny = pt(v, r - 34)
    p.append(
        f'<g><title>{_svg_t(_es_num(f"Puntaje {v:.1f} de 100"))}</title>'
        f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="#0b2447" stroke-width="4" stroke-linecap="round"/>'
        f'<circle cx="{cx}" cy="{cy}" r="9" fill="#0b2447"/><circle cx="{cx}" cy="{cy}" r="3.5" fill="#fff"/></g>'
        f'<text x="{cx}" y="{cy + 42}" text-anchor="middle" font-size="28" font-weight="900" fill="{col}">'
        f'{_svg_t(_es_num(f"{v:.1f}"))}<tspan font-size="11" font-weight="800" fill="#64748b"> / 100</tspan></text>'
        f'<text x="{cx}" y="{cy + 64}" text-anchor="middle" font-size="12" font-weight="900" fill="{col}">{_svg_t(etiqueta)}</text>'
        "</svg>"
    )
    return "".join(p)


def _f6_cat_bars_svg(filas) -> str:
    """Puntaje por categoría: pista = peso máximo, relleno = puntos obtenidos.
    filas=[(etiqueta, obtenido, peso, tooltip)]."""
    n = max(1, len(filas))
    fila_h, top = 40.0, 8.0
    W, H = 520.0, top + n * fila_h + 6
    x0, x1 = 132.0, W - 92.0
    pmax = max([float(pe) for _, _, pe, _ in filas] + [1.0])
    p = [f'<svg viewBox="0 0 {W:.0f} {H:.0f}" xmlns="http://www.w3.org/2000/svg">']
    for i, (etq, obt, peso, tip) in enumerate(filas):
        yc = top + i * fila_h + fila_h / 2
        wt = float(peso) / pmax * (x1 - x0)
        wo = max(0.0, float(obt)) / pmax * (x1 - x0)
        pct = (float(obt) / float(peso) * 100.0) if peso else 0.0
        col = _F6_VERDE if pct >= 85 else ("#0d9488" if pct >= 50 else (_F6_AMBAR if pct >= 30 else _F6_ROJO))
        p.append(
            f'<g class="f6-bar"><title>{_svg_t(tip)}</title>'
            f'<text x="{x0 - 10:.0f}" y="{yc + 4:.1f}" text-anchor="end" font-size="12" font-weight="800" fill="#475569">{_svg_t(etq)}</text>'
            f'<rect x="{x0}" y="{yc - 11:.1f}" width="{wt:.1f}" height="22" rx="9" fill="#f0fdfa" stroke="#99f6e4"/>'
            f'<rect x="{x0}" y="{yc - 11:.1f}" width="{max(wo, 3.0):.1f}" height="22" rx="9" fill="{col}"/>'
            f'<rect x="{x0}" y="{yc - 11:.1f}" width="{max(wo, 3.0):.1f}" height="7" rx="4" fill="#fff" opacity=".25"/>'
            f'<text x="{x0 + wt + 8:.1f}" y="{yc + 4:.1f}" font-size="11.5" font-weight="900" fill="#0b2447">'
            f'{_svg_t(_es_num(f"{float(obt):.1f}"))}<tspan fill="#94a3b8" font-weight="700"> / {int(peso)}</tspan></text></g>'
        )
    p.append("</svg>")
    return "".join(p)


def _f6_esquema_audit() -> str:
    """¿Cómo se calcula el puntaje? Pesos por categoría + reglas + umbrales."""
    x, segs = 40.0, []
    ancho = 480.0
    for k, (cat, peso) in enumerate(_F6_AUDIT_PESOS_ORDEN()):
        w = peso / 100.0 * ancho
        col = _F6_AUDIT_CAT_COL[k % len(_F6_AUDIT_CAT_COL)]
        segs.append(
            f'<rect x="{x + 1:.1f}" y="30" width="{w - 2:.1f}" height="26" rx="7" fill="{col}"/>'
            f'<text x="{x + w / 2:.1f}" y="47" text-anchor="middle" font-size="11" font-weight="900" fill="#fff">{peso}</text>'
            f'<text x="{x + w / 2:.1f}" y="72" text-anchor="middle" font-size="9.5" font-weight="800" fill="#475569">{_svg_t(_F6_AUDIT_CAT_ES.get(cat, cat))}</text>'
        )
        x += w
    umbral = (
        '<rect x="40" y="128" width="336" height="14" rx="7" fill="#fecaca"/>'
        '<rect x="376" y="128" width="72" height="14" fill="#fde68a"/>'
        '<rect x="448" y="128" width="72" height="14" rx="7" fill="#bbf7d0"/>'
        '<text x="208" y="158" text-anchor="middle" font-size="9.5" font-weight="900" fill="#b91c1c">0-70 · aún no listo</text>'
        '<text x="412" y="158" text-anchor="middle" font-size="9.5" font-weight="900" fill="#b45309">70-85 · brechas</text>'
        '<text x="484" y="158" text-anchor="middle" font-size="9.5" font-weight="900" fill="#15803d">≥ 85 · listo</text>'
    )
    reglas = (
        '<g font-size="10" font-weight="900">'
        '<rect x="40" y="86" width="150" height="24" rx="12" fill="#f0fdf4" stroke="#bbf7d0"/><text x="115" y="102" text-anchor="middle" fill="#15803d">✅ Cumple = 1 punto</text>'
        '<rect x="205" y="86" width="165" height="24" rx="12" fill="#f8fafc" stroke="#cbd5e1"/><text x="287" y="102" text-anchor="middle" fill="#475569">➖ Sin dato / manual = ½</text>'
        '<rect x="385" y="86" width="135" height="24" rx="12" fill="#fef2f2" stroke="#fecaca"/><text x="452" y="102" text-anchor="middle" fill="#b91c1c">❌ Falla = 0</text>'
        "</g>"
    )
    svg = (
        '<svg viewBox="0 0 560 168" xmlns="http://www.w3.org/2000/svg">'
        '<text x="40" y="20" font-size="11.5" font-weight="900" fill="#0b2447">100 puntos repartidos por categoría</text>'
        + "".join(segs) + reglas + umbral + "</svg>"
    )
    txt = ("Cada categoría reparte sus puntos entre sus criterios: un criterio que cumple suma completo, uno sin dato "
           "o de verificación manual suma la mitad y uno que falla no suma. El total (0-100) indica si el análisis "
           "ya puede enviarse a un auditor externo (DNV, UL, TÜV). No sustituye una certificación real.")
    return f'<div class="f6-how"><div class="f6-how-t">💡 ¿Cómo se calcula el puntaje?</div>{svg}<p>{_escape(txt)}</p></div>'


def _F6_AUDIT_PESOS_ORDEN():
    import pre_audit_checklist as audit

    return list(audit.PESO_CATEGORIA.items())


def _render_auditoria() -> None:
    import pre_audit_checklist as audit

    with st.container(border=True, key="f6_card_audit"):
        _section_header(
            "Checklist previo a auditoría · estilo DNV",
            "¿Está el análisis listo para un auditor externo? Puntaje de 0 a 100 · ≥ 85 = listo",
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
        score = float(score_res.get("score", 0.0))
        st.session_state["f6_audit_score_pct"] = score  # lo muestra el hero en el siguiente render

        nivel = score_res.get("readiness_level", "")
        _nivel_es = {"READY FOR AUDITOR": "LISTO PARA AUDITOR", "MINOR GAPS": "BRECHAS MENORES", "NOT READY": "AÚN NO LISTO"}
        etq_nivel = _nivel_es.get(nivel, nivel)
        cat_scores = score_res.get("scores_por_categoria") or {}
        pct_cat = {c: (float(v) / audit.PESO_CATEGORIA[c] * 100.0 if audit.PESO_CATEGORIA.get(c) else 0.0)
                   for c, v in cat_scores.items()}
        peor_cat = min(pct_cat, key=pct_cat.get) if pct_cat else ""

        col_g, col_k = st.columns([1, 1.55], gap="medium")
        with col_g:
            st.markdown(
                _f6_fig_html("Puntaje de auditoría", _f6_gauge_svg(score, etq_nivel),
                             [("Aún no listo", "#fecaca"), ("Brechas", "#fde68a"), ("Listo", "#bbf7d0")]),
                unsafe_allow_html=True,
            )
        with col_k:
            st.markdown(
                _kpi_html([
                    ("✅", "Criterios que cumplen", f"{score_res['n_pass']} de {score_res['n_total']}", "suman el punto completo", _F6_VERDE),
                    ("❌", "Criterios que fallan", str(score_res["n_fail"]), "cerrar antes de enviar al auditor", _F6_ROJO),
                    ("✍️", "Sin dato / manual", str(score_res["n_na_manual"]), "cuentan medio punto", _F6_GRIS),
                    ("📉", "Categoría más débil", _F6_AUDIT_CAT_ES.get(peor_cat, peor_cat) or "—",
                     _es_num(f"{pct_cat.get(peor_cat, 0.0):.0f} % de su peso") if peor_cat else "", _F6_AMBAR),
                ], n=2),
                unsafe_allow_html=True,
            )
            s_txt = _es_num(f"{score:.1f}")
            if score >= 85:
                msg, tono = f"Puntaje {s_txt}: el proyecto está listo para un auditor externo (DNV/UL/TÜV).", "ok"
            elif score >= 70:
                msg, tono = f"Puntaje {s_txt}: brechas menores, refine antes de enviar al auditor.", "warn"
            else:
                msg, tono = f"Puntaje {s_txt}: aún no enviar al auditor, cierre los {score_res['n_fail']} criterios que fallan.", "bad"
            st.markdown(_badge_html(msg, tono), unsafe_allow_html=True)

        col_c, col_d = st.columns([1.6, 1], gap="medium")
        with col_c:
            filas = []
            for cat, peso in audit.PESO_CATEGORIA.items():
                obt = float(cat_scores.get(cat, 0.0))
                sub = df_audit[df_audit["categoria"] == cat]
                tip = _es_num(
                    f"{_F6_AUDIT_CAT_ES.get(cat, cat)}: {obt:.1f} de {peso} puntos ({pct_cat.get(cat, 0.0):.0f} %)\n"
                    f"{int((sub['status'] == 'PASS').sum())} cumplen · {int((sub['status'] == 'FAIL').sum())} fallan · "
                    f"{int(sub['status'].isin(['N/A', 'MANUAL']).sum())} sin dato"
                )
                filas.append((f"{_F6_AUDIT_CAT_ICO.get(cat, '')} {_F6_AUDIT_CAT_ES.get(cat, cat)}", obt, peso, tip))
            st.markdown(
                _f6_fig_html("Puntaje por categoría · obtenido / máximo", _f6_cat_bars_svg(filas),
                             [("≥ 85 %", _F6_VERDE), ("50-85 %", "#0d9488"), ("30-50 %", _F6_AMBAR), ("< 30 %", _F6_ROJO)]),
                unsafe_allow_html=True,
            )
        with col_d:
            segs = [("Cumplen", score_res["n_pass"], _F6_VERDE), ("Fallan", score_res["n_fail"], _F6_ROJO),
                    ("Sin dato / manual", score_res["n_na_manual"], _F6_GRIS)]
            st.markdown(
                _f6_fig_html("Resultado de criterios",
                             _f6_donut_svg(segs, str(score_res["n_total"]), "criterios"),
                             [(e, c) for e, _, c in segs]),
                unsafe_allow_html=True,
            )

        fallan = df_audit[df_audit["status"] == "FAIL"]
        if len(fallan):
            acc = "".join(
                f'<div class="f6-acc"><span class="f6-acc-x">❌</span><div><b>{_escape(r["id"])} · '
                f'{_escape(_F6_AUDIT_CRIT_ES.get(r["id"], r["criterio"]))}</b>'
                f'<small>{_escape(_f6_audit_evidencia(r["evidencia"]))}</small></div>'
                f'<span class="f6-pill info f6-acc-d">🔧 {_escape(_F6_AUDIT_DONDE.get(r["id"], "revisar evidencia"))}</span></div>'
                for _, r in fallan.iterrows()
            )
            st.markdown(f'<div class="f6-gtitle" style="margin-top:12px">🔧 Qué falta para estar listo</div>{acc}',
                        unsafe_allow_html=True)
        else:
            st.markdown(_badge_html("Ningún criterio falla: solo quedan ítems sin dato o de verificación manual.", "ok"),
                        unsafe_allow_html=True)

        st.markdown('<div class="f6-gtitle" style="margin-top:14px">📋 Checklist completo</div>', unsafe_allow_html=True)
        filtro = st.segmented_control(
            "Mostrar", ["Todos", "❌ Fallan", "✅ Cumplen", "➖ Sin dato / manual"],
            default="Todos", key="f6_audit_filtro", label_visibility="collapsed",
        ) or "Todos"
        estados = {"Todos": None, "❌ Fallan": {"FAIL"}, "✅ Cumplen": {"PASS"}, "➖ Sin dato / manual": {"N/A", "MANUAL"}}[filtro]
        filas_html = []
        for cat, peso in audit.PESO_CATEGORIA.items():
            sub = df_audit[df_audit["categoria"] == cat]
            if estados is not None:
                sub = sub[sub["status"].isin(estados)]
            if not len(sub):
                continue
            filas_html.append(
                f'<tr class="f6-tcat"><td colspan="4">{_F6_AUDIT_CAT_ICO.get(cat, "")} {_escape(_F6_AUDIT_CAT_ES.get(cat, cat))}'
                f' · {_escape(_es_num(f"{float(cat_scores.get(cat, 0.0)):.1f}"))} de {peso} puntos</td></tr>'
            )
            for _, r in sub.iterrows():
                tono_p, txt_p = _F6_AUDIT_ESTADO.get(r["status"], ("info", str(r["status"])))
                filas_html.append(
                    f'<tr><td class="id">{_escape(r["id"])}</td>'
                    f'<td>{_escape(_F6_AUDIT_CRIT_ES.get(r["id"], r["criterio"]))}</td>'
                    f'<td><span class="f6-pill {tono_p}">{txt_p}</span></td>'
                    f'<td>{_escape(_f6_audit_evidencia(r["evidencia"]))}</td></tr>'
                )
        if filas_html:
            st.markdown(
                '<table class="f6-tbl f6-audit-tbl"><thead><tr><th>ID</th><th>Criterio</th><th>Estado</th>'
                f'<th>Evidencia</th></tr></thead><tbody>{"".join(filas_html)}</tbody></table>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("No hay criterios con ese estado.")

        df_show = df_audit.rename(columns={
            "id": "ID", "categoria": "Categoría", "criterio": "Criterio",
            "status": "Estado", "evidencia": "Evidencia",
        })
        df_show["Categoría"] = df_show["Categoría"].map(_F6_AUDIT_CAT_ES).fillna(df_show["Categoría"])
        df_show["Criterio"] = df_show["ID"].map(_F6_AUDIT_CRIT_ES).fillna(df_show["Criterio"])
        df_show["Evidencia"] = df_show["Evidencia"].map(_f6_audit_evidencia)
        df_show["Estado"] = df_show["Estado"].map(
            {"PASS": "✅ Cumple", "FAIL": "❌ Falla", "N/A": "➖ Sin dato", "MANUAL": "✍️ Manual"}
        ).fillna(df_show["Estado"])
        with st.expander("📑 Tabla ordenable (copiar / exportar)"):
            st.dataframe(df_show, hide_index=True, use_container_width=True)
        with st.expander("💡 ¿Cómo se calcula el puntaje?"):
            st.markdown(_f6_esquema_audit(), unsafe_allow_html=True)
        st.caption(
            "Los estudios de esta fase alimentan el checklist: ruido → EN02, parpadeo de sombra → EN01, "
            "aves → EN03, IEC (validación de Fase 5) → IEC01/IEC03. Los ítems sociales son de verificación manual."
        )


_F6_DIVISORES = {
    "Sitio y cumplimiento": ("🗺️", "Idoneidad IEC · terreno · clima frío", "#0d9488"),
    "Ambiental": ("🌿", "Receptores · ruido · flicker · avifauna · huella CO₂", "#16a34a"),
    "Operación y red": ("⚡", "SCADA real · curtailment · planta híbrida", "#d97706"),
    "Optimización y fin de vida": ("🎯", "Layout óptimo · repotenciación", "#7c3aed"),
    "Auditoría": ("📋", "Checklist previo a auditoría · estilo DNV", "#0b66c2"),
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
