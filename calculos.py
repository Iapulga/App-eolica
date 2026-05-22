import io
import csv
import json
import re
import random
from math import gamma
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

KAPPA = 0.4

SECTOR_LABELS_16 = [
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW"
]
SECTOR_CENTERS_16 = np.arange(0.0, 360.0, 22.5)

ROUGHNESS_OPTIONS_DEFAULT = {
    "Water / Mar": 2e-4,
    "Snow / Nieve": 1e-3,
    "Grass / Césped": 0.03,
    "Farmland / Cultivo": 0.10,
    "Forest / Bosque": 0.80,
    "City / Ciudad": 1.00,
}

LEGACY_LOG_B_LABEL = "Log B (z0 teÃ³rica)"
PROMEDIO_LOG_EXP_LABEL = "Promedio Log-Exp"


def normalizar_modelo_altura(modelo):
    value = str(modelo or "").strip()
    if value == LEGACY_LOG_B_LABEL:
        return PROMEDIO_LOG_EXP_LABEL
    return value

def convertir_a_numero(serie):
    return pd.to_numeric(
        serie.astype(str).str.strip().str.replace(",", ".", regex=False),
        errors="coerce"
    )


@st.cache_data(show_spinner=False)
def preparar_datos_curva(df_raw):
    df_calc = df_raw.copy()

    df_calc["Velocidad_num"] = convertir_a_numero(df_calc["Velocidad (m/s)"])
    df_calc["Potencia_W"] = convertir_a_numero(df_calc["Potencia (W)"])

    df_calc = df_calc.dropna(subset=["Velocidad_num", "Potencia_W"]).copy()
    df_calc = df_calc[
        (df_calc["Velocidad_num"] >= 0) &
        (df_calc["Potencia_W"] >= 0)
    ].copy()

    df_calc = df_calc.sort_values("Velocidad_num").reset_index(drop=True)
    return df_calc


def inferir_puntos_operacion_curva(df_curva):
    if len(df_curva) == 0:
        return 3.0, 12.0, 25.0

    potencia_max = float(df_curva["Potencia_W"].max()) if len(df_curva) > 0 else 0.0

    positivos = df_curva[df_curva["Potencia_W"] > 0].copy()
    if len(positivos) > 0:
        cut_in = float(positivos["Velocidad_num"].iloc[0])
    else:
        cut_in = 3.0

    if potencia_max > 0:
        nominal_rows = df_curva[df_curva["Potencia_W"] >= 0.98 * potencia_max].copy()
        if len(nominal_rows) > 0:
            nominal = float(nominal_rows["Velocidad_num"].iloc[0])
        else:
            nominal = 12.0
    else:
        nominal = 12.0

    cut_out = float(df_curva["Velocidad_num"].max()) if len(df_curva) > 0 else 25.0

    if nominal < cut_in:
        nominal = cut_in + 1.0
    if cut_out <= nominal:
        cut_out = nominal + 1.0

    return cut_in, nominal, cut_out


@st.cache_data(show_spinner=False)
def interpolar_potencia_curva_preparada(curva_df, velocidades):
    xs = curva_df["Velocidad_num"].to_numpy(dtype=float)
    ys = curva_df["Potencia_W"].to_numpy(dtype=float)
    vel = np.asarray(velocidades, dtype=float)

    if len(xs) == 0:
        return np.zeros_like(vel, dtype=float)

    return np.interp(
        vel,
        xs,
        ys,
        left=0.0,
        right=float(ys[-1])
    )


@st.cache_data(show_spinner=False)
def calcular_cp(df_calc, densidad, area):
    df_calc = df_calc.copy()

    v = df_calc["Velocidad_num"].to_numpy()
    p_w = df_calc["Potencia_W"].to_numpy()

    p_viento_w = 0.5 * densidad * (v ** 3) * area
    cp = np.where(p_viento_w > 0, p_w / p_viento_w, np.nan)

    df_calc["P_viento_W"] = p_viento_w
    df_calc["Cp"] = cp
    return df_calc


