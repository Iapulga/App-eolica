"""Inter-Annual Variability (IAV) — desviacion AEP entre anios.

Estima sigma_lt (long-term uncertainty IEC 61400-15-2 cat B) de forma robusta:
    sigma_lt_pct = IAV_pct / sqrt(N_anios)

donde IAV_pct = std(AEP_anual) / mean(AEP_anual) * 100.

Sirve para reemplazar default conservador 4.5% en `calculos_uncertainty`
cuando hay serie horaria multi-anio disponible (ej. NASA POWER 5+ anios).
"""

from __future__ import annotations

import math

try:
    import numpy as np
    import pandas as pd
except ImportError:
    np = None
    pd = None


def split_aep_by_year(df_horario, ws_col: str, power_curve_fn=None, hours_per_year_default: int = 8760) -> dict:
    """Calcula AEP por anio usando curva de potencia + serie horaria.

    Args:
        df_horario: DataFrame con DatetimeIndex y columna ws_col (m/s).
        ws_col: nombre columna velocidad (ej 'WS_ANALISIS').
        power_curve_fn: callable v_ms -> P_W. Si None usa formula simple.
        hours_per_year_default: solo para fallback.

    Returns:
        dict {anio: aep_mwh}
    """
    if pd is None or df_horario is None or len(df_horario) == 0:
        return {}
    if ws_col not in df_horario.columns:
        return {}

    df = df_horario.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        return {}

    if power_curve_fn is None:
        # fallback simplificado: P = 0.5 * rho * A * Cp * v^3, Cp=0.4 area=6000m2 rho=1.22
        def power_curve_fn(v):  # noqa
            v = float(v)
            if v < 3.0 or v > 25.0:
                return 0.0
            return min(0.5 * 1.22 * 6000.0 * 0.4 * v ** 3, 2_000_000.0)

    df["P_W"] = df[ws_col].apply(power_curve_fn)
    # MWh por hora-energia
    df["E_MWh"] = df["P_W"] / 1e6
    by_year = df.groupby(df.index.year)["E_MWh"].sum().to_dict()
    return {int(y): float(v) for y, v in by_year.items()}


def iav_pct(aep_per_year: dict | list) -> float:
    """IAV = std / mean * 100. Robusto a dict {anio:aep} o list[float]."""
    if isinstance(aep_per_year, dict):
        vals = list(aep_per_year.values())
    else:
        vals = list(aep_per_year)
    vals = [float(v) for v in vals if v is not None and v == v and v > 0]
    if len(vals) < 2:
        return float("nan")
    mean_v = sum(vals) / len(vals)
    if mean_v <= 0:
        return float("nan")
    var = sum((v - mean_v) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(var) / mean_v * 100.0


def sigma_lt_from_iav(iav: float, n_years: int) -> float:
    """sigma_lt_pct = IAV / sqrt(N) — error estandar del promedio long-term."""
    if iav is None or not math.isfinite(iav) or n_years <= 0:
        return float("nan")
    return float(iav) / math.sqrt(float(n_years))


def iav_summary(df_horario, ws_col: str, power_curve_fn=None) -> dict:
    """Wrapper: devuelve dict con aep_por_anio, IAV%, sigma_lt%, n_years."""
    by_year = split_aep_by_year(df_horario, ws_col, power_curve_fn)
    iav = iav_pct(by_year)
    n = len([v for v in by_year.values() if v and v > 0])
    sigma_lt = sigma_lt_from_iav(iav, n) if n > 0 else float("nan")
    return {
        "aep_per_year_mwh": by_year,
        "n_years": n,
        "iav_pct": iav,
        "sigma_lt_pct": sigma_lt,
        "mean_aep_mwh": (sum(by_year.values()) / n) if n > 0 else float("nan"),
    }


__all__ = [
    "split_aep_by_year",
    "iav_pct",
    "sigma_lt_from_iav",
    "iav_summary",
]
