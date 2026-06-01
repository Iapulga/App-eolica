"""IEC 61400-1 Ed.4 Site Suitability — V_ref, V_50, V_e1, V_e50, TI_eff, clase IEC.

Estimadores rapidos para uso en informe bankable. NO sustituyen el analisis
formal de site assessment con consultor certificado.

Referencias:
  - IEC 61400-1 Ed.4 (2019) sec 6 + 11
  - Tubino et al. (2014) — Estimacion V50 desde Weibull (Gumbel link)
  - Frandsen NTM ETM models

Clases IEC 61400-1 (Ed.4):
  ----------------------------------------------------------------
  Clase     V_ref(m/s)   V_ave(m/s)   V_e50(m/s)   V_e1(m/s)
  ----------------------------------------------------------------
  I         50.0         10.0         70.0         52.5
  II        42.5         8.5          59.5         44.6
  III       37.5         7.5          52.5         39.4
  S         segun especificacion del fabricante
  ----------------------------------------------------------------

Subcategoria turbulencia:
  A+ Iref = 0.18
  A  Iref = 0.16
  B  Iref = 0.14
  C  Iref = 0.12
"""

from __future__ import annotations

import math

IEC_CLASS_LIMITS = {
    "I":   {"V_ref": 50.0, "V_ave": 10.0, "V_e50": 70.0, "V_e1": 52.5},
    "II":  {"V_ref": 42.5, "V_ave":  8.5, "V_e50": 59.5, "V_e1": 44.6},
    "III": {"V_ref": 37.5, "V_ave":  7.5, "V_e50": 52.5, "V_e1": 39.4},
}

IEC_TURB_SUBCLASS = {
    "A+": 0.18,
    "A":  0.16,
    "B":  0.14,
    "C":  0.12,
}


def v_ave_from_weibull(k: float, c: float) -> float:
    """Velocidad media anual desde Weibull: V_ave = c * Gamma(1 + 1/k)."""
    try:
        return float(c) * math.gamma(1 + 1.0 / float(k))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def v_50_from_weibull(k: float, c: float, n_hours_year: float = 8760.0) -> float:
    """V_50 (vel maxima esperada en 50 anios) via inversion Weibull al 1/(50*N).

    Tasa de excedencia anual = 1/50. Probabilidad cero-cruce p = 1/(50*N).
    P(V > V_50) = exp(-(V_50/c)^k) = p
    => V_50 = c * (-ln p)^(1/k)
    """
    try:
        k_f = float(k); c_f = float(c)
        if k_f <= 0 or c_f <= 0:
            return 0.0
        p = 1.0 / (50.0 * n_hours_year)
        return c_f * (-math.log(p)) ** (1.0 / k_f)
    except (TypeError, ValueError):
        return 0.0


def v_ref_from_weibull(k: float, c: float) -> float:
    """V_ref (vel referencia 50 anios) — aprox por V_50 escalado para 10 min."""
    v50 = v_50_from_weibull(k, c)
    # Factor pico/horario ~ 1.4 conservador (DNV-ST-0437)
    return v50 * 1.4


def v_e50_from_weibull(k: float, c: float) -> float:
    """V_e50 ~ V_ref (vel extrema 50 anios en buje)."""
    return v_ref_from_weibull(k, c)


def v_e1_from_weibull(k: float, c: float) -> float:
    """V_e1 (extrema 1 anio) = 0.75 * V_e50 (IEC 61400-1 Ed.4 Eq.11)."""
    return 0.75 * v_e50_from_weibull(k, c)


def ti_eff_15(v_hub_mean: float, ti_obs_15: float, n_sectors_above_threshold: int = 1) -> float:
    """TI efectiva a 15 m/s (Frandsen simplificado).

    Si solo hay observacion media, TI_eff = TI_obs * factor (1.1 conservador).
    Para implementacion rigurosa usar Frandsen completo con wake-added turbulence.
    """
    try:
        return float(ti_obs_15) * 1.1
    except (TypeError, ValueError):
        return 0.0


def ti_sectorial_observada(df_horario, ws_col: str = "WS_ANALISIS", wd_col: str = "WD_USADA",
                            n_sectors: int = 16, v_target: float = 15.0, v_band: float = 1.0) -> dict:
    """TI observada por sector en una banda alrededor de v_target.

    Args:
        df_horario: DataFrame con velocidad ws_col y direccion wd_col.
        v_target: velocidad central (15 m/s standard IEC).
        v_band: ancho banda (+/- v_band).

    Returns:
        dict {sector_name: ti_obs}
    """
    try:
        import numpy as np
    except ImportError:
        return {}
    if df_horario is None or len(df_horario) == 0:
        return {}
    if ws_col not in df_horario.columns or wd_col not in df_horario.columns:
        return {}

    sector_names = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
    if n_sectors != 16:
        sector_names = [f"S{i+1}" for i in range(n_sectors)]

    width = 360.0 / n_sectors
    out = {}
    df = df_horario.dropna(subset=[ws_col, wd_col]).copy()
    df_band = df[(df[ws_col] >= v_target - v_band) & (df[ws_col] <= v_target + v_band)]
    if len(df_band) < 10:
        # fallback: usar toda la serie sin filtro de velocidad
        df_band = df
    for i, name in enumerate(sector_names):
        center = i * width
        low = (center - width / 2.0) % 360.0
        high = (center + width / 2.0) % 360.0
        if low < high:
            sub = df_band[(df_band[wd_col] >= low) & (df_band[wd_col] < high)]
        else:
            sub = df_band[(df_band[wd_col] >= low) | (df_band[wd_col] < high)]
        if len(sub) < 5:
            out[name] = float("nan")
            continue
        mean_v = float(sub[ws_col].mean())
        std_v = float(sub[ws_col].std())
        out[name] = (std_v / mean_v) if mean_v > 0 else float("nan")
    return out