@st.cache_data(show_spinner=False)
def crear_grafica_curva(df_resultados):
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    if len(df_resultados) > 0:
        fig.add_trace(
            go.Bar(
                x=df_resultados["Velocidad_num"],
                y=df_resultados["Potencia_W"],
                base=0,
                name="Potencia",
                marker_color="#7fb3c4",
                hovertemplate=(
                    "Velocidad: %{x:.2f} m/s<br>"
                    "Potencia: %{y:.2f} W"
                    "<extra></extra>"
                ),
            ),
            secondary_y=False,
        )

        fig.add_trace(
            go.Scatter(
                x=df_resultados["Velocidad_num"],
                y=df_resultados["Cp"],
                name="Cp",
                mode="markers",
                marker=dict(color="red", size=8, symbol="circle"),
                hovertemplate=(
                    "Velocidad: %{x:.2f} m/s<br>"
                    "Cp: %{y:.4f}"
                    "<extra></extra>"
                ),
            ),
            secondary_y=True,
        )

    if len(df_resultados) > 0:
        pmax_w = max(float(df_resultados["Potencia_W"].max()), 1.0)
        cp_validos = df_resultados["Cp"].replace([np.inf, -np.inf], np.nan).dropna()
        cpmax = float(cp_validos.max()) if len(cp_validos) > 0 else 0.30
        cpmax_plot = max(0.30, np.ceil(cpmax / 0.05) * 0.05 + 0.05)
        xmax = max(float(df_resultados["Velocidad_num"].max()), 1.0)
    else:
        pmax_w = 1.0
        cpmax_plot = 0.30
        xmax = 1.0

    fig.update_layout(
        template="plotly_white",
        height=620,
        width=980,
        bargap=0.20,
        margin=dict(l=40, r=40, t=30, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
    )

    fig.update_xaxes(
        title_text="Velocidad del viento (m/s)",
        showgrid=True,
        gridcolor="lightgray",
        zeroline=True,
        zerolinecolor="gray",
        range=[0, xmax + 1],
    )

    fig.update_yaxes(
        title_text="Potencia (W)",
        secondary_y=False,
        showgrid=True,
        gridcolor="lightgray",
        zeroline=True,
        zerolinecolor="gray",
        rangemode="tozero",
        range=[0, pmax_w * 1.10],
    )

    fig.update_yaxes(
        title_text="Cp",
        secondary_y=True,
        showgrid=False,
        zeroline=True,
        zerolinecolor="gray",
        rangemode="tozero",
        range=[0, cpmax_plot],
        tick0=0,
        dtick=0.05,
        tickformat=".2f",
    )

    return fig


def calcular_alpha_desde_dos_alturas(v1, z1, v2, z2):
    if v1 <= 0 or v2 <= 0:
        raise ValueError("Las velocidades deben ser mayores que 0 para calcular alpha.")

    if z1 <= 0 or z2 <= 0 or z1 == z2:
        raise ValueError("Las alturas deben ser positivas y diferentes.")

    return np.log(v2 / v1) / np.log(z2 / z1)


def ajustar_logaritmico_dos_puntos(v1, z1, v2, z2, kappa=KAPPA):
    z1 = float(z1)
    z2 = float(z2)

    if z1 <= 0 or z2 <= 0 or z1 == z2:
        raise ValueError("Las alturas deben ser positivas y diferentes.")

    ln_ratio = np.log(z2 / z1)
    if abs(ln_ratio) < 1e-12:
        raise ValueError("No se puede calcular el ajuste logarítmico.")

    v1_arr = np.asarray(v1, dtype=float)
    v2_arr = np.asarray(v2, dtype=float)

    du = v2_arr - v1_arr
    mask = (v1_arr > 0) & (v2_arr > 0) & (du > 0)

    u_star = np.where(mask, kappa * du / ln_ratio, np.nan)
    z0 = np.where(
        np.isfinite(u_star) & (u_star > 0),
        z1 * np.exp(-(kappa * v1_arr) / u_star),
        np.nan
    )

    if np.ndim(v1_arr) == 0 and np.ndim(v2_arr) == 0:
        return float(u_star), float(z0)

    return u_star, z0


def extrapolar_exponencial_dos_puntos(v1, z1, v2, z2, z_obj):
    z1 = float(z1)
    z2 = float(z2)
    z_obj = float(z_obj)

    if z1 <= 0 or z2 <= 0 or z_obj <= 0 or z1 == z2:
        raise ValueError("Las alturas deben ser positivas y diferentes.")

    v1_arr = np.asarray(v1, dtype=float)
    v2_arr = np.asarray(v2, dtype=float)

    mask = (v1_arr > 0) & (v2_arr > 0)
    alpha = np.where(mask, np.log(v2_arr / v1_arr) / np.log(z2 / z1), np.nan)
    v_obj = np.where(np.isfinite(alpha), v1_arr * (z_obj / z1) ** alpha, np.nan)

    if np.ndim(v1_arr) == 0 and np.ndim(v2_arr) == 0:
        return float(v_obj), float(alpha)

    return v_obj, alpha


def extrapolar_logaritmico_dos_puntos(v1, z1, v2, z2, z_obj, kappa=KAPPA):
    z_obj = float(z_obj)

    u_star, z0 = ajustar_logaritmico_dos_puntos(v1, z1, v2, z2, kappa=kappa)

    u_star_arr = np.asarray(u_star, dtype=float)
    z0_arr = np.asarray(z0, dtype=float)

    mask = np.isfinite(u_star_arr) & np.isfinite(z0_arr) & (u_star_arr > 0) & (z_obj > z0_arr)
    v_obj = np.where(mask, (u_star_arr / kappa) * np.log(z_obj / z0_arr), np.nan)

    if np.ndim(u_star_arr) == 0 and np.ndim(z0_arr) == 0:
        return float(v_obj), float(u_star_arr), float(z0_arr)

    return v_obj, u_star_arr, z0_arr


def calcular_velocidad_friccion(v_ref, h_ref, z0, kappa=KAPPA):
    if z0 <= 0:
        raise ValueError("z0 debe ser mayor que 0.")
    if h_ref <= z0:
        raise ValueError("La altura de referencia debe ser mayor que z0.")
    if v_ref < 0:
        raise ValueError("La velocidad de referencia no puede ser negativa.")

    return kappa * v_ref / np.log(h_ref / z0)


def calcular_perfil_exponencial(v_ref, h_ref, alpha, alturas):
    alturas = np.array(alturas, dtype=float)
    velocidades = v_ref * (alturas / h_ref) ** alpha

    return pd.DataFrame({
        "Altura (m)": alturas,
        "Velocidad (m/s)": velocidades
    })


def calcular_perfil_logaritmico(u_star, z0, alturas, kappa=KAPPA):
    alturas = np.array(alturas, dtype=float)

    if z0 <= 0:
        raise ValueError("z0 debe ser mayor que 0.")

    alturas_validas = np.maximum(alturas, z0 + 1e-6)
    velocidades = (u_star / kappa) * np.log(alturas_validas / z0)

    return pd.DataFrame({
        "Altura (m)": alturas,
        "Velocidad (m/s)": velocidades
    })


def velocidad_logaritmica_en_altura(u_star, z, z0, kappa=KAPPA):
    if z0 <= 0:
        raise ValueError("z0 debe ser mayor que 0.")
    if z <= z0:
        raise ValueError("La altura debe ser mayor que z0.")

    return (u_star / kappa) * np.log(z / z0)


@st.cache_data(show_spinner=False)
def crear_grafica_perfil_individual(
    df_perfil,
    titulo,
    nombre_traza,
    altura_objetivo=None,
    v_objetivo=None,
    color="#3366ff",
    dash=None,
    yaxis_type="linear",
    puntos_medidos=None,
):
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df_perfil["Velocidad (m/s)"],
            y=df_perfil["Altura (m)"],
            mode="lines",
            name=nombre_traza,
            line=dict(width=3, color=color, dash=dash),
            hovertemplate=(
                f"{nombre_traza}<br>"
                "Velocidad: %{x:.2f} m/s<br>"
                "Altura: %{y:.2f} m"
                "<extra></extra>"
            ),
        )
    )

    if puntos_medidos:
        xs = [p["velocidad"] for p in puntos_medidos]
        ys = [p["altura"] for p in puntos_medidos]
        textos = [p["etiqueta"] for p in puntos_medidos]

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                name="Puntos medidos",
                marker=dict(size=10, color="black"),
                text=textos,
                hovertemplate=(
                    "%{text}<br>"
                    "Velocidad: %{x:.2f} m/s<br>"
                    "Altura: %{y:.2f} m"
                    "<extra></extra>"
                ),
            )
        )

    if altura_objetivo is not None:
        fig.add_hline(
            y=float(altura_objetivo),
            line_dash="dot",
            line_color="gray"
        )

    if altura_objetivo is not None and v_objetivo is not None:
        fig.add_trace(
            go.Scatter(
                x=[v_objetivo],
                y=[altura_objetivo],
                mode="markers",
                name="Punto objetivo",
                marker=dict(size=10, color=color),
                hovertemplate=(
                    "Velocidad: %{x:.2f} m/s<br>"
                    "Altura objetivo: %{y:.2f} m"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=titulo,
        template="plotly_white",
        height=560,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        )
    )

    fig.update_xaxes(title_text="Velocidad del viento (m/s)")
    fig.update_yaxes(title_text="Altura (m)", type=yaxis_type)

    return fig


@st.cache_data(show_spinner=False)
def crear_grafica_perfiles_comparados(
    df_exp,
    df_log,
    altura_objetivo=None,
    v_exp=None,
    v_log=None,
    puntos_medidos=None,
):
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(
            "Comparación en escala lineal",
            "Comparación con escala logarítmica en altura"
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df_exp["Velocidad (m/s)"],
            y=df_exp["Altura (m)"],
            mode="lines",
            name="Perfil exponencial",
            line=dict(width=3, color="#3366ff"),
        ),
        row=1,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=df_log["Velocidad (m/s)"],
            y=df_log["Altura (m)"],
            mode="lines",
            name="Perfil logarítmico",
            line=dict(width=3, color="#ff5533", dash="dash"),
        ),
        row=1,
        col=1
    )

    fig.add_trace(
        go.Scatter(
            x=df_exp["Velocidad (m/s)"],
            y=df_exp["Altura (m)"],
            mode="lines",
            name="Perfil exponencial (log-y)",
            line=dict(width=3, color="#3366ff"),
            showlegend=False,
        ),
        row=1,
        col=2
    )

    fig.add_trace(
        go.Scatter(
            x=df_log["Velocidad (m/s)"],
            y=df_log["Altura (m)"],
            mode="lines",
            name="Perfil logarítmico (log-y)",
            line=dict(width=3, color="#ff5533", dash="dash"),
            showlegend=False,
        ),
        row=1,
        col=2
    )

    if puntos_medidos:
        xs = [p["velocidad"] for p in puntos_medidos]
        ys = [p["altura"] for p in puntos_medidos]
        textos = [p["etiqueta"] for p in puntos_medidos]

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                name="Puntos medidos",
                marker=dict(size=10, color="black"),
                text=textos,
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                name="Puntos medidos (log-y)",
                marker=dict(size=10, color="black"),
                text=textos,
                showlegend=False,
            ),
            row=1,
            col=2
        )

    if altura_objetivo is not None:
        fig.add_hline(y=float(altura_objetivo), line_dash="dot", line_color="gray", row=1, col=1)
        fig.add_hline(y=float(altura_objetivo), line_dash="dot", line_color="gray", row=1, col=2)

    if altura_objetivo is not None and v_exp is not None:
        fig.add_trace(
            go.Scatter(
                x=[v_exp],
                y=[altura_objetivo],
                mode="markers",
                name="Punto exp.",
                marker=dict(size=9, color="#00b894"),
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=[v_exp],
                y=[altura_objetivo],
                mode="markers",
                name="Punto exp. (log-y)",
                marker=dict(size=9, color="#00b894"),
                showlegend=False,
            ),
            row=1,
            col=2
        )

    if altura_objetivo is not None and v_log is not None:
        fig.add_trace(
            go.Scatter(
                x=[v_log],
                y=[altura_objetivo],
                mode="markers",
                name="Punto log.",
                marker=dict(size=9, color="#8e63ff", symbol="diamond"),
            ),
            row=1,
            col=1
        )

        fig.add_trace(
            go.Scatter(
                x=[v_log],
                y=[altura_objetivo],
                mode="markers",
                name="Punto log. (log-y)",
                marker=dict(size=9, color="#8e63ff", symbol="diamond"),
                showlegend=False,
            ),
            row=1,
            col=2
        )

    fig.update_layout(
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        )
    )

    fig.update_xaxes(title_text="Velocidad del viento (m/s)", row=1, col=1)
    fig.update_yaxes(title_text="Altura (m)", row=1, col=1)

    fig.update_xaxes(title_text="Velocidad del viento (m/s)", row=1, col=2)
    fig.update_yaxes(title_text="Altura (m) - escala log", type="log", row=1, col=2)

    return fig


