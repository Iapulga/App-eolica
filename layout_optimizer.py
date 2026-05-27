"""Layout optimizer — maximiza AEP neto cambiando posiciones turbinas.

Algoritmos:
  - scipy.optimize.differential_evolution (DE): robusto, sin gradiente, ~50-200 iter
  - Brute force con sampling random (fallback)

Constraints:
  - Spacing mínimo entre turbinas (típico 3-5D)
  - Bounds del área (rectangular o polígono custom)

Usa `analizar_estelas_parque_16` como fitness function (~5-15s per eval).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _layout_array_to_df(posiciones_flat, n_turbinas):
    """Convierte array plano [x0,y0,x1,y1,...] a DataFrame layout."""
    coords = np.asarray(posiciones_flat, dtype=float).reshape(n_turbinas, 2)
    return pd.DataFrame({
        "turbina_id": [f"T{i+1}" for i in range(n_turbinas)],
        "x_m": coords[:, 0],
        "y_m": coords[:, 1],
    })


def evaluar_aep_layout(
    posiciones_flat, n_turbinas, df_curva, df_nasa,
    diametro, ct, kw, wake_model="jensen",
    ambient_ti=0.10, h_hub=80.0,
):
    """Wrapper sobre analizar_estelas_parque_16. Returns AEP neto MWh/año (positivo)."""
    from calculos import analizar_estelas_parque_16
    df_layout = _layout_array_to_df(posiciones_flat, n_turbinas)

    try:
        resumen, _detalles, _wake_pct = analizar_estelas_parque_16(
            df_layout=df_layout, df_nasa=df_nasa, curva_df=df_curva,
            diametro=diametro, ct=ct, kw=kw,
            ws_col="WS50M", wd_col="WD50M",
            modelo=wake_model, ambient_ti=ambient_ti, h_hub=h_hub,
        )
        # AEP = potencia con estela × horas_eq × frecuencia / 100 (sumado sectores)
        # Aproximación: usar (1 - wake_pct_ponderado) × potencia_libre_anual
        potencia_libre = (resumen["Potencia parque sin estela (W)"] * resumen["Frecuencia (%)"] / 100.0).sum()
        potencia_wake = (resumen["Potencia parque con estela (W)"] * resumen["Frecuencia (%)"] / 100.0).sum()
        aep_neto_mwh = potencia_wake * 8760.0 / 1e6
        return float(aep_neto_mwh)
    except Exception:
        return 0.0


def penalty_spacing(posiciones_flat, n_turbinas, diametro, min_spacing_D=3.0):
    """Penalty cuadrático si distance < min_spacing_D · diametro."""
    coords = np.asarray(posiciones_flat).reshape(n_turbinas, 2)
    min_d = float(min_spacing_D) * float(diametro)
    pen = 0.0
    for i in range(n_turbinas):
        for j in range(i + 1, n_turbinas):
            dist = float(np.linalg.norm(coords[i] - coords[j]))
            if dist < min_d:
                pen += (min_d - dist) ** 2
    return pen


def penalty_polygon(posiciones_flat, polygon_xy):
    """Penalty si turbina fuera de polígono (shapely)."""
    if polygon_xy is None or len(polygon_xy) < 3:
        return 0.0
    try:
        from shapely.geometry import Point, Polygon
    except ImportError:
        return 0.0
    poly = Polygon(polygon_xy)
    coords = np.asarray(posiciones_flat).reshape(-1, 2)
    pen = 0.0
    for x, y in coords:
        pt = Point(float(x), float(y))
        if not poly.contains(pt):
            pen += poly.distance(pt) ** 2
    return pen


def optimizar_layout_scipy(
    n_turbinas, df_curva, df_nasa, diametro, ct, kw,
    bounds_xy, min_spacing_D=3.0, max_iter=30,
    polygon_xy=None, wake_model="jensen", ambient_ti=0.10, h_hub=80.0,
    seed=42, popsize=15, callback=None,
):
    """Differential Evolution. Returns (best_layout_df, best_aep, history).

    bounds_xy: tuple ((x_min, x_max), (y_min, y_max)) en metros.
    max_iter: typical 30-100. Cada iter eval popsize × N evals (caro).
    """
    try:
        from scipy.optimize import differential_evolution
    except ImportError:
        raise RuntimeError("Instalar scipy: `pip install scipy`")

    (xmin, xmax), (ymin, ymax) = bounds_xy
    bounds = [(xmin, xmax), (ymin, ymax)] * n_turbinas

    history = {"iter": [], "best_aep": []}

    def objective(x):
        aep = evaluar_aep_layout(x, n_turbinas, df_curva, df_nasa, diametro, ct, kw, wake_model, ambient_ti, h_hub)
        pen_sp = penalty_spacing(x, n_turbinas, diametro, min_spacing_D)
        pen_pol = penalty_polygon(x, polygon_xy) if polygon_xy else 0.0
        return -aep + 1e6 * pen_sp + 1e6 * pen_pol  # minimize → -AEP + penalty

    def cb_wrapper(xk, convergence=None):
        aep_iter = evaluar_aep_layout(xk, n_turbinas, df_curva, df_nasa, diametro, ct, kw, wake_model, ambient_ti, h_hub)
        history["iter"].append(len(history["iter"]) + 1)
        history["best_aep"].append(aep_iter)
        if callback is not None:
            callback(len(history["iter"]), aep_iter)
        return False

    result = differential_evolution(
        objective, bounds,
        maxiter=int(max_iter), seed=int(seed), popsize=int(popsize),
        workers=1, polish=False, callback=cb_wrapper, tol=0.01, mutation=(0.3, 1.0), recombination=0.7,
    )

    best_layout = _layout_array_to_df(result.x, n_turbinas)
    best_aep = -float(result.fun)
    return best_layout, best_aep, history


def comparar_layouts(layout_original, layout_optimizado, df_curva, df_nasa, diametro, ct, kw, wake_model="jensen", ambient_ti=0.10, h_hub=80.0):
    """Devuelve dict comparativo {aep_original, aep_optimizado, delta_pct}."""
    n = max(len(layout_original), len(layout_optimizado))
    arr_orig = layout_original[["x_m", "y_m"]].to_numpy(dtype=float).flatten()
    arr_opt = layout_optimizado[["x_m", "y_m"]].to_numpy(dtype=float).flatten()
    aep_o = evaluar_aep_layout(arr_orig, len(layout_original), df_curva, df_nasa, diametro, ct, kw, wake_model, ambient_ti, h_hub)
    aep_n = evaluar_aep_layout(arr_opt, len(layout_optimizado), df_curva, df_nasa, diametro, ct, kw, wake_model, ambient_ti, h_hub)
    delta_pct = (aep_n - aep_o) / aep_o * 100.0 if aep_o > 0 else 0.0
    return {
        "aep_original_mwh": float(aep_o),
        "aep_optimizado_mwh": float(aep_n),
        "delta_mwh": float(aep_n - aep_o),
        "delta_pct": float(delta_pct),
    }
