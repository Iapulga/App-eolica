import textwrap
from urllib.parse import quote

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from pandas.util import hash_pandas_object
from plotly.subplots import make_subplots

from calculos import (
    PROMEDIO_LOG_EXP_LABEL,
    SECTOR_LABELS_16,
    calidad_weibull,
    construir_serie_viento_analisis,
    crear_histograma_sector_con_ajustes,
    crear_rosa_vientos_16,
    inferir_puntos_operacion_curva,
    normalizar_modelo_altura,
    preparar_datos_curva,
    preparar_datos_rosa,
    rayleigh_cdf,
    rayleigh_interval_prob,
    resumir_sectores_rosa,
    weibull_cdf,
    weibull_interval_prob,
)
from db import (
    cargar_config,
    cargar_nasa_hourly,
    cargar_tabla_curva,
    guardar_config_values,
    init_db,
)
from navigation import _icon_svg, render_dropdown_visibility_fix, render_sidebar_navigation
from widget_helpers import _init_widget_state, _safe_index

st.set_page_config(page_title="Fase 3 · Velocidad promedio", layout="wide")

# Cargar CSS global e inyectar sidebar lo ANTES posible para evitar FOUC.
render_sidebar_navigation("pages/3_Fase_3_Velocidad_promedio.py")

init_db()

ROUGHNESS_OPTIONS = {
    "Water / Mar": 2e-4,
    "Snow / Nieve": 1e-3,
    "Grass / Césped": 0.03,
    "Farmland / Cultivo": 0.10,
    "Forest / Bosque": 0.80,
    "City / Ciudad": 1.00,
}

MODEL_OPTIONS = ["50 m", "10 m", "Exponencial", "Log A (2 puntos)", "Promedio Log-Exp"]
DIRECTION_OPTIONS = ["WD50M", "WD10M"]
MOSTRAR_HISTOGRAMA_SUPERIOR = False  # Control visual para mostrar/ocultar el histograma superior en Fase 3
PLOTLY_PERF_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}


def _df_signature(df: pd.DataFrame, cols: list[str] | None = None) -> tuple:
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


def _render_dataframe_safe(df, numeric_formats=None, **kwargs):
    column_config = {}
    for col, fmt in (numeric_formats or {}).items():
        if col in df.columns:
            column_config[col] = st.column_config.NumberColumn(format=fmt)
    st.dataframe(df, column_config=column_config, **kwargs)


def _expander_icon_label(icon_name: str, label: str) -> str:
    icon_svg = _icon_svg(icon_name, 22, "#2563eb")
    icon_uri = "data:image/svg+xml;utf8," + quote(icon_svg)
    return f"![{label}]({icon_uri}) {label}"


def _config_value(config, primary_key, fallback_keys, default, caster=None):
    keys = [primary_key] + list(fallback_keys)
    for key in keys:
        value = config.get(key)
        if value not in [None, ""]:
            if caster is None:
                return value
            try:
                return caster(value)
            except Exception:
                continue
    return default