@st.cache_data(show_spinner=False)
def preparar_datos_rosa(df_nasa, ws_col="WS50M", wd_col="WD50M"):
    df = df_nasa.copy()

    if ws_col not in df.columns or wd_col not in df.columns:
        raise ValueError(f"No existen las columnas {ws_col} y/o {wd_col} en la tabla.")

    df[ws_col] = pd.to_numeric(df[ws_col], errors="coerce")
    df[wd_col] = pd.to_numeric(df[wd_col], errors="coerce")

    df = df.dropna(subset=[ws_col, wd_col]).copy()
    df = df[df[ws_col] >= 0].copy()

    df["Direccion_360"] = df[wd_col] % 360.0
    df["Sector_idx"] = (((df["Direccion_360"] + 11.25) % 360.0) // 22.5).astype(int)
    df["Sector"] = df["Sector_idx"].map(lambda i: SECTOR_LABELS_16[int(i)])
    df["Centro_deg"] = df["Sector_idx"].map(lambda i: float(SECTOR_CENTERS_16[int(i)]))

    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def ajustar_weibull_por_momentos(velocidades):
    v = np.asarray(velocidades, dtype=float)
    v = v[np.isfinite(v) & (v > 0)]

    if len(v) < 2:
        return np.nan, np.nan

    media = float(np.mean(v))
    sigma = float(np.std(v, ddof=1))

    if media <= 0:
        return np.nan, np.nan

    if sigma <= 0:
        k = 10.0
        c = media / gamma(1.0 + 1.0 / k)
        return float(k), float(c)

    k = (sigma / media) ** (-1.086)
    k = float(np.clip(k, 0.1, 20.0))
    c = media / gamma(1.0 + 1.0 / k)

    return float(k), float(c)


@st.cache_data(show_spinner=False)
def ajustar_rayleigh_desde_media(velocidades):
    v = np.asarray(velocidades, dtype=float)
    v = v[np.isfinite(v) & (v >= 0)]

    if len(v) == 0:
        return np.nan

    media = float(np.mean(v))
    if media <= 0:
        return np.nan

    c = media / gamma(1.0 + 1.0 / 2.0)
    return float(c)


@st.cache_data(show_spinner=False)
def resumir_sectores_rosa(df_rosa, ws_col="WS50M"):
    total = len(df_rosa)
    filas = []

    for idx, label in enumerate(SECTOR_LABELS_16):
        sub = df_rosa[df_rosa["Sector_idx"] == idx].copy()
        velocidades = sub[ws_col].dropna().to_numpy(dtype=float)

        n = len(velocidades)
        freq = (n / total * 100.0) if total > 0 else 0.0

        media = float(np.mean(velocidades)) if n > 0 else np.nan
        std = float(np.std(velocidades, ddof=1)) if n > 1 else np.nan

        k_weibull, c_weibull = ajustar_weibull_por_momentos(velocidades)
        c_rayleigh = ajustar_rayleigh_desde_media(velocidades)

        centro = float(SECTOR_CENTERS_16[idx])
        inicio = (centro - 11.25) % 360.0
        fin = (centro + 11.25) % 360.0

        filas.append({
            "Sector": label,
            "Centro (°)": centro,
            "Inicio (°)": inicio,
            "Fin (°)": fin,
            "Datos": n,
            "Frecuencia (%)": freq,
            "Velocidad media (m/s)": media,
            "Desv. estándar (m/s)": std,
            "k Weibull": k_weibull,
            "c Weibull (m/s)": c_weibull,
            "c Rayleigh (m/s)": c_rayleigh,
        })

    return pd.DataFrame(filas)


@st.cache_data(show_spinner=False)
def crear_rosa_vientos_16(df_resumen):
    customdata = np.stack(
        [
            df_resumen["Sector"],
            df_resumen["Velocidad media (m/s)"].fillna(0),
            df_resumen["Datos"].fillna(0),
        ],
        axis=1
    )

    fig = go.Figure()

    fig.add_trace(
        go.Barpolar(
            r=df_resumen["Frecuencia (%)"],
            theta=df_resumen["Centro (°)"],
            width=[22.5] * len(df_resumen),
            name="Frecuencia",
            customdata=customdata,
            marker=dict(
                color=df_resumen["Velocidad media (m/s)"].fillna(0),
                colorscale="Blues",
                colorbar=dict(title="V media (m/s)")
            ),
            hovertemplate=(
                "Sector: %{customdata[0]}<br>"
                "Frecuencia: %{r:.2f}%<br>"
                "Velocidad media: %{customdata[1]:.2f} m/s<br>"
                "Datos: %{customdata[2]}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        template="plotly_white",
        height=700,
        margin=dict(l=40, r=40, t=40, b=40),
        polar=dict(
            angularaxis=dict(
                direction="clockwise",
                rotation=90,
                tickmode="array",
                tickvals=list(SECTOR_CENTERS_16),
                ticktext=SECTOR_LABELS_16,
            ),
            radialaxis=dict(
                title="Frecuencia (%)",
                angle=90,
            ),
        ),
    )

    return fig


@st.cache_data(show_spinner=False)
def weibull_pdf(v, k, c):
    v = np.asarray(v, dtype=float)
    if np.isnan(k) or np.isnan(c) or k <= 0 or c <= 0:
        return np.full_like(v, np.nan, dtype=float)

    return (k / c) * (v / c) ** (k - 1) * np.exp(-((v / c) ** k))


@st.cache_data(show_spinner=False)
def rayleigh_pdf(v, c):
    v = np.asarray(v, dtype=float)
    if np.isnan(c) or c <= 0:
        return np.full_like(v, np.nan, dtype=float)

    return (2.0 * v / (c ** 2)) * np.exp(-((v / c) ** 2))


@st.cache_data(show_spinner=False)
def weibull_cdf(v, k, c):
    v = np.asarray(v, dtype=float)
    if not np.isfinite(k) or not np.isfinite(c) or k <= 0 or c <= 0:
        return np.full_like(v, np.nan, dtype=float)
    return 1.0 - np.exp(-((v / c) ** k))


@st.cache_data(show_spinner=False)
def rayleigh_cdf(v, c):
    v = np.asarray(v, dtype=float)
    if not np.isfinite(c) or c <= 0:
        return np.full_like(v, np.nan, dtype=float)
    return 1.0 - np.exp(-((v / c) ** 2))


@st.cache_data(show_spinner=False)
def weibull_interval_prob(a, b, k, c):
    if not np.isfinite(k) or not np.isfinite(c) or k <= 0 or c <= 0:
        return np.nan
    return float(weibull_cdf(b, k, c) - weibull_cdf(a, k, c))


@st.cache_data(show_spinner=False)
def rayleigh_interval_prob(a, b, c):
    if not np.isfinite(c) or c <= 0:
        return np.nan
    return float(rayleigh_cdf(b, c) - rayleigh_cdf(a, c))


def calidad_weibull(n):
    if n >= 30:
        return "Alta"
    if n >= 10:
        return "Media"
    return "Baja"


@st.cache_data(show_spinner=False)
def crear_histograma_sector_con_ajustes(velocidades, sector, k_weibull, c_weibull, c_rayleigh):
    v = np.asarray(velocidades, dtype=float)
    v = v[np.isfinite(v) & (v >= 0)]

    fig = go.Figure()

    if len(v) == 0:
        fig.update_layout(
            template="plotly_white",
            height=520,
            title=f"Sector {sector} - sin datos",
        )
        return fig

    fig.add_trace(
        go.Histogram(
            x=v,
            histnorm="probability density",
            nbinsx=min(24, max(8, int(np.sqrt(len(v)) * 2))),
            name="Histograma",
            opacity=0.65,
        )
    )

    vmax = max(float(np.max(v)) * 1.2, 1.0)
    x = np.linspace(0, vmax, 400)

    y_weibull = weibull_pdf(x, k_weibull, c_weibull)
    y_rayleigh = rayleigh_pdf(x, c_rayleigh)

    if np.isfinite(y_weibull).any():
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y_weibull,
                mode="lines",
                name="Weibull",
                line=dict(width=3),
            )
        )

    if np.isfinite(y_rayleigh).any():
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y_rayleigh,
                mode="lines",
                name="Rayleigh",
                line=dict(width=3, dash="dash"),
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=520,
        barmode="overlay",
        title=f"Sector {sector} - Histograma con ajustes Weibull y Rayleigh",
        xaxis_title="Velocidad del viento (m/s)",
        yaxis_title="Densidad de probabilidad",
        margin=dict(l=40, r=40, t=60, b=40),
    )

    return fig


