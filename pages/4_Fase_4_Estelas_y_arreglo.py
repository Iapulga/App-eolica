import base64
import html as _html_module
import textwrap
import unicodedata

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from pandas.util import hash_pandas_object

import calculos_energia as energia_calc
from calculos import (
    PROMEDIO_LOG_EXP_LABEL,
    SECTOR_CENTERS_16,
    SECTOR_LABELS_16,
    calcular_estelas_jensen_direccion,
    construir_serie_viento_analisis,
    crear_figura_direccion_estela,
    crear_figura_layout_parque,
    generar_layout_parque,
    normalizar_modelo_altura,
)
from db import (
    cargar_config,
    cargar_escenario_parque,
    cargar_layout_parque,
    cargar_nasa_hourly,
    cargar_tabla_curva,
    eliminar_escenario_parque,
    guardar_config_values,
    guardar_escenario_parque,
    guardar_layout_parque,
    init_db,
    listar_escenarios_parque,
)
from navigation import _icon_svg, render_dropdown_visibility_fix, render_sidebar_navigation
from widget_helpers import _init_widget_state

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


# ---------------------------------------------------------------------------
# Utility helpers (preserved exactly)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Aurora SMA 2.0 visual helpers
# ---------------------------------------------------------------------------
def _escape(value) -> str:
    return _html_module.escape("" if value is None else str(value))


def _safe_icon(name: str, size: int = 22, color: str = "#7c3aed") -> str:
    try:
        return _icon_svg(name, size, color)
    except Exception:
        stroke = 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"'
        return (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'style="color:{color};display:block" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="12" cy="12" r="8" {stroke}/></svg>'
        )


def _section_header(title: str, subtitle: str = "", icon: str = "chart", color: str = "#7c3aed") -> None:
    st.markdown(
        f"""
<div class="f4-section-header">
    <div class="f4-icon-soft" style="background:linear-gradient(135deg,color-mix(in srgb,{color} 16%,#fff),color-mix(in srgb,{color} 7%,#fff));border:1.5px solid color-mix(in srgb,{color} 35%,#fff);box-shadow:0 5px 12px color-mix(in srgb,{color} 16%,transparent)">
        {_safe_icon(icon, 21, color)}
    </div>
    <div>
        <div class="f4-section-title">{_escape(title)}</div>
        {f'<div class="f4-section-subtitle">{_escape(subtitle)}</div>' if subtitle else ''}
    </div>
</div>""",
        unsafe_allow_html=True,
    )


def _kpi_tile(emoji: str, label: str, value, sub: str = "", color: str = "#7c3aed") -> str:
    return f"""<div class="f4-kpi-card" style="--kc:{color}">
<div class="f4-kpi-icon">{emoji}</div>
<div><small class="f4-kpi-label">{_escape(str(label))}</small>
<b class="f4-kpi-value">{_escape(str(value))}</b>
<i class="f4-kpi-sub">{_escape(str(sub))}</i></div></div>"""


# ---------------------------------------------------------------------------
# Preserved visual/calculation helpers (lines 1666–3033 of original)
# ---------------------------------------------------------------------------
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

    # Enhanced Turbine visuals
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
    """Wrapper que cachea el HTML generado por _render_main_park_animated_html."""
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
    num_segments = 60

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
            x=df_a["x_m"], y=df_a["y_m"],
            mode="markers+text", text=df_a["turbina_id"],
            textposition="top center", name=name_a,
            marker=dict(size=12),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df_b["x_m"], y=df_b["y_m"],
            mode="markers+text", text=df_b["turbina_id"],
            textposition="bottom center", name=name_b,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Aurora SMA 2.0 CSS — Compact (~300 lines)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