def _bool_config_value(config, primary_key, fallback_keys, default=False):
    value = _config_value(config, primary_key, fallback_keys, default, caster=None)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _render_plotly_iframe(fig: go.Figure, height: int, key_suffix: str) -> None:
    # Copia defensiva: no mutar la figura cacheada (@st.cache_data) que también
    # usan las exportaciones. Sobre la copia quitamos width/height fijos y
    # activamos autosize, para que con responsive=True plotly SIEMPRE se ajuste
    # al tamaño real del contenedor — incluido al hacer zoom de página a 150% en
    # pantallas grandes. Sin esto, la figura conserva su ancho original y queda
    # recortada por el overflow:hidden del marco.
    fig = go.Figure(fig)
    fig.update_layout(width=None, height=None, autosize=True)
    html = fig.to_html(
        full_html=False,
        include_plotlyjs="inline",
        config={
            "displayModeBar": False,
            "responsive": True,
        },
        default_width="100%",
        default_height=f"{height}px",
    )
    iframe_html = f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <style>
          html, body {{
            margin: 0;
            padding: 0;
            background: #ffffff;
            overflow: hidden;
          }}
          .f3-plot-frame {{
            width: 100%;
            height: {height}px;
            background: #ffffff;
            overflow: hidden;
          }}
          .f3-plot-frame .plotly-graph-div {{
            width: 100% !important;
            height: 100% !important;
            margin: 0 !important;
          }}
        </style>
      </head>
      <body>
        <div class="f3-plot-frame">{html}</div>
        <script>
          (function(){{
            function fit(){{
              try{{
                var gd = document.querySelector('.plotly-graph-div');
                if (gd && window.Plotly) {{ window.Plotly.Plots.resize(gd); }}
              }} catch (e) {{}}
            }}
            window.addEventListener('resize', fit);
            if (window.ResizeObserver) {{
              try {{ new ResizeObserver(fit).observe(document.documentElement); }} catch (e) {{}}
            }}
            // Re-ajustes diferidos: cubren el momento en que Streamlit fija el
            // ancho real del iframe (tras el render) y cualquier cambio de zoom.
            setTimeout(fit, 50); setTimeout(fit, 250); setTimeout(fit, 600);
          }})();
        </script>
      </body>
    </html>
    """
    components.html(iframe_html, height=height, scrolling=False)


def construir_viento_analisis(df_nasa, modelo, altura_deseada, roughness_label, direccion_fuente):
    modelo = normalizar_modelo_altura(modelo)
    df, meta = construir_serie_viento_analisis(
        df_nasa=df_nasa,
        modelo=modelo,
        altura_deseada=altura_deseada,
        roughness_label=roughness_label,
        direccion_fuente=direccion_fuente,
        roughness_options=ROUGHNESS_OPTIONS,
        output_speed_col="WS_ANALISIS",
        output_direction_col="WD_USADA",
    )

    if modelo == "50 m":
        meta["descripcion"] = "Análisis construido con WS50M y WD50M."
    elif modelo == "10 m":
        meta["descripcion"] = "Análisis construido con WS10M y WD10M."
    elif modelo == "Exponencial":
        meta["descripcion"] = "Análisis con velocidad extrapolada por perfil exponencial."
    elif modelo == "Log A (2 puntos)":
        meta["descripcion"] = "Análisis con velocidad extrapolada por perfil logarítmico ajustado a 2 puntos."
    elif modelo == PROMEDIO_LOG_EXP_LABEL:
        meta["descripcion"] = "Análisis con velocidad extrapolada como promedio entre el perfil exponencial y el perfil logarítmico A."

    return df, meta


@st.cache_data(show_spinner=False)
def construir_heatmap_probabilidad(df_rosa, vmax, bin_width):
    bins = np.arange(0.0, vmax + bin_width, bin_width)
    if bins[-1] < vmax:
        bins = np.append(bins, vmax)

    labels = [f"{bins[i]:.1f}-{bins[i + 1]:.1f}" for i in range(len(bins) - 1)]
    matrix = []

    for sector in SECTOR_LABELS_16:
        sub = df_rosa.loc[df_rosa["Sector"] == sector, "WS_ANALISIS"].dropna().to_numpy(dtype=float)
        if len(sub) == 0:
            probs = np.zeros(len(bins) - 1)
        else:
            counts, _ = np.histogram(sub, bins=bins)
            probs = counts / counts.sum() * 100.0
        matrix.append(probs)

    fig = go.Figure(
        data=go.Heatmap(
            z=np.array(matrix),
            x=labels,
            y=SECTOR_LABELS_16,
            colorscale="YlOrRd",
            colorbar=dict(title="Probabilidad (%)"),
            hovertemplate=(
                "Sector: %{y}<br>"
                "Intervalo: %{x} m/s<br>"
                "Probabilidad: %{z:.2f}%"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=None,
        template="plotly_white",
        height=700,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis_title=None,
        yaxis_title=None,
    )
    return fig, bins


@st.cache_data(show_spinner=False)
def crear_figura_sector(df_sector, fila_sector, bins, mostrar_cdf, cut_in, nominal, cut_out):
    v = df_sector["WS_ANALISIS"].dropna().to_numpy(dtype=float)
    counts, edges = np.histogram(v, bins=bins)
    probs_real = counts / counts.sum() * 100.0 if counts.sum() > 0 else np.zeros_like(counts, dtype=float)
    centers = 0.5 * (edges[:-1] + edges[1:])

    k = float(fila_sector["k Weibull"])
    c_weib = float(fila_sector["c Weibull (m/s)"])
    c_ray = float(fila_sector["c Rayleigh (m/s)"])

    probs_weib = []
    probs_ray = []
    for i in range(len(edges) - 1):
        a = edges[i]
        b = edges[i + 1]
        probs_weib.append(weibull_interval_prob(a, b, k, c_weib) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan)
        probs_ray.append(rayleigh_interval_prob(a, b, c_ray) * 100.0 if np.isfinite(c_ray) else np.nan)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=centers,
            y=probs_real,
            name="Histograma real (%)",
            marker_color="#7fb3c4",
            hovertemplate="Velocidad: %{x:.2f} m/s<br>Probabilidad real: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=centers,
            y=probs_weib,
            mode="lines+markers",
            name="Weibull (%)",
            line=dict(width=3, color="#1f77b4"),
            hovertemplate="Velocidad: %{x:.2f} m/s<br>Probabilidad Weibull: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=centers,
            y=probs_ray,
            mode="lines+markers",
            name="Rayleigh (%)",
            line=dict(width=3, color="#ff7f0e", dash="dash"),
            hovertemplate="Velocidad: %{x:.2f} m/s<br>Probabilidad Rayleigh: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=False,
    )

    if mostrar_cdf:
        xcdf = np.linspace(0.0, edges[-1], 400)
        fig.add_trace(
            go.Scatter(
                x=xcdf,
                y=weibull_cdf(xcdf, k, c_weib) * 100.0,
                mode="lines",
                name="CDF Weibull (%)",
                line=dict(width=2, color="#2ca02c"),
            ),
            secondary_y=True,
        )
        fig.add_trace(
            go.Scatter(
                x=xcdf,
                y=rayleigh_cdf(xcdf, c_ray) * 100.0,
                mode="lines",
                name="CDF Rayleigh (%)",
                line=dict(width=2, color="#d62728", dash="dot"),
            ),
            secondary_y=True,
        )

    for xline, name, color in [
        (cut_in, "Cut-in", "#2ca02c"),
        (nominal, "Nominal", "#9467bd"),
        (cut_out, "Cut-out", "#d62728"),
    ]:
        fig.add_vline(x=float(xline), line_width=2, line_dash="dot", line_color=color)
        fig.add_annotation(x=float(xline), y=1.02, yref="paper", text=name, showarrow=False, font=dict(color=color))

    fig.update_layout(
        title=f"Curva de probabilidad de ocurrencia - Sector {fila_sector['Sector']}",
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        bargap=0.05,
    )
    fig.update_xaxes(title_text="Velocidad del viento (m/s)")
    fig.update_yaxes(title_text="Probabilidad por intervalo (%)", secondary_y=False)
    if mostrar_cdf:
        fig.update_yaxes(title_text="Probabilidad acumulada (%)", secondary_y=True, range=[0, 100])
    return fig


def crear_tabla_probabilidades_intervalos(df_sector, fila_sector, vmax, bin_width):
    v = df_sector["WS_ANALISIS"].dropna().to_numpy(dtype=float)
    bins = np.arange(0.0, vmax + bin_width, bin_width)
    if bins[-1] < vmax:
        bins = np.append(bins, vmax)

    k = float(fila_sector["k Weibull"])
    c_weib = float(fila_sector["c Weibull (m/s)"])
    c_ray = float(fila_sector["c Rayleigh (m/s)"])

    filas = []
    total = len(v)
    for i in range(len(bins) - 1):
        a = bins[i]
        b = bins[i + 1]
        if total > 0:
            if i < len(bins) - 2:
                prob_real = 100.0 * np.sum((v >= a) & (v < b)) / total
            else:
                prob_real = 100.0 * np.sum((v >= a) & (v <= b)) / total
        else:
            prob_real = np.nan

        filas.append({
            "Rango": f"{a:.1f} - {b:.1f} m/s",
            "Probabilidad real (%)": prob_real,
            "Probabilidad Weibull (%)": weibull_interval_prob(a, b, k, c_weib) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan,
            "Probabilidad Rayleigh (%)": rayleigh_interval_prob(a, b, c_ray) * 100.0 if np.isfinite(c_ray) else np.nan,
        })

    return pd.DataFrame(filas)


def crear_tabla_operacion(df_sector, fila_sector, cut_in, nominal, cut_out):
    v = df_sector["WS_ANALISIS"].dropna().to_numpy(dtype=float)
    k = float(fila_sector["k Weibull"])
    c_weib = float(fila_sector["c Weibull (m/s)"])
    c_ray = float(fila_sector["c Rayleigh (m/s)"])

    rangos = [
        (0.0, cut_in, "Menor que cut-in"),
        (cut_in, nominal, "Entre cut-in y nominal"),
        (nominal, cut_out, "Entre nominal y cut-out"),
        (cut_out, max(cut_out + 20.0, cut_out * 1.5), "Mayor que cut-out"),
    ]

    total = len(v)
    filas = []
    for a, b, nombre in rangos:
        if total > 0:
            if nombre == "Mayor que cut-out":
                prob_real = 100.0 * np.sum(v >= a) / total
            else:
                prob_real = 100.0 * np.sum((v >= a) & (v < b)) / total
        else:
            prob_real = np.nan

        if nombre == "Mayor que cut-out":
            prob_weib = (1.0 - weibull_cdf(a, k, c_weib)) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan
            prob_ray = (1.0 - rayleigh_cdf(a, c_ray)) * 100.0 if np.isfinite(c_ray) else np.nan
        else:
            prob_weib = weibull_interval_prob(a, b, k, c_weib) * 100.0 if np.isfinite(k) and np.isfinite(c_weib) else np.nan
            prob_ray = rayleigh_interval_prob(a, b, c_ray) * 100.0 if np.isfinite(c_ray) else np.nan

        filas.append({
            "Zona de operación": nombre,
            "Probabilidad real (%)": prob_real,
            "Probabilidad Weibull (%)": prob_weib,
            "Probabilidad Rayleigh (%)": prob_ray,
        })

    return pd.DataFrame(filas)

def _f3_fmt_num(x):
    try:
        s = f"{float(x):.1f}".rstrip("0").rstrip(".")
    except Exception:
        return "—"
    if s in ("", "-0"):
        s = "0"
    return s.replace(".", ",")


def _f3_nice_ticks(lo, hi, n=5):
    import math
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / max(1, n - 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        if (hi - lo) / (m * mag) <= n + 0.5:
            step = m * mag
            break
    start = math.ceil(lo / step) * step
    ticks, t = [], start
    while t <= hi + step * 0.001:
        ticks.append(round(t, 6))
        t += step
    return ticks


def _f3_svg_html(viewbox, inner):
    """Envuelve el SVG en un iframe con tooltip al pasar el cursor: cualquier
    elemento con atributo data-tip muestra su texto (conserva la interactividad)."""
    tip = (
        '<div id="f3tip" style="position:fixed;display:none;z-index:99;background:#1e293b;color:#fff;'
        'padding:6px 9px;border-radius:8px;font:600 11px \'Segoe UI\',Arial,sans-serif;white-space:pre;'
        'pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.28);line-height:1.45"></div>'
    )
    script = (
        "<script>(function(){var t=document.getElementById('f3tip');"
        "document.addEventListener('mousemove',function(e){"
        "var el=e.target.closest?e.target.closest('[data-tip]'):null;"
        "if(el){t.textContent=el.getAttribute('data-tip');t.style.display='block';"
        "var x=e.clientX+14,y=e.clientY+14;"
        "if(x+t.offsetWidth>window.innerWidth)x=e.clientX-t.offsetWidth-14;"
        "if(y+t.offsetHeight>window.innerHeight)y=e.clientY-t.offsetHeight-14;"
        "t.style.left=x+'px';t.style.top=y+'px';}else{t.style.display='none';}});"
        "document.addEventListener('mouseleave',function(){t.style.display='none';});})();</script>"
    )
    return (
        '<html style="margin:0;padding:0;width:100%;height:100%;">'
        '<body style="margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#fff;">'
        + tip +
        '<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;overflow:hidden;">'
        f'<svg viewBox="{viewbox}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;display:block;'
        "font-family:'Segoe UI Variable Display','Segoe UI',Arial,sans-serif;\">"
        f"{inner}</svg></div>"
        + script +
        "</body></html>"
    )


def render_rosa_svg(resumen):
    """Rosa de vientos polar (mockup): 16 cuñas (radio=Frecuencia %), anillos,
    rótulos N/NE/E/SE/S/SW/W/NW, degradado índigo. Datos reales de `resumen`."""
    import math
    freqs = pd.to_numeric(resumen["Frecuencia (%)"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    bearings = pd.to_numeric(resumen["Centro (°)"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    sectors = resumen["Sector"].astype(str).tolist()
    _vm_col = resumen["Velocidad media (m/s)"] if "Velocidad media (m/s)" in resumen else pd.Series([np.nan] * len(resumen))
    _dt_col = resumen["Datos"] if "Datos" in resumen else pd.Series([0] * len(resumen))
    vmeds = pd.to_numeric(_vm_col, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    datos = pd.to_numeric(_dt_col, errors="coerce").fillna(0).to_numpy(dtype=float)
    fmax = float(np.nanmax(freqs)) if len(freqs) else 1.0
    if fmax <= 0:
        fmax = 1.0
    rings = [r for r in _f3_nice_ticks(0, fmax, 4) if r > 0]
    if rings and rings[-1] < fmax:
        step = rings[1] - rings[0] if len(rings) > 1 else rings[0]
        while rings[-1] < fmax:
            rings.append(rings[-1] + step)
    ring_max = rings[-1] if rings else fmax
    CX, CY, RMAX = 260.0, 270.0, 198.0

    def xy(r, b):
        a = math.radians(b - 90.0)
        return CX + r * math.cos(a), CY + r * math.sin(a)

    grid = ""
    for rv in rings:
        rr = rv / ring_max * RMAX
        grid += f'<circle cx="{CX}" cy="{CY}" r="{rr:.1f}" fill="none" stroke="#e6e9f5" stroke-width="1.2"/>'
        grid += f'<text x="{CX + 4}" y="{CY - rr + 3:.1f}" font-size="12.5" fill="#94a3b8" font-weight="800">{_f3_fmt_num(rv)}%</text>'
    spokes = ""
    for lbl, b in [("N", 0), ("NE", 45), ("E", 90), ("SE", 135), ("S", 180), ("SW", 225), ("W", 270), ("NW", 315)]:
        x2, y2 = xy(RMAX, b)
        spokes += f'<line x1="{CX}" y1="{CY}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#eef1fa" stroke-width="1"/>'
        lx, ly = xy(RMAX + 24, b)
        spokes += f'<text x="{lx:.1f}" y="{ly + 5.5:.1f}" text-anchor="middle" font-size="16" fill="#5a6b85" font-weight="900">{lbl}</text>'
    wedges = ""
    half = (360.0 / 16.0) / 2.0 * 0.84
    for i in range(len(freqs)):
        freq, bearing = freqs[i], bearings[i]
        if freq <= 0:
            continue
        r = freq / ring_max * RMAX
        x0, y0 = xy(r, bearing - half)
        x1, y1 = xy(r, bearing + half)
        _fr = f"{freq:.2f}".replace(".", ",")
        _vm = f"{vmeds[i]:.2f}".replace(".", ",")
        _dt = f"{int(datos[i]):,}".replace(",", ".")
        tip = f"Sector: {sectors[i]}&#10;Frecuencia: {_fr} %&#10;Velocidad media: {_vm} m/s&#10;Datos: {_dt}"
        wedges += (
            f'<path d="M{CX},{CY} L{x0:.1f},{y0:.1f} A{r:.1f},{r:.1f} 0 0 1 {x1:.1f},{y1:.1f} Z" '
            f'fill="url(#f3rosegrad)" stroke="#4338ca" stroke-width="0.6" opacity="0.94" '
            f'data-tip="{tip}" style="cursor:pointer"/>'
        )
    defs = (
        '<defs><radialGradient id="f3rosegrad" gradientUnits="userSpaceOnUse" cx="260" cy="270" r="198">'
        '<stop offset="0" stop-color="#c7d2fe"/><stop offset="1" stop-color="#4f46e5"/>'
        "</radialGradient></defs>"
    )
    return _f3_svg_html("22 32 476 476", defs + grid + spokes + wedges)


def _sector_curve_arrays(df_sector, fila_sector, bins):
    v = df_sector["WS_ANALISIS"].dropna().to_numpy(dtype=float)
    counts, edges = np.histogram(v, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    k = float(fila_sector["k Weibull"])
    cw = float(fila_sector["c Weibull (m/s)"])
    cr = float(fila_sector["c Rayleigh (m/s)"])
    pw, pr = [], []
    for i in range(len(edges) - 1):
        a, b = edges[i], edges[i + 1]
        pw.append(weibull_interval_prob(a, b, k, cw) * 100.0 if np.isfinite(k) and np.isfinite(cw) else np.nan)
        pr.append(rayleigh_interval_prob(a, b, cr) * 100.0 if np.isfinite(cr) else np.nan)
    return centers, np.asarray(pw, dtype=float), np.asarray(pr, dtype=float)


def render_sector_curve_svg(centers, probs_weib, probs_ray, cut_in, nominal, cut_out, vmax, H=440):
    """Curva de probabilidad por sector (mockup): Weibull (índigo) + Rayleigh
    (naranja) + verticales cut-in/nominal/cut-out + ejes con números."""
    cxs = np.asarray(centers, dtype=float)
    pw = np.asarray(probs_weib, dtype=float)
    pr = np.asarray(probs_ray, dtype=float)
    if len(cxs) < 2:
        return ""
    x_lo = 0.0
    x_hi = float(max(vmax, cut_out or 0, cxs.max()))
    allp = np.concatenate([pw[np.isfinite(pw)], pr[np.isfinite(pr)]])
    y_hi = float(np.nanmax(allp)) * 1.14 if len(allp) else 1.0
    if y_hi <= 0:
        y_hi = 1.0
    # H = alto del viewBox (ancho fijo 700); ajustarlo al aspecto del iframe evita letterbox
    X0, X1, YB, YT = 52.0, 686.0, float(H) - 50.0, 26.0

    def px(v):
        return X0 + (float(v) - x_lo) / (x_hi - x_lo) * (X1 - X0)

    def py(p):
        return YB - (float(p) / y_hi) * (YB - YT)

    y_ticks = _f3_nice_ticks(0, y_hi, 5)
    x_ticks = _f3_nice_ticks(x_lo, x_hi, 6)
    grid = "".join(f'<line x1="52" y1="{py(t):.1f}" x2="686" y2="{py(t):.1f}" stroke="#eef1fa" stroke-width="1"/>' for t in y_ticks)
    axes = (
        f'<line x1="52" y1="{YB:.0f}" x2="686" y2="{YB:.0f}" stroke="#c4d4e8" stroke-width="1.4"/>'
        f'<line x1="52" y1="20" x2="52" y2="{YB:.0f}" stroke="#c4d4e8" stroke-width="1.4"/>'
    )
    ylab = "".join(f'<text x="48" y="{py(t) + 3:.1f}" text-anchor="end" font-size="10.5" fill="#94a3b8" font-weight="700">{_f3_fmt_num(t)}</text>' for t in y_ticks)
    xlab = "".join(f'<text x="{px(t):.1f}" y="{YB + 17:.0f}" text-anchor="middle" font-size="10.5" fill="#94a3b8" font-weight="700">{_f3_fmt_num(t)}</text>' for t in x_ticks)

    def line(arr, color):
        pts = [(px(cxs[i]), py(arr[i])) for i in range(len(arr)) if np.isfinite(arr[i])]
        if len(pts) < 2:
            return ""
        d = "M" + f"{pts[0][0]:.1f},{pts[0][1]:.1f}" + "".join(f" L{x:.1f},{y:.1f}" for x, y in pts[1:])
        marks = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="#fff" stroke="{color}" stroke-width="1.8"/>' for x, y in pts)
        return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>' + marks

    body = line(pw, "#4f46e5") + line(pr, "#f97316")
    cuts = ""
    for xv, nm in [(cut_in, "Cut-in"), (nominal, "Nominal"), (cut_out, "Cut-out")]:
        if xv is None:
            continue
        xx = px(xv)
        cuts += f'<line x1="{xx:.1f}" y1="26" x2="{xx:.1f}" y2="{YB:.0f}" stroke="#94a3b8" stroke-width="1.3" stroke-dasharray="4 4"/>'
        cuts += f'<text x="{xx:.1f}" y="20" text-anchor="middle" font-size="9.5" fill="#64748b" font-weight="800">{nm}</text>'
    _ymid = (YT + YB) / 2.0
    labels = (
        f'<text x="369" y="{YB + 38:.0f}" text-anchor="middle" font-size="11.5" fill="#64748b" font-weight="800">Velocidad (m/s)</text>'
        f'<text x="13" y="{_ymid:.0f}" font-size="11.5" fill="#64748b" font-weight="800" transform="rotate(-90 13 {_ymid:.0f})" text-anchor="middle">Probabilidad (%)</text>'
    )
    return _f3_svg_html(f"0 0 700 {int(H)}", grid + axes + cuts + body + ylab + xlab + labels)


def _heatmap_matrix(df_rosa, bins):
    mat = []
    for sector in SECTOR_LABELS_16:
        sub = df_rosa.loc[df_rosa["Sector"] == sector, "WS_ANALISIS"].dropna().to_numpy(dtype=float)
        if len(sub) == 0:
            probs = np.zeros(len(bins) - 1)
        else:
            counts, _ = np.histogram(sub, bins=bins)
            s = counts.sum()
            probs = counts / s * 100.0 if s > 0 else np.zeros(len(bins) - 1)
        mat.append(probs)
    return np.array(mat)


def render_heatmap_svg(matrix, sector_labels, bins):
    """Heatmap 16 sectores × intervalos (mockup): celdas redondeadas color
    crema→naranja→rojo, rótulos de sector y eje de velocidad."""
    M = np.asarray(matrix, dtype=float)
    if M.size == 0:
        return ""
    nrow, ncol = M.shape
    vmax = float(np.nanmax(M)) if np.isfinite(M).any() else 1.0
    if vmax <= 0:
        vmax = 1.0
    LEFT, TOP = 56.0, 12.0
    cw, ch, gap = 26.0, 23.0, 3.0
    W = LEFT + ncol * cw + 24
    H = TOP + nrow * ch + 46

    def color(p):
        t = max(0.0, min(1.0, p / vmax))
        stops = [(1.0, 0.97, 0.92), (0.99, 0.68, 0.42), (0.84, 0.19, 0.12)]
        if t <= 0.5:
            f = t / 0.5
            a, b = stops[0], stops[1]
        else:
            f = (t - 0.5) / 0.5
            a, b = stops[1], stops[2]
        rr = int((a[0] + (b[0] - a[0]) * f) * 255)
        gg = int((a[1] + (b[1] - a[1]) * f) * 255)
        bb = int((a[2] + (b[2] - a[2]) * f) * 255)
        return f"rgb({rr},{gg},{bb})"

    cells = ""
    for i in range(nrow):
        y = TOP + i * ch
        cells += f'<text x="{LEFT - 8}" y="{y + ch / 2 + 3:.1f}" text-anchor="end" font-size="9.5" fill="#5a6b85" font-weight="800">{sector_labels[i]}</text>'
        for j in range(ncol):
            x = LEFT + j * cw
            _b0 = f"{float(bins[j]):.1f}".replace(".", ",")
            _b1 = f"{float(bins[j + 1]):.1f}".replace(".", ",")
            _pb = f"{M[i, j]:.2f}".replace(".", ",")
            ctip = f"Sector: {sector_labels[i]}&#10;Intervalo: {_b0}-{_b1} m/s&#10;Probabilidad: {_pb} %"
            cells += f'<rect x="{x:.1f}" y="{y:.1f}" width="{cw - gap:.1f}" height="{ch - gap:.1f}" rx="3" fill="{color(M[i, j])}" data-tip="{ctip}" style="cursor:pointer"/>'
    # ticks de velocidad (cada ~5 m/s) bajo el eje
    xticks = ""
    bn = np.asarray(bins, dtype=float)
    for j in range(ncol + 1):
        vstart = bn[j] if j < len(bn) else bn[-1]
        if abs(vstart - round(vstart)) < 1e-6 and int(round(vstart)) % 5 == 0:
            xx = LEFT + j * cw
            xticks += f'<text x="{xx:.1f}" y="{TOP + nrow * ch + 16:.1f}" text-anchor="middle" font-size="9" fill="#94a3b8" font-weight="700">{int(round(vstart))}</text>'
    xlabel = f'<text x="{LEFT + ncol * cw / 2:.1f}" y="{H - 8:.1f}" text-anchor="middle" font-size="11" fill="#64748b" font-weight="800">Intervalo de velocidad (m/s) →</text>'
    return _f3_svg_html(f"0 0 {W:.0f} {H:.0f}", cells + xticks + xlabel)


def _phase_card(key: str | None = None):
    return st.container(border=True, key=key)


def _render_phase3_css():
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(180deg, #f5f9ff 0%, #eef5ff 100%) !important;
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
        .f3-hero__title {
            font-size: 2.1rem;
            line-height: 1.05;
            font-weight: 800;
            color: #1e3a8a;
            margin-bottom: 0.28rem;
        }
        .f3-hero__subtitle {
            color: #000000;
            font-size: 0.94rem;
            line-height: 1.42;
            font-weight: 400;
            max-width: 74rem;
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
        .f3-card-heading {
            display: flex;
            align-items: center;
            gap: 0.62rem;
            margin-bottom: 0.56rem;
        }
        .f3-card-heading__icon {
            width: 38px;
            height: 38px;
            min-width: 38px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(180deg, #f8fbff 0%, #edf4ff 100%);
            border: 1px solid #c7dbff;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.95);
        }
        .f3-card-heading__icon--note {
            width: 32px;
            height: 32px;
            min-width: 32px;
        }
        .f3-card-heading__title {
            color: #2563eb;
            font-size: 1.03rem;
            font-weight: 900;
            line-height: 1.08;
        }
        .f3-card-heading__subtitle {
            color: #000000;
            font-size: 0.84rem;
            margin-top: 0.12rem;
        }
        .f3-kpi-card {
            min-height: 92px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 0.86rem !important;
            padding: 0.94rem 0.9rem !important;
            height: 100%;
        }
        .f3-kpi-card__icon {
            width: 66px !important;
            height: 66px !important;
            min-width: 66px !important;
            border-radius: 999px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            align-self: center !important;
            background: linear-gradient(180deg, #f8fbff 0%, #edf5ff 100%) !important;
            border: 1px solid #bfdbfe !important;
            box-shadow: 0 1px 2px rgba(37, 99, 235, 0.08), inset 0 1px 0 rgba(255,255,255,0.95) !important;
            transform: translateY(-4px) !important;
        }
        .f3-kpi-card__icon svg {
            width: 34px !important;
            height: 34px !important;
            display: block !important;
        }
        .f3-kpi-card__icon svg * {
            stroke-width: 2.4 !important;
        }
        .f3-kpi-card__body {
            display: flex !important;
            flex-direction: column !important;
            justify-content: center !important;
            min-height: 66px !important;
        }
        .f3-kpi-card__label {
            font-size: 0.86rem !important;
            font-weight: 800 !important;
            color: #000000 !important;
            line-height: 1.05 !important;
            margin: 0 0 0.28rem 0 !important;
        }
        .f3-kpi-card__value {
            font-size: 1.85rem !important;
            font-weight: 900 !important;
            color: #020617 !important;
            line-height: 1.05 !important;
            margin: 0 !important;
        }
        .st-key-f3_kpi_4 .f3-kpi-card__value {
            font-size: 1.25rem !important;
            line-height: 1.05 !important;
            font-weight: 800 !important;
            white-space: normal !important;
            overflow-wrap: break-word !important;
        }
        .f3-soft-note {
            border: 1px solid #cbd5e1;
            border-radius: 18px;
            background: linear-gradient(180deg, #f8fbff 0%, #f1f7ff 100%);
            padding: 0.72rem 0.95rem;
            color: #1d4ed8;
            font-weight: 400;
            display: flex;
            align-items: center;
            gap: 0.7rem;
            line-height: 1.35;
        }
        .f3-soft-note__text {
            color: #1d4ed8;
            font-size: 0.92rem;
            font-weight: 400;
            line-height: 1.34;
        }
        .f3-summary-card {
            border: 1px solid #dbe5f1;
            border-radius: 16px;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
            padding: 0.98rem 1.02rem 0.92rem 1.02rem;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
        }
        .f3-summary-card__title {
            color: #0f172a;
            font-size: 0.98rem;
            font-weight: 900;
            margin-bottom: 0.76rem;
        }
        .f3-summary-row {
            display: flex;
            justify-content: space-between;
            gap: 0.65rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid #eef4fb;
        }
        .f3-summary-row:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }
        .f3-summary-row__label {
            color: #000000;
            font-size: 0.82rem;
            font-weight: 400;
        }
        .f3-summary-row__value {
            color: #0f172a;
            font-size: 0.86rem;
            font-weight: 800;
            text-align: right;
            line-height: 1.25;
        }
        .f3-mini-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.48rem;
            margin-bottom: 0.48rem;
        }
        .f3-mini-stat {
            border: 1px solid #cbd5e1;
            border-radius: 14px;
            background: #ffffff;
            padding: 0.68rem 0.78rem;
            min-height: 78px;
        }
        .f3-mini-stat__label {
            color: #000000;
            font-size: 0.76rem;
            font-weight: 400;
            margin-bottom: 0.12rem;
        }
        .f3-mini-stat__value {
            color: #0f172a;
            font-size: 1.14rem;
            font-weight: 900;
            line-height: 1.05;
        }
        .f3-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.5rem 0.75rem;
            border-radius: 999px;
            border: 1px solid #bfdbfe;
            background: #eff6ff;
            color: #2563eb;
            font-size: 0.86rem;
            font-weight: 800;
        }
        .st-key-f3_card_expanders [data-testid="stExpander"] {
            border: 1px solid #dbe5f1 !important;
            border-radius: 18px !important;
            background: #ffffff !important;
            box-shadow: 0 1px 4px rgba(15, 23, 42, 0.03) !important;
            margin-bottom: 0.7rem !important;
        }
        .st-key-f3_card_expanders [data-testid="stExpander"] summary {
            color: #0f2f78 !important;
            font-weight: 800 !important;
            min-height: 52px !important;
            display: flex !important;
            align-items: center !important;
        }
        .st-key-f3_card_header,
        .st-key-f3_cfg_general,
        .st-key-f3_cfg_cuts,
        .st-key-f3_cfg_sector,
        .st-key-f3_kpi_1,
        .st-key-f3_kpi_2,
        .st-key-f3_kpi_3,
        .st-key-f3_kpi_4,
        .st-key-f3_kpi_5,
        .st-key-f3_note_card,
        .st-key-f3_card_heatmap,
        .st-key-f3_card_expanders,
        .st-key-f3_sector_summary,
        .st-key-f3_sector_mini_frecuencia,
        .st-key-f3_sector_mini_horas,
        .st-key-f3_sector_mini_horas_eq,
        .st-key-f3_sector_mini_k_weibull,
        .st-key-f3_sector_mini_c_weibull,
        .st-key-f3_pg_altura,
        .st-key-f3_pg_modelo,
        .st-key-f3_pg_vmax,
        .st-key-f3_pg_binwidth {
            border: 1.35px solid #cbd5e1 !important;
            border-radius: 28px !important;
            overflow: visible !important;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        }
        .st-key-f3_card_header div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_sector div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_1 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_2 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_4 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_5 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_note_card div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_card_heatmap div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_card_expanders div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_summary div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_frecuencia div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_horas div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_horas_eq div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_k_weibull div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_c_weibull div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_pg_altura div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_pg_modelo div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_pg_vmax div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_pg_binwidth div[data-testid="stVerticalBlockBorderWrapper"] {
            border: none !important;
            border-radius: 28px !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0.86rem 0.98rem !important;
        }
        .st-key-f3_card_header div[data-testid="stVerticalBlockBorderWrapper"] {
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
        .st-key-f3_cfg_general,
        .st-key-f3_cfg_cuts,
        .st-key-f3_cfg_sector {
            height: 100%;
        }
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_sector div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 226px !important;
            padding-top: 0.82rem !important;
            padding-bottom: 0.76rem !important;
        }
        .st-key-f3_cfg_sector div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 246px !important;
            padding-top: 0.88rem !important;
            padding-bottom: 1.15rem !important;
        }
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 166px !important;
            padding-top: 0.46rem !important;
            padding-bottom: 0.34rem !important;
        }
        .st-key-f3_cfg_general [data-testid="stVerticalBlock"],
        .st-key-f3_cfg_cuts [data-testid="stVerticalBlock"],
        .st-key-f3_cfg_sector [data-testid="stVerticalBlock"] {
            gap: 0.45rem !important;
        }
        .st-key-f3_cfg_general [data-testid="stVerticalBlock"],
        .st-key-f3_cfg_cuts [data-testid="stVerticalBlock"] {
            gap: 0.14rem !important;
        }
        .st-key-f3_cfg_general .f3-card-heading,
        .st-key-f3_cfg_cuts .f3-card-heading {
            margin-bottom: 0.2rem !important;
        }
        .st-key-f3_kpi_1,
        .st-key-f3_kpi_2,
        .st-key-f3_kpi_3,
        .st-key-f3_kpi_4,
        .st-key-f3_kpi_5 {
            height: 100%;
        }
        .st-key-f3_kpi_1 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_2 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_4 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_kpi_5 div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 112px !important;
            padding-top: 0.72rem !important;
            padding-bottom: 0.72rem !important;
        }
        .st-key-f3_note_card div[data-testid="stVerticalBlockBorderWrapper"] {
            padding-top: 0.72rem !important;
            padding-bottom: 0.72rem !important;
        }
        .st-key-f3_card_heatmap div[data-testid="stVerticalBlockBorderWrapper"] {
            padding-top: 0.8rem !important;
            padding-bottom: 0.72rem !important;
        }
        .st-key-f3_sector_summary div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.88rem 0.92rem !important;
        }
        .st-key-f3_sector_mini_frecuencia div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_horas div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_horas_eq div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_k_weibull div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_c_weibull div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 78px !important;
            padding: 0.62rem 0.74rem !important;
        }
        .st-key-f3_card_heatmap [data-testid="stPlotlyChart"] {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        .st-key-f3_cfg_general [data-baseweb="input"],
        .st-key-f3_cfg_general [data-baseweb="select"] > div,
        .st-key-f3_cfg_cuts [data-baseweb="input"],
        .st-key-f3_cfg_cuts [data-baseweb="select"] > div,
        .st-key-f3_cfg_sector [data-baseweb="input"],
        .st-key-f3_cfg_sector [data-baseweb="select"] > div {
            min-height: 44px !important;
        }
        .st-key-f3_pg_altura div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_pg_modelo div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_pg_vmax div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_pg_binwidth div[data-testid="stVerticalBlockBorderWrapper"] {
            border: none !important;
            border-radius: 20px !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0.28rem 0.58rem 0.34rem 0.58rem !important;
            min-height: 82px !important;
        }
        .st-key-f3_cfg_general .f3-card-heading {
            gap: 0.72rem !important;
            margin-bottom: 0.65rem !important;
        }
        .st-key-f3_cfg_general [data-testid="stHorizontalBlock"] {
            row-gap: 0.75rem !important;
            column-gap: 1.0rem !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
        }
        .st-key-f3_cfg_general .f3-card-heading__icon {
            width: 40px !important;
            height: 40px !important;
            min-width: 40px !important;
            background: linear-gradient(180deg, #f8fbff 0%, #edf5ff 100%) !important;
            border: 1px solid #bfdbfe !important;
            box-shadow: 0 1px 2px rgba(37, 99, 235, 0.08), inset 0 1px 0 rgba(255,255,255,0.95) !important;
        }
        .st-key-f3_cfg_general .f3-card-heading__title {
            line-height: 1.1 !important;
            display: flex !important;
            align-items: center !important;
            min-height: 40px !important;
        }
        .st-key-f3_cfg_general .f3-card-heading,
        .st-key-f3_cfg_cuts .f3-card-heading,
        .st-key-f3_cfg_sector .f3-card-heading {
            display: flex !important;
            align-items: center !important;
        }
        .st-key-f3_cfg_general .f3-card-heading__icon,
        .st-key-f3_cfg_cuts .f3-card-heading__icon,
        .st-key-f3_cfg_sector .f3-card-heading__icon {
            width: 54px !important;
            height: 54px !important;
            min-width: 54px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            border-radius: 999px !important;
        }
        .st-key-f3_cfg_general .f3-card-heading__icon svg,
        .st-key-f3_cfg_cuts .f3-card-heading__icon svg,
        .st-key-f3_cfg_sector .f3-card-heading__icon svg {
            width: 28px !important;
            height: 28px !important;
            display: block !important;
        }
        .st-key-f3_cfg_general .f3-card-heading__title,
        .st-key-f3_cfg_cuts .f3-card-heading__title,
        .st-key-f3_cfg_sector .f3-card-heading__title {
            display: flex !important;
            align-items: center !important;
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
            transform: translateY(1px) !important;
        }
        .st-key-f3_pg_altura,
        .st-key-f3_pg_modelo,
        .st-key-f3_pg_vmax,
        .st-key-f3_pg_binwidth {
            border: none !important;
            border-radius: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            overflow: visible !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .st-key-f3_pg_altura [data-testid="stWidgetLabel"],
        .st-key-f3_pg_modelo [data-testid="stWidgetLabel"],
        .st-key-f3_pg_vmax [data-testid="stWidgetLabel"],
        .st-key-f3_pg_binwidth [data-testid="stWidgetLabel"] {
            display: none !important;
        }
        .f3-pg-custom-label {
            font-size: 0.86rem !important;
            font-weight: 800 !important;
            color: #1e293b !important;
            line-height: 1.05 !important;
            margin-bottom: 0.45rem !important;
            padding-left: 0.12rem !important;
            transform: none !important;
            position: static !important;
            top: auto !important;
        }
        .f3-pg-field-label {
            transform: none !important;
            position: static !important;
            top: auto !important;
        }
        .f3-pg-bottom-spacer {
            height: 6px !important;
            min-height: 6px !important;
            display: block !important;
        }
        .f3-pg-content-down-spacer {
            display: block !important;
            width: 100% !important;
            height: 10px !important;
            min-height: 10px !important;
        }
        .f3-pg-input-down-gap {
            display: block !important;
            width: 100% !important;
            height: 26px !important;
            min-height: 26px !important;
        }
        .st-key-f3_pg_altura label,
        .st-key-f3_pg_modelo label,
        .st-key-f3_pg_vmax label,
        .st-key-f3_pg_binwidth label {
            font-size: 0.83rem !important;
            font-weight: 400 !important;
            color: #000000 !important;
            line-height: 1.15 !important;
            margin-bottom: 0.18rem !important;
        }
        .st-key-f3_pg_altura [data-baseweb="input"],
        .st-key-f3_pg_modelo [data-baseweb="select"] > div,
        .st-key-f3_pg_vmax [data-baseweb="input"],
        .st-key-f3_pg_binwidth [data-baseweb="input"] {
            min-height: 46px !important;
            background: #ffffff !important;
            border: 1px solid #bfdbfe !important;
            border-radius: 14px !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.98), 0 1px 2px rgba(15, 23, 42, 0.02) !important;
            display: flex !important;
            align-items: center !important;
            overflow: hidden !important;
        }
        .st-key-f3_pg_altura [data-testid="stNumberInput"] [data-baseweb="input"],
        .st-key-f3_pg_vmax [data-testid="stNumberInput"] [data-baseweb="input"],
        .st-key-f3_pg_binwidth [data-testid="stNumberInput"] [data-baseweb="input"] {
            background: #ffffff !important;
            border: 1px solid #bfdbfe !important;
            border-radius: 14px !important;
            overflow: hidden !important;
        }
        .st-key-f3_pg_altura [data-baseweb="input"] > div,
        .st-key-f3_pg_vmax [data-baseweb="input"] > div,
        .st-key-f3_pg_binwidth [data-baseweb="input"] > div,
        .st-key-f3_pg_modelo [data-baseweb="select"] > div > div {
            background: #ffffff !important;
        }
        .st-key-f3_pg_altura [data-baseweb="input"] input,
        .st-key-f3_pg_modelo [data-baseweb="select"] span,
        .st-key-f3_pg_vmax [data-baseweb="input"] input,
        .st-key-f3_pg_binwidth [data-baseweb="input"] input {
            font-weight: 600 !important;
            color: #0f172a !important;
            line-height: 1.1 !important;
            background: #ffffff !important;
        }
        .st-key-f3_pg_altura [data-testid="stNumberInput"] input,
        .st-key-f3_pg_vmax [data-testid="stNumberInput"] input,
        .st-key-f3_pg_binwidth [data-testid="stNumberInput"] input {
            background: #ffffff !important;
            padding-left: 1rem !important;
            font-weight: 800 !important;
            color: #0f172a !important;
        }
        .st-key-f3_pg_modelo [data-baseweb="select"] > div > div {
            min-height: 46px !important;
            align-items: center !important;
        }
        .st-key-f3_pg_modelo [data-baseweb="select"] svg {
            color: #000000 !important;
        }
        .st-key-f3_pg_altura [data-testid="stNumberInput"] [data-baseweb="input"] > div:last-child,
        .st-key-f3_pg_vmax [data-testid="stNumberInput"] [data-baseweb="input"] > div:last-child,
        .st-key-f3_pg_binwidth [data-testid="stNumberInput"] [data-baseweb="input"] > div:last-child {
            background: #ffffff !important;
            border-left: 1px solid #dbeafe !important;
        }
        .st-key-f3_pg_altura [data-baseweb="input"] button,
        .st-key-f3_pg_vmax [data-baseweb="input"] button,
        .st-key-f3_pg_binwidth [data-baseweb="input"] button {
            color: #0f172a !important;
            background: #ffffff !important;
            border-radius: 10px !important;
            border: 1px solid #eef2f7 !important;
            min-width: 2.35rem !important;
        }
        .st-key-f3_pg_altura [data-testid="stNumberInput"] button,
        .st-key-f3_pg_vmax [data-testid="stNumberInput"] button,
        .st-key-f3_pg_binwidth [data-testid="stNumberInput"] button {
            background: #ffffff !important;
            border-left: 1px solid #dbeafe !important;
            color: #0f172a !important;
            min-width: 2.35rem !important;
        }
        .st-key-f3_pg_altura [data-testid="stNumberInput"] button:hover,
        .st-key-f3_pg_vmax [data-testid="stNumberInput"] button:hover,
        .st-key-f3_pg_binwidth [data-testid="stNumberInput"] button:hover {
            background: #eff6ff !important;
        }
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] [data-baseweb="input"] {
            background: #ffffff !important;
            border: 1px solid #bfdbfe !important;
            border-radius: 14px !important;
            overflow: hidden !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.98), 0 1px 2px rgba(15, 23, 42, 0.02) !important;
        }
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] [data-baseweb="input"] > div,
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] [data-baseweb="input"] input {
            background: #ffffff !important;
            color: #0f172a !important;
        }
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] [data-baseweb="input"] > div:last-child {
            background: #ffffff !important;
            border-left: 1px solid #dbeafe !important;
        }
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] button {
            background: #ffffff !important;
            border-left: 1px solid #dbeafe !important;
            border-radius: 10px !important;
            color: #0f172a !important;
            min-width: 2.35rem !important;
        }
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] button:hover {
            background: #eff6ff !important;
        }
        .st-key-f3_cfg_cuts [data-testid="stCheckbox"] {
            padding-top: 0.18rem !important;
        }
        /* Override final: compactar y empatar altura de los dos cards superiores */
        .st-key-f3_cfg_general,
        .st-key-f3_cfg_cuts {
            min-height: unset !important;
            height: auto !important;
        }
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 170px !important;
            height: 170px !important;
            padding-top: 0.42rem !important;
            padding-bottom: 0.34rem !important;
        }
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 205px !important;
            height: 205px !important;
            padding-top: 0.58rem !important;
            padding-bottom: 0.48rem !important;
        }
        .st-key-f3_cfg_general [data-testid="stVerticalBlock"],
        .st-key-f3_cfg_cuts [data-testid="stVerticalBlock"] {
            gap: 0.1rem !important;
        }
        .st-key-f3_cfg_general .f3-card-heading,
        .st-key-f3_cfg_cuts .f3-card-heading {
            margin-bottom: 0.12rem !important;
        }
        .st-key-f3_cfg_general [data-testid="stHorizontalBlock"],
        .st-key-f3_cfg_cuts [data-testid="stHorizontalBlock"] {
            row-gap: 0.32rem !important;
            column-gap: 0.68rem !important;
        }
        /* Override final exclusivo: Parámetros generales (evitar recorte de labels) */
        .st-key-f3_cfg_general {
            overflow: visible !important;
            height: auto !important;
            min-height: unset !important;
        }
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"] {
            overflow: visible !important;
            height: auto !important;
            min-height: 225px !important;
            padding-top: 1.25rem !important;
            padding-bottom: 1.20rem !important;
        }
        .st-key-f3_cfg_general .f3-pg-custom-label,
        .st-key-f3_cfg_general .f3-pg-field-label,
        .st-key-f3_cfg_general .st-key-f3_pg_altura label,
        .st-key-f3_cfg_general .st-key-f3_pg_modelo label,
        .st-key-f3_cfg_general .st-key-f3_pg_vmax label,
        .st-key-f3_cfg_general .st-key-f3_pg_binwidth label {
            top: auto !important;
            transform: none !important;
            position: static !important;
            margin-bottom: 0.35rem !important;
            line-height: 1.15 !important;
        }
        /* Override final: igualar altura visual de los dos cards superiores */
        .st-key-f3_cfg_general,
        .st-key-f3_cfg_cuts {
            min-height: unset !important;
            height: auto !important;
            overflow: visible !important;
        }
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 225px !important;
            height: 225px !important;
            overflow: visible !important;
        }
        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"] {
            padding-top: 1.25rem !important;
            padding-bottom: 1.20rem !important;
        }
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"] {
            padding-top: 0.92rem !important;
            padding-bottom: 0.88rem !important;
        }
        /* ==========================================================
           FIX encabezados superiores Fase 3
           ========================================================== */
        .st-key-f3_cfg_general .f3-header-icon-fixed,
        .st-key-f3_cfg_cuts .f3-header-icon-fixed,
        .st-key-f3_cfg_sector .f3-header-icon-fixed {
            width: 54px !important;
            height: 54px !important;
            min-width: 54px !important;
            border-radius: 999px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            background: linear-gradient(180deg, #f8fbff 0%, #edf5ff 100%) !important;
            border: 1px solid #bfdbfe !important;
            box-shadow: 0 1px 2px rgba(37, 99, 235, 0.08), inset 0 1px 0 rgba(255,255,255,0.95) !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        .st-key-f3_cfg_general .f3-header-icon-fixed svg,
        .st-key-f3_cfg_cuts .f3-header-icon-fixed svg,
        .st-key-f3_cfg_sector .f3-header-icon-fixed svg {
            width: 28px !important;
            height: 28px !important;
            display: block !important;
            margin: 0 !important;
        }

        .st-key-f3_cfg_general .f3-header-title-fixed,
        .st-key-f3_cfg_cuts .f3-header-title-fixed,
        .st-key-f3_cfg_sector .f3-header-title-fixed {
            min-height: 54px !important;
            height: 54px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            color: #2563eb !important;
            font-size: 1.03rem !important;
            font-weight: 900 !important;
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        .st-key-f3_cfg_general .f3-header-subtitle-fixed,
        .st-key-f3_cfg_cuts .f3-header-subtitle-fixed,
        .st-key-f3_cfg_sector .f3-header-subtitle-fixed {
            color: #000000 !important;
            font-size: 0.84rem !important;
            font-weight: 400 !important;
            line-height: 1.2 !important;
            margin-top: 0.18rem !important;
        }
        .f3-sector-bottom-spacer {
            display: block !important;
            width: 100% !important;
            height: 18px !important;
            min-height: 18px !important;
        }
        .f3-cuts-bottom-spacer {
            display: block !important;
            width: 100% !important;
            height: 14px !important;
            min-height: 14px !important;
        }
        .st-key-f3_cfg_sector,
        .st-key-f3_cfg_sector div[data-testid="stVerticalBlockBorderWrapper"] {
            overflow: visible !important;
        }

        /* ==========================================================
           Fase 3 - Negrilla visual en contenedores superiores
           ========================================================== */

        .st-key-f3_cfg_general,
        .st-key-f3_cfg_cuts,
        .st-key-f3_cfg_sector {
            font-weight: 700 !important;
        }

        /* Titulos de cards */
        .st-key-f3_cfg_general .f3-header-title-fixed,
        .st-key-f3_cfg_cuts .f3-header-title-fixed,
        .st-key-f3_cfg_sector .f3-header-title-fixed,
        .st-key-f3_cfg_general .f3-native-header__title,
        .st-key-f3_cfg_cuts .f3-native-header__title,
        .st-key-f3_cfg_sector .f3-native-header__title {
            font-weight: 900 !important;
        }

        /* Labels visibles */
        .st-key-f3_cfg_general label,
        .st-key-f3_cfg_cuts label,
        .st-key-f3_cfg_sector label,
        .st-key-f3_cfg_general .f3-pg-custom-label,
        .st-key-f3_cfg_cuts .f3-pg-custom-label,
        .st-key-f3_cfg_sector .f3-pg-custom-label,
        .st-key-f3_cfg_general .f3-pg-field-label,
        .st-key-f3_cfg_cuts .f3-pg-field-label,
        .st-key-f3_cfg_sector .f3-pg-field-label {
            font-weight: 800 !important;
            color: #0f172a !important;
        }

        /* Texto y numeros dentro de inputs/selects */
        .st-key-f3_cfg_general input,
        .st-key-f3_cfg_cuts input,
        .st-key-f3_cfg_sector input,
        .st-key-f3_cfg_general [data-baseweb="select"] div,
        .st-key-f3_cfg_cuts [data-baseweb="select"] div,
        .st-key-f3_cfg_sector [data-baseweb="select"] div {
            font-weight: 800 !important;
            color: #0f172a !important;
        }

        /* Botones + y - */
        .st-key-f3_cfg_general button,
        .st-key-f3_cfg_cuts button,
        .st-key-f3_cfg_sector button {
            font-weight: 900 !important;
            color: #0f172a !important;
        }

        /* Checkbox y texto asociado */
        .st-key-f3_cfg_cuts [data-testid="stCheckbox"] label,
        .st-key-f3_cfg_cuts [data-testid="stCheckbox"] span,
        .st-key-f3_cfg_cuts [data-testid="stCheckbox"] p {
            font-weight: 800 !important;
            color: #0f172a !important;
        }

        /* Nota azul del bloque Sector */
        .st-key-f3_cfg_sector .f3-soft-note,
        .st-key-f3_cfg_sector .f3-soft-note * {
            font-weight: 800 !important;
            color: #0f52ff !important;
        }

        /* ==========================================================
           Fase 3 - Negrilla labels faltantes Dirección/Sector
           ========================================================== */
        .st-key-f3_cfg_cuts label,
        .st-key-f3_cfg_cuts label p,
        .st-key-f3_cfg_cuts [data-testid="stWidgetLabel"],
        .st-key-f3_cfg_cuts [data-testid="stWidgetLabel"] p,
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] label,
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"] label p,
        .st-key-f3_cfg_cuts [data-testid="stSelectbox"] label,
        .st-key-f3_cfg_cuts [data-testid="stSelectbox"] label p,
        .st-key-f3_cfg_sector label,
        .st-key-f3_cfg_sector label p,
        .st-key-f3_cfg_sector [data-testid="stWidgetLabel"],
        .st-key-f3_cfg_sector [data-testid="stWidgetLabel"] p,
        .st-key-f3_cfg_sector [data-testid="stSelectbox"] label,
        .st-key-f3_cfg_sector [data-testid="stSelectbox"] label p {
            font-weight: 800 !important;
            color: #0f172a !important;
        }

        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_sector div[data-testid="stVerticalBlockBorderWrapper"] {
            box-sizing: border-box !important;
        }

        .st-key-f3_cfg_cuts [data-testid="stSelectbox"],
        .st-key-f3_cfg_cuts [data-testid="stCheckbox"],
        .st-key-f3_cfg_cuts [data-testid="stNumberInput"],
        .st-key-f3_cfg_sector [data-testid="stSelectbox"],
        .st-key-f3_cfg_sector .f3-soft-note {
            transform: translateY(7px) !important;
        }

        .st-key-f3_card_expanders [data-testid="stExpanderDetails"] {
            padding-top: 0.15rem !important;
        }
        div[data-baseweb="input"],
        div[data-baseweb="select"] > div,
        .stCheckbox {
            border-radius: 14px !important;
        }
        div[data-baseweb="input"],
        div[data-baseweb="select"] > div {
            border: 1px solid #dbe5f1 !important;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03) !important;
            background: #ffffff !important;
        }
        [data-testid="stMetric"] {
            padding: 0 !important;
        }
        @media (max-width: 1200px) {
            .f3-mini-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        /* --- Secciones de altura unificada movidas al bloque final para mayor prioridad --- */

        .st-key-f3_cfg_general [data-testid="stVerticalBlock"],
        .st-key-f3_cfg_cuts [data-testid="stVerticalBlock"],
        .st-key-f3_cfg_sector [data-testid="stVerticalBlock"] {
            height: 100% !important;
            min-height: 100% !important;
            max-height: 100% !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }
        .f3-main-card-header {
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 0.46rem !important;
            color: #1e40af !important;
            font-weight: 900 !important;
            font-size: 1.08rem !important;
            line-height: 1 !important;
            margin: 0 !important;
            padding: 0 !important;
        }
        .f3-main-card-header__title {
            display: inline-flex !important;
            align-items: center !important;
            line-height: 1 !important;
        }
        .f3-main-card-header__icon {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 20px !important;
            height: 20px !important;
            border-radius: 999px !important;
            background: #eff6ff !important;
            border: 1px solid #cbd5e1 !important;
            flex-shrink: 0 !important;
        }
        .f3-main-card-header__icon svg {
            display: block !important;
            width: 14px !important;
            height: 14px !important;
        }
        /* ==========================================================
           Fase 3 - Cards limpios Rosa / Análisis
           ========================================================== */
        .st-key-f3_card_rose_v3,
        .st-key-f3_card_sector_v3 {
            width: 100% !important;
            max-width: none !important;
            height: 600px !important;
            min-height: 600px !important;
            max-height: 600px !important;
            box-sizing: border-box !important;
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 28px !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
            overflow: hidden !important;
        }
        .st-key-f3_card_rose_v3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_card_sector_v3 div[data-testid="stVerticalBlockBorderWrapper"] {
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            height: 600px !important;
            min-height: 600px !important;
            max-height: 600px !important;
            padding: 1.10rem 1.25rem 1.10rem 1.25rem !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }
        .st-key-f3_card_rose_v3 [data-testid="stVerticalBlock"],
        .st-key-f3_card_sector_v3 [data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: column !important;
            gap: 0.82rem !important;
            height: 100% !important;
            min-height: 100% !important;
            max-height: 100% !important;
            overflow: hidden !important;
            transform: none !important;
        }
        .st-key-f3_card_rose_v3 [data-testid="stVerticalBlock"] *,
        .st-key-f3_card_sector_v3 [data-testid="stVerticalBlock"] * {
            transform: none !important;
        }
        .st-key-f3_card_rose_v3 [data-testid="stPlotlyChart"],
        .st-key-f3_card_sector_v3 [data-testid="stPlotlyChart"] {
            overflow: visible !important;
        }
        .st-key-f3_rose_body_v3,
        .st-key-f3_sector_body_v3 {
            flex: 1 1 auto !important;
            min-height: 0 !important;
        }
        .st-key-f3_rose_body_v3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_body_v3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_rose_plot_col_v3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_rose_side_col_v3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_plot_wrap_v3 div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_stats_row_v3 div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0 !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }
        .st-key-f3_rose_body_v3 [data-testid="stHorizontalBlock"] {
            align-items: flex-start !important;
            column-gap: 1.05rem !important;
        }
        .st-key-f3_rose_plot_col_v3 [data-testid="stPlotlyChart"] {
            height: 560px !important;
            min-height: 560px !important;
            display: flex !important;
            justify-content: center !important;
            margin: 0 !important;
        }
        .st-key-f3_rose_side_col_v3,
        .st-key-f3_rose_side_col_v3 div[data-testid="stVerticalBlockBorderWrapper"] {
            height: 100% !important;
            min-height: 100% !important;
        }
        .st-key-f3_rose_side_col_v3 [data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: column !important;
            justify-content: flex-start !important;
            height: 100% !important;
            min-height: 100% !important;
        }
        .st-key-f3_rose_table_button_lower {
            position: static !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            flex: 0 0 auto !important;
        }
        .st-key-f3_rose_table_button_lower div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0 !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }
        .f3-rose-button-big-spacer {
            display: block !important;
            width: 100% !important;
            height: 290px !important;
            min-height: 290px !important;
        }
        .st-key-f3_sector_summary {
            border-radius: 18px !important;
            border: 1px solid #cbd5e1 !important;
            border-color: #d7e3f3 !important;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03) !important;
            min-height: 245px !important;
            height: 245px !important;
            border-radius: 22px !important;
            overflow: hidden !important;
        }
        .st-key-f3_sector_summary div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 1.2rem 1.25rem !important;
            min-height: 245px !important;
            height: 245px !important;
            display: flex !important;
            flex-direction: column !important;
            justify-content: flex-start !important;
            box-sizing: border-box !important;
        }
        .st-key-f3_btn_toggle_sector_table {
            margin-top: 0 !important;
        }
        .st-key-f3_btn_toggle_sector_table button {
            min-height: 44px !important;
            border-radius: 14px !important;
            border: 1px solid #bfdbfe !important;
            background: linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%) !important;
            color: #2563eb !important;
            font-weight: 800 !important;
            box-shadow: 0 1px 4px rgba(37, 99, 235, 0.08) !important;
        }
        .st-key-f3_sector_body_v3 [data-testid="stVerticalBlock"] {
            display: flex !important;
            flex-direction: column !important;
            gap: 0.78rem !important;
        }
        .st-key-f3_sector_stats_row_v3 [data-testid="stHorizontalBlock"] {
            column-gap: 0.52rem !important;
            align-items: stretch !important;
        }
        .st-key-f3_sector_stats_row_v3 {
            margin-top: 0.85rem !important;
        }
        .st-key-f3_sector_stats_row_v3 div[data-testid="stVerticalBlockBorderWrapper"] {
            padding-top: 0.35rem !important;
        }
        .st-key-f3_sector_plot_wrap_v3 {
            flex: 1 1 auto !important;
            min-height: 0 !important;
            margin-top: 0.55rem !important;
        }
        .st-key-f3_sector_plot_wrap_v3 [data-testid="stPlotlyChart"] {
            height: 500px !important;
            min-height: 500px !important;
            display: flex !important;
            justify-content: center !important;
            margin: 0 !important;
        }
        .st-key-f3_sector_mini_frecuencia,
        .st-key-f3_sector_mini_horas,
        .st-key-f3_sector_mini_horas_eq,
        .st-key-f3_sector_mini_k_weibull,
        .st-key-f3_sector_mini_c_weibull {
            border-radius: 12px !important;
            background: linear-gradient(180deg, #fbfdff 0%, #f6faff 100%) !important;
            border-color: #d8e3f2 !important;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.035) !important;
        }
        .st-key-f3_sector_mini_frecuencia div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_horas div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_horas_eq div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_k_weibull div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_sector_mini_c_weibull div[data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 58px !important;
            padding: 0.56rem 0.72rem !important;
            border-radius: 12px !important;
        }
        .st-key-f3_sector_mini_frecuencia .f3-mini-stat__label,
        .st-key-f3_sector_mini_horas .f3-mini-stat__label,
        .st-key-f3_sector_mini_horas_eq .f3-mini-stat__label,
        .st-key-f3_sector_mini_k_weibull .f3-mini-stat__label,
        .st-key-f3_sector_mini_c_weibull .f3-mini-stat__label {
            font-size: 0.74rem !important;
            margin-bottom: 0.1rem !important;
        }
        .st-key-f3_sector_mini_frecuencia .f3-mini-stat__value,
        .st-key-f3_sector_mini_horas .f3-mini-stat__value,
        .st-key-f3_sector_mini_horas_eq .f3-mini-stat__value,
        .st-key-f3_sector_mini_k_weibull .f3-mini-stat__value,
        .st-key-f3_sector_mini_c_weibull .f3-mini-stat__value {
            font-size: 1.04rem !important;
        }
        .f3_sector_stats_row_v3 .f3-mini-stat,
        .st-key-f3_card_sector_v3 .f3-mini-stat {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            position: relative !important;
        }
.f3_sector_stats_row_v3 .f3-mini-stat > *,
.st-key-f3_card_sector_v3 .f3-mini-stat > * {
    transform: translateY(-6px) !important;
}

.st-key-f3_sector_mini_frecuencia .f3-mini-stat__label,
.st-key-f3_sector_mini_frecuencia .f3-mini-stat__value,
.st-key-f3_sector_mini_horas .f3-mini-stat__label,
.st-key-f3_sector_mini_horas .f3-mini-stat__value,
.st-key-f3_sector_mini_horas_eq .f3-mini-stat__label,
.st-key-f3_sector_mini_horas_eq .f3-mini-stat__value,
.st-key-f3_sector_mini_k_weibull .f3-mini-stat__label,
.st-key-f3_sector_mini_k_weibull .f3-mini-stat__value,
.st-key-f3_sector_mini_c_weibull .f3-mini-stat__label,
.st-key-f3_sector_mini_c_weibull .f3-mini-stat__value {
    transform: translateY(-10px) !important;
}
        .f3_sector_stats_row_v3 .f3-mini-stat__label,
        .st-key-f3_card_sector_v3 .f3-mini-stat__label {
            width: 100% !important;
            text-align: center !important;
            margin-bottom: 0.12rem !important;
        }
        .f3_sector_stats_row_v3 .f3-mini-stat__value,
        .st-key-f3_card_sector_v3 .f3-mini-stat__value {
            width: 100% !important;
            text-align: center !important;
        }
        .st-key-f3_sector_table_detached {
            border: 1.35px solid #cbd5e1 !important;
            border-radius: 28px !important;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.045) !important;
            overflow: hidden !important;
        }
        .st-key-f3_sector_table_detached div[data-testid="stVerticalBlockBorderWrapper"] {
            border: none !important;
            border-radius: 28px !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0.95rem 1.05rem 1.05rem 1.05rem !important;
        }
        .f3-sector-table-title {
            color: #1e40af !important;
            font-size: 1.08rem !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
            margin: 0 0 0.58rem 0 !important;
            padding: 0 !important;
        }
        .st-key-f3_sector_table_detached [data-testid="stDataFrame"] {
            border: 1px solid #d5e2f2 !important;
            border-radius: 16px !important;
            background: #ffffff !important;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.035) !important;
            overflow: hidden !important;
        }
        .st-key-f3_sector_table_detached [data-testid="stDataFrame"] [role="columnheader"],
        .st-key-f3_sector_table_detached [data-testid="stDataFrame"] thead th {
            background: linear-gradient(180deg, #f2f7ff 0%, #eaf2ff 100%) !important;
            color: #1e3a8a !important;
            font-weight: 900 !important;
            border-bottom: 1px solid #d5e2f2 !important;
        }
        .st-key-f3_sector_table_detached [data-testid="stDataFrame"] [role="gridcell"],
        .st-key-f3_sector_table_detached [data-testid="stDataFrame"] tbody td {
            color: #0f172a !important;
            font-weight: 800 !important;
        }
        .st-key-f3_card_heatmap {
            border: 1.25px solid #e2e8f0 !important;
            border-radius: 24px !important;
            background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
            box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
            overflow: hidden !important;
            height: 520px !important;
            min-height: 520px !important;
            max-height: 520px !important;
        }
        .st-key-f3_card_heatmap div[data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.85rem 1rem 0.95rem 1rem !important;
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            height: 520px !important;
            min-height: 520px !important;
            max-height: 520px !important;
            box-sizing: border-box !important;
        }
        .st-key-f3_card_heatmap .f3-native-header,
        .st-key-f3_card_heatmap .f3-card-heading {
            margin-bottom: 0.36rem !important;
            justify-content: flex-start !important;
            align-items: center !important;
            text-align: left !important;
        }
        .f3-heatmap-title-row {
            display: flex !important;
            align-items: center !important;
            justify-content: flex-start !important;
            gap: 0.45rem !important;
            margin: 0 0 0.36rem 0 !important;
            padding: 0 !important;
            text-align: left !important;
        }
        .f3-heatmap-title-text {
            color: #2563eb !important;
            font-size: 1.03rem !important;
            font-weight: 900 !important;
            line-height: 1.1 !important;
        }
        .f3-heatmap-title-info {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            width: 19px !important;
            height: 19px !important;
            border-radius: 999px !important;
            border: 1px solid #cbd5e1 !important;
            background: #eff6ff !important;
            color: #2563eb !important;
            flex-shrink: 0 !important;
        }
        .st-key-f3_card_heatmap .f3-card-heading__title,
        .st-key-f3_card_heatmap .f3-header-title-fixed,
        .st-key-f3_card_heatmap .f3-native-header__title {
            color: #2563eb !important;
            font-weight: 900 !important;
            text-align: left !important;
        }
        .st-key-f3_card_heatmap [data-testid="stPlotlyChart"] {
            display: flex !important;
            justify-content: center !important;
            margin: 0 !important;
            height: 455px !important;
            min-height: 455px !important;
        }
        .st-key-f3_card_heatmap [data-testid="stPlotlyChart"] .gtitle,
        .st-key-f3_card_heatmap [data-testid="stPlotlyChart"] .infolayer .g-gtitle {
            display: none !important;
            opacity: 0 !important;
            visibility: hidden !important;
        }
        .f3-heatmap-top-spacer {
            display: block !important;
            width: 100% !important;
            height: 14px !important;
            min-height: 14px !important;
        }

        /* --- Responsive fixes simplificados --- */

        .f3-card-heading {
            display: flex !important;
            align-items: center !important;
            gap: 0.85rem !important;
            flex-wrap: nowrap !important;
        }

        .f3-card-heading__title {
            line-height: 1.15 !important;
            overflow-wrap: anywhere !important;
        }

        .f3-card-heading__icon {
            width: clamp(42px, 3.6vw, 64px) !important;
            height: clamp(42px, 3.6vw, 64px) !important;
            min-width: clamp(42px, 3.6vw, 64px) !important;
        }

        .st-key-f3_cfg_general [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
        .st-key-f3_cfg_cuts [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
        .st-key-f3_cfg_sector [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 0 !important;
        }

        .f3-kpi-card {
            min-height: 96px !important;
            height: auto !important;
            overflow: visible !important;
            display: flex !important;
            align-items: center !important;
            gap: clamp(0.55rem, 1vw, 1rem) !important;
        }

        .f3-kpi-card__icon {
            width: clamp(44px, 3.4vw, 64px) !important;
            height: clamp(44px, 3.4vw, 64px) !important;
            min-width: clamp(44px, 3.4vw, 64px) !important;
            transform: translateY(-4px) !important;
        }

        .f3-kpi-card__label {
            line-height: 1.1 !important;
            overflow-wrap: anywhere !important;
        }

        .f3-kpi-card__value {
            line-height: 1.05 !important;
            overflow-wrap: anywhere !important;
        }

        @media (max-width: 1350px) {
            .f3-card-heading {
                gap: 0.65rem !important;
            }

            .f3-card-heading__title {
                font-size: 1.05rem !important;
                line-height: 1.15 !important;
            }

            .f3-card-heading__icon {
                width: 48px !important;
                height: 48px !important;
                min-width: 48px !important;
            }

            .f3-kpi-card {
                padding: 0.75rem 0.85rem !important;
                gap: 0.65rem !important;
            }

            .f3-kpi-card__icon {
                width: 48px !important;
                height: 48px !important;
                min-width: 48px !important;
                transform: translateY(-4px) !important;
            }

            .f3-kpi-card__value {
                font-size: clamp(1.25rem, 2vw, 1.9rem) !important;
            }

            .f3-kpi-card__label {
                font-size: 0.78rem !important;
            }
        }

        @media (max-width: 1100px) {
            .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f3_cfg_sector div[data-testid="stVerticalBlockBorderWrapper"] {
                min-height: unset !important;
                height: auto !important;
            }

            .f3-card-heading {
                flex-wrap: wrap !important;
                align-items: flex-start !important;
            }

            .f3-kpi-card {
                min-height: 88px !important;
            }

            .f3-kpi-card__value {
                font-size: 1.35rem !important;
            }
        }
        .f3-cut-field-label {
            min-height: 2.55rem;
            display: flex;
            align-items: flex-start;
            color: #0f172a;
            font-weight: 850;
            font-size: clamp(0.84rem, 0.85vw, 1rem);
            line-height: 1.18;
            margin-bottom: 0.35rem;
        }

        .f3-sector-title-row {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .f3-sector-title-icon {
            width: 56px;
            height: 56px;
            min-width: 56px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(180deg, #f8fbff 0%, #edf5ff 100%);
            border: 1px solid #bfdbfe;
            box-shadow: 0 1px 2px rgba(37, 99, 235, 0.08), inset 0 1px 0 rgba(255,255,255,0.95);
        }

        .f3-sector-title-text {
            color: #2563eb;
            font-weight: 900;
            font-size: 1.03rem;
        }

        .st-key-f3_cfg_cuts [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            min-width: 0 !important;
        }

        /* ==========================================================
           Fase 3 - Altura unificada exacta (250px)
           ========================================================== */
        .st-key-f3_cfg_general,
        .st-key-f3_cfg_cuts,
        .st-key-f3_cfg_sector {
            height: 320px !important;
            min-height: 320px !important;
            max-height: 320px !important;
            box-sizing: border-box !important;
            overflow: visible !important;
        }

        .st-key-f3_cfg_general div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_cuts div[data-testid="stVerticalBlockBorderWrapper"],
        .st-key-f3_cfg_sector div[data-testid="stVerticalBlockBorderWrapper"] {
            height: 320px !important;
            min-height: 320px !important;
            max-height: 320px !important;
            box-sizing: border-box !important;
            overflow: visible !important;
            padding-bottom: 0 !important;
        }

        /* Compactar recuadro azul informativo de Sector */
        .st-key-f3_cfg_sector .f3-soft-note,
        .st-key-f3_cfg_sector .f3-sector-info-note,
        .st-key-f3_cfg_sector .f3-info-banner,
        .st-key-f3_cfg_sector .f3-sector-info,
        .st-key-f3_cfg_sector .f3-note-card {
            padding: 0.42rem 0.55rem !important;
            margin-top: 0.45rem !important;
            margin-bottom: 0 !important;
            min-height: 42px !important;
            border-radius: 12px !important;
            display: flex !important;
            align-items: center !important;
            gap: 0.50rem !important;
            transform: none !important;
        }

        .st-key-f3_cfg_sector .f3-soft-note,
        .st-key-f3_cfg_sector .f3-soft-note *,
        .st-key-f3_cfg_sector .f3-sector-info-note *,
        .st-key-f3_cfg_sector .f3-info-banner *,
        .st-key-f3_cfg_sector .f3-sector-info *,
        .st-key-f3_cfg_sector .f3-note-card * {
            font-size: 0.68rem !important;
            line-height: 1.12 !important;
            font-weight: 400 !important;
        }

        .st-key-f3_cfg_sector .f3-soft-note svg,
        .st-key-f3_cfg_sector .f3-sector-info-note svg,
        .st-key-f3_cfg_sector .f3-info-banner svg,
        .st-key-f3_cfg_sector .f3-sector-info svg,
        .st-key-f3_cfg_sector .f3-note-card svg {
            width: 18px !important;
            height: 18px !important;
        }

        .st-key-f3_cfg_sector .f3-soft-note .f3-card-heading__icon {
            width: 28px !important;
            height: 28px !important;
            min-width: 28px !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        }

        @media (max-width: 1400px) {
            .f3-cut-field-label {
                min-height: 2.75rem;
                font-size: 0.86rem;
            }
            .st-key-f3_cfg_sector .f3-soft-note {
                padding: 0.45rem 0.60rem !important;
                min-height: 50px !important;
            }
            .st-key-f3_cfg_sector .f3-soft-note,
            .st-key-f3_cfg_sector .f3-soft-note * {
                font-size: 0.72rem !important;
                line-height: 1.15 !important;
            }
            .st-key-f3_cfg_sector .f3-soft-note svg {
                width: 20px !important;
                height: 20px !important;
            }
            .st-key-f3_cfg_sector .f3-soft-note .f3-card-heading__icon {
                width: 30px !important;
                height: 30px !important;
                min-width: 30px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _panel_header_html(title: str, icon_name: str, subtitle: str = "") -> str:
    subtitle_html = f'<div class="f3-card-heading__subtitle">{subtitle}</div>' if subtitle else ""
    return textwrap.dedent(
        f"""
        <div class="f3-card-heading">
            <div class="f3-card-heading__icon">{_icon_svg(icon_name, 18, "#2563eb")}</div>
            <div>
                <div class="f3-card-heading__title">{title}</div>
                {subtitle_html}
            </div>
        </div>
        """
    ).strip()


def _kpi_card_html(icon_name: str, label: str, value: str) -> str:
    return textwrap.dedent(
        f"""
        <div class="f3-kpi-card">
            <div class="f3-kpi-card__icon">{_icon_svg(icon_name, 22, "#2563eb")}</div>
            <div>
                <div class="f3-kpi-card__label">{label}</div>
                <div class="f3-kpi-card__value">{value}</div>
            </div>
        </div>
        """
    ).strip()


def _mini_stat_html(label: str, value: str) -> str:
    return textwrap.dedent(
        f"""
        <div class="f3-mini-stat">
            <div class="f3-mini-stat__label">{label}</div>
            <div class="f3-mini-stat__value">{value}</div>
        </div>
        """
    ).strip()


def _extract_alpha_promedio(meta: dict) -> str:
    for idx in (1, 2):
        name = str(meta.get(f"parametro_{idx}_nombre") or "")
        value = meta.get(f"parametro_{idx}_valor", np.nan)
        if "alpha" in name.lower() and pd.notna(value):
            return f"{float(value):.4f}"
    return "N/A"


def _summary_sector_html(resumen: pd.DataFrame, direccion_fuente: str) -> str:
    fila_max = resumen.loc[resumen["Frecuencia (%)"].idxmax()]
    fila_min = resumen.loc[resumen["Frecuencia (%)"].idxmin()]
    rows = [
        ("Sectores", f"{int((resumen['Datos'] > 0).sum())}"),
        ("Dirección usada", direccion_fuente),
        ("Frecuencia máx.", f"{fila_max['Frecuencia (%)']:.2f}% ({fila_max['Sector']})"),
        ("Frecuencia mín.", f"{fila_min['Frecuencia (%)']:.2f}% ({fila_min['Sector']})"),
    ]
    rows_html = "".join(
        f'<div class="f3-summary-row"><div class="f3-summary-row__label">{label}</div><div class="f3-summary-row__value">{value}</div></div>'
        for label, value in rows
    )
    return f'<div class="f3-summary-card"><div class="f3-summary-card__title">Resumen sectorial</div>{rows_html}</div>'


def _render_card_header_native(title: str, icon_name: str, subtitle: str = ""):
    """Card-head Aurora: squircle tintado (emoji/glifo o SVG) + título + subtítulo."""
    if icon_name and (not icon_name.isascii() or len(icon_name) <= 2):
        icon_html = f'<span class="aur-cicon-emoji">{icon_name}</span>'
    else:
        icon_html = _icon_svg(icon_name, 22, "#4f46e5")
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f'<div class="aur-card-head"><div class="aur-cicon">{icon_html}</div>'
        f"<div><h2>{title}</h2>{sub}</div></div>",
        unsafe_allow_html=True,
    )


def _render_kpi_card_native(icon_name: str, label: str, value: str, sub: str = "", kc: str = "#4f46e5"):
    """KPI Aurora: aro tintado (emoji/glifo o SVG) + label + valor + subtítulo."""
    if icon_name and (not icon_name.isascii() or len(icon_name) <= 2):
        icon_html = f'<span class="aur-ki-emoji">{icon_name}</span>'
    else:
        icon_html = _icon_svg(icon_name, 24, kc)
    sub_html = f"<i>{sub}</i>" if sub else ""
    st.markdown(
        f'<div class="aur-kpi" style="--kc:{kc}"><div class="aur-ki">{icon_html}</div>'
        f'<div class="aur-kpi-copy"><small>{label}</small><b>{value}</b>{sub_html}</div></div>',
        unsafe_allow_html=True,
    )


def _render_summary_sector_native(resumen: pd.DataFrame, direccion_fuente: str):
    fila_max = resumen.loc[resumen["Frecuencia (%)"].idxmax()]
    fila_min = resumen.loc[resumen["Frecuencia (%)"].idxmin()]
    st.markdown('<div class="f3-summary-card__title">Resumen sectorial</div>', unsafe_allow_html=True)
    rows = [
        ("Sectores", f"{int((resumen['Datos'] > 0).sum())}"),
        ("Dirección usada", direccion_fuente),
        ("Frecuencia máx.", f"{fila_max['Frecuencia (%)']:.2f}% ({fila_max['Sector']})"),
        ("Frecuencia mín.", f"{fila_min['Frecuencia (%)']:.2f}% ({fila_min['Sector']})"),
    ]
    for idx, (label, value) in enumerate(rows):
        border_style = "1px solid #eef4fb" if idx < len(rows) - 1 else "none"
        st.markdown(
            f"""
            <div class="f3-summary-row" style="border-bottom:{border_style};">
                <div class="f3-summary-row__label">{label}</div>
                <div class="f3-summary-row__value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_soft_note_native(text: str):
    icon_col, text_col = st.columns([0.08, 0.92], gap="small")
    with icon_col:
        st.markdown(
            f'<div class="f3-card-heading__icon f3-card-heading__icon--note">{_icon_svg("info", 16, "#2563eb")}</div>',
            unsafe_allow_html=True,
        )
    with text_col:
        st.markdown(f'<div class="f3-soft-note__text">{text}</div>', unsafe_allow_html=True)


