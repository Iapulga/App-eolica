"""Excel profesional bankable — 16 hojas estilo WindPRO/WAsP/OpenWind.

Estructura:
  00_Cover                   Portada + Document Control
  01_Executive_Summary       KPIs P50/P90 + LCOE + CF
  02_Site_Turbine            Coords + WTG model + HH + D + densidad
  03_Wind_Resource           Stats horarias + k/A por sector + perfil vertical
  04_Power_Curve             Tabla v-P-Cp + grafico embebido
  05_Energy_Sectorial        Tabla sectorial completa (refactor de actual)
  06_Loss_Waterfall          Bruto -> wake -> disp -> elec -> otras -> Neto
  07_Per_WTG_AEP             Por turbina: x, y, v_libre, v_efec, AEP bruto/neto
  08_Uncertainty_P50_P90     Categorias sigma IEC 61400-15-2 + tabla P50/P75/P90/P99
  09_Economics               CAPEX/OPEX desglose por componente
  10_Cash_Flow               Anio 0..N: Revenue, OPEX, EBITDA, FCF, FCF desc, acum
  11_Sensitivity             Tornado: precio, AEP, CAPEX, OPEX, WACC
  12_Site_Suitability_IEC    V_ref, V_50, V_e1, V_e50, TI_eff vs CLASS
  13_Assumptions             Lista cerrada de supuestos
  14_Glossary_Refs           Acronimos + normas IEC/DNV/ISO + datasets
  15_Audit_Manifest          Hash SHA-256, timestamp UTC, version SMA

Uso:
    bytes_xlsx = exportar_excel_pro(ctx)

ctx = dict producido por Fase 5 (igual al usado por bankable.py).
"""

from __future__ import annotations

import hashlib
import io
import math
from datetime import UTC, datetime
from typing import Any

import pandas as pd

_NAVY = "1F4E79"
_WHITE = "FFFFFF"
_BAND = "E7EEF7"
_GREEN = "1F6E3B"
_RED = "8B1F1F"
_ORANGE = "D97706"
_BORDER_GRAY = "B7C0C7"

# Paleta SMA pro (matplotlib)
_MPL_PALETTE = {
    "navy":    "#1F4E79",
    "blue":    "#2E5C8A",
    "skyblue": "#5B8DBF",
    "lightbl": "#A4C5E5",
    "green":   "#1F6E3B",
    "lightgr": "#86EFAC",
    "red":     "#8B1F1F",
    "lightrd": "#FCA5A5",
    "orange":  "#D97706",
    "yellow":  "#FDE68A",
    "purple":  "#6B21A8",
    "teal":    "#0F766E",
    "slate":   "#475569",
    "grid":    "#E2E8F0",
}

_SECTOR_LABELS_ES = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _mpl_setup():
    """Configuracion matplotlib pro reutilizable."""
    try:
        import matplotlib as mpl
        import matplotlib.pyplot as plt
        mpl.rcParams.update({
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlecolor": _MPL_PALETTE["navy"],
            "axes.labelsize": 11,
            "axes.labelcolor": _MPL_PALETTE["slate"],
            "axes.edgecolor": "#94A3B8",
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": _MPL_PALETTE["grid"],
            "grid.linewidth": 0.6,
            "grid.alpha": 0.7,
            "xtick.color": _MPL_PALETTE["slate"],
            "ytick.color": _MPL_PALETTE["slate"],
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "legend.frameon": True,
            "legend.fancybox": True,
            "legend.framealpha": 0.92,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "savefig.edgecolor": "white",
        })
        return plt
    except ImportError:
        return None


def _mpl_to_png_bytes(fig, dpi=140):
    """matplotlib Figure → PNG bytes (BytesIO)."""
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none", pad_inches=0.18)
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def _add_png_to_ws(ws, png_bytes, anchor_cell, width_px=None, height_px=None):
    """Inserta PNG en hoja Excel via openpyxl Image."""
    try:
        from openpyxl.drawing.image import Image as XLImage
    except ImportError:
        return False
    if not png_bytes:
        return False
    try:
        img = XLImage(io.BytesIO(png_bytes))
        if width_px:
            img.width = width_px
        if height_px:
            img.height = height_px
        img.anchor = anchor_cell
        ws.add_image(img)
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# Helpers num/safe
# ─────────────────────────────────────────────────────────────
def _to_float(v, default=None):
    try:
        f = float(v)
        if f != f or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe(d, key, default=None):
    if d is None:
        return default
    if isinstance(d, dict):
        return d.get(key, default) if d.get(key) is not None else default
    return getattr(d, key, default) or default


# ─────────────────────────────────────────────────────────────
# Style helpers
# ─────────────────────────────────────────────────────────────
def _styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    thin = Side(style="thin", color=_BORDER_GRAY)
    return {
        "header_fill": PatternFill("solid", fgColor=_NAVY),
        "header_font": Font(name="Calibri", size=11, bold=True, color=_WHITE),
        "header_align": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "band_fill": PatternFill("solid", fgColor=_BAND),
        "border": Border(left=thin, right=thin, top=thin, bottom=thin),
        "title_font": Font(name="Calibri", size=18, bold=True, color=_NAVY),
        "h2_font": Font(name="Calibri", size=13, bold=True, color=_NAVY),
        "kpi_label_font": Font(name="Calibri", size=11, bold=True, color=_NAVY),
        "kpi_value_font": Font(name="Calibri", size=11),
        "right_align": Alignment(horizontal="right", vertical="center"),
        "center_align": Alignment(horizontal="center", vertical="center"),
        "left_wrap": Alignment(horizontal="left", vertical="top", wrap_text=True),
    }


def _format_for_col(col_name: str) -> str | None:
    """Numero format SIEMPRE 2 decimales (legibilidad pro)."""
    low = str(col_name).lower()
    if "(%)" in low or "pct" in low or "porcentaje" in low or "factor" in low:
        return "0.00"
    if "mwh" in low or "kwh" in low or "energia" in low or "aep" in low:
        return "#,##0.00"
    if "(w)" in low or "(kw)" in low or "potencia" in low:
        return "#,##0.00"
    if "(m/s)" in low or "velocidad" in low or "v_" in low:
        return "0.00"
    if "(°)" in low or "(deg)" in low or "direcc" in low or "centro" in low:
        return "0.00"
    if "capex" in low or "opex" in low or "lcoe" in low or "vp " in low or "ebitda" in low or "fcf" in low or "revenue" in low or "ingreso" in low or "usd" in low or "cop" in low:
        return "#,##0.00"
    if "horas" in low:
        return "#,##0.00"
    if "anio" in low or "año" in low or "year" in low:
        return "0"
    # default: 2 decimales
    return "#,##0.00"


def _apply_df_to_sheet(ws, df: pd.DataFrame, start_row: int = 1, start_col: int = 1, freeze: bool = True, autofilter: bool = True):
    s = _styles()
    if df is None or df.empty:
        return start_row
    headers = list(df.columns)
    # write header
    for j, h in enumerate(headers):
        c = ws.cell(row=start_row, column=start_col + j, value=str(h))
        c.fill = s["header_fill"]
        c.font = s["header_font"]
        c.alignment = s["header_align"]
        c.border = s["border"]
    # write body
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        for j, h in enumerate(headers):
            v = row[h]
            if isinstance(v, float) and (v != v or math.isinf(v)):
                v = None
            cell = ws.cell(row=start_row + i, column=start_col + j, value=v)
            cell.border = s["border"]
            if i % 2 == 0:
                cell.fill = s["band_fill"]
            fmt = _format_for_col(h)
            if fmt and isinstance(v, (int, float)):
                cell.number_format = fmt
                cell.alignment = s["right_align"]
    end_row = start_row + len(df)
    # auto-width
    for j, h in enumerate(headers):
        col_letter = ws.cell(row=start_row, column=start_col + j).column_letter
        try:
            sample_values = [str(ws.cell(row=start_row + r, column=start_col + j).value or "") for r in range(0, min(50, len(df) + 1))]
            max_len = max([len(str(h))] + [len(v) for v in sample_values])
        except Exception:
            max_len = len(str(h))
        ws.column_dimensions[col_letter].width = min(max(12, max_len + 2), 48)
    # freeze + autofilter
    if freeze:
        ws.freeze_panes = ws.cell(row=start_row + 1, column=start_col)
    if autofilter and len(df) > 0:
        first = ws.cell(row=start_row, column=start_col).coordinate
        last = ws.cell(row=end_row, column=start_col + len(headers) - 1).coordinate
        ws.auto_filter.ref = f"{first}:{last}"
    return end_row


def _write_kpi_block(ws, rows: list[tuple], start_row: int = 1, title: str | None = None) -> int:
    s = _styles()
    r = start_row
    if title:
        ws.cell(row=r, column=1, value=title).font = s["h2_font"]
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        r += 1
    ws.cell(row=r, column=1, value="Indicador").font = s["header_font"]
    ws.cell(row=r, column=1).fill = s["header_fill"]
    ws.cell(row=r, column=1).alignment = s["header_align"]
    ws.cell(row=r, column=2, value="Valor").font = s["header_font"]
    ws.cell(row=r, column=2).fill = s["header_fill"]
    ws.cell(row=r, column=2).alignment = s["header_align"]
    ws.cell(row=r, column=1).border = s["border"]
    ws.cell(row=r, column=2).border = s["border"]
    r += 1
    for label, val in rows:
        c1 = ws.cell(row=r, column=1, value=str(label))
        c2 = ws.cell(row=r, column=2, value=val)
        c1.font = s["kpi_label_font"]
        c1.border = s["border"]
        c2.border = s["border"]
        if isinstance(val, (int, float)):
            fmt = _format_for_col(label)
            if fmt:
                c2.number_format = fmt
            c2.alignment = s["right_align"]
        else:
            c2.alignment = s["left_wrap"]
        r += 1
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 28
    return r


