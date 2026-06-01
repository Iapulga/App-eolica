import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pandas.util import hash_pandas_object

import calculos
import calculos_energia as energia_calc
from calculos import (
    PROMEDIO_LOG_EXP_LABEL,
    calcular_ti_serie,
    clasificar_iec_61400_1,
    construir_serie_viento_analisis,
    crear_figura_layout_parque,
    crear_rosa_vientos_16,
    interpolar_potencia_curva_preparada,
    normalizar_modelo_altura,
    preparar_datos_curva,
    rayleigh_pdf,
    weibull_pdf,
)
from calculos_economicos import (
    CAPEX_COMPONENT_DEFAULTS,
    CAPEX_MODE_OPTIONS,
    FX_MODE_OPTIONS,
    MONEDA_OPTIONS,
    OPEX_COMPONENT_DEFAULTS,
    OPEX_MODE_OPTIONS,
    calcular_capex,
    calcular_lcoe_descontado,
    calcular_metricas_base_economicas,
    calcular_metricas_financieras,
    calcular_opex,
    calcular_sensibilidad_lcoe,
    convertir_resumen_economico,
    dumps_component_values,
    format_currency_amount,
    format_lcoe_value,
    load_component_values,
    obtener_tasa_cop_usd_online,
)
from db import (
    cargar_config,
    cargar_layout_parque,
    cargar_nasa_hourly,
    cargar_tabla_curva,
    guardar_config_values,
    init_db,
)
from navigation import render_dropdown_visibility_fix, render_sidebar_navigation
from reportes import (
    get_project_context,
    get_report_context,
)
from reportes.fase5_export_helpers import RUNTIME_CONTEXT_STATE_KEY
from widget_helpers import _init_widget_state

st.set_page_config(page_title="Fase 5 · AEP bruta y neta", layout="wide")

init_db()

PLOTLY_PERF_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}


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

render_sidebar_navigation("pages/5_Fase_5_AEP_bruta_y_neta.py")
ROUGHNESS_OPTIONS = {
    "Water / Mar": 2e-4,
    "Snow / Nieve": 1e-3,
    "Grass / Césped": 0.03,
    "Farmland / Cultivo": 0.10,
    "Forest / Bosque": 0.80,
    "City / Ciudad": 1.00,
}

ENERGY_FIGURE_COLORS = {
    "AEP bruta": "#4c78a8",
    "Estelas": "#1f77b4",
    "Disponibilidad": "#2ca02c",
    "Eléctricas": "#9467bd",
    "Otras": "#ff7f0e",
    "AEP neta": "#2ca02c",
}


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
def construir_viento_analisis(df_nasa, modelo, altura_deseada, roughness_label, direccion_fuente):
    modelo = normalize_base_viento_for_energy(modelo)
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
        meta["descripcion"] = "AEP con velocidad y dirección a 50 m"
    elif modelo == "10 m":
        meta["descripcion"] = "AEP con velocidad y dirección a 10 m"
    elif modelo == "Exponencial":
        meta["descripcion"] = "AEP con velocidad extrapolada por perfil exponencial"
    elif modelo == "Log A (2 puntos)":
        meta["descripcion"] = "AEP con velocidad extrapolada por perfil logarítmico ajustado a 2 puntos"
    elif modelo == PROMEDIO_LOG_EXP_LABEL:
        meta["descripcion"] = "AEP con velocidad extrapolada como promedio entre el perfil exponencial y el perfil logarítmico A."

    return df, meta


def potencia_media_sector(curva_df, fila_sector, metodo="Weibull", vmax=35.0, dv=0.1):
    v = np.arange(0.0, vmax + dv, dv)
    p = interpolar_potencia_curva_preparada(curva_df, v)

    if metodo == "Weibull":
        k = float(fila_sector["k Weibull"])
        c = float(fila_sector["c Weibull (m/s)"])
        pdf = weibull_pdf(v, k, c)
    else:
        c = float(fila_sector["c Rayleigh (m/s)"])
        pdf = rayleigh_pdf(v, c)

    if not np.isfinite(pdf).any():
        return np.nan

    y = p * pdf
    potencia_media = np.sum((y[:-1] + y[1:]) * 0.5 * np.diff(v))
    return float(potencia_media)


@st.cache_data(show_spinner=False)
def calcular_aep_sectorial(curva_df, resumen_rosa, metodo_dist, n_turbinas, wake_mode, wake_losses_sector, wake_manual_pct):
    filas = []

    for _, row in resumen_rosa.iterrows():
        sector = str(row["Sector"])
        freq_pct = float(row["Frecuencia (%)"])
        horas_eq = float(row["Horas equivalentes anuales (h/año)"])

        p_media_turbina_w = potencia_media_sector(curva_df, row, metodo=metodo_dist)

        if not np.isfinite(p_media_turbina_w):
            p_media_turbina_w = 0.0

        aep_bruta_turbina_mwh = p_media_turbina_w * horas_eq / 1e6
        aep_bruta_parque_mwh = aep_bruta_turbina_mwh * n_turbinas

        if wake_mode == "Automática desde Fase 4":
            wake_pct = float(wake_losses_sector.get(sector, 0.0))
        else:
            wake_pct = float(wake_manual_pct)

        aep_con_estela_mwh = aep_bruta_parque_mwh * (1.0 - wake_pct / 100.0)

        filas.append({
            "Sector": sector,
            "Frecuencia (%)": freq_pct,
            "Horas equivalentes anuales (h/año)": horas_eq,
            "Potencia media por turbina (W)": p_media_turbina_w,
            "AEP bruta por turbina (MWh/año)": aep_bruta_turbina_mwh,
            "AEP bruta parque (MWh/año)": aep_bruta_parque_mwh,
            "Pérdida estela sector (%)": wake_pct,
            "AEP con estela (MWh/año)": aep_con_estela_mwh,
            "Pérdida estela energética (MWh/año)": aep_bruta_parque_mwh - aep_con_estela_mwh,
        })

    return pd.DataFrame(filas)


def aplicar_perdidas_globales(aep_con_estela, disp_pct, elec_pct, otras_pct):
    factor = (
        (1.0 - disp_pct / 100.0)
        * (1.0 - elec_pct / 100.0)
        * (1.0 - otras_pct / 100.0)
    )
    return aep_con_estela * factor


@st.cache_data(show_spinner=False)
def calcular_resultados_metodo(curva_df, resumen_rosa, metodo_dist, n_turbinas, wake_mode, wake_losses_sector, wake_manual_pct, disp_pct, elec_pct, otras_pct):
    df_aep_sector = calcular_aep_sectorial(
        curva_df=curva_df,
        resumen_rosa=resumen_rosa,
        metodo_dist=metodo_dist,
        n_turbinas=n_turbinas,
        wake_mode=wake_mode,
        wake_losses_sector=wake_losses_sector,
        wake_manual_pct=wake_manual_pct,
    )

    aep_bruta_total = float(df_aep_sector["AEP bruta parque (MWh/año)"].sum())
    aep_con_estela_total = float(df_aep_sector["AEP con estela (MWh/año)"].sum())
    perdida_estela_mwh = float(df_aep_sector["Pérdida estela energética (MWh/año)"].sum())

    aep_neta_total = aplicar_perdidas_globales(
        aep_con_estela=aep_con_estela_total,
        disp_pct=disp_pct,
        elec_pct=elec_pct,
        otras_pct=otras_pct,
    )

    perdida_disp_mwh = aep_con_estela_total * (disp_pct / 100.0)
    base_post_disp = aep_con_estela_total - perdida_disp_mwh
    perdida_elec_mwh = base_post_disp * (elec_pct / 100.0)
    base_post_elec = base_post_disp - perdida_elec_mwh
    perdida_otras_mwh = base_post_elec * (otras_pct / 100.0)

    factor_global = (
        (1.0 - disp_pct / 100.0)
        * (1.0 - elec_pct / 100.0)
        * (1.0 - otras_pct / 100.0)
    )

    df_aep_sector["AEP neta sector (MWh/año)"] = df_aep_sector["AEP con estela (MWh/año)"] * factor_global

    potencia_nominal_turbina_w = float(curva_df["Potencia_W"].max()) if len(curva_df) > 0 else 0.0
    potencia_nominal_parque_w = potencia_nominal_turbina_w * n_turbinas

    if potencia_nominal_parque_w > 0:
        factor_planta_bruto = aep_bruta_total * 1e6 / (potencia_nominal_parque_w * 8760.0) * 100.0
        factor_planta_neto = aep_neta_total * 1e6 / (potencia_nominal_parque_w * 8760.0) * 100.0
    else:
        factor_planta_bruto = np.nan
        factor_planta_neto = np.nan

    aep_bruta_turbina = aep_bruta_total / n_turbinas
    aep_neta_turbina = aep_neta_total / n_turbinas

    tabla_perdidas = pd.DataFrame({
        "Concepto": ["Estelas", "Disponibilidad", "Eléctricas", "Otras", "Total"],
        "Pérdida (%)": [
            (perdida_estela_mwh / aep_bruta_total * 100.0) if aep_bruta_total > 0 else 0.0,
            disp_pct,
            elec_pct,
            otras_pct,
            (1.0 - aep_neta_total / aep_bruta_total) * 100.0 if aep_bruta_total > 0 else 0.0,
        ],
        "Energía perdida (MWh/año)": [
            perdida_estela_mwh,
            perdida_disp_mwh,
            perdida_elec_mwh,
            perdida_otras_mwh,
            aep_bruta_total - aep_neta_total,
        ],
    })

    resumen = {
        "metodo": metodo_dist,
        "aep_bruta_total": aep_bruta_total,
        "aep_neta_total": aep_neta_total,
        "factor_planta_bruto": factor_planta_bruto,
        "factor_planta_neto": factor_planta_neto,
        "aep_bruta_turbina": aep_bruta_turbina,
        "aep_neta_turbina": aep_neta_turbina,
        "potencia_nominal_turbina_w": potencia_nominal_turbina_w,
        "perdida_estela_mwh": perdida_estela_mwh,
        "perdida_disp_mwh": perdida_disp_mwh,
        "perdida_elec_mwh": perdida_elec_mwh,
        "perdida_otras_mwh": perdida_otras_mwh,
        "base_sens": aep_con_estela_total,
    }

    return {
        "df_sector": df_aep_sector,
        "tabla_perdidas": tabla_perdidas,
        "resumen": resumen,
    }


@st.cache_data(show_spinner=False)
def crear_figura_bruto_neto(aep_bruta, perdida_estela, perdida_disp, perdida_elec, perdida_otras, aep_neta, titulo):
    """Create a waterfall/cascade chart showing AEP losses from bruta to neta."""
    bruta = float(aep_bruta)
    est = float(perdida_estela)
    disp = float(perdida_disp)
    elec = float(perdida_elec)
    otras = float(perdida_otras)
    neta = float(aep_neta)

    labels = ["AEP bruta", "Estelas", "Disponibilidad", "Eléctricas", "Otras", "AEP neta"]
    values = [bruta, -est, -disp, -elec, -otras, 0]
    text_values = [bruta, -est, -disp, -elec, -otras, neta]
    measure = ["relative", "relative", "relative", "relative", "relative", "total"]

    def _fmt_val(v):
        """Format value as compact string with K suffix when appropriate."""
        if abs(v) >= 1000:
            return f"{v:,.1f}"
        return f"{v:,.1f}"

    fig = go.Figure(go.Waterfall(
        x=labels,
        y=values,
        measure=measure,
        text=[_fmt_val(v) for v in text_values],
        textposition="outside",
        texttemplate="<b>%{text}</b>",
        textfont=dict(size=11, color="#1f3f7a", family="Inter, sans-serif"),
        connector=dict(line=dict(color="#cbd5e1", width=1, dash="dot")),
        decreasing=dict(marker=dict(color="#ef4444", line=dict(color="#dc2626", width=0.8))),
        increasing=dict(marker=dict(color="#2f6df6", line=dict(color="#1d4ed8", width=0.8))),
        totals=dict(marker=dict(color="#2f6df6", line=dict(color="#1d4ed8", width=0.8))),
        hovertemplate="%{x}<br>%{y:,.1f} MWh/año<extra></extra>",
    ))

    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", font=dict(size=14, color="#1f3f7a", family="Inter, sans-serif"), x=0.5, xanchor="center"),
        template="plotly_white",
        height=500,
        margin=dict(l=40, r=40, t=60, b=40),
        yaxis_title="AEP (MWh/año)",
        yaxis=dict(
            gridcolor="rgba(148,163,184,0.22)",
            zeroline=False,
            title_font=dict(size=11, color="#1f3f7a"),
            tickfont=dict(size=10, color="#64748b"),
        ),
        xaxis=dict(
            tickfont=dict(size=11, color="#64748b"),
        ),
        bargap=0.32,
        showlegend=False,
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_figura_dona_perdidas(perdida_estela, perdida_disp, perdida_elec, perdida_otras, titulo, total_loss_pct=None):
    fig = go.Figure(data=[go.Pie(
        labels=["Estelas", "Disponibilidad", "Eléctricas", "Otras"],
        values=[perdida_estela, perdida_disp, perdida_elec, perdida_otras],
        hole=0.55,
        marker=dict(colors=[
            ENERGY_FIGURE_COLORS["Estelas"],
            ENERGY_FIGURE_COLORS["Disponibilidad"],
            ENERGY_FIGURE_COLORS["Eléctricas"],
            ENERGY_FIGURE_COLORS["Otras"],
        ]),
        textinfo="percent",
        textposition="outside",
        textfont=dict(size=11, color="#0f2f6e", family="Arial"),
        sort=False,
        automargin=True,
        hovertemplate="%{label}: %{value:.2f} MWh/año<extra></extra>",
    )])
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=f"<b>{float(total_loss_pct or 0.0):.2f}%</b><br>Pérdidas<br>totales",
        showarrow=False,
        font=dict(size=12, color="#1f3f7a"),
    )
    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", x=0.5, xanchor="center", font=dict(size=14, color="#1f3f7a")),
        template="plotly_white",
        height=400,
        margin=dict(l=20, r=120, t=16, b=20),
        legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=12, color="#1f3f7a")),
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_figura_sectorial(df_sector, titulo):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_sector["Sector"],
        y=df_sector["AEP bruta parque (MWh/año)"],
        name="Bruta",
        hovertemplate="Sector: %{x}<br>AEP bruta: %{y:.2f} MWh/año<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df_sector["Sector"],
        y=df_sector["AEP neta sector (MWh/año)"],
        name="Neta",
        hovertemplate="Sector: %{x}<br>AEP neta: %{y:.2f} MWh/año<extra></extra>",
    ))
    fig.update_layout(
        title=titulo,
        template="plotly_white",
        barmode="group",
        height=520,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis_title="Sector",
        yaxis_title="Energía (MWh/año)",
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_figura_sensibilidad(base_aep_con_estela, disp_pct, elec_pct, otras_pct, variable, titulo):
    x = np.linspace(0.0, 15.0, 31)
    y = []

    for val in x:
        d = disp_pct
        e = elec_pct
        o = otras_pct

        if variable == "Disponibilidad":
            d = val
        elif variable == "Eléctricas":
            e = val
        elif variable == "Otras":
            o = val
        elif variable == "Estelas":
            neta = (
                base_aep_con_estela
                * (1.0 - val / 100.0)
                * (1.0 - disp_pct / 100.0)
                * (1.0 - elec_pct / 100.0)
                * (1.0 - otras_pct / 100.0)
            )
            y.append(neta)
            continue

        neta = (
            base_aep_con_estela
            * (1.0 - d / 100.0)
            * (1.0 - e / 100.0)
            * (1.0 - o / 100.0)
        )
        y.append(neta)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode="lines+markers",
        name=f"Sensibilidad {variable}",
        hovertemplate=f"{variable}: " + "%{x:.2f}%<br>AEP neta: %{y:.2f} MWh/año<extra></extra>",
    ))
    fig.update_layout(
        title=titulo,
        template="plotly_white",
        height=500,
        margin=dict(l=40, r=40, t=60, b=40),
        xaxis_title=f"{variable} (%)",
        yaxis_title="AEP neta (MWh/año)",
    )
    return fig


@st.cache_data(show_spinner=False)
def crear_figura_comparacion_metodos(res_weib, res_ray):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=["AEP bruta", "AEP neta", "FP bruto", "FP neto"],
        y=[res_weib["aep_bruta_total"], res_weib["aep_neta_total"], res_weib["factor_planta_bruto"], res_weib["factor_planta_neto"]],
        name="Weibull",
    ))
    fig.add_trace(go.Bar(
        x=["AEP bruta", "AEP neta", "FP bruto", "FP neto"],
        y=[res_ray["aep_bruta_total"], res_ray["aep_neta_total"], res_ray["factor_planta_bruto"], res_ray["factor_planta_neto"]],
        name="Rayleigh",
    ))
    fig.update_layout(
        title="Comparación Weibull vs Rayleigh",
        template="plotly_white",
        barmode="group",
        height=520,
        margin=dict(l=40, r=40, t=60, b=40),
        yaxis_title="Valor",
    )
    return fig


def construir_tabla_comparativa(res_weib, res_ray):
    return pd.DataFrame({
        "Indicador": [
            "AEP bruta parque (MWh/año)",
            "AEP neta parque (MWh/año)",
            "Factor de planta bruto (%)",
            "Factor de planta neto (%)",
            "AEP bruta por turbina (MWh/año)",
            "AEP neta por turbina (MWh/año)",
            "Pérdida por estela (MWh/año)",
            "Pérdida por disponibilidad (MWh/año)",
            "Pérdida eléctrica (MWh/año)",
            "Otras pérdidas (MWh/año)",
        ],
        "Weibull": [
            res_weib["aep_bruta_total"],
            res_weib["aep_neta_total"],
            res_weib["factor_planta_bruto"],
            res_weib["factor_planta_neto"],
            res_weib["aep_bruta_turbina"],
            res_weib["aep_neta_turbina"],
            res_weib["perdida_estela_mwh"],
            res_weib["perdida_disp_mwh"],
            res_weib["perdida_elec_mwh"],
            res_weib["perdida_otras_mwh"],
        ],
        "Rayleigh": [
            res_ray["aep_bruta_total"],
            res_ray["aep_neta_total"],
            res_ray["factor_planta_bruto"],
            res_ray["factor_planta_neto"],
            res_ray["aep_bruta_turbina"],
            res_ray["aep_neta_turbina"],
            res_ray["perdida_estela_mwh"],
            res_ray["perdida_disp_mwh"],
            res_ray["perdida_elec_mwh"],
            res_ray["perdida_otras_mwh"],
        ],
    })


def construir_tabla_sectorial_comparada(df_weib, df_ray):
    df1 = df_weib[["Sector", "AEP bruta parque (MWh/año)", "AEP neta sector (MWh/año)"]].copy()
    df1 = df1.rename(columns={
        "AEP bruta parque (MWh/año)": "AEP bruta Weibull (MWh/año)",
        "AEP neta sector (MWh/año)": "AEP neta Weibull (MWh/año)",
    })

    df2 = df_ray[["Sector", "AEP bruta parque (MWh/año)", "AEP neta sector (MWh/año)"]].copy()
    df2 = df2.rename(columns={
        "AEP bruta parque (MWh/año)": "AEP bruta Rayleigh (MWh/año)",
        "AEP neta sector (MWh/año)": "AEP neta Rayleigh (MWh/año)",
    })

    return df1.merge(df2, on="Sector", how="outer")


def calcular_lcoe(
    energia_base_mwh,
    capex_total,
    opex_fijo_anual,
    opex_variable_por_mwh,
    vida_util_anios,
    tasa_descuento_pct,
    degradacion_energia_pct=0.0,
    valor_residual=0.0,
):
    tasa = max(0.0, float(tasa_descuento_pct)) / 100.0
    degradacion = max(0.0, float(degradacion_energia_pct)) / 100.0
    vida_util = max(1, int(vida_util_anios))
    energia_base = max(0.0, float(energia_base_mwh))

    valor_presente_costos = float(capex_total)
    valor_presente_energia = 0.0

    for year in range(1, vida_util + 1):
        energia_anual = energia_base * ((1.0 - degradacion) ** (year - 1))
        descuento = ((1.0 + tasa) ** year) if tasa > 0 else 1.0
        valor_presente_energia += energia_anual / descuento
        valor_presente_costos += (
            float(opex_fijo_anual) + float(opex_variable_por_mwh) * energia_anual
        ) / descuento

    descuento_residual = ((1.0 + tasa) ** vida_util) if tasa > 0 else 1.0
    valor_presente_costos -= float(valor_residual) / descuento_residual

    lcoe_mwh = valor_presente_costos / valor_presente_energia if valor_presente_energia > 0 else np.nan
    lcoe_kwh = lcoe_mwh / 1000.0 if np.isfinite(lcoe_mwh) else np.nan

    return {
        "valor_presente_costos": valor_presente_costos,
        "valor_presente_energia": valor_presente_energia,
        "lcoe_mwh": lcoe_mwh,
        "lcoe_kwh": lcoe_kwh,
    }


def exportar_excel(
    resumen_df,
    perdidas_df,
    sector_df,
    export_metadata_df=None,
    report_manifest_df=None,
    comparacion_df=None,
    comparacion_sector_df=None,
):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        resumen_df.to_excel(writer, index=False, sheet_name="Resumen")
        perdidas_df.to_excel(writer, index=False, sheet_name="Perdidas")
        sector_df.to_excel(writer, index=False, sheet_name="Sectorial")
        if export_metadata_df is not None:
            export_metadata_df.to_excel(writer, index=False, sheet_name="Metadata_exportacion")
        if report_manifest_df is not None:
            report_manifest_df.to_excel(writer, index=False, sheet_name="Manifiesto_reporte")
        if comparacion_df is not None:
            comparacion_df.to_excel(writer, index=False, sheet_name="Comparacion_metodos")
        if comparacion_sector_df is not None:
            comparacion_sector_df.to_excel(writer, index=False, sheet_name="Comparacion_sectorial")
    return output.getvalue()