_render_phase3_css()

# ═══════ Aurora (paridad mockup 03_fase3, acento índigo) — hero + card-head + KPI ═══════
st.markdown(
    """
    <style>
    .f3-hero{position:relative;overflow:hidden;border-radius:26px !important;padding:22px 28px !important;
      background:linear-gradient(118deg,#4f46e5 0%, #3730a3 80%) !important;border:none !important;
      box-shadow:0 22px 44px rgba(79,70,229,.32), inset 0 1px 0 rgba(255,255,255,.25) !important;margin:0 0 1rem 0 !important}
    .f3-hero::after{content:"";position:absolute;inset:0;pointer-events:none;background:
      radial-gradient(circle at 86% 12%, rgba(255,255,255,.20) 0 54px, transparent 55px),
      radial-gradient(circle at 95% 70%, rgba(255,255,255,.12) 0 86px, transparent 87px),
      linear-gradient(180deg, rgba(255,255,255,.08), transparent 40%)}
    .f3-wind{position:absolute;left:-30px;top:0;bottom:0;width:58%;height:100%;opacity:.45;pointer-events:none;z-index:1}
    .f3-wind path{stroke:rgba(255,255,255,.55);stroke-width:2;fill:none;stroke-dasharray:16 11;animation:f3windmove 2.6s linear infinite}
    .f3-wind path:nth-child(2){animation-duration:3.4s;opacity:.7}
    .f3-wind path:nth-child(3){animation-duration:4.2s;opacity:.5}
    @keyframes f3windmove{to{stroke-dashoffset:-54}}
    .f3-hero-row{display:flex;align-items:center;gap:18px;position:relative;z-index:2}
    .f3-hero-icon{width:62px;height:62px;border-radius:19px;background:rgba(255,255,255,.17);
      border:1.5px solid rgba(255,255,255,.4);display:flex;align-items:center;justify-content:center;font-size:31px;flex-shrink:0;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 8px 18px rgba(0,0,0,.12)}
    .f3-hero-text{flex:1;min-width:0}
    .f3-hero .f3-hero-title{font-size:25px;font-weight:900;color:#fff;letter-spacing:-.025em;
      text-shadow:0 1px 2px rgba(0,0,0,.12);margin:0;line-height:1.15}
    .f3-hero .f3-hero-subtitle{font-size:12.5px;color:rgba(255,255,255,.94);font-weight:500;
      max-width:840px;margin:4px 0 0 0;line-height:1.45}
    .f3-hero-pills{display:flex;gap:9px;margin-left:auto;flex-shrink:0}
    .f3-hpill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4);border-radius:15px;
      padding:8px 15px;text-align:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.25);color:#fff}
    .f3-hpill b{display:block;font-size:16.5px;letter-spacing:-.01em}
    .f3-hpill span{font-size:9px;opacity:.92;text-transform:uppercase;letter-spacing:.07em;font-weight:700}
    /* Card-head Aurora */
    .aur-card-head{display:flex;align-items:center;gap:13px;margin-bottom:14px}
    .aur-cicon{width:46px;height:46px;border-radius:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;
      background:linear-gradient(135deg, color-mix(in srgb,#4f46e5 16%,#fff), color-mix(in srgb,#4f46e5 7%,#fff));
      border:1.5px solid color-mix(in srgb,#4f46e5 35%,#fff);box-shadow:0 5px 12px color-mix(in srgb,#4f46e5 16%,transparent)}
    .aur-cicon svg{width:22px;height:22px}
    .aur-cicon-emoji{font-size:23px;line-height:1;display:flex;align-items:center;justify-content:center}
    .aur-card-head h2{margin:0;font-size:16.5px;font-weight:900;color:#0b2447;letter-spacing:-.02em}
    .aur-card-head p{margin:2px 0 0;font-size:11px;color:#5a6b85;font-weight:600}
    /* KPI Aurora */
    .aur-kpi{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;display:flex;gap:12px;align-items:center;
      box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06);min-height:74px;height:100%}
    .aur-ki{width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0;
      background:linear-gradient(135deg, color-mix(in srgb,var(--kc,#4f46e5) 17%,#fff), color-mix(in srgb,var(--kc,#4f46e5) 6%,#fff));
      border:1.5px solid color-mix(in srgb,var(--kc,#4f46e5) 38%,#fff);box-shadow:0 5px 12px color-mix(in srgb,var(--kc,#4f46e5) 18%,transparent)}
    .aur-ki svg{width:24px;height:24px}
    .aur-ki-emoji{font-size:23px;line-height:1;display:flex;align-items:center;justify-content:center}
    .aur-kpi-copy{min-width:0}
    .aur-kpi-copy small{display:block;font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.07em}
    .aur-kpi-copy b{font-size:20px;letter-spacing:-.025em;line-height:1.08;display:block;margin-top:3px;color:#0b2447;font-variant-numeric:tabular-nums}
    .aur-kpi-copy i{font-style:normal;font-size:10px;color:#5a6b85;display:block;margin-top:2.5px;font-weight:600;line-height:1.25}
    .aur-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;font-weight:800;color:#5a6b85;margin:12px 0 2px;justify-content:center}
    .aur-legend i{font-style:normal;display:inline-flex;align-items:center;gap:6px}
    .aur-legend i::before{content:"";width:12px;height:12px;border-radius:4px;background:var(--lc);box-shadow:0 2px 5px color-mix(in srgb,var(--lc) 40%,transparent)}
    /* Hero ocupa el contenedor sin borde/padding del wrapper */
    .st-key-f3_card_header div[data-testid="stVerticalBlockBorderWrapper"]{border:none !important;background:transparent !important;padding:0 !important;box-shadow:none !important}
    .st-key-f3_card_header::before{display:none !important}
    /* KPIs del sector (4 en card mitad): mismo look que el strip, legibles */
    .st-key-f3_skpi_1 .aur-kpi,.st-key-f3_skpi_2 .aur-kpi,.st-key-f3_skpi_3 .aur-kpi,.st-key-f3_skpi_4 .aur-kpi{padding:13px 14px;gap:12px;height:92px !important;min-height:92px !important}
    .st-key-f3_skpi_1 .aur-ki,.st-key-f3_skpi_2 .aur-ki,.st-key-f3_skpi_3 .aur-ki,.st-key-f3_skpi_4 .aur-ki{width:44px;height:44px}
    .st-key-f3_skpi_1 .aur-ki-emoji,.st-key-f3_skpi_2 .aur-ki-emoji,.st-key-f3_skpi_3 .aur-ki-emoji,.st-key-f3_skpi_4 .aur-ki-emoji{font-size:20px}
    .st-key-f3_skpi_1 .aur-kpi-copy small,.st-key-f3_skpi_2 .aur-kpi-copy small,.st-key-f3_skpi_3 .aur-kpi-copy small,.st-key-f3_skpi_4 .aur-kpi-copy small{font-size:9px;letter-spacing:.04em;white-space:nowrap}
    .st-key-f3_skpi_1 .aur-kpi-copy b,.st-key-f3_skpi_2 .aur-kpi-copy b,.st-key-f3_skpi_3 .aur-kpi-copy b,.st-key-f3_skpi_4 .aur-kpi-copy b{font-size:18px;white-space:nowrap}
    .st-key-f3_skpi_1 .aur-kpi-copy i,.st-key-f3_skpi_2 .aur-kpi-copy i,.st-key-f3_skpi_3 .aur-kpi-copy i,.st-key-f3_skpi_4 .aur-kpi-copy i{font-size:10px;white-space:nowrap}
    /* Rosa centrada en su columna */
    .st-key-f3_rose_plot_col_v3{display:flex;align-items:center;justify-content:center}
    /* Anular alturas fijas viejas (600px) de las cards rosa/sector → ajustar al contenido SVG */
    .st-key-f3_card_rose_v3,.st-key-f3_card_sector_v3{height:auto !important;min-height:0 !important;max-height:none !important}
    .st-key-f3_card_rose_v3 div[data-testid="stVerticalBlockBorderWrapper"],.st-key-f3_card_sector_v3 div[data-testid="stVerticalBlockBorderWrapper"]{height:auto !important;min-height:0 !important;max-height:none !important}
    .st-key-f3_card_rose_v3 [data-testid="stVerticalBlock"],.st-key-f3_card_sector_v3 [data-testid="stVerticalBlock"]{height:auto !important;min-height:0 !important;max-height:none !important;overflow:visible !important}
    .st-key-f3_rose_plot_col_v3 [data-testid="stPlotlyChart"]{height:auto !important;min-height:0 !important}
    /* KPI strip: 5 cards del mismo alto (tile altura fija) y contenido centrado */
    .st-key-f3_kpi_1 .aur-kpi,.st-key-f3_kpi_2 .aur-kpi,.st-key-f3_kpi_3 .aur-kpi,.st-key-f3_kpi_4 .aur-kpi,.st-key-f3_kpi_5 .aur-kpi{height:78px !important;min-height:78px !important}
    .st-key-f3_kpi_1 .aur-kpi-copy small,.st-key-f3_kpi_2 .aur-kpi-copy small,.st-key-f3_kpi_3 .aur-kpi-copy small,.st-key-f3_kpi_4 .aur-kpi-copy small,.st-key-f3_kpi_5 .aur-kpi-copy small{white-space:nowrap}
    .st-key-f3_kpi_1 .aur-kpi-copy b,.st-key-f3_kpi_2 .aur-kpi-copy b,.st-key-f3_kpi_3 .aur-kpi-copy b,.st-key-f3_kpi_4 .aur-kpi-copy b,.st-key-f3_kpi_5 .aur-kpi-copy b{white-space:nowrap}
    /* El _phase_card de los KPIs (strip+sector) dibuja su borde gris (8px) en el propio stVerticalBlock -> quitarlo para que se vea SOLO la .aur-kpi blanca redondeada con sombra */
    .st-key-f3_kpi_1,.st-key-f3_kpi_2,.st-key-f3_kpi_3,.st-key-f3_kpi_4,.st-key-f3_kpi_5,
    .st-key-f3_skpi_1,.st-key-f3_skpi_2,.st-key-f3_skpi_3,.st-key-f3_skpi_4{background:transparent !important;border:none !important;box-shadow:none !important;padding:0 !important;border-radius:0 !important;overflow:visible !important}
    /* Botones a índigo (acento F3) */
    .st-key-f3_btn_toggle_sector_table [data-testid="stButton"]>button,
    .st-key-f3_use_alpha_calc [data-testid="stButton"]>button{color:#4f46e5 !important;border-color:#c7d2fe !important}
    .st-key-f3_btn_toggle_sector_table [data-testid="stButton"]>button p,
    .st-key-f3_use_alpha_calc [data-testid="stButton"]>button p{color:#4f46e5 !important}
    .st-key-f3_use_alpha_calc [data-testid="stButton"]>button:hover,
    .st-key-f3_btn_toggle_sector_table [data-testid="stButton"]>button:hover{border-color:#4f46e5 !important}
    /* ── Aurora v2: el hero NO va dentro de una card blanca (el st-key cae en el propio stVerticalBlock) ── */
    #root .st-key-f3_card_header{background:transparent !important;border:none !important;box-shadow:none !important;
      padding:0 !important;border-radius:0 !important;min-height:0 !important;height:auto !important;overflow:visible !important;
      margin-bottom:14px !important;gap:0 !important}
    #root .st-key-f3_card_header .f3-hero{margin:0 !important}
    /* mismo alto que el hero de F1/F2 (131px: padding 22 + fila 87 + 22) */
    #root .st-key-f3_card_header .f3-hero-row{min-height:87px !important}
    /* cortes: la etiqueta quedaba pegada/cortada por el borde del input (margin-bottom:-16px nativo del markdown) */
    #root .st-key-f3_cfg_cuts [data-testid="stMarkdownContainer"]:has(> .f3-cut-field-label){margin-bottom:0 !important}
    #root .st-key-f3_cfg_cuts [data-testid="stElementContainer"]:has(.f3-cut-field-label){height:auto !important;min-height:0 !important;overflow:visible !important}
    #root .st-key-f3_cfg_cuts .f3-cut-field-label{display:block !important;margin:0 0 6px !important;padding:0 !important;transform:none !important;position:static !important}
    #root .st-key-f3_cfg_cuts [data-testid="stHorizontalBlock"] [data-testid="stVerticalBlock"]{gap:0 !important}
    #root .st-key-f3_cfg_cuts [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] p{margin-bottom:6px !important}
    /* ── Aurora v2: 3 cards de configuración (paridad 03_fase3: .card / .field / .input / .chip / .banner) ── */
    #root .st-key-f3_cfg_general,#root .st-key-f3_cfg_cuts,#root .st-key-f3_cfg_sector{
      min-height:0 !important;height:100% !important;padding:20px 22px 18px !important;border:1px solid #d3e0f0 !important;
      border-radius:26px !important;background:linear-gradient(180deg,#fff,#fcfdff) !important;
      box-shadow:0 1px 2px rgba(11,36,71,.05),0 10px 28px rgba(11,36,71,.08) !important;gap:10px !important;margin-bottom:14px !important}
    #root div[data-testid="stLayoutWrapper"]:has(> .st-key-f3_cfg_general),
    #root div[data-testid="stLayoutWrapper"]:has(> .st-key-f3_cfg_cuts),
    #root div[data-testid="stLayoutWrapper"]:has(> .st-key-f3_cfg_sector){flex:1 1 auto !important}
    #root .st-key-f3_cfg_general .aur-card-head,#root .st-key-f3_cfg_cuts .aur-card-head,#root .st-key-f3_cfg_sector .aur-card-head{margin-bottom:4px !important}
    #root .st-key-f3_cfg_general [data-testid="stHorizontalBlock"],#root .st-key-f3_cfg_cuts [data-testid="stHorizontalBlock"]{gap:12px !important}
    #root .st-key-f3_pg_altura,#root .st-key-f3_pg_modelo,#root .st-key-f3_pg_vmax,#root .st-key-f3_pg_binwidth{
      border:none !important;background:transparent !important;box-shadow:none !important;padding:0 !important;
      border-radius:0 !important;margin:0 !important;gap:0 !important;min-height:0 !important}
    /* la etiqueta custom colapsaba (h0 por CSS viejo) y quedaba bajo el input → devolverle su alto */
    #root [class*="st-key-f3_pg_"] [data-testid="stElementContainer"]:has(.f3-pg-custom-label),
    #root [class*="st-key-f3_pg_"] [data-testid="stElementContainer"]:has(.f3-pg-custom-label) [data-testid="stMarkdown"],
    #root [class*="st-key-f3_pg_"] [data-testid="stElementContainer"]:has(.f3-pg-custom-label) [data-testid="stMarkdown"] > div{
      height:auto !important;min-height:0 !important;max-height:none !important;margin:0 !important;overflow:visible !important}
    #root [class*="st-key-f3_pg_"] .f3-pg-custom-label{display:block !important;padding:0 !important}
    #root [class*="st-key-f3_pg_"] [data-testid="stMarkdownContainer"]:has(> .f3-pg-custom-label){margin-bottom:0 !important}
    /* etiquetas: MAYÚSCULAS 9.5px como .field label */
    #root .st-key-f3_cfg_general .f3-pg-custom-label,#root .st-key-f3_cfg_cuts .f3-cut-field-label,
    #root .st-key-f3_cfg_cuts [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] p,
    #root .st-key-f3_cfg_sector [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] p{
      font-size:9.5px !important;font-weight:900 !important;color:#64748b !important;text-transform:uppercase !important;
      letter-spacing:.06em !important;margin:0 0 5px !important;line-height:1.2 !important;min-height:0 !important}
    #root .st-key-f3_cfg_cuts [data-testid="stSelectbox"] [data-testid="stWidgetLabel"],
    #root .st-key-f3_cfg_sector [data-testid="stSelectbox"] [data-testid="stWidgetLabel"]{min-height:0 !important;margin:0 !important}
    /* inputs: 42px, borde 1.5px #cfe0f5, radio 12, texto 13.5px/800 */
    #root .st-key-f3_cfg_general [data-testid="stNumberInputContainer"],#root .st-key-f3_cfg_cuts [data-testid="stNumberInputContainer"],
    #root .st-key-f3_cfg_general [data-baseweb="select"] > div,#root .st-key-f3_cfg_cuts [data-baseweb="select"] > div,
    #root .st-key-f3_cfg_sector [data-baseweb="select"] > div{
      height:42px !important;min-height:42px !important;border:1.5px solid #cfe0f5 !important;border-radius:12px !important;
      background:#fff !important;box-shadow:inset 0 1px 3px rgba(11,36,71,.04) !important;overflow:hidden !important}
    #root .st-key-f3_cfg_general [data-testid="stNumberInputContainer"] [data-baseweb="input"],
    #root .st-key-f3_cfg_cuts [data-testid="stNumberInputContainer"] [data-baseweb="input"]{border:none !important;height:100% !important;min-height:0 !important;background:transparent !important;box-shadow:none !important}
    #root .st-key-f3_cfg_general input,#root .st-key-f3_cfg_cuts input,
    #root .st-key-f3_cfg_general [data-baseweb="select"] div,#root .st-key-f3_cfg_cuts [data-baseweb="select"] div,
    #root .st-key-f3_cfg_sector [data-baseweb="select"] div{font-size:13.5px !important;font-weight:800 !important;color:#0b2447 !important}
    #root .st-key-f3_cfg_general input,#root .st-key-f3_cfg_cuts input{padding-left:12px !important;padding-right:4px !important;min-width:0 !important}
    #root .st-key-f3_cfg_general [data-testid="stNumberInputContainer"] button,
    #root .st-key-f3_cfg_cuts [data-testid="stNumberInputContainer"] button{width:24px !important;min-width:24px !important;height:24px !important;
      padding:0 !important;margin:0 3px 0 0 !important;align-self:center !important;border:1px solid #dbe6f3 !important;border-radius:7px !important;
      background:#f8fbff !important;color:#5a6b85 !important}
    /* botón α al pie: .btn.ghost índigo */
    #root .st-key-f3_use_alpha_calc{margin-top:2px !important}
    #root .st-key-f3_use_alpha_calc [data-testid="stButton"] button{width:auto !important;height:auto !important;min-height:38px !important;
      padding:9px 18px !important;border-radius:13px !important;border:1.5px solid #c7d2fe !important;background:#fff !important;
      box-shadow:0 2px 6px rgba(11,36,71,.05) !important}
    #root .st-key-f3_use_alpha_calc [data-testid="stButton"] button p{color:#4f46e5 !important;font-weight:800 !important;font-size:12.5px !important}
    /* "Mostrar probabilidad acumulada" como .chip (on = índigo) */
    #root .st-key-f3_mostrar_cdf{margin-top:2px !important}
    #root .st-key-f3_mostrar_cdf label[data-baseweb="checkbox"]{display:inline-flex !important;align-items:center !important;width:auto !important;
      padding:9px 15px !important;border-radius:999px !important;border:1.5px solid #cfe0f5 !important;background:#fff !important;
      box-shadow:0 2px 6px rgba(11,36,71,.04) !important;cursor:pointer !important;margin:0 !important}
    #root .st-key-f3_mostrar_cdf label[data-baseweb="checkbox"] > span{display:none !important}
    #root .st-key-f3_mostrar_cdf label[data-baseweb="checkbox"] p{font-size:12px !important;font-weight:800 !important;color:#5a6b85 !important;
      text-transform:none !important;letter-spacing:0 !important;margin:0 !important;line-height:1.2 !important}
    #root .st-key-f3_mostrar_cdf label[data-baseweb="checkbox"]:has(input:checked){border-color:#4f46e5 !important;
      background:linear-gradient(120deg,color-mix(in srgb,#4f46e5 13%,#fff),color-mix(in srgb,#4f46e5 6%,#fff)) !important;
      box-shadow:0 6px 14px color-mix(in srgb,#4f46e5 18%,transparent) !important}
    #root .st-key-f3_mostrar_cdf label[data-baseweb="checkbox"]:has(input:checked) p{color:#4f46e5 !important}
    #root .st-key-f3_mostrar_cdf label[data-baseweb="checkbox"]:has(input:checked) p::before{content:"✓ "}
    /* banner info del sector (.banner.info) */
    #root .st-key-f3_cfg_sector .f3-soft-note.f3-aur-banner{display:flex !important;align-items:center !important;gap:12px !important;
      border-radius:15px !important;padding:12px 16px !important;margin:6px 0 0 !important;min-height:0 !important;
      background:linear-gradient(120deg,color-mix(in srgb,#4f46e5 8%,#fff),#fff) !important;border:1.5px solid color-mix(in srgb,#4f46e5 30%,#fff) !important;box-shadow:none !important}
    #root .st-key-f3_cfg_sector .f3-soft-note.f3-aur-banner,#root .st-key-f3_cfg_sector .f3-soft-note.f3-aur-banner *{
      color:#4f46e5 !important;font-weight:800 !important;font-size:12.5px !important;line-height:1.35 !important}
    #root .st-key-f3_cfg_sector .f3-aur-banner .f3-bx{width:36px;height:36px;min-width:36px;border-radius:11px;display:flex;align-items:center;
      justify-content:center;font-size:18px !important;background:rgba(255,255,255,.7)}
    </style>
    """,
    unsafe_allow_html=True,
)