def parsear_lista_velocidades(texto):
    if not texto.strip():
        return []

    texto = texto.replace("\\n", ",").replace(";", ",")
    partes = [p.strip().replace(",", ".") for p in texto.split(",") if p.strip()]

    valores = []
    for parte in partes:
        valores.append(float(parte))

    return valores


def construir_url_nasa_power(latitude, longitude, start_date, end_date):
    start_txt = pd.to_datetime(start_date).strftime("%Y%m%d")
    end_txt = pd.to_datetime(end_date).strftime("%Y%m%d")

    return (
        "https://power.larc.nasa.gov/api/temporal/hourly/point"
        f"?parameters=WS10M,WS50M,WD10M,WD50M"
        f"&community=RE&longitude={longitude}&latitude={latitude}"
        f"&start={start_txt}&end={end_txt}&format=CSV&header=false"
    )


def _limpiar_nombre_columna(col):
    return (
        str(col)
        .replace("\ufeff", "")
        .replace('"', "")
        .strip()
        .upper()
    )


def _detectar_separador(linea):
    candidatos = [",", ";", "\t"]
    mejor_sep = ","
    mejor_n = -1

    for sep in candidatos:
        n = linea.count(sep)
        if n > mejor_n:
            mejor_n = n
            mejor_sep = sep

    return mejor_sep


def _buscar_header_nasa(lines):
    for i, line in enumerate(lines):
        limpio = line.replace("\ufeff", "").replace('"', "").strip()
        if not limpio:
            continue

        sep = _detectar_separador(limpio)
        partes = [_limpiar_nombre_columna(p) for p in limpio.split(sep)]

        if {"YEAR", "MO", "DY", "HR"}.issubset(set(partes)):
            return i, sep

    return None, ","


def extraer_metadata_nasa_desde_texto(texto):
    meta = {
        "latitude": None,
        "longitude": None,
    }

    patrones_lat = [
        r"LATITUDE\s*[:=,]\s*([-+]?\d+(?:\.\d+)?)",
        r"\bLAT\s*[:=,]\s*([-+]?\d+(?:\.\d+)?)",
    ]

    patrones_lon = [
        r"LONGITUDE\s*[:=,]\s*([-+]?\d+(?:\.\d+)?)",
        r"\bLON\s*[:=,]\s*([-+]?\d+(?:\.\d+)?)",
        r"\bLONG\s*[:=,]\s*([-+]?\d+(?:\.\d+)?)",
    ]

    texto_limpio = texto.replace('"', "").upper()

    for patron in patrones_lat:
        m = re.search(patron, texto_limpio)
        if m:
            val = float(m.group(1))
            if -90 <= val <= 90:
                meta["latitude"] = val
                break

    for patron in patrones_lon:
        m = re.search(patron, texto_limpio)
        if m:
            val = float(m.group(1))
            if -180 <= val <= 180:
                meta["longitude"] = val
                break

    return meta


def normalizar_dataframe_nasa(df):
    df = df.copy()
    df.columns = [_limpiar_nombre_columna(col) for col in df.columns]

    required = ["YEAR", "MO", "DY", "HR", "WS10M", "WS50M"]
    optional = ["WD10M", "WD50M"]

    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"Faltan columnas requeridas: {missing}. "
            f"Columnas encontradas: {list(df.columns)}"
        )

    for col in optional:
        if col not in df.columns:
            df[col] = np.nan

    for col in required + optional:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["YEAR", "MO", "DY", "HR"]).copy()

    df["YEAR"] = df["YEAR"].astype(int)
    df["MO"] = df["MO"].astype(int)
    df["DY"] = df["DY"].astype(int)
    df["HR"] = df["HR"].astype(int)

    df["timestamp"] = pd.to_datetime(
        df[["YEAR", "MO", "DY", "HR"]].rename(
            columns={
                "YEAR": "year",
                "MO": "month",
                "DY": "day",
                "HR": "hour"
            }
        )
    )

    return df[
        ["timestamp", "YEAR", "MO", "DY", "HR", "WS10M", "WS50M", "WD10M", "WD50M"]
    ]


def leer_csv_nasa_subido(uploaded_file):
    raw_bytes = uploaded_file.getvalue()

    try:
        texto = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = raw_bytes.decode("latin-1", errors="ignore")

    texto = texto.replace("\r\n", "\n").replace("\r", "\n")

    if texto.count("\n") <= 2 and "\\n" in texto:
        texto = texto.replace("\\n", "\n")

    lines = [line for line in texto.split("\n") if line.strip()]

    header_index, sep = _buscar_header_nasa(lines)

    if header_index is None:
        raise ValueError("No encontré la cabecera YEAR,MO,DY,HR en el CSV.")

    data_lines = lines[header_index:]

    reader = csv.reader(io.StringIO("\n".join(data_lines)), delimiter=sep)
    rows = [row for row in reader if any(str(cell).strip() for cell in row)]

    if not rows:
        raise ValueError("No encontré filas de datos en el CSV.")

    header = [_limpiar_nombre_columna(c) for c in rows[0]]
    ncols = len(header)

    registros = []
    for row in rows[1:]:
        if len(row) < ncols:
            continue
        if len(row) > ncols:
            row = row[:ncols]
        registros.append(row)

    if not registros:
        raise ValueError("No encontré registros válidos después de la cabecera.")

    df = pd.DataFrame(registros, columns=header)
    df = normalizar_dataframe_nasa(df)

    meta = extraer_metadata_nasa_desde_texto(texto)

    if len(df) > 0:
        meta["start_date"] = df["timestamp"].min().date()
        meta["end_date"] = df["timestamp"].max().date()
    else:
        meta["start_date"] = None
        meta["end_date"] = None

    return df, meta


