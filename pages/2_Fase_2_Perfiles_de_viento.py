
import base64
import textwrap
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from navigation import render_dropdown_visibility_fix, render_sidebar_navigation, _icon_svg

from db import init_db, cargar_config, guardar_config_values, guardar_nasa_hourly, cargar_nasa_hourly, get_db_file_path
from widget_helpers import _init_widget_state
from calculos import (
    KAPPA,
    calcular_alpha_desde_dos_alturas,
    ajustar_logaritmico_dos_puntos,
    calcular_perfil_exponencial,
    calcular_perfil_logaritmico,
    calcular_velocidad_friccion,
    velocidad_logaritmica_en_altura,
    crear_grafica_perfil_individual,
    construir_url_nasa_power,
    leer_csv_nasa_subido,
    leer_json_nasa_subido,
    leer_csv_gwa,
    generar_serie_weibull,
    consultar_open_meteo,
    crear_grafica_nasa_hourly,
)

st.set_page_config(page_title="Fase 2 · Perfiles de viento", layout="wide")

# Cargar CSS global e inyectar sidebar lo ANTES posible para evitar FOUC.
render_sidebar_navigation("pages/2_Fase_2_Perfiles_de_viento.py")

init_db()

PLOTLY_PERF_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}


def _file_signature(path: str | Path) -> tuple:
    file_path = Path(path)
    if not file_path.exists():
        return (str(file_path), 0, 0)
    stat = file_path.stat()
    return (str(file_path), int(stat.st_mtime_ns), int(stat.st_size))


def _session_cached_result(state_key: str, signature: tuple, builder):
    cached = st.session_state.get(state_key)
    if isinstance(cached, dict) and cached.get("signature") == signature:
        return cached["value"]
    value = builder()
    st.session_state[state_key] = {"signature": signature, "value": value}
    return value

ROUGHNESS_OPTIONS = {
    "Water / Mar": 2e-4,
    "Snow / Nieve": 1e-3,
    "Grass / Césped": 0.03,
    "Farmland / Cultivo": 0.10,
    "Forest / Bosque": 0.80,
    "City / Ciudad": 1.00,
}


def _section_title_html(letter: str, icon_name: str, title: str, subtitle: str | None = None) -> str:
    subtitle_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    return textwrap.dedent(
        f"""
        <div class="section-header">
            <div class="section-badge">{letter}</div>
            <div class="section-copy">
                <div class="section-title">
                    <span class="section-icon">{_icon_svg(icon_name, 18, "#2563eb")}</span>
                    <span>{title}</span>
                </div>
                {subtitle_html}
            </div>
        </div>
        """
    ).strip()

def _render_metric_card(
    icon_name: str,
    label: str,
    value: str,
    tone: str = "blue",
    compact: bool = False,
    extra_class: str = "",
    icon_dx: int = 0,
    icon_dy: int = 0,
    icon_variant: str = "",
):
    st.markdown(
        _metric_card_html(
            icon_name=icon_name,
            label=label,
            value=value,
            tone=tone,
            compact=compact,
            extra_class=extra_class,
            icon_dx=icon_dx,
            icon_dy=icon_dy,
            icon_variant=icon_variant,
        ),
        unsafe_allow_html=True,
    )


def _metric_card_html(
    icon_name: str,
    label: str,
    value: str,
    tone: str = "blue",
    compact: bool = False,
    extra_class: str = "",
    icon_dx: int = 0,
    icon_dy: int = 0,
    icon_variant: str = "",
) -> str:
    icon_color = "#2563eb" if tone != "green" else "#15803d"
    if icon_variant == "param":
        icon_color = "#7c3aed"
    elif icon_variant == "combined":
        icon_color = "#0f766e"

    icon_color_class = ""
    if icon_variant == "wind":
        icon_color_class = " icon-color-wind"
    elif icon_variant == "param":
        icon_color_class = " icon-color-param"
    elif icon_variant == "combined":
        icon_color_class = " icon-color-combined"

    icon_inner_style = (
        f'style="transform: translate({icon_dx}px, {icon_dy}px);"'
        if icon_dx or icon_dy
        else ""
    )
    profile_icon_classes = {
        "metric-card--profile",
        "metric-card--profile-combined",
        "metric-card--profile-speed",
    }
    icon_size = 34 if icon_name == "log-exp-average" else 38 if extra_class == "metric-card--summary" else 30 if extra_class in profile_icon_classes else 22
    return textwrap.dedent(
        f"""
        <div class="metric-card metric-{tone}{' metric-card--compact' if compact else ''}{f' {extra_class}' if extra_class else ''}">
            <div class="metric-icon metric-icon--{icon_name}{icon_color_class}">
                <div class="metric-icon-inner" {icon_inner_style}>
                    {_icon_svg(icon_name, icon_size, icon_color)}
                </div>
            </div>
            <div class="metric-copy">
                <div class="metric-label">{label}</div>
                <div class="metric-value{' metric-value--green' if tone == 'green' else ''}">{value}</div>
            </div>
        </div>
        """
    ).strip()


def _phase_card(key: str | None = None):
    return st.container(border=True, key=key)

def _safe_fase2_roughness_label(value):
    label = str(value or "").strip()
    if label in ROUGHNESS_OPTIONS:
        return label
    return "Grass / Césped"


def _load_current_config():
    return cargar_config()


def _fase2_project_signature(current_config):
    return str(current_config.get("project_name") or "")


def _get_saved_profile_values(current_config):
    try:
        altura = float(current_config.get("perfil_hhub") or current_config.get("f2_altura_deseada") or 80.0)
    except Exception:
        altura = 80.0
    altura = max(0.10, altura)
    roughness = _safe_fase2_roughness_label(
        current_config.get("perfil_roughness_label")
        or current_config.get("f2_roughness_label")
        or "Grass / Césped"
    )
    return altura, roughness


def _guardar_parametros_perfiles(altura_visible, rugosidad_visible):
    altura = max(0.10, float(altura_visible))
    roughness = _safe_fase2_roughness_label(rugosidad_visible)

    guardar_config_values({
        "f2_altura_deseada": altura,
        "f2_roughness_label": roughness,
        "perfil_hhub": altura,
        "perfil_roughness_label": roughness,
    })

    st.session_state["f2_profile_save_message"] = "Parámetros de perfiles guardados correctamente."


def _render_dataframe_safe(df, numeric_formats=None, **kwargs):
    column_config = {}
    for col, fmt in (numeric_formats or {}).items():
        if col in df.columns:
            column_config[col] = st.column_config.NumberColumn(format=fmt)
    st.dataframe(df, column_config=column_config, **kwargs)


def _f2_expander_icon_label(icon_name: str, label: str) -> str:
    icon_svg = _icon_svg(icon_name, 22, "#2563eb")
    icon_uri = "data:image/svg+xml;utf8," + quote(icon_svg)
    return f"![{label}]({icon_uri}) {label}"


def _f2_table_panel_header(icon_name: str, title: str, subtitle: str) -> str:
    icon_html = _icon_svg(icon_name, 20, "#2563eb")
    return (
        '<div class="f2-table-panel-header">'
        f'<div class="f2-table-panel-icon">{icon_html}</div>'
        '<div>'
        f'<div class="f2-table-title">{title}</div>'
        f'<div class="f2-table-subtitle">{subtitle}</div>'
        '</div>'
        '</div>'
    )


def _f2_table_summary_cards(items) -> str:
    cards = "".join(
        '<div class="f2-table-summary-card">'
        f'<div class="f2-table-summary-icon">{_icon_svg(icon_name, 30, "#2563eb")}</div>'
        '<div class="f2-table-summary-copy">'
        f'<div class="f2-table-summary-label">{label}</div>'
        f'<div class="f2-table-summary-value">{value}</div>'
        '</div>'
        '</div>'
        for label, value, icon_name in items
    )
    return f'<div class="f2-table-summary-grid">{cards}</div>'


