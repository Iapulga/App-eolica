"""Importador genérico de datos de torre meteorológica (10-min CSV/Excel).

Soporta varios formatos comunes vía detección automática + parser unificado.
Salida estándar: DataFrame con columnas
    timestamp (datetime), ws_10min (float), ws_std (float), wd_10min (float),
    altura_sensor (float, opcional), temp_c (float, opcional).
"""

from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

COLUMNS_OUT_STD = ["timestamp", "ws_10min", "ws_std", "wd_10min", "altura_sensor", "temp_c"]


_TIMESTAMP_CANDIDATES = (
    "timestamp", "time", "datetime", "fecha", "fechahora", "datetime_local",
    "date_time", "date", "fecha_hora",
)
_WS_CANDIDATES = (
    "ws", "ws_mean", "wind_speed", "windspeed", "v", "vel", "velocidad",
    "ws_10min", "ws_avg", "wsavg", "wind speed avg", "ws80_avg", "ws_50m",
)
_WSSTD_CANDIDATES = (
    "ws_std", "ws_sd", "wind_std", "windstd", "std", "sigma", "ws_sigma",
    "ws80_std", "wsstd",
)
_WD_CANDIDATES = (
    "wd", "wd_mean", "wind_dir", "winddir", "direction", "dir", "direccion",
    "wd_10min", "wd_avg", "wd80_avg", "wd_50m",
)
_TEMP_CANDIDATES = (
    "temp", "temperature", "temp_c", "t_amb", "tamb", "tair", "t2m", "tc",
)
_HEIGHT_CANDIDATES = (
    "height", "altura", "h_sensor", "altura_sensor", "z_sensor",
)


def _norm_colname(name: str) -> str:
    s = str(name).strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _read_bytes_as_df(file_bytes: bytes, file_name: str = "") -> pd.DataFrame:
    fname = (file_name or "").lower()
    if fname.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(file_bytes))
    # Try CSV with multiple separator/encoding combos
    last_err = None
    for sep in (",", ";", "\t", "|"):
        for enc in ("utf-8-sig", "latin-1", "utf-8"):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, engine="python")
                if df.shape[1] >= 2 and df.shape[0] > 0:
                    return df
            except Exception as exc:
                last_err = exc
                continue
    raise ValueError(f"No pude parsear el archivo como CSV/Excel: {last_err}")


def detectar_formato_csv(file_bytes: bytes, file_name: str = "") -> str:
    try:
        df = _read_bytes_as_df(file_bytes, file_name)
    except Exception:
        return "desconocido"
    cols_norm = {_norm_colname(c) for c in df.columns}

    if any("nrg" in c or "symphonie" in c for c in cols_norm):
        return "nrg_symphonie"
    if any("campbell" in c or "logger" in c or "cr3000" in c for c in cols_norm):
        return "campbell_sci"
    if any("scada" in c for c in cols_norm):
        return "scada_generico"
    return "generico"