# ─────────────────────────────────────────────────────────────
# Sheets
# ─────────────────────────────────────────────────────────────
def _sheet_cover(wb, ctx):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    s = _styles()
    ws = wb.create_sheet("00_Cover")
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 56
    ws.column_dimensions["C"].width = 4
    ws.column_dimensions["D"].width = 4
    # Banner navy
    banner_fill = PatternFill("solid", fgColor="1F4E79")
    title_font = Font(name="Calibri", size=22, bold=True, color="FFFFFF")
    subtitle_font = Font(name="Calibri", size=12, italic=True, color="C5D2E0")
    for col in range(1, 5):
        c = ws.cell(row=1, column=col)
        c.fill = banner_fill
    ws.cell(row=1, column=1, value="INFORME TÉCNICO — EVALUACIÓN DE RENDIMIENTO ENERGÉTICO").font = title_font
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    ws.row_dimensions[1].height = 42
    # Subtitle row
    for col in range(1, 5):
        c = ws.cell(row=2, column=col)
        c.fill = PatternFill("solid", fgColor="E7EEF7")
    ws.cell(row=2, column=1, value=f"Proyecto: {_safe(ctx, 'project_name', 'Proyecto eólico')}  ·  SMA 2.0 — Generador de informes bankable").font = subtitle_font
    ws.cell(row=2, column=1).alignment = Alignment(horizontal="center", vertical="center")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=4)
    ws.row_dimensions[2].height = 24
    # Spacer
    ws.row_dimensions[3].height = 12
    ws.cell(row=4, column=1, value="Document Control").font = s["h2_font"]

    proj = _safe(ctx, "project_name", "Proyecto eólico")
    md = ctx.get("manifest_metadata") if isinstance(ctx, dict) else {}
    md = md or {}
    rows = [
        ("Proyecto", proj),
        ("País", _safe(md, "country_nombre", _safe(ctx, "country_nombre", "—"))),
        ("Latitud sitio", _safe(ctx, "site_latitude", "—")),
        ("Longitud sitio", _safe(ctx, "site_longitude", "—")),
        ("Documento ID", _safe(md, "doc_id", f"SMA-EYA-{datetime.now(UTC).strftime('%Y%m%d')}-001")),
        ("Revisión", _safe(md, "revision", "Rev 1.0")),
        ("Fecha generación (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")),
        ("Autor", "SMA 2.0 (auto-generado)"),
        ("Revisor", _safe(md, "revisor", "[pendiente]")),
        ("Aprobador", _safe(md, "aprobador", "[pendiente]")),
        ("Estado", _safe(md, "estado", "Borrador")),
        ("Confidencialidad", "Confidencial — distribución restringida"),
    ]
    _write_kpi_block(ws, rows, start_row=5, title=None)

    ws.cell(row=21, column=1, value="Disclaimer").font = s["h2_font"]
    discl = ws.cell(row=22, column=1, value=(
        "Este documento es generado automáticamente por SMA 2.0 a partir de los datos configurados "
        "en la herramienta y fuentes externas como NASA POWER. NO sustituye un EYA bankable de tercera "
        "parte certificada (DNV/UL/TÜV). Los valores P50/P90 son indicativos. Para project finance "
        "se requiere validación independiente, campaña de medición con torre meteorológica ≥12 meses "
        "y MCP long-term ≥10 años (ERA5/MERRA-2). Ver hoja 14_Glossary_Refs."
    ))
    discl.alignment = s["left_wrap"]
    discl.fill = PatternFill("solid", fgColor="FEF3C7")  # amarillo suave para destacar disclaimer
    discl.font = Font(name="Calibri", size=10, italic=True)
    ws.merge_cells(start_row=22, start_column=1, end_row=26, end_column=4)
    ws.row_dimensions[22].height = 80
    return ws


def _sheet_exec_summary(wb, ctx):
    ws = wb.create_sheet("01_Executive_Summary")
    res = ctx.get("res", {}) if isinstance(ctx, dict) else {}
    econ = ctx.get("economics", {}) if isinstance(ctx, dict) else {}
    aep_bruta = _to_float(res.get("aep_bruta_total"))
    aep_neta = _to_float(res.get("aep_neta_total"))
    cf_bruto = _to_float(res.get("factor_planta_bruto"))
    cf_neto = _to_float(res.get("factor_planta_neto"))
    n_t = _to_float(ctx.get("n_turbinas") if isinstance(ctx, dict) else None)
    p_nom_kw = _to_float(res.get("potencia_nominal_turbina_w"))
    if p_nom_kw is not None:
        p_nom_kw = p_nom_kw / 1000.0
    p_inst_mw = (p_nom_kw * n_t / 1000.0) if (p_nom_kw and n_t) else None
    p50 = aep_neta
    sigma_pct = _to_float(ctx.get("sigma_total_pct"), 10.0) or 10.0
    p75 = (aep_neta * (1 - 0.6745 * sigma_pct / 100.0)) if aep_neta else None
    p90 = (aep_neta * (1 - 1.2816 * sigma_pct / 100.0)) if aep_neta else None
    p99 = (aep_neta * (1 - 2.3263 * sigma_pct / 100.0)) if aep_neta else None
    currency = _safe(econ, "moneda_visualizacion", _safe(econ, "moneda_base", "USD"))
    rows = [
        ("Método principal", _safe(ctx, "metodo_detalle", "Weibull")),
        ("Potencia nominal por turbina (kW)", p_nom_kw),
        ("Número de turbinas", n_t),
        ("Potencia instalada (MW)", p_inst_mw),
        ("AEP bruta parque (MWh/año)", aep_bruta),
        ("AEP neta P50 parque (MWh/año)", p50),
        ("AEP neta P75 parque (MWh/año)", p75),
        ("AEP neta P90 parque (MWh/año)", p90),
        ("AEP neta P99 parque (MWh/año)", p99),
        ("Factor de planta bruto (%)", cf_bruto),
        ("Factor de planta neto (%)", cf_neto),
        (f"CAPEX total ({currency})", _to_float(_safe(econ, "capex_total_display", _safe(econ, "capex_total")))),
        (f"OPEX anual ({currency})", _to_float(_safe(econ, "opex_total_anual_display", _safe(econ, "opex_total_anual")))),
        (f"LCOE ({currency}/MWh)", _to_float(_safe(econ, "lcoe_display_mwh", _safe(econ, "lcoe_mwh")))),
        (f"NPV ({currency})", _to_float(_safe(econ, "npv"))),
        ("IRR (%)", _to_float(_safe(econ, "irr_pct"))),
        ("Payback simple (años)", _to_float(_safe(econ, "payback_simple"))),
        ("Sigma total uncertainty (%)", sigma_pct),
    ]
    _write_kpi_block(ws, rows, start_row=1, title="Resumen ejecutivo (KPIs principales)")
    return ws


def _sheet_site_turbine(wb, ctx):
    ws = wb.create_sheet("02_Site_Turbine")
    cfg = ctx.get("config", {}) if isinstance(ctx, dict) else {}
    res = ctx.get("res", {}) if isinstance(ctx, dict) else {}
    rows = [
        ("Latitud", _safe(ctx, "site_latitude", _safe(cfg, "nasa_lat"))),
        ("Longitud", _safe(ctx, "site_longitude", _safe(cfg, "nasa_lon"))),
        ("Fuente de datos", _safe(ctx, "site_source", "NASA POWER API")),
        ("Periodo inicio", _safe(ctx, "site_start_date", _safe(cfg, "nasa_inicio"))),
        ("Periodo fin", _safe(ctx, "site_end_date", _safe(cfg, "nasa_fin"))),
        ("Diámetro rotor (m)", _to_float(cfg.get("diametro"))),
        ("Densidad del aire (kg/m³)", _to_float(cfg.get("densidad"))),
        ("Altura objetivo (m)", _to_float(ctx.get("altura_deseada"))),
        ("Modelo perfil viento", _safe(ctx, "base_viento", "Exponencial")),
        ("Rugosidad terreno", _safe(ctx, "roughness_label", "—")),
        ("Potencia nominal turbina (kW)", (_to_float(res.get("potencia_nominal_turbina_w")) or 0) / 1000.0),
        ("Número de turbinas", _to_float(ctx.get("n_turbinas"))),
    ]
    _write_kpi_block(ws, rows, start_row=1, title="Sitio y configuración del aerogenerador")
    return ws