FASE_5_CSS = """
<style>
    :root {
        --f5-ref-blue: #2563eb;
        --f5-ref-ink: #0b2a5b;
        --f5-ref-muted: #64748b;
        --f5-ref-border: #d9e8fb;
        --f5-ref-soft: #eff6ff;
    }
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(219, 234, 254, 0.6), transparent 34rem),
            linear-gradient(180deg, #f7fbff 0%, #ffffff 45%, #f8fbff 100%);
    }
    .st-key-f5_card_header,
    .st-key-f5_card_config,
    .st-key-f5_card_losses,
    .st-key-f5_card_results,
    .st-key-f5_card_compare,
    .st-key-f5_card_breakdown,
    .st-key-f5_card_sector,
    .st-key-f5_card_econ_master,
    .st-key-f5_card_econ_base,
    .st-key-f5_card_econ_currency,
    .st-key-f5_card_export {
        border-radius: 18px !important;
        border: 1px solid #cbd5e1 !important;
        background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        overflow: visible !important;
    }
    .st-key-f5_card_header div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_config div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_losses div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_results div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_compare div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_breakdown div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_sector div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_master div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_base div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_currency div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_export div[data-testid="stVerticalBlockBorderWrapper"] {
        border: none !important;
        border-radius: 18px !important;
        box-shadow: none !important;
        padding: 0.86rem 0.98rem 1rem 0.98rem !important;
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
        max-width: 74rem;
        margin: 0;
        position: relative;
        z-index: 2;
    }
    .st-key-f5_card_header {
        border: 1.35px solid #cbd5e1 !important;
        border-radius: 28px !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
    }
    .st-key-f5_card_header [data-testid="stVerticalBlockBorderWrapper"] {
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
    .f5-section-header, .f5-ref-section-header {
        display: flex;
        align-items: flex-start;
        gap: 0.62rem;
        margin-bottom: 0.72rem;
    }
    .f5-section-icon, .f5-ref-section-icon {
        width: 2.1rem;
        height: 2.1rem;
        min-width: 2.1rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #eef5ff;
        border: 1px solid #bfd8fb;
    }
    .f5-section-title, .f5-ref-section-title {
        color: var(--f5-ref-ink);
        font-size: 1rem;
        font-weight: 850;
        line-height: 1.15;
    }
    .f5-section-subtitle, .f5-ref-section-subtitle {
        color: var(--f5-ref-muted);
        font-size: 0.74rem;
        font-weight: 400;
        margin-top: 0.17rem;
    }
    .f5-section-header-card {
        background: #ffffff;
        border: 1px solid #d7e8ff;
        border-radius: 24px;
        min-height: 84px;
        display: flex;
        align-items: center;
        padding: 0 28px;
        gap: 14px;
        box-shadow: 0 8px 24px rgba(15, 60, 120, 0.04);
        margin-bottom: 10px;
    }
    /* Card grande para resumen de perfil (p. ej. "AEP con velocidad extrapolada por perfil exponencial") */
    .f5-profile-summary-box {
        border: 1px solid #cbd5e1 !important;
        border-radius: 20px !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        overflow: visible !important;
        box-sizing: border-box !important;
        padding: 0.16rem 1rem 0.26rem 1rem !important;
        margin-top: -0.7rem !important;
        margin-bottom: 1rem !important;
        min-height: 57px !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: space-between !important;
    }

    .f5-profile-summary-box .f5-profile-summary-alert {
        background: transparent !important;
        border: none !important;
        padding: 0 0 0.5rem 0 !important;
        margin: 0 !important;
    }

    .f5-profile-summary-box .f5-profile-summary-grid {
        display: flex !important;
        gap: 0.8rem !important;
        align-items: center !important;
    }
    .f5-section-header-icon,
    .f5-section-header-card-icon {
        width: 46px;
        height: 46px;
        border-radius: 999px;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        color: #2563eb;
        flex-shrink: 0;
    }
    .f5-section-header-card-title {
        font-size: 22px;
        font-weight: 800;
        color: #082f63;
        line-height: 1.1;
    }
    .f5-section-header-card-text {
        display: flex;
        flex-direction: column;
        gap: 0.34rem;
    }
    .f5-section-header-card-subtitle {
        color: #000000;
        font-size: 0.82rem;
        font-weight: 500;
        line-height: 1.25;
    }
    .f5-info-banner {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.78rem 1.1rem;
        border-radius: 15px;
        background: #ecf4ff;
        border: 1px solid #c8dcfb;
        color: #1f4ea8;
        font-size: 0.86rem;
        font-weight: 700;
        margin: 0.42rem 0 0.76rem 0;
    }
    .f5-info-dot {
        width: 1.45rem;
        height: 1.45rem;
        border-radius: 999px;
        background: var(--f5-ref-blue);
        color: #ffffff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 900;
        font-size: 0.88rem;
        flex-shrink: 0;
    }
    .f5-kpi-card {
        min-height: 104px;
        display: flex;
        align-items: center;
        gap: 0.72rem;
        margin-top: -3px;
        padding: 0.86rem 0.88rem;
        border: 1px solid var(--f5-ref-border);
        border-radius: 16px;
        background: #ffffff;
        box-shadow: 0 8px 20px rgba(15, 45, 90, 0.035);
    }
    .f5-kpi-icon {
        width: 2.72rem;
        height: 2.72rem;
        min-width: 2.72rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #ecf4ff;
        color: var(--f5-ref-blue);
    }
    .f5-kpi-card.accent-green .f5-kpi-icon { background: #dcfce7; color: #16a34a; }
    .f5-kpi-card.accent-purple .f5-kpi-icon { background: #f3e8ff; color: #7e22ce; }
    .f5-kpi-card.accent-amber .f5-kpi-icon { background: #fef3c7; color: #d97706; }
    .f5-kpi-label { color: #000000; font-size: 0.69rem; font-weight: 400; margin-bottom: 0.2rem; line-height: 1.16; }
    .f5-kpi-value { color: #102a56; font-size: 1.24rem; font-weight: 900; line-height: 1.02; }
    .f5-kpi-unit, .f5-kpi-caption { color: #000000; font-size: 0.67rem; font-weight: 400; margin-top: 0.2rem; }
    .f5-mini-note {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.46rem 0.62rem;
        border-radius: 12px;
        background: #eff6ff;
        color: #1f4ea8;
        border: 1px solid #d2e5ff;
        font-size: 0.72rem;
        font-weight: 400;
        margin-top: 0.28rem;
    }
    .f5-subcard-title { color: #000000; font-size: 0.86rem; font-weight: 820; margin-bottom: 0.52rem; }
    /* ===== Reference-style loss table ===== */
    .f5-loss-table-wrap {
        border: 1px solid #d9e8fb !important;
        border-radius: 14px !important;
        background: #ffffff !important;
        box-shadow: 0 5px 16px rgba(15, 45, 90, 0.028) !important;
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: auto !important;
        overflow-y: visible !important;
    }
    .f5-loss-table-ref {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
        color: #1e293b;
        font-family: 'Inter', -apple-system, sans-serif;
        table-layout: auto !important;
    }
    .f5-loss-table-ref thead tr {
        background: #f8fafc;
    }
    .f5-loss-table-ref th {
        padding: 0.66rem 0.74rem;
        font-weight: 800;
        font-size: 0.88rem;
        color: #000000;
        border-bottom: 1.5px solid #e2e8f0;
        white-space: normal;
        line-height: 1.2;
    }
    .f5-loss-table-ref td {
        padding: 0.62rem 0.74rem;
        font-weight: 700;
        font-size: 0.96rem;
        border-bottom: 1px solid #f1f5f9;
        color: #0f2f5f;
        font-variant-numeric: tabular-nums;
        white-space: normal;
    }
    .f5-loss-table-ref th:nth-child(3),
    .f5-loss-table-ref td:nth-child(3) {
        min-width: 148px;
    }
    .f5-loss-table-ref tr:last-child td {
        border-bottom: none;
    }
    .f5-loss-table-ref .f5-loss-total-row td {
        font-weight: 800;
        color: #0f172a;
        border-top: 1.5px solid #cbd5e1;
        background: #f0f5ff;
    }
    .f5-loss-card {
        border: 1px solid #d9e7fb;
        border-radius: 20px;
        background: #ffffff;
        box-shadow: 0 8px 22px rgba(15, 23, 42, 0.035);
        padding: 0.72rem 0.78rem 0.78rem 0.78rem;
    }
    .f5-loss-header {
        display: flex;
        align-items: center;
        gap: 0.58rem;
        margin-bottom: 0.66rem;
    }
    .f5-loss-header-icon {
        width: 2rem;
        height: 2rem;
        min-width: 2rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #ecf4ff;
        border: 1px solid #bfd8fb;
    }
    .f5-loss-header-title {
        color: #0f2f6e;
        font-size: 0.99rem;
        font-weight: 840;
        line-height: 1.15;
    }
    .f5-loss-grid {
        margin-top: 0.22rem;
    }
    .f5-loss-col-title {
        color: #000000;
        font-size: 0.8rem;
        font-weight: 800;
        margin-bottom: 0.38rem;
        line-height: 1.18;
    }
    .f5-sector-card {
        border: 1px solid #d9e7fb;
        border-radius: 22px;
        background: #ffffff;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
        padding: 0.78rem 0.82rem 0.85rem 0.82rem;
    }
    .f5-sector-header {
        display: flex;
        align-items: center;
        gap: 0.58rem;
        margin-bottom: 0.66rem;
    }
    .f5-sector-header-icon {
        width: 2rem;
        height: 2rem;
        min-width: 2rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #ecf4ff;
        border: 1px solid #bfd8fb;
    }
    .f5-sector-header-title {
        color: #0f2f6e;
        font-size: 0.99rem;
        font-weight: 840;
        line-height: 1.15;
    }
    .f5-sector-panel {
        border: 1px solid #dbe9fc;
        border-radius: 16px;
        background: #ffffff;
        box-shadow: 0 5px 14px rgba(15, 45, 90, 0.025);
        padding: 0.62rem 0.66rem 0.56rem 0.66rem;
        height: 100%;
    }
    .f5-sector-panel-title {
        color: #000000;
        font-size: 0.84rem;
        font-weight: 800;
        margin-bottom: 0.48rem;
        line-height: 1.18;
    }
    /* ===== Reference-style sector table ===== */
    .f5-sector-table-wrap {
        border: 1px solid #d9e8fb !important;
        border-bottom: 3px solid #2563eb !important;
        border-radius: 14px !important;
        overflow-x: auto !important;
        background: #ffffff !important;
        box-shadow: 0 5px 16px rgba(15, 45, 90, 0.028) !important;
        max-width: 100% !important;
    }
    .f5-sector-table-ref {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.72rem;
        color: #1e293b;
        font-family: 'Inter', -apple-system, sans-serif;
        white-space: normal;
        min-width: 720px;
        table-layout: auto !important;
    }
    .f5-sector-table-ref thead tr {
        background: #f8fafc;
    }
    .f5-sector-table-ref th {
        padding: 0.5rem 0.4rem;
        font-weight: 400;
        font-size: 0.62rem;
        color: #000000;
        border-bottom: 1.5px solid #e2e8f0;
        text-align: right;
        line-height: 1.22;
    }
    .f5-sector-table-ref th:first-child { text-align: left; }
    .f5-sector-table-ref td {
        padding: 0.45rem 0.4rem;
        font-weight: 500;
        border-bottom: 1px solid #f1f5f9;
        color: #000000;
        font-variant-numeric: tabular-nums;
        text-align: right;
    }
    .f5-sector-table-ref td:first-child {
        text-align: left;
        font-weight: 700;
        color: #2563eb;
    }
    .f5-sector-table-ref tr:last-child td { border-bottom: none; }
    .f5-sector-table-ref .f5-sector-total-row td {
        font-weight: 800;
        color: #0f172a;
        border-top: 1.5px solid #cbd5e1;
        background: #f0f5ff;
    }
    .f5-sector-table-ref .f5-sector-total-row td:first-child {
        color: #0f172a;
    }
    .f5-sector-row {
        align-items: stretch;
    }
    .f5-sector-panel-card {
        background: #ffffff;
        border: 1px solid #d7e8ff;
        border-radius: 22px;
        box-shadow: 0 8px 24px rgba(15, 60, 120, 0.04);
        padding: 0.72rem 0.78rem;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }
    .f5-sector-panel-card--table .f5-sector-table-wrap {
        height: 100%;
        overflow: auto;
    }
    .f5-sector-panel-card--chart .f5-sector-plot-host {
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    }
    .f5-sector-panel-card--chart .f5-sector-plot-host [data-testid="stPlotlyChart"] {
        margin-top: -0.2rem;
        height: 100%;
    }
    /* ===== Compact economic section (reference design) ===== */
    .f5-econ-top-card { border:none !important; box-shadow:none !important; background:transparent !important; border-radius:0 !important; padding:0 !important; margin:0 !important; height:100% !important; min-height:100% !important; display:flex !important; flex-direction:column !important; justify-content:center !important; }
    .st-key-f5_card_econ_base,
    .st-key-f5_card_econ_currency { min-height:200px !important; height:auto !important; border-radius:18px !important; border:1px solid #d9e8fb !important; background:#ffffff !important; box-shadow:0 6px 18px rgba(15,45,90,.028) !important; overflow:hidden !important; box-sizing:border-box !important; }
    .st-key-f5_card_econ_base div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_currency div[data-testid="stVerticalBlockBorderWrapper"] { min-height:200px !important; height:auto !important; padding:0.72rem 0.82rem !important; box-sizing:border-box !important; display:flex !important; flex-direction:column !important; justify-content:flex-start !important; overflow:hidden !important; }
    .st-key-f5_card_econ_currency div[data-testid="stVerticalBlockBorderWrapper"] { justify-content:flex-start !important; gap:0.55rem !important; padding-bottom:0.55rem !important; }
    .f5-econ-mini-kpis { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:0.6rem; align-items:center !important; margin-top: 0.6rem; }
    .f5-econ-top-title { display:flex; align-items:center; gap:0.6rem; color:#0f2f6e; font-size:0.96rem; font-weight:850; margin-bottom:0.4rem; }
    .f5-econ-top-title-icon { width:2rem; height:2rem; min-width:2rem; border-radius:999px; display:inline-flex; align-items:center; justify-content:center; background:#ecf4ff; border:1px solid #bfd8fb; }
    .f5-econ-mini-kpi { display:flex; flex-direction:column; gap:0.55rem; padding:0.75rem 0.65rem; border: 1px solid #cbd5e1; border-radius:14px; background:linear-gradient(180deg,#ffffff 0%,#f8fbff 100%); min-width:0; align-items:center; justify-content:space-between; height:100%; box-sizing:border-box; }
    .f5-econ-mini-kpi-header { display:flex; align-items:center; gap:0.5rem; width:100%; justify-content:flex-start; }
    .f5-econ-mini-kpi-body { display:flex; flex-direction:column; align-items:center; justify-content:flex-start; width:100%; margin-top:0; flex-grow:1; }
    .f5-econ-mini-kpi-icon { width:2.8rem; height:2.8rem; min-width:2.8rem; border-radius:999px; display:inline-flex; align-items:center; justify-content:center; background:#ecf4ff; border:1px solid #c8dcfb; }
    .f5-econ-mini-kpi-label { color:#000000; font-size:0.62rem; font-weight:400; line-height:1.15; }
    .f5-econ-mini-kpi-value { color:#102a56; font-size:1.18rem; font-weight:900; line-height:1.0; text-align:center; }
    .f5-econ-mini-kpi-unit { color:#000000; font-size:0.62rem; font-weight:400; margin-top:0.25rem; text-align:center; }
    .f5-econ-fx-strip { display:flex; align-items:center; gap:0.8rem; padding:0.52rem 0.72rem; border-radius:10px; background:#eef5ff; border:1px solid #dbe9fc; font-size:0.66rem; font-weight:400; color:#000000; margin-top:0.25rem; margin-bottom:0.25rem; flex-wrap:wrap; }
    .st-key-f5_btn_actualizar_tasa button,
    .st-key-f5_card_econ_currency div[data-testid="stButton"] button {
        min-height: 2.7rem !important;
        border-radius: 8px !important;
        border: 1px solid #93c5fd !important;
        background: #f0f7ff !important;
        color: #2563eb !important;
    }
    .st-key-f5_card_econ_currency div[data-testid="stButton"] button:hover {
        background: #eef5ff !important;
        border-color: #2563eb !important;
        color: #1d4ed8 !important;
    }
    .st-key-f5_econ_capex_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_econ_opex_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_econ_lcoe_card div[data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff !important;
        border: 1px solid #d9e8fb !important;
        border-radius: 18px !important;
        box-shadow: 0 8px 22px rgba(15, 45, 90, 0.035) !important;
        padding: 0.82rem 0.9rem !important;
        min-height: 19.5rem !important;
    }
    .st-key-f5_econ_capex_card,
    .st-key-f5_econ_opex_card,
    .st-key-f5_econ_lcoe_card {
        border-radius: 18px !important;
        background: #ffffff !important;
        border: 1px solid #d9e8fb !important;
        box-shadow: 0 8px 22px rgba(15, 45, 90, 0.035) !important;
        overflow: hidden !important;
    }
    /* 3-column card borders for CAPEX / OPEX / LCOE */
    .st-key-f5_card_econ_master [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] > div[data-testid="stVerticalBlockBorderWrapper"] {
        border:1px solid #d9e8fb !important; border-radius:18px !important; background:#fff !important; box-shadow:0 6px 18px rgba(15,45,90,.028) !important; padding:0.58rem 0.62rem 0.52rem !important;
    }
    .f5-econ-col-title { display:flex; align-items:center; gap:0.48rem; color:#0f2f6e; font-size:0.92rem; font-weight:860; margin-bottom:0.18rem; }
    .f5-econ-col-title-icon { width:1.85rem; height:1.85rem; min-width:1.85rem; border-radius:999px; display:inline-flex; align-items:center; justify-content:center; background:#ecf4ff; border:1px solid #bfd8fb; }
    .f5-econ-table-wrap { border:1px solid #e2ebf6; border-radius:12px; overflow:hidden; margin-top:0.22rem; }
    .f5-econ-table-title { color:#000000; font-size:0.72rem; font-weight:800; margin-top:0.32rem; margin-bottom:0.12rem; }
    .f5-econ-table { width:100%; border-collapse:collapse; font-size:0.62rem; color:#1e293b; }
    .f5-econ-table th { text-align:left; background:#f4f8ff; color:#000000; font-weight:800; font-size:0.58rem; padding:0.28rem 0.42rem; border-bottom:1px solid #e2ebf6; }
    .f5-econ-table th:not(:first-child) { text-align:right; }
    .f5-econ-table td { padding:0.22rem 0.42rem; border-bottom:1px solid #f1f5f9; font-weight:550; }
    .f5-econ-table td:not(:first-child) { text-align:right; font-variant-numeric:tabular-nums; }
    .f5-econ-table tr:last-child td { border-bottom:none; }
    .f5-econ-table .f5-econ-total-row td { font-weight:900; color:#0f172a; border-top:1.5px solid #cbd5e1; background:#f0f5ff; }
    /* LCOE result KPIs - large centered numbers */
    .f5-econ-lcoe-kpi { display:flex; flex-direction:column; align-items:center; text-align:center; gap:0.18rem; padding:0.52rem 0.32rem; border:1px solid #e2ebf6; border-radius:14px; background:#ffffff; }
    .f5-econ-lcoe-kpi-label { color:#000000; font-size:0.58rem; font-weight:400; line-height:1.18; text-align:center; }
    .f5-econ-lcoe-kpi-value { color:#102a56; font-size:1.52rem; font-weight:900; line-height:1.05; letter-spacing:-0.02em; }
    .f5-econ-lcoe-kpi-value.blue-val { color:#2563eb; }
    .f5-econ-lcoe-kpi-value.green-val { color:#16a34a; }
    .f5-econ-lcoe-kpi-value.purple-val { color:#7e22ce; }
    .f5-econ-lcoe-pair { display:grid; grid-template-columns:1fr 1fr; gap:0.52rem; }
    .f5-econ-lcoe-sep { height:1px; background:#e2ebf6; margin:0.38rem 0; }
    /* Mostrado KPI cards */
    .f5-econ-mostrado-card { display:flex; align-items:center; gap:0.62rem; padding:0.72rem 0.82rem; border:1px solid #d9e8fb; border-radius:16px; background:#fff; box-shadow:0 6px 16px rgba(15,45,90,.032); }
    .f5-econ-mostrado-icon { width:2.35rem; height:2.35rem; min-width:2.35rem; border-radius:999px; display:inline-flex; align-items:center; justify-content:center; }
    .f5-econ-mostrado-icon.blue { background:#ecf4ff; color:#2563eb; }
    .f5-econ-mostrado-icon.green { background:#dcfce7; color:#16a34a; }
    .f5-econ-mostrado-icon.purple { background:#f3e8ff; color:#7e22ce; }
    .f5-econ-mostrado-label { color:#000000; font-size:0.68rem; font-weight:400; line-height:1.12; }
    .f5-econ-mostrado-value { color:#102a56; font-size:1.18rem; font-weight:900; line-height:1.0; }
    /* Grilla 2x2 de resultados dentro del card LCOE */
    .f5-econ-mostrado-grid-inside-lcoe { display:grid !important; grid-template-columns:repeat(2, minmax(0, 1fr)) !important; gap:0.62rem !important; margin-top:0.9rem; width:100% !important; max-width:100% !important; }
    .f5-econ-mostrado-grid-inside-lcoe .f5-econ-mostrado-card { min-height:86px; padding:0.72rem 0.82rem; border:1px solid #d9e8fb; border-radius:16px; background:#ffffff; box-shadow:0 6px 16px rgba(15,45,90,.032); min-width:0 !important; overflow:hidden !important; }
    .f5-econ-mostrado-grid-inside-lcoe .f5-econ-mostrado-icon { width:2.45rem; height:2.45rem; min-width:2.45rem; }
    .f5-econ-mostrado-grid-inside-lcoe .f5-econ-mostrado-label { font-size:0.68rem; font-weight:400; color:#000000; }
    .f5-econ-mostrado-grid-inside-lcoe .f5-econ-mostrado-value { font-size:1.05rem; font-weight:900; color:#102a56; overflow-wrap:anywhere !important; word-break:break-word !important; }
    @media (max-width:1200px) {
        .f5-econ-mini-kpis { grid-template-columns:repeat(2, minmax(0, 1fr)); }
    }
    .f5-action-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 0.48rem;
        margin-top: 0.62rem;
        width: calc(100% - 0.65rem);
        max-width: 100%;
        overflow: hidden;
    }
    .f5-action-card {
        min-height: 112px;
        min-width: 0;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 0.5rem;
        padding: 0.52rem;
        border: 1px solid var(--f5-ref-border);
        border-radius: 16px;
        background: #ffffff;
        box-shadow: 0 8px 20px rgba(15, 45, 90, 0.03);
        overflow: hidden;
    }
    /* ===== Body-only dashboard harmonization (no header touch) ===== */
    .st-key-f5_card_config,
    .st-key-f5_card_losses,
    .st-key-f5_card_results,
    .st-key-f5_card_compare,
    .st-key-f5_card_breakdown,
    .st-key-f5_card_sector,
    .st-key-f5_card_econ_master,
    .st-key-f5_card_econ_base,
    .st-key-f5_card_econ_currency,
    .st-key-f5_card_export {
        border-radius: 22px !important;
        border: 1px solid #d9e8fb !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
    }
    .st-key-f5_card_config div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_losses div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_results div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_compare div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_breakdown div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_sector div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_master div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_base div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_currency div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_export div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.78rem 0.92rem 0.82rem 0.92rem !important;
    }
    .st-key-f5_card_config div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.52rem 0.92rem 1.45rem 0.92rem !important;
    }
    .st-key-f5_card_losses div[data-testid="stVerticalBlockBorderWrapper"] {
        padding: 0.35rem 0.92rem 1.15rem 0.92rem !important;
    }
    .st-key-f5_card_config [data-testid="stVerticalBlock"] {
        min-height: unset !important;
        height: auto !important;
        justify-content: flex-start !important;
        align-content: start !important;
        gap: 0.5rem !important;
    }
    .st-key-f5_card_losses [data-testid="stVerticalBlock"] {
        min-height: unset !important;
        height: auto !important;
        justify-content: flex-start !important;
        align-content: start !important;
        gap: 0.38rem !important;
    }
    .st-key-f5_card_config [data-testid="stColumn"],
    .st-key-f5_card_losses [data-testid="stColumn"] {
        padding-bottom: 0 !important;
    }
    .st-key-f5_card_config .f5-mini-note,
    .st-key-f5_card_losses .f5-mini-note {
        margin-top: 0.08rem !important;
    }
    .st-key-f5_card_config .f5-mini-note {
        margin-bottom: 0.45rem !important;
    }
    .st-key-f5_card_losses .f5-mini-note {
        margin-bottom: 0.45rem !important;
    }
    .st-key-f5_card_config {
        min-height: 459px !important;
    }
    .st-key-f5_card_config div[data-testid="stVerticalBlockBorderWrapper"] {
        height: 100% !important;
        min-height: 459px !important;
    }
    .st-key-f5_card_config div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
        height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
    }
    .st-key-f5_card_config form[data-testid="stForm"] {
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        padding: 1.2rem 1.2rem 1.62rem 1.2rem !important;
    }
    .st-key-f5_card_losses form[data-testid="stForm"] {
        padding: 1rem 1.2rem 1.65rem 1.2rem !important;
    }
    .st-key-f5_card_config div[data-testid="stFormSubmitButton"] {
        margin-top: auto !important;
        padding-top: 1.1rem !important;
    }
    .st-key-f5_card_losses div[data-testid="stFormSubmitButton"] {
        padding-top: 1.1rem !important;
    }
    .st-key-f5_card_breakdown .stDataFrame,
    .st-key-f5_card_sector .stDataFrame,
    .st-key-f5_card_econ_master .stDataFrame,
    .st-key-f5_card_econ_base .stDataFrame,
    .st-key-f5_card_econ_currency .stDataFrame {
        border: 1px solid #d8e7fa !important;
        border-radius: 14px !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
        overflow: hidden !important;
    }
    .st-key-f5_card_breakdown .stDataFrame thead tr th,
    .st-key-f5_card_sector .stDataFrame thead tr th,
    .st-key-f5_card_econ_master .stDataFrame thead tr th,
    .st-key-f5_card_econ_base .stDataFrame thead tr th,
    .st-key-f5_card_econ_currency .stDataFrame thead tr th {
        background: #f1f7ff !important;
        color: #000000 !important;
        font-weight: 800 !important;
    }
    .st-key-f5_card_breakdown [data-testid="stPlotlyChart"],
    .st-key-f5_card_sector [data-testid="stPlotlyChart"],
    .st-key-f5_card_compare [data-testid="stPlotlyChart"] {
        border: 1px solid #d9e8fb !important;
        border-bottom: 3px solid #2563eb !important;
        border-radius: 14px !important;
        background: #ffffff !important;
        padding: 0.06rem 0.14rem 0.06rem 0.14rem !important;
        box-shadow: 0 5px 16px rgba(15, 45, 90, 0.028) !important;
    }
    .st-key-f5_card_export .f5-info-banner {
        margin-bottom: 0.56rem !important;
    }
    .f5-action-title { color: #1d407f; font-size: 0.66rem; font-weight: 850; margin-top: 0.2rem; line-height:1.1; }
    .f5-action-description { color: #000000; font-size: 0.54rem; font-weight: 400; line-height: 1.13; }
    .f5-action-button {
        border: 1px solid #8bb7ff;
        border-radius: 11px;
        color: #0b63f6;
        font-weight: 850;
        font-size: 0.58rem;
        text-align: center;
        padding: 0.38rem 0.24rem;
        background: #ffffff;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    .f5-action-button.btn-blue { border-color:#8bb7ff; color:#0b63f6; background:#f0f6ff; }
    .f5-action-button.btn-orange { border-color:#f5c274; color:#c47a11; background:#fef8ec; }
    .f5-action-button.btn-red { border-color:#f5a0a0; color:#c02020; background:#fef2f2; }
    .f5-action-button.btn-green { border-color:#86e0a0; color:#16a34a; background:#f0fdf4; }
    .f5-action-button.btn-purple { border-color:#c9a4f5; color:#7e22ce; background:#faf5ff; }
    .f5-action-icon-wrap { width:2.12rem; height:2.12rem; min-width:2.12rem; border-radius:999px; display:inline-flex; align-items:center; justify-content:center; }
    .f5-action-icon-wrap.ic-blue { background:#ecf4ff; }
    .f5-action-icon-wrap.ic-orange { background:#fef3cd; }
    .f5-action-icon-wrap.ic-red { background:#fee2e2; }
    .f5-action-icon-wrap.ic-green { background:#dcfce7; }
    .f5-action-icon-wrap.ic-purple { background:#f3e8ff; }
    .f5-main-results-card {
        border: 1px solid #cbd5e1;
        border-radius: 20px;
        background: #ffffff;
        box-shadow: 0 8px 20px rgba(15, 45, 90, 0.035);
        padding: 1.02rem 1.08rem 1.1rem 1.08rem;
    }
    .f5-main-results-header {
        display: flex;
        align-items: center;
        gap: 0.56rem;
        margin-bottom: 0.52rem;
    }
    .f5-main-results-grid {
        margin-top: 0 !important;
    }
    .f5-main-results-spacer {
        height: 0 !important;
    }
    .f5-main-results-first-row {
        margin-top: 16px !important;
    }
    .f5-main-results-row-gap { height: 0.92rem; }
    .f5-main-results-icon {
        width: 2rem;
        height: 2rem;
        min-width: 2rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #ecf4ff;
        border: 1px solid #bfd8fb;
    }
    .f5-main-results-title {
        color: #10346f;
        font-size: 0.98rem;
        font-weight: 850;
        line-height: 1.14;
    }
    .f5-main-kpi-card {
        min-height: 112px;
        max-height: 124px;
        display: flex;
        align-items: center;
        gap: 0.88rem;
        margin-top: -4px;
        padding: 0.92rem 0.96rem;
        border: 1px solid #cbd5e1;
        border-radius: 16px;
        background: #ffffff;
        box-shadow: 0 5px 14px rgba(15, 45, 90, 0.028);
    }
    .f5-main-kpi-icon {
        width: 52px;
        height: 52px;
        min-width: 52px;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        border: 1px solid transparent;
    }
    .f5-main-kpi-icon.icon-blue { background: #eaf2ff; border-color: #d5e7ff; color: #2563eb; }
    .f5-main-kpi-icon.icon-green { background: #e8f9ef; border-color: #c8f0d8; color: #16a34a; }
    .f5-main-kpi-icon.icon-purple { background: #f4ebff; border-color: #e4d3ff; color: #7e22ce; }
    .f5-main-kpi-icon.icon-amber { background: #fff4dc; border-color: #fde3b2; color: #d97706; }
    .f5-main-kpi-title {
        color: #000000;
        font-size: 0.67rem;
        font-weight: 400;
        line-height: 1.16;
        margin-bottom: 0.16rem;
    }
    .f5-main-kpi-method {
        color: #000000;
        font-size: 0.64rem;
        font-weight: 400;
        line-height: 1.1;
        margin-bottom: 0.2rem;
    }
    .f5-main-kpi-value {
        color: #0f2f6e;
        font-size: 1.56rem;
        line-height: 1.03;
        font-weight: 900;
    }
    .f5-main-kpi-unit {
        color: #000000;
        font-size: 0.78rem;
        font-weight: 400;
        margin-top: 0.16rem;
        line-height: 1.15;
    }
    .f5-param-chip {
        border: 1px solid #cbd5e1;
        border-radius: 13px;
        background: #f9fcff;
        box-shadow: 0 3px 10px rgba(15, 45, 90, 0.02);
        padding: 0.52rem 0.62rem;
        min-height: 64px;
        display: flex;
        align-items: center;
        gap: 0.52rem;
        margin-top: -2px;
    }
    .f5-param-chip__icon {
        width: 1.8rem;
        height: 1.8rem;
        min-width: 1.8rem;
        border-radius: 999px;
        background: #ecf4ff;
        border: 1px solid #bfd8fb;
        display: inline-flex;
        align-items: center;
        justify-content: center;
    }
    .f5-param-chip__name {
        color: #000000;
        font-size: 0.65rem;
        font-weight: 400;
        line-height: 1.14;
    }
    .f5-param-chip__value {
        color: #10346f;
        font-size: 0.95rem;
        font-weight: 850;
        line-height: 1.06;
        margin-top: 0.14rem;
    }
    .f5-profile-summary-box {
        margin: 0.45rem 0 0.85rem 0;
        padding: 0.72rem 0.78rem 0.78rem 0.78rem;
        border: 1px solid #d9e9ff;
        border-radius: 16px;
        background: #ffffff;
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.04);
    }
    .f5-profile-summary-alert {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.5rem 0.62rem;
        border: 1px solid #cfe4ff;
        border-radius: 10px;
        background: #eef6ff;
        color: #1d4f91;
        font-size: 0.82rem;
        font-weight: 700;
    }
    .f5-profile-summary-info-icon {
        width: 1.15rem;
        height: 1.15rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #1e63d9;
        color: #fff;
        font-size: 0.72rem;
        line-height: 1;
        font-weight: 800;
        flex-shrink: 0;
    }
    .f5-profile-summary-grid {
        margin-top: 0.58rem;
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.58rem;
    }
    .f5-profile-summary-kpi {
        display: flex;
        align-items: center;
        gap: 0.58rem;
        border: 1px solid #dceaff;
        border-radius: 12px;
        background: #fbfdff;
        padding: 0.62rem 0.7rem;
        min-height: 58px;
    }
    .f5-profile-summary-kpi-icon {
        width: 2rem;
        height: 2rem;
        min-width: 2rem;
        border-radius: 999px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background: #eaf2ff;
        color: #2563eb;
        border: 1px solid #d4e6ff;
    }
    .f5-profile-summary-kpi-label {
        font-size: 0.76rem;
        font-weight: 400;
        color: #000000;
        line-height: 1.2;
    }
    .f5-profile-summary-kpi-value {
        margin-top: 0.08rem;
        font-size: 1rem;
        font-weight: 800;
        color: #173f88;
        line-height: 1.1;
    }
    .stDataFrame { border-radius: 14px !important; overflow: hidden !important; }
    .stDataFrame thead tr th {
        background: #f1f7ff !important;
        color: #000000 !important;
    }
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
    div[data-testid="stNumberInput"] input {
        background: #ffffff !important;
        border-color: #d7e7fb !important;
        border-radius: 10px !important;
        box-shadow: none !important;
    }
    div[data-testid="stNumberInput"] button {
        background: #ffffff !important;
        border: 1px solid #d7e7fb !important;
        color: #0b4edb !important;
    }
    div[data-testid="stNumberInput"] button:hover {
        background: #f1f7ff !important;
        border-color: #9ec5ff !important;
    }
    .st-key-f5_card_config div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
    .st-key-f5_card_losses div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
    .st-key-f5_card_econ_currency div[data-testid="stSelectbox"] [data-baseweb="select"] > div,
    .st-key-f5_card_config div[data-testid="stNumberInput"] input,
    .st-key-f5_card_losses div[data-testid="stNumberInput"] input,
    .st-key-f5_card_econ_currency div[data-testid="stNumberInput"] input,
    .st-key-f5_card_econ_master div[data-testid="stNumberInput"] input {
        background: #ffffff !important;
        border-color: #d7e7fb !important;
        border-radius: 10px !important;
        box-shadow: none !important;
    }
    .st-key-f5_card_config div[data-testid="stNumberInput"] button,
    .st-key-f5_card_losses div[data-testid="stNumberInput"] button,
    .st-key-f5_card_econ_currency div[data-testid="stNumberInput"] button,
    .st-key-f5_card_econ_master div[data-testid="stNumberInput"] button {
        background: #ffffff !important;
        border: 1px solid #d7e7fb !important;
        color: #0b4edb !important;
    }
    .st-key-f5_card_config div[data-testid="stNumberInput"] button:hover,
    .st-key-f5_card_losses div[data-testid="stNumberInput"] button:hover,
    .st-key-f5_card_econ_currency div[data-testid="stNumberInput"] button:hover,
    .st-key-f5_card_econ_master div[data-testid="stNumberInput"] button:hover {
        background: #f1f7ff !important;
        border-color: #9ec5ff !important;
    }
    @media (max-width: 1200px) {
        .hero-card { padding: 1.2rem 1.18rem 1.1rem 1.18rem; }
        .f5-action-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    /* ===== CSS Export Cards ===== */
    .f5-ref-export-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin:8px 0 0; }
    .f5-ref-export-card { background:#ffffff; border:1px solid #c8dcfb; border-radius:18px; padding:16px; box-shadow:0 8px 20px rgba(15,45,90,.04); display:flex; flex-direction:column; gap:12px; min-height:145px; overflow:hidden; transition:box-shadow .18s; justify-content: space-between; }
    .f5-ref-export-card:hover { box-shadow:0 12px 28px rgba(15,45,90,.08); }
    .f5-ref-export-top { display:flex; align-items:flex-start; gap:12px; flex-direction: row; text-align: left; }
    .f5-ref-export-icon { width:46px; height:46px; border-radius:12px; display:inline-flex; align-items:center; justify-content:center; flex:0 0 46px; }
    .f5-ref-export-icon-pdf { background:#ffffff; color:#dc2626; border:1px solid transparent; }
    .f5-ref-export-icon-word { background:#ffffff; color:#2563eb; border:1px solid transparent; }
    .f5-ref-export-icon-excel { background:#ffffff; color:#16a34a; border:1px solid transparent; }
    .f5-ref-export-icon-json { background:#ffffff; color:#7c3aed; border:1px solid transparent; }
    .f5-ref-export-icon-orange { background:#ffffff; color:#d97706; border:1px solid transparent; }
    .f5-ref-export-title { color:#1e293b; font-size:12px; font-weight:800; margin-bottom:4px; line-height:1.2; }
    .f5-ref-export-desc { color:#000000; font-size:10px; font-weight:400; line-height:1.3; }
    @media(max-width:1200px){.f5-ref-export-grid{grid-template-columns:repeat(3,1fr)}}
    @media(max-width:700px){.f5-ref-export-grid{grid-template-columns:repeat(2,1fr)}}
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"]{margin-top:-56px;padding:0 4px;position:relative;z-index:10}
    .st-key-f5_card_export a[href^="Fase_"]{width:100%;background:#ffffff !important;border:1.2px solid #bfdbfe !important;color:#2563eb !important;border-radius:10px !important;font-weight:700 !important;min-height:38px !important;font-size:12.5px !important;justify-content:center !important;text-decoration:none !important;transition:all .18s;display:flex;align-items:center;gap:6px;}
    .st-key-f5_card_export a[href^="Fase_"]:hover{background:#f8fafc !important;border-color:#2563eb !important;}
    
    /* Specific Colors for Action Buttons */
    /* 1: PDF (Red) */
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(1) a[href^="Fase_"] { background: #fef2f2 !important; border-color: #fecaca !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(1) a[href^="Fase_"] * { color: #dc2626 !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(1) a[href^="Fase_"]:hover { background: #fee2e2 !important; border-color: #fca5a5 !important; }

    /* 2: Excel (Green) */
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(2) a[href^="Fase_"] { background: #f0fdf4 !important; border-color: #bbf7d0 !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(2) a[href^="Fase_"] * { color: #16a34a !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(2) a[href^="Fase_"]:hover { background: #dcfce7 !important; border-color: #86efac !important; }

    /* 3: Word (Blue) */
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(3) a[href^="Fase_"] { background: #eff6ff !important; border-color: #bfdbfe !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(3) a[href^="Fase_"] * { color: #2563eb !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(3) a[href^="Fase_"]:hover { background: #dbeafe !important; border-color: #93c5fd !important; }

    /* 4: Save (Purple) */
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(4) a[href^="Fase_"] { background: #f5f3ff !important; border-color: #ddd6fe !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(4) a[href^="Fase_"] * { color: #7c3aed !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(4) a[href^="Fase_"]:hover { background: #ede9fe !important; border-color: #c4b5fd !important; }

    /* 5: Load (Orange) */
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(5) a[href^="Fase_"] { background: #fffbeb !important; border-color: #fde68a !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(5) a[href^="Fase_"] * { color: #d97706 !important; }
    .st-key-f5_card_export div[data-testid="stHorizontalBlock"] > div:nth-child(5) a[href^="Fase_"]:hover { background: #fef3c7 !important; border-color: #fcd34d !important; }
    /* ── Responsive fixes for Phase 5 cards ─────────── */
    .st-key-f5_card_breakdown,
    .st-key-f5_card_breakdown div[data-testid="stVerticalBlockBorderWrapper"] {
        height: auto !important;
        min-height: unset !important;
        max-height: none !important;
        overflow: visible !important;
    }

    /* ── LCOE card height override (must be last to win cascade) ─────────── */
    .st-key-f5_econ_lcoe_card {
        min-height: 600px !important;
        height: auto !important;
        max-height: none !important;
        box-sizing: border-box !important;
        overflow: visible !important;
    }
    .st-key-f5_econ_lcoe_card > div[data-testid="stVerticalBlockBorderWrapper"] {
        min-height: 600px !important;
        height: auto !important;
        max-height: none !important;
        box-sizing: border-box !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: flex-start !important;
        overflow: visible !important;
    }

    @media (max-width: 1200px) {
        .f5-econ-mostrado-grid-inside-lcoe {
            grid-template-columns: 1fr !important;
        }
        .f5-loss-table-ref {
            width: 100% !important;
            table-layout: fixed !important;
            font-size: 0.72rem !important;
        }
        .f5-loss-table-ref th {
            font-size: 0.70rem !important;
            padding: 0.46rem 0.46rem !important;
            line-height: 1.12 !important;
            white-space: normal !important;
        }
        .f5-loss-table-ref td {
            font-size: 0.76rem !important;
            padding: 0.44rem 0.46rem !important;
            line-height: 1.12 !important;
            white-space: normal !important;
        }
        .f5-loss-table-ref th:nth-child(1),
        .f5-loss-table-ref td:nth-child(1) {
            width: 38% !important;
        }
        .f5-loss-table-ref th:nth-child(2),
        .f5-loss-table-ref td:nth-child(2) {
            width: 24% !important;
        }
        .f5-loss-table-ref th:nth-child(3),
        .f5-loss-table-ref td:nth-child(3) {
            width: 38% !important;
        }
    }

    @media (max-width: 900px) {
        .f5-sector-table-ref {
            min-width: 680px !important;
        }
        .f5-loss-table-ref {
            font-size: 0.66rem !important;
        }
        .f5-loss-table-ref th {
            font-size: 0.64rem !important;
            padding: 0.34rem 0.34rem !important;
        }
        .f5-loss-table-ref td {
            font-size: 0.70rem !important;
            padding: 0.34rem 0.34rem !important;
        }
    }
    @media (max-width: 1400px) {
        .st-key-f5_card_econ_currency div[data-testid="stVerticalBlockBorderWrapper"] {
            gap: 0.45rem !important;
            padding-bottom: 0.45rem !important;
        }
        .f5-econ-fx-strip {
            margin-top: 0.20rem !important;
            margin-bottom: 0.25rem !important;
            padding: 0.38rem 0.58rem !important;
        }
    }

    /* ── Ensure outer stVerticalBlockBorderWrapper has rounded blue border ──
       Handles both HTML structures Streamlit may use for keyed containers */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_header),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_config),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_losses),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_results),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_compare),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_breakdown),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_sector),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_econ_master),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_econ_base),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_econ_currency),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_export),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_sector_table_card),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_sector_chart_card),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_econ_capex_card),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_econ_opex_card),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_econ_lcoe_card) {
        border: 1px solid #cbd5e1 !important;
        border-radius: 22px !important;
        background: linear-gradient(180deg, #ffffff 0%, #f9fbff 100%) !important;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05) !important;
        overflow: hidden !important;
    }
    /* Reset inner div conflicting styles (when key class is inside the wrapper) */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_header) > .st-key-f5_card_header,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_config) > .st-key-f5_card_config,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_losses) > .st-key-f5_card_losses,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_results) > .st-key-f5_card_results,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_compare) > .st-key-f5_card_compare,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_breakdown) > .st-key-f5_card_breakdown,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_sector) > .st-key-f5_card_sector,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_econ_master) > .st-key-f5_card_econ_master,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_econ_base) > .st-key-f5_card_econ_base,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_econ_currency) > .st-key-f5_card_econ_currency,
    div[data-testid="stVerticalBlockBorderWrapper"]:has(> .st-key-f5_card_export) > .st-key-f5_card_export {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
    }

</style>
"""


