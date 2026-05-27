"""Cold climate effects — icing detection + AEP derate (IEA Wind Task 19).

Estima horas/año con condiciones de hielo en palas y aplica derate AEP.
Útil para Andes (altitud >1500 m) o sitios con T < 0°C frecuente.

Criterios icing (simplificado IEA):
  - T_aire < 0°C
  - Humedad relativa > 90% (o presencia nubes/niebla, proxy: RH alta)
  - Velocidad viento > 3 m/s (para que hielo se acrete activamente)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEVERIDAD_ICING_DEFAULT = {
    "ligera": {"derate_aep_pct_durante_icing": 30, "factor_horas": 1.0,
               "descripcion": "Hielo ligero, recubrimiento parcial palas"},
    "moderada": {"derate_aep_pct_durante_icing": 60, "factor_horas": 1.0,
                 "descripcion": "Hielo moderado, derate significativo"},
    "severa": {"derate_aep_pct_durante_icing": 100, "factor_horas": 1.5,
               "descripcion": "Hielo severo + shutdown obligatorio + downtime extra"},
}


def estimar_horas_icing_anual(
    df_nasa,
    altitud_m=0.0,
    temperatura_umbral_c=0.0,
    rh_umbral_pct=90.0,
    ws_umbral_ms=3.0,
):
    """Cuenta horas con condiciones de icing en serie NASA POWER.

    Args:
      df_nasa: DataFrame con T2M (°C), WS50M (m/s). RH opcional.
      altitud_m: usado como proxy si T2M no disponible. T baja con altitud.
      temperatura_umbral_c, rh_umbral_pct, ws_umbral_ms: thresholds.

    Returns dict {horas_icing_anuales, fraccion_anio_pct, criterio_principal}.
    """
    if df_nasa is None or len(df_nasa) == 0:
        return {"horas_icing_anuales": 0, "fraccion_anio_pct": 0.0,
                "criterio_principal": "sin_datos", "n_total": 0}

    n_total = len(df_nasa)
    mask_T = None
    mask_RH = None
    mask_WS = None

    if "T2M" in df_nasa.columns:
        t = pd.to_numeric(df_nasa["T2M"], errors="coerce").to_numpy(dtype=float)
        # Si altitud > 0 y T2M no ajustado, aplicar lapse rate 6.5°C/km
        if altitud_m > 100:
            t = t - 0.0065 * float(altitud_m)
        mask_T = (t < float(temperatura_umbral_c)) & np.isfinite(t)
    else:
        # Fallback: estimar % horas frías por altitud (Andes muy alto)
        if altitud_m > 3000:
            frac_estimada = 0.30  # ~30% horas año <0°C
        elif altitud_m > 2000:
            frac_estimada = 0.15
        elif altitud_m > 1500:
            frac_estimada = 0.05
        else:
            frac_estimada = 0.0
        n_t_neg = int(frac_estimada * n_total)
        return {
            "horas_icing_anuales": int(n_t_neg * 0.5),  # 50% de las T<0 cumplen RH+WS
            "fraccion_anio_pct": float(n_t_neg * 0.5 / max(n_total, 1) * 100.0),
            "criterio_principal": "estimacion_altitud_T2M_ausente",
            "n_total": int(n_total),
        }

    if "RH2M" in df_nasa.columns:
        rh = pd.to_numeric(df_nasa["RH2M"], errors="coerce").to_numpy(dtype=float)
        mask_RH = (rh > float(rh_umbral_pct)) & np.isfinite(rh)
    else:
        # Sin RH → asumir 70% de horas frías cumplen RH (regla pulgar Andes)
        mask_RH = None

    if "WS50M" in df_nasa.columns:
        ws = pd.to_numeric(df_nasa["WS50M"], errors="coerce").to_numpy(dtype=float)
        mask_WS = (ws > float(ws_umbral_ms)) & np.isfinite(ws)
    else:
        mask_WS = np.ones(n_total, dtype=bool)

    # AND logic
    mask = mask_T & mask_WS
    if mask_RH is not None:
        mask = mask & mask_RH
        criterio = "T2M + WS50M + RH2M"
    else:
        # Aplicar factor 0.7 para compensar ausencia RH
        n_icing_raw = int(np.sum(mask))
        n_icing = int(n_icing_raw * 0.7)
        return {
            "horas_icing_anuales": n_icing,
            "fraccion_anio_pct": float(n_icing / max(n_total, 1) * 100.0),
            "criterio_principal": "T2M + WS50M (RH estimada)",
            "n_total": int(n_total),
        }

    n_icing = int(np.sum(mask))
    return {
        "horas_icing_anuales": n_icing,
        "fraccion_anio_pct": float(n_icing / max(n_total, 1) * 100.0),
        "criterio_principal": criterio,
        "n_total": int(n_total),
    }


def calcular_derate_icing(horas_icing_anuales, aep_neta_total_mwh, severidad="moderada"):
    """Aplica derate AEP por horas icing.

    Args:
      horas_icing_anuales: horas con condiciones icing (de estimar_horas_icing_anual)
      aep_neta_total_mwh: AEP base sin derate icing
      severidad: ligera | moderada | severa

    Returns dict con AEP corregida + estadísticas.
    """
    config = SEVERIDAD_ICING_DEFAULT.get(severidad, SEVERIDAD_ICING_DEFAULT["moderada"])
    horas_efectivas = float(horas_icing_anuales) * config["factor_horas"]
    fraccion_horas = min(1.0, horas_efectivas / 8760.0)
    derate_pct = config["derate_aep_pct_durante_icing"] / 100.0
    perdida_aep_pct = fraccion_horas * derate_pct * 100.0
    aep_perdida_mwh = float(aep_neta_total_mwh) * perdida_aep_pct / 100.0
    aep_corregida = float(aep_neta_total_mwh) - aep_perdida_mwh
    return {
        "severidad": severidad,
        "horas_icing_anuales": int(horas_icing_anuales),
        "horas_efectivas_inc_shutdown": float(horas_efectivas),
        "perdida_aep_pct": float(perdida_aep_pct),
        "aep_perdida_mwh": float(aep_perdida_mwh),
        "aep_corregida_mwh": float(aep_corregida),
        "descripcion": config["descripcion"],
    }


def analizar_cold_climate_completo(df_nasa, aep_neta_total_mwh, altitud_m=0.0, severidad="moderada"):
    """Wrapper alto nivel: detecta icing + aplica derate."""
    if altitud_m < 1500:
        # Sitios baja altitud Colombia (Guajira) → icing irrelevante
        return {
            "aplica": False,
            "razon": "Altitud < 1500 m, icing irrelevante para sitios tropicales LATAM.",
            "horas_icing_anuales": 0,
            "aep_corregida_mwh": float(aep_neta_total_mwh),
        }

    icing_res = estimar_horas_icing_anual(df_nasa, altitud_m=altitud_m)
    derate_res = calcular_derate_icing(
        icing_res["horas_icing_anuales"],
        aep_neta_total_mwh,
        severidad=severidad,
    )

    return {
        "aplica": True,
        "icing": icing_res,
        "derate": derate_res,
        "aep_corregida_mwh": derate_res["aep_corregida_mwh"],
        "altitud_m": float(altitud_m),
    }