def _mpl_rosa_vientos(df_sector, kind="frecuencia"):
    """Rosa de vientos polar matplotlib. kind in {'frecuencia', 'velocidad'}."""
    plt = _mpl_setup()
    if plt is None or df_sector is None or len(df_sector) == 0:
        return None
    import numpy as np
    cols_lower = {c.lower(): c for c in df_sector.columns}
    sec_col = cols_lower.get("sector")
    if sec_col is None:
        return None
    if kind == "frecuencia":
        val_col = None
        for c in df_sector.columns:
            if "frecuencia" in c.lower() and "%" in c:
                val_col = c; break
        if val_col is None:
            return None
        title = "Rosa de vientos — Frecuencia direccional"
        unit = "%"
        color = _MPL_PALETTE["navy"]
    else:
        val_col = None
        for c in df_sector.columns:
            if "velocidad media" in c.lower():
                val_col = c; break
        if val_col is None:
            return None
        title = "Rosa de vientos — Velocidad media por sector"
        unit = "m/s"
        color = _MPL_PALETTE["green"]

    sectors = df_sector[sec_col].astype(str).tolist()
    values = df_sector[val_col].astype(float).fillna(0).tolist()
    n = len(sectors)
    if n == 0:
        return None
    # Asegurar 16 sectores en orden estandar
    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    width = 2 * np.pi / n
    fig = plt.figure(figsize=(8, 8), dpi=140)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    bars = ax.bar(theta, values, width=width * 0.9, bottom=0,
                  color=color, edgecolor="white", linewidth=1.2, alpha=0.85)
    # Etiquetar valor por sector
    max_v = max(values) if values else 1
    for ang, val, bar in zip(theta, values, bars):
        if val > 0:
            ax.text(ang, val + max_v * 0.05,
                    f"{val:.1f}{unit if kind == 'velocidad' else ''}",
                    ha="center", va="center", fontsize=7,
                    color=_MPL_PALETTE["navy"], fontweight="bold")
    ax.set_xticks(theta)
    ax.set_xticklabels(sectors, fontsize=10, color=_MPL_PALETTE["slate"], fontweight="bold")
    ax.tick_params(axis="y", labelsize=8, colors=_MPL_PALETTE["slate"])
    ax.grid(True, alpha=0.4)
    ax.set_title(f"{title} ({unit})", fontsize=14, fontweight="bold",
                 color=_MPL_PALETTE["navy"], pad=22)
    fig.tight_layout()
    return _mpl_to_png_bytes(fig, dpi=140)


def _sheet_wind_resource(wb, ctx):
    ws = wb.create_sheet("03_Wind_Resource")
    df_sector = ctx.get("df_aep_sector") if isinstance(ctx, dict) else None
    df_extra = ctx.get("df_resumen_sectorial") if isinstance(ctx, dict) else None
    s = _styles()
    ws.cell(row=1, column=1, value="Recurso eólico — Distribución sectorial Weibull").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)

    df_chart = df_extra if (df_extra is not None and len(df_extra) > 0) else df_sector
    if df_chart is not None and len(df_chart) > 0:
        end_row = _apply_df_to_sheet(ws, df_chart, start_row=3, start_col=1)
        anchor_col = ws.cell(row=3, column=len(df_chart.columns) + 2).column_letter
        # Rosa frecuencia
        png_freq = _mpl_rosa_vientos(df_chart, kind="frecuencia")
        if png_freq:
            _add_png_to_ws(ws, png_freq, f"{anchor_col}3", width_px=440, height_px=440)
        # Rosa velocidad (debajo)
        png_vel = _mpl_rosa_vientos(df_chart, kind="velocidad")
        if png_vel:
            _add_png_to_ws(ws, png_vel, f"{anchor_col}26", width_px=440, height_px=440)
    else:
        ws.cell(row=3, column=1, value="Sin datos sectoriales disponibles.").font = s["kpi_value_font"]
    return ws


def _mpl_curva_potencia(df_curva, df_cp=None):
    """Curva de potencia con Cp opcional en eje secundario."""
    plt = _mpl_setup()
    if plt is None or df_curva is None or len(df_curva) == 0:
        return None
    df = df_curva.copy()
    if "Velocidad_num" in df.columns and "Velocidad (m/s)" not in df.columns:
        df = df.rename(columns={"Velocidad_num": "Velocidad (m/s)", "Potencia_W": "Potencia (W)"})
    if "Velocidad (m/s)" not in df.columns or "Potencia (W)" not in df.columns:
        return None
    v = df["Velocidad (m/s)"].astype(float).tolist()
    p_kw = [float(x) / 1000.0 for x in df["Potencia (W)"]]
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    ax.plot(v, p_kw, color=_MPL_PALETTE["navy"], lw=2.6, marker="o",
            markersize=6, markerfacecolor=_MPL_PALETTE["orange"],
            markeredgecolor="white", markeredgewidth=1.2,
            label="Potencia eléctrica")
    ax.fill_between(v, 0, p_kw, alpha=0.18, color=_MPL_PALETTE["skyblue"])
    ax.set_xlabel("Velocidad del viento (m/s)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Potencia (kW)", fontsize=11, fontweight="bold", color=_MPL_PALETTE["navy"])
    ax.tick_params(axis="y", colors=_MPL_PALETTE["navy"])
    ax.set_title("Curva de potencia del aerogenerador",
                 fontsize=14, fontweight="bold", color=_MPL_PALETTE["navy"], pad=14)
    p_max = max(p_kw) if p_kw else 0
    if p_max > 0:
        ax.axhline(p_max, color=_MPL_PALETTE["red"], lw=1.0, ls="--", alpha=0.6)
        ax.text(max(v) * 0.98, p_max * 1.02, f"P nominal ≈ {p_max:,.0f} kW",
                ha="right", fontsize=9, color=_MPL_PALETTE["red"], fontweight="bold")
    ax.grid(True, alpha=0.3, color=_MPL_PALETTE["grid"])
    ax.spines[["top", "right"]].set_visible(False)
    # Cp en eje secundario
    if df_cp is not None and len(df_cp) > 0 and "Cp" in df_cp.columns:
        ax2 = ax.twinx()
        v_cp = df_cp.get("Velocidad_num", df_cp.get("Velocidad (m/s)")).astype(float).tolist()
        cp_vals = df_cp["Cp"].astype(float).tolist()
        ax2.plot(v_cp, cp_vals, color=_MPL_PALETTE["green"], lw=2.2, ls="-",
                 marker="s", markersize=5, markerfacecolor=_MPL_PALETTE["lightgr"],
                 markeredgecolor=_MPL_PALETTE["green"], label="Coeficiente Cp")
        ax2.set_ylabel("Coeficiente Cp (-)", fontsize=11, fontweight="bold",
                       color=_MPL_PALETTE["green"])
        ax2.tick_params(axis="y", colors=_MPL_PALETTE["green"])
        ax2.set_ylim(0, max(0.6, max(cp_vals) * 1.2) if cp_vals else 0.6)
        ax2.spines[["top"]].set_visible(False)
        # Leyenda combinada
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
                  fontsize=10, framealpha=0.95)
    else:
        ax.legend(loc="upper left", fontsize=10)
    fig.tight_layout()
    return _mpl_to_png_bytes(fig)


def _sheet_power_curve(wb, ctx):
    ws = wb.create_sheet("04_Power_Curve")
    df_curva = ctx.get("df_curva") if isinstance(ctx, dict) else None
    df_cp = ctx.get("df_cp") if isinstance(ctx, dict) else None
    s = _styles()
    ws.cell(row=1, column=1, value="Curva de potencia del aerogenerador y Cp calculado").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)

    end_row = 3
    if df_curva is not None and len(df_curva) > 0:
        df_curva_clean = df_curva.copy()
        if "Velocidad_num" in df_curva_clean.columns and "Velocidad (m/s)" not in df_curva_clean.columns:
            df_curva_clean = df_curva_clean.rename(columns={"Velocidad_num": "Velocidad (m/s)", "Potencia_W": "Potencia (W)"})
        end_row = _apply_df_to_sheet(ws,
            df_curva_clean[["Velocidad (m/s)", "Potencia (W)"]] if "Velocidad (m/s)" in df_curva_clean.columns else df_curva_clean,
            start_row=3)
        # Grafica matplotlib (no mas chart nativo)
        png_curva = _mpl_curva_potencia(df_curva, df_cp)
        if png_curva:
            _add_png_to_ws(ws, png_curva, "D3", width_px=820, height_px=410)
        end_row += 2

    if df_cp is not None and len(df_cp) > 0:
        df_cp_clean = df_cp[["Velocidad_num", "Potencia_W", "P_viento_W", "Cp"]].rename(columns={"Velocidad_num": "Velocidad (m/s)", "Potencia_W": "Potencia (W)", "P_viento_W": "Potencia del viento (W)"}) if "Velocidad_num" in df_cp.columns else df_cp
        ws.cell(row=end_row + 20, column=1, value="Cp calculado").font = s["h2_font"]
        end_row = _apply_df_to_sheet(ws, df_cp_clean, start_row=end_row + 21)
    return ws