:root{--ac:#7c3aed;--ac2:#5b21b6}
[data-testid="stAppViewContainer"]{background:linear-gradient(180deg,#f5f3ff 0%,#ede9fe 100%) !important}

/* ════ Hero ════ */
.hero-card{position:relative;overflow:hidden;background:linear-gradient(118deg,var(--ac) 0%,var(--ac2) 80%);border:none;border-radius:26px;padding:22px 28px;margin:0 !important;box-shadow:0 22px 44px rgba(124,58,237,.32),inset 0 1px 0 rgba(255,255,255,.25);min-height:unset !important;height:auto !important}
.hero-card::after{content:"";position:absolute;inset:0;pointer-events:none;background:radial-gradient(circle at 86% 12%,rgba(255,255,255,.20) 0 54px,transparent 55px),radial-gradient(circle at 95% 70%,rgba(255,255,255,.12) 0 86px,transparent 87px),linear-gradient(180deg,rgba(255,255,255,.08),transparent 40%)}
/* mismo alto que F1/F2/F3 (131px: padding 22 + fila 87 + 22) */
.hero-row{display:flex;align-items:center;gap:18px;position:relative;z-index:2;min-height:87px}
.hero-text{flex:1;min-width:0}
.f4-wind{position:absolute;left:-30px;top:0;bottom:0;width:58%;height:100%;opacity:.45;pointer-events:none;z-index:1}
.f4-wind path{stroke:rgba(255,255,255,.55);stroke-width:2;fill:none;stroke-dasharray:16 11;animation:f4windmove 2.6s linear infinite}
.f4-wind path:nth-child(2){animation-duration:3.4s;opacity:.7}
.f4-wind path:nth-child(3){animation-duration:4.2s;opacity:.5}
@keyframes f4windmove{to{stroke-dashoffset:-54}}
/* el hero NO va dentro de una card blanca (el st-key cae en el propio stVerticalBlock) */
#root .st-key-f4_card_header{background:transparent !important;border:none !important;box-shadow:none !important;padding:0 !important;border-radius:0 !important;min-height:0 !important;height:auto !important;overflow:visible !important;margin-bottom:14px !important;gap:0 !important}
#root .st-key-f4_card_header::before{display:none !important}
.hero-icon{width:62px;height:62px;border-radius:19px;background:rgba(255,255,255,.17);border:1.5px solid rgba(255,255,255,.4);display:flex;align-items:center;justify-content:center;font-size:31px;flex-shrink:0;box-shadow:inset 0 1px 0 rgba(255,255,255,.35),0 8px 18px rgba(0,0,0,.12)}
.fase-hero-title{font-size:25px;line-height:1.08;font-weight:800;letter-spacing:-.025em;color:#fff;margin:0 0 4px 0;text-shadow:0 1px 2px rgba(0,0,0,.12)}
.fase-hero-subtitle{color:rgba(255,255,255,.94);font-size:12.5px;line-height:1.45;font-weight:400;max-width:840px;margin:0}
.hero-pills{display:flex;gap:9px;margin-left:auto;position:relative;z-index:2}
.hpill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4);border-radius:15px;padding:8px 15px;text-align:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.25)}
.hpill b{display:block;font-size:16.5px;letter-spacing:-.01em;color:#fff}
.hpill span{font-size:9px;opacity:.92;text-transform:uppercase;letter-spacing:.07em;font-weight:700;color:rgba(255,255,255,.9)}

/* ════ Section headers ════ */
.f4-section-header{display:flex;align-items:center;gap:13px;margin:6px 0 14px}
.f4-section-title{color:#0a2444;font-size:16.5px;font-weight:900;letter-spacing:-.02em}
.f4-section-subtitle{color:#5a6b85;font-size:11px;font-weight:600;margin-top:2px}
.f4-icon-soft{width:46px;height:46px;border-radius:14px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}

/* ════ KPI grid ════ */
.f4-kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:4px 0 16px}
.f4-kpi-card{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;display:flex;gap:12px;align-items:center;box-shadow:0 1px 2px rgba(11,36,71,.04),0 6px 16px rgba(11,36,71,.06);transition:box-shadow .18s}
.f4-kpi-card:hover{box-shadow:0 12px 26px rgba(15,45,90,.10)}
.f4-kpi-icon{width:50px !important;height:50px !important;border-radius:50% !important;display:flex !important;align-items:center !important;justify-content:center !important;font-size:22px !important;flex-shrink:0 !important;
  background:linear-gradient(135deg,color-mix(in srgb,var(--kc,var(--ac)) 17%,#fff),color-mix(in srgb,var(--kc,var(--ac)) 6%,#fff)) !important;
  border:1.5px solid color-mix(in srgb,var(--kc,var(--ac)) 38%,#fff) !important;
  box-shadow:0 5px 12px color-mix(in srgb,var(--kc,var(--ac)) 18%,transparent) !important}
.f4-kpi-label{font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.07em;display:block}
.f4-kpi-value{font-size:20px;font-weight:900;letter-spacing:-.025em;line-height:1.08;margin-top:3px;font-variant-numeric:tabular-nums;color:#0a2444;display:block}
.f4-kpi-sub{font-style:normal;font-size:10px;color:#5a6b85;margin-top:2.5px;font-weight:600;display:block}

/* ════ Banner ════ */
.f4-banner{display:flex;align-items:center;gap:12px;border-radius:15px;padding:12px 16px;font-weight:800;font-size:12.5px;margin:0 0 16px}
.f4-banner .bx{width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:18px;background:rgba(255,255,255,.7);flex-shrink:0}
.f4-banner.info{background:linear-gradient(120deg,color-mix(in srgb,var(--ac) 8%,#fff),#fff);border:1.5px solid color-mix(in srgb,var(--ac) 30%,#fff);color:var(--ac)}

/* ════ Cards — all f4_ containers ════ */
.st-key-f4_card_header,
.st-key-f4_card_config,.st-key-f4_card_edit_table,.st-key-f4_card_move_layout,
.st-key-f4_card_view_layout,.st-key-f4_card_geom_summary,.st-key-f4_card_wind_base,
.st-key-f4_card_geom_analysis,.st-key-f4_card_annual_analysis,
.st-key-f4_card_detail_direction,.st-key-f4_card_scenarios,
.st-key-f4_card_scenario_save,.st-key-f4_card_scenario_list,.st-key-f4_card_scenario_compare,
.st-key-f4_card_compare_bars,.st-key-f4_card_energy_bars,.st-key-f4_card_gis_map{
  border:1px solid #cbd5e1 !important;border-radius:28px !important;
  background:linear-gradient(180deg,#ffffff 0%,#fbfdff 100%) !important;
  box-shadow:0 0 0 1px rgba(148,163,184,.15),0 6px 14px rgba(15,23,42,.08),0 2px 6px rgba(124,58,237,.06) !important;
  overflow:visible !important;box-sizing:border-box !important;margin-bottom:14px !important}
.st-key-f4_card_view_layout,.st-key-f4_card_compare_bars,.st-key-f4_card_energy_bars{overflow:hidden !important}

/* Inner wrapper reset */
.st-key-f4_card_header div[data-testid="stVerticalBlockBorderWrapper"],
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
.st-key-f4_card_scenario_save div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f4_card_scenario_list div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f4_card_scenario_compare div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f4_card_compare_bars div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f4_card_energy_bars div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f4_card_gis_map div[data-testid="stVerticalBlockBorderWrapper"]{
  border:none !important;box-shadow:none !important;border-radius:28px !important;
  background:transparent !important;overflow:visible !important;padding:1.1rem 1.2rem !important}

/* ════ Move subcards ════ */
.st-key-f4_move_turbine_card,.st-key-f4_move_park_card{background:#fff !important;border:1px solid #cbd5e1 !important;border-radius:18px !important;box-shadow:0 2px 8px rgba(124,58,237,.04) !important;overflow:visible !important}
.st-key-f4_rotate_park_card{background:#f0fdf4 !important;border:1px solid #bbf7d0 !important;border-radius:18px !important;box-shadow:0 2px 8px rgba(34,197,94,.04) !important;overflow:visible !important}
.st-key-f4_move_turbine_card div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f4_move_park_card div[data-testid="stVerticalBlockBorderWrapper"],
.st-key-f4_rotate_park_card div[data-testid="stVerticalBlockBorderWrapper"]{padding:.9rem .8rem !important;border:none !important;background:transparent !important;box-shadow:none !important}
.f4-move-subcard-title{font-weight:800 !important;font-size:.95rem !important;text-align:center !important;margin:0 0 .4rem 0 !important}

/* ════ Inputs ════ */
[data-baseweb="input"]{overflow:hidden !important}
div[data-testid="stMetric"]{background:#fff !important;border:1px solid #dde8f5 !important;border-radius:19px !important;padding:.92rem 1rem !important;box-shadow:0 4px 12px rgba(15,23,42,.03) !important}
div[data-testid="stMetricLabel"]{color:#5a6b85 !important;font-weight:600 !important}
div[data-testid="stMetricValue"]{color:#0a2444 !important;font-weight:800 !important}
.stDataFrame,.stDataEditor{border-radius:18px !important;overflow:hidden !important;border:1px solid #dde8f5 !important}

/* ════ Buttons ════ */
.stButton>button,[data-testid="stBaseButton-secondary"]{border-radius:14px !important;border:1.5px solid color-mix(in srgb,var(--ac) 38%,#fff) !important;background:#fff !important;color:var(--ac) !important;font-weight:800 !important;min-height:2.9rem !important;box-shadow:0 4px 12px rgba(124,58,237,.06) !important}
.stButton>button:hover{background:color-mix(in srgb,var(--ac) 6%,#fff) !important;border-color:var(--ac) !important}

/* ════ Tabs ════ */
.stTabs [data-baseweb="tab-list"]{gap:.3rem !important}
.stTabs [data-baseweb="tab"]{border-radius:999px !important;padding:.45rem .95rem !important;background:#f5f3ff !important;color:#5a6b85 !important}
.stTabs [aria-selected="true"]{background:color-mix(in srgb,var(--ac) 12%,#fff) !important;color:var(--ac) !important;font-weight:700 !important}

/* ════ Wake legend ════ */
.f4-wake-legend-card{margin:.45rem 0 1rem;padding:1rem 1.15rem;border:1px solid color-mix(in srgb,var(--ac) 30%,#fff);border-radius:18px;background:#fff;box-shadow:0 8px 20px rgba(15,23,42,.04)}
.f4-wake-legend-title{color:#0a2444;font-size:1.02rem;font-weight:900;margin-bottom:.75rem}
.f4-wake-legend-content{display:grid;grid-template-columns:minmax(220px,.95fr) 1px minmax(300px,1.45fr);gap:1.1rem;align-items:center}
.f4-wake-legend-subtitle{color:#5a6b85;font-size:.88rem;font-weight:800;margin-bottom:.55rem}
.f4-wake-gradient{width:min(320px,100%);height:18px;border-radius:999px;background:linear-gradient(90deg,rgba(219,234,254,.55) 0%,rgba(96,165,250,.68) 45%,rgba(37,99,235,.92) 100%);border:1px solid #bfdbfe}
.f4-wake-legend-divider{width:1px;height:54px;background:#dbeafe}
.f4-wake-status-row{display:flex;align-items:center;gap:.8rem;flex-wrap:wrap}
.f4-wake-status-item{display:inline-flex;align-items:center;gap:.45rem;color:#5a6b85;font-size:.86rem;font-weight:800}
.f4-wake-ring{width:22px;height:22px;border-radius:999px;background:#fff;box-shadow:0 4px 10px rgba(15,23,42,.08)}
.f4-wake-ring-low{border:4px solid #10B981}.f4-wake-ring-mid{border:4px solid #F59E0B}.f4-wake-ring-high{border:4px solid #EF4444}
.f4-wake-status-separator{width:1px;height:24px;background:#e2e8f0}

/* ════ Responsive ════ */
@media(max-width:1100px){.f4-kpi-grid{grid-template-columns:repeat(3,1fr)}.f4-wake-legend-content{grid-template-columns:1fr}.f4-wake-legend-divider{width:100%;height:1px}}
@media(max-width:700px){.f4-kpi-grid{grid-template-columns:repeat(2,1fr)}}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# HERO
# ═══════════════════════════════════════════════════════════════════════════════
def _f4_hero_html(n_turb="—", estela="—", n_esc="—") -> str:
    """Hero Aurora (mockup 04_fase4): icono + título + 3 pills (Turbinas / Estela anual / Escenarios)."""
    return f"""
<div class="hero-card">
<svg class="f4-wind" viewBox="0 0 600 190" preserveAspectRatio="none">
    <path d="M0 42 Q150 24 300 44 T600 34"/><path d="M0 100 Q180 82 340 102 T600 92"/><path d="M0 156 Q140 142 300 158 T600 150"/>
</svg>
<div class="hero-row">
    <div class="hero-icon">🌪️</div>
    <div class="hero-text">
        <div class="fase-hero-title">Fase 4 · Estelas y arreglo del parque</div>
        <div class="fase-hero-subtitle">Configure el arreglo de aerogeneradores, analice el efecto estela geométrico y anual, y compare escenarios.</div>
    </div>
    <div class="hero-pills">
        <div class="hpill"><b>{n_turb}</b><span>Turbinas</span></div>
        <div class="hpill"><b>{estela}</b><span>Estela anual</span></div>
        <div class="hpill"><b>{n_esc}</b><span>Escenarios</span></div>
    </div>
</div>
</div>"""


with st.container(border=True, key="f4_card_header"):
    _f4_hero_slot = st.empty()
    _f4_hero_slot.markdown(_f4_hero_html(), unsafe_allow_html=True)

st.markdown("""
<div class="f4-banner info">
    <div class="bx">💾</div>
    <span>Esta fase guarda automáticamente. Edite, mueva turbinas, rote el parque, guarde escenarios y compare alternativas.</span>
</div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Data loading + defaults (preserved exactly)
# ═══════════════════════════════════════════════════════════════════════════════
df_nasa = cargar_nasa_hourly()
df_curva = cargar_tabla_curva()
diametro = float(config.get("diametro") or 100.0)
altura_deseada_default = float(config.get("perfil_hhub") or 100.0)

if len(df_nasa) == 0:
    st.warning("Primero cargue datos horarios en la Fase 2.")
    st.stop()

layout_type_default = config.get("f4_layout_type", "En línea")
_layout_actual_para_count = cargar_layout_parque()
_layout_size_actual = int(len(_layout_actual_para_count)) if _layout_actual_para_count is not None else 0
_config_num_turbinas = int(float(config.get("f4_num_turbinas", "4")))
num_turbinas_default = _layout_size_actual if _layout_size_actual > 0 else _config_num_turbinas
dx_D_default = float(config.get("f4_dx_D", "5.0"))
dy_D_default = float(config.get("f4_dy_D", "5.0"))
rotation_default = float(config.get("f4_rotation_deg", "0.0"))
ct_default = float(config.get("f4_ct", "0.80"))
kw_default = float(config.get("f4_kw", "0.05"))
wake_model_options_f4 = ["Jensen", "Larsen", "Frandsen", "Gaussian", "TurbOPark", "DWM"]
try:
    from calculos import _pywake_disponible
    if _pywake_disponible():
        wake_model_options_f4 += ["pyWake-NOJ", "pyWake-Bastankhah", "pyWake-Niayifar"]
except Exception:
    pass
wake_model_default_f4 = str(config.get("f4_wake_model") or "Jensen").strip().capitalize()
if wake_model_default_f4 not in wake_model_options_f4:
    wake_model_default_f4 = "Jensen"
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
    "En línea", "En cruz", "Matriz rectangular", "Doble fila",
    "Tresbolillo", "Matriz triangular", "Diagonal", "Circular",
    "Arco", "Aleatorio controlado",
]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Config card (🧩)
# ═══════════════════════════════════════════════════════════════════════════════
with st.container(border=True, key="f4_card_config"):
    _section_header("Configuración del arreglo", "Tipo, separación, coeficientes y modelo de estela", "controls", "#7c3aed")
    with st.form("f4_layout_config_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4, gap="medium")
        with c1:
            layout_type = st.selectbox("Tipo de arreglo", TIPOS_ARREGLO, index=TIPOS_ARREGLO.index(layout_type_default) if layout_type_default in TIPOS_ARREGLO else 0)
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

        c9, c10 = st.columns([1, 3], gap="medium")
        with c9:
            wake_model_f4 = st.selectbox("Modelo de estela", wake_model_options_f4, index=wake_model_options_f4.index(wake_model_default_f4), key="f4_wake_model", help="Jensen (clásico) · Larsen (perfil 3/2, TI ambiente) · Frandsen (parques grandes) · Gaussian (Bastankhah-PA 2014, estándar moderno) · TurbOPark (Orsted 2020, industria 2024)")
        with c10:
            guardar_config_values({"f4_wake_model": wake_model_f4, "f5_wake_model": wake_model_f4})

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

dx_m = dx_D * diametro
dy_m = dy_D * diametro

df_layout_db = cargar_layout_parque()
if len(df_layout_db) == 0:
    df_layout_db = generar_layout_parque(layout_type, num_turbinas, dx_m, dy_m, rotation_deg)
    guardar_layout_parque(df_layout_db)

df_layout = cargar_layout_parque()
if len(df_layout) == 0:
    df_layout = df_layout_db.copy()

# ═══════════════════════════════════════════════════════════════════════════════
# Geometry calculation (preserved)
# ═══════════════════════════════════════════════════════════════════════════════
try:
    f4_geom_signature = (
        _df_signature(df_layout), _df_signature(df_curva),
        float(diametro), float(ct), float(kw), float(velocidad_geom_state),
    )
    resumen_geom, detalles_geom = _session_cached_result(
        "f4_geometria_16", f4_geom_signature,
        lambda: analizar_geometria_16(df_layout=df_layout, curva_df=df_curva, diametro=diametro, ct=ct, kw=kw, velocidad_ref=velocidad_geom_state),
    )
except Exception as e:
    st.error(f"No pude calcular la criticidad geométrica: {e}")
    st.stop()

geom_loss_col = _find_geom_loss_column(resumen_geom)
if geom_loss_col is None:
    st.error("No pude localizar la columna de pérdida geométrica en el resumen del arreglo.")
    st.stop()
geom_loss_series = pd.to_numeric(resumen_geom[geom_loss_col], errors="coerce").fillna(0.0)
max_geom = float(geom_loss_series.max())
sectores_geom_criticos = resumen_geom.loc[np.abs(geom_loss_series - max_geom) <= 1e-4, "Sector"].tolist()
eficiencia_geom = max(0.0, 100.0 - max_geom)
main_base_viento = st.session_state.get("f4_base_viento", base_viento_default)
main_dir_altura = st.session_state.get("f4_dir_altura", dir_altura_default)
main_sector_visual_df, main_sector_visual_meta = _build_main_park_sector_visual_data(
    df_nasa=df_nasa, base_viento=main_base_viento, altura_deseada=altura_deseada,
    roughness_label=roughness_default, direccion_altura=main_dir_altura,
    curva_df=df_curva, fallback_speed=velocidad_geom_state,
)

# Hero pills (dynamic, injected after data is ready)
st.markdown(f"""<script>
var hp=document.getElementById('f4_hero_pills');
if(hp)hp.innerHTML='<div class="hpill"><b>{len(df_layout)}</b><span>Turbinas</span></div><div class="hpill"><b>{max_geom:.1f}%</b><span>Estela máx</span></div><div class="hpill"><b>{eficiencia_geom:.1f}%</b><span>Eficiencia</span></div>';
</script>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# KPI row (Aurora tiles)
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="f4-kpi-grid">' +
    _kpi_tile("🌬️", "Aerogeneradores", f"{len(df_layout)}", "Total en el parque", "#2563eb") +
    _kpi_tile("⊘", "Diámetro rotor", f"{diametro:.1f} m", "Referencia del modelo", "#0ea5e9") +
    _kpi_tile("💨", "Vel. geométrica", f"{velocidad_geom_state:.2f} m/s", "Para análisis geométrico", "#8b5cf6") +
    _kpi_tile("◎", "Sector crítico", ", ".join(sectores_geom_criticos), "Geométricamente críticos", "#f59e0b") +
    _kpi_tile("✓", "Eficiencia geom.", f"{eficiencia_geom:.2f}%", "Eficiencia del arreglo", "#10b981") +
'</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Table + Move (2-col)
# ═══════════════════════════════════════════════════════════════════════════════
layout_edit_cols = st.columns([1.05, 1.15], gap="small")
with layout_edit_cols[0]:
    with st.container(border=True, key="f4_card_edit_table", height=435):
        _section_header("Tabla editable del parque", "Coordenadas x/y en metros", "table", "#7c3aed")
        edited_layout = st.data_editor(df_layout.copy(), num_rows="dynamic", use_container_width=True, key="f4_layout_editor_v4", height=240)
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
        _section_header("Mover turbinas y parque", "Desplazar individualmente o todo el arreglo", "move", "#7c3aed")

        if len(df_layout) > 0:
            turbine_options = df_layout["turbina_id"].astype(str).tolist()
            if selected_turbine_default not in turbine_options:
                selected_turbine_default = turbine_options[0]
            _init_widget_state("f4_selected_turbine", selected_turbine_default)

            m1, m2, m3, m4 = st.columns(4, gap="small")
            with m1:
                turbina_sel = st.selectbox("Turbina seleccionada", turbine_options, index=turbine_options.index(selected_turbine_default), key="f4_selected_turbine")
            with m2:
                move_step_turb = st.number_input("Paso turbina (m)", min_value=1.0, value=50.0, step=10.0, format="%.2f")
            with m3:
                move_step_park = st.number_input("Paso parque (m)", min_value=1.0, value=100.0, step=10.0, format="%.2f")
            with m4:
                rotate_step = st.number_input("Paso rotación (°)", value=5.0, step=1.0, format="%.2f")

            _cur_sel_turb = st.session_state.get("f4_selected_turbine", selected_turbine_default)
            if st.session_state.get("_f4_last_saved_turbine") != _cur_sel_turb:
                guardar_config_values({"f4_selected_turbine": _cur_sel_turb})
                st.session_state["_f4_last_saved_turbine"] = _cur_sel_turb

            move_cards = st.columns(3, gap="small")
            with move_cards[0]:
                with st.container(border=True, key="f4_move_turbine_card", height=235):
                    st.markdown('<div class="f4-move-subcard-title" style="color:#7c3aed">Mover turbina</div>', unsafe_allow_html=True)
                    top_l, top_c, top_r = st.columns(3, gap="small")
                    with top_c:
                        if st.button("↑", use_container_width=True, key="f4_move_turbine_up"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, 0, move_step_turb)); st.rerun()
                    mid_l, mid_c, mid_r = st.columns(3, gap="small")
                    with mid_l:
                        if st.button("←", use_container_width=True, key="f4_move_turbine_left"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, -move_step_turb, 0)); st.rerun()
                    with mid_r:
                        if st.button("→", use_container_width=True, key="f4_move_turbine_right"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, move_step_turb, 0)); st.rerun()
                    bot_l, bot_c, bot_r = st.columns(3, gap="small")
                    with bot_c:
                        if st.button("↓", use_container_width=True, key="f4_move_turbine_down"):
                            guardar_layout_parque(mover_turbina(df_layout, turbina_sel, 0, -move_step_turb)); st.rerun()
            with move_cards[1]:
                with st.container(border=True, key="f4_move_park_card", height=235):
                    st.markdown('<div class="f4-move-subcard-title" style="color:#7c3aed">Mover parque</div>', unsafe_allow_html=True)
                    top_l, top_c, top_r = st.columns(3, gap="small")
                    with top_c:
                        if st.button("↑", use_container_width=True, key="f4_move_park_up"):
                            guardar_layout_parque(mover_parque(df_layout, 0, move_step_park)); st.rerun()
                    mid_l, mid_c, mid_r = st.columns(3, gap="small")
                    with mid_l:
                        if st.button("←", use_container_width=True, key="f4_move_park_left"):
                            guardar_layout_parque(mover_parque(df_layout, -move_step_park, 0)); st.rerun()
                    with mid_r:
                        if st.button("→", use_container_width=True, key="f4_move_park_right"):
                            guardar_layout_parque(mover_parque(df_layout, move_step_park, 0)); st.rerun()
                    bot_l, bot_c, bot_r = st.columns(3, gap="small")
                    with bot_c:
                        if st.button("↓", use_container_width=True, key="f4_move_park_down"):
                            guardar_layout_parque(mover_parque(df_layout, 0, -move_step_park)); st.rerun()
            with move_cards[2]:
                with st.container(border=True, key="f4_rotate_park_card", height=235):
                    st.markdown('<div class="f4-move-subcard-title" style="color:#16a34a">Rotar parque</div>', unsafe_allow_html=True)
                    rot_l, rot_r = st.columns(2, gap="small")
                    with rot_l:
                        if st.button("↺ -", use_container_width=True, key="f4_rotate_park_minus"):
                            guardar_layout_parque(rotar_parque(df_layout, -rotate_step)); st.rerun()
                    with rot_r:
                        if st.button("↻ +", use_container_width=True, key="f4_rotate_park_plus"):
                            guardar_layout_parque(rotar_parque(df_layout, rotate_step)); st.rerun()

df_layout = cargar_layout_parque()

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Park view + Geom summary
# ═══════════════════════════════════════════════════════════════════════════════
view_cols = st.columns([2.7, 0.9], gap="medium")
with view_cols[0]:
    with st.container(border=True, key="f4_card_view_layout"):
        _section_header("Vista del parque y efecto de estela", "Vista en planta con estelas multi-sector", "waves", "#2563eb")
        geom_sector_df_for_park = resumen_geom[["Sector", geom_loss_col]].copy()
        fig_layout = crear_figura_layout_parque(df_layout=df_layout, diametro=diametro, titulo="")
        fig_layout = _enhance_main_park_figure(fig_layout, df_layout, direction_deg=float(main_sector_visual_meta["dominant_deg"]), direction_label=str(main_sector_visual_meta["dominant_label"]), sector_visual_df=main_sector_visual_df, geom_sector_df=geom_sector_df_for_park)
        fig_layout.update_layout(title=None, height=610, margin=dict(l=44, r=28, t=20, b=90), paper_bgcolor="#ffffff", plot_bgcolor="#f8fbff", showlegend=False,
            xaxis=dict(title=dict(text="X (m)", font=dict(size=13, color="#475569")), showgrid=True, gridcolor="rgba(148,163,184,0.20)", zeroline=True, zerolinecolor="rgba(148,163,184,0.35)", tickfont=dict(size=11, color="#64748b")),
            yaxis=dict(title=dict(text="Y (m)", font=dict(size=13, color="#475569")), showgrid=True, gridcolor="rgba(148,163,184,0.20)", zeroline=True, zerolinecolor="rgba(148,163,184,0.35)", tickfont=dict(size=11, color="#64748b"), scaleanchor="x", scaleratio=1),
            annotations=[dict(xref="paper", yref="paper", x=0.01, y=0.99, xanchor="left", yanchor="top", text="<b style='font-size:13px;color:#1e3a8a;'>↗ Viento N (0°)</b>", showarrow=False, bgcolor="rgba(239,246,255,0.88)", bordercolor="#bfdbfe", borderwidth=1, borderpad=5, font=dict(size=12, color="#1d4ed8"))],
        )
        fig_layout = _style_main_park_figure(fig_layout)
        plot_config = {"displayModeBar": True, "displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
        components.html(_cached_park_html(fig=fig_layout, df_layout=df_layout, wind_speed=float(main_sector_visual_meta["representative_speed"]), curva_df=df_curva, plot_config=plot_config, direction_deg=float(main_sector_visual_meta["dominant_deg"])), height=int(fig_layout.layout.height or 610) + 6, scrolling=False)
        st.markdown("""<div style="display:flex;align-items:center;gap:.9rem;margin:.35rem 0 .1rem 0;padding:.48rem .7rem;border:1px solid #cbd5e1;border-radius:12px;background:#fbfdff;font-size:.82rem;">
            <span style="font-weight:800;color:#0a2444">Afectación local por estela</span>
            <span style="display:inline-flex;align-items:center;gap:.32rem"><i style="width:10px;height:10px;border-radius:999px;background:#10B981;display:inline-block"></i>Baja</span>
            <span style="display:inline-flex;align-items:center;gap:.32rem"><i style="width:10px;height:10px;border-radius:999px;background:#F59E0B;display:inline-block"></i>Media</span>
            <span style="display:inline-flex;align-items:center;gap:.32rem"><i style="width:10px;height:10px;border-radius:999px;background:#EF4444;display:inline-block"></i>Alta</span>
        </div>""", unsafe_allow_html=True)

with view_cols[1]:
    with st.container(border=True, key="f4_card_geom_summary"):
        _section_header("Resumen geométrico", "Parámetros del arreglo actual", "info", "#7c3aed")
        summary_items = [
            ("Aerogeneradores", f"{len(df_layout)}"), ("Sep. X (D)", f"{dx_D:.2f}"),
            ("Sep. Y (D)", f"{dy_D:.2f}"), ("Rotación (°)", f"{rotation_deg:.2f}"),
            ("Ct", f"{ct:.2f}"), ("kw", f"{kw:.3f}"),
            ("Altura (m)", f"{altura_deseada:.2f}"), ("Vel. geom.", f"{velocidad_geom_state:.2f} m/s"),
            ("Eficiencia geom.", f"{eficiencia_geom:.2f}%"), ("Sectores críticos", ", ".join(sectores_geom_criticos)),
        ]
        for label, value in summary_items:
            st.markdown(f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #eee"><span style="color:#5a6b85;font-size:13px">{label}</span><b style="color:#0a2444;font-size:13px">{value}</b></div>', unsafe_allow_html=True)
        st.button("Exportar vista", use_container_width=True, key="f4_btn_exportar_vista_layout")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Wind base form
# ═══════════════════════════════════════════════════════════════════════════════
with st.container(border=True, key="f4_card_wind_base"):
    _section_header("Base de viento para análisis anual", "Seleccione el modelo de extrapolación y velocidad geométrica", "wind", "#0ea5e9")
    with st.form("f4_wind_base_form", clear_on_submit=False):
        _init_widget_state("f4_base_viento", base_viento_default)
        _init_widget_state("f4_dir_altura", dir_altura_default)
        _init_widget_state("f4_geom_speed", geom_speed_default)

        v1, v2, v3, v4 = st.columns(4, gap="medium")
        with v1:
            base_viento = st.selectbox("Base de viento anual", ["50 m", "10 m", "Altura deseada - Exponencial", "Altura deseada - Log A (2 puntos)", "Altura deseada - Promedio Log-Exp"],
                index=["50 m", "10 m", "Altura deseada - Exponencial", "Altura deseada - Log A (2 puntos)", "Altura deseada - Promedio Log-Exp"].index(base_viento_default) if base_viento_default in ["50 m", "10 m", "Altura deseada - Exponencial", "Altura deseada - Log A (2 puntos)", "Altura deseada - Promedio Log-Exp"] else 0, key="f4_base_viento")
        with v2:
            dir_altura = st.selectbox("Dirección con altura deseada", ["WD50M", "WD10M"], index=0 if dir_altura_default == "WD50M" else 1, key="f4_dir_altura")
        with v3:
            st.caption("Promedio Log-Exp = promedio entre Exponencial y Log A.")
            roughness_label = roughness_default
        with v4:
            velocidad_geom = st.number_input("Vel. análisis geométrico (m/s)", min_value=0.10, value=geom_speed_default, step=0.10, format="%.2f", key="f4_geom_speed")
        st.form_submit_button("Actualizar análisis anual", use_container_width=True)
    guardar_config_values({
        "f4_base_viento": st.session_state.get("f4_base_viento", base_viento_default),
        "f4_base_viento_canonica": energia_calc.normalize_base_viento_for_energy(st.session_state.get("f4_base_viento", base_viento_default)),
        "f4_dir_altura": st.session_state.get("f4_dir_altura", dir_altura_default),
        "f4_roughness_label": roughness_label,
        "f4_geom_speed": st.session_state.get("f4_geom_speed", geom_speed_default),
    })

    try:
        df_viento_analisis, meta_viento = construir_viento_analisis(df_nasa=df_nasa, base_viento=base_viento, altura_deseada=altura_deseada, roughness_label=roughness_label, direccion_altura=dir_altura)
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

    wm_html = '<div class="f4-kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-top:8px">'
    for label, value, caption in wind_metrics:
        wm_html += _kpi_tile("📊", label, value, caption, "#0ea5e9")
    wm_html += '</div>'
    st.markdown(wm_html, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Geometric analysis
# ═══════════════════════════════════════════════════════════════════════════════
with st.container(border=True, key="f4_card_geom_analysis"):
    _section_header("Análisis geométrico puro del arreglo", "Pérdidas geométricas por sector a velocidad de referencia", "compass", "#7c3aed")
    gk_html = '<div class="f4-kpi-grid" style="grid-template-columns:repeat(3,1fr)">'
    gk_html += _kpi_tile("💨", "Velocidad geométrica", f"{velocidad_geom:.2f} m/s", "Ref. del análisis", "#2563eb")
    gk_html += _kpi_tile("📉", "Peor pérdida geom.", f"{max_geom:.2f}%", "Máxima entre sectores", "#ef4444")
    gk_html += _kpi_tile("◎", "Sectores críticos", ", ".join(sectores_geom_criticos), "Geométricamente críticos", "#f59e0b")
    gk_html += '</div>'
    st.markdown(gk_html, unsafe_allow_html=True)

    fig_geom = crear_rosa_geom(resumen_geom)
    fig_geom.update_layout(title=None, height=520, margin=dict(l=10, r=100, t=20, b=20), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
    fig_geom = _clean_plotly_labels(fig_geom)
    with st.container(border=True, key="f4_geom_rose_subcard"):
        st.markdown('<b style="color:#0a2444;font-size:15px">Rosa geométrica de pérdidas por estela</b>', unsafe_allow_html=True)
        st.plotly_chart(fig_geom, use_container_width=True, key="f4_geom_rose_plot", config=PLOTLY_PERF_CONFIG)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Annual energy analysis
# ═══════════════════════════════════════════════════════════════════════════════
try:
    f4_energy_signature = (_df_signature(df_layout), _df_signature(df_nasa, ["timestamp", "WS10M", "WS50M", "WD10M", "WD50M"]), _df_signature(df_curva), base_viento, "Weibull", "Weibull", float(altura_deseada), roughness_label, dir_altura, int(len(df_layout)), float(diametro), float(ct), float(kw), "Automática desde Fase 4", 0.0, 0.0, 0.0, 0.0)
    energy_result = _session_cached_result("f4_energy_result", f4_energy_signature,
        lambda: energia_calc.calcular_aep_autoritativa(df_layout=df_layout, df_nasa=df_nasa, df_curva_raw=df_curva, base_viento=base_viento, modo_estadistico="Weibull", metodo_detalle="Weibull", altura_deseada=altura_deseada, roughness_label=roughness_label, direccion_fuente=dir_altura, n_turbinas=len(df_layout), diametro=diametro, ct=ct, kw=kw, wake_mode="Automática desde Fase 4", wake_manual_pct=0.0, disp_pct=0.0, elec_pct=0.0, otras_pct=0.0))
except Exception as e:
    st.error(f"No pude calcular el análisis anual: {e}")
    st.stop()

resumen_estelas = energy_result["wake_resumen"].copy()
detalles_estelas = energy_result["wake_detalles"]
perdida_ponderada = float(energy_result["wake_perdida_ponderada"])

if len(resumen_estelas) == 0:
    st.warning("No hay resultados para mostrar.")
    st.stop()

df_sector_energy = energy_result["df_sector"][["Sector", "AEP bruta parque (MWh/año)", "AEP con estela (MWh/año)", "Pérdida estela energética (MWh/año)"]].rename(columns={"AEP bruta parque (MWh/año)": "Energía bruta (MWh/año)", "AEP con estela (MWh/año)": "Energía con estela (MWh/año)", "Pérdida estela energética (MWh/año)": "Pérdida energética (MWh/año)"})
resumen_estelas = resumen_estelas.drop(columns=[col for col in ["Energía bruta (MWh/año)", "Energía con estela (MWh/año)", "Pérdida energética (MWh/año)"] if col in resumen_estelas.columns], errors="ignore").merge(df_sector_energy, on="Sector", how="left")

worst_row = resumen_estelas.sort_values("Pérdida ponderada (%)", ascending=False).iloc[0]
worst_sector = str(worst_row["Sector"])
worst_weighted = float(worst_row["Pérdida ponderada (%)"])
worst_sector_loss = float(worst_row["Pérdida por estela (%)"])
energia_bruta_total = float(energy_result["resumen"]["aep_bruta_total"])
energia_wake_total = float(energy_result["resumen"]["aep_con_estela_total"])
energia_perdida_total = float(energy_result["resumen"]["perdida_estela_mwh"])

guardar_config_values({"f4_weighted_wake_loss_pct": perdida_ponderada, "f4_worst_sector": worst_sector, "f4_worst_sector_loss_pct": worst_sector_loss, "f4_energia_bruta_mwh": energia_bruta_total, "f4_energia_wake_mwh": energia_wake_total, "f4_energia_perdida_mwh": energia_perdida_total, "f4_geom_critical_sectors": ", ".join(sectores_geom_criticos), "f4_geom_max_loss_pct": max_geom})

with st.container(border=True, key="f4_card_annual_analysis"):
    _section_header("Análisis anual ponderado", "Pérdidas ponderadas por frecuencia y energía direccional", "bar-chart-2", "#7c3aed")
    ak_html = '<div class="f4-kpi-grid" style="grid-template-columns:repeat(4,1fr)">'
    ak_html += _kpi_tile("📊", "Pérdida anual pond.", f"{perdida_ponderada:.2f}%", "Total ponderada", "#7c3aed")
    ak_html += _kpi_tile("🧭", "Sector crítico", worst_sector, f"Pérdida: {worst_weighted:.3f}%", "#ef4444")
    ak_html += _kpi_tile("⚡", "Energía bruta", f"{energia_bruta_total:.1f} MWh/año", "", "#2563eb")
    ak_html += _kpi_tile("🔋", "Energía con estela", f"{energia_wake_total:.1f} MWh/año", f"Pérdida: {energia_perdida_total:.1f} MWh", "#10b981")
    ak_html += '</div>'
    st.markdown(ak_html, unsafe_allow_html=True)

    fig_rosa_anual = crear_rosa_anual(resumen_estelas)
    fig_rosa_anual.update_layout(title=None, height=520, margin=dict(l=26, r=28, t=18, b=24), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
    fig_rosa_anual = _clean_plotly_labels(fig_rosa_anual)
    st.caption("Rosa anual ponderada de pérdidas por estela")
    st.plotly_chart(fig_rosa_anual, use_container_width=True, key="f4_annual_wake_rose_plot", config=PLOTLY_PERF_CONFIG)

chart_cols = st.columns(2, gap="medium")
with chart_cols[0]:
    with st.container(border=True, key="f4_card_compare_bars"):
        _section_header("Geométrica vs Anual", "Comparación de criticidad por sector", "bar-chart-2", "#2563eb")
        fig_compare = crear_barras_geom_vs_anual(resumen_geom, resumen_estelas)
        fig_compare.update_layout(title=None, height=360, margin=dict(l=30, r=16, t=14, b=34))
        fig_compare = _clean_plotly_labels(fig_compare)
        st.plotly_chart(fig_compare, use_container_width=True, key="f4_geom_vs_annual_bars_plot", config=PLOTLY_PERF_CONFIG)
with chart_cols[1]:
    with st.container(border=True, key="f4_card_energy_bars"):
        _section_header("Energía anual por dirección", "Bruta vs con estela por sector", "bar-chart-2", "#2563eb")
        fig_energy = crear_barras_energia_direccional(resumen_estelas)
        fig_energy.update_layout(title=None, height=360, margin=dict(l=30, r=16, t=14, b=34))
        fig_energy = _clean_plotly_labels(fig_energy)
        st.plotly_chart(fig_energy, use_container_width=True, key="f4_directional_energy_bars_plot", config=PLOTLY_PERF_CONFIG)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Detail by direction
# ═══════════════════════════════════════════════════════════════════════════════
_detail_icon_speed = _icon_svg("wind", 24, "#0ea5e9")
_detail_icon_loss = _icon_svg("trending-down", 24, "#ef4444")
_detail_icon_eff = _icon_svg("activity", 24, "#10b981")
_detail_icon_turbines = _icon_svg("map-pin", 24, "#f59e0b")
_detail_icon_freq = _icon_svg("bar-chart-2", 24, "#8b5cf6")
_detail_icon_hours = _icon_svg("clock", 24, "#0ea5e9")

with st.container(border=True, key="f4_card_detail_direction"):
    _section_header("Detalle por dirección", "Análisis geométrico y anual por sector", "compass", "#7c3aed")
    sectores_disponibles = resumen_estelas["Sector"].tolist()
    sector_index = sectores_disponibles.index(sector_default) if sector_default in sectores_disponibles else 0
    _init_widget_state("f4_selected_sector", sector_default if sector_default in sectores_disponibles else sectores_disponibles[0])
    sector_elegido = st.selectbox("Seleccione una dirección", sectores_disponibles, index=sector_index, key="f4_selected_sector")
    guardar_config_values({"f4_selected_sector": st.session_state.get("f4_selected_sector", sector_default)})

    fila_sector_detalle = resumen_estelas[resumen_estelas["Sector"] == sector_elegido].iloc[0]
    velocidad_sector_detalle = float(fila_sector_detalle["Velocidad media sector (m/s)"])

    tab1, tab2 = st.tabs(["Detalle geométrico", "Detalle anual"])

    with tab1:
        fila_geom = resumen_geom[resumen_geom["Sector"] == sector_elegido].iloc[0]
        direccion_centro_geom = _get_direction_center_value(fila_geom)
        df_detalle_geom = calcular_estelas_jensen_direccion(df_layout=df_layout, wind_speed=velocidad_sector_detalle, direction_deg=direccion_centro_geom, diametro=diametro, ct=ct, kw=kw, curva_df=df_curva)
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
        with g1: st.metric("Velocidad dirección", f"{fila_geom['Velocidad referencia (m/s)']:.2f} m/s")
        with g2: st.metric("Pérdida geométrica", f"{fila_geom['Pérdida geométrica (%)']:.2f}%")
        with g3: st.metric("Eficiencia geométrica", f"{fila_geom['Eficiencia geométrica (%)']:.2f}%")
        with g4: st.metric("Turbinas afectadas", f"{int(fila_geom['Turbinas afectadas'])}")

        fig_dir_geom = crear_figura_direccion_estela(df_detalle=df_detalle_geom, sector=sector_elegido, direction_deg=direccion_centro_geom, diametro=diametro)
        fig_dir_geom = _add_wake_visual_layers(fig_dir_geom, df_detalle_geom if not df_detalle_geom.empty else df_layout, direction_deg=direccion_centro_geom)
        for trace in fig_dir_geom.data:
            if hasattr(trace, "marker") and trace.marker is not None and hasattr(trace.marker, "colorbar") and trace.marker.colorbar is not None:
                trace.marker.showscale = False
        fig_dir_geom.update_layout(title=None, height=490, margin=dict(l=28, r=28, t=24, b=34), paper_bgcolor="#ffffff", plot_bgcolor="#f8fbff", showlegend=False,
            xaxis=dict(title=dict(text="X (m)", font=dict(size=12, color="#475569")), showgrid=True, gridcolor="rgba(148,163,184,0.20)", zeroline=True, zerolinecolor="rgba(148,163,184,0.30)", tickfont=dict(size=11, color="#64748b")),
            yaxis=dict(title=dict(text="Y (m)", font=dict(size=12, color="#475569")), showgrid=True, gridcolor="rgba(148,163,184,0.20)", zeroline=True, zerolinecolor="rgba(148,163,184,0.30)", tickfont=dict(size=11, color="#64748b"), scaleanchor="x", scaleratio=1),
            annotations=([a for a in (fig_dir_geom.layout.annotations or []) if getattr(a, 'text', '') not in ('', None)] + [dict(xref="paper", yref="paper", x=0.01, y=0.99, xanchor="left", yanchor="top", text=f"<b>&#8599; Viento {sector_elegido} · {direccion_centro_geom:.0f}°</b>", showarrow=False, bgcolor="rgba(239,246,255,0.92)", bordercolor="#93c5fd", borderwidth=1, borderpad=5, font=dict(size=12, color="#1e3a8a"))]))
        fig_dir_geom = _replace_wake_colorbar_with_legend(fig_dir_geom)
        fig_dir_geom = _clean_plotly_labels(fig_dir_geom)
        st.plotly_chart(fig_dir_geom, use_container_width=True, key=f"f4_detail_geom_plot_{sector_elegido}", config=PLOTLY_INTERACTIVE_CONFIG)
        _render_f4_wake_legend()

    with tab2:
        fila_sector = fila_sector_detalle
        df_detalle_sector = detalles_estelas.get(sector_elegido, pd.DataFrame())
        y1, y2, y3, y4, y5 = st.columns(5)
        with y1: st.metric("Frecuencia", f"{fila_sector['Frecuencia (%)']:.2f}%")
        with y2: st.metric("Horas eq. anuales", f"{fila_sector['Horas equivalentes anuales (h/año)']:.1f}")
        with y3: st.metric("U media sector", f"{fila_sector['Velocidad media sector (m/s)']:.2f} m/s")
        with y4: st.metric("Pérdida estela", f"{fila_sector['Pérdida por estela (%)']:.2f}%")
        with y5: st.metric("Pérdida ponderada", f"{fila_sector['Pérdida ponderada (%)']:.3f}%")

        fig_dir = crear_figura_direccion_estela(df_detalle=df_detalle_sector, sector=sector_elegido, direction_deg=float(fila_sector["Dirección centro (°)"]), diametro=diametro)
        fig_dir = _add_wake_visual_layers(fig_dir, df_detalle_sector if not df_detalle_sector.empty else df_layout, direction_deg=float(fila_sector["Dirección centro (°)"]))
        for trace in fig_dir.data:
            if hasattr(trace, "marker") and trace.marker is not None and hasattr(trace.marker, "colorbar") and trace.marker.colorbar is not None:
                trace.marker.showscale = False
        fig_dir.update_layout(title=None, height=490, margin=dict(l=28, r=28, t=24, b=34), paper_bgcolor="#ffffff", plot_bgcolor="#f8fbff", showlegend=False,
            xaxis=dict(title=dict(text="X (m)", font=dict(size=12, color="#475569")), showgrid=True, gridcolor="rgba(148,163,184,0.20)", zeroline=True, zerolinecolor="rgba(148,163,184,0.30)", tickfont=dict(size=11, color="#64748b")),
            yaxis=dict(title=dict(text="Y (m)", font=dict(size=12, color="#475569")), showgrid=True, gridcolor="rgba(148,163,184,0.20)", zeroline=True, zerolinecolor="rgba(148,163,184,0.30)", tickfont=dict(size=11, color="#64748b"), scaleanchor="x", scaleratio=1),
            annotations=([a for a in (fig_dir.layout.annotations or []) if getattr(a, 'text', '') not in ('', None)] + [dict(xref="paper", yref="paper", x=0.01, y=0.99, xanchor="left", yanchor="top", text=f"<b>&#8599; Viento {sector_elegido} · {float(fila_sector['Dirección centro (°)']):.0f}°</b>", showarrow=False, bgcolor="rgba(239,246,255,0.92)", bordercolor="#93c5fd", borderwidth=1, borderpad=5, font=dict(size=12, color="#1e3a8a"))]))
        fig_dir = _replace_wake_colorbar_with_legend(fig_dir)
        fig_dir = _clean_plotly_labels(fig_dir)
        st.plotly_chart(fig_dir, use_container_width=True, key=f"f4_detail_annual_plot_{sector_elegido}", config=PLOTLY_INTERACTIVE_CONFIG)
        _render_f4_wake_legend()

    toolbar_cols = st.columns([1, 1.5, 1.5, 1], gap="small", vertical_alignment="bottom")
    with toolbar_cols[1]:
        st.selectbox("Velocidad", [f"{velocidad_sector_detalle:.1f} m/s"], index=0, key="f4_detail_speed_visual")
    with toolbar_cols[2]:
        st.selectbox("Dirección", [f"{sector_elegido} ({SECTOR_CENTERS_16[SECTOR_LABELS_16.index(sector_elegido)]:.1f}°)"], index=0, key="f4_detail_direction_visual")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Scenarios
# ═══════════════════════════════════════════════════════════════════════════════
with st.container(border=True, key="f4_card_scenarios"):
    _section_header("Guardar y comparar configuraciones", "Administre escenarios del parque y compare alternativas", "cloud-upload", "#7c3aed")

    scenario_cols = st.columns([0.95, 1.2, 1.0], gap="medium")

    with scenario_cols[0]:
        with st.container(border=True, key="f4_card_scenario_save"):
            _section_header("Guardar escenario actual", "", "export", "#2563eb")
            current_scenario_name = st.text_input("Nombre del escenario", value="Escenario_actual")
            if st.button("Guardar escenario", icon=":material/cloud_upload:", use_container_width=True):
                settings_dict = {"layout_type": layout_type, "num_turbinas": int(len(df_layout)), "dx_D": dx_D, "dy_D": dy_D, "rotation_deg": rotation_deg, "ct": ct, "kw": kw, "altura_deseada": altura_deseada, "base_viento": base_viento, "dir_altura": dir_altura, "roughness_label": roughness_label, "velocidad_geom": velocidad_geom, "diametro": diametro}
                metrics_dict = {"perdida_anual_ponderada_pct": perdida_ponderada, "sector_anual_critico": worst_sector, "perdida_sector_anual_pct": worst_sector_loss, "sectores_geom_criticos": ", ".join(sectores_geom_criticos), "perdida_geom_max_pct": max_geom, "energia_bruta_mwh": energia_bruta_total, "energia_wake_mwh": energia_wake_total, "energia_perdida_mwh": energia_perdida_total}
                guardar_escenario_parque(name=current_scenario_name.strip(), df_layout=df_layout, settings_dict=settings_dict, metrics_dict=metrics_dict)
                st.success("Escenario guardado.")
                st.rerun()

    df_scenarios = listar_escenarios_parque()

    with scenario_cols[1]:
        with st.container(border=True, key="f4_card_scenario_list"):
            _section_header("Escenarios guardados", "", "database-stack", "#2563eb")
            if len(df_scenarios) > 0:
                st.dataframe(df_scenarios, use_container_width=True)
            else:
                st.caption("No hay escenarios guardados.")

    with scenario_cols[2]:
        with st.container(border=True, key="f4_card_scenario_compare"):
            _section_header("Comparación", "", "bar-chart-2", "#2563eb")
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
                            "Indicador": ["Pérdida anual ponderada (%)", "Sector anual crítico", "Pérdida sector anual (%)", "Sectores geométricos críticos", "Pérdida geométrica máxima (%)", "Energía bruta (MWh/año)", "Energía con estela (MWh/año)", "Pérdida energética (MWh/año)"],
                            esc_a: [met_a.get("perdida_anual_ponderada_pct", ""), met_a.get("sector_anual_critico", ""), met_a.get("perdida_sector_anual_pct", ""), met_a.get("sectores_geom_criticos", ""), met_a.get("perdida_geom_max_pct", ""), met_a.get("energia_bruta_mwh", ""), met_a.get("energia_wake_mwh", ""), met_a.get("energia_perdida_mwh", "")],
                            esc_b: [met_b.get("perdida_anual_ponderada_pct", ""), met_b.get("sector_anual_critico", ""), met_b.get("perdida_sector_anual_pct", ""), met_b.get("sectores_geom_criticos", ""), met_b.get("perdida_geom_max_pct", ""), met_b.get("energia_bruta_mwh", ""), met_b.get("energia_wake_mwh", ""), met_b.get("energia_perdida_mwh", "")],
                        })
                        st.dataframe(tabla_comp, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. GIS Map
# ═══════════════════════════════════════════════════════════════════════════════
with st.container(border=True, key="f4_card_gis_map"):
    _section_header("Mapa GIS · Turbinas geo-referenciadas", "Visualiza el layout sobre mapa real usando lat/lon del sitio", "map-pin", "#2563eb")

    try:
        lat_site = float(config.get("nasa_lat") or 0.0)
        lon_site = float(config.get("nasa_lon") or 0.0)
    except Exception:
        lat_site, lon_site = 0.0, 0.0

    if abs(lat_site) < 0.01 or abs(lon_site) < 0.01:
        st.info("Configura latitud/longitud del sitio en Fase 2 (mapa NASA) para ver el layout geo-referenciado.")
    elif df_layout is None or len(df_layout) == 0:
        st.info("Sin layout del parque. Genera el arreglo arriba.")
    else:
        try:
            import folium
            from streamlit_folium import st_folium
            from calculos import turbinas_xy_a_latlon

            df_latlon = turbinas_xy_a_latlon(df_layout, lat_centro=lat_site, lon_centro=lon_site, rotation_deg=0.0)

            if len(df_latlon) > 0:
                lat_mean = float(df_latlon["lat"].mean())
                lon_mean = float(df_latlon["lon"].mean())
            else:
                lat_mean, lon_mean = lat_site, lon_site

            map_zoom_gis = st.slider("Zoom mapa", min_value=8, max_value=18, value=14, key="f4_map_zoom_gis")
            map_tiles_gis = st.selectbox("Capa base", ["OpenStreetMap", "CartoDB positron", "CartoDB dark_matter"], key="f4_map_tiles_gis")

            mapa_gis = folium.Map(location=[lat_mean, lon_mean], zoom_start=int(map_zoom_gis), tiles=map_tiles_gis)
            folium.Marker(location=[lat_site, lon_site], popup=f"Centro del sitio<br>lat: {lat_site:.5f}<br>lon: {lon_site:.5f}", icon=folium.Icon(color="purple", icon="star")).add_to(mapa_gis)

            for _, row in df_latlon.iterrows():
                tid = row.get("turbina_id", "T?")
                lat_t = float(row["lat"])
                lon_t = float(row["lon"])
                folium.CircleMarker(location=[lat_t, lon_t], radius=8, color="#7c3aed", fill=True, fill_color="#7c3aed", fill_opacity=0.85, tooltip=f"{tid} · ({lat_t:.5f}, {lon_t:.5f})", popup=f"<b>{tid}</b><br>lat: {lat_t:.6f}<br>lon: {lon_t:.6f}").add_to(mapa_gis)

            lats_gis = df_latlon["lat"].tolist()
            lons_gis = df_latlon["lon"].tolist()
            if len(lats_gis) >= 3:
                pts = list(zip(lats_gis, lons_gis))
                folium.PolyLine(pts + [pts[0]], color="#16a34a", weight=2, opacity=0.5, dash_array="5").add_to(mapa_gis)

            st_folium(mapa_gis, width=1200, height=500, key="f4_mapa_gis_layout")
            st.caption(f"Turbinas plotadas: {len(df_latlon)} · Centro del parque: lat {lat_mean:.5f}, lon {lon_mean:.5f}")

        except ImportError:
            st.warning("Necesita `folium` y `streamlit-folium`. Instalar: `pip install folium streamlit-folium`")
        except Exception as exc:
            st.error(f"Error generando mapa: {exc}")


# Pills del hero con los valores reales (calculados más abajo en la página)
try:
    _f4_hero_n_turb = str(int(len(df_layout))) if df_layout is not None else "—"
    _f4_hero_estela = f"{float(perdida_ponderada):.2f} %".replace(".", ",")
    _f4_hero_n_esc = str(int(len(df_scenarios)))
    _f4_hero_slot.markdown(_f4_hero_html(_f4_hero_n_turb, _f4_hero_estela, _f4_hero_n_esc), unsafe_allow_html=True)
except Exception:
    pass

render_dropdown_visibility_fix()
