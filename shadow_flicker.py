"""Shadow flicker analysis — parpadeo de sombra de rotor sobre receptores.

Algoritmo geométrico simplificado:
  1. Para cada timestamp horario, obtener posición sol (pvlib).
  2. Para cada par (turbina, receptor): proyectar sombra del disco rotor en plano horizontal.
  3. Marcar flicker hora si receptor cae dentro de elipse de sombra + wind speed > cut-in.

Output: horas/año flicker por receptor + mapa heatmap risk.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calcular_posicion_sol_serie(timestamps, lat, lon, altitud_m=0.0):
    """Devuelve DataFrame con elevation/azimuth solar para cada timestamp.

    timestamps: pd.DatetimeIndex (UTC asumido si no es timezone-aware).
    Returns DataFrame indexed by timestamp con columnas apparent_elevation, azimuth.
    """
    try:
        import pvlib
    except ImportError:
        return pd.DataFrame()

    ts = pd.to_datetime(timestamps, utc=True, errors="coerce")
    ts = ts.dropna() if hasattr(ts, "dropna") else pd.DatetimeIndex([t for t in ts if pd.notna(t)])
    if len(ts) == 0:
        return pd.DataFrame()

    pos = pvlib.solarposition.get_solarposition(ts, float(lat), float(lon), altitude=float(altitud_m))
    return pos[["apparent_elevation", "azimuth"]].copy()


def calcular_sombra_intercepta_receptor(
    turbina_xy, receptor_xy,
    sol_elevation_deg, sol_azimuth_deg,
    diametro_rotor, altura_buje, altura_receptor=1.5,
    radio_sombra_extra_m=10.0,
):
    """Determina si la sombra del rotor cae sobre el receptor a una hora dada.

    Geometría simplificada:
    - Sol en (azimuth, elevation). Si elevation <= 0 → no sombra.
    - Centro rotor a (x_t, y_t, h_b). Vector sol-rotor proyectado al plano del receptor.
    - Sombra del disco = elipse en plano horizontal a altura_receptor.
    - Si distancia 2D (receptor → centro sombra) < radio_sombra, devolver True.
    """
    if sol_elevation_deg <= 1.0:  # Sol muy bajo: sombra muy larga, ignoramos
        return False, float("inf")

    x_t, y_t = float(turbina_xy[0]), float(turbina_xy[1])
    x_r, y_r = float(receptor_xy[0]), float(receptor_xy[1])

    # Vector unitario del sol al observador (en plano XY)
    az_rad = np.deg2rad(float(sol_azimuth_deg))
    el_rad = np.deg2rad(float(sol_elevation_deg))

    # Centro de la sombra: turbina + proyección horizontal del rotor en el plano del receptor.
    dz = float(altura_buje) - float(altura_receptor)
    if dz <= 0:
        return False, float("inf")
    horiz_distance = dz / np.tan(el_rad)  # distancia desde turbina al centro sombra

    # Dirección sombra: opuesta al sol (sol azimuth → sombra apunta a opposite_az)
    shadow_az_rad = az_rad + np.pi
    dx_shadow = horiz_distance * np.sin(shadow_az_rad)
    dy_shadow = horiz_distance * np.cos(shadow_az_rad)

    cx_shadow = x_t + dx_shadow
    cy_shadow = y_t + dy_shadow

    # Tamaño sombra: rotor disco proyectado. Eje major = D/sin(elevation), eje minor = D
    eje_major = float(diametro_rotor) / max(0.05, np.sin(el_rad))
    eje_minor = float(diametro_rotor)
    radio_eq = (eje_major + eje_minor) / 4.0 + float(radio_sombra_extra_m)  # aprox circular conservador

    # Distancia receptor-centro sombra
    dx_rs = x_r - cx_shadow
    dy_rs = y_r - cy_shadow
    dist = np.sqrt(dx_rs * dx_rs + dy_rs * dy_rs)

    return bool(dist <= radio_eq), float(dist)


def calcular_horas_flicker_anual(
    df_layout, receptores,
    timestamps, ws_serie,
    lat, lon, diametro_rotor, altura_buje, altura_receptor=1.5,
    cut_in_ms=3.0, cut_out_ms=25.0, altitud_m=0.0,
):
    """Para cada receptor: horas/año con flicker (sombra del rotor + viento dentro de operación).

    Args:
      df_layout: DataFrame {turbina_id, x_m, y_m}
      receptores: list of dicts [{receptor_id, nombre, x_m, y_m}] (coords relativos al centro)
      timestamps: pd.DatetimeIndex
      ws_serie: pd.Series velocidad alineada a timestamps
      lat, lon: del centro
    Returns:
      DataFrame {receptor_id, nombre, horas_flicker, porcentaje_anio, n_turbinas_contribuyen}
    """
    if df_layout is None or len(df_layout) == 0 or not receptores or len(timestamps) == 0:
        return pd.DataFrame()

    pos_sol = calcular_posicion_sol_serie(timestamps, lat, lon, altitud_m)
    if len(pos_sol) == 0:
        return pd.DataFrame()

    n_hours = len(pos_sol)
    ws_arr = np.asarray(pd.to_numeric(ws_serie, errors="coerce"), dtype=float)
    if len(ws_arr) > n_hours:
        ws_arr = ws_arr[:n_hours]
    elif len(ws_arr) < n_hours:
        ws_arr = np.concatenate([ws_arr, np.full(n_hours - len(ws_arr), np.nan)])

    mask_op = np.isfinite(ws_arr) & (ws_arr >= cut_in_ms) & (ws_arr <= cut_out_ms)
    mask_sol = pos_sol["apparent_elevation"].to_numpy(dtype=float) > 1.0
    mask_active = mask_op & mask_sol

    turbinas = list(df_layout.itertuples(index=False))

    rows_out = []
    for rec in receptores:
        rec_id = rec.get("receptor_id", "R?")
        rec_nombre = rec.get("nombre", rec_id)
        rec_x = float(rec.get("x_m", 0.0))
        rec_y = float(rec.get("y_m", 0.0))

        horas_flicker = 0
        contrib_turb = set()

        elev_arr = pos_sol["apparent_elevation"].to_numpy(dtype=float)
        az_arr = pos_sol["azimuth"].to_numpy(dtype=float)
        active_idx = np.where(mask_active)[0]

        for h_idx in active_idx:
            elev = elev_arr[h_idx]
            az = az_arr[h_idx]
            hit_alguna = False
            for turb in turbinas:
                tx = float(getattr(turb, "x_m", 0))
                ty = float(getattr(turb, "y_m", 0))
                hit, _ = calcular_sombra_intercepta_receptor(
                    (tx, ty), (rec_x, rec_y),
                    elev, az, diametro_rotor, altura_buje, altura_receptor,
                )
                if hit:
                    hit_alguna = True
                    contrib_turb.add(str(getattr(turb, "turbina_id", "T?")))
            if hit_alguna:
                horas_flicker += 1

        porcentaje = (horas_flicker / n_hours) * 100.0 if n_hours > 0 else 0.0
        rows_out.append({
            "receptor_id": rec_id,
            "nombre": rec_nombre,
            "x_m": rec_x,
            "y_m": rec_y,
            "horas_flicker_anuales": int(horas_flicker),
            "porcentaje_anio": float(porcentaje),
            "n_turbinas_contribuyen": int(len(contrib_turb)),
            "turbinas_contrib": ",".join(sorted(contrib_turb)),
            "cumple_limite_30h": horas_flicker <= 30,
        })

    return pd.DataFrame(rows_out)


def crear_mapa_flicker_grid(
    df_layout, timestamps, ws_serie, lat, lon,
    diametro_rotor, altura_buje, altura_receptor=1.5,
    grid_extent_m=2000, grid_resolution=20, altitud_m=0.0,
):
    """Genera grid 2D de receptores virtuales alrededor del centro del parque.

    Returns: DataFrame con x_m, y_m, horas_flicker para cada celda grid.
    """
    xs = np.linspace(-grid_extent_m, grid_extent_m, grid_resolution)
    ys = np.linspace(-grid_extent_m, grid_extent_m, grid_resolution)
    receptores_grid = []
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            receptores_grid.append({"receptor_id": f"G{i}_{j}", "nombre": f"grid_{i}_{j}", "x_m": float(x), "y_m": float(y)})

    return calcular_horas_flicker_anual(
        df_layout, receptores_grid, timestamps, ws_serie,
        lat, lon, diametro_rotor, altura_buje, altura_receptor, altitud_m=altitud_m,
    )