def _mpl_aep_sectorial(df_sector):
    """Bar chart AEP bruto vs neto por sector."""
    plt = _mpl_setup()
    if plt is None or df_sector is None or len(df_sector) == 0:
        return None
    import numpy as np
    cols_l = {c.lower(): c for c in df_sector.columns}
    sec_col = cols_l.get("sector")
    bruta_col = None; neta_col = None
    for c in df_sector.columns:
        cl = c.lower()
        if "aep bruta" in cl and "parque" in cl:
            bruta_col = c
        elif "aep neta" in cl and "sector" in cl:
            neta_col = c
    if sec_col is None or bruta_col is None:
        return None
    sectors = df_sector[sec_col].astype(str).tolist()
    bruta = df_sector[bruta_col].astype(float).fillna(0).tolist()
    neta = df_sector[neta_col].astype(float).fillna(0).tolist() if neta_col else None
    x = np.arange(len(sectors))
    w = 0.42 if neta is not None else 0.7
    fig, ax = plt.subplots(figsize=(12, 5.5), dpi=140)
    ax.bar(x - w/2 if neta else x, bruta, width=w,
           color=_MPL_PALETTE["navy"], edgecolor="white", linewidth=0.6,
           label="AEP bruta (MWh/año)")
    if neta is not None:
        ax.bar(x + w/2, neta, width=w,
               color=_MPL_PALETTE["green"], edgecolor="white", linewidth=0.6,
               label="AEP neta (MWh/año)")
    ax.set_xticks(x)
    ax.set_xticklabels(sectors, fontsize=10, fontweight="bold", color=_MPL_PALETTE["slate"])
    ax.set_xlabel("Sector direccional", fontsize=11, fontweight="bold")
    ax.set_ylabel("Energía anual (MWh/año)", fontsize=11, fontweight="bold")
    ax.set_title("Producción energética por sector direccional",
                 fontsize=14, fontweight="bold", color=_MPL_PALETTE["navy"], pad=12)
    ax.grid(True, axis="y", alpha=0.35, color=_MPL_PALETTE["grid"])
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.95)
    ax.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, p: f"{v:,.0f}"))
    fig.tight_layout()
    return _mpl_to_png_bytes(fig)


def _sheet_energy_sectorial(wb, ctx):
    ws = wb.create_sheet("05_Energy_Sectorial")
    df_sector = ctx.get("df_aep_sector") if isinstance(ctx, dict) else None
    s = _styles()
    ws.cell(row=1, column=1, value="Energía sectorial — AEP por dirección").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=10)
    if df_sector is not None and len(df_sector) > 0:
        end_row = _apply_df_to_sheet(ws, df_sector, start_row=3)
        png = _mpl_aep_sectorial(df_sector)
        if png:
            _add_png_to_ws(ws, png, f"A{end_row + 3}", width_px=900, height_px=410)
    else:
        ws.cell(row=3, column=1, value="Sin datos sectoriales.").font = s["kpi_value_font"]
    return ws


def _mpl_loss_waterfall(aep_b, pe, pd_disp, pe_elec, pe_otras, aep_n):
    """Cascada de perdidas profesional (waterfall real)."""
    plt = _mpl_setup()
    if plt is None:
        return None
    import numpy as np
    labels = ["AEP bruta", "Estelas", "Disponibilidad", "Eléctricas", "Otras", "AEP neta P50"]
    values = [aep_b, -pe, -pd_disp, -pe_elec, -pe_otras, aep_n]
    bases = [0, aep_b - pe, aep_b - pe - pd_disp, aep_b - pe - pd_disp - pe_elec, aep_n, 0]
    # Cumulative for floating bars
    cumul = [0]
    for v in values[1:-1]:
        cumul.append(cumul[-1] + values[0] if cumul[-1] == 0 else cumul[-1])
    # Properly: each loss bar starts at running_total and goes down
    running = aep_b
    bar_bases = [0]      # AEP bruta: from 0 to aep_b
    bar_heights = [aep_b]
    for v in [-pe, -pd_disp, -pe_elec, -pe_otras]:
        bar_bases.append(running + v)  # bottom of bar = new running
        bar_heights.append(-v)         # height = |loss|
        running += v
    bar_bases.append(0)
    bar_heights.append(aep_n)
    colors_bar = [_MPL_PALETTE["green"], _MPL_PALETTE["red"], _MPL_PALETTE["red"],
                  _MPL_PALETTE["red"], _MPL_PALETTE["red"], _MPL_PALETTE["navy"]]

    fig, ax = plt.subplots(figsize=(12, 6), dpi=140)
    x = np.arange(len(labels))
    bars = ax.bar(x, bar_heights, bottom=bar_bases, color=colors_bar,
                  edgecolor="white", linewidth=1.0, width=0.65)
    # Etiquetas valor encima/dentro
    for i, (b, h) in enumerate(zip(bar_bases, bar_heights)):
        ypos = b + h + max(aep_b, 1) * 0.02
        if i in [0, len(labels) - 1]:
            ax.text(i, ypos, f"{(b + h):,.0f}",
                    ha="center", fontsize=10, fontweight="bold", color=colors_bar[i])
        else:
            ax.text(i, b + h / 2.0, f"-{h:,.0f}\n({h / aep_b * 100:.1f}%)" if aep_b else f"-{h:,.0f}",
                    ha="center", va="center", fontsize=9, fontweight="bold", color="white")
    # Lineas conectoras
    for i in range(len(labels) - 1):
        y = bar_bases[i] + bar_heights[i] if i == 0 else bar_bases[i]
        if i in [0, 1, 2, 3]:
            y_top = bar_bases[i] + bar_heights[i] if i == 0 else bar_bases[i] + bar_heights[i]
            ax.plot([i + 0.32, i + 1 - 0.32], [bar_bases[i + 1] + bar_heights[i + 1] if i == 0 else bar_bases[i + 1] + bar_heights[i + 1], bar_bases[i + 1] + bar_heights[i + 1]], "k--", lw=0.5, alpha=0.4)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10, fontweight="bold", color=_MPL_PALETTE["slate"])
    ax.set_ylabel("AEP (MWh/año)", fontsize=11, fontweight="bold")
    ax.set_title("Cascada de pérdidas energéticas — IEC 61400-15-2",
                 fontsize=14, fontweight="bold", color=_MPL_PALETTE["navy"], pad=14)
    ax.grid(True, axis="y", alpha=0.35, color=_MPL_PALETTE["grid"])
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, p: f"{v:,.0f}"))
    ax.set_ylim(0, aep_b * 1.15 if aep_b else 1)
    fig.tight_layout()
    return _mpl_to_png_bytes(fig)


def _sheet_loss_waterfall(wb, ctx):
    ws = wb.create_sheet("06_Loss_Waterfall")
    s = _styles()
    res = ctx.get("res", {}) if isinstance(ctx, dict) else {}
    aep_b = _to_float(res.get("aep_bruta_total")) or 0.0
    pe = _to_float(res.get("perdida_estela_mwh")) or 0.0
    pd_disp = _to_float(res.get("perdida_disp_mwh")) or 0.0
    pe_elec = _to_float(res.get("perdida_elec_mwh")) or 0.0
    pe_otras = _to_float(res.get("perdida_otras_mwh")) or 0.0
    aep_n = aep_b - pe - pd_disp - pe_elec - pe_otras

    ws.cell(row=1, column=1, value="Cascada de pérdidas — IEC 61400-15-2").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)

    df = pd.DataFrame([
        {"Etapa": "AEP bruta", "Valor (MWh/año)": aep_b, "Pérdida (%)": 0.0, "AEP acumulada (MWh/año)": aep_b},
        {"Etapa": "Estelas (wake)", "Valor (MWh/año)": -pe, "Pérdida (%)": (pe / aep_b * 100.0) if aep_b else 0.0, "AEP acumulada (MWh/año)": aep_b - pe},
        {"Etapa": "Disponibilidad", "Valor (MWh/año)": -pd_disp, "Pérdida (%)": (pd_disp / aep_b * 100.0) if aep_b else 0.0, "AEP acumulada (MWh/año)": aep_b - pe - pd_disp},
        {"Etapa": "Eléctricas", "Valor (MWh/año)": -pe_elec, "Pérdida (%)": (pe_elec / aep_b * 100.0) if aep_b else 0.0, "AEP acumulada (MWh/año)": aep_b - pe - pd_disp - pe_elec},
        {"Etapa": "Otras", "Valor (MWh/año)": -pe_otras, "Pérdida (%)": (pe_otras / aep_b * 100.0) if aep_b else 0.0, "AEP acumulada (MWh/año)": aep_n},
        {"Etapa": "AEP neta P50", "Valor (MWh/año)": aep_n, "Pérdida (%)": ((aep_b - aep_n) / aep_b * 100.0) if aep_b else 0.0, "AEP acumulada (MWh/año)": aep_n},
    ])
    end_row = _apply_df_to_sheet(ws, df, start_row=3)
    png = _mpl_loss_waterfall(aep_b, pe, pd_disp, pe_elec, pe_otras, aep_n)
    if png:
        _add_png_to_ws(ws, png, "F3", width_px=900, height_px=440)
    return ws


def _mpl_pie_breakdown(title, components):
    """Pie chart con % en cada slice + leyenda lateral."""
    plt = _mpl_setup()
    if plt is None or not components:
        return None
    items = [(k, float(v)) for k, v in components.items() if float(v) > 0]
    if not items:
        return None
    labels = [k for k, _ in items]
    vals = [v for _, v in items]
    palette = [_MPL_PALETTE["navy"], _MPL_PALETTE["skyblue"], _MPL_PALETTE["green"],
               _MPL_PALETTE["orange"], _MPL_PALETTE["purple"], _MPL_PALETTE["teal"],
               _MPL_PALETTE["lightbl"], _MPL_PALETTE["yellow"], _MPL_PALETTE["red"]]
    colors = [palette[i % len(palette)] for i in range(len(items))]
    fig, ax = plt.subplots(figsize=(9, 6.5), dpi=140)
    total = sum(vals)
    wedges, _, autotexts = ax.pie(
        vals,
        labels=None,
        autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
        startangle=90, colors=colors,
        pctdistance=0.72,
        wedgeprops=dict(edgecolor="white", linewidth=2),
        textprops={"fontsize": 10, "fontweight": "bold"},
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontweight("bold")
    # Leyenda lateral con valores
    legend_labels = [f"{lbl}: {v:,.0f} ({v / total * 100:.1f}%)" for lbl, v in zip(labels, vals)]
    ax.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1.05, 0.5),
              fontsize=10, frameon=False)
    ax.set_title(title, fontsize=13, fontweight="bold",
                 color=_MPL_PALETTE["navy"], pad=14)
    fig.tight_layout()
    return _mpl_to_png_bytes(fig)