def leer_json_nasa_subido(uploaded_file):
    """Parse a NASA POWER JSON API response file into the standard DataFrame.

    The expected format is the POWER API JSON with structure:
        properties.parameter.WS10M  -> {"YYYYMMDDHH": value, ...}
        properties.parameter.WS50M  -> ...
        geometry.coordinates         -> [lon, lat]

    Returns (df, meta) matching the contract of leer_csv_nasa_subido.
    """
    raw_bytes = uploaded_file.getvalue()
    try:
        texto = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = raw_bytes.decode("latin-1", errors="ignore")

    try:
        data = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise ValueError(f"El archivo no es un JSON válido: {exc}") from exc

    # Navigate the POWER API structure
    params = None
    if isinstance(data, dict):
        props = data.get("properties") or {}
        if not props:
            features = data.get("features")
            if isinstance(features, list) and len(features) > 0:
                props = features[0].get("properties", {})
        params = props.get("parameter") if isinstance(props, dict) else None

    if params is None:
        raise ValueError(
            "Formato JSON no reconocido. Se esperaba la estructura de la API "
            "NASA POWER con 'properties.parameter.WS10M', etc."
        )

    ws10m_dict = params.get("WS10M", {})
    ws50m_dict = params.get("WS50M", {})
    wd10m_dict = params.get("WD10M", {})
    wd50m_dict = params.get("WD50M", {})

    if not ws10m_dict and not ws50m_dict:
        raise ValueError(
            "El JSON no contiene datos de WS10M ni WS50M en "
            "'properties.parameter'."
        )

    all_keys = sorted(set(ws10m_dict.keys()) | set(ws50m_dict.keys()))
    if not all_keys:
        raise ValueError("No se encontraron registros horarios en el JSON.")

    rows = []
    for key in all_keys:
        key_str = str(key)
        if len(key_str) < 8:
            continue
        try:
            year = int(key_str[:4])
            mo = int(key_str[4:6])
            dy = int(key_str[6:8])
            hr = int(key_str[8:10]) if len(key_str) >= 10 else 0
        except (ValueError, IndexError):
            continue

        rows.append({
            "YEAR": year, "MO": mo, "DY": dy, "HR": hr,
            "WS10M": ws10m_dict.get(key, np.nan),
            "WS50M": ws50m_dict.get(key, np.nan),
            "WD10M": wd10m_dict.get(key, np.nan),
            "WD50M": wd50m_dict.get(key, np.nan),
        })

    if not rows:
        raise ValueError("No se encontraron registros horarios válidos en el JSON.")

    df = pd.DataFrame(rows)
    # Replace NASA fill values (-999, -99) with NaN
    for col in ["WS10M", "WS50M", "WD10M", "WD50M"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] < -900, col] = np.nan

    df = normalizar_dataframe_nasa(df)

    # Extract coordinates from geometry
    meta = {"latitude": None, "longitude": None}
    geometry = data.get("geometry", {})
    coords = geometry.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        meta["longitude"] = float(coords[0])
        meta["latitude"] = float(coords[1])

    if len(df) > 0:
        meta["start_date"] = df["timestamp"].min().date()
        meta["end_date"] = df["timestamp"].max().date()
    else:
        meta["start_date"] = None
        meta["end_date"] = None

    return df, meta