# Override visual puntual: empatar acabado SMA 2.0 para el card del heatmap (Fase 3)
st.markdown(
    """
    <style>
    /* FORZADO: estilo SMA 2.0 para '3. Heatmap de probabilidad para 16 sectores' */
    .st-key-f3_card_rose_v3,
    .st-key-f3_card_sector_v3 {
        min-height: 0 !important;
        box-sizing: border-box !important;
    }

    .st-key-f3_card_rose_v3 div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f3_card_sector_v3 div[data-testid="stVerticalBlockBorderWrapper"] {
        min-height: 0 !important;
        box-sizing: border-box !important;
    }

    .st-key-f3_rose_body_v3,
    .st-key-f3_sector_body_v3 {
        min-height: 0 !important;
        box-sizing: border-box !important;
    }

    .st-key-f3_rose_plot_col_v3 {
        min-height: 0 !important;
    }

    .st-key-f3_sector_plot_wrap_v3 {
        min-height: 0 !important;
    }

    .st-key-f3_card_heatmap {
        border: 1.4px solid #cbd5e1 !important;
        border-radius: 28px !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        overflow: hidden !important;
        box-sizing: border-box !important;
        min-height: 560px !important;
    }

    .st-key-f3_card_heatmap div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        box-shadow: none !important;
        border-radius: 28px !important;
        background: transparent !important;
        overflow: visible !important;
        box-sizing: border-box !important;
        min-height: 560px !important;
    }

    .st-key-f3_card_heatmap [data-testid="stPlotlyChart"] {
        min-height: 470px !important;
    }

    /* ── Botón "Usar α calculado" en header ── */
    .st-key-f3_use_alpha_calc button {
        background: transparent !important;
        border: 1px solid #bfdbfe !important;
        border-radius: 20px !important;
        color: #2563eb !important;
        font-weight: 700 !important;
        font-size: 0.83rem !important;
        padding: 0.26rem 0.85rem !important;
        min-height: 32px !important;
        height: 32px !important;
        box-shadow: none !important;
        width: 100% !important;
    }
    .st-key-f3_use_alpha_calc button:hover {
        background: #eff6ff !important;
        border-color: #93c5fd !important;
        color: #1d4ed8 !important;
    }
    /* Hint text encima del botón alpha */
    .f3-alpha-hint {
        font-size: 0.74rem !important;
        color:#000000 !important;
        font-weight: 400 !important;
        line-height: 1.2 !important;
        margin-bottom: 0.28rem !important;
        text-align: right !important;
    }
    /* Columna derecha del header: alinear contenido a la derecha/centro */
    .st-key-f3_cfg_general > div[data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stHorizontalBlock"]:first-child > div[data-testid="stColumn"]:last-child {
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-end !important;
        justify-content: center !important;
    }

    /* ── Fix: mini-stats en Análisis por sector ── */
    .st-key-f3_sector_mini_frecuencia div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f3_sector_mini_horas div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f3_sector_mini_horas_eq div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f3_sector_mini_k_weibull div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f3_sector_mini_c_weibull div[data-testid="stVerticalBlockBorderWrapper"] {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        min-height: 64px !important;
        padding: 0.55rem 0.6rem !important;
    }
    .st-key-f3_sector_mini_frecuencia div[data-testid="stVerticalBlock"],
    .st-key-f3_sector_mini_horas div[data-testid="stVerticalBlock"],
    .st-key-f3_sector_mini_horas_eq div[data-testid="stVerticalBlock"],
    .st-key-f3_sector_mini_k_weibull div[data-testid="stVerticalBlock"],
    .st-key-f3_sector_mini_c_weibull div[data-testid="stVerticalBlock"] {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 2px !important;
        width: 100% !important;
    }
    .st-key-f3_sector_mini_frecuencia .f3-mini-stat__label,
    .st-key-f3_sector_mini_horas .f3-mini-stat__label,
    .st-key-f3_sector_mini_horas_eq .f3-mini-stat__label,
    .st-key-f3_sector_mini_k_weibull .f3-mini-stat__label,
    .st-key-f3_sector_mini_c_weibull .f3-mini-stat__label,
    .st-key-f3_sector_mini_frecuencia .f3-mini-stat__value,
    .st-key-f3_sector_mini_horas .f3-mini-stat__value,
    .st-key-f3_sector_mini_horas_eq .f3-mini-stat__value,
    .st-key-f3_sector_mini_k_weibull .f3-mini-stat__value,
    .st-key-f3_sector_mini_c_weibull .f3-mini-stat__value {
        transform: none !important;
        text-align: center !important;
        width: 100% !important;
        margin: 0 !important;
    }
    .st-key-f3_sector_mini_frecuencia [data-testid="stMarkdown"],
    .st-key-f3_sector_mini_horas [data-testid="stMarkdown"],
    .st-key-f3_sector_mini_horas_eq [data-testid="stMarkdown"],
    .st-key-f3_sector_mini_k_weibull [data-testid="stMarkdown"],
    .st-key-f3_sector_mini_c_weibull [data-testid="stMarkdown"] {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1 !important;
    }

    /* ── Separación vertical entre cards (fix "contenedores pegados") ── */
    .st-key-f3_card_header,
    .st-key-f3_cfg_general,
    .st-key-f3_cfg_cuts,
    .st-key-f3_cfg_sector,
    .st-key-f3_card_rose_v3,
    .st-key-f3_card_sector_v3,
    .st-key-f3_sector_table_detached,
    .st-key-f3_card_heatmap,
    .st-key-f3_card_expanders {
        margin-bottom: 1.6rem !important;
    }

    /* ── Separación entre las 2 filas de mini-fields de Parámetros generales ── */
    .st-key-f3_pg_altura,
    .st-key-f3_pg_modelo,
    .st-key-f3_pg_vmax,
    .st-key-f3_pg_binwidth {
        margin-bottom: 0.6rem !important;
    }

    /* ── Separación entre el strip de KPIs y la fila de gráficas (rosa|sector) ── */
    .st-key-f3_kpi_1, .st-key-f3_kpi_2, .st-key-f3_kpi_3,
    .st-key-f3_kpi_4, .st-key-f3_kpi_5 {
        margin-bottom: 1.4rem !important;
    }
    /* Resumen sectorial dentro de la card rosa: separarlo del botón y del SVG */
    .st-key-f3_sector_summary {
        margin-top: 0.9rem !important;
    }
    /* ── Separación entre las 2 filas de KPIs del sector (Análisis por sector) ── */
    .st-key-f3_skpi_1, .st-key-f3_skpi_2 {
        margin-bottom: 0.8rem !important;
    }
    /* ── Expanders despegados del heatmap de arriba ── */
    .st-key-f3_card_expanders {
        margin-top: 1.4rem !important;
    }

    </style>
    """,
    unsafe_allow_html=True,
)