def _f5_icon_svg(name: str, color: str = "#0B63F6", size: int = 22) -> str:
    stroke = f'stroke="{color}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    stroke_bold = f'stroke="{color}" stroke-width="2.35" stroke-linecap="round" stroke-linejoin="round" fill="none"'

    if name == "energy":
        body = (
            f'<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" fill="{color}" opacity="0.15"/>'
            f'<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" {stroke}/>'
        )
    elif name == "settings":
        body = (
            f'<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" fill="{color}" opacity="0.15"/>'
            f'<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" {stroke}/>'
            f'<circle cx="12" cy="12" r="3" {stroke}/>'
        )
    elif name == "loss":
        body = (
            f'<path d="M3.8 12h3.3l2.2-4.1 4.1 8.1 2.2-4h4.6" {stroke_bold}/>'
        )
    elif name == "pie-chart-detached":
        body = (
            f'<path d="M21.21 15.89A10 10 0 1 1 8 2.83" {stroke_bold}/>'
            f'<path d="M22 12A10 10 0 0 0 12 2v10z" {stroke_bold}/>'
        )
    elif name == "chart":
        body = (
            f'<rect x="4" y="14" width="4" height="6" fill="{color}" opacity="0.15"/>'
            f'<rect x="10" y="4" width="4" height="16" fill="{color}" opacity="0.15"/>'
            f'<rect x="16" y="10" width="4" height="10" fill="{color}" opacity="0.15"/>'
            f'<path d="M18 20V10" {stroke_bold}/><path d="M12 20V4" {stroke_bold}/><path d="M6 20v-6" {stroke_bold}/>'
        )
    elif name == "sector":
        body = (
            f'<rect x="3" y="3" width="18" height="18" rx="2" ry="2" {stroke_bold}/>'
            f'<path d="M9 3v18" {stroke_bold}/>'
            f'<path d="M9 9h12" {stroke_bold}/>'
            f'<path d="M9 15h12" {stroke_bold}/>'
        )
    elif name == "money":
        body = (
            f'<circle cx="12" cy="12" r="10" fill="{color}" opacity="0.15"/>'
            f'<circle cx="12" cy="12" r="10" {stroke}/>'
            f'<path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8" {stroke}/>'
            f'<path d="M12 18V6" {stroke}/>'
        )
    elif name == "export":
        body = (
            f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" fill="{color}" opacity="0.1"/>'
            f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" {stroke}/>'
            f'<polyline points="7 10 12 15 17 10" {stroke}/>'
            f'<line x1="12" y1="15" x2="12" y2="3" {stroke}/>'
        )
    elif name == "turbine":
        blade = f'<path d="M11 10 L11.4 2 A 0.6 0.6 0 0 1 12.6 2 L13 10 Z" fill="{color}"/>'
        body = (
            f'<path d="M10.5 22 L11.4 10 H12.6 L13.5 22 Z" fill="{color}"/>'
            + blade
            + f'<g transform="rotate(120 12 10)">{blade}</g>'
            + f'<g transform="rotate(240 12 10)">{blade}</g>'
            + f'<circle cx="12" cy="10" r="2.2" fill="{color}"/>'
            + '<circle cx="12" cy="10" r="0.6" fill="#ffffff"/>'
        )
    elif name == "gauge":
        body = (
            f'<path d="M3 15a9 9 0 0 1 18 0" {stroke_bold}/>'
            f'<path d="M12 6V9" {stroke_bold}/>'
            f'<path d="M5.5 8.5L7.5 10.5" {stroke_bold}/>'
            f'<path d="M18.5 8.5L16.5 10.5" {stroke_bold}/>'
            f'<path d="M12 15L7 10" {stroke_bold}/>'
            f'<circle cx="12" cy="15" r="2" fill="{color}"/>'
        )
    elif name == "power-module":
        body = (
            f'<path d="M14 6h3a2.5 2.5 0 0 1 2.5 2.5v7A2.5 2.5 0 0 1 17 18h-3" {stroke_bold}/>'
            f'<path d="M16.5 10v4" {stroke_bold}/>'
            f'<rect x="4.5" y="4" width="9.5" height="16" rx="2.2" {stroke_bold}/>'
            f'<rect x="7.2" y="8" width="4.1" height="4.5" rx="1" {stroke_bold}/>'
        )
    elif name == "group":
        body = (
            f'<circle cx="12" cy="7" r="4" fill="{color}" opacity="0.15"/><circle cx="12" cy="7" r="4" {stroke}/>'
            f'<path d="M5.5 21v-2a4 4 0 0 1 4-4h5a4 4 0 0 1 4 4v2" fill="{color}" opacity="0.15"/><path d="M5.5 21v-2a4 4 0 0 1 4-4h5a4 4 0 0 1 4 4v2" {stroke}/>'
            f'<circle cx="5" cy="8" r="3" {stroke}/><path d="M2 19v-1a3 3 0 0 1 3-3" {stroke}/>'
            f'<circle cx="19" cy="8" r="3" {stroke}/><path d="M22 19v-1a3 3 0 0 0-3-3" {stroke}/>'
        )
    elif name == "file":
        body = (
            f'<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" fill="{color}" opacity="0.15"/>'
            f'<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" {stroke}/>'
            f'<polyline points="13 2 13 9 20 9" {stroke}/>'
        )
    elif name == "excel":
        body = (
            f'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="{color}" opacity="0.15"/>'
            f'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" {stroke}/>'
            f'<polyline points="14 2 14 8 20 8" {stroke}/>'
            f'<path d="M8 13l3 4" {stroke_bold}/>'
            f'<path d="M11 13l-3 4" {stroke_bold}/>'
            f'<rect x="13" y="13" width="3" height="4" {stroke}/>'
            f'<line x1="13" y1="15" x2="16" y2="15" {stroke}/>'
        )
    elif name == "pdf":
        body = (
            f'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="{color}" opacity="0.15"/>'
            f'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" {stroke}/>'
            f'<polyline points="14 2 14 8 20 8" {stroke}/>'
            f'<path d="M8 13h2a2 2 0 1 1 0 4H8v-4z" {stroke}/>'
            f'<line x1="8" y1="17" x2="8" y2="19" {stroke}/>'
        )
    elif name == "word":
        body = (
            f'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="{color}" opacity="0.15"/>'
            f'<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" {stroke}/>'
            f'<polyline points="14 2 14 8 20 8" {stroke}/>'
            f'<polyline points="8 13 10 17 12 13 14 17 16 13" {stroke}/>'
        )
    elif name == "save":
        body = (
            f'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" fill="{color}" opacity="0.15"/>'
            f'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" {stroke}/>'
            f'<polyline points="17 21 17 13 7 13 7 21" {stroke}/>'
            f'<polyline points="7 3 7 8 15 8" {stroke}/>'
        )
    elif name == "folder":
        body = (
            f'<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="{color}" opacity="0.15"/>'
            f'<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" {stroke}/>'
        )
    else:
        body = f'<circle cx="12" cy="12" r="8" {stroke}/>'

    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="display:block; overflow:visible;">{body}</svg>'

