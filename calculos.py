import csv
import io
import json
import random
import re
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


RHO_REF_ESTANDAR = 1.225
ESCALA_ALTURA_BAROMETRICA_M = 8434.5
CONSTANTE_GAS_AIRE = 287.058


def calcular_densidad_sitio(altitud_m, temperatura_c, p0_pa=101325.0):
    try:
        z = float(altitud_m)
    except (TypeError, ValueError):
        z = 0.0
    try:
        t_c = float(temperatura_c)
    except (TypeError, ValueError):
        t_c = 15.0
    t_k = t_c + 273.15
    if t_k <= 0:
        return float("nan")
    p = float(p0_pa) * np.exp(-max(z, 0.0) / ESCALA_ALTURA_BAROMETRICA_M)
    return p / (CONSTANTE_GAS_AIRE * t_k)


def factor_correccion_densidad(rho_sitio, rho_ref=RHO_REF_ESTANDAR):
    try:
        rho = float(rho_sitio)
    except (TypeError, ValueError):
        return 1.0
    if not np.isfinite(rho) or rho <= 0:
        return 1.0
    ref = float(rho_ref) if rho_ref else RHO_REF_ESTANDAR
    if ref <= 0:
        return 1.0
    return rho / ref


def calcular_serie_densidad(df_nasa, altitud_m=0.0, temperatura_fallback_c=15.0):
    """Devuelve serie de densidad (kg/m³) por hora.

    Usa T2M de NASA POWER si está disponible; sino fallback temperatura_fallback_c.
    Usa PS (presión superficial kPa) si disponible; sino fórmula barométrica.
    """
    if df_nasa is None or len(df_nasa) == 0:
        return pd.Series(dtype=float)

    n = len(df_nasa)

    if "T2M" in df_nasa.columns:
        t2m = pd.to_numeric(df_nasa["T2M"], errors="coerce").to_numpy(dtype=float)
        t2m = np.where(np.isfinite(t2m), t2m, float(temperatura_fallback_c))
    else:
        t2m = np.full(n, float(temperatura_fallback_c))

    t_k = t2m + 273.15

    z = max(0.0, float(altitud_m))
    p0_barometric_pa = 101325.0 * np.exp(-z / ESCALA_ALTURA_BAROMETRICA_M)

    if "PS" in df_nasa.columns:
        ps_kpa = pd.to_numeric(df_nasa["PS"], errors="coerce").to_numpy(dtype=float)
        p_pa = np.where(np.isfinite(ps_kpa) & (ps_kpa > 0), ps_kpa * 1000.0, p0_barometric_pa)
    else:
        p_pa = np.full(n, p0_barometric_pa)

    rho = p_pa / (CONSTANTE_GAS_AIRE * np.where(t_k > 0, t_k, 273.15 + temperatura_fallback_c))
    rho = np.where(np.isfinite(rho) & (rho > 0), rho, RHO_REF_ESTANDAR)

    return pd.Series(rho, index=df_nasa.index, name="densidad_kg_m3")


def agregar_densidad_mensual(df_nasa, altitud_m=0.0, temperatura_fallback_c=15.0):
    """Devuelve dict {mes: ρ_medio} + ρ_anual."""
    serie_rho = calcular_serie_densidad(df_nasa, altitud_m, temperatura_fallback_c)
    if len(serie_rho) == 0:
        return {"mensual": {}, "anual": RHO_REF_ESTANDAR, "n_validos": 0}

    if "MO" in df_nasa.columns:
        meses = pd.to_numeric(df_nasa["MO"], errors="coerce").to_numpy(dtype=int)
    elif "timestamp" in df_nasa.columns:
        meses = pd.to_datetime(df_nasa["timestamp"], errors="coerce").dt.month.to_numpy()
    else:
        return {"mensual": {}, "anual": float(serie_rho.mean()), "n_validos": int(len(serie_rho))}

    mensual = {}
    for m in range(1, 13):
        mask = meses == m
        if mask.any():
            mensual[m] = float(serie_rho[mask].mean())

    return {
        "mensual": mensual,
        "anual": float(serie_rho.mean()),
        "n_validos": int(len(serie_rho)),
    }


def interpolar_potencia_corregida(curva_df, velocidades, factor_densidad=1.0):
    base = interpolar_potencia_curva_preparada(curva_df, velocidades)
    try:
        factor = float(factor_densidad)
    except (TypeError, ValueError):
        factor = 1.0
    if not np.isfinite(factor) or factor <= 0:
        factor = 1.0
    return base * factor


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


def turbinas_xy_a_latlon(df_layout, lat_centro, lon_centro, rotation_deg=0.0):
    """Convierte x_m/y_m relativos (origen = centro del parque) a lat/lon absolutos.

    Aproximación planar: 1° lat ≈ 111000 m, 1° lon ≈ 111000·cos(lat) m.
    Válido para parques < ~50 km (error <0.1%).
    rotation_deg: rotación opcional del sistema xy respecto a N/E (0=norte arriba).
    """
    if df_layout is None or len(df_layout) == 0:
        return pd.DataFrame(columns=["turbina_id", "lat", "lon"])
    if not (np.isfinite(lat_centro) and np.isfinite(lon_centro)):
        return pd.DataFrame(columns=["turbina_id", "lat", "lon"])

    lat0 = float(lat_centro)
    lon0 = float(lon_centro)
    lat_rad = np.deg2rad(lat0)
    m_per_deg_lat = 111000.0
    m_per_deg_lon = 111000.0 * np.cos(lat_rad)
    if m_per_deg_lon <= 0:
        m_per_deg_lon = 111000.0

    theta = np.deg2rad(float(rotation_deg))
    cos_t, sin_t = np.cos(theta), np.sin(theta)

    out = df_layout.copy()
    xs = pd.to_numeric(out.get("x_m"), errors="coerce").to_numpy(dtype=float)
    ys = pd.to_numeric(out.get("y_m"), errors="coerce").to_numpy(dtype=float)
    # Rotación: viento positivo X = oeste→este, Y = sur→norte por defecto
    x_rot = xs * cos_t - ys * sin_t
    y_rot = xs * sin_t + ys * cos_t

    out["lat"] = lat0 + y_rot / m_per_deg_lat
    out["lon"] = lon0 + x_rot / m_per_deg_lon
    return out[["turbina_id", "lat", "lon"]] if "turbina_id" in out.columns else out[["lat", "lon"]]