def leer_csv_gwa(uploaded_file):
    """Parse a Global Wind Atlas CSV with Weibull parameters per height.

    Expected columns: height(m), A, k, mean_wind_speed
    Optional extra columns are ignored.

    Returns a dict with keys: alturas, A, k, v_medio.
    """
    raw_bytes = uploaded_file.getvalue()
    try:
        texto = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = raw_bytes.decode("latin-1", errors="ignore")

    first_line = texto.strip().split("\n")[0] if texto.strip() else ""
    sep = _detectar_separador(first_line)

    df = pd.read_csv(io.StringIO(texto), sep=sep)
    df.columns = [c.strip().lower() for c in df.columns]

    # Map common column name variants
    col_map = {
        "height(m)": "height",
        "height (m)": "height",
        "altura(m)": "height",
        "altura (m)": "height",
        "mean_wind_speed": "v_medio",
        "mean wind speed": "v_medio",
        "velocidad_media": "v_medio",
        "mean_wind_speed(m/s)": "v_medio",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    required = {"height", "a", "k"}
    found = set(df.columns)
    missing = required - found
    if missing:
        raise ValueError(
            f"Faltan columnas requeridas en el CSV de GWA: {missing}. "
            f"Columnas encontradas: {list(df.columns)}. "
            f"Se esperan: height(m), A, k, mean_wind_speed"
        )

    for col in ["height", "a", "k"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "v_medio" in df.columns:
        df["v_medio"] = pd.to_numeric(df["v_medio"], errors="coerce")
    else:
        from math import gamma as _gamma
        df["v_medio"] = df["a"] * df.apply(
            lambda r: _gamma(1 + 1 / r["k"]) if r["k"] > 0 else np.nan, axis=1
        )

    df = df.dropna(subset=["height", "a", "k"]).sort_values("height").reset_index(drop=True)

    if len(df) == 0:
        raise ValueError("No se encontraron filas válidas en el CSV de GWA.")

    return {
        "alturas": df["height"].tolist(),
        "A": df["a"].tolist(),
        "k": df["k"].tolist(),
        "v_medio": df["v_medio"].tolist(),
    }


def generar_serie_weibull(gwa_data: dict, n_years: int = 1) -> pd.DataFrame:
    """Generate a synthetic hourly wind-speed series from GWA Weibull parameters.

    For WS10M: uses A, k from the height closest to 10 m.
    For WS50M: uses A, k from the height closest to 50 m.
    Wind direction columns (WD10M, WD50M) are filled with uniform random [0, 360).

    Returns a DataFrame with columns:
        timestamp, YEAR, MO, DY, HR, WS10M, WS50M, WD10M, WD50M
    matching the format produced by normalizar_dataframe_nasa().
    """
    alturas = np.asarray(gwa_data["alturas"], dtype=float)
    A_vals = np.asarray(gwa_data["A"], dtype=float)
    k_vals = np.asarray(gwa_data["k"], dtype=float)

    if len(alturas) == 0:
        raise ValueError("gwa_data no contiene alturas.")

    def _closest(target):
        idx = int(np.argmin(np.abs(alturas - target)))
        return A_vals[idx], k_vals[idx]

    A10, k10 = _closest(10.0)
    A50, k50 = _closest(50.0)

    n_hours = 8760 * max(1, int(n_years))
    rng = np.random.default_rng()

    # Weibull samples: scale * weibull(shape)
    ws10 = A10 * rng.weibull(k10, n_hours)
    ws50 = A50 * rng.weibull(k50, n_hours)
    wd10 = rng.uniform(0, 360, n_hours)
    wd50 = rng.uniform(0, 360, n_hours)

    # Build timestamp index starting 2024-01-01 00:00
    start = pd.Timestamp("2024-01-01 00:00")
    timestamps = pd.date_range(start, periods=n_hours, freq="h")

    df = pd.DataFrame({
        "timestamp": timestamps,
        "YEAR": timestamps.year,
        "MO": timestamps.month,
        "DY": timestamps.day,
        "HR": timestamps.hour,
        "WS10M": ws10,
        "WS50M": ws50,
        "WD10M": wd10,
        "WD50M": wd50,
    })

    return df


def consultar_open_meteo(latitude: float, longitude: float, start_date, end_date) -> pd.DataFrame:
    """Query Open-Meteo Historical Weather API for hourly wind data.

    Uses the free archive endpoint (no API key required).
    Returns a DataFrame with columns:
        timestamp, YEAR, MO, DY, HR, WS10M, WS50M, WD10M, WD50M
    matching the format produced by normalizar_dataframe_nasa().

    WS50M is mapped from wind_speed_100m as a proxy (Open-Meteo does not
    provide 50 m directly; 100 m is the closest available height).
    """
    import requests as _requests

    start_txt = pd.to_datetime(start_date).strftime("%Y-%m-%d")
    end_txt = pd.to_datetime(end_date).strftime("%Y-%m-%d")

    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={latitude}&longitude={longitude}"
        f"&start_date={start_txt}&end_date={end_txt}"
        "&hourly=wind_speed_10m,wind_speed_100m,wind_direction_10m"
        "&wind_speed_unit=ms"
        "&timezone=UTC"
    )

    resp = _requests.get(url, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data and data.get("error"):
        reason = data.get("reason", str(data["error"]))
        raise ValueError(f"Open-Meteo devolvió un error: {reason}")

    hourly = data.get("hourly")
    if not hourly or "time" not in hourly:
        raise ValueError(
            "La respuesta de Open-Meteo no contiene datos horarios. "
            "Verifique las coordenadas y el rango de fechas."
        )

    timestamps = pd.to_datetime(hourly["time"])
    ws10 = np.asarray(hourly.get("wind_speed_10m", []), dtype=float)
    ws100 = np.asarray(hourly.get("wind_speed_100m", []), dtype=float)
    wd10 = np.asarray(hourly.get("wind_direction_10m", []), dtype=float)

    n = len(timestamps)
    # Ensure arrays match timestamp length
    if len(ws10) < n:
        ws10 = np.pad(ws10, (0, n - len(ws10)), constant_values=np.nan)
    if len(ws100) < n:
        ws100 = np.pad(ws100, (0, n - len(ws100)), constant_values=np.nan)
    if len(wd10) < n:
        wd10 = np.pad(wd10, (0, n - len(wd10)), constant_values=np.nan)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "YEAR": timestamps.year,
        "MO": timestamps.month,
        "DY": timestamps.day,
        "HR": timestamps.hour,
        "WS10M": ws10[:n],
        "WS50M": ws100[:n],   # 100 m as proxy for 50 m
        "WD10M": wd10[:n],
        "WD50M": wd10[:n],    # reuse 10 m direction
    })

    # Replace NaN-like sentinel values
    for col in ["WS10M", "WS50M", "WD10M", "WD50M"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


@st.cache_data(show_spinner=False)
def crear_grafica_nasa_hourly(df_nasa):
    fig = go.Figure()

    if len(df_nasa) > 0:
        fig.add_trace(
            go.Scatter(
                x=df_nasa["timestamp"],
                y=df_nasa["WS10M"],
                mode="lines",
                name="WS10M",
                hovertemplate="Fecha: %{x}<br>WS10M: %{y:.2f} m/s<extra></extra>",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=df_nasa["timestamp"],
                y=df_nasa["WS50M"],
                mode="lines",
                name="WS50M",
                hovertemplate="Fecha: %{x}<br>WS50M: %{y:.2f} m/s<extra></extra>",
            )
        )

    fig.update_layout(
        template="plotly_white",
        height=520,
        margin=dict(l=40, r=40, t=30, b=40),
        xaxis_title="Fecha y hora",
        yaxis_title="Velocidad del viento (m/s)",
    )

    return fig


@st.cache_data(show_spinner=False)
def construir_serie_viento_analisis(
    df_nasa,
    modelo,
    altura_deseada,
    roughness_label,
    direccion_fuente,
    roughness_options=None,
    output_speed_col="WS_ANALISIS",
    output_direction_col="WD_USADA",
):
    df = df_nasa.copy()
    roughness_options = roughness_options or ROUGHNESS_OPTIONS_DEFAULT
    modelo = normalizar_modelo_altura(modelo)

    for col in ["WS10M", "WS50M", "WD10M", "WD50M"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    meta = {
        "descripcion": "",
        "parametro_1_nombre": "",
        "parametro_1_valor": np.nan,
        "parametro_2_nombre": "",
        "parametro_2_valor": np.nan,
    }

    if modelo == "50 m":
        df[output_speed_col] = df["WS50M"]
        df[output_direction_col] = df["WD50M"]

    elif modelo == "10 m":
        df[output_speed_col] = df["WS10M"]
        df[output_direction_col] = df["WD10M"]

    elif modelo == "Exponencial":
        ws_alt, alpha_h = extrapolar_exponencial_dos_puntos(
            df["WS10M"].to_numpy(),
            10.0,
            df["WS50M"].to_numpy(),
            50.0,
            altura_deseada,
        )
        df[output_speed_col] = ws_alt
        df[output_direction_col] = df[direccion_fuente]

        alpha_series = pd.Series(alpha_h).dropna()
        meta["parametro_1_nombre"] = "Alpha promedio"
        meta["parametro_1_valor"] = float(alpha_series.mean()) if len(alpha_series) > 0 else np.nan

    elif modelo == "Log A (2 puntos)":
        ws_alt, ustar_h, z0_h = extrapolar_logaritmico_dos_puntos(
            df["WS10M"].to_numpy(),
            10.0,
            df["WS50M"].to_numpy(),
            50.0,
            altura_deseada,
        )
        df[output_speed_col] = ws_alt
        df[output_direction_col] = df[direccion_fuente]

        ustar_series = pd.Series(ustar_h).dropna()
        z0_series = pd.Series(z0_h).dropna()
        meta["parametro_1_nombre"] = "u* promedio"
        meta["parametro_1_valor"] = float(ustar_series.mean()) if len(ustar_series) > 0 else np.nan
        meta["parametro_2_nombre"] = "z0 efectiva promedio"
        meta["parametro_2_valor"] = float(z0_series.mean()) if len(z0_series) > 0 else np.nan

    elif modelo == PROMEDIO_LOG_EXP_LABEL:
        ws_exp, alpha_h = extrapolar_exponencial_dos_puntos(
            df["WS10M"].to_numpy(),
            10.0,
            df["WS50M"].to_numpy(),
            50.0,
            altura_deseada,
        )
        ws_log_a, ustar_h, _ = extrapolar_logaritmico_dos_puntos(
            df["WS10M"].to_numpy(),
            10.0,
            df["WS50M"].to_numpy(),
            50.0,
            altura_deseada,
        )
        df[output_speed_col] = (np.asarray(ws_exp, dtype=float) + np.asarray(ws_log_a, dtype=float)) / 2.0
        df[output_direction_col] = df[direccion_fuente]

        alpha_series = pd.Series(alpha_h).dropna()
        ustar_series = pd.Series(ustar_h).dropna()
        meta["parametro_1_nombre"] = "Alpha promedio"
        meta["parametro_1_valor"] = float(alpha_series.mean()) if len(alpha_series) > 0 else np.nan
        meta["parametro_2_nombre"] = "u* promedio"
        meta["parametro_2_valor"] = float(ustar_series.mean()) if len(ustar_series) > 0 else np.nan

    else:
        raise ValueError("Modelo no reconocido.")

    return df, meta


# =========================================================
# FASE 4 - ARREGLO DEL PARQUE Y ESTELAS
# =========================================================
def rotar_puntos(x, y, angle_deg):
    ang = np.deg2rad(angle_deg)
    xr = x * np.cos(ang) - y * np.sin(ang)
    yr = x * np.sin(ang) + y * np.cos(ang)
    return xr, yr


@st.cache_data(show_spinner=False)
def generar_layout_parque(layout_type, n_turbinas, dx_m, dy_m, rotation_deg=0.0):
    n_turbinas = int(max(1, n_turbinas))
    dx_m = float(dx_m)
    dy_m = float(dy_m)

    coords = []

    def _centrar_coords(puntos):
        if not puntos:
            return puntos
        mean_x = float(np.mean([p[0] for p in puntos]))
        mean_y = float(np.mean([p[1] for p in puntos]))
        return [(float(x - mean_x), float(y - mean_y)) for x, y in puntos]

    if layout_type == "En línea":
        for i in range(n_turbinas):
            x = (i - (n_turbinas - 1) / 2.0) * dx_m
            y = 0.0
            coords.append((x, y))

    elif layout_type == "En cruz":
        coords.append((0.0, 0.0))
        step = 1
        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        while len(coords) < n_turbinas:
            for dxs, dys in dirs:
                if len(coords) >= n_turbinas:
                    break
                coords.append((dxs * step * dx_m, dys * step * dy_m))
            step += 1

    elif layout_type == "Matriz rectangular":
        ncols = int(np.ceil(np.sqrt(n_turbinas)))
        nrows = int(np.ceil(n_turbinas / ncols))

        for r in range(nrows):
            for c in range(ncols):
                if len(coords) >= n_turbinas:
                    break
                x = (c - (ncols - 1) / 2.0) * dx_m
                y = ((nrows - 1) / 2.0 - r) * dy_m
                coords.append((x, y))
    elif layout_type == "Doble fila":
        for i in range(n_turbinas):
            fila = i % 2
            col = i // 2
            x = col * dx_m
            y = -dy_m / 2.0 if fila == 0 else dy_m / 2.0
            coords.append((x, y))
        coords = _centrar_coords(coords)

    elif layout_type == "Tresbolillo":
        ncols = int(np.ceil(np.sqrt(n_turbinas)))
        for i in range(n_turbinas):
            fila = i // ncols
            col = i % ncols
            offset_x = dx_m / 2.0 if fila % 2 else 0.0
            x = col * dx_m + offset_x
            y = fila * dy_m
            coords.append((x, y))
        coords = _centrar_coords(coords)

    elif layout_type == "Matriz triangular":
        row = 0
        while len(coords) < n_turbinas:
            for col in range(row + 1):
                if len(coords) >= n_turbinas:
                    break
                x = (col - row / 2.0) * dx_m
                y = -row * dy_m
                coords.append((x, y))
            row += 1
        coords = _centrar_coords(coords)

    elif layout_type == "Diagonal":
        for i in range(n_turbinas):
            offset = i - (n_turbinas - 1) / 2.0
            coords.append((offset * dx_m, offset * dy_m))

    elif layout_type == "Circular":
        if n_turbinas == 1:
            coords.append((0.0, 0.0))
        else:
            radius = max((n_turbinas * dx_m) / (2.0 * np.pi), 2.0 * min(dx_m, dy_m))
            for i in range(n_turbinas):
                angle = 2.0 * np.pi * i / n_turbinas
                coords.append((radius * np.cos(angle), radius * np.sin(angle)))
        coords = _centrar_coords(coords)

    elif layout_type == "Arco":
        if n_turbinas == 1:
            coords.append((0.0, 0.0))
        else:
            arco_total = 2.0 * np.pi / 3.0
            radius = max((n_turbinas * dx_m) / arco_total, 2.0 * min(dx_m, dy_m))
            for i in range(n_turbinas):
                angle = -arco_total / 2.0 + i * arco_total / (n_turbinas - 1)
                coords.append((radius * np.cos(angle), radius * np.sin(angle)))
        coords = _centrar_coords(coords)

    elif layout_type == "Aleatorio controlado":
        rng = random.Random(42)
        side = np.sqrt(n_turbinas) * max(dx_m, dy_m) * 1.5
        min_dist = max(min(dx_m, dy_m) * 0.7, 1.5)
        for i in range(n_turbinas):
            accepted = False
            for _ in range(100):
                x = rng.uniform(-side / 2.0, side / 2.0)
                y = rng.uniform(-side / 2.0, side / 2.0)
                if all(np.hypot(x - px, y - py) >= min_dist for px, py in coords):
                    coords.append((x, y))
                    accepted = True
                    break
            if not accepted:
                offset = i - (n_turbinas - 1) / 2.0
                coords.append((offset * min_dist, offset * min_dist))
        coords = _centrar_coords(coords)
    else:
        raise ValueError("Tipo de arreglo no reconocido.")

    xs = np.array([c[0] for c in coords], dtype=float)
    ys = np.array([c[1] for c in coords], dtype=float)

    xr, yr = rotar_puntos(xs, ys, rotation_deg)

    df = pd.DataFrame({
        "turbina_id": [f"T{i+1}" for i in range(len(coords))],
        "x_m": xr,
        "y_m": yr,
    })

    return df


@st.cache_data(show_spinner=False)
def crear_figura_layout_parque(df_layout, diametro=None, titulo="Arreglo del parque"):
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df_layout["x_m"],
            y=df_layout["y_m"],
            mode="markers+text",
            text=df_layout["turbina_id"],
            textposition="top center",
            marker=dict(size=12, color="#1f77b4"),
            name="Aerogeneradores",
            hovertemplate=(
                "ID: %{text}<br>"
                "X: %{x:.2f} m<br>"
                "Y: %{y:.2f} m"
                "<extra></extra>"
            ),
        )
    )

    if diametro is not None and diametro > 0:
        r = diametro / 2.0
        for _, row in df_layout.iterrows():
            fig.add_shape(
                type="circle",
                xref="x",
                yref="y",
                x0=row["x_m"] - r,
                y0=row["y_m"] - r,
                x1=row["x_m"] + r,
                y1=row["y_m"] + r,
                line=dict(color="rgba(31,119,180,0.25)", width=1),
            )

    fig.update_layout(
        title=titulo,
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
    )

    fig.update_xaxes(title_text="X (m)", zeroline=True)
    fig.update_yaxes(title_text="Y (m)", scaleanchor="x", scaleratio=1, zeroline=True)

    return fig