def _mpl_per_wtg(turbinas, aep_vals, aep_promedio=None):
    """Bar chart vertical AEP por turbina con linea promedio."""
    plt = _mpl_setup()
    if plt is None or not turbinas:
        return None
    import numpy as np
    x = np.arange(len(turbinas))
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=140)
    bars = ax.bar(x, aep_vals, width=0.65,
                  color=_MPL_PALETTE["navy"], edgecolor="white", linewidth=1.0,
                  label="AEP neta por turbina")
    # Gradient color por valor
    if max(aep_vals) > min(aep_vals):
        rng = max(aep_vals) - min(aep_vals)
        for bar, v in zip(bars, aep_vals):
            ratio = (v - min(aep_vals)) / rng if rng > 0 else 0.5
            if ratio > 0.66:
                bar.set_color(_MPL_PALETTE["green"])
            elif ratio > 0.33:
                bar.set_color(_MPL_PALETTE["skyblue"])
            else:
                bar.set_color(_MPL_PALETTE["red"])
    for bar, v in zip(bars, aep_vals):
        ax.text(bar.get_x() + bar.get_width() / 2.0, v + max(aep_vals) * 0.015,
                f"{v:,.0f}", ha="center", va="bottom", fontsize=9,
                fontweight="bold", color=_MPL_PALETTE["navy"])
    if aep_promedio:
        ax.axhline(aep_promedio, color=_MPL_PALETTE["orange"], lw=1.6, ls="--",
                   label=f"Promedio: {aep_promedio:,.0f} MWh/año")
        ax.legend(loc="upper right", fontsize=10, framealpha=0.95)
    ax.set_xticks(x)
    ax.set_xticklabels(turbinas, fontsize=10, fontweight="bold", color=_MPL_PALETTE["slate"])
    ax.set_xlabel("Aerogenerador", fontsize=11, fontweight="bold")
    ax.set_ylabel("AEP neta anual (MWh/año)", fontsize=11, fontweight="bold")
    ax.set_title("Producción energética anual estimada por aerogenerador",
                 fontsize=14, fontweight="bold", color=_MPL_PALETTE["navy"], pad=14)
    ax.grid(True, axis="y", alpha=0.35, color=_MPL_PALETTE["grid"])
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, p: f"{v:,.0f}"))
    fig.tight_layout()
    return _mpl_to_png_bytes(fig)


def _sheet_per_wtg(wb, ctx):
    ws = wb.create_sheet("07_Per_WTG_AEP")
    s = _styles()
    df_turb = ctx.get("df_per_turbine") if isinstance(ctx, dict) else None
    ws.cell(row=1, column=1, value="AEP por turbina").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)

    df_render = None
    turbinas = []
    aep_vals = []
    if df_turb is not None and len(df_turb) > 0:
        df_render = df_turb
        # try detect columns
        cols_lower = {c.lower(): c for c in df_turb.columns}
        id_col = cols_lower.get("turbina") or cols_lower.get("id") or cols_lower.get("turbina_id")
        aep_col = None
        for c in df_turb.columns:
            cl = c.lower()
            if "aep" in cl and "mwh" in cl:
                aep_col = c
                break
        if id_col and aep_col:
            turbinas = df_turb[id_col].astype(str).tolist()
            aep_vals = df_turb[aep_col].astype(float).tolist()
    else:
        res = ctx.get("res", {}) if isinstance(ctx, dict) else {}
        n_t = int(_to_float(ctx.get("n_turbinas")) or 0)
        aep_t = _to_float(res.get("aep_neta_turbina")) or 0.0
        if n_t > 0 and aep_t > 0:
            turbinas = [f"T{i+1}" for i in range(n_t)]
            aep_vals = [aep_t] * n_t
            df_render = pd.DataFrame({"Turbina": turbinas, "AEP neta P50 (MWh/año)": aep_vals})

    if df_render is not None and len(df_render) > 0:
        end_row = _apply_df_to_sheet(ws, df_render, start_row=3)
        if turbinas and aep_vals:
            aep_prom = sum(aep_vals) / len(aep_vals)
            png = _mpl_per_wtg(turbinas, aep_vals, aep_promedio=aep_prom)
            if png:
                _add_png_to_ws(ws, png, f"D3", width_px=820, height_px=410)
    else:
        ws.cell(row=3, column=1, value="Sin layout disponible.").font = s["kpi_value_font"]
    return ws


def _sheet_uncertainty(wb, ctx):
    ws = wb.create_sheet("08_Uncertainty_P50_P90")
    s = _styles()
    ws.cell(row=1, column=1, value="Incertidumbre IEC 61400-15-2").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)

    sigmas = ctx.get("uncertainty_categories") if isinstance(ctx, dict) else None
    if not sigmas:
        sigmas = {"meas": 3.0, "lt": 4.5, "vert": 2.0, "flow": 4.0, "plant": 3.0}
    labels = {"meas": "A - Medición y adquisición", "lt": "B - Long-term & climate",
              "vert": "C - Extrapolación vertical", "flow": "D - Modelado de flujo",
              "plant": "E - Plant performance"}
    df_sig = pd.DataFrame([{"Categoría": labels.get(k, k), "σ_i (%)": v, "σ_i² (%²)": v * v} for k, v in sigmas.items()])
    sigma_total = math.sqrt(sum(v * v for v in sigmas.values()))
    df_sig.loc[len(df_sig)] = {"Categoría": "σ_total combinado", "σ_i (%)": sigma_total, "σ_i² (%²)": sigma_total * sigma_total}
    end_row = _apply_df_to_sheet(ws, df_sig, start_row=3)

    res = ctx.get("res", {}) if isinstance(ctx, dict) else {}
    aep_n = _to_float(res.get("aep_neta_total")) or 0.0
    pct = sigma_total / 100.0
    df_p = pd.DataFrame([
        {"Percentil": "P50", "Z": 0.0, "AEP (MWh/año)": aep_n},
        {"Percentil": "P75", "Z": 0.6745, "AEP (MWh/año)": aep_n * (1 - 0.6745 * pct)},
        {"Percentil": "P90", "Z": 1.2816, "AEP (MWh/año)": aep_n * (1 - 1.2816 * pct)},
        {"Percentil": "P99", "Z": 2.3263, "AEP (MWh/año)": aep_n * (1 - 2.3263 * pct)},
    ])
    ws.cell(row=end_row + 2, column=1, value="Percentiles AEP — Monte Carlo Gaussiano").font = s["h2_font"]
    _apply_df_to_sheet(ws, df_p, start_row=end_row + 3)
    return ws


def _sheet_economics(wb, ctx):
    ws = wb.create_sheet("09_Economics")
    s = _styles()
    econ = ctx.get("economics", {}) if isinstance(ctx, dict) else {}
    currency = _safe(econ, "moneda_visualizacion", _safe(econ, "moneda_base", "USD"))
    capex_total = _to_float(_safe(econ, "capex_total_display", _safe(econ, "capex_total"))) or 0.0
    opex_total = _to_float(_safe(econ, "opex_total_anual_display", _safe(econ, "opex_total_anual"))) or 0.0
    comps = ctx.get("capex_components") if isinstance(ctx, dict) else None
    if not comps:
        # default split per IRENA proxies
        comps = {
            "Turbinas": 0.65,
            "BOP eléctrico": 0.12,
            "Civil": 0.10,
            "Subestación": 0.05,
            "Conexión red": 0.03,
            "Desarrollo y permisos": 0.03,
            "Contingencia": 0.02,
        }
        comps = {k: v * capex_total for k, v in comps.items()}

    ws.cell(row=1, column=1, value=f"CAPEX desglose ({currency})").font = s["h2_font"]
    df_c = pd.DataFrame([{"Componente": k, f"Monto ({currency})": v, "% del total": (v / capex_total * 100.0) if capex_total else 0.0} for k, v in comps.items()])
    df_c.loc[len(df_c)] = {"Componente": "TOTAL", f"Monto ({currency})": capex_total, "% del total": 100.0}
    end_row = _apply_df_to_sheet(ws, df_c, start_row=3)

    png_capex = _mpl_pie_breakdown(
        title=f"Desglose CAPEX — Total {currency} {capex_total:,.0f}",
        components=comps,
    )
    if png_capex:
        _add_png_to_ws(ws, png_capex, "E3", width_px=720, height_px=520)

    ws.cell(row=end_row + 2, column=1, value=f"OPEX anual ({currency})").font = s["h2_font"]
    opex_comps = ctx.get("opex_components") if isinstance(ctx, dict) else None
    if not opex_comps:
        opex_comps = {
            "O&M turbinas": 0.55,
            "BOP / subestación": 0.15,
            "Seguros": 0.10,
            "Administración y otros": 0.10,
            "Arriendo terreno / royalties": 0.10,
        }
        opex_comps = {k: v * opex_total for k, v in opex_comps.items()}
    df_o = pd.DataFrame([{"Componente": k, f"Monto anual ({currency})": v, "% del total": (v / opex_total * 100.0) if opex_total else 0.0} for k, v in opex_comps.items()])
    df_o.loc[len(df_o)] = {"Componente": "TOTAL", f"Monto anual ({currency})": opex_total, "% del total": 100.0}
    end_opex_row = _apply_df_to_sheet(ws, df_o, start_row=end_row + 3)
    png_opex = _mpl_pie_breakdown(
        title=f"Desglose OPEX anual — Total {currency} {opex_total:,.0f}",
        components=opex_comps,
    )
    if png_opex:
        _add_png_to_ws(ws, png_opex, f"E{end_row + 3}", width_px=720, height_px=520)
    return ws