def ti_eff_frandsen_full(ti_obs_sector: float, n_t_in_sector: int = 0, ct: float = 0.8, distance_D: float = 5.0) -> float:
    """TI efectiva Frandsen (IEC 61400-1 Ed.4 Eq.6.3.2.4).

    sigma_T_total^2 = sigma_T_ambient^2 + N * sigma_T_wake^2
    sigma_T_wake = 1 / (1.5 + 0.8 * dist/D / sqrt(ct))

    Returns:
        TI_eff total (decimal, ej 0.18 = 18%).
    """
    import math as _m
    try:
        ti = float(ti_obs_sector)
        if ti != ti:  # nan
            return float("nan")
    except (TypeError, ValueError):
        return float("nan")
    n_t = max(0, int(n_t_in_sector))
    ct_v = max(0.05, float(ct))
    dist_D = max(1.0, float(distance_D))
    sigma_wake = 1.0 / (1.5 + 0.8 * dist_D / _m.sqrt(ct_v))
    return _m.sqrt(ti ** 2 + n_t * sigma_wake ** 2)


def site_suitability_summary_from_sectorial(ti_sector_dict: dict, n_neighbors: int = 2, ct: float = 0.8, distance_D: float = 5.0) -> dict:
    """Agrega TI Frandsen total por sector + selecciona maximo."""
    out = {}
    for sec, ti_obs in (ti_sector_dict or {}).items():
        out[sec] = ti_eff_frandsen_full(ti_obs, n_t_in_sector=n_neighbors, ct=ct, distance_D=distance_D)
    ti_max = max((v for v in out.values() if v == v), default=float("nan"))
    return {
        "ti_eff_por_sector": out,
        "ti_eff_max": ti_max,
        "subclase_TI": assign_turb_subclass(ti_max) if ti_max == ti_max else "—",
    }


def assign_iec_class(v_ave: float, v_ref: float) -> str:
    """Asigna clase IEC mas adecuada por velocidades del sitio."""
    if v_ref <= IEC_CLASS_LIMITS["III"]["V_ref"] and v_ave <= IEC_CLASS_LIMITS["III"]["V_ave"]:
        return "III"
    if v_ref <= IEC_CLASS_LIMITS["II"]["V_ref"] and v_ave <= IEC_CLASS_LIMITS["II"]["V_ave"]:
        return "II"
    if v_ref <= IEC_CLASS_LIMITS["I"]["V_ref"] and v_ave <= IEC_CLASS_LIMITS["I"]["V_ave"]:
        return "I"
    return "S"


def assign_turb_subclass(ti_eff: float) -> str:
    """Asigna subclase TI por TI_eff(15)."""
    for subclass, iref in IEC_TURB_SUBCLASS.items():
        if ti_eff <= iref:
            return subclass
    return "S"


def site_suitability_summary(k_avg: float, c_avg: float, ti_eff: float = 0.16) -> dict:
    """Devuelve dict con todos los parametros IEC para el sitio.

    Estado de cumplimiento por clase: 'verde' si V_site <= V_class, 'rojo' si excede.
    """
    v_ave = v_ave_from_weibull(k_avg, c_avg)
    v_50 = v_50_from_weibull(k_avg, c_avg)
    v_ref = v_ref_from_weibull(k_avg, c_avg)
    v_e50 = v_e50_from_weibull(k_avg, c_avg)
    v_e1 = v_e1_from_weibull(k_avg, c_avg)

    clase = assign_iec_class(v_ave, v_ref)
    subclase_ti = assign_turb_subclass(ti_eff)
    cumple = clase in {"I", "II", "III"}

    result = {
        "V_ref (m/s)": v_ref,
        "V_50 (m/s)": v_50,
        "V_ave (m/s)": v_ave,
        "V_e1 (m/s)": v_e1,
        "V_e50 (m/s)": v_e50,
        "TI_eff(15)": ti_eff,
        "Clase IEC": clase,
        "Subclase TI": subclase_ti,
        "Cumple": "Si" if cumple else "Requiere clase S (specific design)",
    }
    for clase_id, limits in IEC_CLASS_LIMITS.items():
        for k, lim in limits.items():
            site_val = result.get(f"{k} (m/s)", 0.0)
            ok = site_val <= lim
            result[f"Clase {clase_id} — {k} (limite={lim})"] = "OK" if ok else "EXCEDE"
    return result


__all__ = [
    "IEC_CLASS_LIMITS",
    "IEC_TURB_SUBCLASS",
    "v_ave_from_weibull",
    "v_50_from_weibull",
    "v_ref_from_weibull",
    "v_e50_from_weibull",
    "v_e1_from_weibull",
    "ti_eff_15",
    "assign_iec_class",
    "assign_turb_subclass",
    "site_suitability_summary",
]
