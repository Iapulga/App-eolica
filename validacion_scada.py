"""Validación model vs SCADA real — performance assurance post-construcción.

Compara AEP modelado por SMA vs producción real medida primer año de operación.
Calcula bias, RMSE, R², residuales por sector/velocidad/hora.

Banca exige este análisis post-operación para confirmar P50/P90.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

COLUMNS_SCADA_STD = ["timestamp", "turbine_id", "P_kW", "WS_ms", "WD_deg", "status_code"]


def importar_scada_csv(file_bytes, file_name="", formato="auto"):
    """Parser SCADA genérico CSV/Excel. Detecta columnas estándar.

    Espera columnas tipo: time/timestamp, turbine_id/wt_id, P_kW/power, WS_ms/wind_speed.
    """
    fname = (file_name or "").lower()
    try:
        if fname.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            for sep in (",", ";", "\t"):
                for enc in ("utf-8-sig", "latin-1"):
                    try:
                        df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, engine="python")
                        if df.shape[1] >= 2:
                            break
                    except Exception:
                        continue
                else:
                    continue
                break
    except Exception as exc:
        raise ValueError(f"No pude parsear SCADA: {exc}")

    # Mapping columnas
    col_map = {}
    for c in df.columns:
        cn = str(c).strip().lower()
        if cn in ("time", "timestamp", "datetime", "fecha"):
            col_map[c] = "timestamp"
        elif cn in ("turbine_id", "wt_id", "turbina_id", "tag"):
            col_map[c] = "turbine_id"
        elif cn in ("p_kw", "power_kw", "power", "potencia_kw", "p"):
            col_map[c] = "P_kW"
        elif cn in ("p_mw", "power_mw", "potencia_mw"):
            col_map[c] = "P_MW"
        elif cn in ("ws_ms", "ws", "wind_speed", "v"):
            col_map[c] = "WS_ms"
        elif cn in ("wd_deg", "wd", "direction", "wd_avg"):
            col_map[c] = "WD_deg"
        elif cn in ("status", "status_code", "alarm"):
            col_map[c] = "status_code"

    df = df.rename(columns=col_map)
    if "P_kW" not in df.columns and "P_MW" in df.columns:
        df["P_kW"] = pd.to_numeric(df["P_MW"], errors="coerce") * 1000.0

    if "timestamp" not in df.columns or "P_kW" not in df.columns:
        raise ValueError(f"SCADA debe tener columnas timestamp y P_kW (o P_MW). Detectadas: {list(df.columns)}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["P_kW"] = pd.to_numeric(df["P_kW"], errors="coerce")
    df = df.dropna(subset=["timestamp", "P_kW"])
    if "turbine_id" not in df.columns:
        df["turbine_id"] = "T1"
    return df


def agregar_scada_a_parque_horario(df_scada):
    """Suma todas las turbinas en cada timestamp → potencia total parque por hora."""
    df = df_scada.copy()
    df["hour_floor"] = df["timestamp"].dt.floor("h")
    parque_hourly = df.groupby("hour_floor", as_index=False)["P_kW"].sum().rename(columns={"hour_floor": "timestamp", "P_kW": "P_parque_kW"})
    parque_hourly["P_parque_MW"] = parque_hourly["P_parque_kW"] / 1000.0
    return parque_hourly


def comparar_modelado_vs_real(df_modelo_horario, df_scada_parque):
    """Compara P_predicho vs P_real hora a hora.

    df_modelo_horario: {timestamp, potencia_parque_W o _MW}
    df_scada_parque: {timestamp, P_parque_MW}
    """
    df_m = df_modelo_horario.copy()
    df_s = df_scada_parque.copy()
    df_m["timestamp"] = pd.to_datetime(df_m["timestamp"], errors="coerce")
    df_s["timestamp"] = pd.to_datetime(df_s["timestamp"], errors="coerce")

    if "potencia_parque_W" in df_m.columns:
        df_m["P_modelo_MW"] = df_m["potencia_parque_W"] / 1e6
    elif "potencia_parque_MW" in df_m.columns:
        df_m["P_modelo_MW"] = df_m["potencia_parque_MW"]
    else:
        raise ValueError("df_modelo_horario debe tener potencia_parque_W o _MW")

    merged = df_m[["timestamp", "P_modelo_MW"]].merge(
        df_s[["timestamp", "P_parque_MW"]].rename(columns={"P_parque_MW": "P_real_MW"}),
        on="timestamp", how="inner",
    )
    if len(merged) < 10:
        return {"ok": False, "msg": "Menos de 10 horas en overlap", "n_samples": len(merged)}

    p_real = merged["P_real_MW"].to_numpy(dtype=float)
    p_modelo = merged["P_modelo_MW"].to_numpy(dtype=float)
    valid = np.isfinite(p_real) & np.isfinite(p_modelo) & (p_real >= 0) & (p_modelo >= 0)
    p_real = p_real[valid]
    p_modelo = p_modelo[valid]
    n = len(p_real)

    residuales = p_real - p_modelo
    bias = float(np.mean(residuales))
    rmse = float(np.sqrt(np.mean(residuales ** 2)))
    mae = float(np.mean(np.abs(residuales)))
    ss_res = float(np.sum(residuales ** 2))
    ss_tot = float(np.sum((p_real - np.mean(p_real)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    efficiency_ratio = float(np.mean(p_real) / np.mean(p_modelo)) if np.mean(p_modelo) > 0 else float("nan")

    merged_clean = merged[valid].copy()
    merged_clean["residual_MW"] = residuales
    merged_clean["P_real_MW_valid"] = p_real
    merged_clean["P_modelo_MW_valid"] = p_modelo

    return {
        "ok": True,
        "n_samples": int(n),
        "bias_MW": bias,
        "rmse_MW": rmse,
        "mae_MW": mae,
        "r2": float(r2),
        "efficiency_ratio": float(efficiency_ratio),
        "energia_real_MWh": float(np.sum(p_real)),
        "energia_modelo_MWh": float(np.sum(p_modelo)),
        "df_compare": merged_clean,
    }


def actualizar_p50_p90_con_real(p50_predicho_mwh, sigma_residuales_mwh, factor_anual=1.0):
    """Update P50/P90 banca basándose en sigma observada en datos reales.

    factor_anual: si datos son por hora, scaling para sigma anual.
    """
    p50_real = float(p50_predicho_mwh)
    sigma_anual = float(sigma_residuales_mwh) * factor_anual

    # Standard normal: P90 = mean - 1.282·sigma
    p90_real = p50_real - 1.282 * sigma_anual
    p99_real = p50_real - 2.326 * sigma_anual

    return {
        "p50_actualizado_mwh": p50_real,
        "p90_actualizado_mwh": p90_real,
        "p99_actualizado_mwh": p99_real,
        "sigma_anual_mwh": float(sigma_anual),
        "p90_p50_ratio": float(p90_real / p50_real) if p50_real > 0 else float("nan"),
    }


def calcular_residuales_por_sector(df_compare, sector_col="sector"):
    """Si df_compare tiene sector, calcula bias por sector → detecta wake model bias."""
    if df_compare is None or sector_col not in df_compare.columns:
        return pd.DataFrame()
    grouped = df_compare.groupby(sector_col).agg({
        "residual_MW": ["mean", "std", "count"],
    })
    grouped.columns = ["bias_mean_MW", "bias_std_MW", "n"]
    return grouped.reset_index()