def _render_f5_section_header(icon: str, title: str, subtitle: str | None = None):
    subtitle_html = f'<div class="f5-section-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="f5-section-header"><span class="f5-section-icon">{icon}</span><div><div class="f5-section-title">{title}</div>{subtitle_html}</div></div>',
        unsafe_allow_html=True,
    )


def _render_f5_section_header_card(icon: str, title: str, subtitle: str | None = None):
    subtitle_html = f'<span class="f5-section-header-card-subtitle">{subtitle}</span>' if subtitle else ""
    st.markdown(
        (
            '<div class="f5-section-header-card">'
            f'<span class="f5-section-header-icon">{icon}</span>'
            f'<span class="f5-section-header-card-text">'
            f'<span class="f5-section-header-card-title">{title}</span>'
            f'{subtitle_html}'
            f'</span>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def _render_f5_kpi_card(icon, label, value, unit="", caption="", accent="blue"):
    unit_html = f'<div class="f5-kpi-unit">{unit}</div>' if unit else ""
    caption_html = f'<div class="f5-kpi-caption">{caption}</div>' if caption else ""
    st.markdown(
        f'<div class="f5-kpi-card accent-{accent}"><div class="f5-kpi-icon">{icon}</div><div><div class="f5-kpi-label">{label}</div><div class="f5-kpi-value">{value}</div>{unit_html}{caption_html}</div></div>',
        unsafe_allow_html=True,
    )


def _render_f5_main_result_card(icon, icon_tone, title, method, value, unit):
    method_html = f'<div class="f5-main-kpi-method">{method}</div>' if method else ""
    st.markdown(
        (
            f'<div class="f5-main-kpi-card">'
            f'<div class="f5-main-kpi-icon icon-{icon_tone}">{icon}</div>'
            f'<div>'
            f'<div class="f5-main-kpi-title">{title}</div>'
            f'{method_html}'
            f'<div class="f5-main-kpi-value">{value}</div>'
            f'<div class="f5-main-kpi-unit">{unit}</div>'
            f'</div>'
            f'</div>'
        ),
        unsafe_allow_html=True,
    )


def _render_f5_action_card(icon, title, description, button_label, icon_color="blue", btn_color="blue"):
    if icon_color == "red":
        file_type = "pdf"
    elif icon_color == "blue":
        file_type = "word"
    elif icon_color == "green":
        file_type = "excel"
    elif icon_color == "purple":
        file_type = "json"
    elif icon_color == "orange":
        file_type = "orange"
    else:
        file_type = "default"

    return (
        f'<div class="f5-ref-export-card">'
        f'<div class="f5-ref-export-top">'
        f'<div class="f5-ref-export-icon f5-ref-export-icon-{file_type}">'
        f'<div style="position:relative;width:100%;height:100%;display:flex;align-items:center;justify-content:center;">'
        f'{icon}'
        f'</div>'
        f'</div>'
        f'<div><div class="f5-ref-export-title">{title}</div>'
        f'<div class="f5-ref-export-desc">{description}</div></div>'
        f'</div>'
        f'<div style="height:40px;width:100%;flex-shrink:0;"></div>'
        f'</div>'
    )


def _render_f5_info(text: str):
    st.markdown(
        f'<div class="f5-info-banner"><span class="f5-info-dot">i</span><span>{text}</span></div>',
        unsafe_allow_html=True,
    )




def _build_econ_breakdown_html(breakdown_list, title, col_headers, moneda, potencia_mw=None):
    rows_html = ""
    for item in breakdown_list:
        concepto = item.get("Concepto", "")
        valor = item.get("Valor", 0.0)
        is_total = "total" in concepto.lower()
        tr_class = ' class="f5-econ-total-row"' if is_total else ""
        if len(col_headers) == 3 and potencia_mw and potencia_mw > 0:
            per_mw = valor / potencia_mw
            rows_html += f"<tr{tr_class}><td>{concepto}</td><td>{per_mw:,.0f}</td><td>{valor:,.0f}</td></tr>"
        else:
            rows_html += f"<tr{tr_class}><td>{concepto}</td><td>{valor:,.0f}</td></tr>"
    th_html = "".join(f"<th>{h}</th>" for h in col_headers)
    return (f'<div class="f5-econ-table-title">{title}</div>'
            f'<div class="f5-econ-table-wrap"><table class="f5-econ-table">'
            f'<thead><tr>{th_html}</tr></thead><tbody>{rows_html}</tbody></table></div>')


def _build_opex_breakdown_html(breakdown_list, title, moneda, potencia_mw=None):
    rows_html = ""
    for item in breakdown_list:
        concepto = item.get("Concepto", "")
        valor = item.get("Valor", 0.0)
        is_total = "total" in concepto.lower()
        tr_class = ' class="f5-econ-total-row"' if is_total else ""
        per_mw = valor / potencia_mw if potencia_mw and potencia_mw > 0 else 0.0
        rows_html += f"<tr{tr_class}><td>{concepto}</td><td>{valor:,.0f}</td><td>{per_mw:,.0f}</td></tr>"
    return (f'<div class="f5-econ-table-title">{title}</div>'
            f'<div class="f5-econ-table-wrap"><table class="f5-econ-table">'
            f'<thead><tr><th>Concepto</th><th>{moneda}/año</th><th>{moneda}/año·MW</th></tr></thead>'
            f'<tbody>{rows_html}</tbody></table></div>')


def _econ_mini_kpi(icon_svg, label, value, unit=""):
    u = f'<div class="f5-econ-mini-kpi-unit">{unit}</div>' if unit else ""
    return (f'<div class="f5-econ-mini-kpi">'
            f'<div class="f5-econ-mini-kpi-header"><div class="f5-econ-mini-kpi-icon">{icon_svg}</div><div class="f5-econ-mini-kpi-label">{label}</div></div>'
            f'<div class="f5-econ-mini-kpi-body"><div class="f5-econ-mini-kpi-value">{value}</div>{u}</div>'
            f'</div>')


def _econ_lcoe_kpi(icon_svg, color, label, value, unit=""):
    u = f'<div class="f5-econ-lcoe-kpi-unit">{unit}</div>' if unit else ""
    val_class = f"f5-econ-lcoe-kpi-value {color}-val"
    return (f'<div class="f5-econ-lcoe-kpi">'
            f'<div class="f5-econ-lcoe-kpi-label">{label}</div>'
            f'<div class="{val_class}">{value}</div>{u}</div>')


def _econ_mostrado_card(icon_svg, color, label, value):
    return (f'<div class="f5-econ-mostrado-card"><div class="f5-econ-mostrado-icon {color}">{icon_svg}</div>'
            f'<div><div class="f5-econ-mostrado-label">{label}</div>'
            f'<div class="f5-econ-mostrado-value">{value}</div></div></div>')



st.markdown(FASE_5_CSS, unsafe_allow_html=True)

# Bloque CSS final forzado: aplicar patrón visual de Fase 1 a cards grandes de Fase 5
st.markdown(
    """
    <style>
    /* =========================================================
       FORZADO FINAL: estilo SMA 2.0 para cards grandes - Fase 5
       ========================================================= */

    .st-key-f5_card_header,
    .st-key-f5_card_config,
    .st-key-f5_card_losses,
    .st-key-f5_card_results,
    .st-key-f5_card_compare,
    .st-key-f5_card_breakdown,
    .st-key-f5_card_sector,
    .st-key-f5_card_econ_master,
    .st-key-f5_card_econ_base,
    .st-key-f5_card_econ_currency,
    .st-key-f5_card_export,
    .st-key-f5_econ_capex_card,
    .st-key-f5_econ_opex_card,
    .st-key-f5_econ_lcoe_card,
    .st-key-f5_card_ti_iec,
    .st-key-f5_card_sens_tornado,
    .st-key-f5_card_montecarlo,
    .st-key-f5_card_aep_serie {
        border: 1px solid #cbd5e1 !important;
        border-radius: 28px !important;
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%) !important;
        box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
        overflow: visible !important;
        box-sizing: border-box !important;
    }

    .st-key-f5_card_header {
        border: 1.35px solid #cbd5e1 !important;
        border-radius: 28px !important;
    }

    .st-key-f5_card_header div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_config div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_losses div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_results div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_compare div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_breakdown div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_sector div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_master div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_base div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_econ_currency div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_export div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_econ_capex_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_econ_opex_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_econ_lcoe_card div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_ti_iec div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_sens_tornado div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_montecarlo div[data-testid="stVerticalBlockBorderWrapper"],
    .st-key-f5_card_aep_serie div[data-testid="stVerticalBlockBorderWrapper"] {
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

config = cargar_config()
project_context = get_project_context(config)
report_context = get_report_context(config)
df_nasa = cargar_nasa_hourly()
df_curva_raw = cargar_tabla_curva()
df_layout = cargar_layout_parque()

if len(df_nasa) == 0:
    st.warning("Primero cargue datos horarios en la Fase 2.")
    st.stop()

df_curva = _session_cached_result(
    "f5_curva_preparada",
    ("curva", _df_signature(df_curva_raw)),
    lambda: preparar_datos_curva(df_curva_raw),
)
if len(df_curva) == 0:
    st.warning("Primero defina una curva de potencia válida en la Fase 1.")
    st.stop()

diametro = float(config.get("diametro") or 100.0)
altura_deseada_default = float(config.get("perfil_hhub") or 100.0)
base_viento_default = energia_calc.normalize_base_viento_for_energy(
    config.get("f5_base_viento", config.get("f4_base_viento_canonica", config.get("f4_base_viento", "50 m")))
)
dir_altura_default = config.get("f5_dir_altura", config.get("f4_dir_altura", "WD50M"))
roughness_default = config.get("f5_roughness_label", config.get("f4_roughness_label", "Grass / Césped"))
modo_estadistico_default = config.get("f5_modo_estadistico", "Weibull")
metodo_detalle_default = config.get("f5_metodo_detalle", "Weibull")
wake_mode_default = config.get("f5_wake_mode", "Automática desde Fase 4")
wake_manual_default = float(config.get("f5_wake_manual_pct", 5.0))
disp_default = float(config.get("f5_disp_pct", 3.0))
elec_default = float(config.get("f5_elec_pct", 2.0))
otras_default = float(config.get("f5_otras_pct", 1.5))

# A1 - densidad
altitud_default = float(config.get("f5_altitud_sitio_m") or 0.0)
temperatura_media_default = float(config.get("f5_temperatura_media_c") or 15.0)
densidad_correccion_aplicada_default = str(config.get("f5_densidad_correccion_aplicada", "True")).strip().lower() in ("true", "1", "si", "sí", "yes")

# A2 - pérdidas extra
loss_disp_red_default = float(config.get("f5_loss_disp_red_pct") or 0.0)
loss_hielo_default = float(config.get("f5_loss_hielo_pct") or 0.0)
loss_histeresis_default = float(config.get("f5_loss_histeresis_pct") or 0.0)
loss_curtailment_default = float(config.get("f5_loss_curtailment_pct") or 0.0)

# A3 - financieras
precio_energia_default = float(config.get("f5_precio_energia_mwh") or 60.0)

# A4 - sensibilidad
sens_delta_default = float(config.get("f5_sens_delta_pct") or 15.0)

# A5 - wake model
wake_model_options = ["Jensen", "Larsen", "Frandsen", "Gaussian", "TurbOPark", "DWM"]
try:
    from calculos import _pywake_disponible as _pw_avail
    if _pw_avail():
        wake_model_options += ["pyWake-NOJ", "pyWake-Bastankhah", "pyWake-Niayifar"]
except Exception:
    pass
wake_model_default = str(config.get("f5_wake_model") or config.get("f4_wake_model") or "Jensen").strip().capitalize()
if wake_model_default not in wake_model_options:
    wake_model_default = "Jensen"
ambient_ti_default = float(config.get("f5_ambient_ti") or 0.10)

# A6 - IEC
iec_clase_default = str(config.get("f5_iec_clase_declarada") or "II").upper()
iec_turb_default = str(config.get("f5_iec_turb_declarada") or "B").upper()
project_name_default = config.get("project_name", "Proyecto_eolico_1")
capex_mode_default = str(config.get("f5_capex_mode") or "semi_auto_mw")
capex_total_default = float(config.get("f5_capex_total") or 0.0)
capex_turbina_por_mw_default = float(config.get("f5_capex_turbina_por_mw") or 1100000.0)
capex_bop_por_mw_default = float(config.get("f5_capex_bop_por_mw") or 450000.0)
capex_red_por_mw_default = float(config.get("f5_capex_red_por_mw") or 150000.0)
capex_pct_desarrollo_default = float(config.get("f5_capex_pct_desarrollo") or 5.0)
capex_pct_contingencia_default = float(config.get("f5_capex_pct_contingencia") or 10.0)
capex_componentes_default = load_component_values(
    config.get("f5_capex_componentes_json"),
    CAPEX_COMPONENT_DEFAULTS,
)
opex_mode_default = str(config.get("f5_opex_mode") or "fixed_variable")
opex_total_anual_default = float(config.get("f5_opex_total_anual") or 0.0)
opex_fijo_anual_default = float(config.get("f5_opex_fijo_anual") or 0.0)
opex_fijo_por_mw_anio_default = float(config.get("f5_opex_fijo_por_mw_anio") or 45000.0)
opex_variable_default = float(config.get("f5_opex_variable_por_mwh") or 0.0)
seguros_anuales_default = float(config.get("f5_seguros_anuales") or 0.0)
terreno_anual_default = float(config.get("f5_terreno_anual") or 0.0)
admin_anual_default = float(config.get("f5_admin_anual") or 0.0)
opex_componentes_default = load_component_values(
    config.get("f5_opex_componentes_json"),
    OPEX_COMPONENT_DEFAULTS,
)
vida_util_default = max(1, int(float(config.get("f5_vida_util_anios") or 20)))
tasa_descuento_default = float(config.get("f5_tasa_descuento_pct") or 8.0)
degradacion_default = float(config.get("f5_degradacion_energia_pct") or 0.0)
valor_residual_default = float(config.get("f5_valor_residual") or 0.0)
moneda_base_default = str(config.get("f5_moneda_base") or config.get("f5_unidad_monetaria") or "USD").upper()
moneda_visualizacion_default = str(config.get("f5_moneda_visualizacion") or moneda_base_default).upper()
fx_mode_default = str(config.get("f5_fx_mode") or "manual")
fx_rate_default = float(config.get("f5_fx_rate_cop_per_usd") or 4000.0)
fx_timestamp_default = str(config.get("f5_fx_timestamp") or "")
fx_source_default = str(config.get("f5_fx_source") or "")
unidad_monetaria_default = moneda_base_default

n_turbinas_layout = len(df_layout) if len(df_layout) > 0 else int(float(config.get("f4_num_turbinas", 1)))
ct_default = float(config.get("f4_ct", 0.80))
kw_default = float(config.get("f4_kw", 0.05))


with st.container(border=True, key="f5_card_header"):
    st.markdown(
        """
        <div class="hero-card">
            <div class="fase-hero-title">Fase 5 &middot; AEP bruta y neta</div>
            <div class="fase-hero-subtitle">C&aacute;lculo de AEP bruta y neta, p&eacute;rdidas, an&aacute;lisis por sector y evaluaci&oacute;n econ&oacute;mica (CAPEX, OPEX y LCOE).</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
_render_f5_info("En esta fase se calcula la producción bruta del parque y la producción neta considerando todas las pérdidas definidas.")

# Initialize widget state before creating widgets
_init_widget_state("f5_base_viento", base_viento_default)
_init_widget_state("f5_modo_estadistico", modo_estadistico_default)
_init_widget_state("f5_altura_deseada", altura_deseada_default)
_init_widget_state("f5_n_turbinas", max(1, int(n_turbinas_layout)))
_init_widget_state("f5_dir_altura", dir_altura_default)
_init_widget_state("f5_ct", ct_default)
_init_widget_state("f5_kw", kw_default)
# A1, A5
_init_widget_state("f5_altitud_sitio_m", altitud_default)
_init_widget_state("f5_temperatura_media_c", temperatura_media_default)
_init_widget_state("f5_wake_model", wake_model_default)

top_config_col, top_losses_col = st.columns([1, 1], gap="large")

with top_config_col:
    with st.container(border=True, key="f5_card_config"):
        _render_f5_section_header(_f5_icon_svg("settings"), "Configuración del cálculo")
        with st.form("f5_config_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                base_viento = st.selectbox(
                    "Base de velocidad",
                    ["50 m", "10 m", "Exponencial", "Log A (2 puntos)", "Promedio Log-Exp"],
                    index=["50 m", "10 m", "Exponencial", "Log A (2 puntos)", "Promedio Log-Exp"].index(base_viento_default)
                    if base_viento_default in ["50 m", "10 m", "Exponencial", "Log A (2 puntos)", "Promedio Log-Exp"] else 0,
                    key="f5_base_viento",
                )
            with c2:
                modo_estadistico = st.selectbox(
                    "Modo estadístico",
                    ["Weibull", "Rayleigh", "Comparar Weibull y Rayleigh"],
                    index=["Weibull", "Rayleigh", "Comparar Weibull y Rayleigh"].index(modo_estadistico_default)
                    if modo_estadistico_default in ["Weibull", "Rayleigh", "Comparar Weibull y Rayleigh"] else 0,
                    key="f5_modo_estadistico",
                )

            c3, c4 = st.columns(2)
            with c3:
                altura_deseada = st.number_input(
                    "Altura deseada (m)",
                    min_value=0.10,
                    value=altura_deseada_default,
                    step=0.10,
                    format="%.2f",
                    key="f5_altura_deseada",
                )
            with c4:
                n_turbinas = st.number_input(
                    "Número de aerogeneradores",
                    min_value=1,
                    value=max(1, int(n_turbinas_layout)),
                    step=1,
                    key="f5_n_turbinas",
                )

            d1, d2, d3, d4 = st.columns([1.0, 0.7, 0.7, 0.9])
            with d1:
                dir_altura = st.selectbox(
                    "Dirección usada",
                    ["WD50M", "WD10M"],
                    index=0 if dir_altura_default == "WD50M" else 1,
                    key="f5_dir_altura",
                )
            with d2:
                ct = st.number_input(
                    "Ct",
                    min_value=0.01,
                    max_value=0.99,
                    value=ct_default,
                    step=0.01,
                    format="%.2f",
                    key="f5_ct",
                )
            with d3:
                kw = st.number_input(
                    "kw",
                    min_value=0.001,
                    value=kw_default,
                    step=0.005,
                    format="%.3f",
                    key="f5_kw",
                )
            with d4:
                wake_model_ui = st.selectbox(
                    "Modelo estela",
                    wake_model_options,
                    index=wake_model_options.index(wake_model_default),
                    key="f5_wake_model",
                )

            # A1 - corrección densidad
            e1, e2, e3 = st.columns([1, 1, 1])
            with e1:
                altitud_sitio_m = st.number_input(
                    "Altitud sitio (m)",
                    min_value=-100.0,
                    max_value=6000.0,
                    value=altitud_default,
                    step=10.0,
                    format="%.0f",
                    key="f5_altitud_sitio_m",
                )
            with e2:
                temperatura_media_c = st.number_input(
                    "Temperatura media (°C)",
                    min_value=-30.0,
                    max_value=50.0,
                    value=temperatura_media_default,
                    step=0.5,
                    format="%.1f",
                    key="f5_temperatura_media_c",
                )
            with e3:
                rho_sitio_calc = calculos.calcular_densidad_sitio(altitud_sitio_m, temperatura_media_c)
                factor_densidad_calc = calculos.factor_correccion_densidad(rho_sitio_calc)

                _t2m_avail = (df_nasa is not None and "T2M" in df_nasa.columns and pd.to_numeric(df_nasa["T2M"], errors="coerce").notna().any())
                densidad_modo_default = str(config.get("f5_densidad_modo", "anual")).strip().lower()
                if not _t2m_avail and densidad_modo_default == "mensual":
                    densidad_modo_default = "anual"
                densidad_modo_options = ["anual"] + (["mensual"] if _t2m_avail else [])
                densidad_modo = st.selectbox(
                    "Modo densidad",
                    densidad_modo_options,
                    index=densidad_modo_options.index(densidad_modo_default) if densidad_modo_default in densidad_modo_options else 0,
                    key="f5_densidad_modo",
                    help="anual: T+altitud constantes (A1) · mensual: T2M de NASA POWER por mes (B7, requiere T2M en datos)",
                )

                if densidad_modo == "mensual" and _t2m_avail:
                    _dens_mensual = calculos.agregar_densidad_mensual(df_nasa, altitud_m=altitud_sitio_m, temperatura_fallback_c=temperatura_media_c)
                    rho_anual_serie = _dens_mensual["anual"]
                    factor_densidad_calc = calculos.factor_correccion_densidad(rho_anual_serie)
                    rho_sitio_calc = rho_anual_serie

            roughness_label = roughness_default
            if modo_estadistico == "Comparar Weibull y Rayleigh":
                _init_widget_state("f5_metodo_detalle", metodo_detalle_default)
                metodo_detalle = st.selectbox(
                    "Método usado para gráficas detalladas, tablas principales y sensibilidad",
                    ["Weibull", "Rayleigh"],
                    index=0 if metodo_detalle_default == "Weibull" else 1,
                    key="f5_metodo_detalle",
                )
            else:
                metodo_detalle = modo_estadistico

            st.form_submit_button("Aplicar configuración", use_container_width=True)
# Persist configuration values to database
guardar_config_values({
    "f5_base_viento": energia_calc.normalize_base_viento_for_energy(st.session_state.get("f5_base_viento", base_viento_default)),
    "f5_modo_estadistico": st.session_state.get("f5_modo_estadistico", modo_estadistico_default),
    "f5_metodo_detalle": metodo_detalle,
    "f5_altura_deseada": st.session_state.get("f5_altura_deseada", altura_deseada_default),
    "f5_n_turbinas": st.session_state.get("f5_n_turbinas", n_turbinas_layout),
    "f5_dir_altura": st.session_state.get("f5_dir_altura", dir_altura_default),
    "f5_roughness_label": roughness_label,
    "f5_ct": st.session_state.get("f5_ct", ct_default),
    "f5_kw": st.session_state.get("f5_kw", kw_default),
    "f5_altitud_sitio_m": st.session_state.get("f5_altitud_sitio_m", altitud_default),
    "f5_temperatura_media_c": st.session_state.get("f5_temperatura_media_c", temperatura_media_default),
    "f5_densidad_sitio": f"{rho_sitio_calc:.4f}",
    "f5_wake_model": st.session_state.get("f5_wake_model", wake_model_default),
})

# Initialize widget state before creating widgets
_init_widget_state("f5_wake_mode", wake_mode_default)
_init_widget_state("f5_wake_manual_pct", wake_manual_default)
_init_widget_state("f5_disp_pct", disp_default)
_init_widget_state("f5_elec_pct", elec_default)
_init_widget_state("f5_otras_pct", otras_default)
_init_widget_state("f5_loss_disp_red_pct", loss_disp_red_default)
_init_widget_state("f5_loss_hielo_pct", loss_hielo_default)
_init_widget_state("f5_loss_histeresis_pct", loss_histeresis_default)
_init_widget_state("f5_loss_curtailment_pct", loss_curtailment_default)

with top_losses_col:
    with st.container(border=True, key="f5_card_losses"):
        _render_f5_section_header(_f5_icon_svg("loss"), "Pérdidas")
        with st.form("f5_losses_form", clear_on_submit=False):
            p1, p2 = st.columns(2)
            with p1:
                wake_mode = st.selectbox(
                    "Pérdida por estela",
                    ["Automática desde Fase 4", "Manual"],
                    index=0 if wake_mode_default == "Automática desde Fase 4" else 1,
                    key="f5_wake_mode",
                )
            with p2:
                wake_manual_pct = st.number_input(
                    "Estela manual (%)",
                    min_value=0.0,
                    value=wake_manual_default,
                    step=0.1,
                    format="%.2f",
                    disabled=(wake_mode == "Automática desde Fase 4"),
                    key="f5_wake_manual_pct",
                )

            p3, p4, p5, p6 = st.columns(4)
            with p3:
                disp_pct = st.number_input(
                    "Disp. turbina (%)",
                    min_value=0.0,
                    value=disp_default,
                    step=0.1,
                    format="%.2f",
                    key="f5_disp_pct",
                )
            with p4:
                loss_disp_red_pct = st.number_input(
                    "Disp. red (%)",
                    min_value=0.0,
                    value=loss_disp_red_default,
                    step=0.1,
                    format="%.2f",
                    key="f5_loss_disp_red_pct",
                )
            with p5:
                elec_pct = st.number_input(
                    "Eléctricas (%)",
                    min_value=0.0,
                    value=elec_default,
                    step=0.1,
                    format="%.2f",
                    key="f5_elec_pct",
                )
            with p6:
                otras_pct = st.number_input(
                    "Otras (%)",
                    min_value=0.0,
                    value=otras_default,
                    step=0.1,
                    format="%.2f",
                    key="f5_otras_pct",
                )

            with st.expander("Pérdidas avanzadas", expanded=False):
                ea1, ea2, ea3 = st.columns(3)
                with ea1:
                    loss_hielo_pct = st.number_input(
                        "Hielo / Soiling (%)",
                        min_value=0.0,
                        value=loss_hielo_default,
                        step=0.1,
                        format="%.2f",
                        key="f5_loss_hielo_pct",
                    )
                with ea2:
                    loss_histeresis_pct = st.number_input(
                        "Histéresis (%)",
                        min_value=0.0,
                        value=loss_histeresis_default,
                        step=0.1,
                        format="%.2f",
                        key="f5_loss_histeresis_pct",
                    )
                with ea3:
                    loss_curtailment_pct = st.number_input(
                        "Curtailment (%)",
                        min_value=0.0,
                        value=loss_curtailment_default,
                        step=0.1,
                        format="%.2f",
                        key="f5_loss_curtailment_pct",
                    )

            st.markdown(
                '<div class="f5-mini-note"><span class="f5-info-dot" style="width:1.2rem;height:1.2rem;font-size:0.72rem;">i</span>Las pérdidas se aplican de forma secuencial sobre el AEP bruto. Si todas las avanzadas están en 0, se usa el cálculo 3-bucket legacy.</div>',
                unsafe_allow_html=True,
            )

            st.form_submit_button("Actualizar pérdidas", use_container_width=True)

    # Marcador de posición para colocar el resumen del perfil en esta columna
    profile_summary_placeholder = st.container()

# Persist widget values to database
guardar_config_values({
    "f5_wake_mode": st.session_state.get("f5_wake_mode", wake_mode_default),
    "f5_wake_manual_pct": st.session_state.get("f5_wake_manual_pct", wake_manual_default),
    "f5_disp_pct": st.session_state.get("f5_disp_pct", disp_default),
    "f5_elec_pct": st.session_state.get("f5_elec_pct", elec_default),
    "f5_otras_pct": st.session_state.get("f5_otras_pct", otras_default),
    "f5_loss_disp_red_pct": st.session_state.get("f5_loss_disp_red_pct", loss_disp_red_default),
    "f5_loss_hielo_pct": st.session_state.get("f5_loss_hielo_pct", loss_hielo_default),
    "f5_loss_histeresis_pct": st.session_state.get("f5_loss_histeresis_pct", loss_histeresis_default),
    "f5_loss_curtailment_pct": st.session_state.get("f5_loss_curtailment_pct", loss_curtailment_default),
})

factor_densidad_efectivo = factor_densidad_calc if densidad_correccion_aplicada_default else 1.0
wake_model_lower = str(st.session_state.get("f5_wake_model", wake_model_default)).strip().lower()
altura_hub_ui = float(st.session_state.get("f5_altura_deseada", altura_deseada_default))

try:
    f5_energy_signature = (
        _df_signature(df_nasa, ["timestamp", "WS10M", "WS50M", "WD10M", "WD50M"]),
        _df_signature(df_curva_raw),
        _df_signature(df_layout),
        base_viento,
        modo_estadistico,
        metodo_detalle,
        float(altura_deseada),
        roughness_label,
        dir_altura,
        int(n_turbinas),
        float(diametro),
        float(ct),
        float(kw),
        wake_mode,
        float(wake_manual_pct),
        float(disp_pct),
        float(elec_pct),
        float(otras_pct),
        float(factor_densidad_efectivo),
        wake_model_lower,
        float(ambient_ti_default),
        float(altura_hub_ui),
        float(loss_disp_red_pct),
        float(loss_hielo_pct),
        float(loss_histeresis_pct),
        float(loss_curtailment_pct),
    )
    energy_result = _session_cached_result(
        "f5_energy_result",
        f5_energy_signature,
        lambda: energia_calc.calcular_aep_autoritativa(
            df_nasa=df_nasa,
            df_curva_raw=df_curva_raw,
            df_layout=df_layout,
            base_viento=base_viento,
            modo_estadistico=modo_estadistico,
            metodo_detalle=metodo_detalle,
            altura_deseada=altura_deseada,
            roughness_label=roughness_label,
            direccion_fuente=dir_altura,
            n_turbinas=n_turbinas,
            diametro=diametro,
            ct=ct,
            kw=kw,
            wake_mode=wake_mode,
            wake_manual_pct=wake_manual_pct,
            disp_pct=disp_pct,
            elec_pct=elec_pct,
            otras_pct=otras_pct,
            factor_densidad=factor_densidad_efectivo,
            wake_model=wake_model_lower,
            ambient_ti=ambient_ti_default,
            h_hub=altura_hub_ui,
            loss_disp_red_pct=loss_disp_red_pct,
            loss_hielo_pct=loss_hielo_pct,
            loss_histeresis_pct=loss_histeresis_pct,
            loss_curtailment_pct=loss_curtailment_pct,
        ),
    )
except Exception as e:
    st.error(f"No pude calcular la energía anual: {e}")
    st.stop()

meta = energy_result["meta"]
df_analisis = energy_result["df_analisis"]
resumen_rosa = energy_result["resumen_rosa"]
wake_losses_sector = energy_result["wake_losses_sector"]
resultados = energy_result["resultados"]
metodo_detalle = energy_result["metodo_detalle_resuelto"]
res = energy_result["resumen"]
df_aep_sector = energy_result["df_sector"]
tabla_perdidas = energy_result["tabla_perdidas"]

with profile_summary_placeholder:
    if meta["parametro_1_nombre"] or meta["parametro_2_nombre"]:
        cards_html = ""
        if meta["parametro_1_nombre"]:
            v = meta["parametro_1_valor"]
            cards_html += (
                '<div class="f5-profile-summary-kpi">'
                f'<span class="f5-profile-summary-kpi-icon">{_f5_icon_svg("settings", "#2563eb", 16)}</span>'
                f'<div><div class="f5-profile-summary-kpi-label">{meta["parametro_1_nombre"]}</div>'
                f'<div class="f5-profile-summary-kpi-value">{f"{v:.4f}" if pd.notna(v) else "N/A"}</div></div>'
                '</div>'
            )
        if meta["parametro_2_nombre"]:
            v = meta["parametro_2_valor"]
            cards_html += (
                '<div class="f5-profile-summary-kpi">'
                f'<span class="f5-profile-summary-kpi-icon">{_f5_icon_svg("settings", "#2563eb", 16)}</span>'
                f'<div><div class="f5-profile-summary-kpi-label">{meta["parametro_2_nombre"]}</div>'
                f'<div class="f5-profile-summary-kpi-value">{f"{v:.6f}" if pd.notna(v) else "N/A"}</div></div>'
                '</div>'
            )

        st.markdown(
            (
                '<div class="f5-profile-summary-box">'
                f'<div class="f5-profile-summary-alert"><span class="f5-profile-summary-info-icon">i</span><span>{meta["descripcion"]}</span></div>'
                f'<div class="f5-profile-summary-grid">{cards_html}</div>'
                '</div>'
            ),
            unsafe_allow_html=True,
        )
    else:
        _render_f5_info(meta["descripcion"])

if energy_result["wake_warning"]:
    st.warning(energy_result["wake_warning"])

# A6 - TI + IEC 61400-1
try:
    _serie_hub = df_analisis["WS_ANALISIS"] if df_analisis is not None and "WS_ANALISIS" in df_analisis.columns else None
    if _serie_hub is not None and len(_serie_hub) >= 30:
        with st.container(border=True, key="f5_card_ti_iec"):
            _render_f5_section_header(_f5_icon_svg("settings"), "Validación IEC 61400-1 + Turbulencia")

            ic1, ic2, ic3, ic4 = st.columns([1, 1, 1.4, 1.4])
            with ic1:
                _init_widget_state("f5_iec_clase_declarada", iec_clase_default)
                iec_clase_ui = st.selectbox(
                    "Clase velocidad declarada",
                    ["I", "II", "III", "S"],
                    index=["I", "II", "III", "S"].index(iec_clase_default) if iec_clase_default in ["I", "II", "III", "S"] else 1,
                    key="f5_iec_clase_declarada",
                )
            with ic2:
                _init_widget_state("f5_iec_turb_declarada", iec_turb_default)
                iec_turb_ui = st.selectbox(
                    "Categoría turbulencia",
                    ["A", "B", "C", "S"],
                    index=["A", "B", "C", "S"].index(iec_turb_default) if iec_turb_default in ["A", "B", "C", "S"] else 1,
                    key="f5_iec_turb_declarada",
                )

            _ti_res = calcular_ti_serie(_serie_hub)
            _ti_15 = _ti_res.get("ti_15ms", float("nan"))
            _v_mean = _ti_res.get("v_mean", float("nan"))
            _iec_res = clasificar_iec_61400_1(_v_mean, _ti_15, iec_clase_ui, iec_turb_ui)

            with ic3:
                _ti_str = f"{_ti_15:.3f}" if _ti_15 == _ti_15 and _ti_15 is not None else "N/D"
                _v_str = f"{_v_mean:.2f} m/s" if _v_mean == _v_mean else "N/D"
                st.markdown(
                    f'<div class="f5-mini-note">'
                    f'TI(15 m/s) calc.: <b>{_ti_str}</b><br>'
                    f'v media sitio: <b>{_v_str}</b><br>'
                    f'TI límite clase {iec_turb_ui}: <b>{_iec_res["ti_clase"]:.2f}</b><br>'
                    f'v_avg límite clase {iec_clase_ui}: <b>{_iec_res["v_avg_clase"]}</b> m/s'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with ic4:
                _cumple = _iec_res.get("cumple")
                if _cumple is True:
                    _badge_color = "#16a34a"
                    _badge_txt = "Sitio CUMPLE con la clase declarada"
                elif _cumple is False:
                    _badge_color = "#dc2626"
                    _badge_txt = "Sitio EXCEDE clase declarada — revisar turbina"
                else:
                    _badge_color = "#6b7280"
                    _badge_txt = "Datos insuficientes para validación completa"
                st.markdown(
                    f'<div style="padding:0.7rem; border-radius:8px; background:{_badge_color}1a; '
                    f'border:1px solid {_badge_color}; color:{_badge_color}; font-weight:600;">'
                    f'{_badge_txt}</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div class="f5-mini-note" style="margin-top:-0.3rem;margin-bottom:0.7rem;font-size:0.78rem;color:#000000;font-weight:400;">'
                'Nota: TI se calcula desde la serie WS_ANALISIS (proxy a altura hub). '
                'Método conservador, no reemplaza medición in-situ con torre meteorológica.'
                '</div>',
                unsafe_allow_html=True,
            )

            guardar_config_values({
                "f5_iec_clase_declarada": iec_clase_ui,
                "f5_iec_turb_declarada": iec_turb_ui,
                "f5_ti_15ms_calc": _ti_15 if _ti_15 == _ti_15 else "",
                "f5_iec_cumple": "" if _cumple is None else ("True" if _cumple else "False"),
            })
except Exception as _exc:
    pass

guardar_config_values({
    "f5_aep_bruta_total_mwh": res["aep_bruta_total"],
    "f5_aep_con_estela_total_mwh": res["base_sens"],
    "f5_perdida_estela_total_mwh": res["perdida_estela_mwh"],
    "f5_aep_neta_total_mwh": res["aep_neta_total"],
    "f5_factor_planta_bruto_pct": res["factor_planta_bruto"],
    "f5_factor_planta_neto_pct": res["factor_planta_neto"],
})

with st.container(border=True, key="f5_card_results"):
    st.markdown(
        (
            '<div class="f5-main-results-card">'
            '<div class="f5-main-results-header">'
            f'<span class="f5-main-results-icon">{_f5_icon_svg("chart", "#2563eb", 18)}</span>'
            '<span class="f5-main-results-title">Resultados principales</span>'
            '</div>'
            '<div class="f5-main-results-spacer"></div>'
            '<div class="f5-main-results-grid">'
        ),
        unsafe_allow_html=True,
    )
    st.markdown('<div class="f5-main-results-first-row">', unsafe_allow_html=True)
    r1, r2, r3, r4 = st.columns(4, gap="large")
    with r1:
        _render_f5_main_result_card(
            _f5_icon_svg("energy", "#2563eb", 35),
            "blue",
            "AEP bruta parque",
            f"({metodo_detalle})",
            f"{res['aep_bruta_total']:.1f}",
            "MWh/año",
        )
    with r2:
        _render_f5_main_result_card(
            _f5_icon_svg("energy", "#16a34a", 35),
            "green",
            "AEP neta parque",
            f"({metodo_detalle})",
            f"{res['aep_neta_total']:.1f}",
            "MWh/año",
        )
    with r3:
        _render_f5_main_result_card(
            _f5_icon_svg("gauge", "#7e22ce", 35),
            "purple",
            "Factor de planta bruto",
            f"({metodo_detalle})",
            f"{res['factor_planta_bruto']:.2f}",
            "%",
        )
    with r4:
        _render_f5_main_result_card(
            _f5_icon_svg("gauge", "#16a34a", 35),
            "green",
            "Factor de planta neto",
            f"({metodo_detalle})",
            f"{res['factor_planta_neto']:.2f}",
            "%",
        )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="f5-main-results-row-gap"></div>', unsafe_allow_html=True)
    r5, r6, r7, r8 = st.columns(4, gap="large")
    with r5:
        _render_f5_main_result_card(
            _f5_icon_svg("turbine", "#1d4ed8", 35),
            "blue",
            "AEP bruta por turbina",
            f"({metodo_detalle})",
            f"{res['aep_bruta_turbina']:.1f}",
            "MWh/año",
        )
    with r6:
        _render_f5_main_result_card(
            _f5_icon_svg("turbine", "#16a34a", 35),
            "green",
            "AEP neta por turbina",
            f"({metodo_detalle})",
            f"{res['aep_neta_turbina']:.1f}",
            "MWh/año",
        )
    with r7:
        _render_f5_main_result_card(
            _f5_icon_svg("power-module", "#d97706", 35),
            "amber",
            "Potencia nominal por turbina",
            "",
            f"{res['potencia_nominal_turbina_w']/1000:.0f}",
            "kW",
        )
    with r8:
        _render_f5_main_result_card(
            _f5_icon_svg("group", "#2563eb", 35),
            "blue",
            "Número de turbinas",
            "",
            f"{n_turbinas}",
            "unidades",
        )
    st.markdown("</div></div>", unsafe_allow_html=True)

if modo_estadistico == "Comparar Weibull y Rayleigh":
    with st.container(border=True, key="f5_card_compare"):
        _render_f5_section_header(_f5_icon_svg("chart"), "Comparación Weibull vs Rayleigh")

        comp_df = construir_tabla_comparativa(
            resultados["Weibull"]["resumen"],
            resultados["Rayleigh"]["resumen"],
        )
        st.dataframe(
            comp_df.style.format({"Weibull": "{:.2f}", "Rayleigh": "{:.2f}"}),
            use_container_width=True,
        )

        fig_comp = crear_figura_comparacion_metodos(
            resultados["Weibull"]["resumen"],
            resultados["Rayleigh"]["resumen"],
        )
        fig_comp.update_layout(height=420, margin=dict(l=30, r=20, t=42, b=34), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")
        st.plotly_chart(fig_comp, use_container_width=True, key="f5_comp_chart", config=PLOTLY_PERF_CONFIG)

        comp_sector_df = construir_tabla_sectorial_comparada(
            resultados["Weibull"]["df_sector"],
            resultados["Rayleigh"]["df_sector"],
        )
        st.dataframe(
            comp_sector_df.style.format({
                "AEP bruta Weibull (MWh/año)": "{:.2f}",
                "AEP neta Weibull (MWh/año)": "{:.2f}",
                "AEP bruta Rayleigh (MWh/año)": "{:.2f}",
                "AEP neta Rayleigh (MWh/año)": "{:.2f}",
            }),
            use_container_width=True,
        )
else:
    comp_df = None
    comp_sector_df = None

_total_loss_pct = (1.0 - res["aep_neta_total"] / res["aep_bruta_total"]) * 100.0 if res["aep_bruta_total"] > 0 else 0.0

fig_resumen = crear_figura_bruto_neto(
    aep_bruta=res["aep_bruta_total"],
    perdida_estela=res["perdida_estela_mwh"],
    perdida_disp=res["perdida_disp_mwh"],
    perdida_elec=res["perdida_elec_mwh"],
    perdida_otras=res["perdida_otras_mwh"],
    aep_neta=res["aep_neta_total"],
    titulo=f"Cascada de pérdidas ({metodo_detalle})",
)
fig_resumen.update_layout(height=332, margin=dict(l=14, r=14, t=42, b=16), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff")

fig_dona = crear_figura_dona_perdidas(
    perdida_estela=res["perdida_estela_mwh"],
    perdida_disp=res["perdida_disp_mwh"],
    perdida_elec=res["perdida_elec_mwh"],
    perdida_otras=res["perdida_otras_mwh"],
    titulo=f"Distribución de pérdidas ({metodo_detalle})",
    total_loss_pct=_total_loss_pct,
)
fig_dona.update_layout(height=332, margin=dict(l=10, r=108, t=42, b=12), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff", legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=11)))

# ---- Build HTML table for losses matching reference design ----
def _build_loss_table_html(tp_df):
    """Build a styled HTML table for the losses breakdown matching the reference."""
    rows_html = ""
    for _, row in tp_df.iterrows():
        concepto = row["Concepto"]
        pct = row["Pérdida (%)"]
        energia = row["Energía perdida (MWh/año)"]
        is_total = concepto == "Total"
        row_class = ' class="f5-loss-total-row"' if is_total else ""
        rows_html += (
            f'<tr{row_class}>'
            f'<td>{concepto}</td>'
            f'<td style="text-align:right">{pct:,.2f}%</td>'
            f'<td style="text-align:right">{energia:,.1f}</td>'
            f'</tr>'
        )
    return (
        '<div class="f5-loss-table-wrap">'
        '<table class="f5-loss-table-ref">'
        '<thead><tr>'
        '<th>Concepto</th>'
        '<th style="text-align:right">Pérdida (%)</th>'
        '<th style="text-align:right">Energía perdida<br>(MWh/año)</th>'
        '</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table>'
        '</div>'
    )

with st.container(border=True, key="f5_card_breakdown"):
    _render_f5_section_header_card(_f5_icon_svg("pie-chart-detached", "#2563eb", 20), "Desglose de pérdidas")
    loss_table_col, loss_waterfall_col, loss_donut_col = st.columns([0.95, 1.75, 1.25], gap="medium")
    with loss_table_col:
        st.markdown(_build_loss_table_html(tabla_perdidas), unsafe_allow_html=True)
    with loss_waterfall_col:
        st.plotly_chart(fig_resumen, use_container_width=True, key="f5_loss_waterfall_chart", config=PLOTLY_PERF_CONFIG)
    with loss_donut_col:
        st.plotly_chart(fig_dona, use_container_width=True, key="f5_loss_donut_chart", config=PLOTLY_PERF_CONFIG)


container_height = int(min(740, max(660, len(df_aep_sector) * 32 + 130)))
fig_sectorial = crear_figura_sectorial(df_aep_sector, titulo=f"AEP por sector ({metodo_detalle})")
fig_sectorial.update_layout(
    height=container_height - 28,
    margin=dict(l=60, r=30, t=70, b=60),
    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",
    bargap=0.18,
    legend=dict(orientation="h", x=1.0, y=1.08, xanchor="right", font=dict(size=11, family="Inter, sans-serif", color="#334155")),
    xaxis=dict(showgrid=False, title=dict(text="Sector", font=dict(size=11, color="#475569"))),
    yaxis=dict(
        gridcolor="rgba(148,163,184,0.24)",
        zeroline=False,
        title=dict(text="AEP parque (MWh/año)", font=dict(size=11, color="#475569")),
        tickfont=dict(size=10, color="#64748b"),
    ),
    title=dict(
        text=f"AEP por sector ({metodo_detalle})",
        font=dict(size=15, color="#0f2f6e", family="Inter, sans-serif"),
        x=0.5,
        xanchor="center",
        y=0.99,
        yanchor="top",
    ),
)
if len(fig_sectorial.data) >= 2:
    fig_sectorial.data[0].marker.color = "#2563eb"
    fig_sectorial.data[1].marker.color = "#22c55e"
    fig_sectorial.data[0].marker.line = dict(color="#1d4ed8", width=0.6)
    fig_sectorial.data[1].marker.line = dict(color="#16a34a", width=0.6)
    fig_sectorial.data[0].name = "Bruta"
    fig_sectorial.data[1].name = "Neta"

# ---- Build HTML sector table matching reference ----
def _build_sector_table_html(df_sector):
    """Build a styled HTML table for the sector results matching the reference."""
    col_defs = [
        ("Sector", "Sector", "text", None),
        ("Frecuencia (%)", "Frecuencia<br>(%)", "num1", None),
        ("Horas equivalentes anuales (h/año)", "Horas eq.<br>(h)", "num0", None),
        ("Potencia media por turbina (W)", "Pot. media<br>/turb (W)", "num0", None),
        ("AEP bruta por turbina (MWh/año)", "AEP bruta<br>/turb (MWh)", "num1", None),
        ("AEP bruta parque (MWh/año)", "AEP bruta<br>parque", "num1", None),
        ("Pérdida estela sector (%)", "Pérd. estela<br>(%)", "num1", None),
        ("AEP con estela (MWh/año)", "AEP c/estela<br>(MWh)", "num1", None),
        ("Pérdida estela energética (MWh/año)", "Pérd. estela<br>energ. (MWh)", "num1", None),
        ("AEP neta sector (MWh/año)", "AEP neta<br>(MWh)", "num1", None),
    ]

    def _fmt(val, fmt_type):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return str(val)
        if fmt_type == "num0":
            return f"{v:,.0f}"
        elif fmt_type == "num1":
            return f"{v:,.1f}"
        return str(val)

    # Header
    header_cells = "".join(f'<th>{cd[1]}</th>' for cd in col_defs)
    header_html = f"<thead><tr>{header_cells}</tr></thead>"

    # Body rows
    body_rows = ""
    for _, row in df_sector.iterrows():
        cells = ""
        for col_key, _, fmt_type, _ in col_defs:
            val = row.get(col_key, "")
            cells += f"<td>{_fmt(val, fmt_type)}</td>"
        body_rows += f"<tr>{cells}</tr>"

    # Total / Promedio row
    n_sectors = len(df_sector)
    if n_sectors > 0:
        freq_total = df_sector["Frecuencia (%)"].sum()
        horas_total = df_sector["Horas equivalentes anuales (h/año)"].sum()
        pot_media_avg = df_sector["Potencia media por turbina (W)"].mean()
        bruta_turb_sum = df_sector["AEP bruta por turbina (MWh/año)"].sum()
        bruta_parque_sum = df_sector["AEP bruta parque (MWh/año)"].sum()
        wake_pct_avg = df_sector["Pérdida estela sector (%)"].mean()
        con_estela_sum = df_sector["AEP con estela (MWh/año)"].sum()
        perdida_energ_sum = df_sector["Pérdida estela energética (MWh/año)"].sum()
        neta_sum = df_sector["AEP neta sector (MWh/año)"].sum()
        total_cells = (
            f'<td>Total /<br>Promedio</td>'
            f'<td>{freq_total:,.1f}</td>'
            f'<td>{horas_total:,.0f}</td>'
            f'<td>{pot_media_avg:,.0f}</td>'
            f'<td>{bruta_turb_sum:,.1f}</td>'
            f'<td>{bruta_parque_sum:,.1f}</td>'
            f'<td>{wake_pct_avg:,.2f}</td>'
            f'<td>{con_estela_sum:,.1f}</td>'
            f'<td>{perdida_energ_sum:,.1f}</td>'
            f'<td>{neta_sum:,.1f}</td>'
        )
        body_rows += f'<tr class="f5-sector-total-row">{total_cells}</tr>'

    return (
        '<div class="f5-sector-table-wrap">'
        '<table class="f5-sector-table-ref">'
        f'{header_html}'
        f'<tbody>{body_rows}</tbody>'
        '</table>'
        '</div>'
    )

with st.container(border=True, key="f5_card_sector"):
    _render_f5_section_header_card(_f5_icon_svg("sector", "#2563eb", 20), "Resultados por sector")
    st.markdown(
        f"""
        <style>
            .f5-sector-table-ref {{ white-space: normal !important; }}
            .st-key-f5_card_sector > div[data-testid="stVerticalBlockBorderWrapper"] {{
                padding-bottom: 2.2rem !important;
            }}
            .st-key-f5_card_sector [data-testid="stHorizontalBlock"] {{
                align-items: stretch !important;
                margin-top: -8px !important;
            }}
            /* Outer card parity: both table and chart real containers */
            .st-key-f5_sector_table_card,
            .st-key-f5_sector_chart_card {{
                border-radius: 26px !important;
                background: #ffffff !important;
                border: 1px solid #bcd7ff !important;
                box-shadow: 0 10px 28px rgba(15, 60, 120, 0.06) !important;
                padding: 0.4rem !important;
                height: {container_height}px !important;
                min-height: {container_height}px !important;
                max-height: {container_height}px !important;
                overflow: hidden !important;
                box-sizing: border-box !important;
            }}
            .st-key-f5_sector_table_card > div[data-testid="stVerticalBlockBorderWrapper"],
            .st-key-f5_sector_chart_card > div[data-testid="stVerticalBlockBorderWrapper"] {{
                padding: 0 !important;
                height: 100% !important;
            }}

            /* Inner table wrapper: keep scroll inside, do not clip the outer border */
            .f5-sector-table-inner {{
                height: 100%;
                display: flex;
                flex-direction: column;
            }}
            .f5-sector-table-inner .f5-sector-table-wrap {{
                flex: 1 1 auto;
                min-height: 0;
                overflow: auto;
                border-radius: 20px;
                border: 1px solid #d9e8fb !important;
                margin: 0 !important;
                background: #ffffff;
            }}
            .f5-sector-table-inner .f5-sector-table-wrap table {{ width:100%; border-collapse:collapse; }}

            /* Make the visible blue bottom line part of the outer card so it's never clipped */
            .st-key-f5_sector_table_card {{
                /* Removed blue line */
            }}
            .st-key-f5_sector_chart_card {{
                /* Removed blue line */
            }}

            /* Chart: force full-height canvas inside the card */
            .st-key-f5_sector_chart_card [data-testid="stPlotlyChart"] {{
                height: 100% !important;
                width: 100% !important;
                border-radius: 22px !important;
                border: none !important;
                padding: 0 !important;
                background: transparent !important;
            }}
            .st-key-f5_sector_chart_card > div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stPlotlyChart"] > div {{
                height: 100% !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    sector_table_col, sector_chart_col = st.columns([1.0, 1.0], gap="small")

    with sector_table_col:
        table_html = _build_sector_table_html(df_aep_sector)
        with st.container(border=True, key="f5_sector_table_card"):
            st.markdown(
                f'<div class="f5-sector-table-inner">{table_html}</div>',
                unsafe_allow_html=True,
            )

    with sector_chart_col:
        with st.container(border=True, key="f5_sector_chart_card"):
            st.plotly_chart(fig_sectorial, use_container_width=True, key="f5_sector_chart_col", config=PLOTLY_PERF_CONFIG)

    st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)

fig_wind_rose_export = None
if len(resumen_rosa) > 0:
    try:
        fig_wind_rose_export = crear_rosa_vientos_16(resumen_rosa)
        fig_wind_rose_export.update_layout(title="Rosa de vientos reconstruida desde Fase 5")
    except Exception:
        fig_wind_rose_export = None

fig_layout_export = None
if len(df_layout) > 0:
    try:
        fig_layout_export = crear_figura_layout_parque(
            df_layout=df_layout,
            diametro=diametro,
            titulo="Layout actual del parque",
        )
    except Exception:
        fig_layout_export = None


with st.container(border=True, key="f5_card_econ_master"):
    _render_f5_section_header_card(
        _f5_icon_svg("money", "#2563eb", 20),
        "Evaluación económica: CAPEX, OPEX y LCOE",
        "La evaluación económica usa como base el AEP neto del parque calculado en esta misma Fase 5.",
    )

    metricas_base_economicas = calcular_metricas_base_economicas(
        potencia_nominal_turbina_w=res["potencia_nominal_turbina_w"],
        n_turbinas=n_turbinas,
        aep_neta_mwh_anio=res["aep_neta_total"],
        factor_planta_neto_pct=res["factor_planta_neto"],
    )
    for warning_text in metricas_base_economicas["warnings"]:
        st.warning(warning_text)

    _pot_nom_mw = metricas_base_economicas["potencia_nominal_turbina_mw"]
    _pot_inst_mw = metricas_base_economicas["potencia_instalada_mw"]
    _aep_neta = metricas_base_economicas["aep_neta_mwh_anio"]
    _fp = metricas_base_economicas["factor_planta_neto_pct"]
    _n_turb = metricas_base_economicas["n_turbinas"]

    econ_top_left, econ_top_right = st.columns([1.03, 1.12], gap="medium")
    with econ_top_left:
        with st.container(border=True, key="f5_card_econ_base"):
            st.markdown(
            '<div class="f5-econ-top-card">'
            f'<div class="f5-econ-top-title"><span class="f5-econ-top-title-icon">{_f5_icon_svg("settings","#2563eb",15)}</span> Datos base automáticos</div>'
            '<div class="f5-econ-mini-kpis">'
            + _econ_mini_kpi(_f5_icon_svg("turbine","#2563eb",22), "Potencia nominal<br>por turbina", f"{_pot_nom_mw*1000:,.0f} kW")
            + _econ_mini_kpi(_f5_icon_svg("group","#2563eb",22), "Número de<br>turbinas", f"{_n_turb}", "unidades")
            + _econ_mini_kpi(_f5_icon_svg("power-module","#16a34a",22), "Potencia<br>instalada", f"{_pot_inst_mw*1000:,.0f} kW", f"({_pot_inst_mw:,.2f} MW)")
            + _econ_mini_kpi(_f5_icon_svg("energy","#7e22ce",22), "AEP neta", f"{_aep_neta:,.1f}", "MWh/año")
            + _econ_mini_kpi(_f5_icon_svg("gauge","#16a34a",22), "Factor de planta<br>neto", f"{_fp:.2f}%")
            + '</div></div>',
            unsafe_allow_html=True,
        )

    with econ_top_right:
        with st.container(border=True, key="f5_card_econ_currency"):
            st.markdown(
                f'<div class="f5-econ-top-title"><span class="f5-econ-top-title-icon">{_f5_icon_svg("money","#2563eb",18)}</span> Moneda y conversión</div>',
                unsafe_allow_html=True,
            )
            mc1, mc2, mc3, mc4 = st.columns([0.95, 0.95, 1.25, 1.45], gap="small")
            with mc1:
                moneda_base = st.selectbox("Moneda base del modelo", options=MONEDA_OPTIONS, index=MONEDA_OPTIONS.index(moneda_base_default) if moneda_base_default in MONEDA_OPTIONS else 0)
            with mc2:
                moneda_visualizacion = st.selectbox("Moneda de visualización", options=MONEDA_OPTIONS, index=MONEDA_OPTIONS.index(moneda_visualizacion_default) if moneda_visualizacion_default in MONEDA_OPTIONS else 0)
            with mc3:
                fx_mode_options = list(FX_MODE_OPTIONS.keys())
                fx_mode = st.selectbox("Modo de conversión", options=fx_mode_options, index=fx_mode_options.index(fx_mode_default) if fx_mode_default in fx_mode_options else 0, format_func=lambda key: FX_MODE_OPTIONS[key])

            fx_rate_cop_per_usd = fx_rate_default
            fx_timestamp = fx_timestamp_default
            fx_source = fx_source_default
            fx_warning = ""
            update_fx = False
            if fx_mode == "manual":
                with mc4:
                    fx_rate_cop_per_usd = st.number_input("Tasa COP por USD", min_value=0.0, value=fx_rate_default, step=1.0, format="%.4f")
                fx_timestamp = fx_timestamp_default or "manual"
                fx_source = "manual"
            else:
                with mc4:
                    update_fx = st.button("Actualizar tasa\nautomática", icon=":material/sync:", use_container_width=True, key="f5_fx_update")
                should_fetch_fx = update_fx or (not fx_timestamp_default and moneda_base != moneda_visualizacion)
                if should_fetch_fx:
                    fx_result = obtener_tasa_cop_usd_online()
                    if fx_result["success"]:
                        fx_rate_cop_per_usd = float(fx_result["fx_cop_per_usd"])
                        fx_timestamp = str(fx_result["timestamp"] or "")
                        fx_source = str(fx_result["source"] or "automatic")
                    elif fx_rate_default > 0:
                        fx_rate_cop_per_usd = fx_rate_default
                        fx_timestamp = fx_timestamp_default
                        fx_source = fx_source_default or "cached"
                        fx_warning = f"{fx_result['message']} Se reutilizó la última tasa guardada."
                    else:
                        fx_warning = f"{fx_result['message']} Cambie a modo manual para ingresar una tasa."
                else:
                    fx_rate_cop_per_usd = fx_rate_default
                    fx_timestamp = fx_timestamp_default
                    fx_source = fx_source_default or "cached"
            if fx_warning:
                st.warning(fx_warning)

            _fx_disp = f"1 {moneda_base} = {fx_rate_cop_per_usd:,.4f} {moneda_visualizacion}" if moneda_base != moneda_visualizacion else f"1 {moneda_base} = 1.0000 {moneda_visualizacion}"
            st.markdown(f'<div class="f5-econ-fx-strip"><span>Tasa de cambio usada: &nbsp;<b>{_fx_disp}</b></span><span style="margin-left:auto;">Fuente: {fx_source or "N/D"}</span><span>Fecha: &nbsp;{fx_timestamp or "N/D"}</span></div>', unsafe_allow_html=True)

    econ_col_capex, econ_col_opex, econ_col_lcoe = st.columns(3, gap="medium")

    with econ_col_capex:
        with st.container(border=True, key="f5_econ_capex_card"):
            st.markdown(f'<div class="f5-econ-col-title"><span class="f5-econ-col-title-icon blue">{_f5_icon_svg("money","#2563eb",20)}</span> CAPEX</div>', unsafe_allow_html=True)
            capex_mode_options = list(CAPEX_MODE_OPTIONS.keys())
            capex_mode = st.selectbox("Modo de CAPEX", options=capex_mode_options, index=capex_mode_options.index(capex_mode_default) if capex_mode_default in capex_mode_options else capex_mode_options.index("semi_auto_mw"), format_func=lambda key: CAPEX_MODE_OPTIONS[key])
            capex_componentes = dict(capex_componentes_default)
            if capex_mode == "manual_total":
                capex_total_manual = st.number_input(f"CAPEX total ({moneda_base})", min_value=0.0, value=capex_total_default, step=1000.0, format="%.2f")
                capex_result = calcular_capex(mode=capex_mode, potencia_instalada_mw=metricas_base_economicas["potencia_instalada_mw"], inputs={"capex_total": capex_total_manual})
            elif capex_mode == "detailed":
                for ck in list(CAPEX_COMPONENT_DEFAULTS.keys()):
                    capex_componentes[ck] = st.number_input(ck.replace("_"," ").capitalize(), min_value=0.0, value=float(capex_componentes_default.get(ck, 0.0)), step=1000.0, format="%.2f", key=f"f5_{ck}")
                capex_result = calcular_capex(mode=capex_mode, potencia_instalada_mw=metricas_base_economicas["potencia_instalada_mw"], components=capex_componentes)
            else:
                _cx1, _cx2 = st.columns(2)
                with _cx1:
                    capex_turbina_por_mw = st.number_input(f"Costo turbina por MW ({moneda_base})", min_value=0.0, value=capex_turbina_por_mw_default, step=1000.0, format="%.0f")
                    capex_bop_por_mw = st.number_input(f"Costo BOP por MW ({moneda_base})", min_value=0.0, value=capex_bop_por_mw_default, step=1000.0, format="%.0f")
                    capex_pct_desarrollo = st.number_input("Porcentaje desarrollo (%)", min_value=0.0, value=capex_pct_desarrollo_default, step=0.1, format="%.2f")
                with _cx2:
                    capex_red_por_mw = st.number_input(f"Costo mat. por MW ({moneda_base})", min_value=0.0, value=capex_red_por_mw_default, step=1000.0, format="%.0f")
                    capex_pct_contingencia = st.number_input("Porcentaje contingencia (%)", min_value=0.0, value=capex_pct_contingencia_default, step=0.1, format="%.2f")
                capex_result = calcular_capex(mode="semi_auto_mw", potencia_instalada_mw=metricas_base_economicas["potencia_instalada_mw"], inputs={"costo_turbina_por_mw": capex_turbina_por_mw, "costo_bop_por_mw": capex_bop_por_mw, "costo_red_por_mw": capex_red_por_mw, "porcentaje_desarrollo": capex_pct_desarrollo, "porcentaje_contingencia": capex_pct_contingencia})
            st.markdown(_build_econ_breakdown_html(capex_result["breakdown"], "Componentes de CAPEX", ["Concepto", f"{moneda_base}/MW", f"{moneda_base} Total"], moneda_base, potencia_mw=metricas_base_economicas["potencia_instalada_mw"]), unsafe_allow_html=True)

    with econ_col_opex:
        with st.container(border=True, key="f5_econ_opex_card"):
            st.markdown(f'<div class="f5-econ-col-title"><span class="f5-econ-col-title-icon green">{_f5_icon_svg("money","#16a34a",20)}</span> OPEX</div>', unsafe_allow_html=True)
            opex_mode_options = list(OPEX_MODE_OPTIONS.keys())
            opex_mode = st.selectbox("Modo de OPEX", options=opex_mode_options, index=opex_mode_options.index(opex_mode_default) if opex_mode_default in opex_mode_options else opex_mode_options.index("fixed_variable"), format_func=lambda key: OPEX_MODE_OPTIONS[key])
            opex_componentes = dict(opex_componentes_default)
            if opex_mode == "manual_total":
                opex_total_manual = st.number_input(f"OPEX anual total ({moneda_base})", min_value=0.0, value=opex_total_anual_default, step=100.0, format="%.2f")
                opex_result = calcular_opex(mode=opex_mode, potencia_instalada_mw=metricas_base_economicas["potencia_instalada_mw"], energia_mwh_anio=metricas_base_economicas["aep_neta_mwh_anio"], inputs={"opex_total_anual": opex_total_manual})
            elif opex_mode == "detailed":
                for ck in list(OPEX_COMPONENT_DEFAULTS.keys()):
                    opex_componentes[ck] = st.number_input(ck.replace("_"," ").capitalize(), min_value=0.0, value=float(opex_componentes_default.get(ck, 0.0)), step=100.0, format="%.2f", key=f"f5_{ck}")
                opex_result = calcular_opex(mode=opex_mode, potencia_instalada_mw=metricas_base_economicas["potencia_instalada_mw"], energia_mwh_anio=metricas_base_economicas["aep_neta_mwh_anio"], components=opex_componentes)
            else:
                _ox1, _ox2 = st.columns(2)
                with _ox1:
                    opex_fijo_por_mw_anio = st.number_input(f"OPEX fijo por MW/año ({moneda_base})", min_value=0.0, value=opex_fijo_por_mw_anio_default, step=100.0, format="%.0f")
                    administracion_anual = st.number_input(f"Administración anual ({moneda_base})", min_value=0.0, value=admin_anual_default, step=100.0, format="%.0f")
                    opex_variable_por_mwh = st.number_input(f"OPEX variable por MWh ({moneda_base})", min_value=0.0, value=opex_variable_default, step=0.1, format="%.2f")
                with _ox2:
                    seguros_anuales = st.number_input(f"Seguros anuales ({moneda_base})", min_value=0.0, value=seguros_anuales_default, step=100.0, format="%.0f")
                    terreno_anual = st.number_input(f"Terreno anual ({moneda_base})", min_value=0.0, value=terreno_anual_default, step=100.0, format="%.0f")
                opex_result = calcular_opex(mode="fixed_variable", potencia_instalada_mw=metricas_base_economicas["potencia_instalada_mw"], energia_mwh_anio=metricas_base_economicas["aep_neta_mwh_anio"], inputs={"opex_fijo_por_mw_anio": opex_fijo_por_mw_anio, "opex_variable_por_mwh": opex_variable_por_mwh, "seguros_anuales": seguros_anuales, "terreno_anual": terreno_anual, "administracion_anual": administracion_anual})
            st.markdown(_build_opex_breakdown_html(opex_result["breakdown"], "Distribución de OPEX anual", moneda_base, potencia_mw=metricas_base_economicas["potencia_instalada_mw"]), unsafe_allow_html=True)

    with econ_col_lcoe:
        with st.container(border=True, key="f5_econ_lcoe_card"):
            st.markdown(f'<div class="f5-econ-col-title"><span class="f5-econ-col-title-icon purple">{_f5_icon_svg("chart","#7e22ce",18)}</span> LCOE</div>', unsafe_allow_html=True)
            _lc1, _lc2 = st.columns(2)
            with _lc1:
                vida_util_anios = st.number_input("Vida útil (años)", min_value=1, value=vida_util_default, step=1)
                degradacion_energia_pct = st.number_input("Degradación (%/año)", min_value=0.0, value=degradacion_default, step=0.1, format="%.2f")
            with _lc2:
                tasa_descuento_pct = st.number_input("Tasa de descuento (%)", min_value=0.0, value=tasa_descuento_default, step=0.1, format="%.2f")
                valor_residual = st.number_input(f"Valor residual ({moneda_base})", min_value=0.0, value=valor_residual_default, step=100.0, format="%.2f")

            _lc3, _lc4 = st.columns(2)
            with _lc3:
                precio_energia_mwh = st.number_input(
                    f"Precio venta energía ({moneda_base}/MWh)",
                    min_value=0.0,
                    value=precio_energia_default,
                    step=1.0,
                    format="%.2f",
                    key="f5_precio_energia_mwh",
                    help="Precio de venta supuesto plano. Necesario para NPV/IRR/Payback.",
                )
            with _lc4:
                sens_delta_pct = st.number_input(
                    "Δ sensibilidad (±%)",
                    min_value=1.0,
                    max_value=50.0,
                    value=sens_delta_default,
                    step=1.0,
                    format="%.1f",
                    key="f5_sens_delta_pct",
                    help="Variación aplicada a cada parámetro en el tornado LCOE.",
                )

            lcoe = calcular_lcoe_descontado(capex_total=capex_result["capex_total"], opex_fijo_anual=opex_result["opex_fijo_anual"], opex_variable_por_mwh=opex_result["opex_variable_por_mwh"], energia_base_mwh_anio=metricas_base_economicas["aep_neta_mwh_anio"], vida_util_anios=vida_util_anios, tasa_descuento_pct=tasa_descuento_pct, degradacion_energia_pct=degradacion_energia_pct, valor_residual=valor_residual)
            _lcoe_html = ('<div class="f5-econ-lcoe-pair">'
                + _econ_lcoe_kpi(_f5_icon_svg("money","#2563eb",14), "blue", f"Valor presente<br>de costos ({moneda_base})", f"{lcoe['valor_presente_costos']:,.0f}")
                + _econ_lcoe_kpi(_f5_icon_svg("energy","#16a34a",14), "green", "Valor presente<br>de energía (MWh)", f"{lcoe['valor_presente_energia']:,.0f}")
                + '</div><div class="f5-econ-lcoe-sep"></div><div class="f5-econ-lcoe-pair">'
                + _econ_lcoe_kpi(_f5_icon_svg("chart","#7e22ce",14), "purple", f"LCOE base<br>({moneda_base}/MWh)", f"{lcoe['lcoe_mwh']:,.2f}")
                + _econ_lcoe_kpi(_f5_icon_svg("chart","#7e22ce",14), "purple", f"LCOE base<br>({moneda_base}/kWh)", f"{lcoe['lcoe_kwh']:,.5f}")
                + '</div>')
            st.markdown(_lcoe_html, unsafe_allow_html=True)

            # A3 - NPV / IRR / Payback
            metricas_fin = calcular_metricas_financieras(
                capex_total=capex_result["capex_total"],
                opex_fijo_anual=opex_result["opex_fijo_anual"],
                opex_variable_por_mwh=opex_result["opex_variable_por_mwh"],
                energia_base_mwh_anio=metricas_base_economicas["aep_neta_mwh_anio"],
                vida_util_anios=vida_util_anios,
                tasa_descuento_pct=tasa_descuento_pct,
                degradacion_energia_pct=degradacion_energia_pct,
                valor_residual=valor_residual,
                precio_energia_mwh=precio_energia_mwh,
            )
            import math as _math
            _npv_val = metricas_fin["npv"]
            _irr_val = metricas_fin["irr_pct"]
            _pb_s = metricas_fin["payback_simple_anios"]
            _pb_d = metricas_fin["payback_descontado_anios"]
            _fmt_money = lambda v: f"{v:,.0f}" if _math.isfinite(v) else "N/D"
            _fmt_pct = lambda v: f"{v:,.2f}%" if _math.isfinite(v) else "N/D"
            _fmt_yr = lambda v: f"{v:,.2f}" if _math.isfinite(v) else "N/D"
            _fin_html = ('<div class="f5-econ-lcoe-sep"></div><div class="f5-econ-lcoe-pair">'
                + _econ_lcoe_kpi(_f5_icon_svg("money","#2563eb",14), "blue", f"NPV ({moneda_base})", _fmt_money(_npv_val))
                + _econ_lcoe_kpi(_f5_icon_svg("chart","#16a34a",14), "green", "IRR", _fmt_pct(_irr_val))
                + '</div><div class="f5-econ-lcoe-pair">'
                + _econ_lcoe_kpi(_f5_icon_svg("chart","#7e22ce",14), "purple", "Payback simple<br>(años)", _fmt_yr(_pb_s))
                + _econ_lcoe_kpi(_f5_icon_svg("chart","#7e22ce",14), "purple", "Payback descontado<br>(años)", _fmt_yr(_pb_d))
                + '</div>')
            st.markdown(_fin_html, unsafe_allow_html=True)
            # ── 4 cards de resultados mostrados (2×2) ──────────────────────────
            # Se calculan aquí con los valores ya disponibles en el scope
            _econ_display_preview = convertir_resumen_economico(
                summary={"capex_total": capex_result["capex_total"], "opex_total_anual": opex_result["opex_total_anual"], "vp_costos": lcoe["valor_presente_costos"], "lcoe_mwh": lcoe["lcoe_mwh"], "lcoe_kwh": lcoe["lcoe_kwh"]},
                moneda_base=moneda_base,
                moneda_display=moneda_visualizacion,
                fx_cop_per_usd=fx_rate_cop_per_usd,
            )
            st.markdown('<div class="f5-econ-mostrado-grid-inside-lcoe">'
                + _econ_mostrado_card(_f5_icon_svg("money","#2563eb",17), "blue", "CAPEX mostrado", format_currency_amount(_econ_display_preview["capex_total_display"], moneda_visualizacion))
                + _econ_mostrado_card(_f5_icon_svg("money","#16a34a",17), "green", "OPEX mostrado", format_currency_amount(_econ_display_preview["opex_total_anual_display"], moneda_visualizacion))
                + _econ_mostrado_card(_f5_icon_svg("chart","#7e22ce",17), "purple", "LCOE mostrado", format_lcoe_value(_econ_display_preview["lcoe_display_kwh"], moneda_visualizacion, "kWh"))
                + _econ_mostrado_card(_f5_icon_svg("chart","#7e22ce",17), "purple", "LCOE mostrado", format_lcoe_value(_econ_display_preview["lcoe_display_mwh"], moneda_visualizacion, "MWh"))
                + '</div>', unsafe_allow_html=True)

    economic_display = convertir_resumen_economico(summary={"capex_total": capex_result["capex_total"], "opex_total_anual": opex_result["opex_total_anual"], "vp_costos": lcoe["valor_presente_costos"], "lcoe_mwh": lcoe["lcoe_mwh"], "lcoe_kwh": lcoe["lcoe_kwh"]}, moneda_base=moneda_base, moneda_display=moneda_visualizacion, fx_cop_per_usd=fx_rate_cop_per_usd)

    guardar_config_values({
        "f5_capex_mode": capex_mode, "f5_capex_total": capex_result["capex_total"],
        "f5_capex_turbina_por_mw": capex_turbina_por_mw if capex_mode == "semi_auto_mw" else capex_turbina_por_mw_default,
        "f5_capex_bop_por_mw": capex_bop_por_mw if capex_mode == "semi_auto_mw" else capex_bop_por_mw_default,
        "f5_capex_red_por_mw": capex_red_por_mw if capex_mode == "semi_auto_mw" else capex_red_por_mw_default,
        "f5_capex_pct_desarrollo": capex_pct_desarrollo if capex_mode == "semi_auto_mw" else capex_pct_desarrollo_default,
        "f5_capex_pct_contingencia": capex_pct_contingencia if capex_mode == "semi_auto_mw" else capex_pct_contingencia_default,
        "f5_capex_componentes_json": dumps_component_values(capex_componentes),
        "f5_opex_mode": opex_mode, "f5_opex_total_anual": opex_result["opex_total_anual"],
        "f5_opex_fijo_anual": opex_result["opex_fijo_anual"],
        "f5_opex_fijo_por_mw_anio": opex_fijo_por_mw_anio if opex_mode == "fixed_variable" else opex_fijo_por_mw_anio_default,
        "f5_opex_variable_por_mwh": opex_result["opex_variable_por_mwh"],
        "f5_seguros_anuales": seguros_anuales if opex_mode == "fixed_variable" else seguros_anuales_default,
        "f5_terreno_anual": terreno_anual if opex_mode == "fixed_variable" else terreno_anual_default,
        "f5_admin_anual": administracion_anual if opex_mode == "fixed_variable" else admin_anual_default,
        "f5_opex_componentes_json": dumps_component_values(opex_componentes),
        "f5_vida_util_anios": vida_util_anios, "f5_tasa_descuento_pct": tasa_descuento_pct,
        "f5_degradacion_energia_pct": degradacion_energia_pct, "f5_valor_residual": valor_residual,
        "f5_moneda_base": moneda_base, "f5_moneda_visualizacion": moneda_visualizacion,
        "f5_fx_mode": fx_mode, "f5_fx_rate_cop_per_usd": fx_rate_cop_per_usd,
        "f5_fx_timestamp": fx_timestamp, "f5_fx_source": fx_source,
        "f5_unidad_monetaria": moneda_base,
        "f5_potencia_nominal_turbina_mw": metricas_base_economicas["potencia_nominal_turbina_mw"],
        "f5_potencia_instalada_mw": metricas_base_economicas["potencia_instalada_mw"],
        "f5_aep_neta_mwh_anio": metricas_base_economicas["aep_neta_mwh_anio"],
        "f5_vp_costos": lcoe["valor_presente_costos"], "f5_vp_energia": lcoe["valor_presente_energia"],
        "f5_capex_total_display": economic_display["capex_total_display"],
        "f5_opex_total_anual_display": economic_display["opex_total_anual_display"],
        "f5_vp_costos_display": economic_display["vp_costos_display"],
        "f5_lcoe_display_mwh": economic_display["lcoe_display_mwh"],
        "f5_lcoe_display_kwh": economic_display["lcoe_display_kwh"],
        "f5_lcoe_mwh": lcoe["lcoe_mwh"], "f5_lcoe_kwh": lcoe["lcoe_kwh"],
        "f5_precio_energia_mwh": precio_energia_mwh,
        "f5_npv": metricas_fin["npv"],
        "f5_irr_pct": metricas_fin["irr_pct"],
        "f5_payback_simple_anios": metricas_fin["payback_simple_anios"],
        "f5_payback_descontado_anios": metricas_fin["payback_descontado_anios"],
        "f5_sens_delta_pct": sens_delta_pct,
    })

    # A4 - Tornado sensibilidad LCOE
    with st.container(border=True, key="f5_card_sens_tornado"):
        st.markdown(
            f'<div class="f5-econ-col-title"><span class="f5-econ-col-title-icon purple">'
            f'{_f5_icon_svg("chart","#7e22ce",18)}</span> Sensibilidad LCOE (tornado ±{sens_delta_pct:.0f}%)</div>',
            unsafe_allow_html=True,
        )
        try:
            base_sens_kwargs = {
                "capex_total": capex_result["capex_total"],
                "opex_fijo_anual": opex_result["opex_fijo_anual"],
                "opex_variable_por_mwh": opex_result["opex_variable_por_mwh"],
                "energia_base_mwh_anio": metricas_base_economicas["aep_neta_mwh_anio"],
                "vida_util_anios": vida_util_anios,
                "tasa_descuento_pct": tasa_descuento_pct,
                "degradacion_energia_pct": degradacion_energia_pct,
                "valor_residual": valor_residual,
            }
            df_sens, lcoe_base_val = calcular_sensibilidad_lcoe(base_sens_kwargs, variables_pct=sens_delta_pct)
            import plotly.graph_objects as _go
            fig_torn = _go.Figure()
            fig_torn.add_trace(_go.Bar(
                x=(df_sens["LCOE_minus"] - lcoe_base_val).tolist(),
                y=df_sens["Variable"].tolist(),
                orientation="h",
                base=lcoe_base_val,
                marker=dict(color="#2563eb"),
                name=f"-{sens_delta_pct:.0f}%",
                hovertemplate="%{y}<br>LCOE: %{x:.2f} + base<extra></extra>",
            ))
            fig_torn.add_trace(_go.Bar(
                x=(df_sens["LCOE_plus"] - lcoe_base_val).tolist(),
                y=df_sens["Variable"].tolist(),
                orientation="h",
                base=lcoe_base_val,
                marker=dict(color="#dc2626"),
                name=f"+{sens_delta_pct:.0f}%",
                hovertemplate="%{y}<br>LCOE: %{x:.2f} + base<extra></extra>",
            ))
            fig_torn.add_vline(x=lcoe_base_val, line=dict(color="#7e22ce", width=2, dash="dash"))
            fig_torn.update_layout(
                template="plotly_white",
                barmode="overlay",
                height=350,
                margin=dict(l=14, r=14, t=42, b=16),
                xaxis_title=f"LCOE ({moneda_base}/MWh)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_torn, use_container_width=True, config=PLOTLY_PERF_CONFIG)
        except Exception as _exc:
            st.warning(f"No pude calcular tornado de sensibilidad: {_exc}")

    # B1 - Monte Carlo P50/P75/P90/P99
    with st.container(border=True, key="f5_card_montecarlo"):
        _render_f5_section_header(_f5_icon_svg("chart"), "Monte Carlo · P50 / P75 / P90 / P99 (banca)")
        st.markdown(
            '<div class="f5-mini-note"><span class="f5-info-dot" style="width:1.2rem;height:1.2rem;font-size:0.72rem;">i</span>'
            'Muestreo Monte Carlo de incertidumbres (Weibull, curva, pérdidas, wake) → bandas de confianza AEP. '
            'Banca exige P90 mínimo para project finance.'
            '</div>',
            unsafe_allow_html=True,
        )

        mc_n_default = int(float(config.get("f5_mc_n_samples") or 2000))
        mc_sk_default = float(config.get("f5_mc_sigma_k_pct") or 3.0)
        mc_sc_default = float(config.get("f5_mc_sigma_c_pct") or 4.0)
        mc_scurva_default = float(config.get("f5_mc_sigma_curva_pct") or 3.0)
        mc_sperd_default = float(config.get("f5_mc_sigma_perdidas_pct") or 20.0)
        mc_swake_default = float(config.get("f5_mc_sigma_wake_pct") or 15.0)
        mc_seed_default = int(float(config.get("f5_mc_seed") or 42))

        mc_c1, mc_c2, mc_c3 = st.columns(3)
        with mc_c1:
            mc_n_samples = st.number_input("N muestras", min_value=200, max_value=20000, value=mc_n_default, step=200, key="f5_mc_n_samples")
            mc_seed = st.number_input("Seed (reproducibilidad)", min_value=0, max_value=99999, value=mc_seed_default, step=1, key="f5_mc_seed")
        with mc_c2:
            mc_sigma_c = st.number_input("σ Weibull c (%)", min_value=0.0, max_value=30.0, value=mc_sc_default, step=0.5, format="%.1f", key="f5_mc_sigma_c_pct", help="Incertidumbre escala Weibull. Sat ~3-5%, torre ~2-3%")
            mc_sigma_k = st.number_input("σ Weibull k (%)", min_value=0.0, max_value=30.0, value=mc_sk_default, step=0.5, format="%.1f", key="f5_mc_sigma_k_pct")
        with mc_c3:
            mc_sigma_curva = st.number_input("σ curva potencia (%)", min_value=0.0, max_value=20.0, value=mc_scurva_default, step=0.5, format="%.1f", key="f5_mc_sigma_curva_pct", help="Tolerancia certificación curva (IEC 61400-12-1 típico ±5%)")
            mc_sigma_perd = st.number_input("σ pérdidas (% rel.)", min_value=0.0, max_value=100.0, value=mc_sperd_default, step=1.0, format="%.1f", key="f5_mc_sigma_perdidas_pct")

        mc_sigma_wake = st.number_input("σ wake (% rel.)", min_value=0.0, max_value=100.0, value=mc_swake_default, step=1.0, format="%.1f", key="f5_mc_sigma_wake_pct")

        if st.button("Ejecutar Monte Carlo", key="f5_btn_run_mc", use_container_width=True, type="primary"):
            st.session_state["f5_mc_run_flag"] = True

        if st.session_state.get("f5_mc_run_flag"):
            with st.spinner(f"Muestreando {int(mc_n_samples)} casos…"):
                try:
                    _perd_tuple_mc = (
                        ("disp_turb", float(disp_pct)),
                        ("disp_red", float(loss_disp_red_pct)),
                        ("elec", float(elec_pct)),
                        ("hielo", float(loss_hielo_pct)),
                        ("histeresis", float(loss_histeresis_pct)),
                        ("curtailment", float(loss_curtailment_pct)),
                        ("otras", float(otras_pct)),
                    )
                    mc_res = energia_calc.muestrear_aep_montecarlo(
                        aep_bruta_total=float(res["aep_bruta_total"]),
                        aep_con_estela_total=float(res["aep_con_estela_total"]),
                        perdidas_dict_tuple=_perd_tuple_mc,
                        sigma_k_pct=mc_sigma_k,
                        sigma_c_pct=mc_sigma_c,
                        sigma_curva_pct=mc_sigma_curva,
                        sigma_perdidas_pct=mc_sigma_perd,
                        sigma_wake_pct=mc_sigma_wake,
                        n_samples=int(mc_n_samples),
                        seed=int(mc_seed),
                    )

                    kpis_html = (
                        '<div class="f5-econ-lcoe-pair">'
                        + _econ_lcoe_kpi(_f5_icon_svg("chart","#16a34a",14), "green", "P50 (MWh/año)", f"{mc_res['p50']:,.0f}")
                        + _econ_lcoe_kpi(_f5_icon_svg("chart","#2563eb",14), "blue", "P75 (MWh/año)", f"{mc_res['p75']:,.0f}")
                        + '</div><div class="f5-econ-lcoe-pair">'
                        + _econ_lcoe_kpi(_f5_icon_svg("chart","#ea580c",14), "purple", "P90 (banca)", f"{mc_res['p90']:,.0f}")
                        + _econ_lcoe_kpi(_f5_icon_svg("chart","#dc2626",14), "purple", "P99 (stress)", f"{mc_res['p99']:,.0f}")
                        + '</div>'
                    )
                    st.markdown(kpis_html, unsafe_allow_html=True)

                    rel_p90 = mc_res["p90"] / mc_res["p50"] if mc_res["p50"] > 0 else 0.0
                    rel_p99 = mc_res["p99"] / mc_res["p50"] if mc_res["p50"] > 0 else 0.0
                    st.markdown(
                        f'<div class="f5-mini-note">'
                        f'Mean: <b>{mc_res["mean"]:,.0f}</b> · σ: <b>{mc_res["std"]:,.0f}</b> ({mc_res["std"]/mc_res["mean"]*100 if mc_res["mean"]>0 else 0:.1f}%) · '
                        f'P90/P50: <b>{rel_p90:.3f}</b> · P99/P50: <b>{rel_p99:.3f}</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    import numpy as _np_mc
                    import plotly.graph_objects as _go_mc
                    edges = _np_mc.asarray(mc_res["histograma_edges"])
                    centers = (edges[:-1] + edges[1:]) / 2.0
                    fig_mc = _go_mc.Figure()
                    fig_mc.add_trace(_go_mc.Bar(x=centers, y=mc_res["histograma_counts"], marker_color="#94a3b8", name="Frecuencia"))
                    for p_name, p_val, color in [("P99", mc_res["p99"], "#dc2626"), ("P90", mc_res["p90"], "#ea580c"), ("P75", mc_res["p75"], "#2563eb"), ("P50", mc_res["p50"], "#16a34a")]:
                        fig_mc.add_vline(x=p_val, line=dict(color=color, width=2, dash="dash"), annotation_text=p_name, annotation_position="top")
                    fig_mc.update_layout(
                        template="plotly_white",
                        height=380,
                        margin=dict(l=14, r=14, t=42, b=16),
                        xaxis_title="AEP (MWh/año)",
                        yaxis_title="Frecuencia",
                        showlegend=False,
                    )
                    st.plotly_chart(fig_mc, use_container_width=True, config=PLOTLY_PERF_CONFIG)

                    guardar_config_values({
                        "f5_aep_p50": mc_res["p50"], "f5_aep_p75": mc_res["p75"],
                        "f5_aep_p90": mc_res["p90"], "f5_aep_p99": mc_res["p99"],
                        "f5_aep_mc_mean": mc_res["mean"], "f5_aep_mc_std": mc_res["std"],
                        "f5_mc_n_samples": mc_n_samples, "f5_mc_seed": mc_seed,
                        "f5_mc_sigma_k_pct": mc_sigma_k, "f5_mc_sigma_c_pct": mc_sigma_c,
                        "f5_mc_sigma_curva_pct": mc_sigma_curva, "f5_mc_sigma_perdidas_pct": mc_sigma_perd,
                        "f5_mc_sigma_wake_pct": mc_sigma_wake,
                    })
                except Exception as _exc:
                    st.error(f"Monte Carlo falló: {_exc}")

    # B4 - AEP serie temporal horaria
    with st.container(border=True, key="f5_card_aep_serie"):
        _render_f5_section_header(_f5_icon_svg("energy"), "AEP por serie temporal horaria")
        st.markdown(
            '<div class="f5-mini-note"><span class="f5-info-dot" style="width:1.2rem;height:1.2rem;font-size:0.72rem;">i</span>'
            'Calcula AEP hora-a-hora con la serie NASA POWER (no Weibull agregado). Habilita análisis de patrones estacionales, '
            'horarios, y futura integración con PPA/curtailment dinámico.'
            '</div>',
            unsafe_allow_html=True,
        )
        if st.button("Calcular AEP serie horaria", key="f5_btn_run_serie", use_container_width=True):
            st.session_state["f5_serie_run_flag"] = True

        if st.session_state.get("f5_serie_run_flag"):
            with st.spinner("Calculando AEP horaria…"):
                try:
                    _perd_tuple_h = (
                        ("disp_turb", float(disp_pct)),
                        ("disp_red", float(loss_disp_red_pct)),
                        ("elec", float(elec_pct)),
                        ("hielo", float(loss_hielo_pct)),
                        ("histeresis", float(loss_histeresis_pct)),
                        ("curtailment", float(loss_curtailment_pct)),
                        ("otras", float(otras_pct)),
                    )
                    _df_curva_prep = preparar_datos_curva(df_curva_raw)
                    res_serie = energia_calc.calcular_aep_serie_horaria(
                        df_analisis=df_analisis,
                        df_curva=_df_curva_prep,
                        n_turbinas=int(n_turbinas),
                        factor_densidad=float(factor_densidad_efectivo),
                        wake_losses_sector=wake_losses_sector,
                        wake_mode=wake_mode,
                        wake_manual_pct=float(wake_manual_pct),
                        perdidas_dict_tuple=_perd_tuple_h,
                    )

                    aep_total_serie = res_serie["aep_total_mwh"]
                    aep_weibull = float(res["aep_neta_total"])
                    diff_pct = (aep_total_serie - aep_weibull) / aep_weibull * 100.0 if aep_weibull > 0 else 0.0

                    kpis_serie = (
                        '<div class="f5-econ-lcoe-pair">'
                        + _econ_lcoe_kpi(_f5_icon_svg("energy","#16a34a",14), "green", "AEP serie horaria", f"{aep_total_serie:,.0f} MWh")
                        + _econ_lcoe_kpi(_f5_icon_svg("energy","#2563eb",14), "blue", "AEP Weibull (ref)", f"{aep_weibull:,.0f} MWh")
                        + '</div>'
                    )
                    st.markdown(kpis_serie, unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="f5-mini-note">'
                        f'Diferencia serie vs Weibull: <b>{diff_pct:+.2f}%</b> · '
                        f'Factor planta serie: <b>{res_serie["factor_planta_pct"]:.1f}%</b>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # Heatmap mes x hora
                    heatmap = res_serie["heatmap_mes_hora"]
                    if len(heatmap) > 0:
                        import plotly.graph_objects as _go_hm
                        fig_hm = _go_hm.Figure(data=_go_hm.Heatmap(
                            z=heatmap.values / 1e6,  # MW
                            x=[f"{h:02d}h" for h in heatmap.columns],
                            y=[["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][m-1] for m in heatmap.index],
                            colorscale="YlOrRd",
                            colorbar=dict(title="MW medio"),
                        ))
                        fig_hm.update_layout(
                            template="plotly_white",
                            height=420,
                            margin=dict(l=14, r=14, t=42, b=16),
                            title="Producción media (MW) por mes y hora",
                            xaxis_title="Hora del día",
                            yaxis_title="Mes",
                        )
                        st.plotly_chart(fig_hm, use_container_width=True, config=PLOTLY_PERF_CONFIG)

                    # AEP por mes
                    aep_por_mes = res_serie["aep_por_mes"]
                    if len(aep_por_mes) > 0:
                        import plotly.graph_objects as _go_mes
                        fig_mes = _go_mes.Figure()
                        fig_mes.add_trace(_go_mes.Bar(
                            x=[["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][m-1] for m in aep_por_mes.index],
                            y=aep_por_mes.values,
                            marker_color="#2563eb",
                        ))
                        fig_mes.update_layout(
                            template="plotly_white",
                            height=300,
                            margin=dict(l=14, r=14, t=42, b=16),
                            title="AEP mensual (MWh)",
                            xaxis_title="Mes",
                            yaxis_title="AEP (MWh)",
                        )
                        st.plotly_chart(fig_mes, use_container_width=True, config=PLOTLY_PERF_CONFIG)

                    guardar_config_values({
                        "f5_aep_serie_horaria_total": aep_total_serie,
                        "f5_factor_planta_serie_pct": res_serie["factor_planta_pct"],
                        "f5_serie_horaria_calculada": "True",
                    })
                except Exception as _exc:
                    st.error(f"AEP serie horaria falló: {_exc}")


MASTER_DOCX_FILE_NAME = "informe_tecnico editado por mi.docx"
master_docx_state_key = "fase5_word_master_docx_bytes"
master_docx_name_state_key = "fase5_word_master_docx_name"
master_docx_bytes = st.session_state.get(master_docx_state_key)
master_docx_name = st.session_state.get(master_docx_name_state_key, MASTER_DOCX_FILE_NAME)
sens_variable = str(config.get("f5_sens_variable") or "Disponibilidad")

st.session_state[RUNTIME_CONTEXT_STATE_KEY] = {
    "project_name_default": project_name_default,
    "base_viento": base_viento,
    "modo_estadistico": modo_estadistico,
    "metodo_detalle": metodo_detalle,
    "altura_deseada": altura_deseada,
    "dir_altura": dir_altura,
    "roughness_label": roughness_label,
    "n_turbinas": int(n_turbinas),
    "wake_mode": wake_mode,
    "wake_manual_pct": wake_manual_pct,
    "disp_pct": disp_pct,
    "elec_pct": elec_pct,
    "otras_pct": otras_pct,
    "sens_variable": sens_variable,
    "ct": ct,
    "kw": kw,
    "res": res,
    "df_aep_sector": df_aep_sector,
    "tabla_perdidas": tabla_perdidas,
    "comp_df": comp_df,
    "comp_sector_df": comp_sector_df,
    "df_curva_raw": df_curva_raw,
    "df_nasa": df_nasa,
    "df_layout": df_layout,
    "resumen_rosa": resumen_rosa,
    "fig_wind_rose_export": fig_wind_rose_export,
    "fig_layout_export": fig_layout_export,
    "fig_resumen": fig_resumen,
    "fig_dona": fig_dona,
    "fig_sectorial": fig_sectorial,
    "fig_sens": None,
    "roughness_options": ROUGHNESS_OPTIONS,
    "master_docx_bytes": master_docx_bytes,
    "master_docx_name": master_docx_name,
    "lcoe": {
        "moneda_base": moneda_base,
        "moneda_visualizacion": moneda_visualizacion,
        "fx_mode": fx_mode,
        "fx_rate_cop_per_usd": fx_rate_cop_per_usd,
        "fx_timestamp": fx_timestamp,
        "unidad_monetaria": moneda_base,
        **lcoe,
    },
    "economics": {
        "base_metrics": metricas_base_economicas,
        "capex_mode": capex_mode,
        "capex_total": capex_result["capex_total"],
        "capex_breakdown": capex_result["breakdown"],
        "opex_mode": opex_mode,
        "opex_total_anual": opex_result["opex_total_anual"],
        "opex_breakdown": opex_result["breakdown"],
        "moneda_base": moneda_base,
        "moneda_visualizacion": moneda_visualizacion,
        "fx_mode": fx_mode,
        "fx_rate_cop_per_usd": fx_rate_cop_per_usd,
        "fx_timestamp": fx_timestamp,
        "fx_source": fx_source,
        "unidad_monetaria": moneda_base,
        "vp_costos": lcoe["valor_presente_costos"],
        "vp_energia": lcoe["valor_presente_energia"],
        "lcoe_mwh": lcoe["lcoe_mwh"],
        "lcoe_kwh": lcoe["lcoe_kwh"],
        "capex_total_display": economic_display["capex_total_display"],
        "opex_total_anual_display": economic_display["opex_total_anual_display"],
        "vp_costos_display": economic_display["vp_costos_display"],
        "lcoe_display_mwh": economic_display["lcoe_display_mwh"],
        "lcoe_display_kwh": economic_display["lcoe_display_kwh"],
    },
}

with st.container(border=True, key="f5_card_export"):
    _render_f5_section_header_card(_f5_icon_svg("export", "#2563eb", 20), "Exportación y guardado final")
    _render_f5_info(
        "Guarde su análisis y exporte los resultados en los formatos que necesita. "
        "Las exportaciones finales se preparan para la Fase 6 con el contexto calculado aquí."
    )
    st.markdown(
        '<div class="f5-ref-export-grid">'
        f'<div>{_render_f5_action_card(_f5_icon_svg("pdf","#dc2626",36), "Exportar reporte ejecutivo", "Resumen del proyecto, resultados clave y análisis técnico.", "", "red", "blue") or ""}</div>'
        f'<div>{_render_f5_action_card(_f5_icon_svg("excel","#16a34a",36), "Exportar anexos y datos", "Tabla de cálculo, campo y resultados detallados en Excel.", "", "green", "green") or ""}</div>'
        f'<div>{_render_f5_action_card(_f5_icon_svg("word","#2563eb",36), "Exportar informe técnico", "Informe técnico completo con metodología y resultados.", "", "blue", "purple") or ""}</div>'
        f'<div>{_render_f5_action_card(_f5_icon_svg("save","#7c3aed",36), "Guardar proyecto final", "Guarde la configuración y resultados del proyecto.", "", "purple", "purple") or ""}</div>'
        f'<div>{_render_f5_action_card(_f5_icon_svg("folder","#d97706",36), "Cargar proyecto guardado", "Cargue un proyecto previamente guardado.", "", "orange", "orange") or ""}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    exp1, exp2, exp3, exp4, exp5 = st.columns(5, gap="medium")
    with exp1:
        st.page_link("pages/6_Fase_6_Exportar_y_guardar.py", label="Exportar PDF", icon=":material/picture_as_pdf:", use_container_width=True)
    with exp2:
        st.page_link("pages/6_Fase_6_Exportar_y_guardar.py", label="Exportar Excel", icon=":material/table_view:", use_container_width=True)
    with exp3:
        st.page_link("pages/6_Fase_6_Exportar_y_guardar.py", label="Exportar DOCX", icon=":material/description:", use_container_width=True)
    with exp4:
        st.page_link("pages/6_Fase_6_Exportar_y_guardar.py", label="Guardar proyecto", icon=":material/save:", use_container_width=True)
    with exp5:
        st.page_link("pages/1_Fase_1_Aerogenerador.py", label="Cargar proyecto", icon=":material/folder_open:", use_container_width=True)
    st.caption(
        f"Contexto disponible para Fase 6: {report_context['report_style_label']} "
        f"({project_context['mode_label']}, perfil: {project_context['profile_label']})."
    )

with st.expander("Ver configuración usada en la Fase 5"):
    st.write({
        "base_viento": base_viento,
        "modo_estadistico": modo_estadistico,
        "metodo_detalle": metodo_detalle,
        "altura_deseada_m": altura_deseada,
        "direccion_usada": dir_altura,
        "roughness_label": roughness_label,
        "n_turbinas": n_turbinas,
        "wake_mode": wake_mode,
        "wake_manual_pct": wake_manual_pct,
        "disponibilidad_pct": disp_pct,
        "electricas_pct": elec_pct,
        "otras_pct": otras_pct,
        "ct": ct,
        "kw": kw,
        "project_name": project_name_default,
        "potencia_instalada_mw": metricas_base_economicas["potencia_instalada_mw"],
        "capex_total": capex_result["capex_total"],
        "opex_total_anual": opex_result["opex_total_anual"],
        "lcoe_mwh": lcoe["lcoe_mwh"],
        "lcoe_kwh": lcoe["lcoe_kwh"],
        "moneda_base": moneda_base,
        "moneda_visualizacion": moneda_visualizacion,
        "fx_rate_cop_per_usd": fx_rate_cop_per_usd,
        "lcoe_display_mwh": economic_display["lcoe_display_mwh"],
        "lcoe_display_kwh": economic_display["lcoe_display_kwh"],
        "unidad_monetaria": moneda_base,
    })

render_dropdown_visibility_fix()
