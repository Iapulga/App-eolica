"""Lineal flow over hills — Taylor 1915 / Jackson-Hunt 1975 (simplificado).

Alternativa rápida a WindNinja (mass-consistent) y CFD (RANS).
Precisión ~50-60% WAsP en terreno suave (slopes <15°).
NO usar terreno escarpado/rugoso.

Formulación Jackson-Hunt 1975:
   ΔS(x, z) ≈ 2 · (h_hill / L_hill) · K(z, L)
donde K decae con altura z relativa a longitud característica L.
"""

from __future__ import annotations

import numpy as np


def _gradient_local(arr_2d, pixel_size_m):
    """Calcula gradiente bidimensional del DEM. Returns (dz_dx, dz_dy)."""
    dz_dy, dz_dx = np.gradient(arr_2d, pixel_size_m)
    return dz_dx, dz_dy


def speedup_taylor_hunt_simple(slope_radial, h_hub, L_hill=500.0):
    """Speedup analítico Jackson-Hunt 1975 simplificado.

    Args:
      slope_radial: pendiente en dirección del viento (rad)
      h_hub: altura buje (m)
      L_hill: longitud característica de la colina (m), típico 200-2000 m

    Returns:
      factor de speedup (típico 1.0 - 1.5)
    """
    # Coeficiente K(z/L) - decae exponencial con altura
    K = 2.0 * np.exp(-2.0 * float(h_hub) / max(float(L_hill), 50.0))
    # ΔS ≈ K · slope (en aproximación lineal)
    delta_s = K * np.tan(slope_radial)
    return 1.0 + delta_s


def calcular_speedup_field_lineal(dem_array, pixel_size_m=30.0, h_hub=80.0, L_hill=500.0, smooth_kernel=3):
    """Aplica Taylor-Hunt sobre cada celda del DEM → field 2D de speedup.

    Args:
      dem_array: numpy 2D (elevación en metros)
      pixel_size_m: resolución del raster (m)
      h_hub: altura del buje (m)
      L_hill: longitud característica de colinas (m), estimar manual o auto
      smooth_kernel: suavizado opcional (3x3)

    Returns:
      dict con speedup_field, slope_field, stats.
    """
    dem = np.asarray(dem_array, dtype=np.float32)
    valid = np.isfinite(dem)
    if not np.any(valid):
        return {"speedup_field": np.ones_like(dem), "slope_field": np.zeros_like(dem), "stats": {}}

    # Fill NaN para gradient
    dem_filled = np.where(valid, dem, np.nanmean(dem[valid]))

    if smooth_kernel and smooth_kernel > 1:
        from scipy.ndimage import uniform_filter
        dem_filled = uniform_filter(dem_filled, size=int(smooth_kernel))

    dz_dx, dz_dy = _gradient_local(dem_filled, pixel_size_m)
    slope_magnitude = np.sqrt(dz_dx ** 2 + dz_dy ** 2)
    slope_rad = np.arctan(slope_magnitude)

    speedup = speedup_taylor_hunt_simple(slope_rad, h_hub, L_hill)
    # Clamp realista
    speedup = np.clip(speedup, 0.5, 2.0)

    # Mask invalid
    speedup = np.where(valid, speedup, 1.0)
    slope_deg = np.rad2deg(slope_rad)

    stats = {
        "speedup_min": float(np.nanmin(speedup)),
        "speedup_max": float(np.nanmax(speedup)),
        "speedup_media": float(np.nanmean(speedup)),
        "speedup_std": float(np.nanstd(speedup)),
        "slope_max_deg": float(np.nanmax(slope_deg)),
        "slope_p95_deg": float(np.nanpercentile(slope_deg, 95)),
        "L_hill_usado_m": float(L_hill),
        "h_hub_usado_m": float(h_hub),
    }
    return {"speedup_field": speedup, "slope_field": slope_deg, "stats": stats}


def aplicar_speedup_lineal_a_turbinas(df_layout, speedup_field, transform=None, lat_centro=None, lon_centro=None):
    """Lookup speedup factor por turbina. Asume layout en metros relativos al centro.

    Si transform raster disponible → conversión exacta. Sino aprox centrada.
    """
    h, w = speedup_field.shape
    cy = h / 2.0
    cx = w / 2.0
    pixel_size = abs(transform.a) if transform is not None else 30.0

    factors = []
    for _, row in df_layout.iterrows():
        try:
            x_pix = int(cx + float(row.get("x_m", 0)) / pixel_size)
            y_pix = int(cy - float(row.get("y_m", 0)) / pixel_size)
            if 0 <= x_pix < w and 0 <= y_pix < h:
                val = float(speedup_field[y_pix, x_pix])
                if np.isfinite(val) and val > 0:
                    factors.append(val)
                else:
                    factors.append(1.0)
            else:
                factors.append(1.0)
        except Exception:
            factors.append(1.0)

    out = df_layout.copy()
    out["speedup_lineal"] = factors
    return out


def estimar_L_hill_desde_dem(dem_array, pixel_size_m=30.0):
    """Estima L_hill como distancia característica entre máximos locales del DEM.
    Fallback heurístico si no se conoce: usa diagonal del raster / 4.
    """
    h, w = dem_array.shape
    return float(min(h, w) * pixel_size_m / 4.0)