def _sector_from_direction(deg, n_sectores=12):
    if not np.isfinite(deg):
        return -1
    step = 360.0 / int(n_sectores)
    return int((float(deg) % 360.0) // step)


def mcp_lineal_global(df_sat, df_torre, ws_sat_col="WS50M", ws_torre_col="ws_10min"):
    if df_sat is None or df_torre is None:
        return {"a": 1.0, "b": 0.0, "r2": float("nan"), "n_samples": 0, "rmse": float("nan"), "bias": float("nan")}
    sat = df_sat[["timestamp", ws_sat_col]].copy()
    torre = df_torre[["timestamp", ws_torre_col]].copy()
    sat["timestamp"] = pd.to_datetime(sat["timestamp"], errors="coerce")
    torre["timestamp"] = pd.to_datetime(torre["timestamp"], errors="coerce")
    sat = sat.dropna().rename(columns={ws_sat_col: "ws_sat"})
    torre = torre.dropna().rename(columns={ws_torre_col: "ws_torre"})
    sat["timestamp_h"] = sat["timestamp"].dt.floor("h")
    torre["timestamp_h"] = torre["timestamp"].dt.floor("h")
    sat = sat.groupby("timestamp_h", as_index=False)["ws_sat"].mean()
    torre = torre.groupby("timestamp_h", as_index=False)["ws_torre"].mean()
    merged = sat.merge(torre, on="timestamp_h", how="inner")
    if len(merged) < 10:
        return {"a": 1.0, "b": 0.0, "r2": float("nan"), "n_samples": len(merged), "rmse": float("nan"), "bias": float("nan")}
    x = merged["ws_sat"].to_numpy(dtype=float)
    y = merged["ws_torre"].to_numpy(dtype=float)
    n = len(x)
    a, b = np.polyfit(x, y, 1)
    y_pred = a * x + b
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    rmse = float(np.sqrt(ss_res / n))
    bias = float(np.mean(y_pred - y))
    return {"a": float(a), "b": float(b), "r2": float(r2), "n_samples": int(n), "rmse": rmse, "bias": bias,
            "x_obs": x.tolist(), "y_obs": y.tolist(), "merged_df": merged}


def mcp_lineal_sectorial(df_sat, df_torre, ws_sat_col="WS50M", wd_sat_col="WD50M", ws_torre_col="ws_10min", wd_torre_col="wd_10min", n_sectores=12):
    if df_sat is None or df_torre is None:
        return {"sectores": {}, "global": mcp_lineal_global(df_sat, df_torre, ws_sat_col, ws_torre_col)}
    sat = df_sat[["timestamp", ws_sat_col, wd_sat_col]].copy()
    torre = df_torre[["timestamp", ws_torre_col, wd_torre_col]].copy() if wd_torre_col in df_torre.columns else df_torre[["timestamp", ws_torre_col]].copy()
    sat["timestamp"] = pd.to_datetime(sat["timestamp"], errors="coerce")
    torre["timestamp"] = pd.to_datetime(torre["timestamp"], errors="coerce")
    sat = sat.dropna(subset=["timestamp", ws_sat_col, wd_sat_col]).copy()
    sat["timestamp_h"] = sat["timestamp"].dt.floor("h")
    torre = torre.dropna(subset=["timestamp"]).copy()
    torre["timestamp_h"] = torre["timestamp"].dt.floor("h")
    sat_agg = sat.groupby("timestamp_h", as_index=False).agg({ws_sat_col: "mean", wd_sat_col: "mean"})
    torre_agg = torre.groupby("timestamp_h", as_index=False).agg({ws_torre_col: "mean"})
    merged = sat_agg.merge(torre_agg, on="timestamp_h", how="inner")
    if len(merged) < 30:
        return {"sectores": {}, "global": mcp_lineal_global(df_sat, df_torre, ws_sat_col, ws_torre_col)}

    sectores = {}
    step = 360.0 / int(n_sectores)
    for s in range(int(n_sectores)):
        lo = s * step
        hi = (s + 1) * step
        mask = (merged[wd_sat_col] >= lo) & (merged[wd_sat_col] < hi)
        sub = merged[mask]
        if len(sub) < 20:
            sectores[s] = {"a": 1.0, "b": 0.0, "r2": float("nan"), "n_samples": int(len(sub)), "rmse": float("nan"), "lo": lo, "hi": hi}
            continue
        x = sub[ws_sat_col].to_numpy(dtype=float)
        y = sub[ws_torre_col].to_numpy(dtype=float)
        try:
            a, b = np.polyfit(x, y, 1)
            y_pred = a * x + b
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
            rmse = float(np.sqrt(ss_res / len(x)))
        except Exception:
            a, b, r2, rmse = 1.0, 0.0, float("nan"), float("nan")
        sectores[s] = {"a": float(a), "b": float(b), "r2": float(r2), "n_samples": int(len(sub)), "rmse": rmse, "lo": lo, "hi": hi}

    global_res = mcp_lineal_global(df_sat, df_torre, ws_sat_col, ws_torre_col)
    return {"sectores": sectores, "global": global_res, "n_sectores": int(n_sectores)}


def aplicar_mcp(df_sat, mcp_params, ws_col="WS50M", wd_col="WD50M", sectorial=True):
    if df_sat is None or len(df_sat) == 0:
        return pd.Series(dtype=float)
    df = df_sat.copy()
    ws = pd.to_numeric(df[ws_col], errors="coerce").to_numpy(dtype=float)
    out = np.full(len(ws), np.nan)

    if sectorial and "sectores" in mcp_params and mcp_params.get("sectores"):
        wd = pd.to_numeric(df[wd_col], errors="coerce").to_numpy(dtype=float)
        n_sec = mcp_params.get("n_sectores", 12)
        step = 360.0 / int(n_sec)
        for s, coefs in mcp_params["sectores"].items():
            try:
                s_int = int(s)
            except Exception:
                continue
            lo = s_int * step
            hi = (s_int + 1) * step
            mask = (wd >= lo) & (wd < hi) & np.isfinite(ws)
            out[mask] = coefs["a"] * ws[mask] + coefs["b"]
        # fallback global for missed sectors
        global_a = mcp_params.get("global", {}).get("a", 1.0)
        global_b = mcp_params.get("global", {}).get("b", 0.0)
        mask_missed = np.isnan(out) & np.isfinite(ws)
        out[mask_missed] = global_a * ws[mask_missed] + global_b
    else:
        a = mcp_params.get("global", mcp_params).get("a", 1.0)
        b = mcp_params.get("global", mcp_params).get("b", 0.0)
        mask = np.isfinite(ws)
        out[mask] = a * ws[mask] + b

    out = np.clip(out, 0.0, 60.0)
    return pd.Series(out, index=df.index, name="WS_MCP")


def calcular_alpha_desde_serie(df_nasa, ws_col_low="WS10M", ws_col_high="WS50M", z_low=10.0, z_high=50.0, v_min=0.5):
    if df_nasa is None or len(df_nasa) == 0:
        return {"mediana": float("nan"), "p25": float("nan"), "p75": float("nan"), "media": float("nan"), "n_validos": 0}
    if ws_col_low not in df_nasa.columns or ws_col_high not in df_nasa.columns:
        return {"mediana": float("nan"), "p25": float("nan"), "p75": float("nan"), "media": float("nan"), "n_validos": 0}
    if z_low <= 0 or z_high <= 0 or z_low == z_high:
        return {"mediana": float("nan"), "p25": float("nan"), "p75": float("nan"), "media": float("nan"), "n_validos": 0}

    v_low = pd.to_numeric(df_nasa[ws_col_low], errors="coerce").to_numpy(dtype=float)
    v_high = pd.to_numeric(df_nasa[ws_col_high], errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(v_low) & np.isfinite(v_high) & (v_low > v_min) & (v_high > v_min)
    if not mask.any():
        return {"mediana": float("nan"), "p25": float("nan"), "p75": float("nan"), "media": float("nan"), "n_validos": 0}

    ln_ratio_z = np.log(float(z_high) / float(z_low))
    alphas = np.log(v_high[mask] / v_low[mask]) / ln_ratio_z
    alphas = alphas[np.isfinite(alphas)]
    alphas = alphas[(alphas > -1.0) & (alphas < 2.0)]
    if alphas.size == 0:
        return {"mediana": float("nan"), "p25": float("nan"), "p75": float("nan"), "media": float("nan"), "n_validos": 0}
    return {
        "mediana": float(np.median(alphas)),
        "p25": float(np.percentile(alphas, 25)),
        "p75": float(np.percentile(alphas, 75)),
        "media": float(np.mean(alphas)),
        "n_validos": int(alphas.size),
    }


def calcular_ti_serie(serie_velocidad, bin_v=1.0, v_min=1.0, v_max=30.0):
    if serie_velocidad is None:
        return {"ti_15ms": float("nan"), "ti_mean": float("nan"), "sigma_total": float("nan"), "v_mean": float("nan"), "n_validos": 0, "df_ti_por_bin": pd.DataFrame()}
    arr = np.asarray(pd.to_numeric(pd.Series(serie_velocidad), errors="coerce"), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 20:
        return {"ti_15ms": float("nan"), "ti_mean": float("nan"), "sigma_total": float("nan"), "v_mean": float("nan"), "n_validos": int(arr.size), "df_ti_por_bin": pd.DataFrame()}

    mean_total = float(np.mean(arr))
    sigma_total = float(np.std(arr, ddof=1))
    ti_mean = sigma_total / mean_total if mean_total > 0 else float("nan")

    edges = np.arange(v_min, v_max + bin_v, bin_v)
    centros, sigmas, medias, counts, tis = [], [], [], [], []
    for lo in edges[:-1]:
        hi = lo + bin_v
        sub = arr[(arr >= lo) & (arr < hi)]
        if sub.size >= 5:
            mu = float(np.mean(sub))
            sd = float(np.std(sub, ddof=1)) if sub.size > 1 else 0.0
            centros.append(lo + bin_v / 2.0)
            sigmas.append(sd)
            medias.append(mu)
            counts.append(int(sub.size))
            tis.append(sd / mu if mu > 0 else float("nan"))

    df_ti = pd.DataFrame({
        "v_centro": centros,
        "v_mean_bin": medias,
        "sigma_bin": sigmas,
        "n": counts,
        "TI": tis,
    })

    ti_15 = float("nan")
    if len(df_ti) >= 2:
        ti_15 = float(np.interp(15.0, df_ti["v_centro"].to_numpy(), df_ti["TI"].to_numpy(), left=float("nan"), right=float("nan")))
        if not np.isfinite(ti_15):
            sub = df_ti[(df_ti["v_centro"] >= 10.0) & (df_ti["v_centro"] <= 20.0)]
            if len(sub) > 0:
                ti_15 = float(sub["TI"].mean())

    return {
        "ti_15ms": ti_15,
        "ti_mean": ti_mean,
        "sigma_total": sigma_total,
        "v_mean": mean_total,
        "n_validos": int(arr.size),
        "df_ti_por_bin": df_ti,
    }


IEC_CLASES_VELOCIDAD = {
    "I": {"v_ref": 50.0, "v_avg": 10.0},
    "II": {"v_ref": 42.5, "v_avg": 8.5},
    "III": {"v_ref": 37.5, "v_avg": 7.5},
    "S": {"v_ref": float("nan"), "v_avg": float("nan")},
}
IEC_CATEGORIAS_TURBULENCIA = {
    "A": 0.16,
    "B": 0.14,
    "C": 0.12,
    "S": float("nan"),
}


def calcular_v_ref_50years(serie_velocidad, df_index=None, metodo="Gumbel"):
    """Extreme value V_ref con periodo de retorno 50 años.

    Si df_index tiene columna 'YEAR', usa máximos anuales (block maxima).
    Si no, usa POT con percentil 99.
    Returns dict {v_ref_50y, v_ref_10y, metodo, n_anios, gumbel_params}.
    """
    try:
        from scipy.stats import gumbel_r
    except ImportError:
        return {"v_ref_50y": float("nan"), "v_ref_10y": float("nan"), "metodo": "scipy-missing", "n_anios": 0}

    arr = np.asarray(pd.to_numeric(pd.Series(serie_velocidad), errors="coerce").dropna(), dtype=float)
    arr = arr[np.isfinite(arr) & (arr >= 0)]
    if arr.size < 100:
        return {"v_ref_50y": float("nan"), "v_ref_10y": float("nan"), "metodo": "datos-insuficientes", "n_anios": 0}

    if df_index is not None and "YEAR" in df_index.columns:
        df_tmp = df_index.copy()
        df_tmp["_v"] = pd.to_numeric(serie_velocidad, errors="coerce")
        max_anuales = df_tmp.groupby("YEAR")["_v"].max().dropna()
        n_anios = len(max_anuales)
        if n_anios >= 3:
            loc, scale = gumbel_r.fit(max_anuales.values)
            v_50 = float(gumbel_r.ppf(1 - 1/50, loc, scale))
            v_10 = float(gumbel_r.ppf(1 - 1/10, loc, scale))
            return {"v_ref_50y": v_50, "v_ref_10y": v_10, "metodo": "Gumbel-block-maxima", "n_anios": int(n_anios),
                    "gumbel_loc": float(loc), "gumbel_scale": float(scale)}

    # POT fallback
    p99 = float(np.percentile(arr, 99))
    p99_9 = float(np.percentile(arr, 99.9))
    return {"v_ref_50y": p99_9 * 1.4, "v_ref_10y": p99 * 1.3, "metodo": "POT-percentil-aproximacion",
            "n_anios": max(1, int(arr.size / 8760))}


def calcular_ti_por_sector(df_nasa, ws_col="WS50M", wd_col="WD50M", n_sectores=16, v_min=3.0):
    """TI por sector direccional usando WS std/mean en cada bin direccional."""
    if df_nasa is None or len(df_nasa) == 0:
        return {}
    ws = pd.to_numeric(df_nasa[ws_col], errors="coerce").to_numpy(dtype=float)
    wd = pd.to_numeric(df_nasa[wd_col], errors="coerce").to_numpy(dtype=float)
    mask_valid = np.isfinite(ws) & np.isfinite(wd) & (ws >= v_min) & (ws <= 40)
    ws = ws[mask_valid]
    wd = wd[mask_valid] % 360

    step = 360.0 / n_sectores
    out = {}
    labels = SECTOR_LABELS_16 if n_sectores == 16 else [f"S{i+1}" for i in range(n_sectores)]
    centers = np.arange(0, 360, step)
    for i, c in enumerate(centers):
        lo = (c - step/2) % 360
        hi = (c + step/2) % 360
        if lo < hi:
            m = (wd >= lo) & (wd < hi)
        else:
            m = (wd >= lo) | (wd < hi)
        sub = ws[m]
        if sub.size > 20:
            sigma = float(np.std(sub, ddof=1))
            mu = float(np.mean(sub))
            ti = sigma / mu if mu > 0 else float("nan")
        else:
            ti = float("nan")
            mu = float("nan")
        label = labels[i] if i < len(labels) else f"S{i+1}"
        out[label] = {"ti": ti, "v_mean": mu, "n": int(sub.size)}
    return out


def calcular_inflow_angle(df_nasa, ws_col_low="WS10M", ws_col_high="WS50M", z_low=10, z_high=50, terrain_slope_deg=0.0):
    """Inflow angle = ángulo verticalmente del flujo. IEC: límite ±8° en terreno complejo.
    Approximación: inflow = terrain_slope (asume flujo paralelo al terreno).
    Más sofisticado requiere medición torre o CFD.
    """
    return {"inflow_angle_deg": float(terrain_slope_deg),
            "limite_iec_deg": 8.0,
            "cumple": abs(float(terrain_slope_deg)) <= 8.0}


def validar_iec_61400_1_completo(
    df_nasa, ws_col="WS50M", wd_col="WD50M",
    clase_declarada="II", categoria_declarada="B",
    h_hub=80.0, alpha_user=0.14, terrain_slope_deg=0.0,
):
    """IEC 61400-1 Ed.4 site suitability completo. 6 criterios checklist."""
    serie = pd.to_numeric(df_nasa[ws_col], errors="coerce").to_numpy(dtype=float)
    serie = serie[np.isfinite(serie) & (serie >= 0)]

    v_avg = float(np.mean(serie)) if serie.size > 0 else float("nan")
    ti_res = calcular_ti_serie(serie)
    ti_15 = ti_res.get("ti_15ms", float("nan"))

    v_ref_res = calcular_v_ref_50years(pd.Series(serie), df_index=df_nasa)
    v_ref_50y = v_ref_res.get("v_ref_50y", float("nan"))

    p90_ti = float("nan")
    if ti_res.get("df_ti_por_bin") is not None and len(ti_res["df_ti_por_bin"]) > 0:
        tis = ti_res["df_ti_por_bin"]["TI"].dropna()
        if len(tis) > 0:
            p90_ti = float(tis.quantile(0.9))

    inflow_res = calcular_inflow_angle(df_nasa, terrain_slope_deg=terrain_slope_deg)

    iec_class = clase_declarada.upper() if clase_declarada else "II"
    iec_cat = categoria_declarada.upper() if categoria_declarada else "B"
    v_avg_clase = IEC_CLASES_VELOCIDAD.get(iec_class, {}).get("v_avg", float("nan"))
    v_ref_clase = IEC_CLASES_VELOCIDAD.get(iec_class, {}).get("v_ref", float("nan"))
    ti_clase = IEC_CATEGORIAS_TURBULENCIA.get(iec_cat, float("nan"))

    cumple_v_avg = bool(v_avg <= v_avg_clase) if np.isfinite(v_avg) and np.isfinite(v_avg_clase) else None
    cumple_v_ref = bool(v_ref_50y <= v_ref_clase) if np.isfinite(v_ref_50y) and np.isfinite(v_ref_clase) else None
    cumple_ti = bool(ti_15 <= ti_clase) if np.isfinite(ti_15) and np.isfinite(ti_clase) else None
    cumple_ti_p90 = bool(p90_ti <= ti_clase * 1.4) if np.isfinite(p90_ti) and np.isfinite(ti_clase) else None
    cumple_shear = bool(0 <= float(alpha_user) <= 0.20)
    cumple_inflow = inflow_res.get("cumple")

    checks = [cumple_v_avg, cumple_v_ref, cumple_ti, cumple_ti_p90, cumple_shear, cumple_inflow]
    valid_checks = [c for c in checks if c is not None]
    cumple_global = all(c is True for c in valid_checks) if valid_checks else None

    return {
        "clase": iec_class,
        "categoria": iec_cat,
        "v_avg": {"sitio": v_avg, "limite": v_avg_clase, "cumple": cumple_v_avg},
        "v_ref_50y": {"sitio": v_ref_50y, "limite": v_ref_clase, "cumple": cumple_v_ref,
                      "metodo": v_ref_res.get("metodo", ""), "n_anios": v_ref_res.get("n_anios", 0)},
        "ti_15ms": {"sitio": ti_15, "limite": ti_clase, "cumple": cumple_ti},
        "ti_p90": {"sitio": p90_ti, "limite": ti_clase * 1.4 if np.isfinite(ti_clase) else float("nan"), "cumple": cumple_ti_p90},
        "shear_alpha": {"sitio": float(alpha_user), "rango": [0, 0.20], "cumple": cumple_shear},
        "inflow": {"sitio": inflow_res["inflow_angle_deg"], "limite": inflow_res["limite_iec_deg"], "cumple": cumple_inflow},
        "cumple_global": cumple_global,
        "gumbel_params": {"loc": v_ref_res.get("gumbel_loc"), "scale": v_ref_res.get("gumbel_scale")},
    }


def clasificar_iec_61400_1(v_avg, ti_15, clase_declarada="II", categoria_declarada="B"):
    clase = str(clase_declarada or "II").upper().strip()
    cat = str(categoria_declarada or "B").upper().strip()
    if clase not in IEC_CLASES_VELOCIDAD:
        clase = "S"
    if cat not in IEC_CATEGORIAS_TURBULENCIA:
        cat = "S"
    v_avg_clase = IEC_CLASES_VELOCIDAD[clase]["v_avg"]
    v_ref_clase = IEC_CLASES_VELOCIDAD[clase]["v_ref"]
    ti_clase = IEC_CATEGORIAS_TURBULENCIA[cat]

    cumple_v = bool(v_avg <= v_avg_clase) if (np.isfinite(v_avg_clase) and np.isfinite(v_avg)) else None
    cumple_ti = bool(ti_15 <= ti_clase) if (np.isfinite(ti_clase) and np.isfinite(ti_15)) else None
    if cumple_v is None or cumple_ti is None:
        cumple = None
    else:
        cumple = bool(cumple_v and cumple_ti)

    return {
        "clase_velocidad": clase,
        "clase_turbulencia": cat,
        "v_avg_sitio": float(v_avg) if np.isfinite(v_avg) else float("nan"),
        "ti_15_sitio": float(ti_15) if np.isfinite(ti_15) else float("nan"),
        "v_avg_clase": v_avg_clase,
        "v_ref_clase": v_ref_clase,
        "ti_clase": ti_clase,
        "cumple_velocidad": cumple_v,
        "cumple_turbulencia": cumple_ti,
        "cumple": cumple,
    }


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
        f"?parameters=WS10M,WS50M,WD10M,WD50M,T2M,PS"
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
    optional = ["WD10M", "WD50M", "T2M", "PS"]

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
        ["timestamp", "YEAR", "MO", "DY", "HR", "WS10M", "WS50M", "WD10M", "WD50M", "T2M", "PS"]
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
def calcular_estelas_larsen_direccion(df_layout, wind_speed, direction_deg, diametro, ct=0.8, ambient_ti=0.10, h_hub=80.0, curva_df=None):
    if diametro <= 0:
        raise ValueError("El diámetro debe ser mayor que 0.")
    if not (0 < ct < 1):
        raise ValueError("Ct debe estar entre 0 y 1.")
    if wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    dfp = _proyectar_layout_sobre_viento(df_layout, direction_deg).copy()
    dfp = dfp.sort_values("x_down").reset_index(drop=True)

    n = len(dfp)
    deficits = np.zeros(n, dtype=float)

    R = float(diametro) / 2.0
    A = np.pi * R * R
    ti = max(0.01, float(ambient_ti))
    H = max(10.0, float(h_hub))

    R_nb = R * (0.5 * (1.0 + np.sqrt(1.0 - ct))) ** 0.5
    Rb_term = 1.08 * R + 21.7 * R * (ti - 0.05)
    R_95 = max(Rb_term, R_nb)
    deff = max(1e-3, R_95 - R_nb)
    x0 = 9.5 * R / ((2.0 * R_95 / deff) ** 3 - 1.0)
    c1 = (105.0 / (2.0 * np.pi)) ** (-0.5) * (ct * A * x0) ** (5.0 / 6.0)

    for j in range(n):
        dlist = []
        xj = float(dfp.loc[j, "x_down"])
        yj = float(dfp.loc[j, "y_cross"])

        for i in range(j):
            xi = float(dfp.loc[i, "x_down"])
            yi = float(dfp.loc[i, "y_cross"])

            dx = xj - xi
            r_radial = abs(yj - yi)

            if dx <= 0:
                continue

            x_eff = dx + x0
            if x_eff <= 0:
                continue
            r_wake = ((35.0 / (2.0 * np.pi)) ** (1.0 / 5.0)) * ((3.0 * c1 * c1) ** (1.0 / 5.0)) * (ct * A * x_eff) ** (1.0 / 3.0)
            if r_radial > r_wake:
                continue

            term_a = ct * A * (x_eff ** -2.0)
            term_b = (r_radial ** 1.5) * (3.0 * c1 * c1 * ct * A * x_eff) ** -0.5 - (35.0 / (2.0 * np.pi)) ** (3.0 / 10.0) * (3.0 * c1 * c1) ** -0.2
            deficit_ij = (1.0 / 9.0) * (term_a ** (1.0 / 3.0)) * (term_b ** 2.0)
            if not np.isfinite(deficit_ij) or deficit_ij < 0:
                deficit_ij = 0.0
            dlist.append(min(deficit_ij, 0.999))

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
def calcular_estelas_frandsen_direccion(df_layout, wind_speed, direction_deg, diametro, ct=0.8, kw_frand=0.06, curva_df=None):
    if diametro <= 0:
        raise ValueError("El diámetro debe ser mayor que 0.")
    if not (0 < ct < 1):
        raise ValueError("Ct debe estar entre 0 y 1.")
    if wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    dfp = _proyectar_layout_sobre_viento(df_layout, direction_deg).copy()
    dfp = dfp.sort_values("x_down").reset_index(drop=True)

    n = len(dfp)
    deficits = np.zeros(n, dtype=float)

    R = float(diametro) / 2.0
    beta = 0.5 * (1.0 + np.sqrt(1.0 - ct)) / np.sqrt(max(1e-6, 1.0 - ct))
    alpha = float(kw_frand) if kw_frand and kw_frand > 0 else 0.06

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

            d_eff = diametro * np.sqrt(max(0.0, beta + alpha * dx / diametro))
            r_eff = d_eff / 2.0
            if dy > r_eff:
                continue

            ratio = (diametro / max(d_eff, 1e-6)) ** 2
            deficit_ij = 0.5 * (1.0 - np.sqrt(max(0.0, 1.0 - 2.0 * ct * ratio)))
            if not np.isfinite(deficit_ij) or deficit_ij < 0:
                deficit_ij = 0.0
            dlist.append(min(deficit_ij, 0.999))

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
def calcular_estelas_gaussian_direccion(df_layout, wind_speed, direction_deg, diametro, ct=0.8, ambient_ti=0.10, kstar=0.038, curva_df=None):
    """Bastankhah & Porté-Agel 2014 — Gaussian wake."""
    if diametro <= 0:
        raise ValueError("El diámetro debe ser mayor que 0.")
    if not (0 < ct < 1):
        raise ValueError("Ct debe estar entre 0 y 1.")
    if wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    ti = max(0.02, float(ambient_ti))
    kstar_eff = float(kstar) if kstar and kstar > 0 else (0.32 * ti + 0.0035)

    dfp = _proyectar_layout_sobre_viento(df_layout, direction_deg).copy()
    dfp = dfp.sort_values("x_down").reset_index(drop=True)

    n = len(dfp)
    deficits = np.zeros(n, dtype=float)

    eps = 0.25 * np.sqrt(0.5 * (1.0 + np.sqrt(1.0 - ct)) / np.sqrt(max(1e-6, 1.0 - ct)))

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

            sigma_over_D = kstar_eff * dx / diametro + eps
            sigma = sigma_over_D * diametro
            if sigma <= 0:
                continue

            ct_over_8sigmaD2 = ct / (8.0 * sigma_over_D * sigma_over_D)
            if ct_over_8sigmaD2 >= 1.0:
                continue
            amplitude = 1.0 - np.sqrt(1.0 - ct_over_8sigmaD2)
            radial = np.exp(-0.5 * (dy / sigma) ** 2)
            deficit_ij = amplitude * radial
            if not np.isfinite(deficit_ij) or deficit_ij < 0:
                deficit_ij = 0.0
            dlist.append(min(deficit_ij, 0.999))

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
def calcular_estelas_turbopark_direccion(df_layout, wind_speed, direction_deg, diametro, ct=0.8, ambient_ti=0.10, A=0.04, curva_df=None):
    """TurbOPark (Pedersen/Orsted 2020) — Gaussian deficit + added wake turbulence (Frandsen)."""
    if diametro <= 0:
        raise ValueError("El diámetro debe ser mayor que 0.")
    if not (0 < ct < 1):
        raise ValueError("Ct debe estar entre 0 y 1.")
    if wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    ti_amb = max(0.02, float(ambient_ti))
    A_eff = float(A) if A and A > 0 else 0.04

    dfp = _proyectar_layout_sobre_viento(df_layout, direction_deg).copy()
    dfp = dfp.sort_values("x_down").reset_index(drop=True)

    n = len(dfp)
    deficits = np.zeros(n, dtype=float)

    eps = 0.25 * np.sqrt(0.5 * (1.0 + np.sqrt(1.0 - ct)) / np.sqrt(max(1e-6, 1.0 - ct)))

    for j in range(n):
        dlist_squared = 0.0
        xj = float(dfp.loc[j, "x_down"])
        yj = float(dfp.loc[j, "y_cross"])

        for i in range(j):
            xi = float(dfp.loc[i, "x_down"])
            yi = float(dfp.loc[i, "y_cross"])

            dx = xj - xi
            dy = abs(yj - yi)

            if dx <= 0:
                continue

            x_over_D = dx / diametro
            ti_added = 1.0 / (1.5 + 0.8 * x_over_D / np.sqrt(max(1e-6, ct)))
            ti_eff = np.sqrt(ti_amb * ti_amb + ti_added * ti_added)

            sigma_over_D = eps + A_eff * ti_eff * x_over_D
            sigma = sigma_over_D * diametro
            if sigma <= 0:
                continue

            ct_over_8sigmaD2 = ct / (8.0 * sigma_over_D * sigma_over_D)
            if ct_over_8sigmaD2 >= 1.0:
                continue
            amplitude = 1.0 - np.sqrt(1.0 - ct_over_8sigmaD2)
            radial = np.exp(-0.5 * (dy / sigma) ** 2)
            deficit_ij = amplitude * radial
            if not np.isfinite(deficit_ij) or deficit_ij < 0:
                deficit_ij = 0.0
            dlist_squared += min(deficit_ij, 0.999) ** 2

        deficits[j] = min(np.sqrt(dlist_squared), 0.999)

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


def _pywake_disponible():
    try:
        import py_wake  # noqa: F401
        return True
    except ImportError:
        return False


@st.cache_data(show_spinner=False)
def calcular_estelas_pywake_direccion(
    df_layout, wind_speed, direction_deg, diametro,
    ct=0.8, ambient_ti=0.10, modelo_pywake="Bastankhah",
    curva_df=None, h_hub=80.0,
):
    """Backend py_wake DTU. Modelos: NOJ, Bastankhah, TurbOPark (Niayifar), Niayifar."""
    import warnings

    from py_wake import NOJ, BastankhahGaussian, NiayifarGaussian
    from py_wake.site._site import UniformSite
    from py_wake.wind_turbines import WindTurbine
    from py_wake.wind_turbines.power_ct_functions import PowerCtTabular
    try:
        from py_wake.turbulence_models import STF2017TurbulenceModel
    except ImportError:
        STF2017TurbulenceModel = None

    if diametro <= 0:
        raise ValueError("El diámetro debe ser mayor que 0.")
    if not (0 < ct < 1):
        raise ValueError("Ct debe estar entre 0 y 1.")
    if wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    n = len(df_layout)
    if n == 0:
        return pd.DataFrame()

    if curva_df is not None and len(curva_df) > 0:
        curva_prep = preparar_datos_curva(curva_df) if "Velocidad_num" not in curva_df.columns else curva_df
        v_curve = curva_prep["Velocidad_num"].to_numpy(dtype=float)
        p_curve = curva_prep["Potencia_W"].to_numpy(dtype=float)
        ct_curve = np.full_like(v_curve, float(ct), dtype=float)
        wt = WindTurbine(
            name="SMA_WT",
            diameter=float(diametro),
            hub_height=float(h_hub),
            powerCtFunction=PowerCtTabular(v_curve, p_curve, "w", ct_curve),
        )
    else:
        wt = WindTurbine(
            name="SMA_default",
            diameter=float(diametro),
            hub_height=float(h_hub),
            powerCtFunction=PowerCtTabular(
                u=[0, 3, 12, 25],
                power=[0, 0, 3e6, 3e6],
                power_unit="w",
                ct=[0, ct, ct, ct],
            ),
        )

    site = UniformSite(p_wd=[1.0], ti=float(ambient_ti))

    m_key = str(modelo_pywake).lower().strip()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if m_key == "noj":
            wake_engine = NOJ(site, wt)
        elif m_key in ("niayifar", "turbopark"):
            if STF2017TurbulenceModel is not None:
                wake_engine = NiayifarGaussian(site, wt, turbulenceModel=STF2017TurbulenceModel())
            else:
                wake_engine = BastankhahGaussian(site, wt)
        else:  # bastankhah default
            wake_engine = BastankhahGaussian(site, wt)

    x = pd.to_numeric(df_layout["x_m"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(df_layout["y_m"], errors="coerce").to_numpy(dtype=float)

    sim_res = wake_engine(x, y, wd=[float(direction_deg)], ws=[float(wind_speed)])

    p_wake = np.asarray(sim_res.Power.values).flatten()
    ws_eff = np.asarray(sim_res.WS_eff.values).flatten()
    if len(p_wake) != n:
        p_wake = np.resize(p_wake, n)
        ws_eff = np.resize(ws_eff, n)

    try:
        p_base_val = wt.power(float(wind_speed))
        p_base = float(p_base_val) if not hasattr(p_base_val, '__len__') else float(p_base_val[0])
    except Exception:
        p_base = float(np.interp(float(wind_speed), v_curve, p_curve)) if curva_df is not None and len(curva_df) > 0 else 3e6

    deficits = np.clip(1.0 - ws_eff / max(float(wind_speed), 1e-6), 0.0, 0.999999)

    # Construir DataFrame en orden original df_layout (py_wake mantiene orden de entrada)
    dfp_proj = _proyectar_layout_sobre_viento(df_layout, direction_deg)
    dfp = df_layout.copy().reset_index(drop=True)
    dfp["x_down"] = dfp_proj["x_down"].values
    dfp["y_cross"] = dfp_proj["y_cross"].values
    dfp["deficit_total"] = deficits
    dfp["velocidad_libre"] = float(wind_speed)
    dfp["velocidad_efectiva"] = ws_eff
    dfp["potencia_base_W"] = np.full(n, p_base, dtype=float)
    dfp["potencia_wake_W"] = p_wake
    dfp["perdida_potencia_pct"] = np.where(
        dfp["potencia_base_W"] > 0,
        100.0 * (1.0 - dfp["potencia_wake_W"] / dfp["potencia_base_W"]),
        0.0,
    )
    # Ordenar por x_down ascendente para consistencia con otros modelos
    dfp = dfp.sort_values("x_down").reset_index(drop=True)
    return dfp


@st.cache_data(show_spinner=False)
def calcular_estelas_dwm_direccion(
    df_layout, wind_speed, direction_deg, diametro,
    ct=0.8, ambient_ti=0.10, meander_intensity=1.0, curva_df=None,
    n_realizations=15, seed=42,
):
    """Dynamic Wake Meandering (DWM, Larsen et al. 2008) — simplificado.

    Approach: para cada par turbina-turbina, simular meandering del centro del wake
    como random walk con std ~ ambient_ti × downstream distance. Promediar deficits
    sobre n_realizations.

    Más realista que steady-state pero ~n_realizations veces más caro.
    """
    if diametro <= 0:
        raise ValueError("El diámetro debe ser mayor que 0.")
    if not (0 < ct < 1):
        raise ValueError("Ct debe estar entre 0 y 1.")
    if wind_speed < 0:
        raise ValueError("La velocidad del viento no puede ser negativa.")

    rng = np.random.default_rng(int(seed))
    n_real = max(1, int(n_realizations))
    ti = max(0.02, float(ambient_ti))

    dfp = _proyectar_layout_sobre_viento(df_layout, direction_deg).copy()
    dfp = dfp.sort_values("x_down").reset_index(drop=True)

    n = len(dfp)
    deficits_avg = np.zeros(n, dtype=float)

    R = float(diametro) / 2.0
    eps = 0.25 * np.sqrt(0.5 * (1.0 + np.sqrt(1.0 - ct)) / np.sqrt(max(1e-6, 1.0 - ct)))

    for r_idx in range(n_real):
        deficits_real = np.zeros(n, dtype=float)
        for j in range(n):
            dlist_sq = 0.0
            xj = float(dfp.loc[j, "x_down"])
            yj = float(dfp.loc[j, "y_cross"])

            for i in range(j):
                xi = float(dfp.loc[i, "x_down"])
                yi = float(dfp.loc[i, "y_cross"])
                dx = xj - xi
                if dx <= 0:
                    continue

                # Meandering: posición wake center fluctúa lateralmente
                # std_meander = ti × dx × intensity (heurística Larsen 2008)
                std_meander = ti * dx * float(meander_intensity) * 0.5
                offset_meander = rng.normal(0.0, std_meander)
                y_wake_center = yi + offset_meander
                dy_eff = abs(yj - y_wake_center)

                # Deficit gaussian-like centered on meandered position
                sigma_over_D = 0.038 * dx / diametro + eps
                sigma = sigma_over_D * diametro
                if sigma <= 0:
                    continue
                ct_over_8sigmaD2 = ct / (8.0 * sigma_over_D * sigma_over_D)
                if ct_over_8sigmaD2 >= 1.0:
                    continue
                amplitude = 1.0 - np.sqrt(1.0 - ct_over_8sigmaD2)
                radial = np.exp(-0.5 * (dy_eff / sigma) ** 2)
                d_ij = amplitude * radial
                if not np.isfinite(d_ij) or d_ij < 0:
                    d_ij = 0.0
                dlist_sq += min(d_ij, 0.999) ** 2

            deficits_real[j] = min(np.sqrt(dlist_sq), 0.999)

        deficits_avg += deficits_real

    deficits_avg /= n_real
    deficits = np.clip(deficits_avg, 0.0, 0.999999)
    dfp["deficit_total"] = deficits
    dfp["velocidad_libre"] = float(wind_speed)
    dfp["velocidad_efectiva"] = float(wind_speed) * (1.0 - deficits)

    if curva_df is not None:
        dfp["potencia_base_W"] = interpolar_potencia_desde_curva(curva_df, np.full(n, float(wind_speed)))
        dfp["potencia_wake_W"] = interpolar_potencia_desde_curva(curva_df, dfp["velocidad_efectiva"].to_numpy())
        dfp["perdida_potencia_pct"] = np.where(
            dfp["potencia_base_W"] > 0,
            100.0 * (1.0 - dfp["potencia_wake_W"] / dfp["potencia_base_W"]),
            0.0,
        )
    else:
        dfp["potencia_base_W"] = np.nan
        dfp["potencia_wake_W"] = np.nan
        dfp["perdida_potencia_pct"] = np.nan

    return dfp


def _resolver_modelo_wake(modelo):
    m = str(modelo or "jensen").strip().lower()
    if m.startswith("pywake_") or m.startswith("pywake-"):
        return calcular_estelas_pywake_direccion
    if m in ("larsen",):
        return calcular_estelas_larsen_direccion
    if m in ("frandsen",):
        return calcular_estelas_frandsen_direccion
    if m in ("gaussian", "gauss", "bastankhah"):
        return calcular_estelas_gaussian_direccion
    if m in ("turbopark", "turbo_park", "turbo-park"):
        return calcular_estelas_turbopark_direccion
    if m in ("dwm", "dynamic_wake_meandering", "dynamic-wake-meandering"):
        return calcular_estelas_dwm_direccion
    return calcular_estelas_jensen_direccion


@st.cache_data(show_spinner=False)
def analizar_estelas_parque_16(df_layout, df_nasa, curva_df, diametro, ct=0.8, kw=0.05, ws_col="WS50M", wd_col="WD50M", modelo="jensen", ambient_ti=0.10, h_hub=80.0):
    df_rosa = preparar_datos_rosa(df_nasa, ws_col=ws_col, wd_col=wd_col)
    resumen_rosa = resumir_sectores_rosa(df_rosa, ws_col=ws_col)

    func_wake = _resolver_modelo_wake(modelo)
    modelo_lower = str(modelo or "jensen").strip().lower()

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
            if modelo_lower == "larsen":
                df_dir = func_wake(
                    df_layout=df_layout,
                    wind_speed=u_ref,
                    direction_deg=direction_deg,
                    diametro=diametro,
                    ct=ct,
                    ambient_ti=ambient_ti,
                    h_hub=h_hub,
                    curva_df=curva_df,
                )
            elif modelo_lower == "frandsen":
                df_dir = func_wake(
                    df_layout=df_layout,
                    wind_speed=u_ref,
                    direction_deg=direction_deg,
                    diametro=diametro,
                    ct=ct,
                    kw_frand=kw if kw > 0 else 0.06,
                    curva_df=curva_df,
                )
            elif modelo_lower in ("gaussian", "gauss", "bastankhah"):
                df_dir = func_wake(
                    df_layout=df_layout,
                    wind_speed=u_ref,
                    direction_deg=direction_deg,
                    diametro=diametro,
                    ct=ct,
                    ambient_ti=ambient_ti,
                    kstar=kw if kw > 0 and kw < 0.2 else 0.038,
                    curva_df=curva_df,
                )
            elif modelo_lower in ("turbopark", "turbo_park", "turbo-park"):
                df_dir = func_wake(
                    df_layout=df_layout,
                    wind_speed=u_ref,
                    direction_deg=direction_deg,
                    diametro=diametro,
                    ct=ct,
                    ambient_ti=ambient_ti,
                    A=0.04,
                    curva_df=curva_df,
                )
            elif modelo_lower in ("dwm", "dynamic_wake_meandering", "dynamic-wake-meandering"):
                df_dir = func_wake(
                    df_layout=df_layout,
                    wind_speed=u_ref,
                    direction_deg=direction_deg,
                    diametro=diametro,
                    ct=ct,
                    ambient_ti=ambient_ti,
                    meander_intensity=1.0,
                    n_realizations=10,
                    curva_df=curva_df,
                )
            elif modelo_lower.startswith("pywake_") or modelo_lower.startswith("pywake-"):
                # ex: "pywake_bastankhah", "pywake-noj", "pywake-turbopark"
                sub = modelo_lower.split("_", 1)[-1] if "_" in modelo_lower else modelo_lower.split("-", 1)[-1]
                df_dir = func_wake(
                    df_layout=df_layout,
                    wind_speed=u_ref,
                    direction_deg=direction_deg,
                    diametro=diametro,
                    ct=ct,
                    ambient_ti=ambient_ti,
                    modelo_pywake=sub,
                    h_hub=h_hub,
                    curva_df=curva_df,
                )
            else:
                df_dir = func_wake(
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