def _direccion_met_a_vector_downwind(direction_deg):
    theta_to = np.deg2rad((float(direction_deg) + 180.0) % 360.0)
    ex = np.sin(theta_to)   # X = este
    ey = np.cos(theta_to)   # Y = norte
    return ex, ey


def _proyectar_layout_sobre_viento(df_layout, direction_deg):
    ex, ey = _direccion_met_a_vector_downwind(direction_deg)
    px = df_layout["x_m"].to_numpy(dtype=float)
    py = df_layout["y_m"].to_numpy(dtype=float)

    x_down = px * ex + py * ey
    y_cross = -px * ey + py * ex

    dfp = df_layout.copy()
    dfp["x_down"] = x_down
    dfp["y_cross"] = y_cross
    return dfp


def interpolar_potencia_desde_curva(curva_df, velocidades):
    df_curve = preparar_datos_curva(curva_df)
    return interpolar_potencia_curva_preparada(df_curve, velocidades)


@st.cache_data(show_spinner=False)
def calcular_estelas_jensen_direccion(df_layout, wind_speed, direction_deg, diametro, ct=0.8, kw=0.05, curva_df=None):
    if diametro <= 0:
        raise ValueError("El diámetro debe ser mayor que 0.")
    if not (0 < ct < 1):
        raise ValueError("Ct debe estar entre 0 y 1.")
    if kw <= 0:
        raise ValueError("kw debe ser mayor que 0.")
    if wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    dfp = _proyectar_layout_sobre_viento(df_layout, direction_deg).copy()
    dfp = dfp.sort_values("x_down").reset_index(drop=True)

    n = len(dfp)
    deficits = np.zeros(n, dtype=float)

    for j in range(n):
        dlist = []
        xj = float(dfp.loc[j, "x_down"])
        yj = float(dfp.loc[j, "y_cross"])

        for i in range(j):
            xi = float(dfp.loc[i, "x_down"])
            yi = float(dfp.loc[i, "y_cross"])

            dx = xj - xi
            dy = abs(yj - yi)

            if dx <= 0:
                continue

            wake_radius = diametro / 2.0 + kw * dx
            if dy <= wake_radius:
                deficit_ij = (1.0 - np.sqrt(1.0 - ct)) / (1.0 + 2.0 * kw * dx / diametro) ** 2
                dlist.append(deficit_ij)

        if len(dlist) > 0:
            deficits[j] = np.sqrt(np.sum(np.square(dlist)))

    deficits = np.clip(deficits, 0.0, 0.999999)
    dfp["deficit_total"] = deficits
    dfp["velocidad_libre"] = float(wind_speed)
    dfp["velocidad_efectiva"] = float(wind_speed) * (1.0 - deficits)

    if curva_df is not None:
        dfp["potencia_base_W"] = interpolar_potencia_desde_curva(curva_df, np.full(n, float(wind_speed)))
        dfp["potencia_wake_W"] = interpolar_potencia_desde_curva(curva_df, dfp["velocidad_efectiva"].to_numpy())
        dfp["perdida_potencia_pct"] = np.where(
            dfp["potencia_base_W"] > 0,
            100.0 * (1.0 - dfp["potencia_wake_W"] / dfp["potencia_base_W"]),
            0.0
        )
    else:
        dfp["potencia_base_W"] = np.nan
        dfp["potencia_wake_W"] = np.nan
        dfp["perdida_potencia_pct"] = np.nan

    return dfp