df_nasa = cargar_nasa_hourly()
config = cargar_config()
df_curva = cargar_tabla_curva()

if len(df_nasa) == 0:
    st.warning("Todavía no hay datos horarios guardados desde la Fase 2.")
    st.stop()

df_curva_num = _session_cached_result(
    "f3_curva_preparada",
    ("curva", _df_signature(df_curva)),
    lambda: preparar_datos_curva(df_curva),
)
cut_in_inf, nominal_inf, cut_out_inf = inferir_puntos_operacion_curva(df_curva_num)

altura_deseada_default = _config_value(config, "perfil_hhub", ["f2_altura_deseada"], 80.0, caster=float)
modelo_default = normalizar_modelo_altura(_config_value(config, "f3_modelo_altura", ["f35_modelo"], "Exponencial"))
dir_default = _config_value(config, "f3_direccion_fuente", ["f35_direccion_fuente"], "WD50M")
roughness_default = _config_value(config, "f3_roughness_label", ["f35_roughness_label"], "Grass / Césped")
sector_default = _config_value(config, "f3_selected_sector", ["f35_selected_sector"], "N")
vmax_default = _config_value(config, "f3_prob_vmax", ["f35_vmax"], 25.0, caster=float)
bin_width_default = _config_value(config, "f3_prob_bin_width", ["f35_bin_width"], 0.5, caster=float)
show_cdf_default = _bool_config_value(config, "f3_prob_show_cdf", ["f35_show_cdf"], False)
cut_in_default = _config_value(config, "f3_prob_cutin", ["f35_cutin"], cut_in_inf, caster=float)
nominal_default = _config_value(config, "f3_prob_nominal", ["f35_nominal"], nominal_inf, caster=float)
cut_out_default = _config_value(config, "f3_prob_cutout", ["f35_cutout"], cut_out_inf, caster=float)

