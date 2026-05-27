"""WindNinja wrapper — mass-consistent terrain flow model (NREL, gratis).

WindNinja resuelve flujo de viento sobre terreno usando solver mass-consistent.
Calidad ~60-70% WAsP en terreno medio. CFD real (RANS/LES) sigue siendo Fase D.

REQUERIMIENTO: instalar WindNinja CLI binario (https://www.firelab.org/project/windninja).
En Windows típicamente: C:\\Program Files\\WindNinja\\bin\\WindNinja_cli.exe

Si binario no presente → wrapper devuelve speedup=1.0 (sin corrección).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np

WINDNINJA_DEFAULT_PATHS_WIN = [
    r"C:\Program Files\WindNinja\bin\WindNinja_cli.exe",
    r"C:\Program Files (x86)\WindNinja\bin\WindNinja_cli.exe",
]


def windninja_disponible():
    """Returns ruta del binario WindNinja CLI si encontrado, sino None."""
    # PATH first
    exe = shutil.which("WindNinja_cli") or shutil.which("WindNinja_cli.exe")
    if exe:
        return exe
    # Windows defaults
    for p in WINDNINJA_DEFAULT_PATHS_WIN:
        if os.path.isfile(p):
            return p
    return None


def ejecutar_windninja(
    dem_path,
    wind_speed_input_ms,
    wind_direction_input_deg,
    output_dir,
    mesh_resolution_m=100,
    h_hub=80.0,
    vegetacion="grass",
    timeout_s=600,
):
    """Ejecuta WindNinja CLI domainAverageInitialization.

    Returns: dict con paths de outputs ASCII (velocity, direction).
    """
    exe = windninja_disponible()
    if exe is None:
        raise RuntimeError(
            "WindNinja CLI no encontrado. Instalar desde https://www.firelab.org/project/windninja "
            "y añadir a PATH o instalar en `C:\\Program Files\\WindNinja\\`."
        )

    os.makedirs(output_dir, exist_ok=True)
    veg_arg = {"grass": "grass", "shrub": "brush", "forest": "trees"}.get(vegetacion, "grass")

    cmd = [
        exe,
        "--num_threads", "4",
        "--elevation_file", str(dem_path),
        "--initialization_method", "domainAverageInitialization",
        "--input_speed", str(float(wind_speed_input_ms)),
        "--input_speed_units", "mps",
        "--input_direction", str(float(wind_direction_input_deg)),
        "--input_wind_height", str(float(h_hub)),
        "--units_input_wind_height", "m",
        "--output_speed_units", "mps",
        "--diurnal_winds", "false",
        "--non_neutral_stability", "false",
        "--output_wind_height", str(float(h_hub)),
        "--units_output_wind_height", "m",
        "--vegetation", veg_arg,
        "--mesh_choice", "custom",
        "--mesh_resolution", str(int(mesh_resolution_m)),
        "--units_mesh_resolution", "m",
        "--write_ascii_output", "true",
        "--ascii_out_resolution", str(int(mesh_resolution_m)),
        "--output_path", str(output_dir),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if result.returncode != 0:
        raise RuntimeError(f"WindNinja falló: {result.stderr or result.stdout}")

    # Buscar outputs ASC en output_dir
    out_files = list(Path(output_dir).rglob("*.asc"))
    speed_files = [f for f in out_files if "vel" in f.name.lower() or "speed" in f.name.lower()]
    dir_files = [f for f in out_files if "ang" in f.name.lower() or "dir" in f.name.lower()]

    return {
        "speed_asc": str(speed_files[0]) if speed_files else None,
        "direction_asc": str(dir_files[0]) if dir_files else None,
        "all_outputs": [str(f) for f in out_files],
        "stdout": result.stdout,
    }


def cargar_speedup_map(asc_path, wind_speed_input_ms):
    """Lee ASCII grid → numpy speed array + computes speedup map (ratio vs input)."""
    try:
        import rasterio
    except ImportError:
        raise RuntimeError("Instalar rasterio: `pip install rasterio`")

    with rasterio.open(asc_path) as src:
        arr = src.read(1).astype(np.float32)
        nodata = src.nodata if src.nodata is not None else -9999
        arr = np.where(arr == nodata, np.nan, arr)
        speedup = arr / max(float(wind_speed_input_ms), 0.01)
        return {
            "speed_map": arr,
            "speedup_map": speedup,
            "transform": src.transform,
            "bounds": src.bounds,
            "shape": arr.shape,
            "speedup_stats": {
                "min": float(np.nanmin(speedup)),
                "max": float(np.nanmax(speedup)),
                "mean": float(np.nanmean(speedup)),
                "std": float(np.nanstd(speedup)),
            },
        }


def aplicar_speedup_a_turbinas(df_layout, speedup_map_info, lat_centro, lon_centro):
    """Para cada turbina del layout, lookup speedup factor → asigna columna `speedup`.

    Conversión x_m, y_m a coords raster usando transform.
    """
    transform = speedup_map_info["transform"]
    arr = speedup_map_info["speedup_map"]
    h, w = arr.shape

    # Origin del DEM (esquina superior izquierda)
    # Aprox: turbinas en metros relativos al centro_lat, centro_lon
    # transform.a = pixel_width_x (en grados o m segun CRS)
    # asumiendo CRS metric local con origin del raster ya conocido
    # SIMPLIFICACION: asume turbinas centradas en el centroide del raster
    cy = h / 2.0
    cx = w / 2.0
    pixel_size = abs(transform.a)  # grados o m, depende CRS

    # Asume CRS metric (UTM proyectado) para simplicidad
    factors = []
    for _, row in df_layout.iterrows():
        x_pix = int(cx + float(row["x_m"]) / pixel_size)
        y_pix = int(cy - float(row["y_m"]) / pixel_size)
        if 0 <= x_pix < w and 0 <= y_pix < h:
            val = arr[y_pix, x_pix]
            if np.isfinite(val) and val > 0:
                factors.append(float(val))
            else:
                factors.append(1.0)
        else:
            factors.append(1.0)

    out = df_layout.copy()
    out["speedup"] = factors
    return out
