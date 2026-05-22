import textwrap
import base64
import unicodedata

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pandas.util import hash_pandas_object
from navigation import render_dropdown_visibility_fix, render_sidebar_navigation, _icon_svg
import streamlit.components.v1 as components
import calculos_energia as energia_calc

from db import (
    init_db,
    cargar_config,
    guardar_config_values,
    cargar_nasa_hourly,
    cargar_tabla_curva,
    cargar_layout_parque,
    guardar_layout_parque,
    guardar_escenario_parque,
    listar_escenarios_parque,
    cargar_escenario_parque,
    eliminar_escenario_parque,
)
from widget_helpers import _init_widget_state, _safe_index
from calculos import (
    generar_layout_parque,
    crear_figura_layout_parque,
    analizar_estelas_parque_16,
    crear_figura_direccion_estela,
    calcular_estelas_jensen_direccion,
    SECTOR_LABELS_16,
    SECTOR_CENTERS_16,
    construir_serie_viento_analisis,
    normalizar_modelo_altura,
    PROMEDIO_LOG_EXP_LABEL,
)

st.set_page_config(page_title="Fase 4 · Estelas y arreglo", layout="wide")

# Cargar CSS global e inyectar sidebar lo ANTES posible para evitar FOUC.
render_sidebar_navigation("pages/4_Fase_4_Estelas_y_arreglo.py")

init_db()
config = cargar_config()

PLOTLY_PERF_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}

PLOTLY_INTERACTIVE_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

ROUGHNESS_OPTIONS = {
    "Water / Mar": 2e-4,
    "Snow / Nieve": 1e-3,
    "Grass / Césped": 0.03,
    "Farmland / Cultivo": 0.10,
    "Forest / Bosque": 0.80,
    "City / Ciudad": 1.00,
}


def _normalize_col_name(name: str) -> str:
    text = str(name)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def _find_geom_loss_column(df: pd.DataFrame | None) -> str | None:
    if df is None or df.empty:
        return None

    candidates = {
        "perdida geometrica (%)",
        "pérdida geométrica (%)",
        "perdida geometrica",
        "pérdida geométrica",
        "perdida geom (%)",
        "perdida geometrica sector (%)",
    }

    normalized_map = {_normalize_col_name(col): col for col in df.columns}

    for candidate in candidates:
        key = _normalize_col_name(candidate)
        if key in normalized_map:
            return normalized_map[key]

    for norm_col, original_col in normalized_map.items():
        if "perdida" in norm_col and "geometr" in norm_col:
            return original_col

    return None


def _df_signature(df: pd.DataFrame | None, cols: list[str] | None = None) -> tuple:
    if df is None or len(df) == 0:
        return (0, ())
    subset = df[[col for col in (cols or df.columns) if col in df.columns]].copy()
    try:
        digest = int(hash_pandas_object(subset, index=True).sum())
    except Exception:
        digest = hash(tuple(subset.astype(str).head(50).to_numpy().ravel()))
    return (len(df), tuple(subset.columns), digest)


def _session_cached_result(state_key: str, signature: tuple, builder):
    cached = st.session_state.get(state_key)
    if isinstance(cached, dict) and cached.get("signature") == signature:
        return cached["value"]
    value = builder()
    st.session_state[state_key] = {"signature": signature, "value": value}
    return value


def _get_direction_center_value(row: pd.Series) -> float:
    for col, value in row.items():
        norm_col = _normalize_col_name(col)
        if "direccion" in norm_col and "centro" in norm_col:
            return float(value)
    raise KeyError("Dirección centro (°)")