_init_widget_state("f3_altura_deseada", altura_deseada_default)
_init_widget_state("f3_modelo_altura", modelo_default)
_init_widget_state("f3_direccion_fuente", dir_default)
_init_widget_state("f3_vmax", vmax_default)
_init_widget_state("f3_bin_width", bin_width_default)
_init_widget_state("f3_mostrar_cdf", show_cdf_default)
_init_widget_state("f3_cut_in", cut_in_default)
_init_widget_state("f3_nominal", nominal_default)
_init_widget_state("f3_cut_out", cut_out_default)

altura_deseada = st.session_state.get("f3_altura_deseada", altura_deseada_default)
modelo = st.session_state.get("f3_modelo_altura", modelo_default)
direccion_fuente = st.session_state.get("f3_direccion_fuente", dir_default)
vmax = st.session_state.get("f3_vmax", vmax_default)
bin_width = st.session_state.get("f3_bin_width", bin_width_default)
mostrar_cdf = st.session_state.get("f3_mostrar_cdf", show_cdf_default)
cut_in = st.session_state.get("f3_cut_in", cut_in_default)
nominal = st.session_state.get("f3_nominal", nominal_default)
cut_out = st.session_state.get("f3_cut_out", cut_out_default)
roughness_label = roughness_default

if not (0 <= cut_in < nominal < cut_out):
    st.error("Debe cumplirse: cut-in < nominal < cut-out.")
    st.stop()

