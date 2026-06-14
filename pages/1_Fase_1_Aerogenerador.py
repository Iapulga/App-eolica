import textwrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

from calculos import calcular_cp, preparar_datos_curva
from db import (
    cargar_config,
    cargar_tabla_curva,
    guardar_config_values,
    guardar_tabla_curva,
    init_db,
    tabla_vacia_curva,
)
from navigation import _icon_svg, render_dropdown_visibility_fix, render_sidebar_navigation

st.set_page_config(page_title="Fase 1 Aerogenerador", layout="wide")

# Cargar CSS global e inyectar sidebar lo ANTES posible para evitar FOUC
# (flash del diseño por defecto de Streamlit antes que se aplique el tema custom).
render_sidebar_navigation("pages/1_Fase_1_Aerogenerador.py")

init_db()

PLOTLY_PERF_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}


def _tabla_curva_a_kw(df):
    if df is None:
        return pd.DataFrame(columns=["Velocidad (m/s)", "Potencia (kW)"])

    df_kw = df.copy()
    if "Velocidad (m/s)" not in df_kw.columns:
        df_kw["Velocidad (m/s)"] = ""

    if "Potencia (kW)" in df_kw.columns:
        return df_kw[["Velocidad (m/s)", "Potencia (kW)"]]

    if "Potencia (W)" in df_kw.columns:
        potencia_w = pd.to_numeric(
            df_kw["Potencia (W)"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        df_kw["Potencia (kW)"] = potencia_w / 1000.0
        return df_kw[["Velocidad (m/s)", "Potencia (kW)"]]

    df_kw["Potencia (kW)"] = ""
    return df_kw[["Velocidad (m/s)", "Potencia (kW)"]]


def _tabla_curva_kw_a_w(df):
    df_w = df.copy()
    if "Velocidad (m/s)" not in df_w.columns:
        return df_w

    if "Potencia (kW)" in df_w.columns:
        velocidad = pd.to_numeric(
            df_w["Velocidad (m/s)"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        potencia_kw = pd.to_numeric(
            df_w["Potencia (kW)"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )
        return pd.DataFrame({
            "Velocidad (m/s)": velocidad,
            "Potencia (W)": potencia_kw * 1000.0,
        })

    if "Potencia (W)" in df_w.columns:
        return df_w[["Velocidad (m/s)", "Potencia (W)"]]

    return df_w


def _preparar_datos_curva_fase1(df_raw):
    return preparar_datos_curva(_tabla_curva_kw_a_w(df_raw))


def _build_metric_summary(df_resultados):
    if len(df_resultados) == 0:
        return None

    df_valid = df_resultados.dropna(subset=["Potencia_W"]).copy()
    if len(df_valid) == 0:
        return None

    idx_nominal = df_valid["Potencia_W"].astype(float).idxmax()
    fila_nominal = df_valid.loc[idx_nominal]
    return {
        "potencia_nominal_w": float(fila_nominal["Potencia_W"]),
        "velocidad_nominal_ms": float(fila_nominal["Velocidad_num"]),
    }


def _format_power_nominal(potencia_w):
    potencia_kw = potencia_w / 1000.0
    potencia_mw = potencia_w / 1e6
    if potencia_kw >= 1000.0:
        return f"{potencia_mw:,.2f} MW"
    return f"{potencia_kw:,.2f} kW"


def _section_title_html(emoji: str, title: str, subtitle: str = "") -> str:
    """Card-head del mockup Aurora: cicon emoji en squircle + título + subtítulo."""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    return (
        '<div class="f1-card-head">'
        f'<div class="f1-cicon">{emoji}</div>'
        f'<div><h2>{title}</h2>{sub}</div>'
        '</div>'
    )

def _render_metric_card(emoji, label, value, color, formula=""):
    """KPI del mockup Aurora: ki círculo tintado (--kc) + label + valor + fórmula."""
    st.markdown(
        f"""
        <div class="f1-kpi" style="--kc:{color}">
            <div class="f1-ki">{emoji}</div>
            <div class="f1-kpi-copy">
                <small>{label}</small>
                <b>{value}</b>
                <i>{formula}</i>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _phase_card(key: str | None = None):
    return st.container(border=True, key=key)


def _build_esquema_resumen_html(fila_ref, diametro, area, densidad):
    potencia_viento_kw = float(fila_ref["P_viento_W"]) / 1000.0
    potencia_generada_kw = float(fila_ref["Potencia_W"]) / 1000.0
    cp = float(fila_ref["Cp"]) if pd.notna(fila_ref["Cp"]) else np.nan
    rows = [
        ("V", "Velocidad seleccionada", f"{float(fila_ref['Velocidad_num']):.2f} m/s"),
        ("Pv", "Potencia del viento", f"{potencia_viento_kw:,.2f} kW"),
        ("Pg", "Potencia generada", f"{potencia_generada_kw:,.2f} kW"),
        ("Cp", "Cp en esta velocidad", f"{cp:.4f}"),
        ("&rho;", "Densidad del aire", f"{densidad:.2f} kg/m³"),
        ("D", "Diámetro del rotor", f"{diametro:.2f} m"),
    ]
    rows_html = "".join(
        f'<div class="info-row"><span class="row-left"><span class="row-icon">{icon}</span>{label}</span><strong>{value}</strong></div>'
        for icon, label, value in rows
    )
    return f'<div class="soft-panel">{rows_html}</div>'


def _svg_blade_points(cx, cy, angle_deg, length, root_width, mid_width, tip_width):
    ang = np.deg2rad(angle_deg)
    perp = ang + np.pi / 2
    tip_x = cx + length * np.cos(ang)
    tip_y = cy + length * np.sin(ang)
    mid_x = cx + length * 0.42 * np.cos(ang)
    mid_y = cy + length * 0.42 * np.sin(ang)
    pts = [
        (cx + root_width * np.cos(perp), cy + root_width * np.sin(perp)),
        (cx - root_width * np.cos(perp), cy - root_width * np.sin(perp)),
        (mid_x - mid_width * np.cos(perp), mid_y - mid_width * np.sin(perp)),
        (tip_x - tip_width * np.cos(perp), tip_y - tip_width * np.sin(perp)),
        (tip_x + tip_width * np.cos(perp), tip_y + tip_width * np.sin(perp)),
        (mid_x + mid_width * np.cos(perp), mid_y + mid_width * np.sin(perp)),
    ]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def render_esquema_aerogenerador_svg(
    diametro,
    area,
    densidad,
    velocidad,
    potencia_viento_kw,
    potencia_generada_kw,
    cp,
):
    cp_value = float(cp) if pd.notna(cp) and np.isfinite(cp) else np.nan
    cp_text = f"{cp_value:.3f}" if np.isfinite(cp_value) else "N/A"
    potencia_generada_kw = float(potencia_generada_kw)
    velocidad = float(velocidad)
    power_text = f"{potencia_viento_kw:,.0f} kW"
    generated_text = f"{potencia_generada_kw:,.0f} kW"
    if velocidad <= 0 or potencia_generada_kw <= 0:
        rotor_duration = None
    elif velocidad < 3:
        rotor_duration = 8.0
    elif velocidad < 8:
        rotor_duration = 4.0
    elif velocidad < 12:
        rotor_duration = 2.0
    else:
        rotor_duration = 1.2

    # Textos dinámicos (formato es-ES: coma decimal, punto de miles)
    area_text = f"{area:,.0f} m²".replace(",", ".")
    diam_text = f"{diametro:.1f}".replace(".", ",")
    dens_text = f"{densidad:.2f}".replace(".", ",")
    pv_text = f"{potencia_viento_kw:,.0f}".replace(",", ".")
    pg_text = f"{potencia_generada_kw:,.0f}".replace(",", ".")
    cp_box = f"{cp_value:.3f}".replace(".", ",") if np.isfinite(cp_value) else "N/A"

    # Rotación del rotor (SMIL): la duración depende de la velocidad/potencia.
    # rotor_duration is None ⇒ fuera de cut-in/cut-out (potencia ≤ 0) ⇒ NO gira.
    rotor_anim = (
        f'<animateTransform attributeName="transform" attributeType="XML" type="rotate" '
        f'from="0 248 118" to="360 248 118" dur="{rotor_duration:.2f}s" repeatCount="indefinite"/>'
        if rotor_duration is not None
        else ""
    )
    blade = "M248,118 C236,80 240,52 248,40 C256,52 260,80 248,118 Z"

    return textwrap.dedent(
        f"""
        <html style="margin:0;padding:0;width:100%;height:100%;">
        <body style="margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#fff;">
        <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;">
          <svg viewBox="0 0 760 320" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;display:block;font-family:'Segoe UI Variable Display','Segoe UI',Arial,sans-serif;">
            <defs>
              <linearGradient id="f1sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e8f4ff"/><stop offset="1" stop-color="#f8fcff"/></linearGradient>
              <linearGradient id="f1gw" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7dd3fc"/><stop offset="1" stop-color="#0284c7"/></linearGradient>
              <linearGradient id="f1torre" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cbd5e1"/><stop offset="1" stop-color="#64748b"/></linearGradient>
              <linearGradient id="f1aspa" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f8fafc"/><stop offset="1" stop-color="#94a3b8"/></linearGradient>
              <marker id="f1arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="#64748b"/></marker>
            </defs>
            <style>
              .f1flow{{animation:f1fl 1.4s linear infinite}}@keyframes f1fl{{to{{stroke-dashoffset:-52}}}}
              .f1pulse{{animation:f1pl 1.8s ease-in-out infinite}}@keyframes f1pl{{0%,100%{{opacity:.55}}50%{{opacity:1}}}}
            </style>
            <rect x="6" y="6" width="748" height="308" rx="20" fill="url(#f1sky)"/>
            <ellipse cx="248" cy="274" rx="86" ry="10" fill="#0b2447" opacity=".08"/>

            <g><line x1="26" y1="88" x2="120" y2="88" stroke="url(#f1gw)" stroke-width="6" stroke-linecap="round" stroke-dasharray="15 11" class="f1flow" style="animation-duration:1.2s"/><path d="M126 88 l-13 -7.5 v15 Z" fill="#0284c7"/></g>
            <g><line x1="26" y1="124" x2="120" y2="124" stroke="url(#f1gw)" stroke-width="5" stroke-linecap="round" stroke-dasharray="15 11" class="f1flow" style="animation-duration:1.45s"/><path d="M126 124 l-13 -7.5 v15 Z" fill="#0284c7"/></g>
            <g><line x1="26" y1="160" x2="120" y2="160" stroke="url(#f1gw)" stroke-width="6" stroke-linecap="round" stroke-dasharray="15 11" class="f1flow" style="animation-duration:1.7s"/><path d="M126 160 l-13 -7.5 v15 Z" fill="#0284c7"/></g>
            <g><line x1="26" y1="196" x2="120" y2="196" stroke="url(#f1gw)" stroke-width="5" stroke-linecap="round" stroke-dasharray="15 11" class="f1flow" style="animation-duration:1.95s"/><path d="M126 196 l-13 -7.5 v15 Z" fill="#0284c7"/></g>
            <text x="64" y="262" text-anchor="middle" font-size="14" font-weight="900" fill="#0284c7">VIENTO</text>
            <text x="64" y="280" text-anchor="middle" font-size="12" font-weight="800" fill="#0369a1">{velocidad:.1f} m/s</text>

            <circle cx="248" cy="118" r="78" fill="none" stroke="#94a3b8" stroke-width="1.4" stroke-dasharray="5 7"/>
            <path d="M243 274 L253 274 L250 144 L246 144 Z" fill="url(#f1torre)"/>
            <g>
              {rotor_anim}
              <path d="{blade}" fill="url(#f1aspa)" stroke="#64748b" stroke-width="1"/>
              <path d="{blade}" fill="url(#f1aspa)" stroke="#64748b" stroke-width="1" transform="rotate(120 248 118)"/>
              <path d="{blade}" fill="url(#f1aspa)" stroke="#64748b" stroke-width="1" transform="rotate(240 248 118)"/>
            </g>
            <circle cx="248" cy="118" r="10" fill="#1e3a8a"/><circle cx="248" cy="118" r="4.5" fill="#93c5fd"/>
            <line x1="170" y1="196" x2="326" y2="196" stroke="#0284c7" stroke-width="1.6"/>
            <line x1="170" y1="190" x2="170" y2="202" stroke="#0284c7" stroke-width="1.6"/>
            <line x1="326" y1="190" x2="326" y2="202" stroke="#0284c7" stroke-width="1.6"/>
            <text x="248" y="214" text-anchor="middle" font-size="11" font-weight="900" fill="#0284c7">Ø {diam_text} m · A = {area_text}</text>

            <path d="M340 118 H408" stroke="#94a3b8" stroke-width="3" marker-end="url(#f1arr)" stroke-dasharray="9 7" class="f1flow"/>
            <g>
              <rect x="414" y="84" width="98" height="68" rx="15" fill="#fff" stroke="#cbd5e1" stroke-width="1.6"/>
              <text x="463" y="111" text-anchor="middle" font-size="21">⚙️</text>
              <text x="463" y="134" text-anchor="middle" font-size="9.5" font-weight="900" fill="#475569">MULTIPLICADORA</text>
            </g>
            <path d="M518 118 H552" stroke="#94a3b8" stroke-width="3" marker-end="url(#f1arr)" stroke-dasharray="9 7" class="f1flow"/>
            <g>
              <rect x="558" y="84" width="92" height="68" rx="15" fill="#fff" stroke="#cbd5e1" stroke-width="1.6"/>
              <text x="604" y="111" text-anchor="middle" font-size="21">🔌</text>
              <text x="604" y="134" text-anchor="middle" font-size="9.5" font-weight="900" fill="#475569">GENERADOR</text>
            </g>
            <path d="M656 118 H690" stroke="#94a3b8" stroke-width="3" marker-end="url(#f1arr)" stroke-dasharray="9 7" class="f1flow"/>
            <g class="f1pulse"><text x="716" y="106" text-anchor="middle" font-size="26">💡</text></g>
            <text x="716" y="134" text-anchor="middle" font-size="17" font-weight="900" fill="#16a34a">{pg_text} kW</text>
            <text x="716" y="150" text-anchor="middle" font-size="9.5" font-weight="800" fill="#15803d">POTENCIA GENERADA</text>

            <g transform="translate(30,206)">
              <rect x="0" y="0" width="146" height="42" rx="13" fill="#fff" stroke="#dce7f5" stroke-width="1.4"/>
              <text x="73" y="17" text-anchor="middle" font-size="10" font-weight="900" fill="#64748b">ρ AIRE · DIÁMETRO</text>
              <text x="73" y="33" text-anchor="middle" font-size="12" font-weight="900" fill="#0b2447">{dens_text} kg/m³ · {diam_text} m</text>
            </g>
            <g transform="translate(388,206)">
              <rect x="0" y="0" width="158" height="42" rx="13" fill="#eff8ff" stroke="#bae0fd" stroke-width="1.4"/>
              <text x="79" y="17" text-anchor="middle" font-size="10" font-weight="900" fill="#0369a1">P_viento = ½·ρ·A·v³</text>
              <text x="79" y="33" text-anchor="middle" font-size="12" font-weight="900" fill="#0b2447">{pv_text} kW</text>
            </g>
            <g transform="translate(556,206)">
              <rect x="0" y="0" width="158" height="42" rx="13" fill="#f0fdf4" stroke="#bbf7d0" stroke-width="1.4"/>
              <text x="79" y="17" text-anchor="middle" font-size="10" font-weight="900" fill="#15803d">Cp = P_gen / P_viento</text>
              <text x="79" y="33" text-anchor="middle" font-size="12" font-weight="900" fill="#0b2447">{cp_box} · Betz 0,593</text>
            </g>
          </svg>
        </div>
        </body>
        </html>
        """
    ).strip()


@st.cache_data(show_spinner=False)
def _crear_figura_esquema_aerogenerador(diametro, area, fila_ref):
    radio = max(diametro / 2.0, 1.0)
    x_rotor = 0.0
    y_hub = 0.0
    y_base = -radio * 1.58
    tower_x = x_rotor

    velocidad = float(fila_ref["Velocidad_num"])
    potencia_generada_kw = float(fila_ref["Potencia_W"]) / 1000.0
    potencia_viento_kw = float(fila_ref["P_viento_W"]) / 1000.0
    cp = float(fila_ref["Cp"]) if pd.notna(fila_ref["Cp"]) else np.nan

    fig = go.Figure()

    for y_arrow in [radio * 0.7, radio * 0.2, -radio * 0.3]:
        fig.add_annotation(
            x=x_rotor - radio * 1.7,
            y=y_arrow,
            ax=x_rotor - radio * 2.6,
            ay=y_arrow,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            text="",
            showarrow=True,
            arrowhead=3,
            arrowwidth=3,
            arrowcolor="#218bff",
        )

    fig.add_annotation(
        x=x_rotor - radio * 1.95,
        y=-radio * 0.98,
        text=f"<b>VIENTO</b><br><span style='color:#2563eb'>{velocidad:.1f} m/s</span>",
        showarrow=False,
        font=dict(size=13, color="#2563eb"),
    )

    theta = np.linspace(0, 2 * np.pi, 240)
    fig.add_trace(go.Scatter(
        x=x_rotor + radio * np.cos(theta),
        y=y_hub + radio * np.sin(theta),
        mode="lines",
        line=dict(color="#cfd8e6", width=2.2, dash="dot"),
        hoverinfo="skip",
        showlegend=False,
    ))

    cote_y = radio * 1.06
    fig.add_trace(go.Scatter(
        x=[x_rotor - radio, x_rotor + radio],
        y=[cote_y, cote_y],
        mode="lines",
        line=dict(color="#94a3b8", width=1.6, dash="dash"),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[x_rotor - radio, x_rotor - radio],
        y=[cote_y - radio * 0.06, cote_y + radio * 0.06],
        mode="lines",
        line=dict(color="#94a3b8", width=1.6),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[x_rotor + radio, x_rotor + radio],
        y=[cote_y - radio * 0.06, cote_y + radio * 0.06],
        mode="lines",
        line=dict(color="#94a3b8", width=1.6),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.add_annotation(
        x=x_rotor,
        y=cote_y + radio * 0.16,
        text=f"<b>DIÁMETRO DEL ROTOR</b><br>{diametro:.2f} m",
        showarrow=False,
        font=dict(size=12, color="#1f2937"),
    )

    blade_len = radio * 0.98
    blade_width = radio * 0.17
    for angle_deg in [90, 210, 330]:
        ang = np.deg2rad(angle_deg)
        perp = ang + np.pi / 2
        root_x = x_rotor
        root_y = y_hub
        tip_x = x_rotor + blade_len * np.cos(ang)
        tip_y = y_hub + blade_len * np.sin(ang)
        pts_x = [
            root_x + blade_width * 0.12 * np.cos(perp),
            root_x - blade_width * 0.12 * np.cos(perp),
            x_rotor + blade_len * 0.34 * np.cos(ang) - blade_width * 0.32 * np.cos(perp),
            tip_x - blade_width * 0.46 * np.cos(perp),
            tip_x + blade_width * 0.46 * np.cos(perp),
            x_rotor + blade_len * 0.34 * np.cos(ang) + blade_width * 0.32 * np.cos(perp),
            root_x + blade_width * 0.12 * np.cos(perp),
        ]
        pts_y = [
            root_y + blade_width * 0.12 * np.sin(perp),
            root_y - blade_width * 0.12 * np.sin(perp),
            y_hub + blade_len * 0.34 * np.sin(ang) - blade_width * 0.32 * np.sin(perp),
            tip_y - blade_width * 0.46 * np.sin(perp),
            tip_y + blade_width * 0.46 * np.sin(perp),
            y_hub + blade_len * 0.34 * np.sin(ang) + blade_width * 0.32 * np.sin(perp),
            root_y + blade_width * 0.12 * np.sin(perp),
        ]
        fig.add_trace(go.Scatter(
            x=pts_x,
            y=pts_y,
            mode="lines",
            fill="toself",
            line=dict(color="#8b949e", width=1.4),
            fillcolor="rgba(139, 148, 158, 0.92)",
            hoverinfo="skip",
            showlegend=False,
        ))

    fig.add_trace(go.Scatter(
        x=[tower_x, tower_x],
        y=[y_base, y_hub],
        mode="lines",
        line=dict(color="#6b7280", width=10),
        hoverinfo="skip",
        showlegend=False,
    ))

    fig.add_trace(go.Scatter(
        x=[x_rotor],
        y=[y_hub],
        mode="markers",
        marker=dict(size=22, color="#9ca3af", line=dict(color="#6b7280", width=1.5)),
        hoverinfo="skip",
        showlegend=False,
    ))

    box_x0 = x_rotor + radio * 1.75
    box_x1 = x_rotor + radio * 2.75
    box_y0 = -radio * 0.38
    box_y1 = radio * 0.38
    fig.add_shape(
        type="rect",
        x0=box_x0,
        x1=box_x1,
        y0=box_y0,
        y1=box_y1,
        line=dict(color="#aab8cc", width=2),
        fillcolor="rgba(248, 250, 252, 0.98)",
    )
    fig.add_annotation(
        x=(box_x0 + box_x1) / 2,
        y=radio * 0.23,
        text="<b>AEROGENERADOR</b>",
        showarrow=False,
        font=dict(size=11, color="#334155"),
    )

    box_cx = (box_x0 + box_x1) / 2
    box_cy = (box_y0 + box_y1) / 2
    box_h = box_y1 - box_y0
    mini_r = box_h * 0.22
    mini_hub_y = box_cy - box_h * 0.05
    mini_tower_base = mini_hub_y - box_h * 0.33
    fig.add_trace(go.Scatter(
        x=[box_cx, box_cx],
        y=[mini_tower_base, mini_hub_y],
        mode="lines",
        line=dict(color="#64748b", width=4.4),
        hoverinfo="skip",
        showlegend=False,
    ))
    blade_specs = [
        (90, mini_r * 1.05),
        (214, mini_r * 1.08),
        (326, mini_r * 1.08),
    ]
    for ang_deg, blade_len in blade_specs:
        ang = np.deg2rad(ang_deg)
        x_tip = box_cx + blade_len * np.cos(ang)
        y_tip = mini_hub_y + blade_len * np.sin(ang)
        fig.add_trace(go.Scatter(
            x=[box_cx, x_tip],
            y=[mini_hub_y, y_tip],
            mode="lines",
            line=dict(color="#64748b", width=4.2),
            hoverinfo="skip",
            showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=[box_cx],
        y=[mini_hub_y],
        mode="markers",
        marker=dict(size=9, color="#334155", line=dict(color="#334155", width=1.2)),
        hoverinfo="skip",
        showlegend=False,
    ))

    bulb_x = x_rotor + radio * 4.15
    bulb_y = -radio * 0.20
    bulb_r = radio * 0.19
    fig.add_shape(
        type="circle",
        x0=bulb_x - bulb_r,
        x1=bulb_x + bulb_r,
        y0=bulb_y - bulb_r * 0.95,
        y1=bulb_y + bulb_r * 1.05,
        line=dict(color="#f59e0b", width=2.6),
        fillcolor="rgba(255, 236, 179, 0.65)",
    )
    fig.add_shape(
        type="rect",
        x0=bulb_x - bulb_r * 0.22,
        x1=bulb_x + bulb_r * 0.22,
        y0=bulb_y - bulb_r * 1.24,
        y1=bulb_y - bulb_r * 0.82,
        line=dict(color="#f59e0b", width=2.2),
        fillcolor="rgba(253, 230, 138, 0.9)",
    )
    fig.add_shape(
        type="line",
        x0=bulb_x,
        x1=bulb_x,
        y0=bulb_y - bulb_r * 0.48,
        y1=bulb_y + bulb_r * 0.18,
        line=dict(color="#f59e0b", width=2.2),
    )
    fig.add_shape(
        type="line",
        x0=bulb_x - bulb_r * 0.30,
        x1=bulb_x,
        y0=bulb_y - bulb_r * 0.08,
        y1=bulb_y + bulb_r * 0.18,
        line=dict(color="#f59e0b", width=2.0),
    )
    fig.add_shape(
        type="line",
        x0=bulb_x + bulb_r * 0.30,
        x1=bulb_x,
        y0=bulb_y - bulb_r * 0.08,
        y1=bulb_y + bulb_r * 0.18,
        line=dict(color="#f59e0b", width=2.0),
    )
    fig.add_shape(
        type="line",
        x0=bulb_x - bulb_r * 0.20,
        x1=bulb_x + bulb_r * 0.20,
        y0=bulb_y - bulb_r * 0.58,
        y1=bulb_y - bulb_r * 0.58,
        line=dict(color="#f59e0b", width=2.2),
    )
    for x0, y0, x1, y1 in [
        (bulb_x, bulb_y + bulb_r * 1.18, bulb_x, bulb_y + bulb_r * 1.48),
        (bulb_x - bulb_r * 0.88, bulb_y + bulb_r * 0.66, bulb_x - bulb_r * 1.10, bulb_y + bulb_r * 0.90),
        (bulb_x + bulb_r * 0.88, bulb_y + bulb_r * 0.66, bulb_x + bulb_r * 1.10, bulb_y + bulb_r * 0.90),
        (bulb_x - bulb_r * 1.08, bulb_y + bulb_r * 0.05, bulb_x - bulb_r * 1.34, bulb_y + bulb_r * 0.05),
        (bulb_x + bulb_r * 1.08, bulb_y + bulb_r * 0.05, bulb_x + bulb_r * 1.34, bulb_y + bulb_r * 0.05),
        (bulb_x - bulb_r * 0.82, bulb_y - bulb_r * 0.66, bulb_x - bulb_r * 1.02, bulb_y - bulb_r * 0.86),
        (bulb_x + bulb_r * 0.82, bulb_y - bulb_r * 0.66, bulb_x + bulb_r * 1.02, bulb_y - bulb_r * 0.86),
    ]:
        fig.add_shape(
            type="line",
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            line=dict(color="#f59e0b", width=2.0),
        )
    fig.add_annotation(
        x=bulb_x,
        y=radio * 0.62,
        text=f"<b>POTENCIA GENERADA</b><br><span style='color:#16a34a'>{potencia_generada_kw:,.0f} kW</span>",
        showarrow=False,
        font=dict(size=14, color="#1f2937"),
    )

    fig.add_annotation(
        x=box_x1 + radio * 0.15,
        y=0,
        ax=x_rotor + radio * 0.95,
        ay=0,
        xref="x",
        yref="y",
        axref="x",
        ayref="y",
        text="",
        showarrow=True,
        arrowhead=3,
        arrowwidth=2.5,
        arrowcolor="#1f2937",
    )
    fig.add_annotation(
        x=bulb_x - radio * 0.62,
        y=-radio * 0.02,
        ax=box_x1 + radio * 0.18,
        ay=-radio * 0.02,
        xref="x",
        yref="y",
        axref="x",
        ayref="y",
        text="",
        showarrow=True,
        arrowhead=3,
        arrowwidth=2.5,
        arrowcolor="#1f2937",
    )

    fig.add_annotation(
        x=x_rotor + radio * 1.05,
        y=-radio * 1.05,
        text=(
            f"<b>Potencia del viento</b>: {potencia_viento_kw:,.0f} kW<br>"
            f"<b>Área</b>: {area:,.0f} m²<br>"
            f"<b>Cp</b>: <span style='color:#16a34a'>{cp:.3f}</span>"
        ),
        showarrow=False,
        font=dict(size=12, color="#334155"),
        align="left",
    )

    fig.update_layout(
        template="plotly_white",
        height=490,
        margin=dict(l=4, r=4, t=4, b=4),
        paper_bgcolor="white",
        plot_bgcolor="white",
        xaxis=dict(visible=False, range=[x_rotor - radio * 2.8, x_rotor + radio * 4.95]),
        yaxis=dict(visible=False, range=[y_base - radio * 0.10, radio * 1.30], scaleanchor="x", scaleratio=1),
        showlegend=False,
    )
    return fig


if "f1_editor_version" not in st.session_state:
    st.session_state["f1_editor_version"] = 0

if "f1_tabla_raw" not in st.session_state:
    st.session_state["f1_tabla_raw"] = _tabla_curva_a_kw(cargar_tabla_curva())
else:
    st.session_state["f1_tabla_raw"] = _tabla_curva_a_kw(st.session_state["f1_tabla_raw"])

if "f1_mensaje" not in st.session_state:
    st.session_state["f1_mensaje"] = ""

config = cargar_config()

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%);
    }
    [data-testid="stDataFrame"] [role="columnheader"] {
        color: #0f172a !important;
        font-weight: 800 !important;
    }
    [data-testid="stDataFrame"] [role="columnheader"] * {
        color: #0f172a !important;
        font-weight: 800 !important;
    }
    [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {
        color: #0f172a !important;
        font-weight: 800 !important;
    }
    [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] * {
        color: #0f172a !important;
        font-weight: 800 !important;
    }
    div[data-testid="stButton"] > button,
    div[data-testid="stFormSubmitButton"] > button {
        border-radius: 14px !important;
        padding: 0.72rem 1rem !important;
        font-weight: 500 !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05) !important;
        transition: all 0.18s ease !important;
    }
    div[data-testid="stButton"] > button {
        background: #ffffff !important;
        color: #2563eb !important;
        border-color: #cbd5e1 !important;
    }
    div[data-testid="stButton"] > button:hover {
        background: #f8fbff !important;
        border-color: #93c5fd !important;
    }
    div[data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%) !important;
        color: #2563eb !important;
        border-color: #93c5fd !important;
    }
    div[data-testid="stFormSubmitButton"] > button:hover {
        background: linear-gradient(180deg, #dbeafe 0%, #bfdbfe 100%) !important;
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
        color: #000000;
        font-size: 0.94rem;
        line-height: 1.42;
        font-weight: 400;
        margin: 0;
        max-width: 74rem;
        position: relative;
        z-index: 2;
    }
    .sma-phase-title-shell {
        width: 100% !important;
        box-sizing: border-box !important;
        background: #ffffff !important;
        border: 1px solid #d7e6f8 !important;
        border-radius: 30px !important;
        padding: 0.45rem 0.72rem 0.72rem 0.72rem !important;
        box-shadow: 0 8px 22px rgba(15, 45, 90, 0.045) !important;
        margin: -1.45rem 0 1rem 0 !important;
        overflow: hidden !important;
    }
    .sma-phase-title-inner {
        position: relative !important;
        overflow: hidden !important;
        box-sizing: border-box !important;
        min-height: unset !important;
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%) !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 20px !important;
        padding: 1.45rem 1.55rem 1.35rem 1.55rem !important;
        display: flex !important;
        align-items: center !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
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
        color: #000000 !important;
        font-size: 0.94rem !important;
        line-height: 1.42 !important;
        font-weight: 500 !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 1.02rem 1.08rem !important;
        margin-bottom: 0.92rem !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] {
        gap: 0.62rem !important;
    }
    .st-key-f1_card_a,
    .st-key-f1_card_b,
    .st-key-f1_card_c,
    .st-key-f1_card_d,
    .st-key-f1_card_e,
    .st-key-f1_card_f,
    .st-key-f1_card_g {
        border-radius: 18px !important;
        overflow: visible !important;
    }
    .st-key-f1_card_a > div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_b > div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_c > div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_d > div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_e > div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_f > div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_g > div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #f8fbff !important;
        border: 2px solid #aebcd2 !important;
        border-radius: 18px !important;
        box-shadow:
            0 0 0 1px rgba(148, 163, 184, 0.35),
            0 6px 14px rgba(15, 23, 42, 0.13),
            0 2px 6px rgba(37, 99, 235, 0.10) !important;
    }
    .phase-card {
        padding: 1.24rem 1.24rem 1.16rem 1.24rem;
        margin-bottom: 1.02rem;
    }
    .section-title {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        font-size: 1.14rem;
        font-weight: 760;
        color: #1d4ed8;
        margin-bottom: 0.16rem;
    }
    .section-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        flex-shrink: 0;
    }
    .muted-text {
        color: #000000;
        font-size: 0.94rem;
        margin-bottom: 0.72rem;
    }
    .metric-card {
        display: flex;
        align-items: center;
        gap: 0.9rem;
        border-radius: 18px;
        padding: 0.94rem 1rem;
        border: 1px solid #d7e5f7;
        box-shadow: none;
    }
    .metric-blue { background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%); }
    .metric-green { background: linear-gradient(180deg, #f8fff8 0%, #eefbf1 100%); }
    .metric-violet { background: linear-gradient(180deg, #fcf9ff 0%, #f4efff 100%); }
    .metric-icon {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        background: rgba(255,255,255,0.92);
        border: 1px solid #cbd5e1;
        flex-shrink: 0;
    }
    .metric-icon svg {
        width: 24px;
        height: 24px;
    }
    .metric-copy { min-width: 0; }
    .metric-label {
        font-size: 0.82rem;
        color: #000000;
        margin-bottom: 0.16rem;
    }
    .metric-value {
        font-size: 1.42rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
    }
    .soft-panel {
        background: #ffffff;
        border: 1px solid #e5edf9;
        border-radius: 14px;
        padding: 0.72rem 0.82rem;
    }
    .row-left {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
    }
    .row-icon {
        width: 18px;
        text-align: center;
        color: #2563eb;
        font-size: 0.9rem;
        font-weight: 700;
    }
    .info-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        padding: 0.42rem 0;
        border-bottom: 1px solid #edf2f7;
        font-size: 0.9rem;
        color: #000000;
    }
    .info-row:last-child { border-bottom: none; }
    .formula-strip {
        margin-top: 0.78rem;
        background: linear-gradient(180deg, #f8fbff 0%, #edf5ff 100%);
        border: 1px solid #cbd5e1;
        border-radius: 13px;
        padding: 0.72rem 0.96rem;
        color: #000000;
        font-size: 0.94rem;
        text-align: center;
    }
    .technical-note {
        background: linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
        border: 1px solid #cbd5e1;
        border-radius: 16px;
        padding: 0.82rem 0.92rem;
        color: #000000;
        font-size: 0.92rem;
        line-height: 1.48;
    }
    .f1-notes-bottom-spacer {
        height: 1rem;
    }
    .chart-surface {
        background: linear-gradient(180deg, #ffffff 0%, #fcfdff 100%);
        border: 1px solid #e5eefb;
        border-radius: 16px;
        padding: 0.52rem 0.58rem 0.18rem 0.58rem;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.94);
    }
    .st-key-f1_card_a [data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.82rem 1rem 0.75rem 1rem !important;
    }
    .st-key-f1_card_b [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_c [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_d [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_e [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_f [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_g [data-testid="stVerticalBlockBorderWrapper"] {
        padding-top: 0.96rem !important;
    }
    .st-key-f1_card_b [data-testid="stVerticalBlockBorderWrapper"] {
        padding-bottom: 1.72rem !important;
        overflow: visible !important;
    }
    .st-key-f1_card_b [data-testid="stHorizontalBlock"],
    .st-key-f1_card_c [data-testid="stHorizontalBlock"],
    .st-key-f1_card_d [data-testid="stHorizontalBlock"],
    .st-key-f1_card_e [data-testid="stHorizontalBlock"],
    .st-key-f1_card_h [data-testid="stHorizontalBlock"] {
        align-items: stretch;
    }
    .st-key-f1_card_b [data-testid="stHorizontalBlock"] {
        margin-bottom: 0.5rem !important;
    }
    .st-key-f1_card_b .metric-card {
        min-height: 96px;
        height: 100%;
        margin-bottom: 0.2rem;
    }
    .st-key-f1_card_b [data-testid="stNumberInput"] [data-baseweb="input"] {
        min-height: 46px !important;
        background: #ffffff !important;
        border: 1px solid #bfdbfe !important;
        border-radius: 14px !important;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.98), 0 1px 2px rgba(15, 23, 42, 0.02) !important;
        display: flex !important;
        align-items: center !important;
        overflow: hidden !important;
    }
    .st-key-f1_card_b [data-testid="stNumberInput"] [data-baseweb="input"] > div {
        background: #ffffff !important;
    }
    .st-key-f1_card_b [data-testid="stNumberInput"] input {
        background: #ffffff !important;
        border: none !important;
        padding-left: 1rem !important;
        font-weight: 800 !important;
        color: #0f172a !important;
    }
    .st-key-f1_card_b [data-testid="stNumberInput"] [data-baseweb="input"] > div:last-child {
        background: #ffffff !important;
        border-left: 1px solid #dbeafe !important;
    }
    .st-key-f1_card_b [data-testid="stNumberInput"] button {
        background: #ffffff !important;
        border-left: 1px solid #dbeafe !important;
        color: #0f172a !important;
        min-width: 2.35rem !important;
        font-weight: 900 !important;
    }
    .st-key-f1_card_b [data-testid="stNumberInput"] button:hover {
        background: #eff6ff !important;
    }
    .st-key-f1_card_b [data-testid="stNumberInput"] label {
        color: #0f172a !important;
        font-weight: 800 !important;
    }
    .st-key-f1_card_c .muted-text,
    .st-key-f1_card_d .muted-text,
    .st-key-f1_card_e .muted-text {
        margin-bottom: 0.48rem;
    }
    .st-key-f1_card_c [data-testid="column"] {
        align-self: flex-start;
    }
    .st-key-f1_card_c [data-testid="stVerticalBlockBorderWrapper"] {
        padding-bottom: 0rem !important;
    }
    .st-key-f1_card_c iframe {
        border-radius: 14px;
    }
    .st-key-f1_card_c [data-testid="stSelectbox"],
    .st-key-f1_card_c .soft-panel {
        margin-bottom: 0.18rem;
    }
    .st-key-f1_card_c .soft-panel {
        height: auto;
        min-height: unset;
    }
    .st-key-f1_card_c [data-testid="stHorizontalBlock"] {
        align-items: flex-start;
    }
    .st-key-f1_card_d [data-testid="stDataEditor"] {
        margin-top: 0.12rem;
    }
    .st-key-f1_card_d [data-testid="stFormSubmitButton"] > button,
    .st-key-f1_card_d [data-testid="stButton"] > button,
    .st-key-f1_card_e [data-testid="stPlotlyChart"] {
        margin-top: 0.1rem;
    }
    .st-key-f1_card_d,
    .st-key-f1_card_e {
        height: 100%;
    }
    .st-key-f1_card_d > div,
    .st-key-f1_card_e > div {
        height: 100%;
    }
    .st-key-f1_card_d [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_e [data-testid="stVerticalBlockBorderWrapper"] {
        height: 600px !important;
        min-height: 600px !important;
        max-height: 600px !important;
        box-sizing: border-box !important;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        padding-bottom: 1rem !important;
    }
    .st-key-f1_card_d [data-testid="stVerticalBlock"],
    .st-key-f1_card_e [data-testid="stVerticalBlock"] {
        flex: 1 1 auto;
    }
    .st-key-f1_card_f [data-testid="stVerticalBlockBorderWrapper"] {
        padding-top: 0.78rem;
        padding-bottom: 1.12rem !important;
    }
    .final-expanders [data-testid="stExpander"] {
        border: 1px solid #cfdcf3 !important;
        border-radius: 18px !important;
        background: linear-gradient(180deg, #fbfdff 0%, #f4f8ff 100%) !important;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(59, 130, 246, 0.08);
        margin-bottom: 0.65rem;
    }
    .final-expanders [data-testid="stExpander"] summary {
        padding-top: 0.1rem !important;
        padding-bottom: 0.1rem !important;
    }
    @media (max-width: 1100px) {
        .st-key-f1_card_d [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f1_card_e [data-testid="stVerticalBlockBorderWrapper"] {
            height: auto !important;
            min-height: auto !important;
            max-height: none !important;
            padding-bottom: 0.92rem !important;
        }
    }
    /* =========================================================
       FORZADO FINAL: borde exterior real de cards grandes Fase 1
       ========================================================= */
    .st-key-f1_card_a,
    .st-key-f1_card_b,
    .st-key-f1_card_c,
    .st-key-f1_card_d,
    .st-key-f1_card_e,
    .st-key-f1_card_f,
    .st-key-f1_card_g,
    .st-key-f1_card_multi_curvas {
        border: 1.4px solid #cbd5e1 !important;
        border-radius: 28px !important;
        overflow: visible !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    }

    .st-key-f1_card_a div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_b div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_c div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_d div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_e div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_f div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_g div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_multi_curvas div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        box-shadow: none !important;
        border-radius: 28px !important;
        background: transparent !important;
        overflow: visible !important;
    }
    /* ==========================================================
       Fase 1 - Igualar cards Curva de potencia / Resultados gráficos
       ========================================================== */
    .st-key-f1_card_curva_potencia,
    .st-key-f1_card_resultados_graficos {
        width: 100% !important;
        height: 640px !important;
        min-height: 640px !important;
        max-height: 640px !important;
        box-sizing: border-box !important;
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 28px !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        overflow: hidden !important;
        padding: 1.05rem 1.15rem !important;
    }

    .st-key-f1_card_curva_potencia [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_resultados_graficos [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_curva_potencia div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f1_card_resultados_graficos div[data-testid="stVerticalBlockBorderWrapper"] {
        width: 100% !important;
        height: 100% !important;
        min-height: 100% !important;
        max-height: 100% !important;
        box-sizing: border-box !important;
        background: transparent !important;
        border: none !important;
        border-radius: 28px !important;
        box-shadow: none !important;
        overflow: hidden !important;
        padding: 0 !important;
    }

    .st-key-f1_card_curva_potencia [data-testid="stVerticalBlock"],
    .st-key-f1_card_resultados_graficos [data-testid="stVerticalBlock"] {
        height: 100% !important;
        min-height: 100% !important;
        max-height: 100% !important;
        box-sizing: border-box !important;
        overflow: hidden !important;
    }

    .st-key-f1_card_curva_potencia > div,
    .st-key-f1_card_resultados_graficos > div {
        width: 100% !important;
    }
    /* ==========================================================
       Fase 1 - Header interno Curva de potencia
       ========================================================== */
    .f1-power-subtitle {
        margin: 0 !important;
        padding: 0.35rem 0 0 0 !important;
        color: #000000 !important;
        font-size: 0.98rem !important;
        font-weight: 500 !important;
        line-height: 1.35 !important;
    }
    .st-key-f1_card_curva_potencia [data-testid="stButton"] > button {
        height: 52px !important;
        border-radius: 14px !important;
        border: 1px solid #cbd5e1 !important;
        background: #ffffff !important;
        color: #2563eb !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <style>
    .st-key-f1_card_header {
        border: 1.35px solid #cbd5e1 !important;
        border-radius: 28px !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        overflow: visible !important;
    }
    .st-key-f1_card_header div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #f8fbff !important;
        border: 2px solid #aebcd2 !important;
        border-radius: 18px !important;
        box-shadow: 0 0 0 1px rgba(148,163,184,.35), 0 6px 14px rgba(15,23,42,.13), 0 2px 6px rgba(37,99,235,.10) !important;
        padding: 1.05rem 1.05rem .95rem 1.05rem !important;
        min-height: unset !important;
        height: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    """
<style>
/* ═══════ Paridad F1 con el mockup 01_fase1 (Aurora, acento cian) ═══════ */
/* Hero */
.f1-hero{position:relative;overflow:hidden;border-radius:26px !important;padding:22px 28px !important;
  background:linear-gradient(118deg,var(--ac,#0284c7) 0%, var(--ac2,#075985) 80%) !important;border:none !important;
  box-shadow:0 22px 44px color-mix(in srgb,var(--ac,#0284c7) 32%,transparent), inset 0 1px 0 rgba(255,255,255,.25) !important;
  margin:0 !important}
.f1-hero::after{content:"";position:absolute;inset:0;pointer-events:none;background:
  radial-gradient(circle at 86% 12%, rgba(255,255,255,.20) 0 54px, transparent 55px),
  radial-gradient(circle at 95% 70%, rgba(255,255,255,.12) 0 86px, transparent 87px),
  linear-gradient(180deg, rgba(255,255,255,.08), transparent 40%)}
.f1-wind{position:absolute;left:-30px;top:0;bottom:0;width:58%;height:100%;opacity:.45;pointer-events:none;z-index:1}
.f1-wind path{stroke:rgba(255,255,255,.55);stroke-width:2;fill:none;stroke-dasharray:16 11;animation:f1windmove 2.6s linear infinite}
.f1-wind path:nth-child(2){animation-duration:3.4s;opacity:.7}
.f1-wind path:nth-child(3){animation-duration:4.2s;opacity:.5}
@keyframes f1windmove{to{stroke-dashoffset:-54}}
.f1-hero-row{display:flex;align-items:center;gap:18px;position:relative;z-index:2}
.f1-hero-icon{width:62px;height:62px;border-radius:19px;background:rgba(255,255,255,.17);
  border:1.5px solid rgba(255,255,255,.4);display:flex;align-items:center;justify-content:center;font-size:31px;flex-shrink:0;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 8px 18px rgba(0,0,0,.12)}
.f1-hero-text{flex:1;min-width:0}
.f1-hero .fase-hero-title{font-size:25px !important;font-weight:900 !important;color:#fff !important;letter-spacing:-.025em !important;
  text-shadow:0 1px 2px rgba(0,0,0,.12) !important;margin:0 !important;line-height:1.15 !important}
.f1-hero .fase-hero-subtitle{font-size:12.5px !important;color:rgba(255,255,255,.94) !important;font-weight:500 !important;
  max-width:840px;margin:4px 0 0 0 !important;line-height:1.45 !important}
.f1-hero-pills{display:flex;gap:9px;margin-left:auto;flex-shrink:0}
.f1-hpill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4);border-radius:15px;
  padding:8px 15px;text-align:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.25);color:#fff}
.f1-hpill b{display:block;font-size:16.5px;letter-spacing:-.01em}
.f1-hpill span{font-size:9px;opacity:.92;text-transform:uppercase;letter-spacing:.07em;font-weight:700}

/* Card-head (reemplaza .section-title) */
.f1-card-head{display:flex;align-items:center;gap:13px;margin-bottom:14px}
.f1-cicon{width:46px;height:46px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;
  background:linear-gradient(135deg, color-mix(in srgb,var(--ac,#0284c7) 16%,#fff), color-mix(in srgb,var(--ac,#0284c7) 7%,#fff));
  border:1.5px solid color-mix(in srgb,var(--ac,#0284c7) 35%,#fff);
  box-shadow:0 5px 12px color-mix(in srgb,var(--ac,#0284c7) 16%,transparent)}
.f1-card-head h2{margin:0;font-size:16.5px;font-weight:900;color:#0b2447;letter-spacing:-.02em}
.f1-card-head p{margin:2px 0 0;font-size:11px;color:#5a6b85;font-weight:600}

/* KPI (reemplaza .metric-card) */
.f1-kpi{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;display:flex;gap:12px;align-items:center;
  box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06);min-height:74px}
.f1-ki{width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;
  background:linear-gradient(135deg, color-mix(in srgb,var(--kc,#2563eb) 17%,#fff), color-mix(in srgb,var(--kc,#2563eb) 6%,#fff));
  border:1.5px solid color-mix(in srgb,var(--kc,#2563eb) 38%,#fff);
  box-shadow:0 5px 12px color-mix(in srgb,var(--kc,#2563eb) 18%,transparent)}
.f1-kpi-copy{min-width:0}
.f1-kpi small{display:block;font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.07em}
.f1-kpi b{font-size:20px;letter-spacing:-.025em;line-height:1.08;display:block;margin-top:3px;color:#0b2447;font-variant-numeric:tabular-nums}
.f1-kpi i{font-style:normal;font-size:10px;color:#5a6b85;display:block;margin-top:2.5px;font-weight:600}

/* Banner */
.f1-banner{display:flex;align-items:center;gap:12px;border-radius:15px;padding:12px 16px;font-weight:800;font-size:12.5px;margin:4px 0 0}
.f1-banner .f1-bx{width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:18px;background:rgba(255,255,255,.7);flex-shrink:0}
.f1-banner.info{background:linear-gradient(120deg, color-mix(in srgb,var(--ac,#0284c7) 8%,#fff), #fff);border:1.5px solid color-mix(in srgb,var(--ac,#0284c7) 30%,#fff);color:var(--ac,#0284c7)}
.f1-banner.warn{background:linear-gradient(120deg,#fffbeb,#fff);border:1.5px solid #fde68a;color:#b45309}

/* Look de card del mockup en las cards reales de F1 (la clase st-key cae en el
   stVerticalBlock mismo, igual que en Inicio → se estila directo). */
.st-key-f1_card_b, .st-key-f1_card_c,
.st-key-f1_card_curva_potencia, .st-key-f1_card_resultados_graficos,
.st-key-f1_card_f, .st-key-f1_card_g, .st-key-f1_card_multi_curvas{
  position:relative !important;overflow:hidden !important;
  background:linear-gradient(180deg,#fff,#fcfdff) !important;
  border:1px solid #d3e0f0 !important;border-radius:26px !important;
  padding:20px 22px 18px !important;
  box-shadow:0 1px 2px rgba(11,36,71,.05), 0 10px 28px rgba(11,36,71,.08) !important}
/* El card del hero es solo envoltura: sin card-look ni franja (el .f1-hero ya es el visual) */
.st-key-f1_card_header{padding:0 !important;border:none !important;background:transparent !important;box-shadow:none !important;overflow:visible !important;margin-bottom:14px !important}
.st-key-f1_card_header::before{display:none !important}
/* Botón primary (Guardar y actualizar) con gradiente del acento, ganando al CSS local viejo */
.st-key-f1_card_curva_potencia div[data-testid="stFormSubmitButton"] > button{
  background:linear-gradient(120deg,var(--ac,#0284c7),var(--ac2,#075985)) !important;color:#fff !important;
  border:none !important;border-radius:13px !important;font-weight:800 !important;
  box-shadow:0 10px 20px color-mix(in srgb,var(--ac,#0284c7) 35%,transparent) !important}
.st-key-f1_card_curva_potencia div[data-testid="stFormSubmitButton"] > button p{color:#fff !important;font-weight:800 !important}
</style>
""",
    unsafe_allow_html=True,
)

# Valores reales para las pills del hero (cálculo ligero con los defaults del
# proyecto; el card de Parámetros recalcula igual más abajo).
_d_pill = float(config.get("diametro", 100.0))
_rho_pill = float(config.get("densidad", 1.22))
try:
    _df_pill = calcular_cp(
        _preparar_datos_curva_fase1(st.session_state["f1_tabla_raw"]),
        _rho_pill,
        np.pi * (_d_pill / 2) ** 2,
    )
    _ms_pill = _build_metric_summary(_df_pill)
    _pnom_pill = _format_power_nominal(_ms_pill["potencia_nominal_w"]) if _ms_pill else "—"
    _cpmax = _df_pill["Cp"].dropna().max() if len(_df_pill) else float("nan")
    _cpmax_pill = f"{_cpmax:.2f}".replace(".", ",") if pd.notna(_cpmax) else "—"
except Exception:
    _pnom_pill, _cpmax_pill = "—", "—"
_d_pill_str = f"{_d_pill:.1f}".replace(".", ",") + " m"

with _phase_card("f1_card_header"):
    st.markdown(
        f"""
        <div class="hero-card f1-hero">
            <svg class="f1-wind" viewBox="0 0 600 190" preserveAspectRatio="none">
                <path d="M0 42 Q150 24 300 44 T600 34"/>
                <path d="M0 100 Q180 82 340 102 T600 92"/>
                <path d="M0 156 Q140 142 300 158 T600 150"/>
            </svg>
            <div class="f1-hero-row">
                <div class="f1-hero-icon">🌀</div>
                <div class="f1-hero-text">
                    <h1 class="fase-hero-title">Fase 1 · Aerogenerador y curva de potencia</h1>
                    <div class="fase-hero-subtitle">Defina el aerogenerador, su diámetro, la densidad del aire y la curva de potencia para calcular Cp.</div>
                </div>
                <div class="f1-hero-pills">
                    <div class="f1-hpill"><b>{_d_pill_str}</b><span>Ø rotor</span></div>
                    <div class="f1-hpill"><b>{_pnom_pill}</b><span>P. nominal</span></div>
                    <div class="f1-hpill"><b>{_cpmax_pill}</b><span>Cp máx</span></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if st.session_state["f1_mensaje"]:
    st.success(st.session_state["f1_mensaje"])
    st.session_state["f1_mensaje"] = ""

diametro_default = float(config.get("diametro", 100.0))
densidad_default = float(config.get("densidad", 1.22))
df_resultados = pd.DataFrame()
metric_summary = None

with _phase_card("f1_card_b"):
    st.markdown(_section_title_html("🛠️", "Parámetros del aerogenerador", "Condiciones base del rotor y del aire"), unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        diametro = st.number_input(
            "Diámetro del rotor (m)",
            min_value=0.10,
            value=diametro_default,
            step=0.01,
            format="%.2f",
        )
    with c2:
        densidad = st.number_input(
            "Densidad del aire (kg/m³)",
            min_value=0.10,
            value=densidad_default,
            step=0.01,
            format="%.2f",
        )

    area = np.pi * (diametro / 2) ** 2
    df_resultados = calcular_cp(
        _preparar_datos_curva_fase1(st.session_state["f1_tabla_raw"]),
        densidad,
        area,
    )
    metric_summary = _build_metric_summary(df_resultados)

    m1, m2, m3 = st.columns([1, 1, 1], gap="medium")
    with m1:
        _render_metric_card("⭕", "Área del rotor", f"{area:,.2f} m²", "#2563eb", "πD²/4")
    with m2:
        if metric_summary is not None:
            _render_metric_card("⚡", "Potencia nominal", _format_power_nominal(metric_summary["potencia_nominal_w"]), "#d97706", "desde la curva")
        else:
            _render_metric_card("⚡", "Potencia nominal", "Sin datos", "#d97706", "desde la curva")
    with m3:
        if metric_summary is not None:
            _render_metric_card("🌬️", "Velocidad nominal", f"{metric_summary['velocidad_nominal_ms']:.2f} m/s", "#16a34a", "aprox. de la curva")
        else:
            _render_metric_card("🌬️", "Velocidad nominal", "Sin datos", "#16a34a", "aprox. de la curva")

with _phase_card("f1_card_c"):
    st.markdown(_section_title_html("🎛️", "Esquema interactivo del aerogenerador", "El viento disponible se transforma en potencia eléctrica"), unsafe_allow_html=True)
    st.markdown(
        '<div class="muted-text" style="display:none">Este esquema muestra cómo el viento disponible se transforma en potencia eléctrica según los datos ingresados.</div>',
        unsafe_allow_html=True,
    )

    if len(df_resultados) > 0:
        velocidades_disponibles = df_resultados["Velocidad_num"].astype(float).tolist()
        esquema_col, plot_col = st.columns([0.34, 0.66], gap="medium")
        with esquema_col:
            velocidad_ref = st.selectbox(
                "Velocidad de referencia para visualización",
                options=velocidades_disponibles,
                format_func=lambda x: f"{x:.2f} m/s",
            )
            fila_ref = df_resultados.loc[
                (df_resultados["Velocidad_num"].astype(float) - float(velocidad_ref)).abs().idxmin()
            ]
            st.markdown(
                _build_esquema_resumen_html(fila_ref, diametro, area, densidad),
                unsafe_allow_html=True,
            )
        with plot_col:
            components.html(
                render_esquema_aerogenerador_svg(
                    diametro=diametro,
                    area=area,
                    densidad=densidad,
                    velocidad=float(fila_ref["Velocidad_num"]),
                    potencia_viento_kw=float(fila_ref["P_viento_W"]) / 1000.0,
                    potencia_generada_kw=float(fila_ref["Potencia_W"]) / 1000.0,
                    cp=float(fila_ref["Cp"]) if pd.notna(fila_ref["Cp"]) else np.nan,
                ),
                height=500,
                scrolling=False,
            )
    else:
        st.info("Ingrese la curva de potencia para activar el esquema interactivo.")

col_izq, col_der = st.columns([1, 1], gap="large")

with col_izq:
    with st.container(border=True, key="f1_card_curva_potencia"):
        st.markdown(_section_title_html("📈", "Curva de potencia", "Potencia (kW) por velocidad — editable"), unsafe_allow_html=True)
        desc_col, clear_col = st.columns([0.68, 0.32], gap="large")
        with desc_col:
            st.markdown(
                '<p class="f1-power-subtitle" style="display:none">Ingrese la potencia en kW para cada velocidad del viento.</p>',
                unsafe_allow_html=True,
            )
        with clear_col:
            if st.button("🧹 Limpiar tabla", use_container_width=True):
                st.session_state["f1_tabla_raw"] = _tabla_curva_a_kw(tabla_vacia_curva())
                # forzar_wipe=True porque el usuario lo pidió explícitamente.
                # Sin esto, el guard defensivo de db.py rechazaría el wipe.
                guardar_tabla_curva(
                    _tabla_curva_kw_a_w(st.session_state["f1_tabla_raw"]),
                    forzar_wipe=True,
                )
                st.session_state["f1_editor_version"] += 1
                st.session_state["f1_mensaje"] = "La tabla quedó limpia."
                st.rerun()

        with st.form("form_fase1_curva", clear_on_submit=False):
            tabla_editada = st.data_editor(
                st.session_state["f1_tabla_raw"],
                num_rows="dynamic",
                use_container_width=True,
                height=390,
                hide_index=True,
                key=f"f1_editor_{st.session_state['f1_editor_version']}",
                column_config={
                    "Velocidad (m/s)": st.column_config.NumberColumn(
                        "Velocidad (m/s)",
                        help="Velocidad del viento en m/s.",
                        min_value=0.0,
                        step=0.5,
                        format="%g",
                    ),
                    "Potencia (kW)": st.column_config.NumberColumn(
                        "Potencia (kW)",
                        help="Ingrese la potencia en kilowatts.",
                        min_value=0.0,
                        step=1.0,
                        format="%g",
                    ),
                },
            )
            guardar = st.form_submit_button("💾 Guardar y actualizar", type="primary")

        if guardar:
            st.session_state["f1_tabla_raw"] = tabla_editada.copy()
            guardar_tabla_curva(_tabla_curva_kw_a_w(st.session_state["f1_tabla_raw"]))
            guardar_config_values({
                "diametro": diametro,
                "densidad": densidad,
            })
            st.session_state["f1_editor_version"] += 1
            st.session_state["f1_mensaje"] = "Fase 1 guardada correctamente."
            st.rerun()

with col_der:
    with st.container(border=True, key="f1_card_resultados_graficos"):
        st.markdown(_section_title_html("📊", "Resultados gráficos", "Curva de potencia y coeficiente Cp"), unsafe_allow_html=True)

        fig = make_subplots(specs=[[{"secondary_y": True}]])
        if len(df_resultados) > 0:
            potencia_kw = df_resultados["Potencia_W"] / 1000.0
            fig.add_trace(
                go.Scatter(
                    x=df_resultados["Velocidad_num"],
                    y=potencia_kw,
                    name="Potencia (kW)",
                    mode="lines+markers",
                    line=dict(color="#1e88ff", width=3),
                    marker=dict(size=6, color="#1e88ff"),
                    hovertemplate="Velocidad: %{x:.2f} m/s<br>Potencia: %{y:.2f} kW<extra></extra>",
                ),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(
                    x=df_resultados["Velocidad_num"],
                    y=df_resultados["Cp"],
                    name="Cp",
                    mode="lines+markers",
                    line=dict(color="#2fb344", width=2.5),
                    marker=dict(size=5, color="#2fb344"),
                    hovertemplate="Velocidad: %{x:.2f} m/s<br>Cp: %{y:.4f}<extra></extra>",
                ),
                secondary_y=True,
            )
            pmax_kw = max(float(potencia_kw.max()), 1.0)
            cp_valid = df_resultados["Cp"].replace([np.inf, -np.inf], np.nan).dropna()
            cpmax = float(cp_valid.max()) if len(cp_valid) > 0 else 0.30
            cpmax_plot = max(0.30, np.ceil(cpmax / 0.05) * 0.05 + 0.05)
            xmax = max(float(df_resultados["Velocidad_num"].max()), 1.0)
        else:
            pmax_kw = 1.0
            cpmax_plot = 0.30
            xmax = 1.0

        fig.update_layout(
            template="plotly_white",
            height=520,
            margin=dict(l=14, r=14, t=22, b=12),
            paper_bgcolor="white",
            plot_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        )
        fig.update_xaxes(
            title_text="Velocidad del viento (m/s)",
            showgrid=True,
            gridcolor="#e8eef7",
            zeroline=False,
            range=[0, xmax + 1],
        )
        fig.update_yaxes(
            title_text="Potencia (kW)",
            secondary_y=False,
            showgrid=True,
            gridcolor="#e8eef7",
            range=[0, pmax_kw * 1.10],
            tickfont=dict(color="#1e88ff"),
            title_font=dict(color="#1e88ff"),
        )
        fig.update_yaxes(
            title_text="Cp",
            secondary_y=True,
            showgrid=False,
            range=[0, cpmax_plot],
            tickfont=dict(color="#2fb344"),
            title_font=dict(color="#2fb344"),
        )
        st.markdown('<div class="chart-surface">', unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_PERF_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)

with _phase_card("f1_card_f"):
    st.markdown(_section_title_html("📝", "Notas técnicas", "Recordatorios sobre el límite de Betz"), unsafe_allow_html=True)
    st.markdown(
        """
        <div class="f1-banner warn">
            <span class="f1-bx">⚠️</span>
            <span>Cp &gt; 0,59 es físicamente sospechoso (límite de Betz). Si Cp supera 1, revise unidades, diámetro, densidad o potencia.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="f1-notes-bottom-spacer"></div>', unsafe_allow_html=True)

with _phase_card("f1_card_g"):
    st.markdown('<div class="final-expanders">', unsafe_allow_html=True)
    with st.expander("Ver tabla con Cp calculado", expanded=False):
        if len(df_resultados) > 0:
            tabla_resultados = df_resultados[
                ["Velocidad_num", "Potencia_W", "P_viento_W", "Cp"]
            ].copy()
            tabla_resultados.columns = [
                "Velocidad (m/s)",
                "Potencia (kW)",
                "P viento (W)",
                "Cp",
            ]

            st.dataframe(
                pd.DataFrame({
                    "Velocidad (m/s)": tabla_resultados["Velocidad (m/s)"].map(lambda x: f"{x:.2f}"),
                    "Potencia (kW)": (tabla_resultados["Potencia (kW)"] / 1000.0).map(lambda x: f"{x:.2f}"),
                    "P viento (W)": tabla_resultados["P viento (W)"].map(lambda x: f"{x:.2f}"),
                    "Cp": tabla_resultados["Cp"].map(lambda x: f"{x:.4f}"),
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Todavía no hay filas válidas para calcular Cp.")
    st.markdown("</div>", unsafe_allow_html=True)


# B6 - Catálogo multi-curva potencia (MVP gestor)
with st.container(border=True, key="f1_card_multi_curvas"):
    st.markdown(_section_title_html("📚", "Catálogo de curvas de potencia (B6)", "Guarde múltiples modelos; la curva activa alimenta el cálculo AEP/wake"), unsafe_allow_html=True)
    from db import cargar_power_curves as _cpc
    from db import eliminar_power_curve as _epc
    from db import guardar_power_curve as _gpc

    curves_dict = _cpc()
    if curves_dict:
        st.markdown(f"**Curvas guardadas:** {len(curves_dict)}")
        rows_curves = []
        for cid, info in curves_dict.items():
            df_c = info.get("df_curva", pd.DataFrame())
            p_nom = float(info.get("potencia_nominal_W") or 0.0)
            rows_curves.append({
                "ID": cid,
                "Nombre": info.get("nombre", ""),
                "Diámetro (m)": info.get("diametro"),
                "Potencia nominal (kW)": p_nom / 1000.0 if p_nom else None,
                "Ct": info.get("ct"),
                "N puntos": len(df_c),
                "Creada": (info.get("created_at") or "")[:19],
            })
        st.dataframe(pd.DataFrame(rows_curves), use_container_width=True, hide_index=True)
    else:
        st.markdown(
            '<div class="f1-banner info"><span class="f1-bx">💡</span>'
            '<span>Aún sin curvas en catálogo. Guarde la curva editada arriba con un nombre.</span></div>',
            unsafe_allow_html=True,
        )

    with st.expander("Guardar curva actual al catálogo", expanded=False):
        col_n1, col_n2, col_n3 = st.columns([1.2, 1, 1])
        with col_n1:
            new_curve_id = st.text_input("ID único (sin espacios)", value="", key="f1_new_curve_id", placeholder="vestas_v126_3p45mw")
            new_curve_nombre = st.text_input("Nombre / modelo", value="", key="f1_new_curve_nombre", placeholder="Vestas V126 3.45 MW")
        with col_n2:
            new_curve_diametro = st.number_input("Diámetro (m)", min_value=0.0, value=float(config.get("diametro", 100.0)), step=1.0, key="f1_new_curve_diametro")
            new_curve_ct = st.number_input("Ct", min_value=0.0, max_value=1.0, value=0.80, step=0.01, format="%.2f", key="f1_new_curve_ct")
        with col_n3:
            current_df = _tabla_curva_kw_a_w(st.session_state.get("f1_tabla_raw", tabla_vacia_curva()))
            current_pnom = 0.0
            try:
                vals_w = pd.to_numeric(current_df["Potencia (W)"], errors="coerce")
                current_pnom = float(vals_w.max()) if len(vals_w) > 0 else 0.0
            except Exception:
                current_pnom = 0.0
            st.metric("Potencia nominal detectada (kW)", f"{current_pnom / 1000.0:,.1f}")
            if st.button("Guardar al catálogo", key="f1_btn_save_curve", use_container_width=True):
                if not new_curve_id.strip() or not new_curve_nombre.strip():
                    st.warning("ID y nombre son obligatorios.")
                else:
                    try:
                        _gpc(
                            curve_id=new_curve_id.strip(),
                            nombre=new_curve_nombre.strip(),
                            diametro=new_curve_diametro,
                            potencia_nominal_W=current_pnom,
                            ct=new_curve_ct,
                            df_curva=current_df,
                        )
                        st.success(f"Curva '{new_curve_id}' guardada.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error guardando: {exc}")

    if curves_dict:
        with st.expander("Eliminar / cargar curva del catálogo", expanded=False):
            curve_ids = list(curves_dict.keys())
            target_id = st.selectbox("Seleccionar curva", curve_ids, key="f1_target_curve_id")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Cargar como curva activa", key="f1_btn_load_curve", use_container_width=True):
                    info = curves_dict[target_id]
                    df_load = info.get("df_curva", pd.DataFrame())
                    if len(df_load) > 0:
                        st.session_state["f1_tabla_raw"] = _tabla_curva_a_kw(df_load)
                        guardar_tabla_curva(_tabla_curva_kw_a_w(st.session_state["f1_tabla_raw"]))
                        st.success(f"Curva '{target_id}' cargada como activa.")
                        st.rerun()
                    else:
                        st.warning("Curva sin datos.")
            with col_b:
                if st.button("Eliminar del catálogo", key="f1_btn_del_curve", use_container_width=True):
                    _epc(target_id)
                    st.success(f"Curva '{target_id}' eliminada.")
                    st.rerun()


render_dropdown_visibility_fix()