def _render_phase4_css():
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%) !important;
        }

                                                                                                                                                                .sidebar-project-card,
        .sidebar-user-card {
            margin: 0.85rem 0.5rem 0 0.5rem;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid rgba(203, 213, 225, 0.9);
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
        }

        .sidebar-project-card {
            padding: 0.95rem 0.9rem;
        }

        .sidebar-project-card__row {
            display: flex;
            gap: 0.8rem;
            align-items: flex-start;
        }

        .sidebar-project-card__icon {
            width: 38px;
            height: 38px;
            border-radius: 12px;
            background: #eff6ff;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .sidebar-project-card__eyebrow {
            color: #64748b;
            font-size: 0.78rem;
            font-weight: 700;
            margin-bottom: 0.15rem;
        }

        .sidebar-project-card__title {
            color: #10224f;
            font-size: 1rem;
            font-weight: 800;
            line-height: 1.2;
            margin-bottom: 0.25rem;
        }

        .sidebar-project-card__meta {
            color: #64748b;
            font-size: 0.77rem;
            line-height: 1.35;
        }

        .sidebar-project-card__config {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-top: 0.9rem;
            padding-top: 0.75rem;
            border-top: 1px solid rgba(203, 213, 225, 0.55);
            color: #334155;
            font-size: 0.88rem;
            font-weight: 700;
        }

        .sidebar-user-card {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.85rem 0.9rem;
        }

        .sidebar-user-card__avatar {
            width: 36px;
            height: 36px;
            border-radius: 999px;
            background: #1e40af;
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.86rem;
            font-weight: 800;
            flex-shrink: 0;
        }

        .sidebar-user-card__name {
            color: #0f172a;
            font-size: 0.9rem;
            font-weight: 800;
        }

        .sidebar-user-card__mail {
            color: #64748b;
            font-size: 0.8rem;
            font-weight: 500;
        }

        .hero-card {
            position: relative !important;
            overflow: hidden !important;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%) !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 20px !important;
            padding: 1.45rem 1.55rem 1.35rem 1.55rem !important;
            margin-bottom: 1rem !important;
            box-shadow: 0 1px 4px rgba(15, 23, 42, 0.045) !important;
            min-height: unset !important;
            height: auto !important;
        }
        .hero-card::after {
            content: "" !important;
            position: absolute !important;
            right: -10px !important;
            top: -8px !important;
            width: 260px !important;
            height: 140px !important;
            background:
              radial-gradient(circle at 78% 25%, rgba(147, 197, 253, 0.28) 0 18px, transparent 19px),
              radial-gradient(circle at 56% 18%, rgba(191, 219, 254, 0.30) 0 26px, transparent 27px) !important;
            opacity: 0.9 !important;
            pointer-events: none !important;
        }
        .fase-hero-title {
            font-size: 2.1rem !important;
            line-height: 1.05 !important;
            font-weight: 800 !important;
            color: #1e3a8a !important;
            margin: 0 0 0.28rem 0 !important;
            position: relative !important;
            z-index: 2 !important;
        }
        .fase-hero-subtitle {
            margin: 0 !important;
            color: #64748b !important;
            font-size: 0.94rem !important;
            font-weight: 700 !important;
            line-height: 1.42 !important;
            max-width: 74rem !important;
            position: relative !important;
            z-index: 2 !important;
        }
        .sma-phase-title-shell {
            width: 100% !important;
            box-sizing: border-box !important;
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 30px !important;
            padding: 0.45rem 0.72rem 0.72rem 0.72rem !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
            margin: -1.45rem 0 1rem 0 !important;
            overflow: hidden !important;
        }
        .sma-phase-title-inner {
            position: relative !important;
            overflow: hidden !important;
            box-sizing: border-box !important;
            min-height: unset !important;
            background: transparent !important;
            border: none !important;
            border-radius: 20px !important;
            padding: 1.45rem 1.55rem 1.35rem 1.55rem !important;
            display: flex !important;
            align-items: center !important;
            box-shadow: none !important;
        }
        .sma-phase-title-inner::after {
            content: "";
            position: absolute;
            right: -10px;
            top: -8px;
            width: 260px;
            height: 140px;
            background:
                radial-gradient(circle at 78% 25%, rgba(147, 197, 253, 0.28) 0 18px, transparent 19px),
                radial-gradient(circle at 56% 18%, rgba(191, 219, 254, 0.30) 0 26px, transparent 27px);
            opacity: 0.9;
            pointer-events: none;
        }
        .sma-phase-title-content {
            position: relative !important;
            z-index: 2 !important;
        }
        .sma-phase-title-content h1 {
            margin: 0 0 0.28rem 0 !important;
            color: #1e3a8a !important;
            font-size: 2.1rem !important;
            line-height: 1.05 !important;
            font-weight: 800 !important;
            letter-spacing: 0 !important;
        }
        .sma-phase-title-content p {
            margin: 0 !important;
            max-width: 74rem !important;
            color: #64748b !important;
            font-size: 0.94rem !important;
            line-height: 1.42 !important;
            font-weight: 700 !important;
        }

        .f4-info-banner {
            display: flex !important;
            align-items: center !important;
            gap: 0.75rem !important;
            padding: 0.58rem 0.78rem !important;
            border: 1px solid #c8dcfb !important;
            border-radius: 12px !important;
            background: #ecf4ff !important;
            color: #1f4ea8 !important;
            font-weight: 700 !important;
            margin-bottom: 0.85rem !important;
        }

        .f4-info-banner__icon {
            width: 1.35rem !important;
            height: 1.35rem !important;
            border-radius: 999px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: #2563eb !important;
            color: #ffffff !important;
            font-weight: 900 !important;
            font-size: 0.72rem !important;
        }

        .f4-section-title {
            display: flex !important;
            align-items: center !important;
            gap: 0.75rem !important;
            margin-bottom: 0.95rem !important;
        }

        .f4-section-title__icon {
            width: 2rem !important;
            height: 2rem !important;
            border-radius: 999px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: rgba(37, 99, 235, 0.12) !important;
            color: #2563eb !important;
            font-size: 1rem !important;
            font-weight: 800 !important;
        }

        .f4-section-title__text {
            color: #17326b !important;
            font-size: 1.12rem !important;
            font-weight: 820 !important;
        }

        .f4-card-top-actions {
            margin-top: 0.9rem !important;
        }

        .f4-card-top-actions .stButton > button {
            min-height: 3rem !important;
        }

        .st-key-f4_card_move_layout label,
        .st-key-f4_card_wind_base label {
            color: #334155 !important;
            font-weight: 700 !important;
        }

        .st-key-f4_card_move_layout [data-testid="stNumberInput"] input,
        .st-key-f4_card_move_layout [data-testid="stSelectbox"] div[data-baseweb="select"],
        .st-key-f4_card_wind_base [data-testid="stNumberInput"] input,
        .st-key-f4_card_wind_base [data-testid="stSelectbox"] div[data-baseweb="select"] {
            background: #ffffff !important;
            border-color: #d8e3f0 !important;
            border-radius: 14px !important;
        }

        .st-key-f4_card_config {
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 20px !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.035) !important;
        }

        .st-key-f4_card_config div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 1.12rem 1.35rem 1.35rem 1.35rem !important;
        }

        .st-key-f4_card_config .f4-section-title {
            display: flex !important;
            align-items: center !important;
            gap: 0.75rem !important;
            margin-bottom: 1.15rem !important;
        }

        .st-key-f4_card_config .f4-section-title__icon {
            width: 2.75rem !important;
            height: 2.75rem !important;
            min-width: 2.75rem !important;
            border-radius: 999px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: linear-gradient(180deg, #f0f9ff 0%, #e0f2fe 100%) !important;
            color: #0369a1 !important;
            font-size: 1.35rem !important;
            font-weight: 800 !important;
            border: 1px solid #bae6fd !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.95) !important;
        }

        .st-key-f4_card_config .f4-section-title__icon svg {
            width: 1.45rem !important;
            height: 1.45rem !important;
            display: block !important;
        }

        .st-key-f4_card_config .f4-section-title__text {
            color: #0f172a !important;
            font-size: 1.28rem !important;
            font-weight: 800 !important;
        }

        /* ── Negrilla global en todo el bloque ── */
        .st-key-f4_card_config label,
        .st-key-f4_card_config [data-testid="stWidgetLabel"],
        .st-key-f4_card_config [data-testid="stWidgetLabel"] p,
        .st-key-f4_card_config [data-testid="stWidgetLabel"] span {
            color: #1e293b !important;
            font-weight: 800 !important;
            font-size: 0.92rem !important;
        }

        /* ── Inputs y selects: contenedor baseweb real ── */
        .st-key-f4_card_config [data-baseweb="input"],
        .st-key-f4_card_config [data-testid="stNumberInput"] [data-baseweb="input"],
        .st-key-f4_card_wind_base [data-baseweb="input"],
        .st-key-f4_card_detail_direction [data-baseweb="input"],
        .st-key-f4_card_wind_base [data-testid="stNumberInput"] [data-baseweb="input"],
        .st-key-f4_card_detail_direction [data-testid="stNumberInput"] [data-baseweb="input"] {
            background: #ffffff !important;
            border: 1px solid #bfdbfe !important;
            border-radius: 14px !important;
            min-height: 46px !important;
            display: flex !important;
            align-items: center !important;
            overflow: hidden !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.98), 0 1px 2px rgba(15, 23, 42, 0.02) !important;
        }

        .st-key-f4_card_config [data-baseweb="input"] > div,
        .st-key-f4_card_config [data-baseweb="input"] input,
        .st-key-f4_card_wind_base [data-baseweb="input"],
        .st-key-f4_card_detail_direction [data-baseweb="input"] > div,
        .st-key-f4_card_wind_base [data-baseweb="input"],
        .st-key-f4_card_detail_direction [data-baseweb="input"] input {
            background: #ffffff !important;
            color: #0f172a !important;
        }

        /* ── Divisor y contenedor de stepper para todo Fase 4 ── */
        [data-testid="stNumberInput"] [data-baseweb="input"] > div:last-child {
            background: #ffffff !important;
            border-left: 1px solid #dbeafe !important;
        }

        /* ── Valor numérico en negrilla para todo Fase 4 ── */
        [data-testid="stNumberInput"] input {
            background: #ffffff !important;
            padding-left: 1rem !important;
            font-weight: 800 !important;
            color: #0f172a !important;
        }

        /* ── Botones + y - sobre fondo blanco ── */
        [data-testid="stNumberInput"] button,
        [data-testid="stNumberInput"] [data-baseweb="input"] button {
            background: #ffffff !important;
            color: #0f172a !important;
            border-radius: 10px !important;
            border: 1px solid #eef2f7 !important;
            min-width: 2.35rem !important;
            font-weight: 800 !important;
            font-size: 1.05rem !important;
        }

        /* ── Hover real de los botones + y - ── */
        [data-testid="stNumberInput"] button:hover,
        [data-testid="stNumberInput"] [data-baseweb="input"] button:hover {
            background: #eff6ff !important;
            color: #1d4ed8 !important;
        }

        /* ── Selectbox: contenedor y valor seleccionado ── */
        .st-key-f4_card_config [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        .st-key-f4_card_wind_base [data-testid="stSelectbox"] [data-baseweb="select"] > div,
        .st-key-f4_card_detail_direction [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            min-height: 46px !important;
            background: #ffffff !important;
            border: 1px solid #bfdbfe !important;
            border-radius: 14px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.98), 0 1px 2px rgba(15, 23, 42, 0.02) !important;
            align-items: center !important;
        }
        .st-key-f4_card_config [data-testid="stSelectbox"] [data-baseweb="select"] span,
        .st-key-f4_card_config [data-testid="stSelectbox"] [data-baseweb="select"] div,
        .st-key-f4_card_wind_base [data-testid="stSelectbox"] [data-baseweb="select"] span,
        .st-key-f4_card_detail_direction [data-testid="stSelectbox"] [data-baseweb="select"] span,
        .st-key-f4_card_wind_base [data-testid="stSelectbox"] [data-baseweb="select"] div,
        .st-key-f4_card_detail_direction [data-testid="stSelectbox"] [data-baseweb="select"] div {
            font-weight: 700 !important;
            color: #0f172a !important;
            background: #ffffff !important;
        }

        /* ── Botones de acción inferiores ── */
        .st-key-f4_card_config .stButton > button {
            background: #ffffff !important;
            border: 1px solid #bfdbfe !important;
            border-radius: 14px !important;
            color: #1d4ed8 !important;
            font-weight: 800 !important;
            font-size: 1rem !important;
            min-height: 3.1rem !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.045) !important;
            transition: all 0.2s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.55rem !important;
        }
        .st-key-f4_card_config .stButton > button:hover {
            background: #eff6ff !important;
            border-color: #3b82f6 !important;
            color: #1d4ed8 !important;
        }

        /* ── Iconos nativos Streamlit en botones Generar / Recargar ── */
        /* Streamlit renderiza icon=":material/...:" como .material-symbols-rounded */
        /* Selector sin > porque hay un div.stButton intermedio */
        .st-key-f4_btn_generar button,
        .st-key-f4_btn_recargar button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 10px !important;
            font-weight: 800 !important;
        }
        .st-key-f4_btn_generar button .material-symbols-rounded,
        .st-key-f4_btn_recargar button .material-symbols-rounded {
            font-size: 34px !important;
            line-height: 1 !important;
            width: 34px !important;
            height: 34px !important;
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 34 !important;
            flex-shrink: 0 !important;
            color: #0B63F6 !important;
        }
        .st-key-f4_btn_generar button span:not(.material-symbols-rounded),
        .st-key-f4_btn_recargar button span:not(.material-symbols-rounded) {
            font-weight: 800 !important;
        }

        .f4-top-kpi-card {
            display: flex !important;
            gap: 0.85rem !important;
            align-items: center !important;
            min-height: 75px !important;
            margin-top: -4px !important;
        }

        .f4-top-kpi-card__icon {
            width: 3rem !important;
            height: 3rem !important;
            border-radius: 999px !important;
            background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%) !important;
            border: 1px solid #bfdbfe !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            flex-shrink: 0 !important;
            box-shadow: 0 8px 18px rgba(37, 99, 235, 0.10) !important;
        }

        .f4-top-kpi-card__body {
            display: flex !important;
            flex-direction: column !important;
            gap: 0.18rem !important;
            min-width: 0 !important;
        }

        .f4-top-kpi-card__label {
            color: #475569 !important;
            font-size: 0.86rem !important;
            font-weight: 700 !important;
        }

        .f4-top-kpi-card__value {
            color: #10224f !important;
            font-size: 1.5rem !important;
            line-height: 1.02 !important;
            font-weight: 800 !important;
        }

        .f4-top-kpi-card__caption {
            color: #64748b !important;
            font-size: 0.75rem !important;
            font-weight: 600 !important;
            line-height: 1.25 !important;
        }

        .st-key-f4_top_kpi_1,
        .st-key-f4_top_kpi_2,
        .st-key-f4_top_kpi_3,
        .st-key-f4_top_kpi_4,
        .st-key-f4_top_kpi_5 {
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 22px !important;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04) !important;
            overflow: hidden !important;
        }

        .st-key-f4_top_kpi_1 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_top_kpi_2 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_top_kpi_3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_top_kpi_4 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_top_kpi_5 div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.65rem 1rem 0.65rem 1rem !important;
            min-height: 80px !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        .f4-kpi-html {
            display: flex !important;
            flex-direction: column !important;
            gap: 0.2rem !important;
            min-height: 84px !important;
            margin-top: -4px !important;
        }

        .f4-kpi-html__label {
            color: #58708f !important;
            font-size: 0.88rem !important;
            font-weight: 600 !important;
        }

        .f4-kpi-html__value {
            color: #10224f !important;
            font-size: 1.45rem !important;
            line-height: 1.1 !important;
            font-weight: 800 !important;
        }

        .f4-kpi-html__caption {
            color: #7b8aa4 !important;
            font-size: 0.76rem !important;
            font-weight: 500 !important;
        }

        .f4-note {
            margin-top: 0.7rem !important;
            padding: 0.75rem 0.95rem !important;
            border-radius: 14px !important;
            background: #eff6ff !important;
            color: #2563eb !important;
            font-size: 0.88rem !important;
            font-weight: 600 !important;
            border: 1px solid #cbd5e1 !important;
        }

        .f4-panel-hero__top {
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            gap: 0.8rem !important;
            margin-bottom: 0.55rem !important;
        }

        .f4-panel-hero__subtitle {
            color: #64748b !important;
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            margin-top: -0.2rem !important;
            margin-bottom: 0.5rem !important;
        }

        .f4-panel-toolbar {
            display: inline-flex !important;
            align-items: center !important;
            gap: 0.45rem !important;
        }

        .f4-panel-toolbar__btn {
            width: 2rem !important;
            height: 2rem !important;
            border-radius: 999px !important;
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #1d4ed8 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 0.92rem !important;
            font-weight: 800 !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04) !important;
        }

        .f4-summary-grid {
            display: flex !important;
            flex-direction: column !important;
            gap: 0.7rem !important;
        }

        .f4-summary-item {
            display: flex !important;
            align-items: baseline !important;
            justify-content: space-between !important;
            gap: 0.8rem !important;
            padding-bottom: 0.28rem !important;
            border-bottom: 1px solid rgba(219, 231, 243, 0.72) !important;
        }

        .f4-summary-item:last-child {
            border-bottom: none !important;
        }

        .f4-summary-item__label {
            color: #475569 !important;
            font-size: 0.9rem !important;
            font-weight: 700 !important;
        }

        .f4-summary-item__value {
            color: #0f172a !important;
            font-size: 1rem !important;
            font-weight: 800 !important;
            text-align: right !important;
        }



        .f4-inline-caption {
            color: #64748b !important;
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            line-height: 1.35 !important;
            padding-top: 0.3rem !important;
        }

        .f4-wind-metrics-row {
            margin-top: 0.3rem !important;
        }

        .st-key-f4_wind_metric_1,
        .st-key-f4_wind_metric_2,
        .st-key-f4_wind_metric_3 {
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 20px !important;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.035) !important;
            overflow: hidden !important;
        }

        .st-key-f4_wind_metric_1 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_wind_metric_2 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_wind_metric_3 div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.9rem 1rem !important;
            min-height: 88px !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        .stButton > button,
        [data-testid="stBaseButton-secondary"] {
            border-radius: 14px !important;
            border: 1px solid #c9dcff !important;
            background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%) !important;
            color: #1d4ed8 !important;
            font-weight: 700 !important;
            min-height: 2.9rem !important;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.045) !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.3rem !important;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 999px !important;
            padding: 0.45rem 0.95rem !important;
            color: #35527d !important;
            background: #f6f9ff !important;
        }

        .stTabs [aria-selected="true"] {
            background: #e8f0ff !important;
            color: #1d4ed8 !important;
            font-weight: 700 !important;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            border: 1px solid #dde8f5 !important;
            border-radius: 19px !important;
            padding: 0.92rem 1rem !important;
            box-shadow: 0 7px 18px rgba(15, 23, 42, 0.032) !important;
        }

        div[data-testid="stMetricLabel"] {
            color: #64748b !important;
            font-weight: 600 !important;
        }

        div[data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-weight: 800 !important;
        }

        .stDataFrame, .stDataEditor {
            border-radius: 18px !important;
            overflow: hidden !important;
            border: 1px solid #dde8f5 !important;
        }

        .st-key-f4_card_config,
        .st-key-f4_card_edit_table,
        .st-key-f4_card_move_layout,
        .st-key-f4_card_view_layout,
        .st-key-f4_card_geom_summary,
        .st-key-f4_card_wind_base,
        .st-key-f4_card_geom_analysis,
        .st-key-f4_card_annual_analysis,
        .st-key-f4_card_detail_direction,
        .st-key-f4_card_scenarios {
            background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%) !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 18px !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
            overflow: hidden !important;
        }

        .st-key-f4_card_config div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_edit_table div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_move_layout div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_view_layout div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_geom_summary div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_wind_base div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_geom_analysis div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_annual_analysis div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_detail_direction div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_scenarios div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 1.02rem 1.08rem 1.08rem 1.08rem !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        .st-key-f4_card_geom_summary .stButton > button,
        .st-key-f4_card_view_layout .stButton > button {
            margin-top: 0.5rem !important;
        }

        .st-key-f4_card_edit_table,
        .st-key-f4_card_move_layout {
            min-height: 435px !important;
        }

        .st-key-f4_card_edit_table div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_move_layout div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 435px !important;
        }

        .st-key-f4_card_edit_table [data-testid="stDataFrame"],
        .st-key-f4_card_edit_table [data-testid="stDataEditor"] {
            min-height: 304px !important;
        }

        .f4-move-subcard-title {
            color: #1d4ed8 !important;
            font-size: 0.92rem !important;
            font-weight: 800 !important;
            text-align: center !important;
            margin: 0 0 0.7rem 0 !important;
        }

        .f4-arrow-grid {
            display: grid !important;
            grid-template-columns: 1fr 1fr 1fr !important;
            grid-template-rows: auto auto auto !important;
            gap: 0.45rem !important;
            align-items: center !important;
            justify-items: center !important;
        }

        .f4-arrow-grid .stButton {
            width: 100% !important;
        }

        .f4-arrow-grid .stButton > button {
            min-height: 2.65rem !important;
        }

        .st-key-f4_move_turbine_card,
        .st-key-f4_move_park_card,
        .st-key-f4_rotate_park_card {
            background: linear-gradient(180deg, #ffffff 0%, #fcfdff 100%) !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 18px !important;
            min-height: 188px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.7) !important;
        }

        .st-key-f4_move_turbine_card div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_move_park_card div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_rotate_park_card div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.9rem 0.8rem !important;
            min-height: 188px !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        .st-key-f4_move_layout_note {
            margin-top: 0.8rem !important;
        }

        .st-key-f4_card_geom_analysis,
        .st-key-f4_card_annual_analysis,
        .st-key-f4_card_detail_direction,
        .st-key-f4_card_scenarios,
        .st-key-f4_card_compare_bars,
        .st-key-f4_card_energy_bars,
        .st-key-f4_card_scenario_save,
        .st-key-f4_card_scenario_list,
        .st-key-f4_card_scenario_compare {
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 25px !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
            overflow: visible !important;
        }

        .st-key-f4_card_geom_analysis div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_annual_analysis div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_detail_direction div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_scenarios div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_compare_bars div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_energy_bars div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_scenario_save div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_scenario_list div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_scenario_compare div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 1.02rem 1.08rem 1.08rem 1.08rem !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
        }

        .f4-mini-kpis {
            margin-bottom: 0.85rem !important;
        }

        

        .f4-detail-toolbar {
            display: flex !important;
            align-items: center !important;
            gap: 0.55rem !important;
            flex-wrap: wrap !important;
            margin-top: 0.75rem !important;
        }

        .f4-detail-toolbar .stButton {
            min-width: 106px !important;
        }

        .f4-detail-toolbar [data-testid="stNumberInput"],
        .f4-detail-toolbar [data-testid="stSelectbox"] {
            min-width: 0 !important;
        }

        .f4-plot-caption {
            color: #64748b !important;
            font-size: 0.8rem !important;
            font-weight: 600 !important;
            margin-top: -0.35rem !important;
            margin-bottom: 0.55rem !important;
        }

        .st-key-f4_card_view_layout [data-testid="stPlotlyChart"],
        .st-key-f4_card_detail_direction [data-testid="stPlotlyChart"] {
            border-radius: 18px !important;
            overflow: visible !important;
        }

        .st-key-f4_card_view_layout .js-plotly-plot .gtitle,
        .st-key-f4_card_geom_analysis .js-plotly-plot .gtitle,
        .st-key-f4_card_annual_analysis .js-plotly-plot .gtitle,
        .st-key-f4_card_compare_bars .js-plotly-plot .gtitle,
        .st-key-f4_card_energy_bars .js-plotly-plot .gtitle,
        .st-key-f4_card_detail_direction .js-plotly-plot .gtitle {
            display: none !important;
        }

        .st-key-f4_card_view_layout .modebar,
        .st-key-f4_card_detail_direction .modebar {
            background: rgba(255,255,255,0.82) !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 14px !important;
            padding: 2px 4px !important;
        }

        .st-key-f4_move_turbine_card .stButton > button,
        .st-key-f4_move_park_card .stButton > button,
        .st-key-f4_rotate_park_card .stButton > button {
            min-height: 2.5rem !important;
            padding: 0.2rem 0.35rem !important;
            font-size: 1.15rem !important;
            font-weight: 800 !important;
            line-height: 1 !important;
        }

        .st-key-f4_rotate_park_card .stButton > button {
            font-size: 1.05rem !important;
        }

        .st-key-f4_card_geom_summary .f4-summary-grid,
        .st-key-f4_card_scenario_compare,
        .st-key-f4_card_scenario_list {
            min-height: 100% !important;
        }

        .st-key-f4_card_geom_summary {
            min-height: 560px !important;
        }

        .st-key-f4_card_geom_summary div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 560px !important;
            padding: 1.35rem 1.15rem 1.35rem 1.15rem !important;
        }

        .st-key-f4_card_geom_summary .f4-summary-grid {
            gap: 0.95rem !important;
        }

        .st-key-f4_card_geom_summary .f4-summary-item {
            gap: 1rem !important;
            padding-bottom: 0.46rem !important;
            margin-bottom: 0.12rem !important;
        }

        .st-key-f4_card_geom_summary .f4-summary-item__label,
        .st-key-f4_card_geom_summary .f4-summary-item__value {
            line-height: 1.32 !important;
        }

        .st-key-f4_card_geom_summary .stButton > button {
            margin-top: 1rem !important;
            min-height: 3rem !important;
        }

        .st-key-f4_card_geom_analysis .f4-section-title__icon {
            width: 2.85rem !important;
            height: 2.85rem !important;
            min-width: 2.85rem !important;
            background: linear-gradient(180deg, #eef6ff 0%, #ffffff 100%) !important;
            border: 1px solid #bfdbfe !important;
            box-shadow: inset 0 2px 4px rgba(255, 255, 255, 0.9), 0 8px 18px rgba(37, 99, 235, 0.12) !important;
        }

        .st-key-f4_card_geom_analysis .f4-section-title__icon svg {
            width: 1.65rem !important;
            height: 1.65rem !important;
        }

        .st-key-f4_card_geom_analysis .f4-section-title__text {
            font-size: 1.22rem !important;
            color: #10224f !important;
            font-weight: 850 !important;
        }

        .f4-geom-kpi-card {
            min-height: 104px !important;
            display: flex !important;
            flex-direction: row-reverse !important;
            justify-content: space-between !important;
            align-items: center !important;
            gap: 0.95rem !important;
            padding: 1rem 1.05rem !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 18px !important;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        }

        .f4-geom-kpi-card .f4-top-kpi-card__icon {
            width: 3rem !important;
            height: 3rem !important;
            min-width: 3rem !important;
            border-radius: 999px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: #eef6ff !important;
            border: 1px solid #bfdbfe !important;
            box-shadow: inset 0 2px 4px rgba(255, 255, 255, 0.9) !important;
        }

        .f4-geom-kpi-card .f4-top-kpi-card__icon svg {
            width: 1.75rem !important;
            height: 1.75rem !important;
        }

        .f4-geom-kpi-card .f4-top-kpi-card__body {
            min-width: 0 !important;
        }

        .f4-geom-kpi-card .f4-top-kpi-card__label {
            color: #64748b !important;
            font-size: 0.78rem !important;
            font-weight: 750 !important;
            margin-bottom: 0.25rem !important;
        }

        .f4-geom-kpi-card .f4-top-kpi-card__value {
            color: #0f172a !important;
            font-size: 1.28rem !important;
            line-height: 1.12 !important;
            font-weight: 850 !important;
            overflow-wrap: anywhere !important;
        }

        .f4-geom-kpi-card .f4-top-kpi-card__caption {
            margin-top: 0.32rem !important;
            color: #64748b !important;
            font-size: 0.72rem !important;
            font-weight: 650 !important;
        }

        .st-key-f4_geom_rose_subcard {
            margin-top: 1rem !important;
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 18px !important;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.035) !important;
        }

        .st-key-f4_geom_rose_subcard div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.9rem 1rem 0.7rem 1rem !important;
        }

        .f4-geom-rose-title {
            color: #10224f !important;
            font-size: 0.95rem !important;
            font-weight: 850 !important;
            margin: 0 0 0.35rem 0 !important;
        }

        .st-key-f4_card_scenario_save .stButton > button,
        .st-key-f4_card_scenario_compare .stButton > button {
            min-height: 2.95rem !important;
        }

        .st-key-f4_btn_exportar_vista_layout button,
        .st-key-f4_compare_scenarios_btn button,
        .st-key-f4_card_scenario_save .stButton > button:first-of-type {
            background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%) !important;
            color: #ffffff !important;
            border-color: #2563eb !important;
            box-shadow: 0 10px 18px rgba(37, 99, 235, 0.18) !important;
        }

        .st-key-f4_btn_exportar_vista_layout button:hover,
        .st-key-f4_compare_scenarios_btn button:hover {
            filter: brightness(1.02) !important;
        }
        
        /* Container and Spacing Refinements */
        .st-key-f4_card_detail_direction {
            padding: 1.5rem !important;
            border-radius: 16px !important;
            box-shadow: 0 4px 14px rgba(15,23,42,0.03) !important;
            margin-bottom: 2rem !important;
        }
        .f4-detail-controls {
            margin-top: 0.5rem !important;
            padding-top: 1rem !important;
            border-top: 1px solid #e2e8f0 !important;
        }
        /* Detail section tabs */
        .st-key-f4_card_detail_direction [data-baseweb="tab"] {
            padding: 0.7rem 1.5rem !important;
            border-radius: 12px 12px 0 0 !important;
            background: #f8fafc !important;
            color: #64748b !important;
            font-weight: 700 !important;
            font-size: 1.05rem !important;
            border: 1px solid transparent !important;
            border-bottom: none !important;
            transition: all 0.2s ease !important;
            margin-right: 0.5rem !important;
        }
        .st-key-f4_card_detail_direction [data-baseweb="tab"][aria-selected="true"] {
            background: #ffffff !important;
            color: #0369a1 !important;
            border: 1px solid #bfdbfe !important;
            border-bottom: 2px solid #2563eb !important;
            box-shadow: 0 -4px 10px rgba(15,23,42,0.02) !important;
        }
        .st-key-f4_card_detail_direction [data-baseweb="tab-list"] {
            gap: 0 !important;
            border-bottom: 1px solid #e2e8f0 !important;
            padding-bottom: 0 !important;
            margin-bottom: 1.2rem !important;
        }
        
        /* KPI Cards in Detail Section */
        .f4-detail-kpi {
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 16px !important;
            padding: 0.9rem !important;
            box-shadow: 0 4px 12px rgba(15,23,42,0.035) !important;
            display: flex !important;
            flex-direction: row-reverse !important;
            justify-content: space-between !important;
            align-items: center !important;
            margin-bottom: 0.8rem !important;
        }
        .f4-detail-kpi .f4-top-kpi-card__icon {
            width: 2.8rem !important;
            height: 2.8rem !important;
            border-radius: 50% !important;
            background: #f0f9ff !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            border: 1px solid #bae6fd !important;
        }
        .f4-detail-kpi .f4-top-kpi-card__icon svg {
            width: 1.6rem !important;
            height: 1.6rem !important;
        }
        .f4-detail-kpi .f4-top-kpi-card__title {
            font-size: 0.8rem !important;
            color: #64748b !important;
            font-weight: 700 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 0.2rem !important;
        }
        .f4-detail-kpi .f4-top-kpi-card__value {
            font-size: 1.3rem !important;
            color: #0f172a !important;
            font-weight: 800 !important;
        }

        /* Detail Chart styling tweaks */
        .st-key-f4_card_detail_direction .js-plotly-plot .plotly .colorbar {
            font-family: inherit !important;
            transform: translateX(-15px) !important;
        }
        
        /* Control buttons at bottom */
        .st-key-f4_card_detail_direction .stButton > button {
            background: #ffffff !important;
            border: 1px solid #bfdbfe !important;
            border-radius: 14px !important;
            color: #1d4ed8 !important;
            font-weight: 800 !important;
            min-height: 46px !important;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.045) !important;
            width: 100% !important;
            transition: all 0.2s ease !important;
        }
        .st-key-f4_card_detail_direction .stButton > button:hover {
            background: #eff6ff !important;
            border-color: #3b82f6 !important;
        }

        .f4-wake-legend-card {
            margin: 0.45rem 0 1rem;
            padding: 1rem 1.15rem;
            border: 1px solid #bfdbfe;
            border-radius: 18px;
            background: #ffffff;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
        }

        .f4-wake-legend-title {
            color: #10224f;
            font-size: 1.02rem;
            font-weight: 900;
            letter-spacing: -0.01em;
            margin-bottom: 0.75rem;
        }

        .f4-wake-legend-content {
            display: grid;
            grid-template-columns: minmax(220px, 0.95fr) 1px minmax(300px, 1.45fr);
            gap: 1.1rem;
            align-items: center;
        }

        .f4-wake-legend-subtitle {
            color: #243b5a;
            font-size: 0.88rem;
            font-weight: 800;
            margin-bottom: 0.55rem;
        }

        .f4-wake-gradient {
            width: min(320px, 100%);
            height: 18px;
            border-radius: 999px;
            background: linear-gradient(90deg, rgba(219,234,254,0.55) 0%, rgba(96,165,250,0.68) 45%, rgba(37,99,235,0.92) 100%);
            border: 1px solid #bfdbfe;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.55);
        }

        .f4-wake-legend-divider {
            width: 1px;
            height: 54px;
            background: #dbeafe;
        }

        .f4-wake-status-row {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            flex-wrap: wrap;
        }

        .f4-wake-status-item {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            color: #334155;
            font-size: 0.86rem;
            font-weight: 800;
        }

        .f4-wake-ring {
            width: 22px;
            height: 22px;
            border-radius: 999px;
            background: #ffffff;
            box-shadow: 0 4px 10px rgba(15, 23, 42, 0.08);
        }

        .f4-wake-ring-low { border: 4px solid #10B981; }
        .f4-wake-ring-mid { border: 4px solid #F59E0B; }
        .f4-wake-ring-high { border: 4px solid #EF4444; }

        .f4-wake-status-separator {
            width: 1px;
            height: 24px;
            background: #e2e8f0;
        }

        @media (max-width: 900px) {
            .f4-wake-legend-content {
                grid-template-columns: 1fr;
            }
            .f4-wake-legend-divider {
                width: 100%;
                height: 1px;
            }
        }

        .f4-scenario-hero {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
            padding: 0.35rem 0.15rem 0.1rem;
        }

        .f4-scenario-hero__icon {
            width: 58px;
            height: 58px;
            border-radius: 18px;
            background: linear-gradient(135deg, #0B63F6 0%, #60a5fa 100%);
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 14px 28px rgba(11, 99, 246, 0.22);
        }

        .f4-scenario-hero__title {
            color: #10224f;
            font-size: 1.35rem;
            font-weight: 900;
            letter-spacing: -0.02em;
            line-height: 1.12;
        }

        .f4-scenario-hero__subtitle {
            margin-top: 0.22rem;
            color: #526a88;
            font-size: 0.9rem;
            font-weight: 650;
        }

        .f4-scenario-card-title {
            display: flex;
            align-items: center;
            gap: 0.65rem;
            margin-bottom: 0.85rem;
            color: #10224f;
            font-size: 1rem;
            font-weight: 900;
        }

        .f4-scenario-card-title__icon {
            width: 36px;
            height: 36px;
            border-radius: 12px;
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            color: #2563eb;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .f4-scenario-helper {
            display: flex;
            align-items: center;
            gap: 0.42rem;
            margin-top: 0.72rem;
            color: #64748b;
            font-size: 0.82rem;
            font-weight: 700;
        }

        .f4-scenario-table-wrap {
            border: 1px solid #cbd5e1;
            border-radius: 14px;
            overflow: hidden;
            background: #ffffff;
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.035);
        }

        .st-key-f4_card_scenario_save div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_scenario_list div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f4_card_scenario_compare div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 320px;
        }

        /* ── Ensure outer stVerticalBlockBorderWrapper has rounded blue border ──
           Handles both HTML structures Streamlit may use for keyed containers */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_config),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_edit_table),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_move_layout),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_view_layout),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_geom_summary),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_wind_base),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_geom_analysis),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_annual_analysis),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_detail_direction),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_scenarios),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_compare_bars),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_energy_bars),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_scenario_save),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_scenario_list),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_scenario_compare),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_geom_rose_subcard),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_move_turbine_card),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_move_park_card),
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_rotate_park_card) {
            border: 1px solid #cbd5e1 !important;
            border-radius: 22px !important;
            background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%) !important;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05) !important;
            overflow: hidden !important;
        }
        /* Reset inner div conflicting styles (when key class is inside the wrapper) */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_config) > .st-key-f4_card_config,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_edit_table) > .st-key-f4_card_edit_table,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_move_layout) > .st-key-f4_card_move_layout,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_view_layout) > .st-key-f4_card_view_layout,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_geom_summary) > .st-key-f4_card_geom_summary,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_wind_base) > .st-key-f4_card_wind_base,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_geom_analysis) > .st-key-f4_card_geom_analysis,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_annual_analysis) > .st-key-f4_card_annual_analysis,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_detail_direction) > .st-key-f4_card_detail_direction,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_scenarios) > .st-key-f4_card_scenarios {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
        }

</style>
        """,
        unsafe_allow_html=True,
    )


def _render_page_hero():
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f4_card_header) {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
        }
        .st-key-f4_card_header {
            border: 1.35px solid #cbd5e1 !important;
            border-radius: 28px !important;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
            overflow: visible !important;
            padding: 1.05rem 1.05rem .95rem 1.05rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True, key="f4_card_header"):
        st.markdown(
            """
            <div class="hero-card">
                <div class="fase-hero-title">Fase 4 &middot; Estelas y arreglo del parque</div>
                <div class="fase-hero-subtitle">Configure el arreglo de aerogeneradores y analice el efecto de estela.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_section_header(title, icon):
    st.markdown(
        f"""
        <div class="f4-section-title">
            <span class="f4-section-title__icon">{icon}</span>
            <span class="f4-section-title__text">{title}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_kpi_card(label, value, caption="", icon=None, class_name="f4-kpi-html"):
    icon_html = ""
    body_class = ""
    label_class = "f4-kpi-html__label"
    value_class = "f4-kpi-html__value"
    caption_class = "f4-kpi-html__caption"
    if icon:
        icon_html = f'<div class="f4-top-kpi-card__icon">{icon}</div>'
        body_class = ' class="f4-top-kpi-card__body"'
        label_class = "f4-top-kpi-card__label"
        value_class = "f4-top-kpi-card__value"
        caption_class = "f4-top-kpi-card__caption"
    st.markdown(
        textwrap.dedent(
            f"""
            <div class="{class_name}">
                {icon_html}
                <div{body_class}>
                    <div class="{label_class}">{label}</div>
                    <div class="{value_class}">{value}</div>
                    <div class="{caption_class}">{caption}</div>
                </div>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )


def _render_summary_item(label, value):
    st.markdown(
        f"""
        <div class="f4-summary-item">
            <div class="f4-summary-item__label">{label}</div>
            <div class="f4-summary-item__value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _clean_plotly_labels(fig: go.Figure) -> go.Figure:
    fig.update_layout(title=None, title_text="")
    annotations = list(fig.layout.annotations) if fig.layout.annotations else []
    clean_annotations = []
    for ann in annotations:
        ann_text = getattr(ann, "text", "")
        if ann_text is None:
            continue
        if "undefined" in str(ann_text).lower():
            continue
        clean_annotations.append(ann)
    fig.update_layout(annotations=clean_annotations)
    return fig


def _replace_wake_colorbar_with_legend(fig: go.Figure) -> go.Figure:
    """Hide Plotly color scales in wake detail views and add a compact visual legend."""
    for trace in fig.data:
        if hasattr(trace, "marker") and trace.marker is not None:
            try:
                trace.marker.showscale = False
            except Exception:
                pass
        if hasattr(trace, "showscale"):
            try:
                trace.showscale = False
            except Exception:
                pass
    return fig

    legend_shapes = [
        dict(type="rect", xref="paper", yref="paper", x0=0.705, x1=0.965, y0=0.035, y1=0.165, line=dict(color="#bfdbfe", width=1), fillcolor="rgba(255,255,255,0.92)", layer="above"),
        dict(type="rect", xref="paper", yref="paper", x0=0.725, x1=0.775, y0=0.103, y1=0.123, line=dict(width=0), fillcolor="rgba(37,99,235,0.30)", layer="above"),
        dict(type="circle", xref="paper", yref="paper", x0=0.728, x1=0.746, y0=0.061, y1=0.079, line=dict(color="#10B981", width=2), fillcolor="rgba(255,255,255,0.95)", layer="above"),
        dict(type="circle", xref="paper", yref="paper", x0=0.790, x1=0.808, y0=0.061, y1=0.079, line=dict(color="#F59E0B", width=2), fillcolor="rgba(255,255,255,0.95)", layer="above"),
        dict(type="circle", xref="paper", yref="paper", x0=0.852, x1=0.870, y0=0.061, y1=0.079, line=dict(color="#EF4444", width=2), fillcolor="rgba(255,255,255,0.95)", layer="above"),
    ]
    legend_annotations = [
        dict(xref="paper", yref="paper", x=0.725, y=0.148, xanchor="left", yanchor="middle", text="<b>Leyenda visual</b>", showarrow=False, font=dict(size=11, color="#1e3a8a")),
        dict(xref="paper", yref="paper", x=0.785, y=0.113, xanchor="left", yanchor="middle", text="Estela / déficit", showarrow=False, font=dict(size=10, color="#334155")),
        dict(xref="paper", yref="paper", x=0.884, y=0.070, xanchor="left", yanchor="middle", text="Baja · Media · Alta", showarrow=False, font=dict(size=10, color="#334155")),
    ]

    fig.update_layout(
        shapes=list(fig.layout.shapes or []) + legend_shapes,
        annotations=list(fig.layout.annotations or []) + legend_annotations,
    )
    return fig


def _render_f4_wake_legend():
    st.markdown(
        """
        <div class="f4-wake-legend-card">
            <div class="f4-wake-legend-title">Leyenda visual</div>
            <div class="f4-wake-legend-content">
                <div class="f4-wake-legend-left">
                    <div class="f4-wake-legend-subtitle">Estela / déficit</div>
                    <div class="f4-wake-gradient"></div>
                </div>
                <div class="f4-wake-legend-divider"></div>
                <div class="f4-wake-legend-right">
                    <div class="f4-wake-legend-subtitle">Afectación de aerogeneradores</div>
                    <div class="f4-wake-status-row">
                        <div class="f4-wake-status-item"><span class="f4-wake-ring f4-wake-ring-low"></span><span>Baja</span></div>
                        <div class="f4-wake-status-separator"></div>
                        <div class="f4-wake-status-item"><span class="f4-wake-ring f4-wake-ring-mid"></span><span>Media</span></div>
                        <div class="f4-wake-status-separator"></div>
                        <div class="f4-wake-status-item"><span class="f4-wake-ring f4-wake-ring-high"></span><span>Alta</span></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _add_wake_visual_layers(fig: go.Figure, df_points: pd.DataFrame, direction_deg: float = 0.0) -> go.Figure:
    """Draw wake plumes and styled turbine markers on top of a layout figure."""
    if df_points is None or df_points.empty:
        return fig

    id_col = next((c for c in ["turbina_id", "Turbina", "turbina", "id"] if c in df_points.columns), None)
    x_col = next((c for c in ["x_m", "x", "X (m)"] if c in df_points.columns), None)
    y_col = next((c for c in ["y_m", "y", "Y (m)"] if c in df_points.columns), None)
    if not x_col or not y_col:
        return fig

    df_plot = df_points[[x_col, y_col] + ([id_col] if id_col else [])].copy()
    df_plot[x_col] = pd.to_numeric(df_plot[x_col], errors="coerce")
    df_plot[y_col] = pd.to_numeric(df_plot[y_col], errors="coerce")
    df_plot = df_plot.dropna(subset=[x_col, y_col]).copy()
    if df_plot.empty:
        return fig

    n = len(df_plot)
    x_span = float(df_plot[x_col].max() - df_plot[x_col].min()) if n > 1 else 3000.0
    y_span = float(df_plot[y_col].max() - df_plot[y_col].min()) if n > 1 else 1600.0

    # Direction-aware plume geometry: layered, soft and readable without changing wake calculations.
    base_length = max(1700.0, max(x_span, y_span) * 0.72)
    near_width = max(180.0, max(x_span, y_span) * 0.055)
    far_width = max(460.0, max(x_span, y_span) * 0.18)

    angle_rad = np.deg2rad(float(direction_deg) if pd.notna(direction_deg) else 0.0)
    dx = -np.sin(angle_rad)
    dy = -np.cos(angle_rad)
    px = -dy
    py = dx
    wake_extent_x = df_plot[x_col].astype(float).tolist()
    wake_extent_y = df_plot[y_col].astype(float).tolist()

    # Layered wake: (fraction_of_length, near_w_scale, far_w_scale, opacity)
    # Each layer represents a progressively expanding, fading zone
    wake_layers = [
        (0.34, 0.42, 0.68, 0.26),
        (0.58, 0.56, 1.00, 0.18),
        (0.82, 0.82, 1.36, 0.11),
        (1.02, 1.10, 1.72, 0.07),
        (1.14, 1.36, 2.08, 0.035),
    ]

    for _, row in df_plot.iterrows():
        x0 = float(row[x_col])
        y0 = float(row[y_col])
        prev_len = 0.0
        prev_w = near_width * 0.42
        for frac, nw_scale, fw_scale, opacity in wake_layers:
            next_len = base_length * frac
            w1 = far_width * fw_scale
            start_x = x0 + dx * prev_len
            start_y = y0 + dy * prev_len
            end_x = x0 + dx * next_len
            end_y = y0 + dy * next_len
            xs = [
                start_x + px * prev_w,
                end_x + px * w1,
                end_x - px * w1,
                start_x - px * prev_w,
            ]
            ys = [
                start_y + py * prev_w,
                end_y + py * w1,
                end_y - py * w1,
                start_y - py * prev_w,
            ]
            fig.add_trace(
                go.Scatter(
                    x=xs, y=ys,
                    mode="lines",
                    line=dict(width=0),
                    fill="toself",
                    fillcolor=f"rgba(37, 99, 235, {opacity})",
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            wake_extent_x.extend(xs)
            wake_extent_y.extend(ys)
            prev_len = next_len
            prev_w = w1

    # Enhanced Turbine visuals (SVG animations and hover layers)
    labels = df_plot[id_col].astype(str).tolist() if id_col else [f"T{i+1}" for i in range(n)]
    rotor_r_m = max(150.0, max(x_span, y_span) * 0.045)
    
    # Calculate simple penalties for coloring
    penalties = {}
    theta = np.deg2rad(float(direction_deg) if pd.notna(direction_deg) else 0.0)
    dx, dy = -np.sin(theta), -np.cos(theta)
    px, py = -dy, dx
    wake_width = rotor_r_m * 2.0
    wake_length = rotor_r_m * 12.0
    
    for row_a in df_plot.itertuples(index=False):
        penalty = 0.0
        x_a = float(getattr(row_a, x_col))
        y_a = float(getattr(row_a, y_col))
        id_a = str(getattr(row_a, id_col)) if id_col else str(x_a)
        for row_b in df_plot.itertuples(index=False):
            x_b = float(getattr(row_b, x_col))
            y_b = float(getattr(row_b, y_col))
            id_b = str(getattr(row_b, id_col)) if id_col else str(x_b)
            if id_a == id_b: continue
            rel_x = x_a - x_b
            rel_y = y_a - y_b
            down_proj = rel_x * dx + rel_y * dy
            cross_proj = abs(rel_x * px + rel_y * py)
            if down_proj <= 0.0 or cross_proj > wake_width: continue
            penalty += float(np.exp(-down_proj / wake_length) * np.exp(-((cross_proj / wake_width) ** 2)))
        penalties[id_a] = penalty
    max_penalty = max(penalties.values(), default=0.0)

    ring_x = []
    ring_y = []
    ring_colors = []
    for i, row in enumerate(df_plot.itertuples(index=False)):
        x0 = float(getattr(row, x_col))
        y0 = float(getattr(row, y_col))
        id_a = str(getattr(row, id_col)) if id_col else str(x0)
        penalty_norm = penalties.get(id_a, 0.0) / max(max_penalty, 1e-6) if max_penalty > 0 else 0.0
        
        if penalty_norm < 0.15: turbine_color = "#10B981"
        elif penalty_norm < 0.45: turbine_color = "#F59E0B"
        else: turbine_color = "#EF4444"
        ring_x.append(x0)
        ring_y.append(y0)
        ring_colors.append(turbine_color)
            
        image_source = _build_animated_turbine_data_uri(None, color=turbine_color)
        fig.add_layout_image(
            dict(
                source=image_source,
                xref="x",
                yref="y",
                x=x0,
                y=y0,
                sizex=rotor_r_m * 3.0,
                sizey=rotor_r_m * 3.0,
                xanchor="center",
                yanchor="middle",
                sizing="contain",
                layer="above",
                opacity=1.0,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=ring_x,
            y=ring_y,
            mode="markers",
            marker=dict(
                size=36,
                color="rgba(255,255,255,0.92)",
                line=dict(color=ring_colors, width=4),
            ),
            hoverinfo="skip",
            showlegend=False,
            name="",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_plot[x_col],
            y=df_plot[y_col] + rotor_r_m * 1.35,
            mode="text",
            text=labels,
            textfont=dict(size=15, color="#0B3A82", family="Arial Black, Arial, sans-serif"),
            hoverinfo="skip",
            showlegend=False,
            name="",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_plot[x_col],
            y=df_plot[y_col],
            mode="markers",
            marker=dict(size=30, color="rgba(0,0,0,0)"),
            text=labels,
            hovertemplate="<b>%{text}</b><br>X: %{x:.0f} m<br>Y: %{y:.0f} m<extra></extra>",
            showlegend=False,
            name="",
        )
    )
    pad = max(rotor_r_m * 2.4, 380.0)
    fig.update_xaxes(range=[min(wake_extent_x) - pad, max(wake_extent_x) + pad], automargin=True)
    fig.update_yaxes(range=[min(wake_extent_y) - pad, max(wake_extent_y) + pad], automargin=True)
    return fig


def _enhance_main_park_figure(
    fig: go.Figure,
    df_layout: pd.DataFrame,
    direction_deg: float = 0.0,
    direction_label: str = "N",
    sector_visual_df: pd.DataFrame | None = None,
    geom_sector_df: pd.DataFrame | None = None,
) -> go.Figure:
    if df_layout is None or df_layout.empty:
        return fig

    df_plot = df_layout[["turbina_id", "x_m", "y_m"]].copy()
    df_plot["x_m"] = pd.to_numeric(df_plot["x_m"], errors="coerce")
    df_plot["y_m"] = pd.to_numeric(df_plot["y_m"], errors="coerce")
    df_plot = df_plot.dropna(subset=["x_m", "y_m"]).copy()
    if df_plot.empty:
        return fig

    fig.data = ()

    x_min = float(df_plot["x_m"].min())
    x_max = float(df_plot["x_m"].max())
    y_min = float(df_plot["y_m"].min())
    y_max = float(df_plot["y_m"].max())
    x_span = max(2400.0, x_max - x_min)
    y_span = max(1800.0, y_max - y_min)
    plume_length = max(3220.0, x_span * 0.84)
    rotor_r = max(126.0, y_span * 0.052)
    rotor_diameter_m = float(globals().get("diametro", rotor_r * 2.0))
    initial_half_width = rotor_diameter_m / 2.0
    theta_deg = float(direction_deg)
    fig.update_layout(
        meta=dict(
            main_park_rotor_radius_m=rotor_r,
            main_park_direction_deg=theta_deg,
            main_park_direction_label=str(direction_label),
        )
    )

    # opacity, end-length factor, start width, end width
    wake_specs = [
        (0.20, 0.70, 0.13, 0.62),
        (0.17, 0.78, 0.145, 0.76),
        (0.14, 0.86, 0.16, 0.93),
        (0.11, 0.94, 0.175, 1.14),
        (0.09, 1.00, 0.19, 1.37),
        (0.07, 1.06, 0.205, 1.63),
        (0.055, 1.11, 0.225, 1.88),
        (0.04, 1.15, 0.25, 2.13),
        (0.03, 1.19, 0.28, 2.34),
        (0.02, 1.22, 0.31, 2.55),
    ]
    if sector_visual_df is None or sector_visual_df.empty:
        sector_visual_df = pd.DataFrame(
            [{
                "Sector": str(direction_label),
                "Dirección centro (°)": float(theta_deg),
                "Frecuencia (%)": 100.0,
                "Velocidad media sector (m/s)": 8.0,
                "intensidad_visual": 1.0,
            }]
        )
    geom_lookup: dict[str, float] = {}
    geom_max = 0.0
    if geom_sector_df is not None and not geom_sector_df.empty:
        geom_sector_col = next((c for c in geom_sector_df.columns if "sector" in str(c).lower()), None)
        geom_loss_col = next((c for c in geom_sector_df.columns if "geom" in str(c).lower()), None)
        if geom_sector_col and geom_loss_col:
            geom_tmp = geom_sector_df[[geom_sector_col, geom_loss_col]].copy()
            geom_tmp[geom_sector_col] = geom_tmp[geom_sector_col].astype(str)
            geom_tmp[geom_loss_col] = pd.to_numeric(geom_tmp[geom_loss_col], errors="coerce").fillna(0.0)
            geom_lookup = dict(zip(geom_tmp[geom_sector_col], geom_tmp[geom_loss_col]))
            geom_max = max(geom_lookup.values(), default=0.0)

    wake_extent_x = [x_min, x_max]
    wake_extent_y = [y_min, y_max]
    freq_max = max(float(sector_visual_df["Frecuencia (%)"].max()), 1e-6)
    for _, sector_row in sector_visual_df.iterrows():
        sector_deg = float(sector_row["Dirección centro (°)"])
        sector_intensity = float(sector_row.get("intensidad_visual", 0.0))
        if sector_intensity <= 0.0:
            continue
        theta = np.deg2rad(sector_deg)
        dx = -np.sin(theta)
        dy = -np.cos(theta)
        px = -dy
        py = dx
        geom_sector_loss = float(geom_lookup.get(str(sector_row.get("Sector", direction_label)), 0.0))
        geom_sector_weight = geom_sector_loss / max(geom_max, 1e-6) if geom_max > 0 else 0.0
        prob_pct = float(sector_row["Frecuencia (%)"])
        prob_weight = float(np.clip(prob_pct / freq_max, 0.0, 1.0))
        wake_len_scale = 0.46 + 0.84 * sector_intensity
        wake_width_scale = 0.84 + 1.28 * sector_intensity
        opacity_scale = 0.16 + 0.84 * prob_weight
        wake_extent_x.extend([x_min + dx * plume_length * wake_len_scale, x_max + dx * plume_length * wake_len_scale])
        wake_extent_y.extend([y_min + dy * plume_length * wake_len_scale, y_max + dy * plume_length * wake_len_scale])

        for _, row in df_plot.iterrows():
            x0 = float(row["x_m"])
            y0 = float(row["y_m"])
            x_start = x0 + dx * rotor_r * 0.25
            y_start = y0 + dy * rotor_r * 0.25
            for opacity, len_factor, w0_scale, w_end_scale in wake_specs:
                lengths = np.linspace(0.0, plume_length * len_factor * wake_len_scale, 84)
                t = lengths / max(plume_length * len_factor * wake_len_scale, 1e-6)
                layer_start_half = initial_half_width * max(1.0, w0_scale / 0.13)
                layer_end_half = rotor_r * wake_width_scale * w_end_scale
                width_curve = layer_start_half + (layer_end_half - layer_start_half) * (t ** 0.72)
                tail_window = np.clip((t - 0.82) / 0.18, 0.0, 1.0)
                tail_soft = 1.0 - 0.16 * np.sin(tail_window * np.pi / 2.0) ** 1.35
                edge_soft = 0.96 + 0.04 * np.cos(np.pi * (1.0 - t)) ** 2
                width_curve = width_curve * tail_soft * edge_soft
                center_x = x_start + dx * lengths
                center_y = y_start + dy * lengths
                x_top = center_x + px * width_curve
                y_top = center_y + py * width_curve
                x_bottom = center_x - px * width_curve
                y_bottom = center_y - py * width_curve
                x_poly = np.concatenate((x_top, x_bottom[::-1]))
                y_poly = np.concatenate((y_top, y_bottom[::-1]))
                fig.add_trace(
                    go.Scatter(
                        x=x_poly,
                        y=y_poly,
                        mode="none",
                        line=dict(width=0),
                        fill="toself",
                        fillcolor=f"rgba(11, 99, 246, {opacity * opacity_scale * sector_intensity:.4f})",
                        hoverinfo="skip",
                        showlegend=False,
                    )
                )

            core_len = plume_length * 0.96 * wake_len_scale
            core_lengths = np.linspace(0.0, core_len, 76)
            core_t = core_lengths / max(core_len, 1e-6)
            core_w = rotor_r * wake_width_scale * (0.085 + (0.42 - 0.085) * (core_t ** 0.66))
            core_tail = np.clip((core_t - 0.84) / 0.16, 0.0, 1.0)
            core_w = core_w * (1.0 - 0.18 * np.sin(core_tail * np.pi / 2.0) ** 1.2)
            core_center_x = x_start + dx * core_lengths
            core_center_y = y_start + dy * core_lengths
            core_top_x = core_center_x + px * core_w
            core_top_y = core_center_y + py * core_w
            core_bottom_x = core_center_x - px * core_w
            core_bottom_y = core_center_y - py * core_w
            core_poly_x = np.concatenate((core_top_x, core_bottom_x[::-1]))
            core_poly_y = np.concatenate((core_top_y, core_bottom_y[::-1]))
            fig.add_trace(
                go.Scatter(
                    x=core_poly_x,
                    y=core_poly_y,
                    mode="none",
                    line=dict(width=0),
                    fill="toself",
                    fillcolor=f"rgba(11, 99, 246, {0.18 * opacity_scale * sector_intensity:.4f})",
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            if geom_sector_weight > 0.0:
                overlap_weights: list[float] = []
                for _, other_row in df_plot.iterrows():
                    if other_row["turbina_id"] == row["turbina_id"]:
                        continue
                    delta_x = float(other_row["x_m"]) - x0
                    delta_y = float(other_row["y_m"]) - y0
                    down_proj = delta_x * dx + delta_y * dy
                    if down_proj <= rotor_r * 0.30:
                        continue
                    cross_proj = abs(delta_x * px + delta_y * py)
                    longitudinal = np.exp(-down_proj / max(plume_length * 0.56, 1e-6))
                    transverse = np.exp(-((cross_proj / max(rotor_r * 1.95, 1e-6)) ** 1.45))
                    overlap_weights.append(longitudinal * transverse)
                turbine_penalty = np.clip(sum(overlap_weights), 0.0, 2.4) / 2.4
                geom_intensity = float(np.clip(geom_sector_weight * turbine_penalty * (0.38 + 0.62 * sector_intensity), 0.0, 1.0))
                if geom_intensity > 0.025:
                    geom_specs = [
                        ("rgba(251, 146, 60, {alpha:.4f})", 0.09, 0.40, 0.05, 0.17),
                        ("rgba(249, 115, 22, {alpha:.4f})", 0.08, 0.52, 0.06, 0.22),
                        ("rgba(239, 68, 68, {alpha:.4f})", 0.06, 0.64, 0.07, 0.27),
                    ]
                    for color_tpl, base_opacity, len_factor, w0_scale, w_end_scale in geom_specs:
                        geom_lengths = np.linspace(0.0, plume_length * len_factor * wake_len_scale, 64)
                        geom_t = geom_lengths / max(plume_length * len_factor * wake_len_scale, 1e-6)
                        geom_width = rotor_r * (w0_scale + (w_end_scale - w0_scale) * (geom_t ** 0.78))
                        geom_tail = np.clip((geom_t - 0.74) / 0.26, 0.0, 1.0)
                        geom_width = geom_width * (1.0 - 0.20 * np.sin(geom_tail * np.pi / 2.0) ** 1.15)
                        geom_center_x = x_start + dx * geom_lengths
                        geom_center_y = y_start + dy * geom_lengths
                        geom_top_x = geom_center_x + px * geom_width
                        geom_top_y = geom_center_y + py * geom_width
                        geom_bottom_x = geom_center_x - px * geom_width
                        geom_bottom_y = geom_center_y - py * geom_width
                        geom_poly_x = np.concatenate((geom_top_x, geom_bottom_x[::-1]))
                        geom_poly_y = np.concatenate((geom_top_y, geom_bottom_y[::-1]))
                        fig.add_trace(
                            go.Scatter(
                                x=geom_poly_x,
                                y=geom_poly_y,
                                mode="none",
                                line=dict(width=0),
                                fill="toself",
                                fillcolor=color_tpl.format(alpha=base_opacity * geom_intensity),
                                hoverinfo="skip",
                                showlegend=False,
                            )
                        )

    cross_pad = rotor_r * 1.35 + 280.0
    fig.update_xaxes(
        range=[
            min(wake_extent_x) - cross_pad,
            max(wake_extent_x) + cross_pad,
        ],
        automargin=True,
    )
    fig.update_yaxes(
        range=[
            min(wake_extent_y) - cross_pad,
            max(wake_extent_y) + cross_pad,
        ],
        automargin=True,
    )
    fig.frames = ()
    fig.update_layout(updatemenus=[])
    return fig


def _infer_cut_speeds_from_curve(curva_df: pd.DataFrame) -> tuple[float, float]:
    if curva_df is None or curva_df.empty:
        return 3.0, 25.0
    df = curva_df.copy()
    vel_candidates = [c for c in df.columns if "vel" in str(c).lower()]
    pot_candidates = [c for c in df.columns if "pot" in str(c).lower()]
    vel_col = vel_candidates[0] if vel_candidates else None
    pot_col = pot_candidates[0] if pot_candidates else None
    if vel_col is None or pot_col is None:
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if len(numeric_cols) >= 2:
            vel_col = vel_col or numeric_cols[0]
            pot_col = pot_col or numeric_cols[1]
        else:
            return 3.0, 25.0
    vel = pd.to_numeric(df[vel_col], errors="coerce")
    pot = pd.to_numeric(df[pot_col], errors="coerce")
    valid = pd.DataFrame({"vel": vel, "pot": pot}).dropna()
    valid = valid[valid["pot"] > 0]
    if valid.empty:
        return 3.0, 25.0
    return float(valid["vel"].min()), float(valid["vel"].max())


def _rotor_animation_duration(wind_speed: float, cut_in: float, cut_out: float) -> float | None:
    if wind_speed < cut_in or wind_speed >= cut_out:
        return None
    if wind_speed < 6.0:
        return 4.8
    if wind_speed < 9.0:
        return 3.2
    if wind_speed < 12.0:
        return 2.0
    return 1.2


def _build_main_park_sector_visual_data(
    df_nasa: pd.DataFrame,
    base_viento: str,
    altura_deseada: float,
    roughness_label: str,
    direccion_altura: str,
    curva_df: pd.DataFrame,
    fallback_speed: float,
) -> tuple[pd.DataFrame, dict]:
    cut_in, cut_out = _infer_cut_speeds_from_curve(curva_df)
    fallback_rows = pd.DataFrame(
        {
            "Sector": SECTOR_LABELS_16,
            "Dirección centro (°)": SECTOR_CENTERS_16,
            "Frecuencia (%)": [100.0 / len(SECTOR_LABELS_16)] * len(SECTOR_LABELS_16),
            "Velocidad media sector (m/s)": [float(fallback_speed)] * len(SECTOR_LABELS_16),
        }
    )
    try:
        df_viento, _ = construir_viento_analisis(
            df_nasa=df_nasa,
            base_viento=base_viento,
            altura_deseada=altura_deseada,
            roughness_label=roughness_label,
            direccion_altura=direccion_altura,
        )
        if df_viento is None or df_viento.empty or "WD_ANALISIS" not in df_viento.columns or "WS_ANALISIS" not in df_viento.columns:
            raise ValueError("No hay columnas de viento analizado.")
        df_work = df_viento[["WD_ANALISIS", "WS_ANALISIS"]].copy()
        df_work["WD_ANALISIS"] = pd.to_numeric(df_work["WD_ANALISIS"], errors="coerce") % 360.0
        df_work["WS_ANALISIS"] = pd.to_numeric(df_work["WS_ANALISIS"], errors="coerce")
        df_work = df_work.dropna()
        if df_work.empty:
            raise ValueError("No hay registros válidos de viento analizado.")
        sector_idx = (((df_work["WD_ANALISIS"] + 11.25) % 360.0) // 22.5).astype(int)
        df_work["Sector"] = sector_idx.map(lambda i: SECTOR_LABELS_16[int(i)])
        grouped = (
            df_work.groupby("Sector", observed=False)
            .agg(
                frecuencia=("Sector", "size"),
                velocidad_media=("WS_ANALISIS", "mean"),
            )
            .reset_index()
        )
        total = max(float(grouped["frecuencia"].sum()), 1.0)
        grouped["Frecuencia (%)"] = grouped["frecuencia"] / total * 100.0
        grouped["Velocidad media sector (m/s)"] = grouped["velocidad_media"]
        grouped = grouped.drop(columns=["frecuencia", "velocidad_media"])
        sector_df = pd.DataFrame(
            {
                "Sector": SECTOR_LABELS_16,
                "Dirección centro (°)": SECTOR_CENTERS_16,
            }
        ).merge(grouped, on="Sector", how="left")
        sector_df["Frecuencia (%)"] = sector_df["Frecuencia (%)"].fillna(0.0)
        sector_df["Velocidad media sector (m/s)"] = sector_df["Velocidad media sector (m/s)"].fillna(float(fallback_speed))
        fallback_used = False
    except Exception:
        sector_df = fallback_rows.copy()
        fallback_used = True

    freq_max = max(float(sector_df["Frecuencia (%)"].max()), 1e-6)
    speed_span = max(cut_out - cut_in, 1e-6)
    sector_df["operativo"] = (
        (sector_df["Velocidad media sector (m/s)"] >= cut_in)
        & (sector_df["Velocidad media sector (m/s)"] < cut_out)
    )
    sector_df["peso_prob"] = sector_df["Frecuencia (%)"] / freq_max
    sector_df["peso_vel"] = np.clip((sector_df["Velocidad media sector (m/s)"] - cut_in) / speed_span, 0.0, 1.0)
    sector_df["intensidad_visual"] = np.where(
        sector_df["operativo"],
        sector_df["peso_prob"] * sector_df["peso_vel"],
        0.0,
    )
    operational = sector_df[sector_df["operativo"] & (sector_df["Frecuencia (%)"] > 0)]
    if operational.empty:
        representative_speed = float(fallback_speed)
        dominant_label = "N"
        dominant_deg = 0.0
    else:
        representative_speed = float(
            np.average(
                operational["Velocidad media sector (m/s)"],
                weights=np.clip(operational["Frecuencia (%)"], 1e-6, None),
            )
        )
        dominant_row = sector_df.sort_values(["intensidad_visual", "Frecuencia (%)"], ascending=False).iloc[0]
        dominant_label = str(dominant_row["Sector"])
        dominant_deg = float(dominant_row["Dirección centro (°)"])

    return sector_df, {
        "cut_in": cut_in,
        "cut_out": cut_out,
        "representative_speed": representative_speed,
        "dominant_label": dominant_label,
        "dominant_deg": dominant_deg,
        "fallback_used": fallback_used,
    }


def _build_animated_turbine_data_uri(rotor_duration: float | None, color: str = "#0B63F6") -> str:
    def _blade_points(angle_deg: float) -> str:
        rad = np.deg2rad(angle_deg)
        perp = rad + np.pi / 2.0
        inner = 11.5
        mid = 27.0
        tip = 39.0
        root_half = 2.2
        mid_half = 4.2
        tip_half = 1.5
        sweep = 2.0
        points = [
            (inner * np.cos(rad) + root_half * np.cos(perp), -(inner * np.sin(rad) + root_half * np.sin(perp))),
            (mid * np.cos(rad) + mid_half * np.cos(perp), -(mid * np.sin(rad) + mid_half * np.sin(perp))),
            (tip * np.cos(rad) + tip_half * np.cos(perp), -(tip * np.sin(rad) + tip_half * np.sin(perp))),
            ((tip - sweep) * np.cos(rad) - tip_half * 0.8 * np.cos(perp), -((tip - sweep) * np.sin(rad) - tip_half * 0.8 * np.sin(perp))),
            ((mid - sweep) * np.cos(rad) - mid_half * np.cos(perp), -((mid - sweep) * np.sin(rad) - mid_half * np.sin(perp))),
            ((inner - sweep * 0.35) * np.cos(rad) - root_half * np.cos(perp), -((inner - sweep * 0.35) * np.sin(rad) - root_half * np.sin(perp))),
        ]
        return " ".join(f"{px:.1f},{py:.1f}" for px, py in points)

    rotor_animation = (
        f"""
        <animateTransform
            attributeName="transform"
            attributeType="XML"
            type="rotate"
            from="0 0 0"
            to="360 0 0"
            dur="{rotor_duration:.2f}s"
            repeatCount="indefinite"
        />
        """
        if rotor_duration is not None
        else ""
    )
    svg = textwrap.dedent(
        f"""
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="-64 -64 128 128">
            <g>
                <line x1="0" y1="4" x2="0" y2="52" stroke="{color}" stroke-width="1.8" stroke-linecap="round"/>
                <circle cx="0" cy="0" r="33" fill="#ffffff" stroke="{color}" stroke-width="2.0"/>
                <g>
                    <polygon points="{_blade_points(90)}" fill="{color}"/>
                    <polygon points="{_blade_points(210)}" fill="{color}"/>
                    <polygon points="{_blade_points(330)}" fill="{color}"/>
                    {rotor_animation}
                </g>
                <circle cx="0" cy="0" r="3.6" fill="{color}"/>
            </g>
        </svg>
        """
    ).strip()
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _render_main_park_animated_html(
    fig: go.Figure,
    df_layout: pd.DataFrame,
    wind_speed: float,
    curva_df: pd.DataFrame,
    plot_config: dict,
    direction_deg: float = 0.0,
) -> str:
    cut_in, cut_out = _infer_cut_speeds_from_curve(curva_df)
    rotor_duration = _rotor_animation_duration(float(wind_speed), cut_in, cut_out)
    rotor_r_m = 120.0
    if isinstance(fig.layout.meta, dict):
        rotor_r_m = float(fig.layout.meta.get("main_park_rotor_radius_m", rotor_r_m))
    fig.update_layout(images=[])
    label_x = []
    label_y = []
    label_text = []

    df_turbines = df_layout[["turbina_id", "x_m", "y_m"]].dropna().copy()
    df_turbines["x_m"] = pd.to_numeric(df_turbines["x_m"], errors="coerce")
    df_turbines["y_m"] = pd.to_numeric(df_turbines["y_m"], errors="coerce")
    df_turbines = df_turbines.dropna(subset=["x_m", "y_m"])
    theta = np.deg2rad(float(direction_deg))
    dx = -np.sin(theta)
    dy = -np.cos(theta)
    px = -dy
    py = dx
    wake_length = max(rotor_r_m * 18.0, 2200.0)
    wake_width = max(rotor_r_m * 2.25, 260.0)
    penalties: dict[str, float] = {}
    for row_a in df_turbines.itertuples(index=False):
        penalty = 0.0
        x_a = float(row_a.x_m)
        y_a = float(row_a.y_m)
        for row_b in df_turbines.itertuples(index=False):
            if row_a.turbina_id == row_b.turbina_id:
                continue
            rel_x = x_a - float(row_b.x_m)
            rel_y = y_a - float(row_b.y_m)
            down_proj = rel_x * dx + rel_y * dy
            cross_proj = abs(rel_x * px + rel_y * py)
            if down_proj <= 0.0 or cross_proj > wake_width:
                continue
            penalty += float(np.exp(-down_proj / wake_length) * np.exp(-((cross_proj / wake_width) ** 2)))
        penalties[str(row_a.turbina_id)] = penalty
    max_penalty = max(penalties.values(), default=0.0)

    for row in df_turbines.itertuples(index=False):
        x0 = float(row.x_m)
        y0 = float(row.y_m)
        penalty_norm = penalties.get(str(row.turbina_id), 0.0) / max(max_penalty, 1e-6) if max_penalty > 0 else 0.0
        if penalty_norm < 0.15:
            turbine_color = "#10B981"
        elif penalty_norm < 0.45:
            turbine_color = "#F59E0B"
        else:
            turbine_color = "#EF4444"
        image_source = _build_animated_turbine_data_uri(rotor_duration, color=turbine_color)
        fig.add_layout_image(
            dict(
                source=image_source,
                xref="x",
                yref="y",
                x=x0,
                y=y0,
                sizex=rotor_r_m * 3.0,
                sizey=rotor_r_m * 3.0,
                xanchor="center",
                yanchor="middle",
                sizing="contain",
                layer="above",
                opacity=1.0,
            )
        )
        label_x.append(x0)
        label_y.append(y0 + rotor_r_m * 1.20)
        label_text.append(str(row.turbina_id))
    fig.add_trace(
        go.Scatter(
            x=label_x,
            y=label_y,
            mode="text",
            text=label_text,
            textfont=dict(size=14, color="#0B63F6", family="Arial Black, Arial, sans-serif"),
            hoverinfo="skip",
            showlegend=False,
        )
    )

    return fig.to_html(
        full_html=False,
        include_plotlyjs=True,
        config=plot_config,
        default_width="100%",
        default_height=f"{int(fig.layout.height or 610)}px",
    )


def _cached_park_html(fig, df_layout, wind_speed, curva_df, plot_config, direction_deg=0.0):
    """Wrapper que cachea el HTML generado por _render_main_park_animated_html.

    El bundle plotly.js (~3.5 MB) se serializa una vez por configuración única
    de layout + viento + curva. Reruns con la misma config son cache hit.
    """
    try:
        df_l = df_layout[["turbina_id", "x_m", "y_m"]].copy()
        df_l["x_m"] = pd.to_numeric(df_l["x_m"], errors="coerce").round(2)
        df_l["y_m"] = pd.to_numeric(df_l["y_m"], errors="coerce").round(2)
        layout_hash = int(pd.util.hash_pandas_object(df_l, index=False).sum())
    except Exception:
        layout_hash = id(df_layout)
    try:
        curva_hash = int(pd.util.hash_pandas_object(curva_df, index=False).sum()) if curva_df is not None else 0
    except Exception:
        curva_hash = id(curva_df)
    key = (
        layout_hash,
        round(float(wind_speed), 4),
        round(float(direction_deg), 4),
        curva_hash,
        int(fig.layout.height or 610),
    )
    cache = st.session_state.setdefault("_f4_park_html_cache", {})
    if key in cache:
        return cache[key]
    html = _render_main_park_animated_html(
        fig=fig,
        df_layout=df_layout,
        wind_speed=wind_speed,
        curva_df=curva_df,
        plot_config=plot_config,
        direction_deg=direction_deg,
    )
    cache[key] = html
    if len(cache) > 32:
        cache.pop(next(iter(cache)), None)
    return html


def _style_main_park_figure(fig: go.Figure) -> go.Figure:
    current_annotations = list(fig.layout.annotations or [])
    current_shapes = list(fig.layout.shapes or [])
    bar_x0 = 0.035
    bar_x1 = 0.67
    bar_y0 = -0.215
    bar_y1 = -0.198
    num_segments = 60  # 60 segmentos sin bordes visibles para un gradiente suave

    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    start_rgb = _hex_to_rgb("#dbeafe")
    mid_rgb = _hex_to_rgb("#60a5fa")
    end_rgb = _hex_to_rgb("#2563eb")
    gradient_shapes = []
    for idx in range(num_segments):
        t = idx / max(num_segments - 1, 1)
        if t <= 0.5:
            local_t = t / 0.5
            rgb = tuple(int(start_rgb[c] + (mid_rgb[c] - start_rgb[c]) * local_t) for c in range(3))
        else:
            local_t = (t - 0.5) / 0.5
            rgb = tuple(int(mid_rgb[c] + (end_rgb[c] - mid_rgb[c]) * local_t) for c in range(3))
        seg_x0 = bar_x0 + (bar_x1 - bar_x0) * (idx / num_segments)
        seg_x1 = bar_x0 + (bar_x1 - bar_x0) * ((idx + 1) / num_segments)
        gradient_shapes.append(
            dict(
                type="rect",
                xref="paper",
                yref="paper",
                x0=seg_x0,
                x1=seg_x1,
                y0=bar_y0,
                y1=bar_y1,
                line=dict(width=0),
                fillcolor=f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})",
            )
        )

    fig.update_layout(
        title=None,
        height=610,
        margin=dict(l=44, r=28, t=20, b=104),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#fbfdff",
        showlegend=False,
        xaxis=dict(
            title=dict(text="X (m)", font=dict(size=13, color="#475569")),
            showgrid=True,
            gridcolor="rgba(148,163,184,0.16)",
            gridwidth=1,
            linecolor="#cbd5e1",
            linewidth=1,
            mirror=False,
            zeroline=False,
            tickfont=dict(size=11, color="#64748b"),
        ),
        yaxis=dict(
            title=dict(text="Y (m)", font=dict(size=13, color="#475569")),
            showgrid=True,
            gridcolor="rgba(148,163,184,0.16)",
            gridwidth=1,
            linecolor="#cbd5e1",
            linewidth=1,
            mirror=False,
            zeroline=False,
            tickfont=dict(size=11, color="#64748b"),
            scaleanchor="x",
            scaleratio=1,
        ),
        annotations=current_annotations + [
            dict(
                xref="paper", yref="paper",
                x=bar_x0, y=-0.165,
                xanchor="left", yanchor="top",
                text="<b>Intensidad del efecto de estela (d\u00e9ficit de velocidad)</b>",
                showarrow=False,
                align="left",
                font=dict(size=11, color="#334155"),
            ),
            dict(
                xref="paper", yref="paper",
                x=bar_x0, y=-0.255,
                xanchor="left", yanchor="top",
                text="<b>0%</b>",
                showarrow=False,
                font=dict(size=10, color="#64748b"),
            ),
            dict(
                xref="paper", yref="paper",
                x=(bar_x0 + bar_x1) / 2.0, y=-0.255,
                xanchor="center", yanchor="top",
                text="<b>50%</b>",
                showarrow=False,
                font=dict(size=10, color="#64748b"),
            ),
            dict(
                xref="paper", yref="paper",
                x=bar_x1, y=-0.255,
                xanchor="right", yanchor="top",
                text="<b>100%</b>",
                showarrow=False,
                font=dict(size=10, color="#64748b"),
            ),
        ],
        shapes=current_shapes + gradient_shapes + [
            dict(
                type="rect",
                xref="paper",
                yref="paper",
                x0=bar_x0,
                x1=bar_x1,
                y0=bar_y0,
                y1=bar_y1,
                line=dict(color="#cbd5e1", width=1),
                fillcolor="rgba(0,0,0,0)",
            ),
        ],
    )
    return _clean_plotly_labels(fig)


@st.cache_data(show_spinner=False)
def crear_rosa_geom(df_geom):
    import math
    max_val = df_geom["Pérdida geométrica (%)"].max() if not df_geom.empty else 1.0
    if pd.isna(max_val) or max_val == 0: max_val = 1.0
    if max_val <= 10: dtick = 2; max_r = math.ceil(max_val / 2.0) * 2
    elif max_val <= 25: dtick = 5; max_r = math.ceil(max_val / 5.0) * 5
    else: dtick = 10; max_r = math.ceil(max_val / 10.0) * 10
    if max_r < dtick: max_r = dtick

    scale_shapes = [dict(type="line", xref="paper", yref="paper", x0=0.08, x1=0.08, y0=0.15, y1=0.85, line=dict(color="#cbd5e1", width=2))]
    scale_annotations = [dict(xref="paper", yref="paper", x=0.08, y=0.92, text="<b>Escala Radial</b><br><span style='font-size:9px'>(Pérdida)</span>", showarrow=False, font=dict(size=11, color="#64748b"), align="center")]
    
    vals = []
    v = 0.0
    while v <= max_r + 1e-9:
        vals.append(v)
        v += dtick
        
    for v in vals:
        y_pos = 0.15 + 0.7 * (v / max_r)
        scale_shapes.append(dict(type="line", xref="paper", yref="paper", x0=0.08, x1=0.10, y0=y_pos, y1=y_pos, line=dict(color="#cbd5e1", width=2)))
        scale_annotations.append(dict(xref="paper", yref="paper", x=0.065, y=y_pos, text=f"<b>{v:g}%</b>", showarrow=False, xanchor="right", yanchor="middle", font=dict(size=11, color="#475569")))

    fig = go.Figure()
    fig.add_trace(
        go.Barpolar(
            r=df_geom["Pérdida geométrica (%)"],
            theta=df_geom["Dirección centro (°)"],
            width=[22.5] * len(df_geom),
            marker=dict(color=df_geom["Pérdida geométrica (%)"], colorscale="Reds", colorbar=dict(title="Pérdida geométrica (%)")),
            customdata=np.stack([df_geom["Sector"], df_geom["Velocidad referencia (m/s)"], df_geom["Turbinas afectadas"], df_geom["Eficiencia geométrica (%)"]], axis=1),
            hovertemplate="Sector: %{customdata[0]}<br>Pérdida geométrica: %{r:.2f}%<br>Velocidad referencia: %{customdata[1]:.2f} m/s<br>Turbinas afectadas: %{customdata[2]}<br>Eficiencia: %{customdata[3]:.2f}%<extra></extra>",
            name="Pérdida geométrica",
        )
    )
    fig.update_layout(
        title="Rosa geométrica de pérdidas por estela",
        template="plotly_white",
        height=650,
        margin=dict(l=20, r=40, t=60, b=40),
        shapes=scale_shapes,
        annotations=scale_annotations,
        polar=dict(
            domain=dict(x=[0.18, 1.0]),
            angularaxis=dict(direction="clockwise", rotation=90, tickmode="array", tickvals=list(SECTOR_CENTERS_16), ticktext=SECTOR_LABELS_16),
            radialaxis=dict(showticklabels=False, range=[0, max_r], dtick=dtick, showline=False, gridcolor="rgba(148,163,184,0.3)"),
        ),
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_rosa_anual(df_resumen):
    import math
    max_val = df_resumen["Pérdida ponderada (%)"].max() if not df_resumen.empty else 1.0
    if pd.isna(max_val) or max_val == 0: max_val = 1.0
    if max_val <= 2: dtick = 0.5; max_r = math.ceil(max_val / 0.5) * 0.5
    elif max_val <= 5: dtick = 1.0; max_r = math.ceil(max_val / 1.0) * 1.0
    elif max_val <= 10: dtick = 2.0; max_r = math.ceil(max_val / 2.0) * 2.0
    else: dtick = 5.0; max_r = math.ceil(max_val / 5.0) * 5.0
    if max_r < dtick: max_r = dtick

    scale_shapes = [dict(type="line", xref="paper", yref="paper", x0=0.08, x1=0.08, y0=0.15, y1=0.85, line=dict(color="#cbd5e1", width=2))]
    scale_annotations = [dict(xref="paper", yref="paper", x=0.08, y=0.92, text="<b>Escala Radial</b><br><span style='font-size:9px'>(Pérdida)</span>", showarrow=False, font=dict(size=11, color="#64748b"), align="center")]
    
    vals = []
    v = 0.0
    while v <= max_r + 1e-9:
        vals.append(v)
        v += dtick
        
    for v in vals:
        y_pos = 0.15 + 0.7 * (v / max_r)
        scale_shapes.append(dict(type="line", xref="paper", yref="paper", x0=0.08, x1=0.10, y0=y_pos, y1=y_pos, line=dict(color="#cbd5e1", width=2)))
        scale_annotations.append(dict(xref="paper", yref="paper", x=0.065, y=y_pos, text=f"<b>{v:g}%</b>", showarrow=False, xanchor="right", yanchor="middle", font=dict(size=11, color="#475569")))

    fig = go.Figure()
    fig.add_trace(
        go.Barpolar(
            r=df_resumen["Pérdida ponderada (%)"],
            theta=df_resumen["Dirección centro (°)"],
            width=[22.5] * len(df_resumen),
            marker=dict(color=df_resumen["Pérdida por estela (%)"], colorscale="Blues", colorbar=dict(title="Pérdida sector (%)")),
            customdata=np.stack([df_resumen["Sector"], df_resumen["Frecuencia (%)"], df_resumen["Pérdida por estela (%)"], df_resumen["Velocidad media sector (m/s)"]], axis=1),
            hovertemplate="Sector: %{customdata[0]}<br>Pérdida ponderada: %{r:.3f}%<br>Frecuencia: %{customdata[1]:.2f}%<br>Pérdida sector: %{customdata[2]:.2f}%<br>Velocidad media: %{customdata[3]:.2f} m/s<extra></extra>",
            name="Pérdida anual ponderada",
        )
    )
    fig.update_layout(
        title="Rosa anual ponderada de pérdidas por estela",
        template="plotly_white",
        height=650,
        margin=dict(l=20, r=40, t=60, b=40),
        shapes=scale_shapes,
        annotations=scale_annotations,
        polar=dict(
            domain=dict(x=[0.18, 1.0]),
            angularaxis=dict(direction="clockwise", rotation=90, tickmode="array", tickvals=list(SECTOR_CENTERS_16), ticktext=SECTOR_LABELS_16),
            radialaxis=dict(showticklabels=False, range=[0, max_r], dtick=dtick, showline=False, gridcolor="rgba(148,163,184,0.3)"),
        ),
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_barras_energia_direccional(df_resumen):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_resumen["Sector"], y=df_resumen["Energía bruta (MWh/año)"], name="Bruta", marker_color="#2563EB"))
    fig.add_trace(go.Bar(x=df_resumen["Sector"], y=df_resumen["Energía con estela (MWh/año)"], name="Con estela", marker_color="#FF5A36"))
    fig.update_layout(
        title="Energía anual por dirección",
        template="plotly_white",
        barmode="group",
        height=500,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis_title="Sector",
        yaxis_title="Energía (MWh/año)",
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_barras_geom_vs_anual(df_geom, df_anual):
    df_plot = df_geom.merge(
        df_anual[["Sector", "Pérdida ponderada (%)"]],
        on="Sector",
        how="left"
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_plot["Sector"], y=df_plot["Pérdida geométrica (%)"], name="Geométrica (%)", marker_color="#2563EB"))
    fig.add_trace(go.Bar(x=df_plot["Sector"], y=df_plot["Pérdida ponderada (%)"], name="Anual ponderada (%)", marker_color="#FF5A36"))
    fig.update_layout(
        title="Comparación: criticidad geométrica vs criticidad anual",
        template="plotly_white",
        barmode="group",
        height=500,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis_title="Sector",
        yaxis_title="Pérdida (%)",
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_figura_comparacion_layouts(df_a, df_b, name_a, name_b):
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df_a["x_m"],
            y=df_a["y_m"],
            mode="markers+text",
            text=df_a["turbina_id"],
            textposition="top center",
            name=name_a,
            marker=dict(size=12),
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_b["x_m"],
            y=df_b["y_m"],
            mode="markers+text",
            text=df_b["turbina_id"],
            textposition="bottom center",
            name=name_b,
            marker=dict(size=12, symbol="diamond"),
        )
    )

    fig.update_layout(
        title="Comparación de configuraciones en planta",
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    fig.update_xaxes(title_text="X (m)", zeroline=True)
    fig.update_yaxes(title_text="Y (m)", scaleanchor="x", scaleratio=1, zeroline=True)
    return fig


def mover_turbina(df_layout, turbina_id, dx, dy):
    df = df_layout.copy()
    mask = df["turbina_id"] == turbina_id
    df.loc[mask, "x_m"] = pd.to_numeric(df.loc[mask, "x_m"], errors="coerce") + float(dx)
    df.loc[mask, "y_m"] = pd.to_numeric(df.loc[mask, "y_m"], errors="coerce") + float(dy)
    return df


def mover_parque(df_layout, dx, dy):
    df = df_layout.copy()
    df["x_m"] = pd.to_numeric(df["x_m"], errors="coerce") + float(dx)
    df["y_m"] = pd.to_numeric(df["y_m"], errors="coerce") + float(dy)
    return df


def rotar_parque(df_layout, angle_deg):
    df = df_layout.copy()
    x = pd.to_numeric(df["x_m"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df["y_m"], errors="coerce").to_numpy(dtype=float)

    cx = np.mean(x)
    cy = np.mean(y)

    xr = x - cx
    yr = y - cy

    ang = np.deg2rad(float(angle_deg))
    x_rot = xr * np.cos(ang) - yr * np.sin(ang)
    y_rot = xr * np.sin(ang) + yr * np.cos(ang)

    df["x_m"] = x_rot + cx
    df["y_m"] = y_rot + cy
    return df


def normalize_base_viento_for_energy(base_viento):
    value = str(normalizar_modelo_altura(base_viento) or "").strip()
    model_map = {
        "50 m": "50 m",
        "10 m": "10 m",
        "Exponencial": "Exponencial",
        "Log A (2 puntos)": "Log A (2 puntos)",
        PROMEDIO_LOG_EXP_LABEL: PROMEDIO_LOG_EXP_LABEL,
        "Altura deseada - Exponencial": "Exponencial",
        "Altura deseada - Log A (2 puntos)": "Log A (2 puntos)",
        "Altura deseada - Log B (z0 te\u00f3rica)": PROMEDIO_LOG_EXP_LABEL,
        "Altura deseada - Log B (z0 teórica)": PROMEDIO_LOG_EXP_LABEL,
        "Altura deseada - Promedio Log-Exp": PROMEDIO_LOG_EXP_LABEL,
    }
    return model_map.get(value, value)


@st.cache_data(show_spinner=False)
def construir_viento_analisis(df_nasa, base_viento, altura_deseada, roughness_label, direccion_altura):
    base_viento_normalizada = normalize_base_viento_for_energy(base_viento)
    model_map = {
        "50 m": "50 m",
        "10 m": "10 m",
        "Exponencial": "Exponencial",
        "Log A (2 puntos)": "Log A (2 puntos)",
        PROMEDIO_LOG_EXP_LABEL: PROMEDIO_LOG_EXP_LABEL,
        "Altura deseada - Exponencial": "Exponencial",
        "Altura deseada - Log A (2 puntos)": "Log A (2 puntos)",
        "Altura deseada - Log B (z0 teórica)": "Promedio Log-Exp",
        "Altura deseada - Promedio Log-Exp": "Promedio Log-Exp",
    }

    if base_viento_normalizada not in model_map:
        raise ValueError("Base de viento no reconocida.")

    df, meta = construir_serie_viento_analisis(
        df_nasa=df_nasa,
        modelo=model_map[base_viento_normalizada],
        altura_deseada=altura_deseada,
        roughness_label=roughness_label,
        direccion_fuente=direccion_altura,
        roughness_options=ROUGHNESS_OPTIONS,
        output_speed_col="WS_ANALISIS",
        output_direction_col="WD_ANALISIS",
    )

    if base_viento == "50 m":
        meta["descripcion"] = "Cálculo directo con WS50M y WD50M"
    elif base_viento == "10 m":
        meta["descripcion"] = "Cálculo directo con WS10M y WD10M"
    elif base_viento == "Altura deseada - Exponencial":
        meta["descripcion"] = "Extrapolación exponencial ajustada con 10 m y 50 m"
    elif base_viento == "Altura deseada - Log A (2 puntos)":
        meta["descripcion"] = "Extrapolación logarítmica ajustada con 10 m y 50 m"
    elif base_viento in ["Altura deseada - Log B (z0 teórica)", "Altura deseada - Promedio Log-Exp"]:
        meta["descripcion"] = "Extrapolación a altura deseada usando el promedio entre el perfil exponencial y el logarítmico A."

    return df, meta


def _normalize_base_viento_fase5(base_viento):
    return normalize_base_viento_for_energy(base_viento)


def _safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value):
    try:
        return int(float(value))
    except Exception:
        return None


def _same_float(a, b, tol=1e-6):
    av = _safe_float(a)
    bv = _safe_float(b)
    return av is not None and bv is not None and abs(av - bv) <= tol


def _fase5_stat_context_consistent(config):
    modo = str(config.get("f5_modo_estadistico", "") or "").strip()
    detalle = str(config.get("f5_metodo_detalle", "") or "").strip()

    if not modo:
        return False
    if modo == "Comparar Weibull y Rayleigh":
        return detalle in {"Weibull", "Rayleigh"}
    return detalle in {"", modo}


def _fase5_match_context(config, base_viento, dir_altura, roughness_label, n_turbinas, ct, kw, altura_deseada):
    roughness_saved = str(
        config.get("f5_roughness_label", config.get("f4_roughness_label", ""))
        or ""
    ).strip()
    roughness_input = str(roughness_label or "").strip()
    return (
        _normalize_base_viento_fase5(config.get("f5_base_viento")) == _normalize_base_viento_fase5(base_viento) and
        str(config.get("f5_dir_altura", "") or "").strip() == str(dir_altura or "").strip() and
        _safe_int(config.get("f5_n_turbinas")) == int(n_turbinas) and
        _same_float(config.get("f5_ct"), ct) and
        _same_float(config.get("f5_kw"), kw) and
        _same_float(config.get("f5_altura_deseada"), altura_deseada) and
        (not roughness_saved or roughness_saved == roughness_input) and
        _fase5_stat_context_consistent(config)
    )


def _resolve_energy_metrics(config, base_viento, dir_altura, roughness_label, n_turbinas, ct, kw, altura_deseada, energia_bruta_local, energia_wake_local):
    energia_bruta_f5 = _safe_float(config.get("f5_aep_bruta_total_mwh"))
    energia_wake_f5 = _safe_float(config.get("f5_aep_con_estela_total_mwh"))
    energia_perdida_f5 = _safe_float(config.get("f5_perdida_estela_total_mwh"))

    if (
        energia_bruta_f5 is not None and
        energia_wake_f5 is not None and
        _fase5_match_context(
            config=config,
            base_viento=base_viento,
            dir_altura=dir_altura,
            roughness_label=roughness_label,
            n_turbinas=n_turbinas,
            ct=ct,
            kw=kw,
            altura_deseada=altura_deseada,
        )
    ):
        return {
            "energia_bruta_mwh": energia_bruta_f5,
            "energia_wake_mwh": energia_wake_f5,
            "energia_perdida_mwh": energia_perdida_f5 if energia_perdida_f5 is not None else energia_bruta_f5 - energia_wake_f5,
            "note": "Mostrando energía autoritativa calculada en Fase 5.",
        }

    return {
        "energia_bruta_mwh": energia_bruta_local,
        "energia_wake_mwh": energia_wake_local,
        "energia_perdida_mwh": energia_bruta_local - energia_wake_local,
        "note": "Valor indicativo de Fase 4. Ejecute Fase 5 con esta misma base de viento para obtener la energía autoritativa.",
    }


@st.cache_data(show_spinner=False)
def analizar_geometria_16(df_layout, curva_df, diametro, ct, kw, velocidad_ref):
    filas = []
    detalles = {}

    for sector, center_deg in zip(SECTOR_LABELS_16, SECTOR_CENTERS_16):
        df_dir = calcular_estelas_jensen_direccion(
            df_layout=df_layout,
            wind_speed=float(velocidad_ref),
            direction_deg=float(center_deg),
            diametro=diametro,
            ct=ct,
            kw=kw,
            curva_df=curva_df,
        )

        p_base = float(df_dir["potencia_base_W"].sum())
        p_wake = float(df_dir["potencia_wake_W"].sum())

        if p_base > 0:
            loss_pct = 100.0 * (1.0 - p_wake / p_base)
            eff_pct = 100.0 * p_wake / p_base
        else:
            loss_pct = 0.0
            eff_pct = 100.0

        turbinas_afectadas = int((df_dir["deficit_total"] > 1e-8).sum())

        filas.append({
            "Sector": sector,
            "Dirección centro (°)": float(center_deg),
            "Velocidad referencia (m/s)": float(velocidad_ref),
            "Potencia parque sin estela (W)": p_base,
            "Potencia parque con estela (W)": p_wake,
            "Pérdida geométrica (%)": loss_pct,
            "Eficiencia geométrica (%)": eff_pct,
            "Turbinas afectadas": turbinas_afectadas,
        })

        detalles[sector] = df_dir.copy()

    return pd.DataFrame(filas), detalles


_render_phase4_css()
# FORZADO FINAL: aplicar acabado SMA 2.0 a los contenedores grandes y KPI de Fase 4
st.markdown(
    """
    <style>
    /* FORZADO FINAL: estilo SMA 2.0 para cards grandes y KPI en Fase 4 */
    .st-key-f4_card_config,
    .st-key-f4_card_edit_table,
    .st-key-f4_card_move_layout,
    .st-key-f4_card_view_layout,
    .st-key-f4_card_geom_summary,
    .st-key-f4_card_wind_base,
    .st-key-f4_card_geom_analysis,
    .st-key-f4_card_annual_analysis,
    .st-key-f4_card_detail_direction,
    .st-key-f4_card_scenarios,
    .st-key-f4_card_compare_bars,
    .st-key-f4_card_energy_bars,
    .st-key-f4_move_turbine_card,
    .st-key-f4_move_park_card,
    .st-key-f4_rotate_park_card,
    .st-key-f4_card_move_layout,
    .st-key-f4_top_kpi_1,
    .st-key-f4_top_kpi_2,
    .st-key-f4_top_kpi_3,
    .st-key-f4_top_kpi_4,
    .st-key-f4_top_kpi_5 {
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        border: 1.4px solid #cbd5e1 !important;
        border-radius: 28px !important;
        box-shadow:
            0 1px 4px rgba(15, 23, 42, 0.045),
            0 8px 22px rgba(15, 23, 42, 0.040) !important;
        overflow: visible !important;
        box-sizing: border-box !important;
    }

    .st-key-f4_card_config div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_edit_table div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_move_layout div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_view_layout div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_geom_summary div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_wind_base div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_geom_analysis div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_annual_analysis div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_detail_direction div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_scenarios div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_compare_bars div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_energy_bars div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_move_turbine_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_move_park_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_rotate_park_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_card_move_layout div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_top_kpi_1 div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_top_kpi_2 div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_top_kpi_3 div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_top_kpi_4 div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f4_top_kpi_5 div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        border-radius: 28px !important;
        padding: 1.02rem 1.08rem 1.08rem 1.08rem !important;
    }

    </style>
    """,
    unsafe_allow_html=True,
)
_render_page_hero()
st.markdown(
    """
    <div class="f4-info-banner">
        <span class="f4-info-banner__icon">i</span>
        <span>Esta fase ya guarda sus cambios. Ahora puede editar manualmente, mover turbinas, mover todo el parque, rotarlo, guardar escenarios y compararlos.</span>
    </div>
    """,
    unsafe_allow_html=True,
)

df_nasa = cargar_nasa_hourly()
df_curva = cargar_tabla_curva()
diametro = float(config.get("diametro") or 100.0)
altura_deseada_default = float(config.get("perfil_hhub") or 100.0)

if len(df_nasa) == 0:
    st.warning("Primero cargue datos horarios en la Fase 2.")
    st.stop()

layout_type_default = config.get("f4_layout_type", "En línea")
num_turbinas_default = int(float(config.get("f4_num_turbinas", "4")))
dx_D_default = float(config.get("f4_dx_D", "5.0"))
dy_D_default = float(config.get("f4_dy_D", "5.0"))
rotation_default = float(config.get("f4_rotation_deg", "0.0"))
ct_default = float(config.get("f4_ct", "0.80"))
kw_default = float(config.get("f4_kw", "0.05"))
sector_default = config.get("f4_selected_sector", "N")
base_viento_default = str(config.get("f4_base_viento", "50 m") or "50 m").strip()
if base_viento_default == "Altura deseada - Log B (z0 teórica)":
    base_viento_default = "Altura deseada - Promedio Log-Exp"
dir_altura_default = config.get("f4_dir_altura", "WD50M")
roughness_default = config.get("f4_roughness_label", "Grass / Césped")
geom_speed_default = float(config.get("f4_geom_speed", "8.0"))
selected_turbine_default = config.get("f4_selected_turbine", "")
velocidad_geom_state = float(st.session_state.get("f4_geom_speed", geom_speed_default))

TIPOS_ARREGLO = [
    "En línea",
    "En cruz",
    "Matriz rectangular",
    "Doble fila",
    "Tresbolillo",
    "Matriz triangular",
    "Diagonal",
    "Circular",
    "Arco",
    "Aleatorio controlado",
]

with st.container(border=True, key="f4_card_config"):
    _render_section_header("Configuración del arreglo", _icon_svg("controls", 22, "#0369a1"))
    with st.form("f4_layout_config_form", clear_on_submit=False):

        c1, c2, c3, c4 = st.columns(4, gap="medium")
        with c1:
            layout_type = st.selectbox(
                "Tipo de arreglo",
                TIPOS_ARREGLO,
                index=TIPOS_ARREGLO.index(layout_type_default)
                if layout_type_default in TIPOS_ARREGLO else 0,
            )
        with c2:
            num_turbinas = st.number_input("Número de aerogeneradores", min_value=1, value=num_turbinas_default, step=1)
        with c3:
            dx_D = st.number_input("Separación X (en D)", min_value=1.0, value=dx_D_default, step=0.5, format="%.2f")
        with c4:
            dy_D = st.number_input("Separación Y (en D)", min_value=1.0, value=dy_D_default, step=0.5, format="%.2f")

        c5, c6, c7, c8 = st.columns(4, gap="medium")
        with c5:
            rotation_deg = st.number_input("Rotación del arreglo (°)", value=rotation_default, step=5.0, format="%.2f")
        with c6:
            ct = st.number_input("Ct", min_value=0.01, max_value=0.99, value=ct_default, step=0.01, format="%.2f")
        with c7:
            kw = st.number_input("Constante de expansión kw", min_value=0.001, value=kw_default, step=0.005, format="%.3f")
        with c8:
            altura_deseada = st.number_input("Altura deseada (m)", min_value=0.10, value=altura_deseada_default, step=0.10, format="%.2f")

        dx_m_preview = dx_D * diametro
        dy_m_preview = dy_D * diametro
        action_cols = st.columns(2, gap="medium")
        with action_cols[0]:
            if st.form_submit_button("Generar arreglo automático", icon=":material/autorenew:", use_container_width=True, key="f4_btn_generar"):
                df_layout_new = generar_layout_parque(layout_type, num_turbinas, dx_m_preview, dy_m_preview, rotation_deg)
                guardar_layout_parque(df_layout_new)
                st.success("Arreglo generado.")
                st.rerun()
        with action_cols[1]:
            if st.form_submit_button("Recargar layout guardado", icon=":material/restore:", use_container_width=True, key="f4_btn_recargar"):
                st.rerun()

# Widget values persisted in session_state. Config saves removed.

dx_m = dx_D * diametro
dy_m = dy_D * diametro

df_layout_db = cargar_layout_parque()
if len(df_layout_db) == 0:
    df_layout_db = generar_layout_parque(layout_type, num_turbinas, dx_m, dy_m, rotation_deg)
    guardar_layout_parque(df_layout_db)

df_layout = cargar_layout_parque()
if len(df_layout) == 0:
    df_layout = df_layout_db.copy()

try:
    f4_geom_signature = (
        _df_signature(df_layout),
        _df_signature(df_curva),
        float(diametro),
        float(ct),
        float(kw),
        float(velocidad_geom_state),
    )
    resumen_geom, detalles_geom = _session_cached_result(
        "f4_geometria_16",
        f4_geom_signature,
        lambda: analizar_geometria_16(
            df_layout=df_layout,
            curva_df=df_curva,
            diametro=diametro,
            ct=ct,
            kw=kw,
            velocidad_ref=velocidad_geom_state,
        ),
    )
except Exception as e:
    st.error(f"No pude calcular la criticidad geométrica: {e}")
    st.stop()

geom_loss_col = _find_geom_loss_column(resumen_geom)
if geom_loss_col is None:
    st.error("No pude localizar la columna de p?rdida geom?trica en el resumen del arreglo.")
    st.stop()
geom_loss_series = pd.to_numeric(resumen_geom[geom_loss_col], errors="coerce").fillna(0.0)
max_geom = float(geom_loss_series.max())
sectores_geom_criticos = resumen_geom.loc[
    np.abs(geom_loss_series - max_geom) <= 1e-4,
    "Sector"
].tolist()
eficiencia_geom = max(0.0, 100.0 - max_geom)
main_base_viento = st.session_state.get("f4_base_viento", base_viento_default)
main_dir_altura = st.session_state.get("f4_dir_altura", dir_altura_default)
main_sector_visual_df, main_sector_visual_meta = _build_main_park_sector_visual_data(
    df_nasa=df_nasa,
    base_viento=main_base_viento,
    altura_deseada=altura_deseada,
    roughness_label=roughness_default,
    direccion_altura=main_dir_altura,
    curva_df=df_curva,
    fallback_speed=velocidad_geom_state,
)

kpi_top = st.columns(5, gap="small")
with kpi_top[0]:
    with st.container(border=True, key="f4_top_kpi_1"):
        icon_aero = "<svg xmlns='http://www.w3.org/2000/svg' width='30' height='30' viewBox='0 0 24 24' fill='none' stroke='#0B63F6' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M12 12v10'/><path d='M12 12Q10.5 8 12 3Q13.5 8 12 12'/><path d='M12 12Q16.2 12.7 19.8 16.5Q14.7 15.3 12 12'/><path d='M12 12Q9.3 15.3 4.2 16.5Q7.8 12.7 12 12'/><circle cx='12' cy='12' r='1.5' fill='#0B63F6'/></svg>"
        _render_kpi_card("Aerogeneradores", f"{len(df_layout)}", "Total en el parque", icon=icon_aero, class_name="f4-top-kpi-card")
with kpi_top[1]:
    with st.container(border=True, key="f4_top_kpi_2"):
        icon_diam = "<svg xmlns='http://www.w3.org/2000/svg' width='30' height='30' viewBox='0 0 24 24' fill='none' stroke='#0B63F6' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'/><path d='M12 5.5v0 M12 18.5v0 M5.5 12h0 M18.5 12h0'/><circle cx='12' cy='12' r='1.5' fill='#0B63F6'/><path d='M12 12V7.5'/></svg>"
        _render_kpi_card("Diámetro rotor (m)", f"{diametro:.1f}", "Referencia del modelo", icon=icon_diam, class_name="f4-top-kpi-card")
with kpi_top[2]:
    with st.container(border=True, key="f4_top_kpi_3"):
        icon_vel = "<svg xmlns='http://www.w3.org/2000/svg' width='30' height='30' viewBox='0 0 24 24' fill='none' stroke='#0B63F6' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M12.8 19.6A2 2 0 1 0 14 16H2'/><path d='M17.5 8a2.5 2.5 0 1 1 2 4H2'/><path d='M9.8 4.4A2 2 0 1 1 11 8H2'/></svg>"
        _render_kpi_card("Velocidad geométrica", f"{velocidad_geom_state:.2f} m/s", "Para el análisis geométrico", icon=icon_vel, class_name="f4-top-kpi-card")
with kpi_top[3]:
    with st.container(border=True, key="f4_top_kpi_4"):
        icon_sector = "<svg xmlns='http://www.w3.org/2000/svg' width='30' height='30' viewBox='0 0 24 24' fill='none' stroke='#0B63F6' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10' opacity='0.2'/><path d='M12 3v18M3 12h18'/></svg>"
        _render_kpi_card("Sector crítico", ", ".join(sectores_geom_criticos), "Sectores geométricamente críticos", icon=icon_sector, class_name="f4-top-kpi-card")
with kpi_top[4]:
    with st.container(border=True, key="f4_top_kpi_5"):
        icon_efic = "<svg xmlns='http://www.w3.org/2000/svg' width='30' height='30' viewBox='0 0 24 24' fill='none' stroke='#0B63F6' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><circle cx='12' cy='12' r='10'/><path d='M8 12l3 3 5-6'/></svg>"
        _render_kpi_card("Eficiencia geométrica", f"{eficiencia_geom:.2f}%", "Eficiencia del arreglo", icon=icon_efic, class_name="f4-top-kpi-card")

layout_edit_cols = st.columns([1.05, 1.15], gap="small")
with layout_edit_cols[0]:
    with st.container(border=True, key="f4_card_edit_table", height=435):
        st.markdown(
            """
            <style>
            /* ── Twin-card symmetry (Structural height applied via python) ── */
            .st-key-f4_card_edit_table > div[data-testid="stVerticalBlock"],
            .st-key-f4_card_move_layout > div[data-testid="stVerticalBlock"],
            div.st-key-f4_card_edit_table[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"],
            div.st-key-f4_card_move_layout[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
                display: flex !important;
                flex-direction: column !important;
                justify-content: space-between !important;
            }
            /* ────────────────────────────────────────────────────────────── */
            .st-key-f4_card_edit_table {
                background: #ffffff !important;
                border: 1px solid #c9dcff !important;
                border-radius: 20px !important;
                box-shadow: 0 4px 14px rgba(37, 99, 235, 0.05) !important;
            }
            .st-key-f4_card_edit_table div[data-testid="stVerticalBlockBorderWrapper"] {
                padding: 1.2rem 1.4rem !important;
            }
            .st-key-f4_card_edit_table .f4-section-title {
                margin-bottom: 1rem !important;
            }
            .st-key-f4_card_edit_table .f4-section-title__icon {
                width: 2.8rem !important;
                height: 2.8rem !important;
                border-radius: 999px !important;
                background: #eef5ff !important;
                border: 1px solid #cbd5e1 !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                box-shadow: inset 0 2px 4px rgba(255,255,255,0.8) !important;
            }
            .st-key-f4_card_edit_table .f4-section-title__icon svg {
                width: 1.5rem !important;
                height: 1.5rem !important;
                stroke: #1d4ed8 !important;
            }
            .st-key-f4_card_edit_table .f4-section-title__text {
                color: #10224f !important;
                font-size: 1.25rem !important;
                font-weight: 800 !important;
            }
            .st-key-f4_card_edit_table [data-testid="stDataFrame"],
            .st-key-f4_card_edit_table [data-testid="stDataEditor"] {
                min-height: auto !important;
                border: 1px solid #cbd5e1 !important;
                border-radius: 16px !important;
                overflow: hidden !important;
            }
            .st-key-f4_card_edit_table th {
                background: #f4f8fc !important;
                color: #1e3a8a !important;
                font-weight: 800 !important;
                font-size: 0.9rem !important;
                border-bottom: 1px solid #dbeafe !important;
            }
            .st-key-f4_card_edit_table td {
                color: #0f172a !important;
                font-weight: 700 !important;
                font-size: 0.95rem !important;
                border-bottom: 1px solid #eff6ff !important;
            }
            .st-key-f4_card_edit_table .stButton > button {
                background: #ffffff !important;
                border: 1px solid #bfdbfe !important;
                border-radius: 14px !important;
                color: #1d4ed8 !important;
                font-weight: 800 !important;
                font-size: 1.05rem !important;
                min-height: 3.2rem !important;
                box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04) !important;
                transition: all 0.2s ease !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                gap: 0.6rem !important;
                margin-top: 0.8rem !important;
            }
            .st-key-f4_card_edit_table .stButton > button:hover {
                background: #eff6ff !important;
                border-color: #3b82f6 !important;
            }
            .st-key-f4_card_edit_table .stButton > button .material-symbols-rounded {
                font-size: 1.5rem !important;
                color: #2563eb !important;
                font-weight: 600 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        
        icon_table = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><rect x='3' y='3' width='18' height='18' rx='2' ry='2'/><line x1='3' y1='9' x2='21' y2='9'/><line x1='9' y1='9' x2='9' y2='21'/><line x1='15' y1='9' x2='15' y2='21'/></svg>"
        _render_section_header("Tabla editable del parque", icon_table)
        edited_layout = st.data_editor(
            df_layout.copy(),
            num_rows="dynamic",
            use_container_width=True,
            key="f4_layout_editor_v4",
            height=240,
        )

        if st.button("Guardar tabla del parque", icon=":material/save:", use_container_width=True):
            try:
                df_save = edited_layout.copy()
                df_save["turbina_id"] = df_save["turbina_id"].astype(str).str.strip()
                df_save["x_m"] = pd.to_numeric(df_save["x_m"], errors="coerce")
                df_save["y_m"] = pd.to_numeric(df_save["y_m"], errors="coerce")
                df_save = df_save.dropna(subset=["turbina_id", "x_m", "y_m"]).copy()

                if len(df_save) == 0:
                    raise ValueError("La tabla quedó vacía.")

                guardar_layout_parque(df_save[["turbina_id", "x_m", "y_m"]])
                guardar_config_values({"f4_num_turbinas": len(df_save)})
                st.success("Tabla guardada.")
                st.rerun()
            except Exception as e:
                st.error(f"No pude guardar la tabla: {e}")

df_layout = cargar_layout_parque()

with layout_edit_cols[1]:
    with st.container(border=True, key="f4_card_move_layout", height=435):
        st.markdown(
            """
            <style>
            .st-key-f4_card_move_layout {
                background: #ffffff !important;
                border: 1px solid #c9dcff !important;
                border-radius: 20px !important;
                box-shadow: 0 4px 14px rgba(37, 99, 235, 0.05) !important;
            }
            .st-key-f4_card_move_layout div[data-testid="stVerticalBlockBorderWrapper"] {
                padding: 1.2rem 1.4rem !important;
            }
            .st-key-f4_card_move_layout .f4-section-title {
                margin-bottom: 1.2rem !important;
                display: flex !important;
                align-items: center !important;
                gap: 0.8rem !important;
            }
            .st-key-f4_card_move_layout .f4-section-title__icon {
                width: 2.8rem !important;
                height: 2.8rem !important;
                border-radius: 999px !important;
                background: #eef5ff !important;
                border: 1px solid #cbd5e1 !important;
                display: inline-flex !important;
                align-items: center !important;
                justify-content: center !important;
                box-shadow: inset 0 2px 4px rgba(255,255,255,0.8) !important;
            }
            .st-key-f4_card_move_layout .f4-section-title__icon svg {
                width: 1.5rem !important;
                height: 1.5rem !important;
                stroke: #1d4ed8 !important;
            }
            .st-key-f4_card_move_layout .f4-section-title__text {
                color: #10224f !important;
                font-size: 1.25rem !important;
                font-weight: 800 !important;
            }
            .st-key-f4_card_move_layout label,
            .st-key-f4_card_move_layout [data-testid="stWidgetLabel"],
            .st-key-f4_card_move_layout [data-testid="stWidgetLabel"] p,
            .st-key-f4_card_move_layout [data-testid="stWidgetLabel"] span {
                font-weight: 800 !important;
                color: #1e293b !important;
                font-size: 0.88rem !important;
            }
            /* ── Selectbox ── */
            .st-key-f4_card_move_layout [data-baseweb="select"] > div {
                background: #ffffff !important;
                border: 1px solid #bfdbfe !important;
                border-radius: 14px !important;
                min-height: 46px !important;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.98), 0 1px 2px rgba(15,23,42,0.02) !important;
                align-items: center !important;
            }
            .st-key-f4_card_move_layout [data-baseweb="select"] span {
                font-weight: 800 !important;
                color: #0f172a !important;
            }
            /* ── Number inputs — mismo patrón que f4_card_config ── */
            .st-key-f4_card_move_layout [data-baseweb="input"],
            .st-key-f4_card_move_layout [data-testid="stNumberInput"] [data-baseweb="input"] {
                background: #ffffff !important;
                border: 1px solid #bfdbfe !important;
                border-radius: 14px !important;
                min-height: 46px !important;
                display: flex !important;
                align-items: center !important;
                overflow: hidden !important;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.98), 0 1px 2px rgba(15,23,42,0.02) !important;
            }
            .st-key-f4_card_move_layout [data-baseweb="input"] > div,
            .st-key-f4_card_move_layout [data-baseweb="input"] input {
                background: #ffffff !important;
                color: #0f172a !important;
            }
            /* divisor input/stepper */
            .st-key-f4_card_move_layout [data-testid="stNumberInput"] [data-baseweb="input"] > div:last-child {
                background: #ffffff !important;
                border-left: 1px solid #dbeafe !important;
            }
            /* valor en negrilla */
            .st-key-f4_card_move_layout [data-testid="stNumberInput"] input {
                background: #ffffff !important;
                padding-left: 0.8rem !important;
                font-weight: 800 !important;
                color: #0f172a !important;
            }
            /* botones + y - — idénticos a f4_card_config */
            .st-key-f4_card_move_layout [data-baseweb="input"] button {
                color: #0f172a !important;
                background: #ffffff !important;
                border-radius: 10px !important;
                border: 1px solid #eef2f7 !important;
                min-width: 2.35rem !important;
                font-weight: 800 !important;
                font-size: 1.05rem !important;
            }
            .st-key-f4_card_move_layout [data-testid="stNumberInput"] button {
                background: #ffffff !important;
                border-left: 1px solid #dbeafe !important;
                color: #0f172a !important;
                min-width: 2.35rem !important;
                font-weight: 800 !important;
                font-size: 1.05rem !important;
            }
            .st-key-f4_card_move_layout [data-testid="stNumberInput"] button:hover,
            .st-key-f4_card_move_layout [data-baseweb="input"] button:hover {
                background: #eff6ff !important;
                color: #1d4ed8 !important;
            }
            .st-key-f4_move_turbine_card,
            .st-key-f4_move_park_card,
            .st-key-f4_rotate_park_card {
                border-radius: 16px !important;
            }
            .st-key-f4_move_turbine_card,
            .st-key-f4_move_park_card {
                background: #ffffff !important;
                border: 1px solid #cbd5e1 !important;
                box-shadow: 0 2px 8px rgba(37, 99, 235, 0.04) !important;
            }
            .st-key-f4_rotate_park_card {
                background: #f0fdf4 !important;
                border: 1px solid #bbf7d0 !important;
                box-shadow: 0 2px 8px rgba(34, 197, 94, 0.04) !important;
            }
            /* ── Subcards (Structural height applied via python) ── */
            div[data-testid="stVerticalBlockBorderWrapper"]:has(> div.st-key-f4_move_turbine_card),
            div[data-testid="stVerticalBlockBorderWrapper"]:has(> div.st-key-f4_move_park_card),
            div[data-testid="stVerticalBlockBorderWrapper"]:has(> div.st-key-f4_rotate_park_card),
            div.st-key-f4_move_turbine_card[data-testid="stVerticalBlockBorderWrapper"],
            div.st-key-f4_move_park_card[data-testid="stVerticalBlockBorderWrapper"],
            div.st-key-f4_rotate_park_card[data-testid="stVerticalBlockBorderWrapper"] {
                padding: 1rem 0.8rem !important;
                box-sizing: border-box !important;
            }
            .st-key-f4_rotate_park_card > div[data-testid="stVerticalBlock"],
            div.st-key-f4_rotate_park_card[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
                display: flex !important;
                flex-direction: column !important;
                align-items: center !important;
                justify-content: center !important;
                height: 100% !important;
                gap: 0.5rem !important;
            }
            /* ── Desplazamiento y compresión vertical interna para los 3 subcards ── */
            .st-key-f4_move_turbine_card > div[data-testid="stVerticalBlock"],
            .st-key-f4_move_park_card > div[data-testid="stVerticalBlock"],
            .st-key-f4_rotate_park_card > div[data-testid="stVerticalBlock"],
            div.st-key-f4_move_turbine_card[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"],
            div.st-key-f4_move_park_card[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"],
            div.st-key-f4_rotate_park_card[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
                transform: translateY(-12px) !important;
            }
            .st-key-f4_move_turbine_card > div[data-testid="stVerticalBlock"],
            .st-key-f4_move_park_card > div[data-testid="stVerticalBlock"],
            div.st-key-f4_move_turbine_card[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"],
            div.st-key-f4_move_park_card[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
                gap: 0.15rem !important;
            }
            .st-key-f4_move_turbine_card .f4-move-subcard-title,
            .st-key-f4_move_park_card .f4-move-subcard-title {
                color: #1d4ed8 !important;
                font-weight: 800 !important;
                font-size: 0.95rem !important;
                text-align: center !important;
                margin-bottom: 0.1rem !important;
            }
            .st-key-f4_rotate_park_card .f4-move-subcard-title {
                color: #16a34a !important;
                font-weight: 800 !important;
                font-size: 0.95rem !important;
                text-align: center !important;
                margin-bottom: 0.1rem !important;
            }
            .st-key-f4_rotate_park_card [data-testid="stHorizontalBlock"] {
                transform: translateY(55px) !important;
            }
            .st-key-f4_move_turbine_card .stButton > button,
            .st-key-f4_move_park_card .stButton > button {
                background: #ffffff !important;
                border: 1px solid #c9dcff !important;
                border-radius: 12px !important;
                color: #2563eb !important;
                font-weight: 800 !important;
                font-size: 26px !important;
                height: 48px !important;
                min-height: 48px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                box-shadow: 0 2px 6px rgba(37,99,235,0.06) !important;
                padding: 0 !important;
                line-height: 1 !important;
                max-width: 76px !important;
                margin: 0 auto !important;
            }
            .st-key-f4_move_turbine_card .stButton > button:hover,
            .st-key-f4_move_park_card .stButton > button:hover {
                background: #eff6ff !important;
                border-color: #93c5fd !important;
            }
            .st-key-f4_rotate_park_card .stButton > button {
                background: #ffffff !important;
                border: 1px solid #86efac !important;
                border-radius: 12px !important;
                color: #16a34a !important;
                font-weight: 800 !important;
                font-size: 24px !important;
                height: 54px !important;
                min-height: 54px !important;
                width: 100% !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                box-shadow: 0 2px 6px rgba(34,197,94,0.06) !important;
                padding: 0 0.6rem !important;
                line-height: 1 !important;
                margin: 0 !important;
                gap: 0.4rem !important;
            }
            .st-key-f4_rotate_park_card .stButton > button:hover {
                background: #f0fdf4 !important;
                border-color: #4ade80 !important;
            }

            </style>
            """,
            unsafe_allow_html=True,
        )

        icon_move = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M5 9l-3 3 3 3M9 5l3-3 3 3M19 9l3 3-3 3M9 19l3 3 3-3M2 12h20M12 2v20'/></svg>"
        _render_section_header("Mover turbinas y parque", icon_move)

        if len(df_layout) > 0:
            turbine_options = df_layout["turbina_id"].astype(str).tolist()
            if selected_turbine_default not in turbine_options:
                selected_turbine_default = turbine_options[0]

            _init_widget_state("f4_selected_turbine", selected_turbine_default)

            m1, m2, m3, m4 = st.columns(4, gap="small")
            with m1:
                turbina_sel = st.selectbox(
                    "Turbina seleccionada",
                    turbine_options,
                    index=turbine_options.index(selected_turbine_default),
                    key="f4_selected_turbine",
                )
            with m2:
                move_step_turb = st.number_input("Paso mover turbina (m)", min_value=1.0, value=50.0, step=10.0, format="%.2f")
            with m3:
                move_step_park = st.number_input("Paso mover parque (m)", min_value=1.0, value=100.0, step=10.0, format="%.2f")
            with m4:
                rotate_step = st.number_input("Paso rotación (°)", value=5.0, step=1.0, format="%.2f")

            _cur_sel_turb = st.session_state.get("f4_selected_turbine", selected_turbine_default)
            if st.session_state.get("_f4_last_saved_turbine") != _cur_sel_turb:
                guardar_config_values({"f4_selected_turbine": _cur_sel_turb})
                st.session_state["_f4_last_saved_turbine"] = _cur_sel_turb

            move_cards = st.columns(3, gap="small")
            with move_cards[0]:
                with st.container(border=True, key="f4_move_turbine_card", height=235):
                    st.markdown('<div class="f4-move-subcard-title">Mover turbina</div>', unsafe_allow_html=True)
                    top_l, top_c, top_r = st.columns(3, gap="small")
                    with top_c:
                        if st.button("↑", use_container_width=True, key="f4_move_turbine_up"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, 0, move_step_turb))
                            st.rerun()
                    mid_l, mid_c, mid_r = st.columns(3, gap="small")
                    with mid_l:
                        if st.button("←", use_container_width=True, key="f4_move_turbine_left"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, -move_step_turb, 0))
                            st.rerun()
                    with mid_r:
                        if st.button("→", use_container_width=True, key="f4_move_turbine_right"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, move_step_turb, 0))
                            st.rerun()
                    bot_l, bot_c, bot_r = st.columns(3, gap="small")
                    with bot_c:
                        if st.button("↓", use_container_width=True, key="f4_move_turbine_down"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, 0, -move_step_turb))
                            st.rerun()
            with move_cards[1]:
                with st.container(border=True, key="f4_move_park_card", height=235):
                    st.markdown('<div class="f4-move-subcard-title">Mover parque</div>', unsafe_allow_html=True)
                    top_l, top_c, top_r = st.columns(3, gap="small")
                    with top_c:
                        if st.button("↑", use_container_width=True, key="f4_move_park_up"):
                            guardar_layout_parque(mover_parque(df_layout, 0, move_step_park))
                            st.rerun()
                    mid_l, mid_c, mid_r = st.columns(3, gap="small")
                    with mid_l:
                        if st.button("←", use_container_width=True, key="f4_move_park_left"):
                            guardar_layout_parque(mover_parque(df_layout, -move_step_park, 0))
                            st.rerun()
                    with mid_r:
                        if st.button("→", use_container_width=True, key="f4_move_park_right"):
                            guardar_layout_parque(mover_parque(df_layout, move_step_park, 0))
                            st.rerun()
                    bot_l, bot_c, bot_r = st.columns(3, gap="small")
                    with bot_c:
                        if st.button("↓", use_container_width=True, key="f4_move_park_down"):
                            guardar_layout_parque(mover_parque(df_layout, 0, -move_step_park))
                            st.rerun()
            with move_cards[2]:
                with st.container(border=True, key="f4_rotate_park_card", height=235):
                    st.markdown('<div class="f4-move-subcard-title">Rotar parque</div>', unsafe_allow_html=True)
                    rot_l, rot_r = st.columns(2, gap="small")
                    with rot_l:
                        if st.button("↺ -", use_container_width=True, key="f4_rotate_park_minus"):
                            guardar_layout_parque(rotar_parque(df_layout, -rotate_step))
                            st.rerun()
                    with rot_r:
                        if st.button("↻ +", use_container_width=True, key="f4_rotate_park_plus"):
                            guardar_layout_parque(rotar_parque(df_layout, rotate_step))
                            st.rerun()



df_layout = cargar_layout_parque()

st.markdown("""
<style>
.f4-after-top-row-spacer {
    height: 6px !important;
    min-height: 6px !important;
    width: 100%;
    display: block;
}
</style>
<div class="f4-after-top-row-spacer"></div>
""", unsafe_allow_html=True)

view_cols = st.columns([2.7, 0.9], gap="medium")
with view_cols[0]:
    with st.container(border=True, key="f4_card_view_layout"):
        st.markdown(
            f"""
            <div class="f4-panel-hero__top">
                <div>
                    <div class="f4-section-title" style="margin-bottom:0.2rem;">
                        <span class="f4-section-title__icon">{_icon_svg("waves", 22, "#0B63F6")}</span>
                        <span class="f4-section-title__text">Vista del parque y efecto de estela</span>
                    </div>
                    <div class="f4-panel-hero__subtitle">(vista en planta)</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        geom_sector_df_for_park = resumen_geom[["Sector", geom_loss_col]].copy()
        fig_layout = crear_figura_layout_parque(df_layout=df_layout, diametro=diametro, titulo="")
        fig_layout = _enhance_main_park_figure(
            fig_layout,
            df_layout,
            direction_deg=float(main_sector_visual_meta["dominant_deg"]),
            direction_label=str(main_sector_visual_meta["dominant_label"]),
            sector_visual_df=main_sector_visual_df,
            geom_sector_df=geom_sector_df_for_park,
        )
        fig_layout.update_layout(
            title=None,
            height=610,
            margin=dict(l=44, r=28, t=20, b=90),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f8fbff",
            showlegend=False,
            xaxis=dict(
                title=dict(text="X (m)", font=dict(size=13, color="#475569")),
                showgrid=True,
                gridcolor="rgba(148,163,184,0.20)",
                gridwidth=1,
                zeroline=True,
                zerolinecolor="rgba(148,163,184,0.35)",
                zerolinewidth=1,
                tickfont=dict(size=11, color="#64748b"),
            ),
            yaxis=dict(
                title=dict(text="Y (m)", font=dict(size=13, color="#475569")),
                showgrid=True,
                gridcolor="rgba(148,163,184,0.20)",
                gridwidth=1,
                zeroline=True,
                zerolinecolor="rgba(148,163,184,0.35)",
                zerolinewidth=1,
                tickfont=dict(size=11, color="#64748b"),
                scaleanchor="x",
                scaleratio=1,
            ),
            annotations=[
                # Wind-direction compass badge (top-left, inside plot area)
                dict(
                    xref="paper", yref="paper",
                    x=0.01, y=0.99,
                    xanchor="left", yanchor="top",
                    text=(
                        "<b style='font-size:13px;color:#1e3a8a;'>↗ Viento N (0°)</b>"
                    ),
                    showarrow=False,
                    align="left",
                    bgcolor="rgba(239,246,255,0.88)",
                    bordercolor="#bfdbfe",
                    borderwidth=1,
                    borderpad=5,
                    font=dict(size=12, color="#1d4ed8"),
                ),
            ],
        )
        fig_layout = _style_main_park_figure(fig_layout)
        plot_config = {
            "displayModeBar": True,
            "displaylogo": False,
            "responsive": True,
            "modeBarButtonsToRemove": [
                "lasso2d", "select2d",
            ],
        }
        components.html(
            _cached_park_html(
                fig=fig_layout,
                df_layout=df_layout,
                wind_speed=float(main_sector_visual_meta["representative_speed"]),
                curva_df=df_curva,
                plot_config=plot_config,
                direction_deg=float(main_sector_visual_meta["dominant_deg"]),
            ),
            height=int(fig_layout.layout.height or 610) + 6,
            scrolling=False,
        )
        st.markdown(
            """
            <div style="display:flex;align-items:center;gap:0.9rem;margin:0.35rem 0 0.1rem 0;padding:0.48rem 0.7rem;border: 1px solid #cbd5e1;border-radius:12px;background:#fbfdff;color:#475569;font-size:0.82rem;font-weight:700;">
                <span style="color:#0f172a;font-weight:800;">Afectación local por estela</span>
                <span style="display:inline-flex;align-items:center;gap:0.32rem;"><i style="width:10px;height:10px;border-radius:999px;background:#10B981;display:inline-block;"></i>Verde: Baja</span>
                <span style="display:inline-flex;align-items:center;gap:0.32rem;"><i style="width:10px;height:10px;border-radius:999px;background:#F59E0B;display:inline-block;"></i>Naranja: Media</span>
                <span style="display:inline-flex;align-items:center;gap:0.32rem;"><i style="width:10px;height:10px;border-radius:999px;background:#EF4444;display:inline-block;"></i>Rojo: Alta</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

with view_cols[1]:
    with st.container(border=True, key="f4_card_geom_summary"):
        _render_section_header("Resumen geométrico del arreglo", "◎")
        _render_summary_item("Número de aerogeneradores", f"{len(df_layout)}")
        _render_summary_item("Separación X (en D)", f"{dx_D:.2f}")
        _render_summary_item("Separación Y (en D)", f"{dy_D:.2f}")
        _render_summary_item("Rotación del arreglo (°)", f"{rotation_deg:.2f}")
        _render_summary_item("Ct", f"{ct:.2f}")
        _render_summary_item("Constante de expansión kw", f"{kw:.3f}")
        _render_summary_item("Altura deseada (m)", f"{altura_deseada:.2f}")
        _render_summary_item("Velocidad geométrica", f"{velocidad_geom_state:.2f} m/s")
        _render_summary_item("Eficiencia geométrica", f"{eficiencia_geom:.2f}%")
        _render_summary_item("Sectores críticos", ", ".join(sectores_geom_criticos))
        st.button("Exportar vista", use_container_width=True, key="f4_btn_exportar_vista_layout")

with st.container(border=True, key="f4_card_wind_base"):
    _render_section_header("Base de viento para el análisis anual", _icon_svg("waves", 24, "#0B63F6"))
    with st.form("f4_wind_base_form", clear_on_submit=False):

        # Initialize widget state before creating widgets
        _init_widget_state("f4_base_viento", base_viento_default)
        _init_widget_state("f4_dir_altura", dir_altura_default)
        _init_widget_state("f4_geom_speed", geom_speed_default)

        v1, v2, v3, v4 = st.columns(4, gap="medium")
        with v1:
            base_viento = st.selectbox(
                "Base de viento anual",
                ["50 m", "10 m", "Altura deseada - Exponencial", "Altura deseada - Log A (2 puntos)", "Altura deseada - Promedio Log-Exp"],
                index=["50 m", "10 m", "Altura deseada - Exponencial", "Altura deseada - Log A (2 puntos)", "Altura deseada - Promedio Log-Exp"].index(base_viento_default)
                if base_viento_default in ["50 m", "10 m", "Altura deseada - Exponencial", "Altura deseada - Log A (2 puntos)", "Altura deseada - Promedio Log-Exp"] else 0,
                key="f4_base_viento",
            )
        with v2:
            dir_altura = st.selectbox(
                "Dirección usada cuando hay altura deseada",
                ["WD50M", "WD10M"],
                index=0 if dir_altura_default == "WD50M" else 1,
                key="f4_dir_altura",
            )
        with v3:
            st.markdown('<div class="f4-inline-caption">Promedio Log-Exp = promedio entre Exponencial y Log A.</div>', unsafe_allow_html=True)
            roughness_label = roughness_default
        with v4:
            velocidad_geom = st.number_input(
                "Velocidad para análisis geométrico (m/s)",
                min_value=0.10,
                value=geom_speed_default,
                step=0.10,
                format="%.2f",
                key="f4_geom_speed",
            )

        st.form_submit_button("Actualizar análisis anual", use_container_width=True)
    # Persist widget values to database (reads from session_state via keys)
    guardar_config_values({
        "f4_base_viento": st.session_state.get("f4_base_viento", base_viento_default),
        "f4_base_viento_canonica": energia_calc.normalize_base_viento_for_energy(st.session_state.get("f4_base_viento", base_viento_default)),
        "f4_dir_altura": st.session_state.get("f4_dir_altura", dir_altura_default),
        "f4_roughness_label": roughness_label,
        "f4_geom_speed": st.session_state.get("f4_geom_speed", geom_speed_default),
    })

    try:
        df_viento_analisis, meta_viento = construir_viento_analisis(
            df_nasa=df_nasa,
            base_viento=base_viento,
            altura_deseada=altura_deseada,
            roughness_label=roughness_label,
            direccion_altura=dir_altura,
        )
    except Exception as e:
        st.error(f"No pude construir la base de viento: {e}")
        st.stop()



    wind_metrics = []
    if meta_viento["parametro_1_nombre"]:
        v = meta_viento["parametro_1_valor"]
        wind_metrics.append((meta_viento["parametro_1_nombre"], f"{v:.4f}" if pd.notna(v) else "N/A", "Parámetro derivado"))
    if meta_viento["parametro_2_nombre"]:
        v = meta_viento["parametro_2_valor"]
        wind_metrics.append((meta_viento["parametro_2_nombre"], f"{v:.6f}" if pd.notna(v) else "N/A", "Parámetro derivado"))
    wind_metrics.append(("Base canónica", energia_calc.normalize_base_viento_for_energy(base_viento), "Motor anual compartido"))

    wind_metric_cols = st.columns(3, gap="medium")
    for idx, col in enumerate(wind_metric_cols):
        if idx >= len(wind_metrics):
            continue
        label, value, caption = wind_metrics[idx]
        with col:
            with st.container(border=True, key=f"f4_wind_metric_{idx + 1}"):
                st.markdown(
                    textwrap.dedent(
                        f"""
                        <div class="f4-kpi-html">
                            <div class="f4-kpi-html__label">{label}</div>
                            <div class="f4-kpi-html__value">{value}</div>
                            <div class="f4-kpi-html__caption">{caption}</div>
                        </div>
                        """
                    ).strip(),
                    unsafe_allow_html=True,
                )

with st.container(border=True, key="f4_card_geom_analysis"):
    _render_section_header("Análisis geométrico puro del arreglo", '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0B63F6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3L3 21h18L12 3z"/><path d="M12 3v18"/><path d="M3 21l9-9"/></svg>')

    _geom_icon_vel = (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" '
        'style="display:block;overflow:visible;">'
        '<path d="M4 12h12M16 12l-3-3M16 12l-3 3M4 6h16M4 18h8" stroke="#0B63F6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        '</svg>'
    )
    _geom_icon_loss = (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" '
        'style="display:block;overflow:visible;">'
        '<path d="M12 4v16M12 20l-4-4M12 20l4-4" stroke="#EF4444" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>'
        '<path d="M4 12h3M17 12h3" stroke="#EF4444" stroke-width="2.2" stroke-linecap="round" fill="none" opacity="0.4"/>'
        '</svg>'
    )
    _geom_icon_sector = (
        '<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" '
        'style="display:block;overflow:visible;">'
        '<circle cx="12" cy="12" r="9" stroke="#F59E0B" stroke-width="2" fill="none"/>'
        '<circle cx="12" cy="12" r="3" stroke="#F59E0B" stroke-width="2" fill="none"/>'
        '<path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="#F59E0B" stroke-width="2" stroke-linecap="round" fill="none"/>'
        '</svg>'
    )

    g1, g2, g3 = st.columns(3, gap="medium")
    with g1:
        _render_kpi_card(
            "Velocidad geométrica",
            f"{velocidad_geom:.2f} m/s",
            "Ref. del análisis",
            icon=_geom_icon_vel,
            class_name="f4-geom-kpi-card",
        )
    with g2:
        _render_kpi_card(
            "Peor pérdida geométrica",
            f"{max_geom:.2f}%",
            "Máxima entre sectores",
            icon=_geom_icon_loss,
            class_name="f4-geom-kpi-card",
        )
    with g3:
        _render_kpi_card(
            "Sectores críticos",
            ", ".join(sectores_geom_criticos),
            "Geométricamente críticos",
            icon=_geom_icon_sector,
            class_name="f4-geom-kpi-card",
        )

    fig_geom = crear_rosa_geom(resumen_geom)
    fig_geom.update_layout(
        title=None,
        height=520,
        margin=dict(l=10, r=100, t=20, b=20),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    fig_geom = _clean_plotly_labels(fig_geom)
    with st.container(border=True, key="f4_geom_rose_subcard"):
        st.markdown('<div class="f4-geom-rose-title">Rosa geométrica de pérdidas por estela</div>', unsafe_allow_html=True)
        st.plotly_chart(fig_geom, use_container_width=True, key="f4_geom_rose_plot", config=PLOTLY_PERF_CONFIG)

try:
    f4_energy_signature = (
        _df_signature(df_layout),
        _df_signature(df_nasa, ["timestamp", "WS10M", "WS50M", "WD10M", "WD50M"]),
        _df_signature(df_curva),
        base_viento,
        "Weibull",
        "Weibull",
        float(altura_deseada),
        roughness_label,
        dir_altura,
        int(len(df_layout)),
        float(diametro),
        float(ct),
        float(kw),
        "AutomÃ¡tica desde Fase 4",
        0.0,
        0.0,
        0.0,
        0.0,
    )
    energy_result = _session_cached_result(
        "f4_energy_result",
        f4_energy_signature,
        lambda: energia_calc.calcular_aep_autoritativa(
            df_layout=df_layout,
            df_nasa=df_nasa,
            df_curva_raw=df_curva,
            base_viento=base_viento,
            modo_estadistico="Weibull",
            metodo_detalle="Weibull",
            altura_deseada=altura_deseada,
            roughness_label=roughness_label,
            direccion_fuente=dir_altura,
            n_turbinas=len(df_layout),
            diametro=diametro,
            ct=ct,
            kw=kw,
            wake_mode="Automática desde Fase 4",
            wake_manual_pct=0.0,
            disp_pct=0.0,
            elec_pct=0.0,
            otras_pct=0.0,
        ),
    )
except Exception as e:
    st.error(f"No pude calcular el análisis anual: {e}")
    st.stop()

resumen_estelas = energy_result["wake_resumen"].copy()
detalles_estelas = energy_result["wake_detalles"]
perdida_ponderada = float(energy_result["wake_perdida_ponderada"])

if len(resumen_estelas) == 0:
    st.warning("No hay resultados para mostrar.")
    st.stop()

df_sector_energy = energy_result["df_sector"][[
    "Sector",
    "AEP bruta parque (MWh/año)",
    "AEP con estela (MWh/año)",
    "Pérdida estela energética (MWh/año)",
]].rename(columns={
    "AEP bruta parque (MWh/año)": "Energía bruta (MWh/año)",
    "AEP con estela (MWh/año)": "Energía con estela (MWh/año)",
    "Pérdida estela energética (MWh/año)": "Pérdida energética (MWh/año)",
})
resumen_estelas = resumen_estelas.drop(
    columns=[
        col for col in [
            "Energía bruta (MWh/año)",
            "Energía con estela (MWh/año)",
            "Pérdida energética (MWh/año)",
        ]
        if col in resumen_estelas.columns
    ],
    errors="ignore",
).merge(df_sector_energy, on="Sector", how="left")

worst_row = resumen_estelas.sort_values("Pérdida ponderada (%)", ascending=False).iloc[0]
worst_sector = str(worst_row["Sector"])
worst_weighted = float(worst_row["Pérdida ponderada (%)"])
worst_sector_loss = float(worst_row["Pérdida por estela (%)"])
energia_bruta_total = float(energy_result["resumen"]["aep_bruta_total"])
energia_wake_total = float(energy_result["resumen"]["aep_con_estela_total"])
energia_perdida_total = float(energy_result["resumen"]["perdida_estela_mwh"])

guardar_config_values({
    "f4_weighted_wake_loss_pct": perdida_ponderada,
    "f4_worst_sector": worst_sector,
    "f4_worst_sector_loss_pct": worst_sector_loss,
    "f4_energia_bruta_mwh": energia_bruta_total,
    "f4_energia_wake_mwh": energia_wake_total,
    "f4_energia_perdida_mwh": energia_perdida_total,
    "f4_geom_critical_sectors": ", ".join(sectores_geom_criticos),
    "f4_geom_max_loss_pct": max_geom,
})

with st.container(border=True, key="f4_card_annual_analysis"):
    _render_section_header("Análisis anual ponderado", "◉")
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        st.metric("Pérdida anual ponderada total", f"{perdida_ponderada:.2f}%")
    with a2:
        st.metric("Sector anual más crítico", worst_sector)
    with a3:
        st.metric("Pérdida ponderada sector crítico", f"{worst_weighted:.3f}%")
    with a4:
        st.metric("Sectores geométricamente críticos", ", ".join(sectores_geom_criticos))

    a5, a6, a7 = st.columns(3)
    with a5:
        st.metric("Energía bruta", f"{energia_bruta_total:.2f} MWh/año")
    with a6:
        st.metric("Energía con estela", f"{energia_wake_total:.2f} MWh/año")
    with a7:
        st.metric("Pérdida energética", f"{energia_perdida_total:.2f} MWh/año")



    fig_rosa_anual = crear_rosa_anual(resumen_estelas)
    fig_rosa_anual.update_layout(
        title=None,
        height=520,
        margin=dict(l=26, r=28, t=18, b=24),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    fig_rosa_anual = _clean_plotly_labels(fig_rosa_anual)
    st.markdown('<div class="f4-plot-caption">Rosa anual ponderada de pérdidas por estela</div>', unsafe_allow_html=True)
    st.plotly_chart(fig_rosa_anual, use_container_width=True, key="f4_annual_wake_rose_plot", config=PLOTLY_PERF_CONFIG)

chart_cols = st.columns(2, gap="medium")
with chart_cols[0]:
    with st.container(border=True, key="f4_card_compare_bars"):
        _render_section_header("Comparación: criticidad geométrica vs criticidad anual", '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#0B63F6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 14h10M4 14l4-4M4 14l4 4M20 10H10M20 10l-4-4M20 10l-4 4"/></svg>')
        fig_compare = crear_barras_geom_vs_anual(resumen_geom, resumen_estelas)
        fig_compare.update_layout(title=None, height=360, margin=dict(l=30, r=16, t=14, b=34))
        fig_compare = _clean_plotly_labels(fig_compare)
        st.plotly_chart(fig_compare, use_container_width=True, key="f4_geom_vs_annual_bars_plot", config=PLOTLY_PERF_CONFIG)
with chart_cols[1]:
    with st.container(border=True, key="f4_card_energy_bars"):
        _render_section_header("Energía anual por dirección", '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#0B63F6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10M12 20V4M6 20v-6"/><path d="M4 22h16"/></svg>')
        fig_energy = crear_barras_energia_direccional(resumen_estelas)
        fig_energy.update_layout(title=None, height=360, margin=dict(l=30, r=16, t=14, b=34))
        fig_energy = _clean_plotly_labels(fig_energy)
        st.plotly_chart(fig_energy, use_container_width=True, key="f4_directional_energy_bars_plot", config=PLOTLY_PERF_CONFIG)

_detail_icon_speed = _icon_svg("wind", 24, "#0ea5e9")
_detail_icon_loss = _icon_svg("trending-down", 24, "#ef4444")
_detail_icon_eff = _icon_svg("activity", 24, "#10b981")
_detail_icon_turbines = _icon_svg("map-pin", 24, "#f59e0b")
_detail_icon_freq = _icon_svg("bar-chart-2", 24, "#8b5cf6")
_detail_icon_hours = _icon_svg("clock", 24, "#0ea5e9")

with st.container(border=True, key="f4_card_detail_direction"):
    _render_section_header("Detalle por dirección", '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#0B63F6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2v20M2 12h20"/></svg>')
    sectores_disponibles = resumen_estelas["Sector"].tolist()
    sector_index = sectores_disponibles.index(sector_default) if sector_default in sectores_disponibles else 0

    _init_widget_state("f4_selected_sector", sector_default if sector_default in sectores_disponibles else sectores_disponibles[0])

    sector_elegido = st.selectbox(
        "Seleccione una dirección",
        sectores_disponibles,
        index=sector_index,
        key="f4_selected_sector",
    )

    guardar_config_values({"f4_selected_sector": st.session_state.get("f4_selected_sector", sector_default)})

    fila_sector_detalle = resumen_estelas[resumen_estelas["Sector"] == sector_elegido].iloc[0]
    velocidad_sector_detalle = float(fila_sector_detalle["Velocidad media sector (m/s)"])

    tab1, tab2 = st.tabs(["Detalle geométrico", "Detalle anual"])

    with tab1:
        fila_geom = resumen_geom[resumen_geom["Sector"] == sector_elegido].iloc[0]
        direccion_centro_geom = _get_direction_center_value(fila_geom)
        df_detalle_geom = calcular_estelas_jensen_direccion(
            df_layout=df_layout,
            wind_speed=velocidad_sector_detalle,
            direction_deg=direccion_centro_geom,
            diametro=diametro,
            ct=ct,
            kw=kw,
            curva_df=df_curva,
        )
        p_base_detalle = float(df_detalle_geom["potencia_base_W"].sum())
        p_wake_detalle = float(df_detalle_geom["potencia_wake_W"].sum())
        perdida_geom_detalle = 100.0 * (1.0 - p_wake_detalle / p_base_detalle) if p_base_detalle > 0 else 0.0
        eficiencia_geom_detalle = 100.0 * p_wake_detalle / p_base_detalle if p_base_detalle > 0 else 100.0
        turbinas_afectadas_detalle = int((df_detalle_geom["deficit_total"] > 1e-8).sum())
        fila_geom = fila_geom.copy()
        fila_geom["Velocidad referencia (m/s)"] = velocidad_sector_detalle
        for _col in fila_geom.index:
            _norm_col = _normalize_col_name(_col)
            if "perdida" in _norm_col and "geometr" in _norm_col:
                fila_geom[_col] = perdida_geom_detalle
            elif "eficiencia" in _norm_col and "geometr" in _norm_col:
                fila_geom[_col] = eficiencia_geom_detalle
        fila_geom["Turbinas afectadas"] = turbinas_afectadas_detalle

        g1, g2, g3, g4 = st.columns(4)
        with g1:
            _render_kpi_card("Velocidad dirección", f"{fila_geom['Velocidad referencia (m/s)']:.2f} m/s", "", _detail_icon_speed, "f4-detail-kpi")
        with g2:
            _render_kpi_card("Pérdida geométrica", f"{fila_geom['Pérdida geométrica (%)']:.2f}%", "", _detail_icon_loss, "f4-detail-kpi")
        with g3:
            _render_kpi_card("Eficiencia geométrica", f"{fila_geom['Eficiencia geométrica (%)']:.2f}%", "", _detail_icon_eff, "f4-detail-kpi")
        with g4:
            _render_kpi_card("Turbinas afectadas", f"{int(fila_geom['Turbinas afectadas'])}", "", _detail_icon_turbines, "f4-detail-kpi")

        fig_dir_geom = crear_figura_direccion_estela(
            df_detalle=df_detalle_geom,
            sector=sector_elegido,
            direction_deg=direccion_centro_geom,
            diametro=diametro,
        )
        fig_dir_geom = _add_wake_visual_layers(
            fig_dir_geom,
            df_detalle_geom if not df_detalle_geom.empty else df_layout,
            direction_deg=direccion_centro_geom,
        )
        # Hide Plotly colorbar; the figure uses a custom visual legend instead.
        for trace in fig_dir_geom.data:
            if hasattr(trace, "marker") and trace.marker is not None and hasattr(trace.marker, "colorbar") and trace.marker.colorbar is not None:
                trace.marker.showscale = False
        
        # Tight margins to reduce empty space
        fig_dir_geom.update_layout(
            title=None,
            height=490,
            margin=dict(l=28, r=28, t=24, b=34),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f8fbff",
            showlegend=False,
            xaxis=dict(
                title=dict(text="X (m)", font=dict(size=12, color="#475569")),
                showgrid=True,
                gridcolor="rgba(148,163,184,0.20)",
                zeroline=True,
                zerolinecolor="rgba(148,163,184,0.30)",
                tickfont=dict(size=11, color="#64748b"),
            ),
            yaxis=dict(
                title=dict(text="Y (m)", font=dict(size=12, color="#475569")),
                showgrid=True,
                gridcolor="rgba(148,163,184,0.20)",
                zeroline=True,
                zerolinecolor="rgba(148,163,184,0.30)",
                tickfont=dict(size=11, color="#64748b"),
                scaleanchor="x",
                scaleratio=1,
            ),
            annotations=(
                # Keep only existing non-empty annotations from the base figure,
                # then add our clean wind-direction badge.
                [a for a in (fig_dir_geom.layout.annotations or []) if getattr(a, 'text', '') not in ('', None)]
                + [
                    dict(
                        xref="paper", yref="paper",
                        x=0.01, y=0.99,
                        xanchor="left", yanchor="top",
                        text=(
                            f"<b>&#8599; Viento {sector_elegido} · "
                            f"{direccion_centro_geom:.0f}°</b>"
                        ),
                        showarrow=False,
                        align="left",
                        bgcolor="rgba(239,246,255,0.92)",
                        bordercolor="#93c5fd",
                        borderwidth=1,
                        borderpad=5,
                        font=dict(size=12, color="#1e3a8a"),
                    ),
                ]
            ),
        )
        fig_dir_geom = _replace_wake_colorbar_with_legend(fig_dir_geom)
        fig_dir_geom = _clean_plotly_labels(fig_dir_geom)
        st.plotly_chart(
            fig_dir_geom,
            use_container_width=True,
            key=f"f4_detail_geom_plot_{sector_elegido}",
            config=PLOTLY_INTERACTIVE_CONFIG,
        )
        _render_f4_wake_legend()

    with tab2:
        fila_sector = fila_sector_detalle
        df_detalle_sector = detalles_estelas.get(sector_elegido, pd.DataFrame())

        y1, y2, y3, y4, y5 = st.columns(5)
        with y1:
            _render_kpi_card("Frecuencia", f"{fila_sector['Frecuencia (%)']:.2f}%", "", _detail_icon_freq, "f4-detail-kpi")
        with y2:
            _render_kpi_card("Horas eq. anuales", f"{fila_sector['Horas equivalentes anuales (h/año)']:.1f}", "", _detail_icon_hours, "f4-detail-kpi")
        with y3:
            _render_kpi_card("U media sector", f"{fila_sector['Velocidad media sector (m/s)']:.2f} m/s", "", _detail_icon_speed, "f4-detail-kpi")
        with y4:
            _render_kpi_card("Pérdida por estela", f"{fila_sector['Pérdida por estela (%)']:.2f}%", "", _detail_icon_loss, "f4-detail-kpi")
        with y5:
            _render_kpi_card("Pérdida ponderada", f"{fila_sector['Pérdida ponderada (%)']:.3f}%", "", _detail_icon_loss, "f4-detail-kpi")

        fig_dir = crear_figura_direccion_estela(
            df_detalle=df_detalle_sector,
            sector=sector_elegido,
            direction_deg=float(fila_sector["Dirección centro (°)"]),
            diametro=diametro,
        )
        fig_dir = _add_wake_visual_layers(
            fig_dir,
            df_detalle_sector if not df_detalle_sector.empty else df_layout,
            direction_deg=float(fila_sector["Dirección centro (°)"]),
        )
        # Hide Plotly colorbar; the figure uses a custom visual legend instead.
        for trace in fig_dir.data:
            if hasattr(trace, "marker") and trace.marker is not None and hasattr(trace.marker, "colorbar") and trace.marker.colorbar is not None:
                trace.marker.showscale = False
        
        # Tight margins to reduce empty space
        fig_dir.update_layout(
            title=None,
            height=490,
            margin=dict(l=28, r=28, t=24, b=34),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#f8fbff",
            showlegend=False,
            xaxis=dict(
                title=dict(text="X (m)", font=dict(size=12, color="#475569")),
                showgrid=True,
                gridcolor="rgba(148,163,184,0.20)",
                zeroline=True,
                zerolinecolor="rgba(148,163,184,0.30)",
                tickfont=dict(size=11, color="#64748b"),
            ),
            yaxis=dict(
                title=dict(text="Y (m)", font=dict(size=12, color="#475569")),
                showgrid=True,
                gridcolor="rgba(148,163,184,0.20)",
                zeroline=True,
                zerolinecolor="rgba(148,163,184,0.30)",
                tickfont=dict(size=11, color="#64748b"),
                scaleanchor="x",
                scaleratio=1,
            ),
            annotations=(
                [a for a in (fig_dir.layout.annotations or []) if getattr(a, 'text', '') not in ('', None)]
                + [
                    dict(
                        xref="paper", yref="paper",
                        x=0.01, y=0.99,
                        xanchor="left", yanchor="top",
                        text=(
                            f"<b>&#8599; Viento {sector_elegido} · "
                            f"{float(fila_sector['Dirección centro (°)']):.0f}°</b>"
                        ),
                        showarrow=False,
                        align="left",
                        bgcolor="rgba(239,246,255,0.92)",
                        bordercolor="#93c5fd",
                        borderwidth=1,
                        borderpad=5,
                        font=dict(size=12, color="#1e3a8a"),
                    ),
                ]
            ),
        )
        fig_dir = _replace_wake_colorbar_with_legend(fig_dir)
        fig_dir = _clean_plotly_labels(fig_dir)
        st.plotly_chart(
            fig_dir,
            use_container_width=True,
            key=f"f4_detail_annual_plot_{sector_elegido}",
            config=PLOTLY_INTERACTIVE_CONFIG,
        )
        _render_f4_wake_legend()

    st.markdown("<div class='f4-detail-controls'>", unsafe_allow_html=True)
    toolbar_cols = st.columns([1, 1.5, 1.5, 1], gap="small", vertical_alignment="bottom")
    with toolbar_cols[1]:
        st.selectbox("Velocidad", [f"{velocidad_sector_detalle:.1f} m/s"], index=0, key="f4_detail_speed_visual")
    with toolbar_cols[2]:
        st.selectbox("Dirección", [f"{sector_elegido} ({SECTOR_CENTERS_16[SECTOR_LABELS_16.index(sector_elegido)]:.1f}°)"], index=0, key="f4_detail_direction_visual")
    st.markdown("</div>", unsafe_allow_html=True)

with st.container(border=True, key="f4_card_scenarios"):
    st.markdown(
        f"""
        <div class="f4-scenario-hero">
            <div class="f4-scenario-hero__icon">{_icon_svg("cloud-upload", 30, "#ffffff")}</div>
            <div>
                <div class="f4-scenario-hero__title">Guardar y comparar configuraciones</div>
                <div class="f4-scenario-hero__subtitle">Administre escenarios del parque, recupere configuraciones y compare alternativas guardadas.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    scenario_cols = st.columns([0.95, 1.2, 1.0], gap="medium")

    with scenario_cols[0]:
        with st.container(border=True, key="f4_card_scenario_save"):
            st.markdown(
                f'<div class="f4-scenario-card-title"><span class="f4-scenario-card-title__icon">{_icon_svg("export", 20, "#2563eb")}</span><span>Guardar escenario actual</span></div>',
                unsafe_allow_html=True,
            )
            current_scenario_name = st.text_input("Nombre del escenario", value="Escenario_actual")
            if st.button("Guardar escenario", icon=":material/cloud_upload:", use_container_width=True):
                settings_dict = {
                    "layout_type": layout_type,
                    "num_turbinas": int(len(df_layout)),
                    "dx_D": dx_D,
                    "dy_D": dy_D,
                    "rotation_deg": rotation_deg,
                    "ct": ct,
                    "kw": kw,
                    "altura_deseada": altura_deseada,
                    "base_viento": base_viento,
                    "dir_altura": dir_altura,
                    "roughness_label": roughness_label,
                    "velocidad_geom": velocidad_geom,
                    "diametro": diametro,
                }

                metrics_dict = {
                    "perdida_anual_ponderada_pct": perdida_ponderada,
                    "sector_anual_critico": worst_sector,
                    "perdida_sector_anual_pct": worst_sector_loss,
                    "sectores_geom_criticos": ", ".join(sectores_geom_criticos),
                    "perdida_geom_max_pct": max_geom,
                    "energia_bruta_mwh": energia_bruta_total,
                    "energia_wake_mwh": energia_wake_total,
                    "energia_perdida_mwh": energia_perdida_total,
                }

                guardar_escenario_parque(
                    name=current_scenario_name.strip(),
                    df_layout=df_layout,
                    settings_dict=settings_dict,
                    metrics_dict=metrics_dict,
                )
                st.success("Escenario guardado.")
                st.rerun()
            st.markdown(
                f'<div class="f4-scenario-helper">{_icon_svg("clock", 16, "#64748b")}<span>Última actualización: al guardar el escenario actual.</span></div>',
                unsafe_allow_html=True,
            )

    df_scenarios = listar_escenarios_parque()

    with scenario_cols[1]:
        with st.container(border=True, key="f4_card_scenario_list"):
            st.markdown(
                f'<div class="f4-scenario-card-title"><span class="f4-scenario-card-title__icon">{_icon_svg("database-stack", 20, "#2563eb")}</span><span>Escenarios guardados</span></div>',
                unsafe_allow_html=True,
            )
            if len(df_scenarios) > 0:
                st.markdown('<div class="f4-scenario-table-wrap">', unsafe_allow_html=True)
                st.dataframe(df_scenarios, use_container_width=True)
                st.markdown('</div>', unsafe_allow_html=True)
            else:
                st.caption("No hay escenarios guardados.")

    with scenario_cols[2]:
        with st.container(border=True, key="f4_card_scenario_compare"):
            st.markdown(
                f'<div class="f4-scenario-card-title"><span class="f4-scenario-card-title__icon">{_icon_svg("bar-chart-2", 20, "#2563eb")}</span><span>Comparación de configuraciones</span></div>',
                unsafe_allow_html=True,
            )
            if len(df_scenarios) > 0:
                names = df_scenarios["name"].tolist()
                escenario_cargar = st.selectbox("Escenario base", names, index=0, key="f4_load_scenario")
                if st.button("Cargar escenario seleccionado", icon=":material/cloud_download:", use_container_width=True):
                    esc = cargar_escenario_parque(escenario_cargar)
                    if esc is not None:
                        guardar_layout_parque(esc["layout"])
                        guardar_config_values(esc["settings"])
                        st.success("Escenario cargado.")
                        st.rerun()
                if st.button("Eliminar escenario seleccionado", icon=":material/delete:", use_container_width=True):
                    eliminar_escenario_parque(escenario_cargar)
                    st.success("Escenario eliminado.")
                    st.rerun()

                if len(names) >= 2:
                    esc_a = st.selectbox("Escenario base", names, index=0, key="escenario_a")
                    esc_b = st.selectbox("Comparar con", names, index=1, key="escenario_b")
                    st.button("Comparar escenarios", icon=":material/stacked_line_chart:", use_container_width=True, key="f4_compare_scenarios_btn")

                    data_a = cargar_escenario_parque(esc_a)
                    data_b = cargar_escenario_parque(esc_b)
                    if data_a is not None and data_b is not None:
                        df_a = data_a["layout"]
                        df_b = data_b["layout"]
                        met_a = data_a["metrics"]
                        met_b = data_b["metrics"]
                        fig_comp = crear_figura_comparacion_layouts(df_a, df_b, esc_a, esc_b)
                        fig_comp.update_layout(title=None, height=320, margin=dict(l=24, r=18, t=16, b=24))
                        st.plotly_chart(fig_comp, use_container_width=True, key="f4_scenario_comparison_plot", config=PLOTLY_PERF_CONFIG)

                        tabla_comp = pd.DataFrame({
                            "Indicador": [
                                "Pérdida anual ponderada (%)",
                                "Sector anual crítico",
                                "Pérdida sector anual (%)",
                                "Sectores geométricos críticos",
                                "Pérdida geométrica máxima (%)",
                                "Energía bruta (MWh/año)",
                                "Energía con estela (MWh/año)",
                                "Pérdida energética (MWh/año)",
                            ],
                            esc_a: [
                                met_a.get("perdida_anual_ponderada_pct", ""),
                                met_a.get("sector_anual_critico", ""),
                                met_a.get("perdida_sector_anual_pct", ""),
                                met_a.get("sectores_geom_criticos", ""),
                                met_a.get("perdida_geom_max_pct", ""),
                                met_a.get("energia_bruta_mwh", ""),
                                met_a.get("energia_wake_mwh", ""),
                                met_a.get("energia_perdida_mwh", ""),
                            ],
                            esc_b: [
                                met_b.get("perdida_anual_ponderada_pct", ""),
                                met_b.get("sector_anual_critico", ""),
                                met_b.get("perdida_sector_anual_pct", ""),
                                met_b.get("sectores_geom_criticos", ""),
                                met_b.get("perdida_geom_max_pct", ""),
                                met_b.get("energia_bruta_mwh", ""),
                                met_b.get("energia_wake_mwh", ""),
                                met_b.get("energia_perdida_mwh", ""),
                            ],
                        })

                        st.dataframe(tabla_comp, use_container_width=True)





        st.markdown(
            """
            <style>
            /* =========================================================
               FORZADO FINAL: estilo SMA 2.0 para cards grandes - Fase 4
               ========================================================= */

            .st-key-f4_card_config,
            .st-key-f4_card_edit_table,
            .st-key-f4_card_move_layout,
            .st-key-f4_card_view_layout,
            .st-key-f4_card_geom_summary,
            .st-key-f4_card_wind_base,
            .st-key-f4_card_geom_analysis,
            .st-key-f4_card_annual_analysis,
            .st-key-f4_card_compare_bars,
            .st-key-f4_card_energy_bars,
            .st-key-f4_card_detail_direction,
            .st-key-f4_card_scenarios,
            .st-key-f4_card_scenario_save,
            .st-key-f4_card_scenario_list,
            .st-key-f4_card_scenario_compare {
                border: 1.4px solid #cbd5e1 !important;
                border-radius: 28px !important;
                background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
                box-shadow:
                    0 1px 4px rgba(15, 23, 42, 0.045),
                    0 8px 22px rgba(15, 23, 42, 0.040) !important;
                overflow: visible !important;
                box-sizing: border-box !important;
            }

            .st-key-f4_card_config div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_edit_table div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_move_layout div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_view_layout div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_geom_summary div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_wind_base div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_geom_analysis div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_annual_analysis div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_compare_bars div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_energy_bars div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_detail_direction div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_scenarios div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_scenario_save div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_scenario_list div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f4_card_scenario_compare div[data-testid="stVerticalBlockBorderWrapper"] {
                border: none !important;
                box-shadow: none !important;
                border-radius: 28px !important;
                background: transparent !important;
                overflow: visible !important;
                box-sizing: border-box !important;
            }

            /* --- FORZADO: Sombra con volumen estilo Fase 3 --- */
            .st-key-f4_card_move_layout,
            .st-key-f4_card_edit_table,
            .st-key-f4_card_config,
            .st-key-f4_card_view_layout,
            .st-key-f4_card_geom_summary,
            .st-key-f4_top_kpi_1,
            .st-key-f4_top_kpi_2,
            .st-key-f4_top_kpi_3,
            .st-key-f4_top_kpi_4,
            .st-key-f4_top_kpi_5,
            .st-key-f4_card_wind_base,
            .st-key-f4_card_geom_analysis,
            .st-key-f4_card_annual_analysis,
            .st-key-f4_card_compare_bars,
            .st-key-f4_card_energy_bars,
            .st-key-f4_card_detail_direction,
            .st-key-f4_card_scenarios {
                border: 1px solid #cbd5e1 !important;
                box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
            }

            </style>
            """,
            unsafe_allow_html=True,
        )

render_dropdown_visibility_fix()