try:
    f3_analysis_signature = (
        _df_signature(df_nasa, ["timestamp", "WS10M", "WS50M", "WD10M", "WD50M"]),
        modelo,
        float(altura_deseada),
        roughness_label,
        direccion_fuente,
    )

    def _build_f3_analysis_bundle():
        df_analisis_local, meta_local = construir_viento_analisis(
            df_nasa=df_nasa,
            modelo=modelo,
            altura_deseada=altura_deseada,
            roughness_label=roughness_label,
            direccion_fuente=direccion_fuente,
        )
        df_rosa_local = preparar_datos_rosa(df_analisis_local, ws_col="WS_ANALISIS", wd_col="WD_USADA")
        resumen_local = resumir_sectores_rosa(df_rosa_local, ws_col="WS_ANALISIS").copy()
        resumen_local["Horas observadas (h)"] = resumen_local["Datos"].astype(int)
        resumen_local["Horas equivalentes anuales (h/año)"] = resumen_local["Frecuencia (%)"] / 100.0 * 8760.0
        resumen_local["Calidad Weibull"] = resumen_local["Datos"].apply(calidad_weibull)
        return df_analisis_local, meta_local, df_rosa_local, resumen_local

    df_analisis, meta, df_rosa, resumen = _session_cached_result(
        "f3_analysis_bundle",
        f3_analysis_signature,
        _build_f3_analysis_bundle,
    )
except Exception as e:
    st.error(f"No pude preparar los datos de análisis sectorial: {e}")
    st.stop()

if len(df_rosa) == 0:
    st.warning("No hay registros válidos para la Fase 3.")
    st.stop()

sectores_disponibles = resumen.loc[resumen["Datos"] > 0, "Sector"].tolist()
if not sectores_disponibles:
    st.warning("No hay sectores con datos suficientes.")
    st.stop()
if sector_default not in sectores_disponibles:
    sector_default = sectores_disponibles[0]

_init_widget_state("f3_selected_sector", sector_default)
sector_elegido = st.session_state.get("f3_selected_sector", sector_default)
if sector_elegido not in sectores_disponibles:
    sector_elegido = sector_default
    st.session_state["f3_selected_sector"] = sector_elegido

fila_sector = resumen[resumen["Sector"] == sector_elegido].iloc[0]
df_sector = df_rosa[df_rosa["Sector"] == sector_elegido].copy()
velocidades_sector = df_sector["WS_ANALISIS"].to_numpy(dtype=float)

fig_hist = crear_histograma_sector_con_ajustes(
    velocidades=velocidades_sector,
    sector=sector_elegido,
    k_weibull=fila_sector["k Weibull"],
    c_weibull=fila_sector["c Weibull (m/s)"],
    c_rayleigh=fila_sector["c Rayleigh (m/s)"],
)

fig_heatmap, bins = _session_cached_result(
    "f3_heatmap_result",
    (f3_analysis_signature, float(vmax), float(bin_width)),
    lambda: construir_heatmap_probabilidad(df_rosa, vmax=vmax, bin_width=bin_width),
)
fig_heatmap = go.Figure(fig_heatmap)
fig_sector = crear_figura_sector(
    df_sector=df_sector,
    fila_sector=fila_sector,
    bins=bins,
    mostrar_cdf=mostrar_cdf,
    cut_in=cut_in,
    nominal=nominal,
    cut_out=cut_out,
)
fig_rosa = crear_rosa_vientos_16(resumen)
for trace in fig_rosa.data:
    if hasattr(trace, "showscale"):
        trace.showscale = False
    marker = getattr(trace, "marker", None)
    if marker is not None and hasattr(marker, "showscale"):
        marker.showscale = False

fig_rosa.update_layout(
    title_text="",
    width=500,
    height=500,
    autosize=False,
    margin=dict(t=16, b=22, l=6, r=6),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    coloraxis_showscale=False,
    showlegend=False,
    polar=dict(
        bgcolor="#ffffff",
        radialaxis=dict(tickfont=dict(size=10)),
        angularaxis=dict(tickfont=dict(size=10)),
        domain=dict(x=[0.0, 1.0], y=[0.02, 0.94]),
    ),
)
fig_sector.update_layout(
    width=960,
    height=500,
    autosize=False,
    title=dict(
        text=f"<b>Curva de probabilidad de ocurrencia - Sector {sector_elegido}</b>",
        x=0.5,
        xanchor="center",
        y=0.98,
        yanchor="top",
        pad=dict(t=2, b=12),
        font=dict(size=14, color="#0f172a"),
    ),
    margin=dict(t=78, b=82, l=88, r=14),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="left",
        x=0.0,
        font=dict(size=10),
    ),
)
fig_sector.update_xaxes(title_text="Velocidad del viento (m/s)", title_standoff=10)
fig_sector.update_yaxes(title_text="Probabilidad por intervalo (%)", title_standoff=8)
fig_heatmap.update_layout(
    title=None,
    title_text=None,
    annotations=[],
    height=470,
    autosize=False,
    margin=dict(t=6, b=72, l=52, r=72),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    xaxis=dict(automargin=True),
    yaxis=dict(automargin=True),
    coloraxis_colorbar=dict(
        x=1.03,
        y=0.5,
        len=0.88,
        thickness=14,
        outlinecolor="#d1d9e6",
        outlinewidth=1,
        title=dict(text="<b>Probabilidad (%)</b>", side="top", font=dict(size=11, color="#475569", family="Arial Black, Arial, sans-serif")),
        tickfont=dict(size=10, color="#334155", family="Arial Black, Arial, sans-serif"),
    ),
)
_heatmap_x_labels = [f"{bins[i]:.1f}-{bins[i + 1]:.1f}" for i in range(len(bins) - 1)]
_heatmap_x_ticktext = [f"<b>{lbl}</b>" for lbl in _heatmap_x_labels]
fig_heatmap.update_xaxes(
    title_text="<b>Intervalo de velocidad (m/s)</b>",
    tickangle=-32,
    tickmode="array",
    tickvals=_heatmap_x_labels,
    ticktext=_heatmap_x_ticktext,
    tickfont=dict(size=8, color="#64748b", family="Arial Black, Arial, sans-serif"),
    title_font=dict(size=11, color="#475569", family="Arial Black, Arial, sans-serif"),
    automargin=True,
    showgrid=False,
)
fig_heatmap.update_yaxes(
    title_text="<b>Sector</b>",
    tickfont=dict(size=10, color="#64748b", family="Arial Black, Arial, sans-serif"),
    title_font=dict(size=11, color="#475569", family="Arial Black, Arial, sans-serif"),
    automargin=True,
    showgrid=False,
)
_sector_labels = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
fig_heatmap.update_yaxes(tickmode="array", tickvals=_sector_labels, ticktext=[f"<b>{s}</b>" for s in _sector_labels])
fig_heatmap.update_traces(
    colorbar=dict(
        title=dict(
            text="<b>Probabilidad (%)</b>",
            side="top",
            font=dict(size=10, color="#475569", family="Arial Black, Arial, sans-serif"),
        ),
        thickness=16,
        len=0.84,
        x=1.01,
        y=0.50,
        tickfont=dict(size=9, color="#64748b", family="Arial Black, Arial, sans-serif"),
        outlinewidth=0,
    )
)

