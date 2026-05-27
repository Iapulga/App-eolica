"""Ruido ambiental — propagación según ISO 9613-2 (simplificada).

Componentes:
  - Atenuación geométrica (spherical divergence): Adiv = 20·log10(d) + 11
  - Atenuación atmosférica (ISO 9613-1): Aatm = α·d (función T, RH, frecuencia)
  - Atenuación suelo (ISO 9613-2): Agr simplificada
  - Corrección meteorológica (favorable conditions): Cmet = 0 (peor caso)

Output: LpA por receptor en dB(A). Estándar comparado con límite legal:
  - Diurno residencial: típico 50-55 dB(A)
  - Nocturno residencial: típico 40-45 dB(A)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calcular_atenuacion_geometrica(distancia_m):
    """Adiv = 20·log10(d) + 11 (radiación esférica desde fuente puntual)."""
    d = np.asarray(distancia_m, dtype=float)
    d_safe = np.maximum(d, 1.0)
    return 20.0 * np.log10(d_safe) + 11.0


def _coef_absorcion_atmosferica(frecuencia_hz, temperatura_c, humedad_pct, presion_kpa=101.325):
    """Coeficiente α (dB/km) según ISO 9613-1, banda de frecuencia.

    Fórmula simplificada para banda 500 Hz (dominante en turbinas eólicas).
    """
    T_K = float(temperatura_c) + 273.15
    T_ref = 293.15
    T_01 = 273.16
    p_a = float(presion_kpa) * 1000.0
    p_r = 101325.0
    rh = max(0.1, min(100.0, float(humedad_pct))) / 100.0

    # Presión saturación vapor (Antoine simplificado)
    p_sat = 10.79586 * (1 - T_01/T_K) - 5.02808 * np.log10(T_K/T_01)
    p_sat = 10.0 ** p_sat * 101.325 * 10  # Pa
    h = rh * p_sat / p_a * 100.0  # fracción molar % de agua

    # Relaxation frequencies
    fro = (p_a / p_r) * (24.0 + 4.04e4 * h * (0.02 + h) / (0.391 + h))  # oxygen
    frn = (p_a / p_r) * (T_K / T_ref) ** -0.5 * (9.0 + 280.0 * h * np.exp(-4.170 * ((T_K / T_ref) ** (-1/3) - 1)))  # nitrogen

    f = float(frecuencia_hz)
    alpha = 8.686 * f * f * (
        1.84e-11 * (p_r / p_a) * (T_K / T_ref) ** 0.5
        + (T_K / T_ref) ** -2.5 * (
            0.01275 * np.exp(-2239.1 / T_K) / (fro + f * f / fro)
            + 0.1068 * np.exp(-3352.0 / T_K) / (frn + f * f / frn)
        )
    )  # dB/m
    return alpha * 1000.0  # dB/km


def calcular_atenuacion_atmosferica(distancia_m, temperatura_c=15.0, humedad_pct=70.0, frecuencia_hz=500.0):
    """Aatm = α(f, T, RH) · d. Resultado en dB."""
    alpha_db_km = _coef_absorcion_atmosferica(frecuencia_hz, temperatura_c, humedad_pct)
    return float(alpha_db_km) * (np.asarray(distancia_m, dtype=float) / 1000.0)


def calcular_atenuacion_suelo(distancia_m, altura_emisor_m=80.0, altura_receptor_m=1.5, tipo_suelo="poroso"):
    """ISO 9613-2 Agr — suelo poroso (G=1) vs duro (G=0). Simplificación.

    Para frecuencia 500 Hz tipo turbinas:
    """
    d = np.asarray(distancia_m, dtype=float)
    hm = (float(altura_emisor_m) + float(altura_receptor_m)) / 2.0
    G = 1.0 if tipo_suelo == "poroso" else 0.0
    # Simplificación para banda media (ISO 9613-2 Eq. 7)
    # Agr_500 = 4.8 - (2·hm/d)·(17 + 300/d)  pero clamped >= 0 y minimum -3 dB
    # Para grandes d, A_gr → -3·G (negativo = atenuación adicional)
    base = 4.8 - (2.0 * hm / np.maximum(d, 1.0)) * (17.0 + 300.0 / np.maximum(d, 1.0))
    Agr = np.where(base > 0, base * (1.0 - G), -3.0 * G * np.ones_like(d))
    return Agr


def calcular_LpA_receptor(
    turbinas_xy, lwa_por_turbina_db, receptor_xy,
    altura_emisor=80.0, altura_receptor=1.5,
    temperatura_c=20.0, humedad_pct=70.0,
    frecuencia_hz=500.0, tipo_suelo="poroso",
    cmet_db=0.0,
):
    """LpA total en receptor por suma logarítmica.

    Args:
      turbinas_xy: list of (x, y) o array Nx2.
      lwa_por_turbina_db: float o array N. Sound power level dB(A). Típico turbina 3MW = 105-108.
      receptor_xy: tuple (x, y).
    Returns: dict con lpA_total + contribucion_por_turbina.
    """
    turbinas = np.asarray(turbinas_xy, dtype=float)
    if turbinas.ndim == 1:
        turbinas = turbinas.reshape(1, -1)
    n = len(turbinas)
    if isinstance(lwa_por_turbina_db, (int, float)):
        lwa_arr = np.full(n, float(lwa_por_turbina_db))
    else:
        lwa_arr = np.asarray(lwa_por_turbina_db, dtype=float)

    rx, ry = float(receptor_xy[0]), float(receptor_xy[1])

    dx = turbinas[:, 0] - rx
    dy = turbinas[:, 1] - ry
    dz = altura_emisor - altura_receptor
    d3 = np.sqrt(dx * dx + dy * dy + dz * dz)

    adiv = calcular_atenuacion_geometrica(d3)
    aatm = calcular_atenuacion_atmosferica(d3, temperatura_c, humedad_pct, frecuencia_hz)
    agr = calcular_atenuacion_suelo(d3, altura_emisor, altura_receptor, tipo_suelo)

    lp_i = lwa_arr - adiv - aatm - agr + float(cmet_db)
    # Suma energética: Lp_total = 10·log10(sum(10^(Lp_i/10)))
    lp_linear = 10.0 ** (lp_i / 10.0)
    lp_total = 10.0 * np.log10(np.sum(lp_linear)) if np.sum(lp_linear) > 0 else float("-inf")

    return {
        "lpA_total_db": float(lp_total),
        "contribuciones_db": lp_i.tolist(),
        "distancias_m": d3.tolist(),
        "adiv_db": adiv.tolist(),
        "aatm_db": aatm.tolist() if hasattr(aatm, "tolist") else [float(aatm)] * n,
        "agr_db": agr.tolist() if hasattr(agr, "tolist") else [float(agr)] * n,
    }


def calcular_LpA_receptores(
    df_layout, lwa_db, receptores,
    altura_emisor=80.0, altura_receptor=1.5,
    temperatura_c=20.0, humedad_pct=70.0,
    limite_diurno_db=50.0, limite_nocturno_db=40.0,
):
    """Para lista de receptores: tabla LpA + cumple/excede límites."""
    if df_layout is None or len(df_layout) == 0:
        return pd.DataFrame()

    turbinas = df_layout[["x_m", "y_m"]].to_numpy(dtype=float)
    n_turb = len(turbinas)
    lwa_arr = lwa_db if hasattr(lwa_db, "__len__") else [lwa_db] * n_turb

    rows = []
    for rec in receptores:
        rid = rec.get("receptor_id", "R?")
        nombre = rec.get("nombre", rid)
        rx = float(rec.get("x_m", 0.0))
        ry = float(rec.get("y_m", 0.0))
        res = calcular_LpA_receptor(
            turbinas, lwa_arr, (rx, ry),
            altura_emisor, altura_receptor, temperatura_c, humedad_pct,
        )
        lp = res["lpA_total_db"]
        rows.append({
            "receptor_id": rid,
            "nombre": nombre,
            "x_m": rx,
            "y_m": ry,
            "lpA_db": float(lp),
            "cumple_diurno": bool(lp <= limite_diurno_db),
            "cumple_nocturno": bool(lp <= limite_nocturno_db),
            "distancia_min_m": float(min(res["distancias_m"])),
        })

    return pd.DataFrame(rows)


def crear_mapa_ruido_grid(
    df_layout, lwa_db,
    grid_extent_m=2000, grid_resolution=30,
    altura_emisor=80.0, altura_receptor=1.5,
    temperatura_c=20.0, humedad_pct=70.0,
):
    """Genera grid de receptores virtuales → heatmap LpA."""
    xs = np.linspace(-grid_extent_m, grid_extent_m, grid_resolution)
    ys = np.linspace(-grid_extent_m, grid_extent_m, grid_resolution)
    receptores = []
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            receptores.append({"receptor_id": f"G{i}_{j}", "nombre": "", "x_m": float(x), "y_m": float(y)})
    return calcular_LpA_receptores(df_layout, lwa_db, receptores, altura_emisor, altura_receptor, temperatura_c, humedad_pct)
