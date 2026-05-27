"""GIS helpers — SRTM DEM + Land Cover lookup automático.

Funcionalidad:
  - Descarga SRTM 30m DEM via `elevation` package (público, gratuito).
  - Calcula pendiente media + max desde DEM.
  - Lookup tabla rugosidad z0 desde clase Land Cover (default IGBP).
  - Auto-extrae altitud media del polígono del parque.

Limitación: Land Cover automático para Colombia requiere capas IGAC/IDEAM. Por defecto usa
tabla estándar IGBP y permite override manual.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np

# Z0 lookup table (m) - estándar prácticas eólicas (Manwell et al. 2009)
Z0_LOOKUP_LANDCOVER = {
    "agua": 0.0002,
    "mar": 0.0002,
    "nieve_hielo": 0.001,
    "arena_playa": 0.005,
    "desierto": 0.005,
    "césped_corto": 0.008,
    "césped_pasto": 0.03,
    "campo_abierto_cultivo": 0.05,
    "cultivos": 0.10,
    "matorral_bajo": 0.10,
    "agroforestal": 0.20,
    "bosque": 0.80,
    "ciudad_suburbano": 0.50,
    "ciudad_centro": 1.00,
    "industrial": 0.40,
}


def descargar_srtm_dem(lat_centro, lon_centro, radius_km=10, output_dir=None):
    """Descarga DEM SRTM 30m con `elevation` package. Returns path GeoTIFF.

    Requiere conexión internet primera vez. Cache local típico ~/.elevation/cache/SRTM3/.
    """
    try:
        import elevation
    except ImportError:
        raise RuntimeError("Instalar elevation: `pip install elevation`")

    lat = float(lat_centro)
    lon = float(lon_centro)
    delta = max(0.02, float(radius_km) * 0.01)  # 1 km ≈ 0.01° en lat

    if output_dir is None:
        output_dir = tempfile.gettempdir()
    output_path = os.path.join(output_dir, f"sma_dem_{lat:.4f}_{lon:.4f}_{radius_km:.0f}km.tif")

    bounds = (lon - delta, lat - delta, lon + delta, lat + delta)
    elevation.clip(bounds=bounds, output=output_path, product="SRTM3")
    return output_path


def cargar_dem_array(dem_path):
    """Lee GeoTIFF DEM → (array, transform, crs)."""
    try:
        import rasterio
    except ImportError:
        raise RuntimeError("Instalar rasterio: `pip install rasterio`")

    with rasterio.open(dem_path) as src:
        arr = src.read(1).astype(np.float32)
        # NaN para no-data
        nodata = src.nodata if src.nodata is not None else -32768
        arr = np.where(arr == nodata, np.nan, arr)
        return arr, src.transform, src.crs, src.bounds


def calcular_estadisticas_dem(arr, pixel_size_m=30.0):
    """Stats: elevación mín/max/media/std, pendiente media/p95."""
    arr_clean = arr[np.isfinite(arr)]
    if arr_clean.size == 0:
        return {}

    # Pendiente: gradiente del DEM
    grad_y, grad_x = np.gradient(arr, pixel_size_m)
    slope_rad = np.arctan(np.sqrt(grad_x ** 2 + grad_y ** 2))
    slope_deg = np.rad2deg(slope_rad)
    slope_clean = slope_deg[np.isfinite(slope_deg)]

    return {
        "elev_min_m": float(np.nanmin(arr_clean)),
        "elev_max_m": float(np.nanmax(arr_clean)),
        "elev_media_m": float(np.nanmean(arr_clean)),
        "elev_std_m": float(np.nanstd(arr_clean)),
        "slope_media_deg": float(np.nanmean(slope_clean)) if slope_clean.size > 0 else float("nan"),
        "slope_p95_deg": float(np.nanpercentile(slope_clean, 95)) if slope_clean.size > 0 else float("nan"),
        "slope_max_deg": float(np.nanmax(slope_clean)) if slope_clean.size > 0 else float("nan"),
        "pixel_size_m": float(pixel_size_m),
        "n_pixels": int(arr_clean.size),
    }


def lookup_z0_por_landcover(label):
    """Devuelve z0 (m) desde label de Land Cover. None si no encuentra."""
    return Z0_LOOKUP_LANDCOVER.get(str(label).strip().lower())


def estimar_landcover_global(lat, lon):
    """Estimación landcover GLOBAL basada en lat/lon usando zonificación climática
    Köppen-Geiger aproximada + tablas IGBP/MODIS.

    Mucho más limitada que datos raster reales (MODIS MCD12Q1, ESA WorldCover) pero
    útil cuando no hay conexión o datos pagos.

    Returns dict {label, z0, confianza_pct, region_climatica}.
    """
    lat_f = float(lat)
    lon_f = float(lon)
    abs_lat = abs(lat_f)

    # 1. Verificar agua (océanos)
    # Aproximación gruesa: si NO está en ninguna landmass conocida → asumir agua
    landmasses_approx = [
        # (lat_min, lat_max, lon_min, lon_max, label, z0)
        (-55, 80, -170, -50, "Americas_landmass", None),     # Americas
        (35, 75, -10, 60, "Europe_landmass", None),          # Europe
        (-35, 40, -20, 55, "Africa_landmass", None),          # Africa
        (5, 80, 55, 180, "Asia_landmass", None),              # Asia
        (-45, -10, 110, 155, "Australia_landmass", None),    # Australia/NZ
    ]
    on_land = any(
        lo_lat <= lat_f <= hi_lat and lo_lon <= lon_f <= hi_lon
        for lo_lat, hi_lat, lo_lon, hi_lon, _, _ in landmasses_approx
    )
    if not on_land:
        return {"label": "mar", "z0": Z0_LOOKUP_LANDCOVER["mar"], "confianza_pct": 70.0,
                "region_climatica": "oceano", "comentario": "Sobre cuerpo de agua (océano)"}

    # 2. Zonificación climática Köppen-Geiger aproximada
    # Tropical húmedo (Af, Am): lat |≤10|, no desierto → bosque tropical
    # Tropical sabana (Aw): lat 10-20 → césped/sabana
    # Árido (B): grandes desiertos por lat+lon específicos
    # Templado (C): lat 30-50 → cultivos/agroforestal
    # Continental (D): lat 50-70 → forest/taiga
    # Polar (E): lat >70 → tundra/nieve

    # Desiertos conocidos (zona árida)
    desiertos = [
        # Sahara
        (15, 33, -15, 35),
        # Arabia
        (15, 30, 35, 55),
        # Gobi
        (38, 48, 90, 110),
        # Australian outback
        (-30, -20, 120, 145),
        # Atacama
        (-26, -18, -71, -68),
        # Mojave/Sonoran
        (28, 38, -120, -105),
        # Karoo
        (-32, -28, 18, 26),
        # Guajira (semiárida costa Caribe)
        (10.5, 13, -73, -71),
    ]
    if any(lo_lat <= lat_f <= hi_lat and lo_lon <= lon_f <= hi_lon for lo_lat, hi_lat, lo_lon, hi_lon in desiertos):
        return {"label": "desierto", "z0": Z0_LOOKUP_LANDCOVER["desierto"], "confianza_pct": 70.0,
                "region_climatica": "arido", "comentario": "Zona desierta/semiárida"}

    # Tropical húmedo (selvas)
    if abs_lat <= 10:
        # Amazonía, Congo, Sudeste asiático
        amazonia = (-78 <= lon_f <= -45)
        congo = (10 <= lon_f <= 30)
        seasia = (95 <= lon_f <= 145)
        if amazonia or congo or seasia:
            return {"label": "bosque", "z0": Z0_LOOKUP_LANDCOVER["bosque"], "confianza_pct": 65.0,
                    "region_climatica": "tropical_humedo", "comentario": "Bosque tropical denso"}

    # Tropical seco / sabana
    if abs_lat <= 25:
        return {"label": "césped_pasto", "z0": Z0_LOOKUP_LANDCOVER["césped_pasto"], "confianza_pct": 50.0,
                "region_climatica": "tropical_seco", "comentario": "Sabana / pastos tropicales"}

    # Templado
    if 25 < abs_lat <= 50:
        # Áreas con altos cultivos en hemisferio norte: USA, Europa, China
        if (lat_f > 0 and ((-100 <= lon_f <= -75) or (-10 <= lon_f <= 40) or (100 <= lon_f <= 130))):
            return {"label": "cultivos", "z0": Z0_LOOKUP_LANDCOVER["cultivos"], "confianza_pct": 50.0,
                    "region_climatica": "templado", "comentario": "Zona templada con cultivos"}
        return {"label": "agroforestal", "z0": Z0_LOOKUP_LANDCOVER["agroforestal"], "confianza_pct": 40.0,
                "region_climatica": "templado", "comentario": "Templado mixto (agroforestal)"}

    # Continental/subártico
    if 50 < abs_lat <= 70:
        return {"label": "bosque", "z0": Z0_LOOKUP_LANDCOVER["bosque"], "confianza_pct": 55.0,
                "region_climatica": "boreal", "comentario": "Taiga / bosque boreal"}

    # Polar
    if abs_lat > 70:
        return {"label": "nieve_hielo", "z0": Z0_LOOKUP_LANDCOVER["nieve_hielo"], "confianza_pct": 70.0,
                "region_climatica": "polar", "comentario": "Tundra / hielo permanente"}

    # Default fallback
    return {"label": "cultivos", "z0": Z0_LOOKUP_LANDCOVER["cultivos"], "confianza_pct": 25.0,
            "region_climatica": "indeterminado", "comentario": "Estimación genérica — override manual"}


def estimar_landcover_aproximado_colombia(lat, lon):
    """Estimación aproximada Land Cover para Colombia.

    Sin APIs externas, basado en zonificación gruesa Colombia:
    - Costa Caribe (Guajira, lat >10, lon entre -75 y -70): playa/desierto → z0 ≈ 0.005
    - Llanos (lat 3-8, lon -75 a -67): pasto/cultivos → z0 ≈ 0.05
    - Andes (lat 1-8, lon -77 a -73): variable según altitud (bosque alto → pasto)
    - Amazonía (lat <2, lon -78 a -67): bosque tropical → z0 ≈ 0.80
    - Mar Caribe (lat >10, lon -76 a -71 con elevacion 0): agua → z0 ≈ 0.0002

    Returns dict {label, z0, confianza_pct}.
    """
    lat_f = float(lat)
    lon_f = float(lon)

    # Costa Caribe / Guajira
    if 9.5 <= lat_f <= 13.5 and -75 <= lon_f <= -70:
        return {"label": "arena_playa", "z0": Z0_LOOKUP_LANDCOVER["arena_playa"], "confianza_pct": 60.0,
                "comentario": "Guajira costa — predominio playa/sabana baja"}
    # Llanos orientales
    if 2.5 <= lat_f <= 8.5 and -74 <= lon_f <= -67:
        return {"label": "césped_pasto", "z0": Z0_LOOKUP_LANDCOVER["césped_pasto"], "confianza_pct": 55.0,
                "comentario": "Llanos orientales — pastos/sabanas"}
    # Amazonía
    if -4.5 <= lat_f <= 2.5 and -78 <= lon_f <= -66:
        return {"label": "bosque", "z0": Z0_LOOKUP_LANDCOVER["bosque"], "confianza_pct": 65.0,
                "comentario": "Amazonía colombiana — bosque tropical denso"}
    # Andes
    if 1 <= lat_f <= 8 and -77 <= lon_f <= -73:
        return {"label": "agroforestal", "z0": Z0_LOOKUP_LANDCOVER["agroforestal"], "confianza_pct": 40.0,
                "comentario": "Andes — variable; usar manual override según altitud"}
    # Default
    return {"label": "cultivos", "z0": Z0_LOOKUP_LANDCOVER["cultivos"], "confianza_pct": 30.0,
            "comentario": "Default genérico — recomendado override manual"}


def auto_configurar_sitio_desde_lat_lon(lat, lon, radius_km=10, descargar_dem=True, forzar_global=False):
    """Wrapper alto nivel: descarga DEM + calcula stats + estima z0 → dict listo para UI.

    Si lat/lon dentro Colombia (lat 0-13, lon -80 a -65) y NO forzar_global:
    usa estimar_landcover_aproximado_colombia (más precisa). Sino usa global.
    """
    res = {
        "lat": float(lat),
        "lon": float(lon),
        "radius_km": float(radius_km),
        "dem_disponible": False,
        "dem_stats": {},
        "landcover": {},
        "error": None,
    }

    en_colombia = (-2.0 <= float(lat) <= 13.5) and (-82.0 <= float(lon) <= -66.0)
    if en_colombia and not forzar_global:
        lc = estimar_landcover_aproximado_colombia(lat, lon)
    else:
        lc = estimar_landcover_global(lat, lon)
    res["landcover"] = lc

    if descargar_dem:
        try:
            dem_path = descargar_srtm_dem(lat, lon, radius_km)
            arr, transform, crs, bounds = cargar_dem_array(dem_path)
            stats = calcular_estadisticas_dem(arr, pixel_size_m=30.0)
            res["dem_disponible"] = True
            res["dem_path"] = dem_path
            res["dem_stats"] = stats
        except Exception as exc:
            res["error"] = f"DEM descarga falló: {exc}"

    return res