def _toggle_flag(state_key):
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def _render_fase2_plot_chip_controls():
    defaults = {
        "f2_show_fig_exp": False,
        "f2_show_fig_log_a": False,
        "f2_show_fig_promedio": False,
        "f2_show_fig_comparacion": False,
        "f2_show_fig_comparacion_log": False,
    }
    for key, default in defaults.items():
        st.session_state.setdefault(key, default)

    st.markdown(
        """
        <style>
        .st-key-f2_fig_chip_panel {
            margin: 0.25rem 0 0.35rem 0;
        }
        .st-key-f2_fig_chip_panel [data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-wrap: wrap !important;
            gap: 0.55rem !important;
            align-items: flex-start !important;
        }
        .st-key-f2_fig_chip_panel [data-testid="stButton"] > button {
            display: inline-flex !important;
            align-items: center !important;
            gap: 0.55rem !important;
            border-radius: 999px;
            border: 1px solid #93c5fd !important;
            background: #ffffff !important;
            color: #1e3a8a !important;
            font-size: 0.88rem !important;
            font-weight: 700 !important;
            padding: 0.34rem 0.9rem 0.34rem 0.42rem !important;
            min-height: 2.5rem !important;
            width: auto !important;
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06) !important;
            white-space: nowrap !important;
        }
        .st-key-f2_fig_chip_panel [data-testid="stButton"] > button[kind="primary"] {
            background: #dbeafe !important;
            border-color: #60a5fa !important;
            color: #1e40af !important;
        }
        .st-key-f2_fig_chip_panel [data-testid="stButton"] > button:hover {
            border-color: #3b82f6 !important;
            color: #1e3a8a !important;
        }
        .st-key-f2_fig_chip_panel [data-testid="stButton"] > button p {
            margin: 0 !important;
            line-height: 1.05 !important;
        }
        .st-key-btn_f2_fig_exp [data-testid="stButton"] > button::before,
        .st-key-btn_f2_fig_log_a [data-testid="stButton"] > button::before,
        .st-key-btn_f2_fig_promedio [data-testid="stButton"] > button::before,
        .st-key-btn_f2_fig_comparacion [data-testid="stButton"] > button::before,
        .st-key-btn_f2_fig_comparacion_log [data-testid="stButton"] > button::before {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 2rem;
            height: 1.55rem;
            padding: 0 0.45rem;
            border-radius: 999px;
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            color: #2563eb;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.01em;
            box-sizing: border-box;
        }
        .st-key-btn_f2_fig_exp [data-testid="stButton"] > button::before { content: "F1"; }
        .st-key-btn_f2_fig_log_a [data-testid="stButton"] > button::before { content: "F2"; }
        .st-key-btn_f2_fig_promedio [data-testid="stButton"] > button::before { content: "F3"; }
        .st-key-btn_f2_fig_comparacion [data-testid="stButton"] > button::before { content: "F4"; }
        .st-key-btn_f2_fig_comparacion_log [data-testid="stButton"] > button::before { content: "F5"; }
        .st-key-btn_f2_fig_exp [data-testid="stButton"] > button[kind="primary"]::before,
        .st-key-btn_f2_fig_log_a [data-testid="stButton"] > button[kind="primary"]::before,
        .st-key-btn_f2_fig_promedio [data-testid="stButton"] > button[kind="primary"]::before,
        .st-key-btn_f2_fig_comparacion [data-testid="stButton"] > button[kind="primary"]::before,
        .st-key-btn_f2_fig_comparacion_log [data-testid="stButton"] > button[kind="primary"]::before {
            background: #dbeafe;
            border-color: #93c5fd;
            color: #1d4ed8;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    chip_panel = st.container(
        horizontal=True,
        horizontal_alignment="left",
        gap="small",
        key="f2_fig_chip_panel",
    )
    chips = [
        ("Perfil exponencial", "f2_show_fig_exp", "btn_f2_fig_exp"),
        ("Log A", "f2_show_fig_log_a", "btn_f2_fig_log_a"),
        ("Promedio", "f2_show_fig_promedio", "btn_f2_fig_promedio"),
        ("Comparación", "f2_show_fig_comparacion", "btn_f2_fig_comparacion"),
        ("Escala log", "f2_show_fig_comparacion_log", "btn_f2_fig_comparacion_log"),
    ]
    with chip_panel:
        for label, state_key, button_key in chips:
            st.button(
                label,
                key=button_key,
                type="primary" if st.session_state.get(state_key, False) else "secondary",
                on_click=_toggle_flag,
                args=(state_key,),
            )


def _build_preview_table(df, key_prefix, default_rows=300):
    total_rows = len(df)
    if total_rows == 0:
        return df

    with st.container(key=f"{key_prefix}_controls_white"):
        preview_cols = st.columns([1.15, 0.85], gap="medium")
        with preview_cols[0]:
            modo = st.selectbox(
                "Modo de visualización",
                ["Primeras filas", "Últimas filas", "Rango de filas", "Muestreo uniforme"],
                index=0,
                key=f"{key_prefix}_mode",
            )

        with preview_cols[1]:
            n_rows = st.number_input(
                "Cantidad de filas a mostrar",
                min_value=10,
                max_value=max(10, total_rows),
                value=min(default_rows, total_rows),
                step=10,
                key=f"{key_prefix}_rows",
            )

        if modo == "Rango de filas":
            inicio_max = max(0, total_rows - int(n_rows))
            inicio = st.number_input(
                "Fila inicial",
                min_value=0,
                max_value=inicio_max,
                value=0,
                step=1,
                key=f"{key_prefix}_start",
            )
        else:
            inicio = 0

    if modo == "Primeras filas":
        return df.head(int(n_rows))

    if modo == "Últimas filas":
        return df.tail(int(n_rows))

    if modo == "Rango de filas":
        fin = int(inicio) + int(n_rows)
        return df.iloc[int(inicio):fin]

    if total_rows <= int(n_rows):
        return df

    idx = np.linspace(0, total_rows - 1, int(n_rows), dtype=int)
    return df.iloc[idx]


def _process_csv_callback():
    archivo = st.session_state.get("f2_csv_upload")
    if archivo is None:
        st.session_state["f2_csv_result"] = ("warning", "Primero seleccione un archivo CSV o JSON.")
        return

    try:
        file_name = getattr(archivo, "name", "") or ""
        if file_name.lower().endswith(".json"):
            df_csv, meta = leer_json_nasa_subido(archivo)
        else:
            df_csv, meta = leer_csv_nasa_subido(archivo)

        lat_guardar = st.session_state["f2_latitude"]
        lon_guardar = st.session_state["f2_longitude"]

        if meta.get("latitude") is not None and meta.get("longitude") is not None:
            lat_guardar = float(meta["latitude"])
            lon_guardar = float(meta["longitude"])
            st.session_state["f2_latitude"] = lat_guardar
            st.session_state["f2_longitude"] = lon_guardar
            warning_coords = None
        else:
            warning_coords = (
                "El CSV no trajo coordenadas detectables. "
                "Se conservarán la latitud y longitud actuales."
            )

        inicio_guardar = (
            pd.to_datetime(meta["start_date"]).date()
            if meta.get("start_date") is not None
            else st.session_state["f2_fecha_inicio"]
        )
        fin_guardar = (
            pd.to_datetime(meta["end_date"]).date()
            if meta.get("end_date") is not None
            else st.session_state["f2_fecha_fin"]
        )

        st.session_state["f2_fecha_inicio"] = inicio_guardar
        st.session_state["f2_fecha_fin"] = fin_guardar

        guardar_nasa_hourly(
            df=df_csv,
            latitude=lat_guardar,
            longitude=lon_guardar,
            source="CSV NASA POWER",
            start_date=inicio_guardar,
            end_date=fin_guardar,
        )
        st.session_state.pop("f2_nasa_hourly_df", None)

        guardar_config_values({
            "nasa_lat": lat_guardar,
            "nasa_lon": lon_guardar,
            "nasa_inicio": inicio_guardar,
            "nasa_fin": fin_guardar,
            "nasa_fuente": "CSV NASA POWER",
        })

        if warning_coords:
            st.session_state["f2_csv_result"] = ("warning_success", warning_coords)
        else:
            st.session_state["f2_csv_result"] = ("success", "CSV procesado, actualizado y guardado en SQLite.")
    except Exception as e:
        st.session_state["f2_csv_result"] = ("error", f"No pude procesar el CSV: {e}")


config = _load_current_config()

if "f2_latitude" not in st.session_state:
    st.session_state["f2_latitude"] = float(config.get("nasa_lat") or 10.968540)

if "f2_longitude" not in st.session_state:
    st.session_state["f2_longitude"] = float(config.get("nasa_lon") or -74.781320)

if "f2_fecha_inicio" not in st.session_state:
    st.session_state["f2_fecha_inicio"] = pd.to_datetime(config.get("nasa_inicio") or "2024-01-01").date()

if "f2_fecha_fin" not in st.session_state:
    st.session_state["f2_fecha_fin"] = pd.to_datetime(config.get("nasa_fin") or "2024-01-07").date()

if "f2_map_zoom" not in st.session_state:
    try:
        st.session_state["f2_map_zoom"] = max(9, int(float(config.get("site_map_zoom") or 9)))
    except Exception:
        st.session_state["f2_map_zoom"] = 9

# ── GWA: separate lat/lon session state ──
_init_widget_state("f2_gwa_latitude", float(config.get("gwa_lat", 0.0)))
_init_widget_state("f2_gwa_longitude", float(config.get("gwa_lon", 0.0)))
if "f2_gwa_map_zoom" not in st.session_state:
    try:
        st.session_state["f2_gwa_map_zoom"] = max(9, int(float(config.get("gwa_map_zoom") or config.get("site_map_zoom") or 9)))
    except Exception:
        st.session_state["f2_gwa_map_zoom"] = 9

if "f2_gwa_inicio" not in st.session_state:
    st.session_state["f2_gwa_inicio"] = pd.to_datetime(config.get("gwa_inicio") or "2020-01-01").date()
if "f2_gwa_fin" not in st.session_state:
    st.session_state["f2_gwa_fin"] = pd.to_datetime(config.get("gwa_fin") or "2024-12-31").date()


def guardar_config_mapa():
    current_config = _load_current_config()
    previous_lat = current_config.get("nasa_lat")
    previous_lon = current_config.get("nasa_lon")
    new_lat = st.session_state["f2_latitude"]
    new_lon = st.session_state["f2_longitude"]

    values = {
        "nasa_lat": st.session_state["f2_latitude"],
        "nasa_lon": st.session_state["f2_longitude"],
        "nasa_inicio": st.session_state["f2_fecha_inicio"],
        "nasa_fin": st.session_state["f2_fecha_fin"],
        "site_map_zoom": st.session_state.get("f2_map_zoom", current_config.get("site_map_zoom", "9")),
        "site_map_tiles": current_config.get("site_map_tiles", "OpenStreetMap"),
    }

    try:
        coords_changed = (
            previous_lat not in [None, ""] and previous_lon not in [None, ""]
            and (abs(float(previous_lat) - float(new_lat)) > 1e-9 or abs(float(previous_lon) - float(new_lon)) > 1e-9)
        )
    except Exception:
        coords_changed = str(previous_lat) != str(new_lat) or str(previous_lon) != str(new_lon)

    if coords_changed:
        values.update({
            "site_map_image_name": "",
            "site_map_image_mime": "",
            "site_map_image_b64": "",
        })

    guardar_config_values(values)


def guardar_config_mapa_gwa():
    """Persist GWA map coordinates and dates to their own DB keys."""
    guardar_config_values({
        "gwa_lat": st.session_state["f2_gwa_latitude"],
        "gwa_lon": st.session_state["f2_gwa_longitude"],
        "gwa_map_zoom": st.session_state.get("f2_gwa_map_zoom", 9),
        "gwa_inicio": st.session_state.get("f2_gwa_inicio", ""),
        "gwa_fin": st.session_state.get("f2_gwa_fin", ""),
    })


def guardar_imagen_canonica_mapa(uploaded_file):
    if uploaded_file is None:
        return False, "No se recibio ninguna imagen para guardar."

    raw_bytes = uploaded_file.getvalue()
    if not raw_bytes:
        return False, "La imagen seleccionada esta vacia."

    max_size_bytes = 8 * 1024 * 1024
    if len(raw_bytes) > max_size_bytes:
        return False, "La imagen supera el limite recomendado de 8 MB para guardarla dentro del proyecto."

    guardar_config_values({
        "site_map_image_name": str(getattr(uploaded_file, "name", "") or ""),
        "site_map_image_mime": str(getattr(uploaded_file, "type", "") or ""),
        "site_map_image_b64": base64.b64encode(raw_bytes).decode("ascii"),
    })
    return True, "La imagen canonica del mapa se guardo en el proyecto actual."


def limpiar_imagen_canonica_mapa():
    guardar_config_values({
        "site_map_image_name": "",
        "site_map_image_mime": "",
        "site_map_image_b64": "",
    })


@st.cache_data(show_spinner=False)
def crear_grafica_modos(df_exp, df_log_a, df_promedio, altura_deseada, v_exp, v_log_a, v_promedio, puntos_medidos):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_exp["Velocidad (m/s)"],
        y=df_exp["Altura (m)"],
        mode="lines",
        name="Exponencial (2 puntos)",
        line=dict(width=3, color="#3366ff"),
        hovertemplate="Exp. 2 puntos<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_log_a["Velocidad (m/s)"],
        y=df_log_a["Altura (m)"],
        mode="lines",
        name="Logarítmico A (2 puntos)",
        line=dict(width=3, color="#ff5533", dash="dash"),
        hovertemplate="Log A<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_promedio["Velocidad (m/s)"],
        y=df_promedio["Altura (m)"],
        mode="lines",
        name="Promedio Log-Exp",
        line=dict(width=3, color="#2ca25f", dash="dot"),
        hovertemplate="Promedio Log-Exp<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[p["velocidad"] for p in puntos_medidos],
        y=[p["altura"] for p in puntos_medidos],
        mode="markers",
        name="Puntos medidos",
        marker=dict(size=10, color="black"),
        text=[p["etiqueta"] for p in puntos_medidos],
        hovertemplate="%{text}<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[v_exp],
        y=[altura_deseada],
        mode="markers",
        name="Objetivo exp.",
        marker=dict(size=10, color="#3366ff"),
        hovertemplate="Objetivo exp.<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
    ))
    if np.isfinite(v_log_a):
        fig.add_trace(go.Scatter(
            x=[v_log_a],
            y=[altura_deseada],
            mode="markers",
            name="Objetivo log A",
            marker=dict(size=10, color="#ff5533", symbol="diamond"),
            hovertemplate="Objetivo log A<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
        ))
    if np.isfinite(v_promedio):
        fig.add_trace(go.Scatter(
            x=[v_promedio],
            y=[altura_deseada],
            mode="markers",
            name="Objetivo promedio",
            marker=dict(size=10, color="#2ca25f", symbol="square"),
            hovertemplate="Objetivo promedio<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
        ))
    fig.add_hline(y=float(altura_deseada), line_dash="dot", line_color="gray")
    fig.update_layout(
        title="Comparación entre Exponencial, Log A y Promedio Log-Exp",
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(title_text="Velocidad del viento (m/s)")
    fig.update_yaxes(title_text="Altura (m)")
    return fig


@st.cache_data(show_spinner=False)
def crear_grafica_modos_log(df_exp, df_log_a, df_promedio, altura_deseada, v_exp, v_log_a, v_promedio, puntos_medidos):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_exp["Velocidad (m/s)"], y=df_exp["Altura (m)"], mode="lines", name="Exponencial (2 puntos)", line=dict(width=3, color="#3366ff")))
    fig.add_trace(go.Scatter(x=df_log_a["Velocidad (m/s)"], y=df_log_a["Altura (m)"], mode="lines", name="Logarítmico A (2 puntos)", line=dict(width=3, color="#ff5533", dash="dash")))
    fig.add_trace(go.Scatter(x=df_promedio["Velocidad (m/s)"], y=df_promedio["Altura (m)"], mode="lines", name="Promedio Log-Exp", line=dict(width=3, color="#2ca25f", dash="dot")))
    fig.add_trace(go.Scatter(
        x=[p["velocidad"] for p in puntos_medidos],
        y=[p["altura"] for p in puntos_medidos],
        mode="markers",
        name="Puntos medidos",
        marker=dict(size=10, color="black"),
        text=[p["etiqueta"] for p in puntos_medidos],
        hovertemplate="%{text}<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
    ))
    fig.add_trace(go.Scatter(x=[v_exp], y=[altura_deseada], mode="markers", name="Objetivo exp.", marker=dict(size=10, color="#3366ff")))
    if np.isfinite(v_log_a):
        fig.add_trace(go.Scatter(x=[v_log_a], y=[altura_deseada], mode="markers", name="Objetivo log A", marker=dict(size=10, color="#ff5533", symbol="diamond")))
    if np.isfinite(v_promedio):
        fig.add_trace(go.Scatter(x=[v_promedio], y=[altura_deseada], mode="markers", name="Objetivo promedio", marker=dict(size=10, color="#2ca25f", symbol="square")))
    fig.add_hline(y=float(altura_deseada), line_dash="dot", line_color="gray")
    fig.update_layout(
        title="Comparación entre Exponencial, Log A y Promedio Log-Exp - altura en escala logarítmica",
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(title_text="Velocidad del viento (m/s)")
    fig.update_yaxes(title_text="Altura (m)", type="log")
    return fig


st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%) !important;
    }
                                                                    .sidebar-help {
        margin: auto 0.42rem 0.2rem 0.42rem;
        padding: 0.85rem 0.75rem 0.8rem 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.7rem;
        border-top: 1px solid rgba(219, 234, 254, 0.95);
    }
    .sidebar-help__icon {
        width: 34px;
        height: 34px;
        min-width: 34px;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(180deg, #ffffff 0%, #f3f6fb 100%);
        border: 1px solid #cbd5e1;
        box-shadow: 0 6px 12px rgba(37, 99, 235, 0.08);
    }
    .sidebar-help__copy {
        min-width: 0;
    }
    .sidebar-help__title {
        font-size: 0.92rem;
        font-weight: 700;
        color: #0f172a;
        line-height: 1.15;
        margin-bottom: 0.14rem;
    }
    .sidebar-help__subtitle {
        font-size: 0.84rem;
        color: #64748b;
        line-height: 1.2;
    }
    div[data-testid="stButton"] > button,
    div[data-testid="stDownloadButton"] > button {
        border-radius: 14px !important;
        padding: 0.72rem 1rem !important;
        font-weight: 700 !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05) !important;
        transition: all 0.18s ease !important;
        background: #ffffff !important;
        color: #2563eb !important;
    }
    div[data-testid="stButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:hover {
        background: #f8fbff !important;
        border-color: #93c5fd !important;
    }
    [data-testid="stNumberInput"] input,
    [data-testid="stDateInputField"] input,
    [data-testid="stFileUploader"] section {
        border-radius: 14px !important;
    }
    .hero-card {
        position: relative;
        overflow: hidden;
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        border: 1px solid #cbd5e1;
        border-radius: 20px;
        padding: 1.45rem 1.55rem 1.35rem 1.55rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.045);
    }
    .hero-card::after {
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
    .fase-hero-title {
        font-size: 2.1rem;
        line-height: 1.05;
        font-weight: 800;
        color: #1e3a8a;
        margin: 0 0 0.28rem 0;
        position: relative;
        z-index: 2;
    }
    .fase-hero-subtitle {
        color: #64748b;
        font-size: 0.94rem;
        line-height: 1.42;
        font-weight: 700;
        margin: 0;
        max-width: 74rem;
        position: relative;
        z-index: 2;
    }
.f2-source-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    margin-left: 8px;
    vertical-align: middle;
}
.f2-source-badge--nasa {
    background: #dbeafe;
    color: #1e40af;
    border: 1px solid #93c5fd;
}
.f2-source-badge--gwa {
    background: #dcfce7;
    color: #166534;
    border: 1px solid #86efac;
}
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%);
        border: 1px solid #cbd5e1 !important;
        border-radius: 16px !important;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.045);
        padding: 1.05rem 1.05rem 0.95rem 1.05rem;
        margin-bottom: 1rem;
    }
    .phase-card {
        background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%);
        border: 1px solid #cbd5e1;
        border-radius: 18px;
        padding: 1.15rem 1.15rem 1.05rem 1.15rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.045);
    }
    .section-header {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        margin-bottom: 0.85rem;
    }
    .section-badge {
        width: 1.8rem;
        height: 1.8rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        color: #2563eb;
        font-weight: 800;
        flex-shrink: 0;
    }
    .section-title {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        font-size: 1.12rem;
        font-weight: 800;
        color: #1d4ed8;
        margin-bottom: 0.12rem;
    }
    .section-subtitle,
    .muted-text {
        color: #64748b;
        font-size: 0.94rem;
        font-weight: 700;
    }
    .section-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
    }
    .metric-card {
        display: flex;
        align-items: center;
        gap: 0.9rem;
        border-radius: 16px;
        padding: 1rem 1.02rem;
        border: 1px solid #cbd5e1;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.045);
        margin-bottom: 0.75rem;
    }
    .metric-card--compact {
        padding: 0.75rem 0.85rem;
        min-height: 92px;
        margin-bottom: 0;
        box-shadow: none;
        background: #ffffff;
    }
    .metric-blue { background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%); }
    .metric-green { background: linear-gradient(180deg, #f8fff8 0%, #eefbf1 100%); }
    .metric-icon {
        width: 46px;
        height: 46px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(255,255,255,0.92);
        border: 1px solid #cbd5e1;
        flex-shrink: 0;
    }
    .metric-card--compact .metric-icon {
        width: 42px;
        height: 42px;
        background: #eff6ff;
        border-color: #bfdbfe;
    }
    .metric-label {
        font-size: 0.82rem;
        color: #64748b;
        margin-bottom: 0.16rem;
    }
    .metric-value {
        font-size: 1.42rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
    }
    .metric-value--green {
        color: #15803d;
    }
    .summary-strip {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.75rem;
    }
    .summary-strip--featured {
        gap: 0.9rem;
        align-items: stretch;
    }
    .summary-strip--featured .metric-card {
        align-items: center;
        gap: 1rem;
        min-height: 110px;
        padding: 0.95rem 1rem;
        border-radius: 18px;
        border: 1px solid #cbd5e1;
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.055);
    }
    .summary-strip--featured .metric-card.metric-card--compact {
        min-height: 110px;
        padding: 0.95rem 1rem;
    }
    .summary-strip--featured .metric-icon {
        width: 66px !important;
        height: 66px !important;
        min-width: 66px !important;
        min-height: 66px !important;
        display: grid !important;
        place-items: center !important;
        padding: 0 !important;
        line-height: 0 !important;
        text-align: center !important;
        border-radius: 50% !important;
        background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
        border: 1px solid #bfdbfe;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.94);
    }
    .summary-strip--featured .metric-icon-inner {
        width: 34px !important;
        height: 34px !important;
        display: grid !important;
        place-items: center !important;
        line-height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    .summary-strip--featured .metric-icon svg {
        width: 34px !important;
        height: 34px !important;
        display: block !important;
        margin: 0 !important;
        flex-shrink: 0 !important;
        overflow: visible !important;
        vertical-align: middle !important;
    }
    .summary-strip--featured .metric-copy {
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-width: 0;
    }
    .summary-strip--featured .metric-label {
        font-size: 0.92rem;
        font-weight: 900;
        color: #475569;
        margin-bottom: 0.24rem;
        line-height: 1.2;
        letter-spacing: -0.01em;
        text-wrap: balance;
    }
    .summary-strip--featured .metric-value {
        font-size: 1.5rem;
        font-weight: 900;
        color: #0f172a;
        line-height: 1.08;
        letter-spacing: -0.02em;
    }
    .chart-surface {
        background: linear-gradient(180deg, #ffffff 0%, #fcfdff 100%);
        border: 1px solid #e5eefb;
        border-radius: 16px;
        padding: 0.5rem 0.55rem 0.15rem 0.55rem;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.92);
    }
    .profile-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        row-gap: 0.28rem;
        column-gap: 0.42rem;
        margin-top: 0.12rem;
        margin-bottom: 0.18rem;
    }
    .st-key-f2_card_e [data-testid="column"] > div {
        height: auto;
    }
    .st-key-f2_card_e [data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
        gap: 0.44rem !important;
    }
    .st-key-f2_card_e .section-title {
        font-size: 1.15rem;
        font-weight: 900;
        letter-spacing: -0.01em;
    }
    .st-key-f2_card_e .section-subtitle {
        font-size: 0.93rem;
        font-weight: 700;
        color: #64748b;
        line-height: 1.35;
    }
    .st-key-f2_card_e .metric-card--profile,
    .st-key-f2_card_e .metric-card--profile-combined,
    .st-key-f2_card_e .metric-card--profile-speed {
        margin-bottom: 0;
        min-height: 74px;
        padding: 0.56rem 0.72rem;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
        border: 1px solid #cbd5e1;
        border-radius: 16px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.035), inset 0 1px 0 rgba(255,255,255,0.9);
        gap: 0.54rem;
        align-items: center;
    }
    .st-key-f2_card_e .metric-card--profile .metric-icon,
    .st-key-f2_card_e .metric-card--profile-combined .metric-icon,
    .st-key-f2_card_e .metric-card--profile-speed .metric-icon {
        width: 48px;
        height: 48px;
        min-width: 48px;
        min-height: 48px;
        border-radius: 50%;
        background: linear-gradient(180deg, #f8fbff 0%, #eaf2ff 100%);
        border: 1px solid #cbd5e1;
        display: grid;
        place-items: center;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.94);
    }
    .st-key-f2_card_e .metric-icon.icon-color-wind svg,
    .st-key-f2_card_e .metric-icon.icon-color-wind svg * {
        stroke: #2563eb !important;
        color: #2563eb !important;
    }
    .st-key-f2_card_e .metric-icon.icon-color-param svg,
    .st-key-f2_card_e .metric-icon.icon-color-param svg * {
        stroke: #7c3aed !important;
        color: #7c3aed !important;
    }
    .st-key-f2_card_e .metric-icon.icon-color-combined svg,
    .st-key-f2_card_e .metric-icon.icon-color-combined svg * {
        stroke: #0f766e !important;
        color: #0f766e !important;
    }
    .st-key-f2_card_e .metric-card--profile .metric-icon-inner,
    .st-key-f2_card_e .metric-card--profile-combined .metric-icon-inner,
    .st-key-f2_card_e .metric-card--profile-speed .metric-icon-inner {
        width: 30px;
        height: 30px;
        display: grid;
        place-items: center;
    }
    .st-key-f2_card_e .metric-card--profile .metric-icon svg,
    .st-key-f2_card_e .metric-card--profile-combined .metric-icon svg,
    .st-key-f2_card_e .metric-card--profile-speed .metric-icon svg {
        width: 30px;
        height: 30px;
        display: block;
        overflow: visible;
    }
    .st-key-f2_card_e .metric-icon--log-exp-average .metric-icon-inner,
    .st-key-f2_card_e .metric-icon--log-exp-average svg {
        width: 34px !important;
        height: 34px !important;
    }
    .st-key-f2_card_e .metric-card--profile .metric-label,
    .st-key-f2_card_e .metric-card--profile-combined .metric-label,
    .st-key-f2_card_e .metric-card--profile-speed .metric-label {
        font-size: 0.96rem;
        font-weight: 900;
        color: #475569;
        margin-bottom: 0.16rem;
        line-height: 1.18;
        letter-spacing: -0.01em;
    }
    .st-key-f2_card_e .metric-card--profile .metric-value,
    .st-key-f2_card_e .metric-card--profile-combined .metric-value,
    .st-key-f2_card_e .metric-card--profile-speed .metric-value {
        font-size: 1.18rem;
        font-weight: 900;
        line-height: 1.08;
        letter-spacing: -0.02em;
    }
    .profile-secondary-row {
        display: grid;
        grid-template-columns: 0.9fr 2.1fr;
        row-gap: 0.28rem;
        column-gap: 0.42rem;
        align-items: stretch;
        margin-top: 0.1rem;
        margin-bottom: 0.14rem;
    }
    .profile-speed-panel {
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
        border: 1px solid #cbd5e1;
        border-radius: 18px;
        padding: 0.6rem 0.7rem 0.56rem 0.7rem;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03), inset 0 1px 0 rgba(255,255,255,0.92);
    }
    .profile-speed-title {
        font-size: 1.02rem;
        font-weight: 900;
        color: #1e3a8a;
        margin-bottom: 0.24rem;
        letter-spacing: -0.01em;
    }
    .profile-speed-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.42rem;
    }
    .profile-speed-grid [data-testid="column"] > div {
        height: 100%;
    }
    .st-key-f2_card_e .metric-card--profile-combined {
        min-height: 86px;
    }
    .st-key-f2_card_e .metric-card--profile-combined .metric-value {
        font-size: 1.34rem;
    }
    .profile-note {
        display: flex;
        align-items: center;
        gap: 0.85rem;
        margin-top: 0.35rem;
        margin-bottom: 0.6rem;
        padding: 0.6rem 0.74rem;
        border: 1px solid #bfdbfe;
        border-radius: 16px;
        background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%);
        color: #2563eb;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.94);
        min-height: auto !important;
    }
    .profile-note__icon {
        width: 40px;
        height: 40px;
        min-width: 40px;
        min-height: 40px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        background: #ffffff;
        border: 1px solid #bfdbfe;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.96);
    }
    .profile-note__icon svg {
        width: 22px;
        height: 22px;
        display: block;
    }
    .profile-note__text {
        font-size: 0.95rem;
        font-weight: 800;
        line-height: 1.35;
        color: #2563eb;
    }
    .st-key-f2_card_e,
    .st-key-f2_card_e [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_e [data-testid="stVerticalBlock"] {
        height: auto !important;
        min-height: unset !important;
        max-height: none !important;
        align-self: flex-start !important;
        flex: 0 0 auto !important;
    }
    .st-key-f2_card_e [data-testid="stVerticalBlock"] {
        gap: 0.3rem !important;
    }
    .st-key-f2_card_e .f2-e-compact {
        display: grid;
        row-gap: 0.3rem;
        margin-top: 0.08rem;
    }
    .st-key-f2_card_e .f2-e-grid-top {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.42rem;
    }
    .st-key-f2_card_e .f2-e-bottom {
        display: grid;
        grid-template-columns: 0.9fr 2.1fr;
        gap: 0.42rem;
        align-items: stretch;
    }
    .st-key-f2_card_e .f2-e-note {
        margin-top: 0.35rem;
        margin-bottom: 0.58rem;
    }
    .st-key-f2_card_e .f2-e-speed-panel {
        display: grid;
        row-gap: 0.24rem;
    }
    .st-key-f2_card_e .f2-e-speed-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.34rem;
    }
    @media (max-width: 1020px) {
        .st-key-f2_card_e .f2-e-grid-top,
        .st-key-f2_card_e .f2-e-bottom,
        .st-key-f2_card_e .f2-e-speed-grid {
            grid-template-columns: 1fr;
        }
    }
    .st-key-f2_card_e [data-testid="stVerticalBlockBorderWrapper"] {
        padding-top: 0.45rem !important;
        padding-bottom: 0.45rem !important;
    }
    .st-key-f2_card_e [data-testid="stVerticalBlock"] > div:last-child {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    .soft-note {
        background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%);
        border: 1px solid #cbd5e1;
        border-radius: 14px;
        padding: 0.8rem 0.95rem;
        color: #2563eb;
        margin-top: 0.35rem;
        margin-bottom: 0.35rem;
    }
    .soft-note.is-success {
        color: #2563eb;
    }
    /* â”€â”€ Upload dropzone wrapper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
    .st-key-f2_csv_dropzone_wrapper {
        border: 1.5px dashed #bfdbfe;
        border-radius: 14px;
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        padding: 0.78rem 0.78rem 0.52rem 0.78rem;
        margin-top: 0.25rem !important;
        margin-bottom: 0.2rem;
    }
    .st-key-f2_csv_dropzone_wrapper [data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }
    .upload-dropzone-top {
        text-align: center;
        margin-bottom: 0.04rem;
    }
    .f2-upload-zone {
        margin-top: 0.25rem !important;
    }
    .upload-dropzone__icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 72px !important;
        height: 72px !important;
        min-width: 72px !important;
        min-height: 72px !important;
        border-radius: 999px;
        background: #eff6ff;
        border: 1.5px solid #bfdbfe;
        margin: 0 auto 0.32rem auto;
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.12);
    }
    /* Variantes/compatibilidad: wrapper y circulo del icono upload */
    .f2-upload-icon-wrap,
    .f2-upload-icon-circle {
        width: 72px !important;
        height: 72px !important;
        min-width: 72px !important;
        min-height: 72px !important;
        border-radius: 999px !important;
    }
    /* SVG interno más grande y trazo más grueso */
    .upload-dropzone__icon svg,
    .f2-upload-icon-wrap svg,
    .f2-upload-icon svg,
    .f2-upload-zone svg,
    .f2-csv-dropzone-wrapper svg {
        width: 46px !important;
        height: 46px !important;
        stroke-width: 2.3 !important;
    }
    .upload-dropzone__title {
        color: #1e3a8a;
        font-size: 1rem;
        font-weight: 800;
        margin-bottom: 0.15rem;
    }
    .upload-dropzone__subtitle {
        color: #64748b;
        font-size: 0.85rem;
        font-weight: 700;
    }
    .upload-dropzone-bottom {
        text-align: center;
        color: #64748b;
        font-size: 0.85rem;
        font-weight: 700;
        margin-top: 0.45rem;
        margin-bottom: 0.35rem;
    }
    /* â”€â”€ Date field with calendar icon â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
    .f2-date-field {
        position: relative;
    }
    .f2-date-field .f2-cal-icon {
        position: absolute;
        right: 0.6rem;
        top: 50%;
        transform: translateY(-50%);
        pointer-events: none;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0.55;
    }
    /* â”€â”€ Inline status message with check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
    .f2-status-inline {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        background: #eff6ff !important;
        border: 1px solid #bfdbfe !important;
        border-radius: 14px !important;
        padding: 1rem 1.1rem;
        margin-top: 0.2rem;
        margin-bottom: 0;
        min-height: 82px !important;
        font-weight: 800 !important;
        line-height: 1.35 !important;
    }
    .f2-status-check {
        width: 46px !important;
        height: 46px !important;
        min-width: 46px !important;
        border-radius: 999px;
        background: #e9f1ff;
        border: 3px solid #2563eb;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.14);
    }
    .f2-status-check svg {
        width: 26px !important;
        height: 26px !important;
        stroke-width: 2.7 !important;
    }
    .f2-status-text {
        font-size: 1rem;
        font-weight: 800;
        line-height: 1.3;
        color: #1e40af;
    }
    /* â”€â”€ Button icon prefix â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
    .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button p::before {
        content: "";
        display: none;
    }
    .ab-card-shell {
        display: flex;
        flex-direction: column;
        gap: 0.8rem;
    }
    .ab-card-block {
        margin-top: 0.12rem;
    }
    .ab-actions-row {
        margin-top: 0.2rem;
    }
    .ab-actions-row [data-testid="column"] {
        display: flex;
    }
    .ab-actions-row [data-testid="column"] > div {
        width: 100%;
    }
    .st-key-f2_card_header [data-testid="stVerticalBlockBorderWrapper"] {
        background: #f8fbff !important;
        border: 2px solid #aebcd2 !important;
        border-radius: 18px !important;
        box-shadow:
            0 0 0 1px rgba(148, 163, 184, 0.35),
            0 6px 14px rgba(15, 23, 42, 0.13),
            0 2px 6px rgba(37, 99, 235, 0.10) !important;
    }
    .f2-card-b-status {
        margin-top: 0 !important;
    }

    .st-key-f2_card_a .section-header,
    .st-key-f2_card_gwa_a .section-header {
        align-items: center;
        margin-bottom: 1rem;
    }
    .st-key-f2_card_b .section-header,
    .st-key-f2_card_gwa_b .section-header {
        align-items: center;
        margin-bottom: 0.4rem;
    }
    .st-key-f2_card_a .section-badge,
    .st-key-f2_card_b .section-badge,
    .st-key-f2_card_gwa_a .section-badge,
    .st-key-f2_card_gwa_b .section-badge {
        width: 2rem;
        height: 2rem;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);
    }
    .st-key-f2_card_a .section-title,
    .st-key-f2_card_b .section-title,
    .st-key-f2_card_gwa_a .section-title,
    .st-key-f2_card_gwa_b .section-title {
        font-size: 1.14rem;
        color: #1e3a8a;
    }
    .st-key-f2_card_a .section-subtitle,
    .st-key-f2_card_b .section-subtitle,
    .st-key-f2_card_gwa_a .section-subtitle,
    .st-key-f2_card_gwa_b .section-subtitle {
        margin-top: 0.16rem;
        line-height: 1.35;
    }
    .st-key-f2_card_a [data-testid="stVerticalBlock"] > div:has(iframe),
    .st-key-f2_card_a [data-testid="stVerticalBlock"] > div:has([title="st.iframe"]),
    .st-key-f2_card_gwa_a [data-testid="stVerticalBlock"] > div:has(iframe),
    .st-key-f2_card_gwa_a [data-testid="stVerticalBlock"] > div:has([title="st.iframe"]) {
        margin-bottom: 0.35rem;
    }
    .st-key-f2_card_a iframe,
    .st-key-f2_card_gwa_a iframe {
        border-radius: 16px;
        border: 1px solid #cbd5e1;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.9);
    }
    .st-key-f2_card_a [data-testid="stExpander"] {
        margin-top: 0.05rem;
        margin-bottom: 0.2rem;
    }
    .st-key-f2_card_a .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button {
        min-height: 52px;
        font-size: 1rem !important;
    }
    .st-key-f2_csv_dropzone_wrapper [data-testid="stFileUploader"],
    .st-key-f2_gwa_dropzone_wrapper [data-testid="stFileUploader"] {
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
    .st-key-f2_csv_dropzone_wrapper [data-testid="stFileUploader"] section,
    .st-key-f2_gwa_dropzone_wrapper [data-testid="stFileUploader"] section {
        border: none !important;
        background: transparent !important;
        padding: 0.4rem 0 !important;
        min-height: auto !important;
    }
    .st-key-f2_csv_dropzone_wrapper [data-testid="stFileUploaderDropzone"],
    .st-key-f2_gwa_dropzone_wrapper [data-testid="stFileUploaderDropzone"] {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 0 !important;
    }
    .st-key-f2_csv_dropzone_wrapper [data-testid="stFileUploaderDropzoneInstructions"],
    .st-key-f2_gwa_dropzone_wrapper [data-testid="stFileUploaderDropzoneInstructions"] {
        display: none !important;
    }
    .st-key-f2_card_b [data-testid="stNumberInput"] {
        margin-top: 0.05rem;
        margin-bottom: 0.05rem;
    }
    .st-key-f2_card_b [data-testid="stButton"] > button {
        min-height: 68px !important;
    }
    .st-key-f2_card_b .soft-note,
    .st-key-f2_card_b [data-testid="stAlert"] {
        margin-top: 0.3rem;
    }
    .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button {
        background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        border-color: #2563eb !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    }
    .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button:hover {
        background: linear-gradient(180deg, #1d4ed8 0%, #1e40af 100%) !important;
        border-color: #1d4ed8 !important;
    }
    /* ── Consultar Open-Meteo: same blue gradient as NASA POWER button ── */
    .st-key-f2_card_gwa_a [data-testid="stButton"] > button[kind="primaryFormSubmit"],
    .st-key-f2_card_gwa_a [data-testid="stButton"] > button[data-testid="baseButton-primary"],
    .st-key-f2_card_gwa_a [data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        border-color: #2563eb !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
    }
    .st-key-f2_card_gwa_a [data-testid="stButton"] > button[kind="primaryFormSubmit"]:hover,
    .st-key-f2_card_gwa_a [data-testid="stButton"] > button[data-testid="baseButton-primary"]:hover,
    .st-key-f2_card_gwa_a [data-testid="stButton"] > button[kind="primary"]:hover {
        background: linear-gradient(180deg, #1d4ed8 0%, #1e40af 100%) !important;
        border-color: #1d4ed8 !important;
    }
    .subpanel-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 16px;
        padding: 0.75rem 0.8rem 0.7rem 0.8rem;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.9);
        margin-bottom: 0.75rem;
    }
    .subpanel-title {
        font-size: 0.96rem;
        font-weight: 760;
        color: #1d4ed8;
        margin-bottom: 0.5rem;
    }
    /* Bloque F: tarjetas de gráficas individuales */
    .st-key-f2_card_f [data-testid="stVerticalBlockBorderWrapper"] {
        padding-top: 0.58rem !important;
        padding-bottom: 0.58rem !important;
    }
    .st-key-f2_card_f [data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
        gap: 0.6rem !important;
    }
    .st-key-f2_card_f [data-testid="column"] > div {
        height: 100%;
    }
    .st-key-f2_card_f .subpanel-card {
        display: flex;
        flex-direction: column;
        height: 100%;
        margin-bottom: 0 !important;
        padding: 0.76rem 0.8rem 0.62rem 0.8rem;
        border: 1px solid #dbe5f1;
        border-radius: 18px;
        background: #ffffff;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.03);
        gap: 0.18rem;
    }
    .st-key-f2_card_f .subpanel-title {
        font-size: 0.98rem;
        font-weight: 900;
        line-height: 1.22;
        letter-spacing: -0.01em;
        margin-bottom: 0.28rem;
        color: #1e3a8a;
        text-align: center;
    }
    .st-key-f2_card_f [data-testid="stPlotlyChart"] {
        margin-top: -0.12rem !important;
        margin-bottom: -0.08rem !important;
        border-radius: 12px;
        overflow: hidden;
    }
    .st-key-f2_f_chart_card_1 [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_f_chart_card_2 [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_f_chart_card_3 [data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        border: 1.2px solid #cbd5e1 !important;
        border-radius: 24px !important;
        overflow: hidden !important;
        box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04) !important;
        padding: 0.52rem 0.66rem 0.5rem 0.66rem !important;
    }
    .st-key-f2_f_chart_card_1 [data-testid="stVerticalBlock"],
    .st-key-f2_f_chart_card_2 [data-testid="stVerticalBlock"],
    .st-key-f2_f_chart_card_3 [data-testid="stVerticalBlock"] {
        gap: 0.14rem !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 24px !important;
        background: transparent !important;
    }
    .f2-f-chart-header {
        font-size: 0.99rem;
        font-weight: 900;
        line-height: 1.24;
        letter-spacing: -0.01em;
        color: #1e3a8a;
        text-align: center;
        margin-bottom: 0.08rem;
        padding: 0.04rem 0.12rem 0.28rem 0.12rem;
        border-bottom: 1px solid #eef4fb;
    }
    .st-key-f2_g_chart_card_1 [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_g_chart_card_2 [data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        border: 1.3px solid #cbd5e1 !important;
        border-radius: 28px !important;
        overflow: hidden !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        padding: 0.52rem 0.66rem 0.5rem 0.66rem !important;
        min-height: 660px !important;
    }
    .st-key-f2_g_chart_card_1 [data-testid="stVerticalBlock"],
    .st-key-f2_g_chart_card_2 [data-testid="stVerticalBlock"] {
        gap: 0.14rem !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 28px !important;
        background: transparent !important;
        min-height: 620px !important;
    }
    .st-key-f2_g_chart_card_1,
    .st-key-f2_g_chart_card_2 {
        border-radius: 28px !important;
        border: 1.3px solid #cbd5e1 !important;
        overflow: hidden !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    }
    .st-key-f2_g_chart_card_1 [data-testid="stPlotlyChart"],
    .st-key-f2_g_chart_card_2 [data-testid="stPlotlyChart"] {
        min-height: 590px !important;
        margin-top: 0.12rem !important;
    }
    .f2-g-chart-header {
        text-align: center !important;
        font-weight: 900 !important;
        color: #0f2f78 !important;
        padding: 0.75rem 1rem 0.65rem 1rem !important;
        border-bottom: 1px solid #eef4fb !important;
        background: #ffffff !important;
        line-height: 1.22 !important;
    }
    .f2-g-chart-caption {
        text-align: center;
        color: #64748b;
        font-size: 0.9rem;
        margin: 0.15rem 0 0.2rem 0;
        font-weight: 600;
    }
    .comparison-caption {
        color: #64748b;
        font-size: 0.92rem;
        margin-bottom: 0.35rem;
    }
    .final-expanders [data-testid="stExpander"] {
        border: 1px solid #d6e6f7 !important;
        border-radius: 20px !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.055), inset 0 1px 0 rgba(255,255,255,0.94) !important;
        margin-bottom: 0.78rem;
        overflow: hidden;
    }
    .final-expanders [data-testid="stExpander"] summary {
        min-height: 58px !important;
        padding: 0.72rem 1rem !important;
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%) !important;
        border-radius: 18px !important;
        color: #1e3a8a !important;
        letter-spacing: -0.01em;
        display: flex !important;
        align-items: center !important;
        gap: 0.72rem !important;
    }
    .final-expanders [data-testid="stExpander"] summary::before {
        content: "";
        width: 34px;
        height: 34px;
        min-width: 34px;
        border-radius: 999px;
        display: inline-block;
        background:
            linear-gradient(180deg, rgba(37, 99, 235, 0.94), rgba(11, 99, 246, 0.82)),
            #eff6ff;
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.14), inset 0 0 0 7px #eff6ff;
        border: 1px solid #bfdbfe;
    }
    .final-expanders [data-testid="stExpander"] summary:hover {
        background: #f4f8ff !important;
    }
    .final-expanders [data-testid="stExpander"] summary p,
    .final-expanders [data-testid="stExpander"] summary span {
        color: #243b5a !important;
        font-weight: 900 !important;
        font-size: 0.98rem !important;
    }
    .f2-table-panel-header {
        display: flex;
        align-items: center;
        gap: 0.82rem;
        padding: 0.85rem 0.92rem;
        margin: 0.16rem 0 0.68rem 0;
        border: 1px solid #cbd5e1;
        border-radius: 18px;
        background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.035), inset 0 1px 0 rgba(255,255,255,0.94);
    }
    .f2-table-panel-icon {
        width: 42px;
        height: 42px;
        min-width: 42px;
        display: grid;
        place-items: center;
        border-radius: 999px;
        background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%);
        border: 1px solid #bfdbfe;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.96);
    }
    .f2-table-title {
        color: #1e3a8a;
        font-size: 1rem;
        font-weight: 900;
        line-height: 1.1;
        letter-spacing: -0.01em;
    }
    .f2-table-subtitle {
        color: #526a88;
        font-size: 0.82rem;
        font-weight: 700;
        line-height: 1.25;
        margin-top: 0.12rem;
    }
    .f2-table-summary-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.68rem;
        margin: 0.24rem 0 0.78rem 0;
    }
    .f2-table-summary-card {
        display: flex;
        align-items: center;
        gap: 0.62rem;
        min-height: 72px;
        padding: 0.68rem 0.72rem;
        border: 1px solid #cbd5e1;
        border-radius: 16px;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.04);
    }
    .f2-table-summary-icon {
        width: 54px !important;
        height: 54px !important;
        min-width: 54px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        border-radius: 999px !important;
        background: #eff6ff !important;
        border: 1px solid #bfdbfe !important;
    }
    .f2-table-summary-icon svg {
        width: 30px !important;
        height: 30px !important;
        display: block !important;
    }
    .f2-table-summary-copy {
        min-width: 0;
    }
    .f2-table-summary-label {
        color: #64748b;
        font-size: 0.76rem;
        font-weight: 800;
        margin-bottom: 0.14rem;
    }
    .f2-table-summary-value {
        color: #0f172a;
        font-size: 1.02rem;
        font-weight: 900;
        line-height: 1.08;
    }
    .f2-table-info-banner {
        display: flex;
        align-items: center;
        gap: 0.62rem;
        padding: 0.66rem 0.78rem;
        margin: 0.24rem 0 0.7rem 0;
        border: 1px solid #bfdbfe;
        border-radius: 16px;
        background: linear-gradient(180deg, #eff6ff 0%, #eaf3ff 100%);
        color: #1e5fbf;
        font-size: 0.86rem;
        font-weight: 800;
    }
    .f2-table-info-banner svg {
        width: 18px !important;
        height: 18px !important;
        padding: 6px;
        box-sizing: content-box;
        border-radius: 999px;
        background: #ffffff;
        border: 1px solid #bfdbfe;
    }
    .final-expanders [data-testid="stDataFrame"] {
        background: #ffffff !important;
        border: 1px solid #d7e7fb !important;
        border-radius: 16px !important;
        overflow: hidden !important;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.035) !important;
    }
    .final-expanders [data-testid="stDataFrame"] * {
        border-color: #e3edf8 !important;
    }
    .final-expanders [data-testid="stDataFrame"] [role="columnheader"] {
        background: #f1f7ff !important;
        color: #31527a !important;
        font-weight: 800 !important;
        border-bottom: 1px solid #d7e7fb !important;
    }
    .final-expanders [data-testid="stDataFrame"] [role="gridcell"],
    .final-expanders [data-testid="stDataFrame"] [role="cell"],
    .final-expanders [data-testid="stDataFrame"] [role="rowheader"] {
        background: #ffffff !important;
        color: #102a56 !important;
        font-weight: 650 !important;
        border-color: #e3edf8 !important;
    }
    .final-expanders [data-testid="stDataFrame"] [role="row"]:nth-child(even) [role="gridcell"],
    .final-expanders [data-testid="stDataFrame"] [role="row"]:nth-child(even) [role="cell"],
    .final-expanders [data-testid="stDataFrame"] [role="row"]:nth-child(even) [role="rowheader"] {
        background: #fbfdff !important;
    }
    .final-expanders [data-testid="stDataFrame"] canvas {
        background: #ffffff !important;
    }
    .st-key-f2_nasa_preview_controls_white [data-testid="stSelectbox"] label,
    .st-key-f2_nasa_preview_controls_white [data-testid="stNumberInput"] label,
    .st-key-f2_profiles_preview_controls_white [data-testid="stSelectbox"] label,
    .st-key-f2_profiles_preview_controls_white [data-testid="stNumberInput"] label {
        color: #475569 !important;
        font-weight: 800 !important;
        font-size: 0.82rem !important;
    }
    .st-key-f2_nasa_preview_controls_white div[data-testid="stSelectbox"] div[data-baseweb="select"],
    .st-key-f2_profiles_preview_controls_white div[data-testid="stSelectbox"] div[data-baseweb="select"] {
        background-color: #ffffff !important;
    }
    .st-key-f2_nasa_preview_controls_white div[data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    .st-key-f2_profiles_preview_controls_white div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: 1px solid #d7e7fb !important;
        color: #102a56 !important;
        box-shadow: none !important;
    }
    .st-key-f2_nasa_preview_controls_white div[data-testid="stNumberInput"] div[data-baseweb="input"],
    .st-key-f2_profiles_preview_controls_white div[data-testid="stNumberInput"] div[data-baseweb="input"] {
        background-color: #ffffff !important;
        border-color: #d7e7fb !important;
        box-shadow: none !important;
        border-radius: 12px !important;
    }
    .st-key-f2_nasa_preview_controls_white div[data-testid="stNumberInput"] input,
    .st-key-f2_profiles_preview_controls_white div[data-testid="stNumberInput"] input {
        background-color: #ffffff !important;
        color: #102a56 !important;
        font-weight: 700 !important;
        border-color: #d7e7fb !important;
        box-shadow: none !important;
    }
    .st-key-f2_nasa_preview_controls_white div[data-testid="stNumberInput"] button,
    .st-key-f2_profiles_preview_controls_white div[data-testid="stNumberInput"] button {
        background-color: #ffffff !important;
        border: 1px solid #d7e7fb !important;
        color: #0b4edb !important;
        box-shadow: none !important;
    }
    .st-key-f2_nasa_preview_controls_white div[data-testid="stNumberInput"] button:hover,
    .st-key-f2_profiles_preview_controls_white div[data-testid="stNumberInput"] button:hover {
        background-color: #f1f7ff !important;
        border-color: #9ec5ff !important;
        color: #0057ff !important;
    }
    .st-key-f2_nasa_preview_controls_white div[data-testid="stNumberInput"] button:focus,
    .st-key-f2_profiles_preview_controls_white div[data-testid="stNumberInput"] button:focus {
        background-color: #ffffff !important;
        border-color: #9ec5ff !important;
        box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
    }
    .final-expanders div[data-testid="stDownloadButton"] > button {
        border: 1.5px solid #93c5fd !important;
        border-radius: 16px !important;
        background: #ffffff !important;
        color: #1d4ed8 !important;
        font-weight: 900 !important;
        min-height: 46px !important;
        box-shadow: 0 8px 18px rgba(37, 99, 235, 0.08) !important;
    }
    .final-expanders div[data-testid="stDownloadButton"] > button:hover {
        background: #f4f8ff !important;
        border-color: #60a5fa !important;
    }
    @media (max-width: 1100px) {
        .f2-table-summary-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
    .comparison-layout {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.75rem;
        align-items: start;
    }
    .comparison-layout .subpanel-card {
        margin-bottom: 0;
        min-height: 100%;
    }
    /* Layout puntual: evitar estiramiento vertical del bloque B */
    .st-key-f2_card_b,
    .st-key-f2_card_b [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_b [data-testid="stVerticalBlock"],
    .st-key-f2_card_gwa_b,
    .st-key-f2_card_gwa_b [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_gwa_b [data-testid="stVerticalBlock"] {
        min-height: unset !important;
        height: auto !important;
        flex: 0 0 auto !important;
        align-self: flex-start !important;
    }
    .st-key-f2_card_b [data-testid="stVerticalBlock"] > div:last-child,
    .st-key-f2_card_gwa_b [data-testid="stVerticalBlock"] > div:last-child {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    /* â"€â"€ GWA: dropzone dashed border â"€â"€ */
    .st-key-f2_gwa_dropzone_wrapper {
        border: 1.5px dashed #bfdbfe;
        border-radius: 14px;
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
        padding: 0.78rem 0.78rem 0.52rem 0.78rem;
        margin-top: 0.25rem !important;
        margin-bottom: 0.2rem;
    }
    .st-key-f2_gwa_dropzone_wrapper [data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }
    /* â"€â"€ GWA link button styling â"€â"€ */
    .st-key-f2_card_gwa_a a[data-testid="baseLinkButton-secondary"] {
        background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: #ffffff !important;
        border-color: #2563eb !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        min-height: 52px;
        font-size: 1rem !important;
        border-radius: 14px !important;
    }
    .st-key-f2_card_gwa_a a[data-testid="baseLinkButton-secondary"]:hover {
        background: linear-gradient(180deg, #1d4ed8 0%, #1e40af 100%) !important;
        border-color: #1d4ed8 !important;
    }
    .st-key-f2_card_gwa_a a[data-testid="baseLinkButton-secondary"] p {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    /* ── GWA Lat/Lon inputs: mirror NASA styling ── */
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-testid="stNumberInput"],
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-testid="stNumberInput"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        overflow: visible;
    }
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-baseweb="input"],
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-baseweb="input"] {
        background: #ffffff !important;
        border: 1.5px solid #bfdbfe !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.07), inset 0 1px 0 rgba(255,255,255,0.9) !important;
        transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
        overflow: hidden !important;
    }
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-baseweb="input"]:focus-within,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-baseweb="input"]:focus-within {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12), 0 4px 12px rgba(37, 99, 235, 0.10) !important;
    }
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-baseweb="base-input"],
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-baseweb="base-input"],
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-baseweb="input"] > div,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-baseweb="input"] > div {
        background-color: transparent !important;
        background: transparent !important;
    }
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-testid="stNumberInput"] input,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-testid="stNumberInput"] input {
        font-weight: 700 !important;
        font-size: 1rem !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0.6rem 0.75rem !important;
        color: inherit !important;
    }
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-testid="stNumberInput"] button,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-testid="stNumberInput"] button {
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%) !important;
        border: none !important;
        border-left: 1px solid #e0eaff !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        color: #2563eb !important;
        font-weight: 700 !important;
        min-height: unset !important;
        padding: 0 0.55rem !important;
        transition: background 0.15s ease !important;
    }
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-testid="stNumberInput"] button:hover,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-testid="stNumberInput"] button:hover {
        background: #eff6ff !important;
    }
    /* Acabado visual global Fase 2: bordes suaves y redondez consistente */
    .st-key-f2_card_header [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_a [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_b [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_gwa_a [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_gwa_b [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_c [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_d [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_e [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_f [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_g [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_final [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_empty [data-testid="stVerticalBlockBorderWrapper"],
    .subpanel-card,
    .metric-card,
    .profile-speed-panel,
    .chart-surface,
    .soft-note,
    .f2-status-inline,
    .st-key-f2_csv_dropzone_wrapper,
    .st-key-f2_gwa_dropzone_wrapper {
        border: 1px solid #dbe5f1 !important;
        border-radius: 16px !important;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
        background: #ffffff !important;
    }
    .st-key-f2_card_gwa_a > div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_gwa_b > div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff !important;
        border-radius: 18px !important;
        border: 1px solid #e8eef7 !important;
        padding: 1.5rem !important;
    }
    .st-key-f2_card_a [data-testid="stNumberInput"] [data-baseweb="input"],
    .st-key-f2_card_b [data-testid="stNumberInput"] [data-baseweb="input"],
    .st-key-f2_card_gwa_a [data-testid="stNumberInput"] [data-baseweb="input"],
    .st-key-f2_card_gwa_b [data-testid="stNumberInput"] [data-baseweb="input"],
    .st-key-f2_fecha_inicio [data-baseweb="input"],
    .st-key-f2_fecha_fin [data-baseweb="input"],
    .st-key-f2_gwa_inicio [data-baseweb="input"],
    .st-key-f2_gwa_fin [data-baseweb="input"] {
        border: 1px solid #dbe5f1 !important;
        border-radius: 14px !important;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
        background: #ffffff !important;
    }
    .st-key-f2_card_a [data-testid="stExpander"],
    .st-key-f2_card_b [data-testid="stAlert"],
    .st-key-f2_card_b .f2-status-inline {
        border-radius: 16px !important;
    }
    .st-key-f2_card_b [data-testid="stButton"] > button,
    .st-key-f2_card_a [data-testid="stButton"] > button,
    .st-key-f2_card_gwa_a [data-testid="stButton"] > button,
    .st-key-f2_card_gwa_b [data-testid="stButton"] > button,
    .st-key-f2_card_c [data-testid="stButton"] > button,
    .st-key-f2_card_d [data-testid="stButton"] > button,
    .st-key-f2_card_e [data-testid="stButton"] > button,
    .st-key-f2_card_f [data-testid="stButton"] > button,
    .st-key-f2_card_g [data-testid="stButton"] > button {
        border: 1px solid #dbe5f1 !important;
        border-radius: 14px !important;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
    }
    @media (max-width: 1200px) {
        .summary-strip,
        .profile-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .profile-secondary-row,
        .comparison-layout {
            grid-template-columns: 1fr;
        }
    }
    @media (max-width: 760px) {
        .hero-card {
            padding: 1.2rem 1.1rem 1.1rem 1.1rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.95rem 0.85rem 0.9rem 0.85rem;
        }
        .summary-strip,
        .profile-grid,
        .profile-speed-grid,
        .comparison-layout {
            grid-template-columns: 1fr;
        }
        .upload-dropzone {
            padding: 1rem 0.85rem 0.85rem 0.85rem;
            min-height: 188px;
        }
        .st-key-f2_card_a .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button {
            max-width: 100%;
        }
    }
    /* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
    /* â”€â”€ FASE 2: Negrilla global en todos los textos visibles â”€â”€â”€ */
    /* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

    /* Título principal hero */
    .hero-card div[style*="font-size: 2.1rem"] {
        font-weight: 800 !important;
    }
    /* Subtítulo hero */
    .hero-card .muted-text {
        font-weight: 700 !important;
    }
    /* Títulos de secciones A, B, etc. */
    .section-title, .section-badge {
        font-weight: 800 !important;
    }
    /* Subtítulos de secciones */
    .section-subtitle {
        font-weight: 700 !important;
    }
    /* Labels de todos los widgets Streamlit */
    label p,
    label div p,
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] span {
        font-weight: 700 !important;
    }
    /* Texto dentro de inputs de texto y fechas */
    [data-testid="stDateInputField"] input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextInput"] input {
        font-weight: 700 !important;
    }
    /* Texto de todos los botones */
    div[data-testid="stButton"] > button p,
    div[data-testid="stButton"] > button span,
    div[data-testid="stDownloadButton"] > button p {
        font-weight: 700 !important;
    }
    /* Texto de expanders */
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span {
        font-weight: 700 !important;
    }
    /* Texto del mensaje de estado (f2-status-inline) */
    .f2-status-text {
        font-weight: 700 !important;
    }
    /* Subtitulo upload-dropzone */
    .upload-dropzone__title {
        font-weight: 800 !important;
    }
    .upload-dropzone__subtitle,
    .upload-dropzone__hint {
        font-weight: 700 !important;
    }
    /* Metric cards y subpanels */
    .metric-card-label {
        font-weight: 700 !important;
    }
    .metric-card-value {
        font-weight: 800 !important;
    }
    .subpanel-title {
        font-weight: 800 !important;
    }
    .comparison-caption {
        font-weight: 700 !important;
    }
    /* Captions de Streamlit */
    [data-testid="stCaptionContainer"] p {
        font-weight: 600 !important;
    }
    /* Textos generales en bloques de Fase 2 */
    .st-key-f2_card_header p,
    .st-key-f2_card_a p,
    .st-key-f2_card_b p {
        font-weight: 700 !important;
    }
    /* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
    /* â”€â”€ BLOQUE A: Inputs premium (Lat, Lon, Fechas) â”€â”€ */
    /* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

    /* â”€â”€ Lat/Lon/Altura: reset outer container, borde solo en el inner input-box */
    .st-key-f2_card_a .st-key-f2_latitude  [data-testid="stNumberInput"],
    .st-key-f2_card_a .st-key-f2_longitude [data-testid="stNumberInput"],
    .st-key-f2_card_b .st-key-f2_altura    [data-testid="stNumberInput"],
    .st-key-f2_card_gwa_b .st-key-f2_altura    [data-testid="stNumberInput"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        overflow: visible;
    }

    /* Contenedor INTERNO: input + botones (sin el label) */
    .st-key-f2_card_a .st-key-f2_latitude  [data-baseweb="input"],
    .st-key-f2_card_a .st-key-f2_longitude [data-baseweb="input"],
    .st-key-f2_card_b .st-key-f2_altura    [data-baseweb="input"],
    .st-key-f2_card_gwa_b .st-key-f2_altura    [data-baseweb="input"] {
        background: #ffffff !important; /* Fondo blanco base para el input */
        border: 1.5px solid #bfdbfe !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.07), inset 0 1px 0 rgba(255,255,255,0.9) !important;
        transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
        overflow: hidden !important;
    }
    .st-key-f2_card_a .st-key-f2_latitude  [data-baseweb="input"]:focus-within,
    .st-key-f2_card_a .st-key-f2_longitude [data-baseweb="input"]:focus-within,
    .st-key-f2_card_b .st-key-f2_altura    [data-baseweb="input"]:focus-within,
    .st-key-f2_card_gwa_b .st-key-f2_altura    [data-baseweb="input"]:focus-within {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12), 0 4px 12px rgba(37, 99, 235, 0.10) !important;
    }

    /* Limpiar fondos grises internos heredados en Lat/Lon/Altura */
    .st-key-f2_card_a .st-key-f2_latitude  [data-baseweb="base-input"],
    .st-key-f2_card_a .st-key-f2_longitude [data-baseweb="base-input"],
    .st-key-f2_card_b .st-key-f2_altura    [data-baseweb="base-input"],
    .st-key-f2_card_gwa_b .st-key-f2_altura    [data-baseweb="base-input"],
    .st-key-f2_card_a .st-key-f2_latitude  [data-baseweb="input"] > div,
    .st-key-f2_card_a .st-key-f2_longitude [data-baseweb="input"] > div,
    .st-key-f2_card_b .st-key-f2_altura    [data-baseweb="input"] > div,
    .st-key-f2_card_gwa_b .st-key-f2_altura    [data-baseweb="input"] > div {
        background-color: transparent !important;
        background: transparent !important;
    }

    /* Input de texto dentro de Latitud y Longitud */
    .st-key-f2_card_a .st-key-f2_latitude  [data-testid="stNumberInput"] input,
    .st-key-f2_card_a .st-key-f2_longitude [data-testid="stNumberInput"] input {
        font-weight: 700 !important;
        font-size: 1rem !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0.6rem 0.75rem !important;
        color: inherit !important;
    }
    
    /* Input de Altura deseada más compacto */
    .st-key-f2_card_b .st-key-f2_altura [data-testid="stNumberInput"] input,
    .st-key-f2_card_gwa_b .st-key-f2_altura [data-testid="stNumberInput"] input {
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0.45rem 0.75rem !important;
        color: inherit !important;
    }

    /* Botones +/- del number input: con ligero gradiente/diferenciación */
    .st-key-f2_card_a .st-key-f2_latitude  [data-testid="stNumberInput"] button,
    .st-key-f2_card_a .st-key-f2_longitude [data-testid="stNumberInput"] button,
    .st-key-f2_card_b .st-key-f2_altura    [data-testid="stNumberInput"] button,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-testid="stNumberInput"] button,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-testid="stNumberInput"] button,
    .st-key-f2_card_gwa_b .st-key-f2_altura    [data-testid="stNumberInput"] button {
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%) !important;
        border: none !important;
        border-left: 1px solid #e0eaff !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        color: #2563eb !important;
        font-weight: 700 !important;
        min-height: unset !important;
        padding: 0 0.55rem !important;
        transition: background 0.15s ease !important;
    }
    .st-key-f2_card_a .st-key-f2_latitude  [data-testid="stNumberInput"] button:hover,
    .st-key-f2_card_a .st-key-f2_longitude [data-testid="stNumberInput"] button:hover,
    .st-key-f2_card_b .st-key-f2_altura    [data-testid="stNumberInput"] button:hover,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_latitude  [data-testid="stNumberInput"] button:hover,
    .st-key-f2_card_gwa_a .st-key-f2_gwa_longitude [data-testid="stNumberInput"] button:hover,
    .st-key-f2_card_gwa_b .st-key-f2_altura    [data-testid="stNumberInput"] button:hover {
        background: #eff6ff !important;
    }

    /* â”€â”€ Fechas: reset outer container */
    .st-key-f2_fecha_inicio [data-testid="stDateInputField"],
    .st-key-f2_fecha_fin    [data-testid="stDateInputField"],
    .st-key-f2_gwa_inicio   [data-testid="stDateInputField"],
    .st-key-f2_gwa_fin      [data-testid="stDateInputField"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        overflow: visible !important;
    }

    /* â”€â”€ Fechas: Contenedor INTERNO (input + icono) */
    .st-key-f2_fecha_inicio [data-baseweb="input"],
    .st-key-f2_fecha_fin    [data-baseweb="input"],
    .st-key-f2_gwa_inicio   [data-baseweb="input"],
    .st-key-f2_gwa_fin      [data-baseweb="input"] {
        background: #ffffff !important;
        border: 1.5px solid #bfdbfe !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.07), inset 0 1px 0 rgba(255,255,255,0.9) !important;
        transition: border-color 0.18s ease, box-shadow 0.18s ease !important;
        overflow: hidden !important;
    }
    .st-key-f2_fecha_inicio [data-baseweb="input"]:focus-within,
    .st-key-f2_fecha_fin    [data-baseweb="input"]:focus-within,
    .st-key-f2_gwa_inicio   [data-baseweb="input"]:focus-within,
    .st-key-f2_gwa_fin      [data-baseweb="input"]:focus-within {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12), 0 4px 12px rgba(37, 99, 235, 0.10) !important;
    }

    /* Limpiar parches grises en zona derecha o wrappers internos de las fechas */
    .st-key-f2_fecha_inicio [data-baseweb="base-input"],
    .st-key-f2_fecha_fin    [data-baseweb="base-input"],
    .st-key-f2_gwa_inicio   [data-baseweb="base-input"],
    .st-key-f2_gwa_fin      [data-baseweb="base-input"],
    .st-key-f2_fecha_inicio [data-baseweb="input"] > div,
    .st-key-f2_fecha_fin    [data-baseweb="input"] > div,
    .st-key-f2_gwa_inicio   [data-baseweb="input"] > div,
    .st-key-f2_gwa_fin      [data-baseweb="input"] > div {
        background-color: transparent !important;
        background: transparent !important;
    }

    /* Input de texto dentro de las fechas (valor mostrado) */
    .st-key-f2_fecha_inicio input,
    .st-key-f2_fecha_fin    input,
    .st-key-f2_gwa_inicio   input,
    .st-key-f2_gwa_fin      input {
        font-weight: 700 !important;
        font-size: 0.97rem !important;
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 0 !important;
        padding: 0.6rem 2.2rem 0.6rem 0.75rem !important;
        color: inherit !important;
    }

    /* ── Calendar icon on date fields ── */
    .st-key-f2_fecha_inicio [data-baseweb="input"],
    .st-key-f2_fecha_fin    [data-baseweb="input"],
    .st-key-f2_gwa_inicio   [data-baseweb="input"],
    .st-key-f2_gwa_fin      [data-baseweb="input"] {
        position: relative !important;
    }
    .st-key-f2_fecha_inicio [data-baseweb="input"]::after,
    .st-key-f2_fecha_fin    [data-baseweb="input"]::after,
    .st-key-f2_gwa_inicio   [data-baseweb="input"]::after,
    .st-key-f2_gwa_fin      [data-baseweb="input"]::after {
        content: "" !important;
        position: absolute !important;
        right: 0.7rem !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        width: 16px !important;
        height: 16px !important;
        pointer-events: none !important;
        background-image: url("data:image/svg+xml;utf8,%3Csvg width='16' height='16' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' stroke='%2364748b' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round' fill='none'%3E%3Crect x='3' y='4' width='18' height='18' rx='2'/%3E%3Cpath d='M16 2v4M8 2v4M3 10h18'/%3E%3C/svg%3E") !important;
        background-repeat: no-repeat !important;
        background-position: center !important;
        background-size: 16px 16px !important;
        opacity: 0.95 !important;
    }
    .st-key-f2_fecha_inicio input,
    .st-key-f2_fecha_fin   input,
    .st-key-f2_gwa_inicio  input,
    .st-key-f2_gwa_fin     input {
        padding-right: 2.2rem !important;
        background-image: none !important;
    }
    /* =========================================================
       FORZADO FINAL: borde exterior real de cards grandes Fase 2
       ========================================================= */

    .st-key-f2_card_header,
    .st-key-f2_card_a,
    .st-key-f2_card_b,
    .st-key-f2_card_gwa_a,
    .st-key-f2_card_gwa_b,
    .st-key-f2_card_c,
    .st-key-f2_card_d,
    .st-key-f2_card_e,
    .st-key-f2_card_f,
    .st-key-f2_card_g,
    .st-key-f2_card_final,
    .st-key-f2_card_empty {
        border: 1.4px solid #cbd5e1 !important;
        border-radius: 28px !important;
        overflow: hidden !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    }

    /* Neutralizar el borde original interno de Streamlit para que no se vea cuadrado */
    .st-key-f2_card_header div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_a div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_b div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_gwa_a div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_gwa_b div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_c div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_d div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_e div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_f div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_g div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_final div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_card_empty div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        box-shadow: none !important;
        border-radius: 28px !important;
        background: transparent !important;
        overflow: visible !important;
    }
    .st-key-f2_card_header [data-testid="stVerticalBlockBorderWrapper"] {
        background: #f8fbff !important;
        border: 2px solid #aebcd2 !important;
        border-radius: 18px !important;
        box-shadow:
            0 0 0 1px rgba(148, 163, 184, 0.35),
            0 6px 14px rgba(15, 23, 42, 0.13),
            0 2px 6px rgba(37, 99, 235, 0.10) !important;
        padding: 1.05rem 1.05rem 0.95rem 1.05rem !important;
        min-height: unset !important;
        height: auto !important;
    }

    /* Forzado específico: cards F1/F2/F3 del bloque F (contenedor externo real) */
    .st-key-f2_f_chart_card_1,
    .st-key-f2_f_chart_card_2,
    .st-key-f2_f_chart_card_3 {
        border-radius: 28px !important;
        overflow: hidden !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        border: 1.3px solid #cbd5e1 !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    }
    .st-key-f2_f_chart_card_1 div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_f_chart_card_2 div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f2_f_chart_card_3 div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        border-radius: 28px !important;
        box-shadow: none !important;
        background: transparent !important;
        overflow: hidden !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

_f2_data_source_saved = config.get("data_source", "NASA POWER")
_f2_source_class = "nasa" if _f2_data_source_saved == "NASA POWER" else "gwa"
_f2_source_label = _f2_data_source_saved

with _phase_card("f2_card_header"):
    st.markdown(
        f"""
        <div class="hero-card">
            <div class="fase-hero-title">Fase 2 &middot; Perfiles de viento</div>
            <div class="fase-hero-subtitle">
                Consulta y an&aacute;lisis de datos horarios de viento y generaci&oacute;n de perfiles verticales.
                <span class="f2-source-badge f2-source-badge--{_f2_source_class}">Fuente: {_f2_source_label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if st.session_state.get("f2_profile_save_message"):
    st.success(st.session_state["f2_profile_save_message"])
    st.session_state["f2_profile_save_message"] = ""

cfg_saved_top = _load_current_config()
f2_nasa_signature = (
    "nasa_hourly",
    _file_signature(get_db_file_path()),
    cfg_saved_top.get("nasa_lat"),
    cfg_saved_top.get("nasa_lon"),
    cfg_saved_top.get("nasa_inicio"),
    cfg_saved_top.get("nasa_fin"),
    cfg_saved_top.get("nasa_fuente"),
)
df_nasa = _session_cached_result("f2_nasa_hourly_df", f2_nasa_signature, cargar_nasa_hourly)
altura_guardada_top, rugosidad_guardada_top = _get_saved_profile_values(cfg_saved_top)
_init_widget_state("f2_altura", altura_guardada_top)
rugosidad_visible_top = rugosidad_guardada_top
altura_visible_top = st.session_state.get("f2_altura", altura_guardada_top)
cambios_pendientes_top = (
    float(altura_visible_top) != float(altura_guardada_top)
    or _safe_fase2_roughness_label(rugosidad_visible_top) != _safe_fase2_roughness_label(rugosidad_guardada_top)
)

consultar_nasa = False

# ── Data source selector ──
_f2_ds_options = ["NASA POWER", "Global Wind Atlas / Open-Meteo"]
_f2_ds_default = config.get("data_source", "NASA POWER")
if _f2_ds_default not in _f2_ds_options:
    _f2_ds_default = "NASA POWER"
_f2_ds_idx = _f2_ds_options.index(_f2_ds_default)

f2_data_source = st.radio(
    "Fuente de datos de viento",
    _f2_ds_options,
    index=_f2_ds_idx,
    horizontal=True,
    key="f2_data_source",
)
# Persist choice
if f2_data_source != _f2_ds_default:
    guardar_config_values({"data_source": f2_data_source})

# ── GWA block: shown only when Global Wind Atlas is selected ──
if f2_data_source == "Global Wind Atlas / Open-Meteo":
    # Sincronizar desde DB si los valores son 0 (sin inicializar)
    _gwa_lat_db = float(config.get("gwa_lat") or 0.0)
    _gwa_lon_db = float(config.get("gwa_lon") or 0.0)
    if _gwa_lat_db != 0.0 and st.session_state.get("f2_gwa_latitude", 0.0) == 0.0:
        st.session_state["f2_gwa_latitude"] = _gwa_lat_db
    if _gwa_lon_db != 0.0 and st.session_state.get("f2_gwa_longitude", 0.0) == 0.0:
        st.session_state["f2_gwa_longitude"] = _gwa_lon_db
    if st.session_state.get("f2_gwa_inicio") is None:
        st.session_state["f2_gwa_inicio"] = datetime.date(2023, 1, 1)
    if st.session_state.get("f2_gwa_fin") is None:
        st.session_state["f2_gwa_fin"] = datetime.date(2023, 12, 31)

    _gwa_col_a, _gwa_col_b = st.columns([1.38, 1.0], gap="large")

    # ── Column A: Map, coords, dates & query ──
    _consultar_open_meteo_flag = False
    with _gwa_col_a:
        with _phase_card("f2_card_gwa_a"):
            st.markdown(
                _section_title_html("A", "globe", "Ubicaci\u00f3n y periodo", "Seleccione coordenadas y rango de fechas para consultar Open-Meteo."),
                unsafe_allow_html=True,
            )
            st.markdown('<div class="ab-card-shell ab-card-shell--a">', unsafe_allow_html=True)

            try:
                import folium
                from streamlit_folium import st_folium

                _gwa_mapa = folium.Map(
                    location=[st.session_state.get("f2_gwa_latitude", 11.85), st.session_state.get("f2_gwa_longitude", -72.35)],
                    zoom_start=st.session_state.get("f2_gwa_map_zoom", 9),
                    tiles="OpenStreetMap",
                )
                folium.CircleMarker(
                    location=[st.session_state.get("f2_gwa_latitude", 11.85), st.session_state.get("f2_gwa_longitude", -72.35)],
                    radius=7,
                    color="red",
                    fill=True,
                    fill_color="red",
                    fill_opacity=0.9,
                    tooltip="Punto GWA / Open-Meteo",
                ).add_to(_gwa_mapa)
                folium.LatLngPopup().add_to(_gwa_mapa)

                _gwa_mapa_data = st_folium(_gwa_mapa, width=1200, height=360, key="mapa_gwa")

                if _gwa_mapa_data and _gwa_mapa_data.get("last_clicked"):
                    st.session_state["f2_gwa_latitude"] = float(_gwa_mapa_data["last_clicked"]["lat"])
                    st.session_state["f2_gwa_longitude"] = float(_gwa_mapa_data["last_clicked"]["lng"])
                    if _gwa_mapa_data.get("zoom") is not None:
                        try:
                            st.session_state["f2_gwa_map_zoom"] = int(_gwa_mapa_data["zoom"])
                        except Exception:
                            pass
                    guardar_config_mapa_gwa()

            except Exception:
                st.warning("El mapa interactivo necesita instalar `folium` y `streamlit-folium`.")

            _gc1, _gc2 = st.columns(2)
            with _gc1:
                st.number_input("Latitud", format="%.6f", key="f2_gwa_latitude", on_change=guardar_config_mapa_gwa)
            with _gc2:
                st.number_input("Longitud", format="%.6f", key="f2_gwa_longitude", on_change=guardar_config_mapa_gwa)

            _gd1, _gd2 = st.columns(2)
            with _gd1:
                st.date_input("Fecha inicial", key="f2_gwa_inicio", on_change=guardar_config_mapa_gwa)
            with _gd2:
                st.date_input("Fecha final", key="f2_gwa_fin", on_change=guardar_config_mapa_gwa)

            with st.expander("Imagen can\u00f3nica del mapa para reportes (opcional)"):
                st.caption("La captura directa del widget de mapa no se exporta de forma fiable desde el backend actual. Si desea que el informe use una vista igual o muy cercana a la selecci\u00f3n realizada en Fase 2, suba aqu\u00ed una captura o imagen de referencia del sitio. Esa imagen tendr\u00e1 prioridad como `mapa_sitio.png` en LaTeX, el ZIP y el pack de Overleaf.")
                st.caption("Si cambia la latitud o la longitud del proyecto, la imagen can\u00f3nica guardada se invalida autom\u00e1ticamente para evitar que el reporte reutilice una captura de otro sitio.")

                cfg_img_gwa = _load_current_config()
                existing_site_map_name_gwa = str(cfg_img_gwa.get("site_map_image_name") or "").strip()
                existing_site_map_b64_gwa = str(cfg_img_gwa.get("site_map_image_b64") or "").strip()
                existing_site_map_mime_gwa = str(cfg_img_gwa.get("site_map_image_mime") or "").strip() or "image/png"

                if existing_site_map_b64_gwa:
                    try:
                        existing_site_map_bytes_gwa = base64.b64decode(existing_site_map_b64_gwa)
                        st.image(
                            existing_site_map_bytes_gwa,
                            caption=f"Imagen can\u00f3nica actualmente guardada: {existing_site_map_name_gwa or 'mapa_sitio'}",
                            use_container_width=True,
                        )
                        st.caption(f"Formato original guardado: {existing_site_map_mime_gwa}. En exportaci\u00f3n se normaliza a `mapa_sitio.png`.")
                    except Exception:
                        st.warning("La imagen can\u00f3nica guardada no pudo previsualizarse. Puede reemplazarla con una nueva carga.")

                uploaded_site_map_gwa = st.file_uploader(
                    "Suba una imagen del mapa seleccionado en Fase 2",
                    type=["png", "jpg", "jpeg"],
                    key="f2_gwa_site_map_image_upload",
                    help="Use una captura o imagen del mapa elegido en Fase 2. La app la convertir\u00e1 a un `mapa_sitio.png` can\u00f3nico para reportes.",
                )

                if uploaded_site_map_gwa is not None:
                    st.image(uploaded_site_map_gwa, caption="Vista previa de la nueva imagen can\u00f3nica propuesta", use_container_width=True)

                upload_col_gwa, clear_col_gwa = st.columns(2)
                with upload_col_gwa:
                    if st.button("Guardar imagen can\u00f3nica", use_container_width=True, key="guardar_imagen_canonica_mapa_btn_gwa"):
                        ok, message = guardar_imagen_canonica_mapa(uploaded_site_map_gwa)
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.warning(message)
                with clear_col_gwa:
                    if st.button("Quitar imagen can\u00f3nica", use_container_width=True, key="limpiar_imagen_canonica_mapa_btn_gwa"):
                        limpiar_imagen_canonica_mapa()
                        st.success("Se elimin\u00f3 la imagen can\u00f3nica guardada del mapa del sitio.")
                        st.rerun()

            _c_gwa_l, _c_gwa_btn, _c_gwa_r = st.columns([1, 1.5, 1])
            with _c_gwa_btn:
                _consultar_open_meteo_flag = st.button(
                    "Consultar Open-Meteo",
                    use_container_width=True,
                    type="primary",
                    icon=":material/search:",
                )

            st.markdown('</div>', unsafe_allow_html=True)

    # ── Column B: altura + CSV (alternative) — mirrors NASA POWER Block B ──
    with _gwa_col_b:
        with _phase_card("f2_card_gwa_b"):
            st.markdown(
                _section_title_html("B", "upload", "Par\u00e1metros y datos opcionales", "Gestione la altura operativa y, opcionalmente, cargue un CSV de GWA."),
                unsafe_allow_html=True,
            )

            # ── Inline CSS: mirror NASA Block B styling for GWA card ──
            st.markdown(
                """
                <style>
                .st-key-f2_card_gwa_b [data-testid="stButton"] > button {
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    gap: 0.75rem !important;
                    min-height: 80px !important;
                    padding: 0.5rem 0.75rem !important;
                    border-radius: 13px !important;
                    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06) !important;
                }
                .st-key-f2_card_gwa_b [data-testid="stButton"] > button p {
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    gap: 0.75rem !important;
                    width: 100% !important;
                    white-space: pre-line !important;
                    line-height: 1.25 !important;
                    text-align: left !important;
                    font-size: 0.95rem !important;
                    font-weight: 800 !important;
                }
                .st-key-btn_f2_gwa_guardar [data-testid="stButton"] > button p::before {
                    content: '';
                    display: inline-flex;
                    width: 27px; height: 27px;
                    flex-shrink: 0;
                    background-image: url("data:image/svg+xml;utf8,<svg width='20' height='20' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' stroke='%232563eb' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round' fill='none'><path d='M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z'/><polyline points='17 21 17 13 7 13 7 21'/><polyline points='7 3 7 8 15 8'/></svg>");
                    background-repeat: no-repeat;
                    background-size: 26px 26px;
                    background-position: center;
                }
                .st-key-btn_f2_gwa_recargar [data-testid="stButton"] > button p::before {
                    content: '';
                    display: inline-flex;
                    width: 27px; height: 27px;
                    flex-shrink: 0;
                    background-image: url("data:image/svg+xml;utf8,<svg width='20' height='20' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' stroke='%232563eb' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round' fill='none'><polyline points='23 4 23 10 17 10'/><path d='M20.49 15a9 9 0 1 1-2.12-9.36L23 10'/></svg>");
                    background-repeat: no-repeat;
                    background-size: 26px 26px;
                    background-position: center;
                }
                /* Hide native instructions, style the browse button */
                .st-key-f2_gwa_upload [data-testid="stFileUploaderDropzoneInstructions"] {
                    display: none !important;
                }
                .st-key-f2_gwa_upload [data-testid="stFileUploaderDropzone"] button {
                    font-size: 0.95rem !important;
                    font-weight: 700 !important;
                    border-radius: 12px !important;
                    padding: 0.45rem 1.4rem !important;
                    border: 1.5px solid #93c5fd !important;
                    color: #1e40af !important;
                    background: #ffffff !important;
                    min-width: 170px;
                }
                .st-key-f2_gwa_upload [data-testid="stFileUploaderDropzone"] button p {
                    font-size: 0 !important;
                }
                .st-key-f2_gwa_upload [data-testid="stFileUploaderDropzone"] button p::after {
                    content: 'Seleccionar archivo';
                    font-size: 0.95rem;
                    font-weight: 700;
                    color: #1e40af;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            # ── Optional: CSV de GWA (alternativa al CSV de Weibull) ──
            with st.container(key="f2_gwa_dropzone_wrapper"):
                st.markdown(
                    f"""
                    <div class="upload-dropzone-top">
                        <div class="upload-dropzone__icon">{_icon_svg("cloud-upload", 46, "#2563eb")}</div>
                        <div class="upload-dropzone__title">Opcional: CSV de par\u00e1metros Weibull (GWA)</div>
                        <div class="upload-dropzone__subtitle">Arrastra y suelta el archivo aqu&iacute;</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                gwa_file = st.file_uploader(
                    "Suba un archivo CSV del Global Wind Atlas",
                    type=["csv"], key="f2_gwa_upload", label_visibility="collapsed",
                )
                st.markdown('<div class="upload-dropzone-bottom">M&aacute;x. 200 MB por archivo</div>', unsafe_allow_html=True)

            gwa_result = st.session_state.pop("f2_gwa_result", None)
            if gwa_result:
                kind, message = gwa_result
                if kind == "success":
                    st.success(message)
                else:
                    st.error(message)

            if gwa_file is not None:
                if st.button("Procesar datos GWA", use_container_width=True, icon=":material/cloud_upload:"):
                    try:
                        gwa_data = leer_csv_gwa(gwa_file)
                        import json as _json
                        guardar_config_values({"gwa_data": _json.dumps(gwa_data)})
                        st.session_state["f2_gwa_result"] = ("success", "Datos GWA procesados y guardados correctamente.")
                        st.rerun()
                    except Exception as e:
                        st.session_state["f2_gwa_result"] = ("error", f"No pude procesar el CSV de GWA: {e}")
                        st.rerun()


            # ── Altura deseada ──
            _gwa_altura_visible = st.number_input(
                "Altura deseada (m)",
                min_value=0.10,
                step=0.10,
                format="%.2f",
                key="f2_altura",
            )
            _gwa_cambios_pendientes = (
                float(_gwa_altura_visible) != float(altura_guardada_top)
                or _safe_fase2_roughness_label(rugosidad_visible_top) != _safe_fase2_roughness_label(rugosidad_guardada_top)
            )

            # ── Guardar / Recargar buttons ──
            st.markdown('<div class="ab-actions-row">', unsafe_allow_html=True)
            _gb1, _gb2 = st.columns(2)
            with _gb1:
                if st.button("Guardar par\u00e1metros\nde perfiles", use_container_width=True, key="btn_f2_gwa_guardar"):
                    _guardar_parametros_perfiles(_gwa_altura_visible, rugosidad_visible_top)
                    st.success(st.session_state.get("f2_profile_save_message", "Guardado."))
            with _gb2:
                if st.button("Recargar valores\nguardados", use_container_width=True, key="btn_f2_gwa_recargar"):
                    st.session_state["f2_altura"] = altura_guardada_top
                    st.session_state["f2_profile_save_message"] = "Se recargaron los par\u00e1metros guardados."
                    st.success(st.session_state["f2_profile_save_message"])
            st.markdown("</div>", unsafe_allow_html=True)

            # ── Status indicator ──
            st.markdown('<div class="f2-card-b-status">', unsafe_allow_html=True)
            if _gwa_cambios_pendientes:
                st.warning("Hay cambios sin guardar en altura deseada. Los c\u00e1lculos siguen usando los \u00faltimos valores guardados.")
            else:
                st.markdown(
                    '<div class="f2-status-inline">'
                    '<div class="f2-status-check">'
                    '<svg width="14" height="14" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" '
                    'stroke="#2563eb" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none">'
                    '<polyline points="20 6 9 17 4 12"/>'
                    '</svg>'
                    '</div>'
                    '<div class="f2-status-text">Los par\u00e1metros de perfiles visibles coinciden con los valores guardados en la base de datos.</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            st.markdown('</div>', unsafe_allow_html=True)


            # Show saved GWA Weibull data + synthetic generator
            _gwa_raw = config.get("gwa_data", "")
            if _gwa_raw:
                try:
                    import json as _json
                    _gwa_saved = _json.loads(_gwa_raw)
                    _gwa_df = pd.DataFrame({
                        "Altura (m)": _gwa_saved["alturas"],
                        "A (Weibull)": _gwa_saved["A"],
                        "k (Weibull)": _gwa_saved["k"],
                        "V media (m/s)": _gwa_saved["v_medio"],
                    })
                    st.markdown("##### Resumen de datos GWA guardados")
                    st.dataframe(_gwa_df, use_container_width=True, hide_index=True)

                    _gwa_n_years = st.number_input(
                        "N\u00famero de a\u00f1os a simular",
                        min_value=1, max_value=10, value=1, step=1,
                        key="f2_gwa_years",
                    )
                    if st.button("Generar serie sint\u00e9tica desde Weibull", use_container_width=True, icon=":material/auto_graph:"):
                        try:
                            _gwa_params = _json.loads(config["gwa_data"])
                            _gwa_synth_df = generar_serie_weibull(_gwa_params, int(_gwa_n_years))
                            _gwa_s_lat = st.session_state["f2_gwa_latitude"]
                            _gwa_s_lon = st.session_state["f2_gwa_longitude"]
                            guardar_nasa_hourly(
                                df=_gwa_synth_df,
                                latitude=_gwa_s_lat, longitude=_gwa_s_lon,
                                source="GWA Weibull sint\u00e9tico",
                                start_date=_gwa_synth_df["timestamp"].min().date(),
                                end_date=_gwa_synth_df["timestamp"].max().date(),
                            )
                            st.session_state.pop("f2_nasa_hourly_df", None)
                            guardar_config_values({
                                "nasa_lat": _gwa_s_lat, "nasa_lon": _gwa_s_lon,
                                "nasa_inicio": _gwa_synth_df["timestamp"].min().date(),
                                "nasa_fin": _gwa_synth_df["timestamp"].max().date(),
                                "nasa_fuente": "GWA Weibull sint\u00e9tico",
                            })
                            st.session_state["f2_gwa_result"] = (
                                "success",
                                f"Serie sint\u00e9tica: {len(_gwa_synth_df):,} horas. Guardada para Fases 3-6."
                            )
                            st.rerun()
                        except Exception as e:
                            st.session_state["f2_gwa_result"] = ("error", f"Error: {e}")
                            st.rerun()
                except Exception:
                    pass

    # ── Open-Meteo query execution ──
    if _consultar_open_meteo_flag:
        try:
            _om_lat = st.session_state["f2_gwa_latitude"]
            _om_lon = st.session_state["f2_gwa_longitude"]
            _om_start = st.session_state["f2_gwa_inicio"]
            _om_end = st.session_state["f2_gwa_fin"]

            with st.spinner("Consultando Open-Meteo..."):
                _om_df = consultar_open_meteo(_om_lat, _om_lon, _om_start, _om_end)

            guardar_nasa_hourly(
                df=_om_df,
                latitude=_om_lat, longitude=_om_lon,
                source="Open-Meteo (GWA site)",
                start_date=_om_start, end_date=_om_end,
            )
            st.session_state.pop("f2_nasa_hourly_df", None)

            guardar_config_values({
                "nasa_lat": _om_lat, "nasa_lon": _om_lon,
                "nasa_inicio": _om_start, "nasa_fin": _om_end,
                "nasa_fuente": "Open-Meteo (GWA site)",
            })

            st.session_state["f2_gwa_result"] = (
                "success",
                f"Datos Open-Meteo recibidos: {len(_om_df):,} horas "
                f"({_om_start} a {_om_end}). Guardados para Fases 3-6."
            )
            st.rerun()
        except Exception as e:
            st.error(f"Error al consultar Open-Meteo: {e}")


# ── NASA POWER blocks (shown only when NASA POWER is selected) ──
if f2_data_source == "NASA POWER":
    _f2_show_nasa = True
else:
    _f2_show_nasa = False

if _f2_show_nasa:
    col_a, col_b = st.columns([1.38, 1.0], gap="large")

    with col_a:
        with _phase_card("f2_card_a"):
            st.markdown(
                _section_title_html("A", "globe", "Consulta NASA POWER por coordenadas", "Ubique el sitio, defina el rango temporal y consulte la serie horaria."),
                unsafe_allow_html=True,
            )
            st.markdown('<div class="ab-card-shell ab-card-shell--a">', unsafe_allow_html=True)

            try:
                import folium
                from streamlit_folium import st_folium

                mapa = folium.Map(
                    location=[11.85, -72.35],
                    zoom_start=st.session_state.get("f2_map_zoom", 8),
                    tiles="OpenStreetMap",
                )
                folium.CircleMarker(
                    location=[st.session_state["f2_latitude"], st.session_state["f2_longitude"]],
                    radius=7,
                    color="red",
                    fill=True,
                    fill_color="red",
                    fill_opacity=0.9,
                    tooltip="Punto actual",
                ).add_to(mapa)
                folium.LatLngPopup().add_to(mapa)

                mapa_data = st_folium(mapa, width=1200, height=360, key="mapa_nasa_grande")

                if mapa_data and mapa_data.get("last_clicked"):
                    st.session_state["f2_latitude"] = float(mapa_data["last_clicked"]["lat"])
                    st.session_state["f2_longitude"] = float(mapa_data["last_clicked"]["lng"])
                    if mapa_data.get("zoom") is not None:
                        try:
                            st.session_state["f2_map_zoom"] = int(mapa_data["zoom"])
                        except Exception:
                            pass
                    guardar_config_mapa()

            except Exception:
                st.warning("El mapa interactivo necesita instalar `folium` y `streamlit-folium`. Mientras tanto puede escribir latitud y longitud manualmente o usar el CSV.")

            c1, c2 = st.columns(2)
            with c1:
                st.number_input("Latitud", format="%.6f", key="f2_latitude", on_change=guardar_config_mapa)
            with c2:
                st.number_input("Longitud", format="%.6f", key="f2_longitude", on_change=guardar_config_mapa)

            d1, d2 = st.columns(2)
            with d1:
                st.date_input("Fecha inicial", key="f2_fecha_inicio", on_change=guardar_config_mapa)
            with d2:
                st.date_input("Fecha final", key="f2_fecha_fin", on_change=guardar_config_mapa)

            with st.expander("Imagen canónica del mapa para reportes (opcional)"):
                st.caption("La captura directa del widget de mapa no se exporta de forma fiable desde el backend actual. Si desea que el informe use una vista igual o muy cercana a la selección realizada en Fase 2, suba aquí­ una captura o imagen de referencia del sitio. Esa imagen tendrá prioridad como `mapa_sitio.png` en LaTeX, el ZIP y el pack de Overleaf.")
                st.caption("Si cambia la latitud o la longitud del proyecto, la imagen canónica guardada se invalida automáticamente para evitar que el reporte reutilice una captura de otro sitio.")

                cfg_img = _load_current_config()
                existing_site_map_name = str(cfg_img.get("site_map_image_name") or "").strip()
                existing_site_map_b64 = str(cfg_img.get("site_map_image_b64") or "").strip()
                existing_site_map_mime = str(cfg_img.get("site_map_image_mime") or "").strip() or "image/png"

                if existing_site_map_b64:
                    try:
                        existing_site_map_bytes = base64.b64decode(existing_site_map_b64)
                        st.image(
                            existing_site_map_bytes,
                            caption=f"Imagen canónica actualmente guardada: {existing_site_map_name or 'mapa_sitio'}",
                            use_container_width=True,
                        )
                        st.caption(f"Formato original guardado: {existing_site_map_mime}. En exportación se normaliza a `mapa_sitio.png`.")
                    except Exception:
                        st.warning("La imagen canónica guardada no pudo previsualizarse. Puede reemplazarla con una nueva carga.")

                uploaded_site_map = st.file_uploader(
                    "Suba una imagen del mapa seleccionado en Fase 2",
                    type=["png", "jpg", "jpeg"],
                    key="f2_site_map_image_upload",
                    help="Use una captura o imagen del mapa elegido en Fase 2. La app la convertirá a un `mapa_sitio.png` canónico para reportes.",
                )

                if uploaded_site_map is not None:
                    st.image(uploaded_site_map, caption="Vista previa de la nueva imagen canónica propuesta", use_container_width=True)

                upload_col, clear_col = st.columns(2)
                with upload_col:
                    if st.button("Guardar imagen canónica", use_container_width=True, key="guardar_imagen_canonica_mapa_btn"):
                        ok, message = guardar_imagen_canonica_mapa(uploaded_site_map)
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.warning(message)
                with clear_col:
                    if st.button("Quitar imagen canónica", use_container_width=True, key="limpiar_imagen_canonica_mapa_btn"):
                        limpiar_imagen_canonica_mapa()
                        st.success("Se eliminó la imagen canónica guardada del mapa del sitio.")
                        st.rerun()

            # â”€â”€ NASA POWER button: inject search icon via label HTML â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            _nasa_lupa = (
                "<svg width='18' height='18' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' "
                "stroke='white' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' fill='none' "
                "style='display:inline-block;vertical-align:middle;flex-shrink:0;'>"
                "<circle cx='11' cy='11' r='7'/><path d='m21 21-4.35-4.35'/>"
                "</svg>"
            )
            st.markdown(
                """
                <style>
                /* Make Block A texts pop out more */
                .st-key-f2_card_a .section-title {
                    font-weight: 700 !important;
                }
                .st-key-f2_card_a label p {
                    font-weight: 600 !important;
                }
                .st-key-f2_card_a [data-testid="stExpander"] summary p {
                    font-weight: 600 !important;
                }
                .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button p {
                    font-weight: 600 !important;
                }
            
                /* Center content inside the NASA POWER button */
                .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button {
                    display: inline-flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    gap: 0.55rem !important;
                    padding-left: 1.4rem !important;
                    padding-right: 1.4rem !important;
                }
                /* Hide the default ::before pseudo-element (reset from previous pass) */
                .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button::before {
                    display: none !important;
                    content: none !important;
                }
                /* Icon injected via [data-testid="stMarkdownContainer"] sibling trick:
                   We render the button via st.markdown wrapper below */
                .f2-nasa-btn-wrap {
                    display: contents;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            c_l, c_btn, c_r = st.columns([1, 1.5, 1])
            with c_btn:
                consultar_nasa = st.button("Consultar NASA POWER", key="btn_consultar_nasa_power", use_container_width=True)
            # Overlay the search icon inside the button text via CSS content trick on the <p> tag
            st.markdown(
                f"""
                <style>
                .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button p {{
                    display: inline-flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    gap: 0.5rem !important;
                }}
                .st-key-btn_consultar_nasa_power [data-testid="stButton"] > button p::before {{
                    content: '';
                    display: inline-flex;
                    width: 18px;
                    height: 18px;
                    flex-shrink: 0;
                    background-image: url("data:image/svg+xml;utf8,<svg width='18' height='18' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' stroke='white' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' fill='none'><circle cx='11' cy='11' r='7'/><path d='m21 21-4.35-4.35'/></svg>");
                    background-repeat: no-repeat;
                    background-size: contain;
                    background-position: center;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        with _phase_card("f2_card_b"):
            st.markdown(
                _section_title_html("B", "upload", "O cargar un CSV descargado desde NASA POWER", "Importe un CSV existente y gestione la altura operativa usada en los perfiles."),
                unsafe_allow_html=True,
            )

            with st.container(key="f2_csv_dropzone_wrapper"):
                st.markdown(
                    f"""
                    <div class="upload-dropzone-top">
                        <div class="upload-dropzone__icon">{_icon_svg("cloud-upload", 46, "#2563eb")}</div>
                        <div class="upload-dropzone__title">Sube un archivo CSV o JSON de NASA POWER</div>
                        <div class="upload-dropzone__subtitle">Arrastra y suelta el archivo aquí</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                archivo = st.file_uploader("Suba un archivo CSV o JSON de NASA POWER", type=["csv", "json"], key="f2_csv_upload", label_visibility="collapsed")
                st.markdown('<div class="upload-dropzone-bottom">M&aacute;x. 200 MB por archivo</div>', unsafe_allow_html=True)

            csv_result = st.session_state.pop("f2_csv_result", None)
            if csv_result:
                kind, message = csv_result
                if kind == "success":
                    st.success(message)
                elif kind == "warning_success":
                    st.warning(message)
                    st.success("CSV procesado, actualizado y guardado en SQLite.")
                elif kind == "warning":
                    st.warning(message)
                else:
                    st.error(message)

            if archivo is not None:
                st.button("Procesar CSV y guardar", use_container_width=True, on_click=_process_csv_callback)

            altura_visible_top = st.number_input(
                "Altura deseada (m)",
                min_value=0.10,
                step=0.10,
                format="%.2f",
                key="f2_altura",
            )
            cambios_pendientes_top = (
                float(altura_visible_top) != float(altura_guardada_top)
                or _safe_fase2_roughness_label(rugosidad_visible_top) != _safe_fase2_roughness_label(rugosidad_guardada_top)
            )

            st.markdown(
                """
                <style>
                /* â”€â”€ Action buttons in Block B: base layout (bigger, more robust) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
                .st-key-f2_card_b [data-testid="stButton"] > button {
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    gap: 0.75rem !important;
                    min-height: 80px !important;
                    padding: 0.5rem 0.75rem !important;
                    border-radius: 13px !important;
                    box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06) !important;
                }
                .st-key-f2_card_b [data-testid="stButton"] > button p {
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    gap: 0.75rem !important;
                    width: 100% !important;
                    white-space: pre-line !important;
                    line-height: 1.25 !important;
                    text-align: left !important;
                    font-size: 0.95rem !important;
                    font-weight: 800 !important;
                }
                .st-key-btn_f2_guardar_perfiles [data-testid="stButton"] > button p::before {
                    content: '';
                    display: inline-flex;
                    width: 27px;
                    height: 27px;
                    flex-shrink: 0;
                    background-image: url("data:image/svg+xml;utf8,<svg width='20' height='20' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' stroke='%232563eb' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round' fill='none'><path d='M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z'/><polyline points='17 21 17 13 7 13 7 21'/><polyline points='7 3 7 8 15 8'/></svg>");
                    background-repeat: no-repeat;
                    background-size: 26px 26px;
                    background-position: center;
                }
                /* â”€â”€ Recargar: refresh icon via p::before (bigger) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
                .st-key-btn_f2_recargar_perfiles [data-testid="stButton"] > button p::before {
                    content: '';
                    display: inline-flex;
                    width: 27px;
                    height: 27px;
                    flex-shrink: 0;
                    background-image: url("data:image/svg+xml;utf8,<svg width='20' height='20' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' stroke='%232563eb' stroke-width='2.6' stroke-linecap='round' stroke-linejoin='round' fill='none'><polyline points='23 4 23 10 17 10'/><path d='M20.49 15a9 9 0 1 1-2.12-9.36L23 10'/></svg>");
                    background-repeat: no-repeat;
                    background-size: 26px 26px;
                    background-position: center;
                }
                /* â”€â”€ File uploader: hide native instructions, style the button â”€ */
                .st-key-f2_csv_upload [data-testid="stFileUploaderDropzoneInstructions"] {
                    display: none !important;
                }
                /* Target the "Browse files" button by any attribute */
                .st-key-f2_csv_upload [data-testid="stFileUploaderDropzone"] button {
                    font-size: 0.95rem !important;
                    font-weight: 700 !important;
                    border-radius: 12px !important;
                    padding: 0.45rem 1.4rem !important;
                    border: 1.5px solid #93c5fd !important;
                    color: #1e40af !important;
                    background: #ffffff !important;
                    min-width: 170px;
                }
                /* Override the button text to show 'Seleccionar archivo' */
                .st-key-f2_csv_upload [data-testid="stFileUploaderDropzone"] button p {
                    font-size: 0 !important;  /* hide original text */
                }
                .st-key-f2_csv_upload [data-testid="stFileUploaderDropzone"] button p::after {
                    content: 'Seleccionar archivo';
                    font-size: 0.95rem;
                    font-weight: 700;
                    color: #1e40af;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="ab-actions-row">', unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Guardar parámetros\nde perfiles", use_container_width=True, key="btn_f2_guardar_perfiles"):
                    _guardar_parametros_perfiles(altura_visible_top, rugosidad_visible_top)
                    st.success(st.session_state.get("f2_profile_save_message", "Guardado."))
            with b2:
                if st.button("Recargar valores\nguardados", use_container_width=True, key="btn_f2_recargar_perfiles"):
                    st.session_state["f2_altura"] = altura_guardada_top
                    st.session_state["f2_profile_save_message"] = "Se recargaron los parámetros guardados."
                    st.success(st.session_state["f2_profile_save_message"])
            st.markdown("</div>", unsafe_allow_html=True)

            _check_svg = (
                "<svg width='18' height='18' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg' "
                "stroke='%232563eb' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' fill='none'>"
                "<polyline points='20 6 9 17 4 12'/>"
                "</svg>"
            )
            st.markdown('<div class="f2-card-b-status">', unsafe_allow_html=True)
            if cambios_pendientes_top:
                st.warning("Hay cambios sin guardar en altura deseada. Los cálculos de esta fase y de las demás hojas siguen usando los últimos valores guardados.")
            else:
                st.markdown(
                    '<div class="f2-status-inline">'
                    '<div class="f2-status-check">'
                    '<svg width="14" height="14" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" '
                    'stroke="#2563eb" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" fill="none">'
                    '<polyline points="20 6 9 17 4 12"/>'
                    '</svg>'
                    '</div>'
                    '<div class="f2-status-text">Los par\u00e1metros de perfiles visibles coinciden con los valores guardados en la base de datos.</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            st.markdown('</div>', unsafe_allow_html=True)

    if consultar_nasa:
        try:
            latitude = st.session_state["f2_latitude"]
            longitude = st.session_state["f2_longitude"]
            fecha_inicio = st.session_state["f2_fecha_inicio"]
            fecha_fin = st.session_state["f2_fecha_fin"]

            url = construir_url_nasa_power(latitude, longitude, fecha_inicio, fecha_fin)
            df = pd.read_csv(url)

            if "YEAR" not in [str(c).upper() for c in df.columns]:
                raw = requests.get(url, timeout=60)
                raw.raise_for_status()
                from io import StringIO

                lines = raw.text.splitlines()
                idx = None
                for i, line in enumerate(lines):
                    test = line.strip().upper().replace(" ", "").replace('"', "")
                    if "YEAR" in test and "MO" in test and "DY" in test and "HR" in test:
                        idx = i
                        break

                if idx is None:
                    raise ValueError("No encontré la cabecera YEAR,MO,DY,HR en la respuesta de NASA POWER.")

                df = pd.read_csv(StringIO("\n".join(lines[idx:])))

            df.columns = [str(c).strip().upper().replace('"', "") for c in df.columns]

            required = ["YEAR", "MO", "DY", "HR", "WS10M", "WS50M"]
            optional = ["WD10M", "WD50M"]

            faltan = [c for c in required if c not in df.columns]
            if faltan:
                raise ValueError(f"Faltan columnas en la respuesta: {faltan}")

            for c in optional:
                if c not in df.columns:
                    df[c] = np.nan

            for col in required + optional:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.dropna(subset=["YEAR", "MO", "DY", "HR"]).copy()
            df["YEAR"] = df["YEAR"].astype(int)
            df["MO"] = df["MO"].astype(int)
            df["DY"] = df["DY"].astype(int)
            df["HR"] = df["HR"].astype(int)

            df["timestamp"] = pd.to_datetime(
                df[["YEAR", "MO", "DY", "HR"]].rename(
                    columns={"YEAR": "year", "MO": "month", "DY": "day", "HR": "hour"}
                )
            )

            guardar_nasa_hourly(
                df=df,
                latitude=latitude,
                longitude=longitude,
                source="NASA POWER API",
                start_date=fecha_inicio,
                end_date=fecha_fin,
            )
            st.session_state.pop("f2_nasa_hourly_df", None)

            guardar_config_values({
                "nasa_lat": latitude,
                "nasa_lon": longitude,
                "nasa_inicio": fecha_inicio,
                "nasa_fin": fecha_fin,
                "nasa_fuente": "NASA POWER API",
            })

            st.success("Datos horarios NASA POWER descargados y guardados.")
            st.rerun()

        except Exception as e:
            st.error(f"No pude descargar los datos de NASA POWER: {e}")

if len(df_nasa) > 0:
    cfg_saved = _load_current_config()
    altura_guardada, rugosidad_guardada = _get_saved_profile_values(cfg_saved)

    wd10 = df_nasa["WD10M"].dropna()
    valor_wd10 = f"{wd10.mean():.2f}°" if len(wd10) > 0 else "Sin dato"

    with _phase_card("f2_card_c"):
        st.markdown(
            _section_title_html("C", "database", "Resumen de datos horarios guardados", "Síntesis de la base horaria disponible para el proyecto actual."),
            unsafe_allow_html=True,
        )
        st.markdown('<div class="summary-strip summary-strip--featured">', unsafe_allow_html=True)
        s1, s2, s3, s4 = st.columns(4, gap="small")
        with s1:
            _render_metric_card("database-records", "Registros horarios", f"{len(df_nasa):,}", "blue", compact=True, extra_class="metric-card--summary", icon_dx=0, icon_dy=2)
        with s2:
            _render_metric_card("wind", "Promedio WS10M", f"{df_nasa['WS10M'].mean():.2f} m/s", "blue", compact=True, extra_class="metric-card--summary", icon_dx=0, icon_dy=-2)
        with s3:
            _render_metric_card("wind", "Promedio WS50M", f"{df_nasa['WS50M'].mean():.2f} m/s", "blue", compact=True, extra_class="metric-card--summary", icon_dx=0, icon_dy=-2)
        with s4:
            _render_metric_card("target", "Promedio WD10M", valor_wd10, "blue", compact=True, extra_class="metric-card--summary", icon_dx=0, icon_dy=0)
        st.markdown("</div>", unsafe_allow_html=True)

    with _phase_card("f2_card_d"):
        st.markdown(
            _section_title_html("D", "chart", "Serie horaria de velocidades", "Comportamiento temporal de WS10M y WS50M en la serie almacenada."),
            unsafe_allow_html=True,
        )
        fig_nasa = crear_grafica_nasa_hourly(df_nasa)
        st.markdown('<div class="chart-surface">', unsafe_allow_html=True)
        st.plotly_chart(fig_nasa, use_container_width=True, config=PLOTLY_PERF_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)

    v10 = float(pd.to_numeric(df_nasa["WS10M"], errors="coerce").dropna().mean())
    v50 = float(pd.to_numeric(df_nasa["WS50M"], errors="coerce").dropna().mean())
    h1 = 10.0
    h2 = 50.0

    altura_deseada = float(altura_guardada)
    roughness_label = _safe_fase2_roughness_label(rugosidad_guardada)

    alpha = float(calcular_alpha_desde_dos_alturas(v10, h1, v50, h2))
    u_star_a, z0_ajustada = ajustar_logaritmico_dos_puntos(v10, h1, v50, h2, kappa=KAPPA)

    v_exp_deseada = float(v10 * (altura_deseada / h1) ** alpha)

    advertencias_altura = []

    try:
        v_log_a_deseada = float(
            velocidad_logaritmica_en_altura(u_star_a, altura_deseada, z0_ajustada, kappa=KAPPA)
        )
    except Exception:
        v_log_a_deseada = float("nan")
        advertencias_altura.append(
            f"Log A no es válido para una altura deseada de {altura_deseada:.2f} m porque debe ser mayor que z0 ajustada ({z0_ajustada:.6f} m)."
        )

    v_promedio_deseada = float((v_exp_deseada + v_log_a_deseada) / 2.0) if np.isfinite(v_log_a_deseada) else float("nan")

    guardar_config_values({
        "perfil_vref": v10,
        "perfil_v50": v50,
        "perfil_href": h1,
        "perfil_alpha": alpha,
        "perfil_ustar": u_star_a,
        "perfil_z0": z0_ajustada,
        "perfil_z0_teorica": "",
        "perfil_metodo": "Comparación entre Exponencial, Log A (2 puntos) y Promedio Log-Exp",
    })

    puntos_medidos = [
        {"altura": 10.0, "velocidad": v10, "etiqueta": "Punto medido 10 m"},
        {"altura": 50.0, "velocidad": v50, "etiqueta": "Punto medido 50 m"},
    ]

    with _phase_card("f2_card_e"):
        st.markdown(
            _section_title_html("E", "profile", "Perfiles verticales del viento", "Comparación técnica entre los perfiles exponencial, logarítmico A y Promedio Log-Exp."),
            unsafe_allow_html=True,
        )
        top_cards = "".join(
            [
                _metric_card_html("wind-10m", "Velocidad media a 10 m", f"{v10:.2f} m/s", "green", compact=True, extra_class="metric-card--profile", icon_variant="wind"),
                _metric_card_html("wind-50m", "Velocidad media a 50 m", f"{v50:.2f} m/s", "green", compact=True, extra_class="metric-card--profile", icon_variant="wind"),
                _metric_card_html("alpha-profile", "Alpha (2 puntos)", f"{alpha:.4f}", "green", compact=True, extra_class="metric-card--profile", icon_variant="param"),
                _metric_card_html("friction-velocity", "u* modo A (2 puntos)", f"{u_star_a:.4f} m/s", "green", compact=True, extra_class="metric-card--profile", icon_variant="param"),
                _metric_card_html("roughness-z0", "z0 modo A ajustada", f"{z0_ajustada:.6f} m", "green", compact=True, extra_class="metric-card--profile", icon_variant="param"),
                _metric_card_html("log-exp-average", "Promedio Log-Exp", "Activo", "green", compact=True, extra_class="metric-card--profile", icon_variant="combined"),
            ]
        )
        speed_cards = "".join(
            [
                _metric_card_html("exp-profile", "Exponencial", f"{v_exp_deseada:.2f} m/s", "green", compact=True, extra_class="metric-card--profile-speed", icon_variant="wind"),
                _metric_card_html("log-profile", "Log A", f"{v_log_a_deseada:.2f} m/s" if np.isfinite(v_log_a_deseada) else "No válida", "green", compact=True, extra_class="metric-card--profile-speed", icon_variant="wind"),
                _metric_card_html("log-exp-average", "Promedio Log-Exp", f"{v_promedio_deseada:.2f} m/s" if np.isfinite(v_promedio_deseada) else "No válida", "green", compact=True, extra_class="metric-card--profile-speed", icon_variant="combined"),
            ]
        )
        combined_card = _metric_card_html("model-combo", "Modelo combinado", "Exp + Log A", "green", compact=True, extra_class="metric-card--profile-combined", icon_variant="combined")
        note_html = f'<div class="profile-note"><div class="profile-note__icon">{_icon_svg("info", 22, "#2563eb")}</div><div class="profile-note__text">Promedio Log-Exp: promedio entre el perfil exponencial ajustado con 10 m y 50 m y el perfil logarítmico A ajustado con los mismos dos puntos.</div></div>'

        profile_e_html = (
            f'<div class="f2-e-compact">'
            f'<div class="f2-e-grid-top">{top_cards}</div>'
            f'<div class="f2-e-bottom">'
            f'{combined_card}'
            f'<div class="profile-speed-panel f2-e-speed-panel">'
            f'<div class="profile-speed-title">Vel. a altura deseada ({altura_deseada:.2f} m)</div>'
            f'<div class="f2-e-speed-grid">{speed_cards}</div>'
            f'</div>'
            f'</div>'
            f'<div class="f2-e-note">{note_html}</div>'
            f'</div>'
        )
        st.markdown(profile_e_html, unsafe_allow_html=True)

        for advertencia in advertencias_altura:
            st.warning(advertencia)

    altura_min = max(1.0, z0_ajustada + 0.1)
    altura_max = max(altura_deseada, 50.0)
    alturas = np.linspace(altura_min, altura_max, 120)

    df_exp = calcular_perfil_exponencial(v10, h1, alpha, alturas)
    df_log_a = calcular_perfil_logaritmico(u_star_a, z0_ajustada, alturas, kappa=KAPPA)
    df_promedio = df_exp.copy()
    df_promedio["Velocidad (m/s)"] = (df_exp["Velocidad (m/s)"].to_numpy(dtype=float) + df_log_a["Velocidad (m/s)"].to_numpy(dtype=float)) / 2.0

    with _phase_card("f2_card_f"):
        st.markdown(
            _section_title_html("F", "chart", "Panel de gráficas de perfiles", "Use los chips para mostrar u ocultar cada figura sin recargar cálculos."),
            unsafe_allow_html=True,
        )
        _render_fase2_plot_chip_controls()

        fig_exp = crear_grafica_perfil_individual(
            df_perfil=df_exp,
            titulo="Perfil exponencial ajustado con 10 m y 50 m",
            nombre_traza="Perfil exponencial",
            altura_objetivo=altura_deseada,
            v_objetivo=v_exp_deseada,
            color="#3366ff",
            yaxis_type="linear",
            puntos_medidos=puntos_medidos,
        )

        fig_log_a = crear_grafica_perfil_individual(
            df_perfil=df_log_a,
            titulo="Perfil logarítmico modo A - ajustado con 10 m y 50 m",
            nombre_traza="Perfil logarítmico A",
            altura_objetivo=altura_deseada,
            v_objetivo=v_log_a_deseada,
            color="#ff5533",
            dash="dash",
            yaxis_type="log",
            puntos_medidos=puntos_medidos,
        )

        fig_log_b = crear_grafica_perfil_individual(
            df_perfil=df_promedio,
            titulo="Promedio Log-Exp",
            nombre_traza="Promedio Log-Exp",
            altura_objetivo=altura_deseada,
            v_objetivo=v_promedio_deseada,
            color="#2ca25f",
            dash="dot",
            yaxis_type="log",
            puntos_medidos=puntos_medidos,
        )
        legend_bold_targets = {
            "Perfil exponencial",
            "Perfil logarítmico A",
            "Promedio Log-Exp",
            "Puntos medidos",
            "Punto objetivo",
        }
        for fig in (fig_exp, fig_log_a, fig_log_b):
            title_text = fig.layout.title.text or ""
            fig.update_xaxes(title_text="<b>Velocidad del viento (m/s)</b>")
            fig.update_yaxes(title_text="<b>Altura (m)</b>")
            for traza in fig.data:
                trace_name = traza.name or ""
                plain_name = trace_name.replace("<b>", "").replace("</b>", "").strip()
                if plain_name in legend_bold_targets:
                    traza.name = f"<b>{plain_name}</b>"
            fig.update_layout(
                title=dict(
                    text=f"<b>{title_text}</b>" if title_text else title_text,
                    x=0.5,
                    xanchor="center",
                    font=dict(size=17, color="#0f172a"),
                ),
                legend=dict(
                    y=0.992,
                    font=dict(size=12, color="#334155"),
                ),
                font=dict(size=12, color="#334155"),
                height=550,
                margin=dict(t=72, b=40, l=44, r=24),
                paper_bgcolor="#ffffff",
                plot_bgcolor="#ffffff",
            )
        fig_cols = st.columns(3, gap="medium")
        if st.session_state.get("f2_show_fig_exp", False):
            with fig_cols[0]:
                with st.container(border=True, key="f2_f_chart_card_1"):
                    st.markdown('<div class="f2-f-chart-header">F1 · Gráfica individual - Perfil exponencial</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_exp, use_container_width=True, config=PLOTLY_PERF_CONFIG)
        if st.session_state.get("f2_show_fig_log_a", False):
            with fig_cols[1]:
                with st.container(border=True, key="f2_f_chart_card_2"):
                    st.markdown('<div class="f2-f-chart-header">F2 · Gráfica individual - Perfil logarítmico modo A</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_log_a, use_container_width=True, config=PLOTLY_PERF_CONFIG)
        if st.session_state.get("f2_show_fig_promedio", False):
            with fig_cols[2]:
                with st.container(border=True, key="f2_f_chart_card_3"):
                    st.markdown('<div class="f2-f-chart-header">F3 · Gráfica individual - Promedio Log-Exp</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_log_b, use_container_width=True, config=PLOTLY_PERF_CONFIG)

    fig_compare_linear = crear_grafica_modos(
        df_exp=df_exp,
        df_log_a=df_log_a,
        df_promedio=df_promedio,
        altura_deseada=altura_deseada,
        v_exp=v_exp_deseada,
        v_log_a=v_log_a_deseada,
        v_promedio=v_promedio_deseada,
        puntos_medidos=puntos_medidos,
    )

    fig_compare_log = crear_grafica_modos_log(
        df_exp=df_exp,
        df_log_a=df_log_a,
        df_promedio=df_promedio,
        altura_deseada=altura_deseada,
        v_exp=v_exp_deseada,
        v_log_a=v_log_a_deseada,
        v_promedio=v_promedio_deseada,
        puntos_medidos=puntos_medidos,
    )
    fig_compare_linear.update_layout(
        title=dict(
            text="<b>Comparación entre Exponencial, Log A y Promedio Log-Exp - altura en escala normal</b>",
            x=0.5,
            xanchor="center",
            y=0.98,
            yanchor="top",
            pad=dict(t=0, b=6),
            font=dict(size=17, color="#0f172a"),
        )
    )
    fig_compare_log.update_layout(
        title=dict(
            text="<b>Comparación entre Exponencial, Log A y Promedio Log-Exp - altura en escala logarítmica</b>",
            x=0.5,
            xanchor="center",
            y=0.98,
            yanchor="top",
            pad=dict(t=0, b=6),
            font=dict(size=17, color="#0f172a"),
        )
    )

    for fig in (fig_compare_linear, fig_compare_log):
        fig.update_xaxes(title_text="<b>Velocidad del viento (m/s)</b>")
        fig.update_yaxes(title_text="<b>Altura (m)</b>")
        for traza in fig.data:
            trace_name = traza.name or ""
            plain_name = trace_name.replace("<b>", "").replace("</b>", "").strip()
            if plain_name:
                traza.name = f"<b>{plain_name}</b>"
        fig.update_layout(
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.03,
                xanchor="center",
                x=0.5,
                font=dict(size=14, color="#334155"),
                itemsizing="constant",
                tracegroupgap=10,
            ),
            font=dict(size=12, color="#334155"),
            height=820,
            margin=dict(t=155, b=80, l=80, r=30),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
        )

    with _phase_card("f2_card_g"):
        st.markdown(
            _section_title_html("G", "profile", "Comparación entre perfiles", "Lectura comparativa de los tres modelos en escala lineal y logarítmica."),
            unsafe_allow_html=True,
        )
        compare_cols = st.columns(2, gap="medium")
        if st.session_state.get("f2_show_fig_comparacion", False):
            with compare_cols[0]:
                with st.container(border=True, key="f2_g_chart_card_1"):
                    st.markdown('<div class="f2-g-chart-header">G1 · Comparación entre perfiles - altura en escala normal</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_compare_linear, use_container_width=True, config=PLOTLY_PERF_CONFIG)
        if st.session_state.get("f2_show_fig_comparacion_log", False):
            with compare_cols[1]:
                with st.container(border=True, key="f2_g_chart_card_2"):
                    st.markdown('<div class="f2-g-chart-header">G2 · Comparación entre perfiles - altura en escala logarítmica</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_compare_log, use_container_width=True, config=PLOTLY_PERF_CONFIG)

    with _phase_card("f2_card_final"):
        st.markdown('<div class="final-expanders">', unsafe_allow_html=True)
        with st.expander(_f2_expander_icon_label("table-intervals", "Comparación numérica entre perfiles"), expanded=False):
            tabla_comparacion = pd.DataFrame({
                "Concepto": [
                    "Velocidad media a 10 m",
                    "Velocidad media a 50 m",
                    "Alpha exponencial (2 puntos)",
                    "u* modo A (2 puntos)",
                    "z0 modo A ajustada",
                    "Velocidad a altura deseada - Exponencial",
                    "Velocidad a altura deseada - Log A",
                    "Velocidad a altura deseada - Promedio Log-Exp",
                ],
                "Valor": [v10, v50, alpha, u_star_a, z0_ajustada, v_exp_deseada, v_log_a_deseada, v_promedio_deseada],
            })
            st.markdown(
                _f2_table_panel_header(
                    "bar-chart-2",
                    "Comparación técnica de perfiles",
                    "Resumen numérico de parámetros base y velocidades calculadas a la altura objetivo.",
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                _f2_table_summary_cards(
                    [
                        ("Exponencial", f"{v_exp_deseada:.2f} m/s", "exp-profile"),
                        ("Log A", f"{v_log_a_deseada:.2f} m/s" if np.isfinite(v_log_a_deseada) else "No válida", "log-profile"),
                        ("Promedio Log-Exp", f"{v_promedio_deseada:.2f} m/s" if np.isfinite(v_promedio_deseada) else "No válida", "log-exp-average"),
                        ("Parámetros", f"{len(tabla_comparacion)} filas", "controls"),
                    ]
                ),
                unsafe_allow_html=True,
            )
            _render_dataframe_safe(
                tabla_comparacion,
                {"Valor": "%.6f"},
                use_container_width=True,
            )

        with st.expander(_f2_expander_icon_label("table-grid", "Ver tabla de perfiles"), expanded=False):
            tabla_perfiles = pd.DataFrame({
                "Altura (m)": df_exp["Altura (m)"],
                "Velocidad exp. (m/s)": df_exp["Velocidad (m/s)"],
                "Velocidad log A (m/s)": df_log_a["Velocidad (m/s)"],
                "Velocidad promedio log-exp (m/s)": df_promedio["Velocidad (m/s)"],
            })
            st.markdown(
                _f2_table_panel_header(
                    "profile",
                    "Tabla de perfiles verticales",
                    "Vista técnica de los modelos exponencial, logarítmico A y promedio Log-Exp por altura.",
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                _f2_table_summary_cards(
                    [
                        ("Registros", f"{len(tabla_perfiles):,}", "database-records"),
                        ("Modelos", "3", "model-combo"),
                        ("Altura objetivo", f"{altura_deseada:.2f} m", "target-height"),
                        ("Vista", "Completa" if len(tabla_perfiles) <= 500 else "Parcial", "table"),
                    ]
                ),
                unsafe_allow_html=True,
            )

            if len(tabla_perfiles) > 500:
                st.markdown(
                    f'<div class="f2-table-info-banner">{_icon_svg("info", 18, "#2563eb")}<span>La tabla es grande. Se mostrará una vista parcial para mantener la app fluida.</span></div>',
                    unsafe_allow_html=True,
                )
                tabla_perfiles_vista = _build_preview_table(tabla_perfiles, key_prefix="f2_profiles_preview", default_rows=300)
            else:
                tabla_perfiles_vista = tabla_perfiles

            _render_dataframe_safe(
                tabla_perfiles_vista,
                {
                    "Altura (m)": "%.2f",
                    "Velocidad exp. (m/s)": "%.2f",
                    "Velocidad log A (m/s)": "%.2f",
                    "Velocidad promedio log-exp (m/s)": "%.2f",
                },
                use_container_width=True,
            )

        with st.expander(_f2_expander_icon_label("database-stack", "Ver tabla NASA POWER guardada"), expanded=False):
            mostrar = df_nasa[["timestamp", "WS10M", "WS50M", "WD10M", "WD50M"]]
            rango_temporal = "No disponible"
            if "timestamp" in mostrar.columns and len(mostrar) > 0:
                try:
                    ts_min = pd.to_datetime(mostrar["timestamp"]).min()
                    ts_max = pd.to_datetime(mostrar["timestamp"]).max()
                    rango_temporal = f"{ts_min:%Y-%m-%d} a {ts_max:%Y-%m-%d}"
                except Exception:
                    rango_temporal = "No disponible"

            st.markdown(
                _f2_table_panel_header(
                    "database-records",
                    "Tabla NASA POWER guardada",
                    "Previsualización controlada de la base horaria almacenada para el proyecto actual.",
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                _f2_table_summary_cards(
                    [
                        ("Filas totales", f"{len(mostrar):,}", "table-grid"),
                        ("Columnas", f"{mostrar.shape[1]}", "columns-3"),
                        ("Rango temporal", rango_temporal, "calendar-grid"),
                        ("Fuente", "NASA POWER / CSV", "cloud-upload"),
                    ]
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="f2-table-info-banner">{_icon_svg("info", 18, "#2563eb")}<span>Se muestra solo una parte de la tabla para mantener la app fluida.</span></div>',
                unsafe_allow_html=True,
            )

            mostrar_vista = _build_preview_table(mostrar, key_prefix="f2_nasa_preview", default_rows=300)

            _render_dataframe_safe(
                mostrar_vista,
                {
                    "WS10M": "%.2f",
                    "WS50M": "%.2f",
                    "WD10M": "%.2f",
                    "WD50M": "%.2f",
                },
                use_container_width=True,
                height=440,
            )

            st.download_button(
                "Descargar tabla NASA POWER completa (CSV)",
                data=mostrar.to_csv(index=False).encode("utf-8"),
                file_name="nasa_power_guardada.csv",
                mime="text/csv",
                use_container_width=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

else:
    with _phase_card("f2_card_empty"):
        st.markdown(
            _section_title_html("C", "database", "Datos horarios pendientes", "Cuando exista una base horaria guardada, aquí­ aparecerán el resumen, las gráficas y los perfiles verticales."),
            unsafe_allow_html=True,
        )
        st.info("Todavía no hay datos horarios de NASA POWER guardados.")

render_dropdown_visibility_fix()