@st.cache_data(show_spinner=False)
def analizar_estelas_parque_16(df_layout, df_nasa, curva_df, diametro, ct=0.8, kw=0.05, ws_col="WS50M", wd_col="WD50M"):
    df_rosa = preparar_datos_rosa(df_nasa, ws_col=ws_col, wd_col=wd_col)
    resumen_rosa = resumir_sectores_rosa(df_rosa, ws_col=ws_col)

    filas = []
    detalles = {}

    for _, row in resumen_rosa.iterrows():
        sector = row["Sector"]
        direction_deg = float(row["Centro (°)"])
        freq_pct = float(row["Frecuencia (%)"])
        horas_eq = freq_pct / 100.0 * 8760.0
        u_ref = float(row["Velocidad media (m/s)"]) if pd.notna(row["Velocidad media (m/s)"]) else 0.0
        n_datos = int(row["Datos"])

        if n_datos > 0 and u_ref >= 0:
            df_dir = calcular_estelas_jensen_direccion(
                df_layout=df_layout,
                wind_speed=u_ref,
                direction_deg=direction_deg,
                diametro=diametro,
                ct=ct,
                kw=kw,
                curva_df=curva_df,
            )

            p_base_park = float(df_dir["potencia_base_W"].sum())
            p_wake_park = float(df_dir["potencia_wake_W"].sum())

            if p_base_park > 0:
                wake_loss_pct = 100.0 * (1.0 - p_wake_park / p_base_park)
                eficiencia_pct = 100.0 * p_wake_park / p_base_park
            else:
                wake_loss_pct = 0.0
                eficiencia_pct = 100.0

            detalles[sector] = df_dir.copy()
        else:
            p_base_park = 0.0
            p_wake_park = 0.0
            wake_loss_pct = 0.0
            eficiencia_pct = 100.0
            detalles[sector] = pd.DataFrame()

        filas.append({
            "Sector": sector,
            "Dirección centro (°)": direction_deg,
            "Datos": n_datos,
            "Frecuencia (%)": freq_pct,
            "Horas equivalentes anuales (h/año)": horas_eq,
            "Velocidad media sector (m/s)": u_ref,
            "Potencia parque sin estela (W)": p_base_park,
            "Potencia parque con estela (W)": p_wake_park,
            "Pérdida por estela (%)": wake_loss_pct,
            "Eficiencia parque (%)": eficiencia_pct,
            "Pérdida ponderada (%)": wake_loss_pct * freq_pct / 100.0,
        })

    resumen = pd.DataFrame(filas)
    weighted_loss_pct = float(resumen["Pérdida ponderada (%)"].sum()) if len(resumen) > 0 else 0.0

    return resumen, detalles, weighted_loss_pct


@st.cache_data(show_spinner=False)
def crear_figura_direccion_estela(df_detalle, sector, direction_deg, diametro=None):
    fig = go.Figure()

    if len(df_detalle) == 0:
        fig.update_layout(
            template="plotly_white",
            height=600,
            title=f"Sector {sector} - sin datos"
        )
        return fig

    fig.add_trace(
        go.Scatter(
            x=df_detalle["x_m"],
            y=df_detalle["y_m"],
            mode="markers+text",
            text=df_detalle["turbina_id"],
            textposition="top center",
            marker=dict(
                size=14,
                color=df_detalle["perdida_potencia_pct"],
                colorscale="Reds",
                colorbar=dict(title="Pérdida %"),
                showscale=True,
            ),
            name="Turbinas",
            hovertemplate=(
                "ID: %{text}<br>"
                "X: %{x:.2f} m<br>"
                "Y: %{y:.2f} m<br>"
                "U libre: %{customdata[0]:.2f} m/s<br>"
                "U efectiva: %{customdata[1]:.2f} m/s<br>"
                "Déficit: %{customdata[2]:.2f}%<br>"
                "Pérdida potencia: %{customdata[3]:.2f}%"
                "<extra></extra>"
            ),
            customdata=np.stack([
                df_detalle["velocidad_libre"],
                df_detalle["velocidad_efectiva"],
                100.0 * df_detalle["deficit_total"],
                df_detalle["perdida_potencia_pct"],
            ], axis=1)
        )
    )

    if diametro is not None and diametro > 0:
        r = diametro / 2.0
        for _, row in df_detalle.iterrows():
            fig.add_shape(
                type="circle",
                xref="x",
                yref="y",
                x0=row["x_m"] - r,
                y0=row["y_m"] - r,
                x1=row["x_m"] + r,
                y1=row["y_m"] + r,
                line=dict(color="rgba(200,0,0,0.20)", width=1),
            )

    xmin = float(df_detalle["x_m"].min())
    xmax = float(df_detalle["x_m"].max())
    ymin = float(df_detalle["y_m"].min())
    ymax = float(df_detalle["y_m"].max())

    span = max(xmax - xmin, ymax - ymin, diametro if diametro else 100.0)
    ex, ey = _direccion_met_a_vector_downwind(direction_deg)
    cx = xmin + 0.15 * span
    cy = ymax + 0.15 * span
    arrow_len = 0.35 * span

    fig.add_annotation(
        x=cx + ex * arrow_len,
        y=cy + ey * arrow_len,
        ax=cx,
        ay=cy,
        xref="x",
        yref="y",
        axref="x",
        ayref="y",
        showarrow=True,
        arrowhead=3,
        arrowsize=1.2,
        arrowwidth=2,
        text=f"Viento {sector}",
    )

    fig.update_layout(
        title=f"Vista en planta - sector {sector} ({direction_deg:.1f}°)",
        template="plotly_white",
        height=620,
        margin=dict(l=40, r=40, t=60, b=40),
    )

    fig.update_xaxes(title_text="X (m)", zeroline=True)
    fig.update_yaxes(title_text="Y (m)", scaleanchor="x", scaleratio=1, zeroline=True)

    return fig