def _sheet_cash_flow(wb, ctx):
    ws = wb.create_sheet("10_Cash_Flow")
    s = _styles()
    econ = ctx.get("economics", {}) if isinstance(ctx, dict) else {}
    res = ctx.get("res", {}) if isinstance(ctx, dict) else {}
    currency = _safe(econ, "moneda_visualizacion", _safe(econ, "moneda_base", "USD"))
    capex = _to_float(_safe(econ, "capex_total_display", _safe(econ, "capex_total"))) or 0.0
    opex_y = _to_float(_safe(econ, "opex_total_anual_display", _safe(econ, "opex_total_anual"))) or 0.0
    price = _to_float(_safe(econ, "precio_energia_mwh"), 50.0) or 50.0
    wacc = _to_float(_safe(econ, "tasa_descuento"), 8.0) or 8.0
    degr = _to_float(_safe(econ, "degradacion_pct"), 0.5) or 0.5
    n_years = int(_to_float(_safe(econ, "vida_util"), 20) or 20)
    aep_n = _to_float(res.get("aep_neta_total")) or 0.0

    ws.cell(row=1, column=1, value=f"Flujo de caja {n_years} años ({currency})").font = s["h2_font"]
    rows = []
    cum = -capex
    rows.append({"Año": 0, f"AEP (MWh)": 0.0, f"Revenue ({currency})": 0.0, f"OPEX ({currency})": 0.0, f"EBITDA ({currency})": -capex, f"FCF desc ({currency})": -capex, f"FCF acum ({currency})": cum})
    for y in range(1, n_years + 1):
        aep_y = aep_n * ((1 - degr / 100.0) ** (y - 1))
        rev = aep_y * price
        ebitda = rev - opex_y
        fcf_desc = ebitda / ((1 + wacc / 100.0) ** y)
        cum += ebitda
        rows.append({"Año": y, "AEP (MWh)": aep_y, f"Revenue ({currency})": rev, f"OPEX ({currency})": -opex_y, f"EBITDA ({currency})": ebitda, f"FCF desc ({currency})": fcf_desc, f"FCF acum ({currency})": cum})
    df_cf = pd.DataFrame(rows)
    end_row = _apply_df_to_sheet(ws, df_cf, start_row=3)

    # Grafica matplotlib FCF acumulado + EBITDA anual
    png_cf = _mpl_cash_flow(rows, currency=currency)
    if png_cf:
        _add_png_to_ws(ws, png_cf, f"I3", width_px=900, height_px=460)
    return ws


def _mpl_cash_flow(rows, currency="USD"):
    """Doble-eje: FCF acumulado (linea) + EBITDA anual (bar)."""
    plt = _mpl_setup()
    if plt is None or not rows:
        return None
    import numpy as np
    years = [r["Año"] for r in rows]
    fcf_acum = [r[f"FCF acum ({currency})"] for r in rows]
    ebitda_key = f"EBITDA ({currency})"
    ebitda = [r.get(ebitda_key, 0) for r in rows]
    fig, ax1 = plt.subplots(figsize=(12, 5.5), dpi=140)
    # EBITDA bars (verde si positivo, rojo si negativo)
    bar_colors = [_MPL_PALETTE["green"] if v >= 0 else _MPL_PALETTE["red"] for v in ebitda]
    bars = ax1.bar(years, ebitda, width=0.6, color=bar_colors,
                   edgecolor="white", alpha=0.78, label="EBITDA anual")
    ax1.axhline(0, color="black", lw=0.8, alpha=0.5)
    ax1.set_xlabel("Año del proyecto", fontsize=11, fontweight="bold")
    ax1.set_ylabel(f"EBITDA / FCF anual ({currency})", fontsize=11, fontweight="bold",
                   color=_MPL_PALETTE["slate"])
    ax1.tick_params(axis="y", colors=_MPL_PALETTE["slate"])
    ax1.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, p: f"{v/1e6:,.1f}M"))
    ax1.grid(True, axis="y", alpha=0.3, color=_MPL_PALETTE["grid"])
    ax1.spines[["top"]].set_visible(False)
    # FCF acumulado linea (1 sola serie!)
    ax2 = ax1.twinx()
    ax2.plot(years, fcf_acum, color=_MPL_PALETTE["navy"], lw=3,
             marker="o", markersize=6, markerfacecolor=_MPL_PALETTE["orange"],
             markeredgecolor="white", markeredgewidth=1.0,
             label="FCF acumulado")
    ax2.set_ylabel(f"FCF acumulado ({currency})", fontsize=11, fontweight="bold",
                   color=_MPL_PALETTE["navy"])
    ax2.tick_params(axis="y", colors=_MPL_PALETTE["navy"])
    ax2.yaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, p: f"{v/1e6:,.1f}M"))
    ax2.spines[["top"]].set_visible(False)
    # Marca payback (cuando FCF acum cruza 0)
    for i in range(1, len(fcf_acum)):
        if fcf_acum[i - 1] < 0 <= fcf_acum[i]:
            ax2.axvline(years[i], color=_MPL_PALETTE["red"], lw=1.5, ls="--", alpha=0.8)
            ax2.text(years[i] + 0.2, max(fcf_acum) * 0.5,
                     f"Payback ≈ año {years[i]}",
                     fontsize=10, fontweight="bold", color=_MPL_PALETTE["red"])
            break
    # Combinar leyendas
    lines1, lbls1 = ax1.get_legend_handles_labels()
    lines2, lbls2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, lbls1 + lbls2, loc="upper left",
               fontsize=10, framealpha=0.95)
    ax1.set_title(f"Flujo de caja del proyecto — Vida útil 20 años ({currency})",
                  fontsize=14, fontweight="bold", color=_MPL_PALETTE["navy"], pad=14)
    fig.tight_layout()
    return _mpl_to_png_bytes(fig)


def _sheet_sensitivity(wb, ctx):
    ws = wb.create_sheet("11_Sensitivity")
    s = _styles()
    econ = ctx.get("economics", {}) if isinstance(ctx, dict) else {}
    res = ctx.get("res", {}) if isinstance(ctx, dict) else {}
    currency = _safe(econ, "moneda_visualizacion", _safe(econ, "moneda_base", "USD"))
    capex = _to_float(_safe(econ, "capex_total_display", _safe(econ, "capex_total"))) or 0.0
    opex_y = _to_float(_safe(econ, "opex_total_anual_display", _safe(econ, "opex_total_anual"))) or 0.0
    price = _to_float(_safe(econ, "precio_energia_mwh"), 50.0) or 50.0
    wacc = _to_float(_safe(econ, "tasa_descuento"), 8.0) or 8.0
    n_years = int(_to_float(_safe(econ, "vida_util"), 20) or 20)
    aep_n = _to_float(res.get("aep_neta_total")) or 0.0
    delta = _to_float(_safe(econ, "sens_delta_pct"), 15.0) or 15.0

    def _npv(c, o, p, a):
        cf = -c
        for y in range(1, n_years + 1):
            cf += (a * p - o) / ((1 + wacc / 100.0) ** y)
        return cf

    base = _npv(capex, opex_y, price, aep_n)
    sens = []
    for var, lbl in [("Precio PPA", "price"), ("AEP", "aep"), ("CAPEX", "capex"), ("OPEX", "opex")]:
        if lbl == "price":
            low = _npv(capex, opex_y, price * (1 - delta / 100.0), aep_n)
            high = _npv(capex, opex_y, price * (1 + delta / 100.0), aep_n)
        elif lbl == "aep":
            low = _npv(capex, opex_y, price, aep_n * (1 - delta / 100.0))
            high = _npv(capex, opex_y, price, aep_n * (1 + delta / 100.0))
        elif lbl == "capex":
            low = _npv(capex * (1 - delta / 100.0), opex_y, price, aep_n)
            high = _npv(capex * (1 + delta / 100.0), opex_y, price, aep_n)
        else:
            low = _npv(capex, opex_y * (1 - delta / 100.0), price, aep_n)
            high = _npv(capex, opex_y * (1 + delta / 100.0), price, aep_n)
        sens.append({"Variable": f"{var} ±{delta:.0f}%", f"NPV bajo ({currency})": low, f"NPV base ({currency})": base, f"NPV alto ({currency})": high, f"Δ NPV ({currency})": high - low})
    df_s = pd.DataFrame(sens).sort_values(f"Δ NPV ({currency})", ascending=False).reset_index(drop=True)
    ws.cell(row=1, column=1, value=f"Análisis de sensibilidad — Tornado NPV (base = {currency} {base:,.0f})").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    end_row = _apply_df_to_sheet(ws, df_s, start_row=3)
    png_torn = _mpl_tornado(sens, base_npv=base, currency=currency)
    if png_torn:
        _add_png_to_ws(ws, png_torn, "G3", width_px=900, height_px=440)
    return ws


