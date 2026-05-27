"""Grid integration + curtailment dinámico.

Simula constraints reales de red eléctrica:
  1. Curtailment técnico (capacidad inyección STN/SDL limitada)
  2. Curtailment económico (precio bolsa < CV → no inyectar)
  3. Disponibilidad de red (downtime ~2-5% típico)
  4. Servicios auxiliares (AGC reserva, regulación frecuencia)

Datos Colombia:
  - XM precio bolsa horario: público (CSV)
  - UPME capacidad transmisión por zona STN
  - CREG cargo confiabilidad
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def aplicar_curtailment_capacity_constraint(
    df_aep_horario,
    capacidad_max_inyeccion_mw,
    col_potencia_mw="potencia_parque_MW",
):
    """Si potencia horaria > capacidad → recortar diferencia.

    df_aep_horario debe tener col_potencia_mw (potencia parque en MW).
    Returns DataFrame con columnas adicionales:
      potencia_inyectada_mw, energia_recortada_mwh, curtailed_capacity (bool).
    """
    df = df_aep_horario.copy()
    p_max = float(capacidad_max_inyeccion_mw)
    p_orig = pd.to_numeric(df[col_potencia_mw], errors="coerce").to_numpy(dtype=float)

    p_inj = np.minimum(p_orig, p_max)
    p_curt = np.maximum(0.0, p_orig - p_max)

    df["potencia_inyectada_MW"] = p_inj
    df["energia_recortada_capacity_MWh"] = p_curt  # asume 1 hora paso
    df["curtailed_capacity"] = p_curt > 0
    return df


def simular_curtailment_economico(
    df_aep_horario,
    df_precio_bolsa_horario=None,
    costo_variable_usd_mwh=5.0,
    col_potencia_mw="potencia_inyectada_MW",
):
    """Si precio bolsa < costo variable → no inyectar (curtailment económico).

    df_precio_bolsa_horario: DataFrame con {timestamp, precio_usd_mwh}.
    Si None → simula con precio aleatorio mean 50 ± 30.
    """
    df = df_aep_horario.copy()
    n = len(df)

    if df_precio_bolsa_horario is None or len(df_precio_bolsa_horario) == 0:
        # Genera serie simulada
        rng = np.random.default_rng(42)
        precio = rng.lognormal(np.log(45), 0.5, n)
    else:
        # Merge por timestamp
        if "timestamp" in df.columns and "timestamp" in df_precio_bolsa_horario.columns:
            df_merge = df.merge(df_precio_bolsa_horario[["timestamp", "precio_usd_mwh"]], on="timestamp", how="left")
            precio = pd.to_numeric(df_merge["precio_usd_mwh"], errors="coerce").to_numpy(dtype=float)
            precio = np.where(np.isfinite(precio), precio, 50.0)
        else:
            precio = np.full(n, 50.0)

    df["precio_bolsa_usd_mwh"] = precio
    mask_eco_curt = precio < float(costo_variable_usd_mwh)
    p_orig = pd.to_numeric(df[col_potencia_mw], errors="coerce").to_numpy(dtype=float)
    df["energia_recortada_economica_MWh"] = np.where(mask_eco_curt, p_orig, 0.0)
    df["potencia_neta_inyectada_MW"] = np.where(mask_eco_curt, 0.0, p_orig)
    df["curtailed_economico"] = mask_eco_curt
    df["ingreso_horario_usd"] = df["potencia_neta_inyectada_MW"] * df["precio_bolsa_usd_mwh"]

    return df


def estimar_servicios_auxiliares(
    potencia_nominal_mw,
    factor_reserva_agc_pct=5.0,
    precio_reserva_usd_mw_dia=8.0,
    horas_disponibles_anual=8400,
):
    """Estimación ingreso por servicios auxiliares AGC/regulación frecuencia.
    Valores típicos CREG/XM Colombia (estimación, varía cada subasta).
    """
    reserva_mw = float(potencia_nominal_mw) * float(factor_reserva_agc_pct) / 100.0
    dias = horas_disponibles_anual / 24.0
    ingreso_anual = reserva_mw * float(precio_reserva_usd_mw_dia) * dias
    return {
        "reserva_mw_disponible": float(reserva_mw),
        "dias_disponibles": float(dias),
        "ingreso_anual_usd": float(ingreso_anual),
        "ingreso_usd_mwh_inyectado": float(ingreso_anual / (potencia_nominal_mw * 8000)) if potencia_nominal_mw > 0 else 0.0,
    }


def construir_serie_curtailment_completa(
    df_aep_horario,
    capacidad_inyeccion_mw,
    df_precio_bolsa=None,
    costo_variable_usd_mwh=5.0,
    factor_disponibilidad_red_pct=98.0,
    col_potencia_mw="potencia_parque_MW",
):
    """Wrapper completo: aplica curtailment técnico + económico + downtime red.

    Returns DataFrame con todas las series + KPIs en attributes.
    """
    df = df_aep_horario.copy()
    n_total = len(df)

    # 1. Capacidad técnica
    df = aplicar_curtailment_capacity_constraint(df, capacidad_inyeccion_mw, col_potencia_mw)

    # 2. Económico
    df = simular_curtailment_economico(df, df_precio_bolsa, costo_variable_usd_mwh, col_potencia_mw="potencia_inyectada_MW")

    # 3. Downtime red (disponibilidad de red)
    disp = float(factor_disponibilidad_red_pct) / 100.0
    rng = np.random.default_rng(123)
    mask_red_down = rng.random(n_total) > disp
    df["red_disponible"] = ~mask_red_down
    p_neta = pd.to_numeric(df["potencia_neta_inyectada_MW"], errors="coerce").to_numpy(dtype=float)
    df["potencia_final_MW"] = np.where(mask_red_down, 0.0, p_neta)
    df["energia_recortada_downtime_MWh"] = np.where(mask_red_down, p_neta, 0.0)

    return df


def calcular_kpis_curtailment(df_curtailment):
    """Resumen KPIs del análisis curtailment."""
    if df_curtailment is None or len(df_curtailment) == 0:
        return {}

    total_e_bruta = float(pd.to_numeric(df_curtailment.get("potencia_parque_MW"), errors="coerce").sum())
    e_capacity = float(pd.to_numeric(df_curtailment.get("energia_recortada_capacity_MWh", 0), errors="coerce").sum())
    e_eco = float(pd.to_numeric(df_curtailment.get("energia_recortada_economica_MWh", 0), errors="coerce").sum())
    e_downtime = float(pd.to_numeric(df_curtailment.get("energia_recortada_downtime_MWh", 0), errors="coerce").sum())
    e_final = float(pd.to_numeric(df_curtailment.get("potencia_final_MW", 0), errors="coerce").sum())

    ingreso = float(pd.to_numeric(df_curtailment.get("ingreso_horario_usd", 0), errors="coerce").sum())

    return {
        "energia_bruta_MWh": total_e_bruta,
        "energia_final_inyectada_MWh": e_final,
        "energia_recortada_total_MWh": e_capacity + e_eco + e_downtime,
        "pct_recorte_capacity": (e_capacity / total_e_bruta * 100.0) if total_e_bruta > 0 else 0,
        "pct_recorte_economico": (e_eco / total_e_bruta * 100.0) if total_e_bruta > 0 else 0,
        "pct_recorte_downtime": (e_downtime / total_e_bruta * 100.0) if total_e_bruta > 0 else 0,
        "pct_recorte_total": ((e_capacity + e_eco + e_downtime) / total_e_bruta * 100.0) if total_e_bruta > 0 else 0,
        "ingreso_total_usd": ingreso,
        "horas_curtailed_capacity": int(df_curtailment["curtailed_capacity"].sum() if "curtailed_capacity" in df_curtailment else 0),
        "horas_curtailed_economico": int(df_curtailment["curtailed_economico"].sum() if "curtailed_economico" in df_curtailment else 0),
    }
