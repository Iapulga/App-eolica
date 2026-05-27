"""Hybrid wind + solar + storage — dimensioning preliminar.

Combinación común en Guajira: viento (alisios) + solar (irradiancia alta) son
complementarios. Hybrid plant comparte conexión grid → reduce LCOE + curtailment.

Usa pvlib (ya instalado) para perfil solar horario.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generar_perfil_solar_horario(timestamps, lat, lon, capacidad_solar_mw,
                                  azimuth_deg=180, tilt_deg=15, altitud_m=0,
                                  perdidas_pct=14):
    """Genera serie horaria de producción solar fotovoltaica con pvlib.

    Returns Series MW por hora.
    """
    try:
        import pvlib
        from pvlib import irradiance, pvsystem
        from pvlib.location import Location
    except ImportError:
        # Fallback: perfil sinusoidal aproximado
        ts = pd.to_datetime(timestamps, utc=True, errors="coerce")
        horas = ts.hour + ts.minute / 60.0
        sol_factor = np.maximum(0.0, np.sin((horas - 6) / 12 * np.pi))
        capacity_factor_anual = 0.20  # típico tropical
        return pd.Series(sol_factor * float(capacidad_solar_mw) * capacity_factor_anual * 2.0,
                         index=range(len(timestamps)))

    site = Location(latitude=float(lat), longitude=float(lon), altitude=float(altitud_m), tz="UTC")
    ts = pd.to_datetime(timestamps, utc=True, errors="coerce")
    if hasattr(ts, "dropna"):
        ts = ts.dropna()
    if len(ts) == 0:
        return pd.Series(dtype=float)

    solpos = site.get_solarposition(ts)
    clearsky = site.get_clearsky(ts, model="ineichen")
    poa = irradiance.get_total_irradiance(
        surface_tilt=float(tilt_deg),
        surface_azimuth=float(azimuth_deg),
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
        dni=clearsky["dni"],
        ghi=clearsky["ghi"],
        dhi=clearsky["dhi"],
    )
    # Aprox: producción AC = POA · capacidad · efficiency / 1000
    eficiencia = (1.0 - float(perdidas_pct) / 100.0)
    p_mw = poa["poa_global"] / 1000.0 * float(capacidad_solar_mw) * eficiencia
    return pd.Series(np.clip(p_mw.values, 0, capacidad_solar_mw), index=ts, name="P_solar_MW")


def combinar_eolico_solar(p_eolico_mw, p_solar_mw, capacidad_inyeccion_mw):
    """Suma eólico + solar, recorta a capacidad inyección.

    Returns dict con series y stats.
    """
    n = min(len(p_eolico_mw), len(p_solar_mw))
    p_e = np.asarray(p_eolico_mw[:n], dtype=float)
    p_s = np.asarray(p_solar_mw[:n], dtype=float)
    p_total = p_e + p_s
    p_inyectada = np.minimum(p_total, float(capacidad_inyeccion_mw))
    p_curtailed = np.maximum(0.0, p_total - float(capacidad_inyeccion_mw))

    return {
        "p_eolico_MW": p_e,
        "p_solar_MW": p_s,
        "p_total_MW": p_total,
        "p_inyectada_MW": p_inyectada,
        "p_curtailed_MW": p_curtailed,
        "energia_eolico_MWh": float(np.sum(p_e)),
        "energia_solar_MWh": float(np.sum(p_s)),
        "energia_inyectada_MWh": float(np.sum(p_inyectada)),
        "energia_curtailed_MWh": float(np.sum(p_curtailed)),
        "curtailment_pct": float(np.sum(p_curtailed) / np.sum(p_total) * 100.0) if np.sum(p_total) > 0 else 0,
    }


def dimensionar_solar_complemento(
    p_eolico_horario_mw, capacidad_inyeccion_mw, lat, lon,
    capacidad_solar_min_mw=1, capacidad_solar_max_mw=50, paso_mw=5,
    timestamps=None,
):
    """Sweep de capacidad solar → encuentra óptimo que maximiza energía inyectada
    sin generar curtailment excesivo.

    Returns DataFrame {capacidad_solar_mw, energia_inyectada, curtailment_pct}.
    """
    if timestamps is None:
        timestamps = pd.date_range("2024-01-01", periods=len(p_eolico_horario_mw), freq="h", tz="UTC")

    rows = []
    for cap_s in range(int(capacidad_solar_min_mw), int(capacidad_solar_max_mw) + 1, int(paso_mw)):
        p_solar = generar_perfil_solar_horario(timestamps, lat, lon, capacidad_solar_mw=cap_s)
        # Alinear longitudes
        n_min = min(len(p_eolico_horario_mw), len(p_solar))
        res = combinar_eolico_solar(p_eolico_horario_mw[:n_min], p_solar.values[:n_min], capacidad_inyeccion_mw)
        rows.append({
            "capacidad_solar_MW": cap_s,
            "energia_total_MWh": res["energia_eolico_MWh"] + res["energia_solar_MWh"],
            "energia_inyectada_MWh": res["energia_inyectada_MWh"],
            "energia_curtailed_MWh": res["energia_curtailed_MWh"],
            "curtailment_pct": res["curtailment_pct"],
        })
    return pd.DataFrame(rows)


def dimensionar_storage(
    serie_combinada_horaria,
    capacidad_inyeccion_mw,
    costo_bess_usd_kwh=300,
    profundidad_descarga_pct=80,
    eficiencia_round_trip_pct=88,
):
    """Dimensionado preliminar BESS para shifting:
       - Almacena curtailed excess → libera en horas pico precio.
       - Tamaño basado en energy excess máximo continuo.
    """
    arr = np.asarray(serie_combinada_horaria, dtype=float)
    excess = np.maximum(0.0, arr - float(capacidad_inyeccion_mw))
    # BESS capacity needed: max acumulado durante 4-8h shift típico
    if len(excess) >= 8:
        window = 8
        rolling = np.convolve(excess, np.ones(window), mode="valid")
        cap_kwh = float(np.max(rolling)) * 1000.0  # MWh → kWh
    else:
        cap_kwh = float(np.sum(excess)) * 1000.0
    cap_mwh = cap_kwh / 1000.0
    capex_bess = cap_kwh * float(costo_bess_usd_kwh)
    return {
        "capacidad_bess_MWh": cap_mwh,
        "capacidad_bess_kWh": cap_kwh,
        "capex_bess_usd": float(capex_bess),
        "profundidad_descarga_pct": float(profundidad_descarga_pct),
        "eficiencia_round_trip_pct": float(eficiencia_round_trip_pct),
        "energia_potencial_shift_anual_MWh": float(np.sum(excess) * float(eficiencia_round_trip_pct) / 100.0),
    }


def analizar_hibrido_completo(
    p_eolico_horario_mw, capacidad_inyeccion_mw, lat, lon,
    capacidad_solar_max_mw=50, timestamps=None,
    incluir_storage=True, costo_bess_usd_kwh=300,
):
    """Wrapper completo: sweep solar + dimensionado storage + recomendación."""
    sweep_df = dimensionar_solar_complemento(
        p_eolico_horario_mw, capacidad_inyeccion_mw, lat, lon,
        capacidad_solar_max_mw=capacidad_solar_max_mw,
        timestamps=timestamps,
    )
    if len(sweep_df) == 0:
        return {}

    # Recomendación: máxima energía inyectada con curtailment <10%
    eligible = sweep_df[sweep_df["curtailment_pct"] < 10]
    if len(eligible) > 0:
        recomendado = eligible.sort_values("energia_inyectada_MWh", ascending=False).iloc[0]
    else:
        recomendado = sweep_df.sort_values("energia_inyectada_MWh", ascending=False).iloc[0]

    storage_res = None
    if incluir_storage:
        cap_solar_opt = recomendado["capacidad_solar_MW"]
        ts_use = timestamps if timestamps is not None else pd.date_range("2024-01-01", periods=len(p_eolico_horario_mw), freq="h", tz="UTC")
        p_solar_opt = generar_perfil_solar_horario(ts_use, lat, lon, capacidad_solar_mw=cap_solar_opt)
        p_total_opt = np.asarray(p_eolico_horario_mw[:len(p_solar_opt)]) + np.asarray(p_solar_opt[:len(p_eolico_horario_mw)])
        storage_res = dimensionar_storage(p_total_opt, capacidad_inyeccion_mw, costo_bess_usd_kwh=costo_bess_usd_kwh)

    return {
        "sweep_solar": sweep_df,
        "recomendacion_solar_mw": float(recomendado["capacidad_solar_MW"]),
        "energia_inyectada_recomendada_MWh": float(recomendado["energia_inyectada_MWh"]),
        "curtailment_pct_recomendado": float(recomendado["curtailment_pct"]),
        "storage": storage_res,
    }