def _mpl_tornado(sens_list, base_npv, currency="USD"):
    """Tornado horizontal real (bars low/high desde base)."""
    plt = _mpl_setup()
    if plt is None or not sens_list:
        return None
    import numpy as np
    # ordenar por amplitud
    sens_sorted = sorted(sens_list,
                         key=lambda s: abs((s.get(f"NPV alto ({currency})", 0) or 0) - (s.get(f"NPV bajo ({currency})", 0) or 0)),
                         reverse=False)  # menor abajo, mayor arriba
    labels = [s["Variable"] for s in sens_sorted]
    lows = [s.get(f"NPV bajo ({currency})", 0) - base_npv for s in sens_sorted]
    highs = [s.get(f"NPV alto ({currency})", 0) - base_npv for s in sens_sorted]
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(11, max(4, 0.7 * len(labels) + 2)), dpi=140)
    ax.barh(y, lows, height=0.6, color=_MPL_PALETTE["red"], alpha=0.85,
            edgecolor="white", label="Caso bajo (-Δ%)")
    ax.barh(y, highs, height=0.6, color=_MPL_PALETTE["green"], alpha=0.85,
            edgecolor="white", label="Caso alto (+Δ%)")
    # Valores extremos como texto
    for i, (lo, hi) in enumerate(zip(lows, highs)):
        if lo < 0:
            ax.text(lo - max(abs(min(lows)), abs(max(highs))) * 0.02, i,
                    f"{lo/1e6:,.2f}M", ha="right", va="center",
                    fontsize=9, color=_MPL_PALETTE["red"], fontweight="bold")
        if hi > 0:
            ax.text(hi + max(abs(min(lows)), abs(max(highs))) * 0.02, i,
                    f"+{hi/1e6:,.2f}M", ha="left", va="center",
                    fontsize=9, color=_MPL_PALETTE["green"], fontweight="bold")
    ax.axvline(0, color="black", lw=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11, fontweight="bold", color=_MPL_PALETTE["slate"])
    ax.set_xlabel(f"Δ NPV vs base ({currency})", fontsize=11, fontweight="bold")
    ax.set_title(f"Análisis de sensibilidad Tornado — NPV base = {currency} {base_npv:,.0f}",
                 fontsize=13, fontweight="bold", color=_MPL_PALETTE["navy"], pad=14)
    ax.xaxis.set_major_formatter(plt.matplotlib.ticker.FuncFormatter(lambda v, p: f"{v/1e6:,.1f}M"))
    ax.grid(True, axis="x", alpha=0.3, color=_MPL_PALETTE["grid"])
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right", fontsize=10, framealpha=0.95)
    # margenes
    rng = max(abs(min(lows)), abs(max(highs))) * 1.4
    ax.set_xlim(-rng, rng)
    fig.tight_layout()
    return _mpl_to_png_bytes(fig)


def _sheet_iec_site_suitability(wb, ctx):
    ws = wb.create_sheet("12_Site_Suitability_IEC")
    s = _styles()
    site = ctx.get("iec_site") if isinstance(ctx, dict) else None
    ws.cell(row=1, column=1, value="IEC 61400-1 Site Suitability").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    if site and isinstance(site, dict):
        rows = [(k, site.get(k)) for k in ["V_ref (m/s)", "V_50 (m/s)", "V_ave (m/s)", "V_e1 (m/s)", "V_e50 (m/s)", "TI_eff(15)", "Clase IEC", "Cumple"]]
        _write_kpi_block(ws, rows, start_row=3)
    else:
        ws.cell(row=3, column=1, value="Pendiente — requiere módulo calculos_iec_site (Phase C).").font = s["kpi_value_font"]
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=6)
    return ws


def _sheet_assumptions(wb, ctx):
    ws = wb.create_sheet("13_Assumptions")
    s = _styles()
    ws.cell(row=1, column=1, value="Supuestos (Assumptions)").font = s["h2_font"]
    cfg = ctx.get("config", {}) if isinstance(ctx, dict) else {}
    econ = ctx.get("economics", {}) if isinstance(ctx, dict) else {}
    rows = [
        ("Densidad del aire (kg/m³)", _to_float(cfg.get("densidad"))),
        ("Modelo wake", _safe(ctx, "wake_mode", "Manual")),
        ("Pérdida wake manual (%)", _to_float(ctx.get("wake_manual_pct"))),
        ("CT", _to_float(ctx.get("ct"), 0.8)),
        ("kW (wake)", _to_float(ctx.get("kw"), 0.05)),
        ("Disponibilidad (%)", _to_float(ctx.get("disp_pct"))),
        ("Eléctricas (%)", _to_float(ctx.get("elec_pct"))),
        ("Otras pérdidas (%)", _to_float(ctx.get("otras_pct"))),
        ("Vida útil (años)", _to_float(_safe(econ, "vida_util"), 20)),
        ("WACC (%)", _to_float(_safe(econ, "tasa_descuento"), 8)),
        ("Degradación anual (%)", _to_float(_safe(econ, "degradacion_pct"), 0.5)),
        ("Precio PPA (USD/MWh)", _to_float(_safe(econ, "precio_energia_mwh"), 50)),
        ("Δ sensibilidad (%)", _to_float(_safe(econ, "sens_delta_pct"), 15)),
    ]
    _write_kpi_block(ws, rows, start_row=2)
    return ws


def _sheet_glossary(wb, ctx):
    ws = wb.create_sheet("14_Glossary_Refs")
    s = _styles()
    ws.cell(row=1, column=1, value="Glosario, acrónimos y referencias normativas").font = s["h2_font"]
    glos = [
        ("AEP", "Annual Energy Production"),
        ("P50/P75/P90/P99", "Percentiles de la distribución probabilística de AEP"),
        ("TI", "Turbulence Intensity"),
        ("WACC", "Weighted Average Cost of Capital"),
        ("LCOE", "Levelized Cost of Energy"),
        ("DSCR", "Debt Service Coverage Ratio"),
        ("EYA", "Energy Yield Assessment"),
        ("MCP", "Measure-Correlate-Predict"),
        ("CT", "Coeficiente de empuje (thrust coefficient)"),
        ("EPC", "Engineering, Procurement & Construction"),
        ("FID", "Final Investment Decision"),
        ("BOP", "Balance of Plant"),
    ]
    df_g = pd.DataFrame(glos, columns=["Acrónimo", "Definición"])
    end_row = _apply_df_to_sheet(ws, df_g, start_row=3)

    ws.cell(row=end_row + 2, column=1, value="Referencias normativas").font = s["h2_font"]
    refs = [
        "IEC 61400-1 Ed.4 (2019) — Wind energy generation systems — Part 1: Design requirements",
        "IEC 61400-12-1 Ed.3 (2022) — Power performance measurements",
        "IEC 61400-15-1 (2025) — Site specific wind conditions assessment",
        "IEC 61400-15-2 (en desarrollo) — Framework for site-specific wind conditions",
        "DNV-SE-0073 (2022) — Project certification of wind farms",
        "DNV-ST-0437 (2021) — Loads and site conditions for wind turbines",
        "ISO 9613-2:1996 — Acoustics — Attenuation of sound during propagation",
        "Jensen, N.O. (1983) — A note on wind generator interaction (Risø-M-2411)",
        "Bastankhah & Porté-Agel (2014) — A new analytical model for wind-turbine wakes",
        "Pedersen et al. (2022) — TurbOPark model",
        "IRENA (2024) — Renewable Power Generation Costs",
        "NASA POWER project — NASA Langley Research Center",
        "Copernicus ERA5 reanalysis — ECMWF",
    ]
    df_r = pd.DataFrame({"Referencia": refs})
    _apply_df_to_sheet(ws, df_r, start_row=end_row + 3)
    return ws


