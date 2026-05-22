"""Helpers para cargas y validación de datos (NASA hourly, layout, etc.).

Objetivo: centralizar normalizaciones y conversiones de tipos para evitar
duplicar esta lógica en páginas. Los cambios aquí no alteran la semántica
de los cálculos, solo garantizan formatos y tipos.
"""
from __future__ import annotations

import pandas as pd


def load_and_validate_nasa_data(cargar_nasa_func) -> pd.DataFrame:
    """Carga datos horarios usando la función provista y normaliza columnas.

    `cargar_nasa_func` debe ser una función callable que retorne un DataFrame
    (por ejemplo `db.cargar_nasa_hourly`).
    """
    df = cargar_nasa_func()
    if df is None or len(df) == 0:
        return pd.DataFrame()

    df = df.copy()

    # Normalizar timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        # Intentar construir timestamp desde YEAR/MO/DY/HR
        if all(c in df.columns for c in ("YEAR", "MO", "DY", "HR")):
            try:
                df["timestamp"] = pd.to_datetime(
                    df["YEAR"].astype(str)
                    + "-"
                    + df["MO"].astype(str).str.zfill(2)
                    + "-"
                    + df["DY"].astype(str).str.zfill(2)
                    + " "
                    + df["HR"].astype(str).str.zfill(2)
                    + ":00",
                    errors="coerce",
                )
            except Exception:
                df["timestamp"] = pd.NaT

    # Columnas de viento: asegurar tipos numéricos
    for col in ("WS10M", "WS50M", "WD10M", "WD50M"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Asegurar orden por timestamp
    if "timestamp" in df.columns:
        try:
            df = df.sort_values("timestamp").reset_index(drop=True)
        except Exception:
            pass

    return df
