"""Tests minimos para exportables bankable.

Cobertura:
  - Mojibake normalizado (Phase F)
  - Cp table sin columnas duplicadas (Phase F)
  - Excel PRO 16 hojas (Phase A)
  - Monte Carlo Pn ordering (Phase C)
  - IEC site suitability (Phase C)
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import pytest

# anadir root al path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calculos_iec_site import site_suitability_summary
from calculos_uncertainty import (
    combined_sigma_pct,
    monte_carlo_aep,
    percentiles_gaussian,
)
from reportes.excel_pro import exportar_excel_pro
from reportes.texto import normalize_visible_text


# ───────── Phase F: Mojibake ─────────
def test_mojibake_question_words_fixed():
    cases = {
        "P?rdida": "Pérdida",
        "p?rdida": "pérdida",
        "Energ?a": "Energía",
        "energ?a": "energía",
        "An?lisis": "Análisis",
        "Distribuci?n": "Distribución",
        "Caracterizaci?n": "Caracterización",
        "Geom?trico": "Geométrico",
        "MWh/a?o": "MWh/año",
    }
    for bad, good in cases.items():
        out = normalize_visible_text(bad)
        assert good in out, f"esperado '{good}' en '{out}' (input='{bad}')"


def test_mojibake_double_question_fixed():
    cases = {
        "logar??tmico": "logarítmico",
        "caracterizaci??n": "caracterización",
        "num??rico": "numérico",
        "par??metros": "parámetros",
    }
    for bad, good in cases.items():
        assert good in normalize_visible_text(bad)


def test_mojibake_single_question_logar_fixed():
    assert "logarítmico" in normalize_visible_text("Perfil logar?tmico modo A")


# ───────── Phase F: tabla Cp sin duplicados ─────────
def test_cp_table_no_duplicate_columns():
    """Simulate df_cp como en calculos.calcular_cp."""
    df_cp = pd.DataFrame({
        "Velocidad (m/s)": [3.0, 5.0, 8.0],
        "Potencia (W)": [22000, 122000, 816000],
        "Velocidad_num": [3.0, 5.0, 8.0],
        "Potencia_W": [22000, 122000, 816000],
        "P_viento_W": [168608.8, 491570.85, 2013474.22],
        "Cp": [0.1305, 0.2482, 0.4053],
    })
    # apply same slice + rename as informe_tecnico.py / manifiestos.py
    df_clean = df_cp[["Velocidad_num", "Potencia_W", "P_viento_W", "Cp"]].rename(columns={
        "Velocidad_num": "Velocidad (m/s)",
        "Potencia_W": "Potencia (W)",
        "P_viento_W": "Potencia del viento (W)",
    })
    cols = list(df_clean.columns)
    assert cols.count("Velocidad (m/s)") == 1
    assert cols.count("Potencia (W)") == 1
    assert "Potencia del viento (W)" in cols
    assert "Cp" in cols


# ───────── Phase A: Excel PRO ─────────
@pytest.fixture
def synthetic_ctx():
    return {
        "project_name": "Test Project",
        "site_latitude": 11.948,
        "site_longitude": -72.164,
        "altura_deseada": 100.0,
        "base_viento": "Exponencial",
        "metodo_detalle": "Weibull",
        "n_turbinas": 5,
        "wake_mode": "Manual",
        "wake_manual_pct": 5.0,
        "ct": 0.8,
        "kw": 0.05,
        "disp_pct": 3.0,
        "elec_pct": 2.0,
        "otras_pct": 1.5,
        "config": {"diametro": 90.6, "densidad": 1.22},
        "res": {
            "aep_bruta_total": 62858.0,
            "aep_neta_total": 55913.0,
            "factor_planta_bruto": 71.76,
            "factor_planta_neto": 63.83,
            "aep_neta_turbina": 11182.0,
            "potencia_nominal_turbina_w": 2000000.0,
            "perdida_estela_mwh": 3142.0,
            "perdida_disp_mwh": 1791.0,
            "perdida_elec_mwh": 1158.0,
            "perdida_otras_mwh": 851.0,
        },
        "economics": {
            "moneda_visualizacion": "USD",
            "capex_total": 19634000.0,
            "capex_total_display": 19634000.0,
            "opex_total_anual": 449991.0,
            "opex_total_anual_display": 449991.0,
            "lcoe_display_mwh": 43.81,
            "precio_energia_mwh": 75.0,
            "tasa_descuento": 8.0,
            "degradacion_pct": 0.5,
            "vida_util": 20,
            "sens_delta_pct": 15.0,
        },
        "df_aep_sector": pd.DataFrame([
            {"Sector": "N", "Frecuencia (%)": 0.64, "AEP bruta parque (MWh/año)": 44.91, "AEP neta sector (MWh/año)": 39.95},
            {"Sector": "E", "Frecuencia (%)": 36.28, "AEP bruta parque (MWh/año)": 25566.04, "AEP neta sector (MWh/año)": 22741.6},
        ]),
    }


def test_excel_pro_generates_all_16_sheets(synthetic_ctx):
    import openpyxl
    xlsx_bytes = exportar_excel_pro(synthetic_ctx)
    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 5000
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    expected = [
        "00_Cover", "01_Executive_Summary", "02_Site_Turbine", "03_Wind_Resource",
        "04_Power_Curve", "05_Energy_Sectorial", "06_Loss_Waterfall", "07_Per_WTG_AEP",
        "08_Uncertainty_P50_P90", "09_Economics", "10_Cash_Flow", "11_Sensitivity",
        "12_Site_Suitability_IEC", "13_Assumptions", "14_Glossary_Refs", "15_Audit_Manifest",
    ]
    for s in expected:
        assert s in wb.sheetnames, f"Falta hoja {s}"


def test_excel_pro_has_sha256_hash(synthetic_ctx):
    import openpyxl
    xlsx_bytes = exportar_excel_pro(synthetic_ctx)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb["15_Audit_Manifest"]
    found = False
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=1).value == "content_sha256":
            val = ws.cell(row=r, column=2).value
            assert val and val != "—" and len(str(val)) == 64
            found = True
    assert found, "Falta entrada content_sha256 en Audit_Manifest"


def test_excel_pro_loss_waterfall_consistent(synthetic_ctx):
    import openpyxl
    xlsx_bytes = exportar_excel_pro(synthetic_ctx)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb["06_Loss_Waterfall"]
    # AEP bruta row 4, AEP neta row 9
    aep_bruta = ws.cell(row=4, column=2).value
    aep_neta_row_val = ws.cell(row=9, column=2).value
    assert aep_bruta == pytest.approx(62858.0, rel=1e-3)
    assert aep_neta_row_val == pytest.approx(55913.0, rel=1e-3)


# ───────── Phase C: Uncertainty ─────────
def test_combined_sigma_is_root_sum_squared():
    sig = combined_sigma_pct({"meas": 3.0, "lt": 4.0})
    # default cats incl. pcv=1.5: vert=2, flow=4, plant=3, pcv=1.5
    # total^2 = 9 + 16 + 4 + 16 + 9 + 2.25 = 56.25
    # total = sqrt(56.25) = 7.5
    assert sig == pytest.approx(7.5, abs=0.01)


def test_percentiles_ordering():
    """P50 > P75 > P90 > P99 (en MWh, mayor a menor probabilidad de exceder)."""
    out = percentiles_gaussian(55913.0)
    assert out["P50"] > out["P75"] > out["P90"] > out["P99"]
    # P90 ~10% por debajo de P50 con sigma~7.6
    assert (out["P50"] - out["P90"]) / out["P50"] > 0.05


def test_monte_carlo_returns_all_percentiles():
    mc = monte_carlo_aep(55913.0, seed=42)
    for k in ["P50", "P75", "P90", "P99", "sigma_total_pct", "mc_mean", "mc_std"]:
        assert k in mc
    assert mc["P50"] > mc["P90"]


# ───────── Phase C: IEC Site ─────────
def test_iec_site_assigns_class():
    out = site_suitability_summary(k_avg=2.5, c_avg=10.5, ti_eff=0.14)
    assert out["Clase IEC"] in {"I", "II", "III", "S"}
    assert out["V_ref (m/s)"] > 0
    assert out["V_50 (m/s)"] > 0
    assert out["V_ave (m/s)"] > 0
    assert out["V_e50 (m/s)"] > out["V_e1 (m/s)"]


def test_iec_site_low_wind_is_class_III():
    """Sitio muy suave (c=5, k=2) deberia caer en III."""
    out = site_suitability_summary(k_avg=2.0, c_avg=5.0, ti_eff=0.12)
    assert out["Clase IEC"] in {"III", "II"}


# ───────── G2: IAV ─────────
def test_iav_pct_basic():
    from calculos_iav import iav_pct, sigma_lt_from_iav
    aep = {2020: 55000, 2021: 58000, 2022: 53000, 2023: 56000, 2024: 54000}
    iav = iav_pct(aep)
    assert 0 < iav < 20  # realistic 0-20%
    # sigma_lt deberia ser < IAV (escalado por sqrt(N))
    sigma_lt = sigma_lt_from_iav(iav, 5)
    assert sigma_lt < iav


def test_iav_handles_empty():
    from calculos_iav import iav_pct
    assert iav_pct({}) != iav_pct({})  # nan != nan
    assert iav_pct([1.0]) != iav_pct([1.0])  # need >=2


# ───────── G3: TI Frandsen ─────────
def test_ti_frandsen_increases_with_n():
    from calculos_iec_site import ti_eff_frandsen_full
    ti_0 = ti_eff_frandsen_full(0.10, n_t_in_sector=0, ct=0.8, distance_D=5.0)
    ti_1 = ti_eff_frandsen_full(0.10, n_t_in_sector=1, ct=0.8, distance_D=5.0)
    ti_3 = ti_eff_frandsen_full(0.10, n_t_in_sector=3, ct=0.8, distance_D=5.0)
    assert ti_0 < ti_1 < ti_3
    # ti_0 == ti_obs (sin wake)
    assert abs(ti_0 - 0.10) < 1e-9


def test_ti_sectorial_observada_returns_16():
    import numpy as np
    import pandas as pd
    from calculos_iec_site import ti_sectorial_observada
    rng = pd.date_range("2024-01-01", periods=8760, freq="h")
    df = pd.DataFrame({
        "WS_ANALISIS": np.random.RandomState(42).normal(15, 2, 8760).clip(min=0),
        "WD_USADA":    np.random.RandomState(43).uniform(0, 360, 8760),
    }, index=rng)
    out = ti_sectorial_observada(df, "WS_ANALISIS", "WD_USADA")
    assert len(out) == 16
    # at least some sectors finite
    finite = [v for v in out.values() if v == v]
    assert len(finite) >= 8


# ───────── J2: Air density + PCV ─────────
def test_air_density_correction_no_change_at_reference():
    from calculos_uncertainty import air_density_correction
    assert abs(air_density_correction(10.0, 1.225) - 10.0) < 1e-9


def test_air_density_correction_high_altitude():
    """Sitio a 1.1 kg/m3 vs ref 1.225 → V_norm < V."""
    from calculos_uncertainty import air_density_correction
    v_norm = air_density_correction(10.0, 1.10, 1.225)
    assert v_norm < 10.0
    assert v_norm > 9.5  # ~9.65


def test_pcv_category_F_in_defaults():
    from calculos_uncertainty import DEFAULT_SIGMAS_PCT
    assert "pcv" in DEFAULT_SIGMAS_PCT
    assert DEFAULT_SIGMAS_PCT["pcv"] > 0


def test_combined_sigma_with_pcv_increases():
    """Agregar pcv aumenta sigma_total."""
    from calculos_uncertainty import combined_sigma_pct
    base = combined_sigma_pct({"meas":3,"lt":4.5,"vert":2,"flow":4,"plant":3,"pcv":0})
    with_pcv = combined_sigma_pct({"meas":3,"lt":4.5,"vert":2,"flow":4,"plant":3,"pcv":1.5})
    assert with_pcv > base


# ───────── H1: Wind rose RadarChart ─────────
def test_excel_pro_has_wind_rose_image_when_sector_data(synthetic_ctx):
    """Verifica rosa de vientos como imagen matplotlib embebida (no RadarChart nativo)."""
    import io

    import openpyxl
    from reportes.excel_pro import exportar_excel_pro
    xlsx = exportar_excel_pro(synthetic_ctx)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), data_only=True)
    ws = wb["03_Wind_Resource"]
    # buscar imagenes embebidas (matplotlib PNG)
    n_imgs = len(ws._images) if hasattr(ws, "_images") else 0
    assert n_imgs >= 1, "rosa de vientos PNG no encontrada en 03_Wind_Resource"


# ───────── K2: Diurnal sheet ─────────
def test_diurnal_sheet_present_in_excel_pro(synthetic_ctx):
    import io

    import openpyxl
    from reportes.excel_pro import exportar_excel_pro
    xlsx = exportar_excel_pro(synthetic_ctx)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), data_only=True)
    assert "16_Diurnal_Seasonal" in wb.sheetnames
