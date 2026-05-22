import numpy as np
import pandas as pd
import streamlit as st

from calculos import (
    ROUGHNESS_OPTIONS_DEFAULT,
    PROMEDIO_LOG_EXP_LABEL,
    analizar_estelas_parque_16,
    construir_serie_viento_analisis,
    interpolar_potencia_curva_preparada,
    normalizar_modelo_altura,
    preparar_datos_curva,
    preparar_datos_rosa,
    rayleigh_pdf,
    resumir_sectores_rosa,
    weibull_pdf,
)


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
        "Altura deseada - Log B (z0 teórica)": PROMEDIO_LOG_EXP_LABEL,
        "Altura deseada - Log B (z0 teÃ³rica)": PROMEDIO_LOG_EXP_LABEL,
        "Altura deseada - Promedio Log-Exp": PROMEDIO_LOG_EXP_LABEL,
    }
    return model_map.get(value, value)


@st.cache_data(show_spinner=False)
def construir_viento_analisis(
    df_nasa,
    modelo,
    altura_deseada,
    roughness_label,
    direccion_fuente,
    roughness_options=None,
):
    modelo = normalize_base_viento_for_energy(modelo)
    df, meta = construir_serie_viento_analisis(
        df_nasa=df_nasa,
        modelo=modelo,
        altura_deseada=altura_deseada,
        roughness_label=roughness_label,
        direccion_fuente=direccion_fuente,
        roughness_options=roughness_options or ROUGHNESS_OPTIONS_DEFAULT,
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
        "aep_con_estela_total": aep_con_estela_total,
        "perdida_estela_mwh": perdida_estela_mwh,
        "aep_neta_total": aep_neta_total,
        "factor_planta_bruto": factor_planta_bruto,
        "factor_planta_neto": factor_planta_neto,
        "aep_bruta_turbina": aep_bruta_turbina,
        "aep_neta_turbina": aep_neta_turbina,
        "potencia_nominal_turbina_w": potencia_nominal_turbina_w,
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
def calcular_aep_autoritativa(
    df_nasa,
    df_curva_raw,
    df_layout,
    base_viento,
    modo_estadistico,
    metodo_detalle,
    altura_deseada,
    roughness_label,
    direccion_fuente,
    n_turbinas,
    diametro,
    ct,
    kw,
    wake_mode,
    wake_manual_pct,
    disp_pct,
    elec_pct,
    otras_pct,
):
    df_curva = preparar_datos_curva(df_curva_raw)
    if len(df_curva) == 0:
        raise ValueError("No hay una curva de potencia válida para el cálculo energético.")

    df_analisis, meta = construir_viento_analisis(
        df_nasa=df_nasa,
        modelo=base_viento,
        altura_deseada=altura_deseada,
        roughness_label=roughness_label,
        direccion_fuente=direccion_fuente,
    )

    df_rosa = preparar_datos_rosa(df_analisis, ws_col="WS_ANALISIS", wd_col="WD_USADA")
    resumen_rosa = resumir_sectores_rosa(df_rosa, ws_col="WS_ANALISIS").copy()
    resumen_rosa["Horas equivalentes anuales (h/año)"] = resumen_rosa["Frecuencia (%)"] / 100.0 * 8760.0

    wake_losses_sector = {}
    wake_resumen = pd.DataFrame()
    wake_detalles = {}
    wake_perdida_ponderada = 0.0
    wake_warning = None

    if wake_mode == "Automática desde Fase 4":
        if len(df_layout) == 0:
            wake_warning = "No hay layout del parque guardado en la Fase 4. Se usará estela manual = 0%."
        else:
            try:
                wake_resumen, wake_detalles, wake_perdida_ponderada = analizar_estelas_parque_16(
                    df_layout=df_layout,
                    df_nasa=df_analisis,
                    curva_df=df_curva_raw,
                    diametro=diametro,
                    ct=ct,
                    kw=kw,
                    ws_col="WS_ANALISIS",
                    wd_col="WD_USADA",
                )
                wake_losses_sector = {
                    str(r["Sector"]): float(r["Pérdida por estela (%)"])
                    for _, r in wake_resumen.iterrows()
                }
            except Exception as exc:
                wake_warning = f"No pude leer estelas automáticas desde la Fase 4: {exc}. Se usará 0%."
                wake_losses_sector = {}
                wake_resumen = pd.DataFrame()
                wake_detalles = {}
                wake_perdida_ponderada = 0.0

    resultados = {}
    if modo_estadistico in {"Weibull", "Comparar Weibull y Rayleigh"}:
        resultados["Weibull"] = calcular_resultados_metodo(
            curva_df=df_curva,
            resumen_rosa=resumen_rosa,
            metodo_dist="Weibull",
            n_turbinas=n_turbinas,
            wake_mode=wake_mode,
            wake_losses_sector=wake_losses_sector,
            wake_manual_pct=wake_manual_pct,
            disp_pct=disp_pct,
            elec_pct=elec_pct,
            otras_pct=otras_pct,
        )

    if modo_estadistico in {"Rayleigh", "Comparar Weibull y Rayleigh"}:
        resultados["Rayleigh"] = calcular_resultados_metodo(
            curva_df=df_curva,
            resumen_rosa=resumen_rosa,
            metodo_dist="Rayleigh",
            n_turbinas=n_turbinas,
            wake_mode=wake_mode,
            wake_losses_sector=wake_losses_sector,
            wake_manual_pct=wake_manual_pct,
            disp_pct=disp_pct,
            elec_pct=elec_pct,
            otras_pct=otras_pct,
        )

    if not resultados:
        raise ValueError("Modo estadístico no soportado para el cálculo energético.")

    metodo_principal = metodo_detalle if metodo_detalle in resultados else next(iter(resultados))
    resultado_principal = resultados[metodo_principal]

    return {
        "meta": meta,
        "df_curva": df_curva,
        "df_analisis": df_analisis,
        "df_rosa": df_rosa,
        "resumen_rosa": resumen_rosa,
        "wake_losses_sector": wake_losses_sector,
        "wake_resumen": wake_resumen,
        "wake_detalles": wake_detalles,
        "wake_perdida_ponderada": float(wake_perdida_ponderada),
        "wake_warning": wake_warning,
        "resultados": resultados,
        "metodo_detalle_resuelto": metodo_principal,
        "df_sector": resultado_principal["df_sector"],
        "tabla_perdidas": resultado_principal["tabla_perdidas"],
        "resumen": resultado_principal["resumen"],
    }