tabla_intervalos = crear_tabla_probabilidades_intervalos(
    df_sector=df_sector,
    fila_sector=fila_sector,
    vmax=vmax,
    bin_width=bin_width,
)
tabla_operacion = crear_tabla_operacion(
    df_sector=df_sector,
    fila_sector=fila_sector,
    cut_in=cut_in,
    nominal=nominal,
    cut_out=cut_out,
)
kpi_items = [
    ("🧾", "Registros válidos", f"{len(df_rosa):,}".replace(",", "."), "tras filtros", "#2563eb"),
    ("💨", "Velocidad media", f"{df_rosa['WS_ANALISIS'].mean():.2f} m/s".replace(".", ","), "serie completa", "#4f46e5"),
    ("🎯", "Sectores con datos", f"{int((resumen['Datos'] > 0).sum())} / 16", "rosa completa", "#16a34a"),
    ("📐", "Modelo", modelo, "perfil activo", "#0e7490"),
    ("α", "Alpha promedio", str(_extract_alpha_promedio(meta)).replace(".", ","), "de la Fase 2", "#d97706"),
]
if "f3_show_sector_table" not in st.session_state:
    st.session_state["f3_show_sector_table"] = False

_n_sec_dato = int((resumen["Datos"] > 0).sum())
_v_med_hero = float(df_rosa["WS_ANALISIS"].mean())
try:
    _sec_dom = str(resumen.loc[resumen["Frecuencia (%)"].idxmax(), "Sector"])
except Exception:
    _sec_dom = "—"
_v_med_txt = f"{_v_med_hero:.2f}".replace(".", ",")

with _phase_card("f3_card_header"):
    st.markdown(
        f"""
        <div class="f3-hero">
            <svg class="f3-wind" viewBox="0 0 600 190" preserveAspectRatio="none">
                <path d="M0 42 Q150 24 300 44 T600 34"/>
                <path d="M0 100 Q180 82 340 102 T600 92"/>
                <path d="M0 156 Q140 142 300 158 T600 150"/>
            </svg>
            <div class="f3-hero-row">
                <div class="f3-hero-icon">🧭</div>
                <div class="f3-hero-text">
                    <div class="f3-hero-title">Fase 3 · Rosa y velocidad promedio</div>
                    <div class="f3-hero-subtitle">Caracterización direccional del viento y probabilidad de ocurrencia por sector.</div>
                </div>
                <div class="f3-hero-pills">
                    <div class="f3-hpill"><b>{_n_sec_dato}/16</b><span>Sectores</span></div>
                    <div class="f3-hpill"><b>{_v_med_txt} m/s</b><span>V</span></div>
                    <div class="f3-hpill"><b>{_sec_dom}</b><span>Dominante</span></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Pre-compute alpha button state for header
_alpha_calc_med = config.get("f2_alpha_calc_mediana", "")
_alpha_show = False
_alpha_val = None
_alpha_hint = ""
if _alpha_calc_med and str(_alpha_calc_med).strip():
    try:
        _alpha_val = float(_alpha_calc_med)
        _alpha_p25 = config.get("f2_alpha_calc_p25", "")
        _alpha_p75 = config.get("f2_alpha_calc_p75", "")
        _alpha_hint = f"α calc. (Fase 2): {_alpha_val:.3f}"
        if _alpha_p25 and _alpha_p75:
            _alpha_hint += f" (IQR {float(_alpha_p25):.3f}–{float(_alpha_p75):.3f})"
        _alpha_show = True
    except (TypeError, ValueError):
        pass

config_cols = st.columns([1.0, 1.0, 1.0], gap="small")
with config_cols[0]:
    with _phase_card("f3_cfg_general"):
        _render_card_header_native("Parámetros generales", "🎛️", "Altura, modelo y discretización")
        if True:
            g1, g2 = st.columns(2, gap="small")
            with g1:
                with st.container(border=True, key="f3_pg_altura"):
                    st.markdown('<div class="f3-pg-custom-label">Altura (m)</div>', unsafe_allow_html=True)
                    altura_deseada = st.number_input(
                        "Altura (m)",
                        min_value=0.10,
                        step=0.10,
                        format="%.2f",
                        key="f3_altura_deseada",
                        label_visibility="collapsed",
                    )
            with g2:
                with st.container(border=True, key="f3_pg_modelo"):
                    st.markdown('<div class="f3-pg-custom-label">Modelo</div>', unsafe_allow_html=True)
                    modelo = st.selectbox(
                        "Modelo",
                        MODEL_OPTIONS,
                        index=_safe_index(MODEL_OPTIONS, st.session_state.get("f3_modelo_altura", modelo_default), 2),
                        key="f3_modelo_altura",
                        label_visibility="collapsed",
                    )
            g3, g4 = st.columns(2, gap="small")
            with g3:
                with st.container(border=True, key="f3_pg_vmax"):
                    st.markdown('<div class="f3-pg-custom-label">V. máx. análisis (m/s)</div>', unsafe_allow_html=True)
                    vmax = st.number_input(
                        "V. máx. análisis (m/s)",
                        min_value=5.0,
                        step=1.0,
                        format="%.2f",
                        key="f3_vmax",
                        label_visibility="collapsed",
                    )
            with g4:
                with st.container(border=True, key="f3_pg_binwidth"):
                    st.markdown('<div class="f3-pg-custom-label">Ancho de intervalo (m/s)</div>', unsafe_allow_html=True)
                    bin_width = st.number_input(
                        "Ancho de intervalo (m/s)",
                        min_value=0.25,
                        step=0.25,
                        format="%.2f",
                        key="f3_bin_width",
                        label_visibility="collapsed",
                    )
            if _alpha_show:
                if st.button("α  Usar α calculado", key="f3_use_alpha_calc", help=_alpha_hint or None):
                    guardar_config_values({"perfil_alpha": _alpha_val, "perfil_alpha_usuario": _alpha_val})
                    st.success(f"α actualizado a {_alpha_val:.3f}. Recarga la fase para ver el efecto.")
                    st.rerun()

with config_cols[1]:
    with _phase_card("f3_cfg_cuts"):
        _render_card_header_native("Dirección y cortes", "🧭", "Sectores y ventana de operación")
        if True:
            direccion_fuente = st.selectbox(
                "Dirección usada",
                DIRECTION_OPTIONS,
                index=_safe_index(DIRECTION_OPTIONS, st.session_state.get("f3_direccion_fuente", dir_default), 0),
                key="f3_direccion_fuente",
            )
            cuts1, cuts2, cuts3 = st.columns(3, gap="small")
            with cuts1:
                st.markdown('<div class="f3-cut-field-label">Cut-in (m/s)</div>', unsafe_allow_html=True)
                cut_in = st.number_input(
                    "Cut-in (m/s)",
                    min_value=0.0,
                    step=0.5,
                    format="%.1f",
                    key="f3_cut_in",
                    label_visibility="collapsed",
                )
            with cuts2:
                st.markdown('<div class="f3-cut-field-label">Nominal (m/s)</div>', unsafe_allow_html=True)
                nominal = st.number_input(
                    "Velocidad nominal (m/s)",
                    min_value=0.0,
                    step=0.5,
                    format="%.1f",
                    key="f3_nominal",
                    label_visibility="collapsed",
                )
            with cuts3:
                st.markdown('<div class="f3-cut-field-label">Cut-out (m/s)</div>', unsafe_allow_html=True)
                cut_out = st.number_input(
                    "Cut-out (m/s)",
                    min_value=0.0,
                    step=0.5,
                    format="%.1f",
                    key="f3_cut_out",
                    label_visibility="collapsed",
                )
            mostrar_cdf = st.checkbox(
                "Mostrar probabilidad acumulada",
                key="f3_mostrar_cdf",
            )

with config_cols[2]:
    with _phase_card("f3_cfg_sector"):
        _render_card_header_native("Sector", "🎯", "Análisis individual")
        sector_elegido = st.selectbox(
            "Seleccionar sector",
            sectores_disponibles,
            index=sectores_disponibles.index(sector_default),
            key="f3_selected_sector",
        )
        st.markdown(
            '<div class="f3-soft-note f3-aur-banner"><span class="f3-bx">ℹ️</span>'
            '<div>La curva y tablas usan el ancho de intervalo elegido</div></div>',
            unsafe_allow_html=True,
        )

guardar_config_values({
    "f3_modelo_altura": modelo,
    "f3_direccion_fuente": direccion_fuente,
    "f3_roughness_label": roughness_label,
    "f3_selected_sector": st.session_state.get("f3_selected_sector", sector_default),
    "f3_prob_vmax": vmax,
    "f3_prob_bin_width": bin_width,
    "f3_prob_show_cdf": mostrar_cdf,
    "f3_prob_cutin": cut_in,
    "f3_prob_nominal": nominal,
    "f3_prob_cutout": cut_out,
})

kpi_cols = st.columns(5, gap="small")
for idx, ((icon_name, label, value, sub, kc), col) in enumerate(zip(kpi_items, kpi_cols), start=1):
    with col:
        with _phase_card(f"f3_kpi_{idx}"):
            _render_kpi_card_native(icon_name, label, value, sub, kc)

if MOSTRAR_HISTOGRAMA_SUPERIOR:
    st.plotly_chart(fig_hist, use_container_width=True, config=PLOTLY_PERF_CONFIG)

top_cols = st.columns([1.03, 1.03], gap="small")
with top_cols[0]:
    with st.container(border=True, key="f3_card_rose_v3"):
        _render_card_header_native("1 · Rosa de vientos", "🌹", "Frecuencia por dirección — 16 sectores")
        with st.container(key="f3_rose_body_v3"):
            with st.container(key="f3_rose_plot_col_v3"):
                components.html(render_rosa_svg(resumen), height=500, scrolling=False)
            with st.container(border=True, key="f3_sector_summary"):
                _render_summary_sector_native(resumen, direccion_fuente)
            if st.button(
                "▦  Ver tabla sectorial",
                key="f3_btn_toggle_sector_table",
                use_container_width=True,
            ):
                st.session_state["f3_show_sector_table"] = not st.session_state["f3_show_sector_table"]

with top_cols[1]:
    with st.container(border=True, key="f3_card_sector_v3"):
        _render_card_header_native(f"2 · Análisis por sector ({fila_sector['Sector']})", "📊", "Weibull y Rayleigh con líneas de operación")
        with st.container(key="f3_sector_body_v3"):
            with st.container(key="f3_sector_stats_row_v3"):
                _ha_txt = f"{fila_sector['Horas equivalentes anuales (h/año)']:,.0f}".replace(",", ".")
                sec_kpis = [
                    ("📊", "Frecuencia", f"{fila_sector['Frecuencia (%)']:.1f} %".replace(".", ","), "", "#4f46e5"),
                    ("⏱️", "Horas/año", f"{_ha_txt} h", "equivalentes", "#0e7490"),
                    ("k", "k Weibull", f"{fila_sector['k Weibull']:.2f}".replace(".", ","), "", "#16a34a"),
                    ("c", "c Weibull", f"{fila_sector['c Weibull (m/s)']:.1f} m/s".replace(".", ","), "", "#d97706"),
                ]
                _srow1 = st.columns(2, gap="small")
                _srow2 = st.columns(2, gap="small")
                _scells = [_srow1[0], _srow1[1], _srow2[0], _srow2[1]]
                for idx, (col, (emo, label, value, sub, kc)) in enumerate(zip(_scells, sec_kpis), 1):
                    with col:
                        with _phase_card(f"f3_skpi_{idx}"):
                            _render_kpi_card_native(emo, label, value, sub, kc)
            with st.container(key="f3_sector_plot_wrap_v3"):
                _f3_centers, _f3_pw, _f3_pr = _sector_curve_arrays(df_sector, fila_sector, bins)
                components.html(
                    render_sector_curve_svg(_f3_centers, _f3_pw, _f3_pr, cut_in, nominal, cut_out, vmax, H=547),
                    height=505, scrolling=False,
                )
                st.markdown(
                    '<div class="aur-legend">'
                    '<i style="--lc:#4f46e5">Histograma + Weibull</i>'
                    '<i style="--lc:#f97316">Rayleigh</i>'
                    '<i style="--lc:#94a3b8">Cut-in / Nominal / Cut-out</i>'
                    '</div>',
                    unsafe_allow_html=True,
                )

if st.session_state.get("f3_show_sector_table", False):
    with _phase_card("f3_sector_table_detached"):
        st.markdown('<div class="f3-sector-table-title">Tabla sectorial</div>', unsafe_allow_html=True)
        _render_dataframe_safe(
            resumen,
            {
                "Centro (°)": "%.1f",
                "Inicio (°)": "%.1f",
                "Fin (°)": "%.1f",
                "Frecuencia (%)": "%.2f",
                "Horas equivalentes anuales (h/año)": "%.2f",
                "Velocidad media (m/s)": "%.2f",
                "Desv. estándar (m/s)": "%.2f",
                "k Weibull": "%.4f",
                "c Weibull (m/s)": "%.4f",
                "c Rayleigh (m/s)": "%.4f",
            },
            use_container_width=True,
        )

with _phase_card("f3_card_heatmap"):
    st.markdown(
        '',
        unsafe_allow_html=True,
    )
    _render_card_header_native("3 · Heatmap de probabilidad para 16 sectores", "🔥", "Probabilidad (%) por sector e intervalo de velocidad — toda la rosa de un vistazo")
    st.markdown('<div class="f3-heatmap-top-spacer"></div>', unsafe_allow_html=True)
    _f3_hmat = _heatmap_matrix(df_rosa, bins)
    components.html(
        render_heatmap_svg(_f3_hmat[::-1], list(SECTOR_LABELS_16)[::-1], bins),
        height=460, scrolling=False,
    )
    st.markdown(
        '<div class="aur-legend">'
        '<i style="--lc:#fdebcf">Baja probabilidad</i>'
        '<i style="--lc:#f59e42">Media</i>'
        '<i style="--lc:#d7301f">Alta (&gt;20%)</i>'
        '</div>',
        unsafe_allow_html=True,
    )

with _phase_card("f3_card_expanders"):
    with st.expander(_expander_icon_label("table-intervals", "Ver tabla de probabilidades por intervalos"), expanded=False):
        _render_dataframe_safe(
            tabla_intervalos,
            {
                "Probabilidad real (%)": "%.2f",
                "Probabilidad Weibull (%)": "%.2f",
                "Probabilidad Rayleigh (%)": "%.2f",
            },
            use_container_width=True,
        )
    with st.expander(_expander_icon_label("table-zones", "Ver tabla de probabilidades por zona de operación del aerogenerador"), expanded=False):
        _render_dataframe_safe(
            tabla_operacion,
            {
                "Probabilidad real (%)": "%.2f",
                "Probabilidad Weibull (%)": "%.2f",
                "Probabilidad Rayleigh (%)": "%.2f",
            },
            use_container_width=True,
        )
    with st.expander(_expander_icon_label("table-hourly", "Ver datos horarios usados en la Fase 3"), expanded=False):
        mostrar = df_rosa[["timestamp", "WS_ANALISIS", "WD_USADA", "Sector"]].copy()
        mostrar.columns = ["timestamp", "Velocidad usada (m/s)", "Dirección usada (°)", "Sector"]
        _render_dataframe_safe(
            mostrar,
            {
                "Velocidad usada (m/s)": "%.2f",
                "Dirección usada (°)": "%.2f",
            },
            use_container_width=True,
        )

render_dropdown_visibility_fix()
st.stop()