def _pick_first(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    cols_map = {_norm_colname(c): c for c in df.columns}
    for cand in candidates:
        if cand in cols_map:
            return cols_map[cand]
    for cand in candidates:
        for norm, original in cols_map.items():
            if cand in norm:
                return original
    return None


def parsear_torre_csv(
    file_bytes: bytes,
    file_name: str = "",
    altura_objetivo: float | None = None,
    formato: str = "auto",
) -> pd.DataFrame:
    df = _read_bytes_as_df(file_bytes, file_name)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS_OUT_STD)

    col_ts = _pick_first(df, _TIMESTAMP_CANDIDATES)
    col_ws = _pick_first(df, _WS_CANDIDATES)
    col_wsstd = _pick_first(df, _WSSTD_CANDIDATES)
    col_wd = _pick_first(df, _WD_CANDIDATES)
    col_temp = _pick_first(df, _TEMP_CANDIDATES)
    col_height = _pick_first(df, _HEIGHT_CANDIDATES)

    if col_ts is None or col_ws is None:
        raise ValueError(
            f"Faltan columnas críticas. timestamp candidate: {col_ts}, ws candidate: {col_ws}. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    out = pd.DataFrame()
    out["timestamp"] = pd.to_datetime(df[col_ts], errors="coerce", dayfirst=False)
    if out["timestamp"].isna().all():
        out["timestamp"] = pd.to_datetime(df[col_ts], errors="coerce", dayfirst=True)

    out["ws_10min"] = pd.to_numeric(df[col_ws], errors="coerce")
    out["ws_std"] = pd.to_numeric(df[col_wsstd], errors="coerce") if col_wsstd else np.nan
    out["wd_10min"] = pd.to_numeric(df[col_wd], errors="coerce") if col_wd else np.nan
    out["temp_c"] = pd.to_numeric(df[col_temp], errors="coerce") if col_temp else np.nan

    if col_height is not None:
        h_series = pd.to_numeric(df[col_height], errors="coerce")
        out["altura_sensor"] = h_series
    else:
        out["altura_sensor"] = float(altura_objetivo) if altura_objetivo else np.nan

    out = out.dropna(subset=["timestamp", "ws_10min"]).copy()
    out = out[out["ws_10min"] >= 0].copy()
    out = out[out["ws_10min"] <= 60].copy()
    if "wd_10min" in out.columns:
        out["wd_10min"] = out["wd_10min"].where((out["wd_10min"] >= 0) & (out["wd_10min"] < 360))

    out = out.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    return out[COLUMNS_OUT_STD]


def agregar_10min_a_horario(df_10min: pd.DataFrame) -> pd.DataFrame:
    if df_10min is None or len(df_10min) == 0:
        return pd.DataFrame(columns=["timestamp", "ws_10min", "ws_std", "wd_10min", "temp_c"])

    df = df_10min.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df["hour_floor"] = df["timestamp"].dt.floor("h")

    grouped = df.groupby("hour_floor")
    def _wd_circular_mean(s):
        s = pd.to_numeric(s, errors="coerce").dropna()
        if len(s) == 0:
            return np.nan
        rad = np.deg2rad(s.to_numpy(dtype=float))
        x = np.mean(np.cos(rad))
        y = np.mean(np.sin(rad))
        ang = np.rad2deg(np.arctan2(y, x))
        return ang if ang >= 0 else ang + 360

    out = pd.DataFrame({
        "timestamp": list(grouped.groups.keys()),
        "ws_10min": grouped["ws_10min"].mean().to_numpy(),
        "ws_std": grouped["ws_std"].apply(lambda s: np.sqrt(np.nanmean(np.square(s.dropna()))) if s.dropna().size else np.nan).to_numpy(),
        "wd_10min": grouped["wd_10min"].apply(_wd_circular_mean).to_numpy(),
        "temp_c": grouped["temp_c"].mean().to_numpy(),
    })
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out


def validar_torre_data(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        return {"ok": False, "msg": "DataFrame vacío"}

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    t_start = df["timestamp"].iloc[0]
    t_end = df["timestamp"].iloc[-1]
    n_obs = len(df)

    delta = df["timestamp"].diff().median()
    if pd.isna(delta) or delta.total_seconds() <= 0:
        cadencia_min = float("nan")
    else:
        cadencia_min = delta.total_seconds() / 60.0

    if not pd.isna(cadencia_min) and cadencia_min > 0:
        n_esperado = int((t_end - t_start).total_seconds() / (cadencia_min * 60.0)) + 1
        recovery_pct = 100.0 * n_obs / n_esperado if n_esperado > 0 else float("nan")
    else:
        n_esperado = n_obs
        recovery_pct = 100.0

    ws = pd.to_numeric(df["ws_10min"], errors="coerce")
    outliers_high = int((ws > 40).sum())
    outliers_low = int((ws < 0).sum())
    ws_mean = float(ws.mean())
    ws_max = float(ws.max())
    n_valid_ws = int(ws.notna().sum())

    return {
        "ok": True,
        "t_start": str(t_start),
        "t_end": str(t_end),
        "n_obs": int(n_obs),
        "n_esperado": int(n_esperado),
        "recovery_pct": float(recovery_pct),
        "cadencia_min": float(cadencia_min) if not pd.isna(cadencia_min) else 10.0,
        "ws_mean": ws_mean,
        "ws_max": ws_max,
        "n_valid_ws": n_valid_ws,
        "outliers_high": outliers_high,
        "outliers_low": outliers_low,
    }
