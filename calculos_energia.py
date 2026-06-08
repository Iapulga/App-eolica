import numpy as np
import pandas as pd
import streamlit as st

from calculos import (
    PROMEDIO_LOG_EXP_LABEL,
    ROUGHNESS_OPTIONS_DEFAULT,
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


def potencia_media_sector(curva_df, fila_sector, metodo="Weibull", vmax=35.0, dv=0.1, factor_densidad=1.0):
    v = np.arange(0.0, vmax + dv, dv)
    p = interpolar_potencia_curva_preparada(curva_df, v)
    try:
        fd = float(factor_densidad)
    except (TypeError, ValueError):
        fd = 1.0
    if not np.isfinite(fd) or fd <= 0:
        fd = 1.0
    p = p * fd

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
def calcular_aep_sectorial(curva_df, resumen_rosa, metodo_dist, n_turbinas, wake_mode, wake_losses_sector, wake_manual_pct, factor_densidad=1.0):
    filas = []

    for _, row in resumen_rosa.iterrows():
        sector = str(row["Sector"])
        freq_pct = float(row["Frecuencia (%)"])
        horas_eq = float(row["Horas equivalentes anuales (h/año)"])

        p_media_turbina_w = potencia_media_sector(curva_df, row, metodo=metodo_dist, factor_densidad=factor_densidad)
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


LOSS_BUCKET_ORDER = [
    ("disp_turb", "Disponibilidad turbina"),
    ("disp_red", "Disponibilidad red"),
    ("elec", "Eléctricas"),
    ("hielo", "Hielo / Soiling"),
    ("histeresis", "Histéresis"),
    ("curtailment", "Curtailment"),
    ("otras", "Otras"),
]


def _safe_pct(value, default=0.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(v) or v < 0:
        return float(default)
    return v


def aplicar_perdidas_detalladas(aep_con_estela, perdidas_dict):
    factor = 1.0
    for key, _ in LOSS_BUCKET_ORDER:
        factor *= (1.0 - _safe_pct(perdidas_dict.get(key, 0.0)) / 100.0)
    return aep_con_estela * factor


def desglose_perdidas_secuencial(aep_con_estela, perdidas_dict):
    base = float(aep_con_estela)
    out = {}
    for key, label in LOSS_BUCKET_ORDER:
        pct = _safe_pct(perdidas_dict.get(key, 0.0)) / 100.0
        perdida = base * pct
        out[f"perdida_{key}_mwh"] = perdida
        out[f"perdida_{key}_label"] = label
        base = base - perdida
    out["aep_neta_mwh"] = base
    return out


@st.cache_data(show_spinner=False)
def calcular_resultados_metodo(
    curva_df,
    resumen_rosa,
    metodo_dist,
    n_turbinas,
    wake_mode,
    wake_losses_sector,
    wake_manual_pct,
    disp_pct,
    elec_pct,
    otras_pct,
    factor_densidad=1.0,
    loss_disp_red_pct=0.0,
    loss_hielo_pct=0.0,
    loss_histeresis_pct=0.0,
    loss_curtailment_pct=0.0,
):
    df_aep_sector = calcular_aep_sectorial(
        curva_df=curva_df,
        resumen_rosa=resumen_rosa,
        metodo_dist=metodo_dist,
        n_turbinas=n_turbinas,
        wake_mode=wake_mode,
        wake_losses_sector=wake_losses_sector,
        wake_manual_pct=wake_manual_pct,
        factor_densidad=factor_densidad,
    )

    aep_bruta_total = float(df_aep_sector["AEP bruta parque (MWh/año)"].sum())
    aep_con_estela_total = float(df_aep_sector["AEP con estela (MWh/año)"].sum())
    perdida_estela_mwh = float(df_aep_sector["Pérdida estela energética (MWh/año)"].sum())

    perdidas_dict = {
        "disp_turb": disp_pct,
        "disp_red": loss_disp_red_pct,
        "elec": elec_pct,
        "hielo": loss_hielo_pct,
        "histeresis": loss_histeresis_pct,
        "curtailment": loss_curtailment_pct,
        "otras": otras_pct,
    }

    extras_total = sum(_safe_pct(perdidas_dict[k]) for k in ("disp_red", "hielo", "histeresis", "curtailment"))
    usar_detallado = extras_total > 0.0

    if usar_detallado:
        aep_neta_total = aplicar_perdidas_detalladas(aep_con_estela_total, perdidas_dict)
    else:
        aep_neta_total = aplicar_perdidas_globales(
            aep_con_estela=aep_con_estela_total,
            disp_pct=disp_pct,
            elec_pct=elec_pct,
            otras_pct=otras_pct,
        )

    desglose = desglose_perdidas_secuencial(aep_con_estela_total, perdidas_dict)

    perdida_disp_mwh = desglose["perdida_disp_turb_mwh"]
    perdida_disp_red_mwh = desglose["perdida_disp_red_mwh"]
    perdida_elec_mwh = desglose["perdida_elec_mwh"]
    perdida_hielo_mwh = desglose["perdida_hielo_mwh"]
    perdida_histeresis_mwh = desglose["perdida_histeresis_mwh"]
    perdida_curtailment_mwh = desglose["perdida_curtailment_mwh"]
    perdida_otras_mwh = desglose["perdida_otras_mwh"]

    factor_global = 1.0
    for key, _ in LOSS_BUCKET_ORDER:
        factor_global *= (1.0 - _safe_pct(perdidas_dict.get(key, 0.0)) / 100.0)
    df_aep_sector["AEP neta sector (MWh/año)"] = df_aep_sector["AEP con estela (MWh/año)"] * factor_global

    potencia_nominal_turbina_w = float(curva_df["Potencia_W"].max()) if len(curva_df) > 0 else 0.0
    try:
        fd = float(factor_densidad)
    except (TypeError, ValueError):
        fd = 1.0
    if not np.isfinite(fd) or fd <= 0:
        fd = 1.0
    potencia_nominal_turbina_w_corr = potencia_nominal_turbina_w * fd
    potencia_nominal_parque_w = potencia_nominal_turbina_w_corr * n_turbinas

    if potencia_nominal_parque_w > 0:
        factor_planta_bruto = aep_bruta_total * 1e6 / (potencia_nominal_parque_w * 8760.0) * 100.0
        factor_planta_neto = aep_neta_total * 1e6 / (potencia_nominal_parque_w * 8760.0) * 100.0
    else:
        factor_planta_bruto = np.nan
        factor_planta_neto = np.nan

    aep_bruta_turbina = aep_bruta_total / n_turbinas
    aep_neta_turbina = aep_neta_total / n_turbinas

    if usar_detallado:
        conceptos = ["Estelas", "Disp. turbina", "Disp. red", "Eléctricas",
                     "Hielo/Soiling", "Histéresis", "Curtailment", "Otras", "Total"]
        perdida_pct = [
            (perdida_estela_mwh / aep_bruta_total * 100.0) if aep_bruta_total > 0 else 0.0,
            _safe_pct(disp_pct),
            _safe_pct(loss_disp_red_pct),
            _safe_pct(elec_pct),
            _safe_pct(loss_hielo_pct),
            _safe_pct(loss_histeresis_pct),
            _safe_pct(loss_curtailment_pct),
            _safe_pct(otras_pct),
            (1.0 - aep_neta_total / aep_bruta_total) * 100.0 if aep_bruta_total > 0 else 0.0,
        ]
        energia_perdida = [
            perdida_estela_mwh,
            perdida_disp_mwh,
            perdida_disp_red_mwh,
            perdida_elec_mwh,
            perdida_hielo_mwh,
            perdida_histeresis_mwh,
            perdida_curtailment_mwh,
            perdida_otras_mwh,
            aep_bruta_total - aep_neta_total,
        ]
    else:
        conceptos = ["Estelas", "Disponibilidad", "Eléctricas", "Otras", "Total"]
        perdida_pct = [
            (perdida_estela_mwh / aep_bruta_total * 100.0) if aep_bruta_total > 0 else 0.0,
            disp_pct,
            elec_pct,
            otras_pct,
            (1.0 - aep_neta_total / aep_bruta_total) * 100.0 if aep_bruta_total > 0 else 0.0,
        ]
        energia_perdida = [
            perdida_estela_mwh,
            perdida_disp_mwh,
            perdida_elec_mwh,
            perdida_otras_mwh,
            aep_bruta_total - aep_neta_total,
        ]

    tabla_perdidas = pd.DataFrame({
        "Concepto": conceptos,
        "Pérdida (%)": perdida_pct,
        "Energía perdida (MWh/año)": energia_perdida,
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
        "potencia_nominal_turbina_w": potencia_nominal_turbina_w_corr,
        "potencia_nominal_turbina_w_curva": potencia_nominal_turbina_w,
        "factor_densidad_aplicado": fd,
        "perdida_disp_mwh": perdida_disp_mwh,
        "perdida_disp_red_mwh": perdida_disp_red_mwh,
        "perdida_elec_mwh": perdida_elec_mwh,
        "perdida_hielo_mwh": perdida_hielo_mwh,
        "perdida_histeresis_mwh": perdida_histeresis_mwh,
        "perdida_curtailment_mwh": perdida_curtailment_mwh,
        "perdida_otras_mwh": perdida_otras_mwh,
        "base_sens": aep_con_estela_total,
        "loss_buckets_usados": usar_detallado,
        "perdidas_dict": perdidas_dict,
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
    factor_densidad=1.0,
    wake_model="jensen",
    ambient_ti=0.10,
    h_hub=80.0,
    loss_disp_red_pct=0.0,
    loss_hielo_pct=0.0,
    loss_histeresis_pct=0.0,
    loss_curtailment_pct=0.0,
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
                    modelo=wake_model,
                    ambient_ti=ambient_ti,
                    h_hub=h_hub,
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
            factor_densidad=factor_densidad,
            loss_disp_red_pct=loss_disp_red_pct,
            loss_hielo_pct=loss_hielo_pct,
            loss_histeresis_pct=loss_histeresis_pct,
            loss_curtailment_pct=loss_curtailment_pct,
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
            factor_densidad=factor_densidad,
            loss_disp_red_pct=loss_disp_red_pct,
            loss_hielo_pct=loss_hielo_pct,
            loss_histeresis_pct=loss_histeresis_pct,
            loss_curtailment_pct=loss_curtailment_pct,
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


@st.cache_data(show_spinner=False)
def muestrear_aep_montecarlo(
    aep_bruta_total,
    aep_con_estela_total,
    perdidas_dict_tuple,
    sigma_k_pct=3.0,
    sigma_c_pct=4.0,
    sigma_curva_pct=3.0,
    sigma_perdidas_pct=20.0,
    sigma_wake_pct=15.0,
    n_samples=2000,
    seed=42,
):
    rng = np.random.default_rng(int(seed))
    n = int(n_samples)

    # Multiplier viento desde k,c uncertainty (aprox: AEP ∝ c^2.5 zona pre-rated)
    factor_v_pct = 2.5 * float(sigma_c_pct) + 0.3 * float(sigma_k_pct)
    factor_v = 1.0 + rng.normal(0.0, factor_v_pct / 100.0, n)

    factor_curva = 1.0 + rng.normal(0.0, float(sigma_curva_pct) / 100.0, n)

    aep_bruta = max(0.0, float(aep_bruta_total))
    aep_con_estela = max(0.0, float(aep_con_estela_total))
    wake_pct_base = (1.0 - aep_con_estela / aep_bruta) if aep_bruta > 0 else 0.0
    wake_pct_sample = np.clip(
        wake_pct_base * (1.0 + rng.normal(0.0, float(sigma_wake_pct) / 100.0, n)),
        0.0, 0.9,
    )

    aep_pre_loss = aep_bruta * factor_v * factor_curva * (1.0 - wake_pct_sample)

    perdidas_dict = dict(perdidas_dict_tuple)
    factor_perdidas_total = np.ones(n)
    for bucket, pct_base in perdidas_dict.items():
        pct_base_f = float(pct_base) if pct_base is not None else 0.0
        if pct_base_f > 0:
            pct_sample = np.clip(
                pct_base_f * (1.0 + rng.normal(0.0, float(sigma_perdidas_pct) / 100.0, n)),
                0.0, 100.0,
            )
            factor_perdidas_total *= (1.0 - pct_sample / 100.0)

    aep_samples = aep_pre_loss * factor_perdidas_total
    aep_samples = np.clip(aep_samples, 0.0, None)

    p50 = float(np.percentile(aep_samples, 50))
    p75 = float(np.percentile(aep_samples, 25))
    p90 = float(np.percentile(aep_samples, 10))
    p99 = float(np.percentile(aep_samples, 1))

    counts, bin_edges = np.histogram(aep_samples, bins=40)

    return {
        "samples": aep_samples,
        "p50": p50,
        "p75": p75,
        "p90": p90,
        "p99": p99,
        "mean": float(np.mean(aep_samples)),
        "std": float(np.std(aep_samples, ddof=1)) if n > 1 else 0.0,
        "n_samples": n,
        "histograma_counts": counts.tolist(),
        "histograma_edges": bin_edges.tolist(),
        "factor_v_pct_usado": factor_v_pct,
    }


@st.cache_data(show_spinner=False)
def calcular_aep_serie_horaria(
    df_analisis,
    df_curva,
    n_turbinas,
    factor_densidad=1.0,
    wake_losses_sector=None,
    wake_mode="Manual",
    wake_manual_pct=0.0,
    perdidas_dict_tuple=(),
    factor_densidad_serie=None,
):
    if df_analisis is None or len(df_analisis) == 0:
        return {
            "df_horario": pd.DataFrame(),
            "aep_total_mwh": float("nan"),
            "aep_por_mes": pd.Series(dtype=float),
            "heatmap_mes_hora": pd.DataFrame(),
            "factor_planta_pct": float("nan"),
        }

    df_h = df_analisis.copy()
    if "WS_ANALISIS" not in df_h.columns:
        raise ValueError("df_analisis no contiene WS_ANALISIS")

    ws = pd.to_numeric(df_h["WS_ANALISIS"], errors="coerce").to_numpy(dtype=float)
    n_hours = len(ws)

    p_turb_w = interpolar_potencia_curva_preparada(df_curva, ws)
    try:
        fd = float(factor_densidad)
    except (TypeError, ValueError):
        fd = 1.0
    if not np.isfinite(fd) or fd <= 0:
        fd = 1.0

    if factor_densidad_serie is not None and len(factor_densidad_serie) == n_hours:
        fd_serie = np.asarray(factor_densidad_serie, dtype=float)
        fd_serie = np.where(np.isfinite(fd_serie) & (fd_serie > 0), fd_serie, fd)
        p_turb_w = p_turb_w * fd_serie
    else:
        p_turb_w = p_turb_w * fd

    p_park_w = p_turb_w * int(n_turbinas)

    if wake_mode == "Automática desde Fase 4" and wake_losses_sector and "WD_USADA" in df_h.columns:
        wd = pd.to_numeric(df_h["WD_USADA"], errors="coerce").to_numpy(dtype=float)
        from calculos import SECTOR_CENTERS_16, SECTOR_LABELS_16
        sector_idx = np.full(n_hours, -1, dtype=int)
        wd_mod = np.mod(wd, 360.0)
        for i, center in enumerate(SECTOR_CENTERS_16):
            lo = (center - 11.25) % 360.0
            hi = (center + 11.25) % 360.0
            if lo < hi:
                mask = (wd_mod >= lo) & (wd_mod < hi)
            else:
                mask = (wd_mod >= lo) | (wd_mod < hi)
            sector_idx[mask] = i
        wake_pct_h = np.zeros(n_hours, dtype=float)
        for i, label in enumerate(SECTOR_LABELS_16):
            pct = float(wake_losses_sector.get(label, 0.0))
            wake_pct_h[sector_idx == i] = pct
        sector_labels_arr = np.array([SECTOR_LABELS_16[i] if i >= 0 else "?" for i in sector_idx])
    else:
        wake_pct_h = np.full(n_hours, float(wake_manual_pct), dtype=float)
        sector_labels_arr = np.full(n_hours, "?", dtype=object)

    factor_perd = 1.0
    for _, pct in dict(perdidas_dict_tuple).items():
        try:
            v = float(pct)
        except (TypeError, ValueError):
            v = 0.0
        factor_perd *= (1.0 - max(0.0, v) / 100.0)

    aep_h_mwh = p_park_w * (1.0 - wake_pct_h / 100.0) * factor_perd / 1e6

    df_h_out = pd.DataFrame({
        "timestamp": df_h.get("timestamp", pd.Series(range(n_hours))),
        "ws": ws,
        "potencia_parque_W": p_park_w * (1.0 - wake_pct_h / 100.0) * factor_perd,
        "aep_h_MWh": aep_h_mwh,
        "sector": sector_labels_arr,
        "wake_pct_h": wake_pct_h,
    })

    # La serie horaria puede abarcar varios años (p.ej. NASA POWER ~5 años de
    # datos). Anualizamos dividiendo por el nº de años para obtener AEP/año,
    # comparable con el método Weibull (que ya es anual) y con factor de planta
    # físico (<100%). Sin esto, aep_total sumaría la energía de TODOS los años.
    n_years = (n_hours / 8760.0) if n_hours > 0 else 1.0
    if not np.isfinite(n_years) or n_years <= 0:
        n_years = 1.0
    aep_total = float(np.nansum(aep_h_mwh)) / n_years

    df_h_out["timestamp"] = pd.to_datetime(df_h_out["timestamp"], errors="coerce")
    df_with_ts = df_h_out.dropna(subset=["timestamp"])
    if len(df_with_ts) > 0:
        meses = df_with_ts["timestamp"].dt.month
        horas = df_with_ts["timestamp"].dt.hour
        aep_por_mes = df_with_ts.groupby(meses)["aep_h_MWh"].sum() / n_years
        heatmap = pd.DataFrame(
            df_with_ts.assign(mes=meses, hora=horas)
            .groupby(["mes", "hora"])["potencia_parque_W"]
            .mean()
            .unstack("hora")
        )
    else:
        aep_por_mes = pd.Series(dtype=float)
        heatmap = pd.DataFrame()

    potencia_nominal_parque_w = float(df_curva["Potencia_W"].max() if len(df_curva) > 0 else 0.0) * fd * int(n_turbinas)
    if potencia_nominal_parque_w > 0:
        factor_planta = aep_total * 1e6 / (potencia_nominal_parque_w * 8760.0) * 100.0
    else:
        factor_planta = float("nan")

    return {
        "df_horario": df_h_out,
        "aep_total_mwh": aep_total,
        "aep_por_mes": aep_por_mes,
        "heatmap_mes_hora": heatmap,
        "factor_planta_pct": factor_planta,
    }