def _sheet_diurnal_seasonal(wb, ctx):
    """Hoja 16_Diurnal_Seasonal: pivot mes(1-12) x hora(0-23) velocidad media."""
    ws = wb.create_sheet("16_Diurnal_Seasonal")
    s = _styles()
    ws.cell(row=1, column=1, value="Patrones diurnos y estacionales").font = s["h2_font"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=14)

    df_nasa = ctx.get("df_nasa") if isinstance(ctx, dict) else None
    ws_col = None
    for cand in ("WS_ANALISIS", "WS50M", "WS10M", "WS"):
        if df_nasa is not None and hasattr(df_nasa, "columns") and cand in df_nasa.columns:
            ws_col = cand
            break
    if df_nasa is None or ws_col is None or len(df_nasa) == 0:
        ws.cell(row=3, column=1, value="Sin serie horaria disponible (df_nasa no provisto en ctx).").font = s["kpi_value_font"]
        return ws
    try:
        import numpy as np
        import pandas as pd
        df = df_nasa.copy()
        if not hasattr(df.index, "hour"):
            # intenta convertir
            df.index = pd.to_datetime(df.index, errors="coerce")
        df = df.dropna(subset=[ws_col])
        df["hour"] = df.index.hour
        df["month"] = df.index.month
        pivot = df.pivot_table(values=ws_col, index="hour", columns="month", aggfunc="mean").round(3)
        # header row: month numbers 1..12
        ws.cell(row=3, column=1, value="Hora \\ Mes").font = s["header_font"]
        ws.cell(row=3, column=1).fill = s["header_fill"]
        ws.cell(row=3, column=1).alignment = s["header_align"]
        ws.cell(row=3, column=1).border = s["border"]
        meses = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        for j in range(12):
            c = ws.cell(row=3, column=2 + j, value=meses[j])
            c.font = s["header_font"]; c.fill = s["header_fill"]
            c.alignment = s["header_align"]; c.border = s["border"]
        # body
        for i in range(24):
            row_idx = 4 + i
            c0 = ws.cell(row=row_idx, column=1, value=f"{i:02d}:00")
            c0.font = s["kpi_label_font"]; c0.border = s["border"]
            if i % 2 == 0:
                c0.fill = s["band_fill"]
            for j in range(12):
                month_id = j + 1
                try:
                    v = float(pivot.loc[i, month_id]) if (i in pivot.index and month_id in pivot.columns) else None
                except Exception:
                    v = None
                cell = ws.cell(row=row_idx, column=2 + j, value=v if v is not None and v == v else None)
                cell.border = s["border"]
                cell.number_format = "0.00"
                cell.alignment = s["right_align"]
                if i % 2 == 0:
                    cell.fill = s["band_fill"]
        # conditional formatting: gradient 3-color
        try:
            from openpyxl.formatting.rule import ColorScaleRule
            rule = ColorScaleRule(
                start_type="min", start_color="63BE7B",
                mid_type="percentile", mid_value=50, mid_color="FFEB84",
                end_type="max", end_color="F8696B",
            )
            ws.conditional_formatting.add(f"B4:M27", rule)
        except Exception:
            pass
        ws.column_dimensions["A"].width = 14
        for j in range(12):
            ws.column_dimensions[ws.cell(row=3, column=2 + j).column_letter].width = 10
        ws.freeze_panes = "B4"
        # min/max highlight bottom
        try:
            ws.cell(row=29, column=1, value="Velocidad media global (m/s)").font = s["kpi_label_font"]
            ws.cell(row=29, column=2, value=float(df[ws_col].mean())).number_format = "0.00"
            ws.cell(row=30, column=1, value="Pico horario maximo (m/s)").font = s["kpi_label_font"]
            ws.cell(row=30, column=2, value=float(pivot.values.max())).number_format = "0.00"
            ws.cell(row=31, column=1, value="Valle horario minimo (m/s)").font = s["kpi_label_font"]
            ws.cell(row=31, column=2, value=float(pivot.values.min())).number_format = "0.00"
        except Exception:
            pass
    except Exception as exc:
        ws.cell(row=3, column=1, value=f"Error procesando serie: {exc}").font = s["kpi_value_font"]
    return ws


def _sheet_audit_manifest(wb, ctx, content_hash=None):
    ws = wb.create_sheet("15_Audit_Manifest")
    s = _styles()
    ws.cell(row=1, column=1, value="Manifiesto de auditoría").font = s["h2_font"]
    rows = [
        ("generated_at_utc", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("sma_version", _safe(ctx, "sma_version", "2.0")),
        ("git_hash", _safe(ctx, "git_hash", "—")),
        ("content_sha256", content_hash or "—"),
        ("project_name", _safe(ctx, "project_name", "—")),
        ("report_style", _safe(ctx, "report_style", "bankable")),
        ("export_format", "xlsx"),
        ("python_pkg_versions", _safe(ctx, "pkg_versions", "—")),
    ]
    _write_kpi_block(ws, rows, start_row=2)
    return ws


# ─────────────────────────────────────────────────────────────
# Public entry
# ─────────────────────────────────────────────────────────────
_TAB_COLORS = {
    "00_Cover": "1F4E79",                   # navy
    "01_Executive_Summary": "1F4E79",
    "02_Site_Turbine": "2E5C8A",
    "03_Wind_Resource": "2E5C8A",
    "04_Power_Curve": "2E5C8A",
    "05_Energy_Sectorial": "1F6E3B",        # green
    "06_Loss_Waterfall": "8B1F1F",          # red (losses)
    "07_Per_WTG_AEP": "1F6E3B",
    "08_Uncertainty_P50_P90": "D97706",     # orange
    "09_Economics": "6B21A8",               # purple
    "10_Cash_Flow": "6B21A8",
    "11_Sensitivity": "D97706",
    "12_Site_Suitability_IEC": "0F766E",    # teal
    "13_Assumptions": "9CA3AF",             # gray
    "14_Glossary_Refs": "9CA3AF",
    "16_Diurnal_Seasonal": "2E5C8A",
    "15_Audit_Manifest": "374151",          # dark gray
}


def _apply_tab_colors(wb):
    """Colorea tabs por categoria."""
    for sheet_name, color in _TAB_COLORS.items():
        if sheet_name in wb.sheetnames:
            try:
                wb[sheet_name].sheet_properties.tabColor = color
            except Exception:
                pass


def _add_conditional_formatting(wb):
    """Conditional formatting: losses rojo>10%, FP verde>30%, etc."""
    try:
        from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        return
    # 06_Loss_Waterfall: columna Perdida (%) — rojo si >10
    if "06_Loss_Waterfall" in wb.sheetnames:
        ws = wb["06_Loss_Waterfall"]
        if ws.max_row >= 4:
            red = PatternFill("solid", fgColor="FCA5A5")
            green = PatternFill("solid", fgColor="86EFAC")
            yellow = PatternFill("solid", fgColor="FDE68A")
            rng = f"C4:C{ws.max_row}"
            try:
                ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["10"], fill=red))
                ws.conditional_formatting.add(rng, CellIsRule(operator="between", formula=["5", "10"], fill=yellow))
                ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["5"], fill=green))
            except Exception:
                pass
    # 05_Energy_Sectorial: colorscale en frecuencia (%) y AEP neta
    if "05_Energy_Sectorial" in wb.sheetnames:
        ws = wb["05_Energy_Sectorial"]
        if ws.max_row >= 4:
            try:
                cs = ColorScaleRule(start_type="min", start_color="FEE2E2",
                                    mid_type="percentile", mid_value=50, mid_color="FEF3C7",
                                    end_type="max", end_color="86EFAC")
                ws.conditional_formatting.add(f"B4:B{ws.max_row}", cs)
                ws.conditional_formatting.add(f"F4:F{ws.max_row}", cs)
            except Exception:
                pass
    # 08_Uncertainty: scale color en sigma
    if "08_Uncertainty_P50_P90" in wb.sheetnames:
        ws = wb["08_Uncertainty_P50_P90"]
        try:
            cs = ColorScaleRule(start_type="min", start_color="86EFAC",
                                mid_type="percentile", mid_value=50, mid_color="FDE68A",
                                end_type="max", end_color="FCA5A5")
            ws.conditional_formatting.add(f"B4:B{ws.max_row}", cs)
        except Exception:
            pass


def exportar_excel_pro(ctx: dict[str, Any]) -> bytes:
    """Genera Excel bankable 16 hojas con polish profesional. Devuelve bytes."""
    from openpyxl import Workbook

    wb = Workbook()
    # remove default sheet
    default = wb.active
    wb.remove(default)

    _sheet_cover(wb, ctx)
    _sheet_exec_summary(wb, ctx)
    _sheet_site_turbine(wb, ctx)
    _sheet_wind_resource(wb, ctx)
    _sheet_power_curve(wb, ctx)
    _sheet_energy_sectorial(wb, ctx)
    _sheet_loss_waterfall(wb, ctx)
    _sheet_per_wtg(wb, ctx)
    _sheet_uncertainty(wb, ctx)
    _sheet_economics(wb, ctx)
    _sheet_cash_flow(wb, ctx)
    _sheet_sensitivity(wb, ctx)
    _sheet_iec_site_suitability(wb, ctx)
    _sheet_assumptions(wb, ctx)
    _sheet_glossary(wb, ctx)
    _sheet_diurnal_seasonal(wb, ctx)
    _sheet_audit_manifest(wb, ctx, content_hash=None)  # placeholder; finalized below

    # Polish profesional final
    _apply_tab_colors(wb)
    _add_conditional_formatting(wb)

    buf = io.BytesIO()
    wb.save(buf)
    payload = buf.getvalue()
    # final hash + rewrite audit sheet
    content_hash = hashlib.sha256(payload).hexdigest()
    # re-open, update hash, re-save
    from openpyxl import load_workbook
    wb2 = load_workbook(io.BytesIO(payload))
    if "15_Audit_Manifest" in wb2.sheetnames:
        ws_a = wb2["15_Audit_Manifest"]
        # row "content_sha256" is row 5 (title r1, blank? actually _write_kpi_block start_row=2 -> header r2, rows 3..)
        # find "content_sha256" cell
        for r in range(1, ws_a.max_row + 1):
            v = ws_a.cell(row=r, column=1).value
            if v == "content_sha256":
                ws_a.cell(row=r, column=2, value=content_hash)
                break
    buf2 = io.BytesIO()
    wb2.save(buf2)
    return buf2.getvalue()


__all__ = ["exportar_excel_pro"]
