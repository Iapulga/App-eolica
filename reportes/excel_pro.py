"""Excel PRO — libro técnico-económico de 17 hojas (estilo WindPRO / WAsP / openWind).

Todas las cifras salen del proyecto ACTIVO vía `reportes.datos_proyecto` (la misma fuente que el
informe técnico y el reporte bankable): energía y pérdidas de la Fase 5, Monte Carlo guardado,
economía calculada con las funciones de la Fase 5, IEC con la clasificación de la Fase 5 y
resultados ambientales de la Fase 6. Nada queda fijo ni inventado.

Hojas:
  00_Portada · 01_Resumen_ejecutivo · 02_Sitio_y_turbina · 03_Recurso_eólico · 04_Curva_de_potencia
  05_Energía_por_sector · 06_Cascada_de_pérdidas · 07_AEP_por_turbina · 08_Incertidumbre · 09_Economía
  10_Flujo_de_caja · 11_Sensibilidad · 12_Idoneidad_IEC · 13_Supuestos · 14_Glosario_y_referencias
  15_Diurno_y_estacional · 16_Manifiesto

Uso: bytes_xlsx = exportar_excel_pro(ctx)   (ctx = contexto de la Fase 5; si trae ctx["datos"] se usa)
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from . import estilo, graficas
from .datos_proyecto import construir_datos_exportacion, fmt_num, texto_aviso

HOJAS = [
    "00_Portada", "01_Resumen_ejecutivo", "02_Sitio_y_turbina", "03_Recurso_eólico", "04_Curva_de_potencia",
    "05_Energía_por_sector", "06_Cascada_de_pérdidas", "07_AEP_por_turbina", "08_Incertidumbre", "09_Economía",
    "10_Flujo_de_caja", "11_Sensibilidad", "12_Idoneidad_IEC", "13_Supuestos", "14_Glosario_y_referencias",
    "15_Diurno_y_estacional", "16_Manifiesto",
]

_NAVY = estilo.MARINO
_WHITE = "FFFFFF"
_BAND = estilo.CEBRA
_BORDER_GRAY = estilo.REGLA
_PAL = {  # paleta formal común (reportes/estilo.py)
    "navy": "#1B365D", "blue": "#2F5F8F", "sky": "#5F86B0", "light": "#C9D6E6", "green": "#1F7A6F",
    "lgreen": "#86C5B8", "red": "#B3261E", "orange": "#C98A1B", "purple": "#2F5F8F", "teal": "#1F7A6F",
    "slate": "#6B7785", "grid": "#C9D2DC", "yellow": "#FBF3E4",
}
_ETIQUETAS_CAPEX = {"Turbinas": "Aerogeneradores", "BOP": "Balance of Plant (BOP)", "Red": "Conexión a red",
                    "Desarrollo": "Desarrollo y permisos", "Contingencia": "Contingencia"}


# ─────────────────────────────────────────────────────────────
# Estilo
# ─────────────────────────────────────────────────────────────
def _styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    thin = Side(style="thin", color=_BORDER_GRAY)
    return {
        "header_fill": PatternFill("solid", fgColor=_NAVY),
        "header_font": Font(name="Calibri", size=11, bold=True, color=_WHITE),
        "header_align": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "band_fill": PatternFill("solid", fgColor=_BAND),
        "border": Border(bottom=thin),  # estilo formal: solo reglas horizontales
        "h2_font": Font(name="Calibri", size=13, bold=True, color=_NAVY),
        "label_font": Font(name="Calibri", size=11, bold=True, color=_NAVY),
        "value_font": Font(name="Calibri", size=11),
        "note_font": Font(name="Calibri", size=10, italic=True),
        "right": Alignment(horizontal="right", vertical="center"),
        "wrap": Alignment(horizontal="left", vertical="top", wrap_text=True),
    }


def _formato(etiqueta) -> str:
    """Formato numérico por etiqueta (Excel lo muestra con la configuración regional: 1.234,56)."""
    t = str(etiqueta or "").lower()
    if t.startswith(("año", "número", "datos", "muestras", "semilla")) or t in ("n", "turbinas"):
        return "0"
    if "latitud" in t or "longitud" in t:
        return "0.000000"
    if "z0" in t:
        return "0.0000"
    if "cizalladura" in t or t.strip() == "cp" or "kg/m³" in t:
        return "0.000"
    if "(%)" in t or "(σ, %)" in t or t.endswith("%)"):
        return "0.00"
    if "(°" in t:
        return "0.0"
    if "(m/s)" in t or "empuje" in t or t.startswith("k weibull") or t == "k":
        return "0.00"
    if "/kwh)" in t:
        return "0.0000"
    if "/mwh)" in t:
        return "#,##0.00"
    if "mwh" in t or "(kw)" in t:
        return "#,##0.0"
    if "(mw)" in t:
        return "#,##0.00"
    if "(m²)" in t or "(w)" in t or "h/año" in t or "horas" in t:
        return "#,##0"
    if "(años)" in t or "vida útil" in t:
        return "0.0"
    if "(m)" in t or "(°c)" in t:
        return "#,##0.0"
    if any(m in t for m in ("(cop", "(usd", "(eur", "(gbp", "(mxn", "(brl", "(clp", "(pen", "(ars", "capex", "opex", "vpn",
                            "ingresos", "inversión", "flujo", "acumulado", "valor residual", "rango", "monto")):
        return "#,##0"
    return "#,##0.00"


def _titulo(ws, texto, fila=1, hasta=8):
    """Título de hoja: azul marino, 14 pt, con filete inferior a lo ancho de la tabla."""
    from openpyxl.styles import Alignment, Border, Font, Side

    celda = ws.cell(row=fila, column=1, value=texto)
    celda.font = Font(name="Calibri", size=14, bold=True, color=_NAVY)
    celda.alignment = Alignment(vertical="center")
    filete = Border(bottom=Side(style="medium", color=_NAVY))
    for col in range(1, hasta + 1):
        ws.cell(row=fila, column=col).border = filete
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=hasta)
    ws.row_dimensions[fila].height = 26


def _nota(ws, fila, texto, hasta=8, color=estilo.AMBAR_SUAVE, alto=34):
    from openpyxl.styles import PatternFill

    s = _styles()
    c = ws.cell(row=fila, column=1, value=texto)
    c.alignment = s["wrap"]
    c.font = s["note_font"]
    c.fill = PatternFill("solid", fgColor=color)
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=hasta)
    ws.row_dimensions[fila].height = alto
    return fila + 1


def _tabla(ws, df, fila=1, col=1, congelar=True, filtro=True):
    s = _styles()
    if df is None or df.empty:
        return fila
    headers = list(df.columns)
    for j, h in enumerate(headers):
        c = ws.cell(row=fila, column=col + j, value=str(h))
        c.fill, c.font, c.alignment, c.border = s["header_fill"], s["header_font"], s["header_align"], s["border"]
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        for j, h in enumerate(headers):
            v = row[h]
            if isinstance(v, float) and (v != v or math.isinf(v)):
                v = None
            if hasattr(v, "item") and not isinstance(v, str):
                try:
                    v = v.item()
                except Exception:
                    pass
            cell = ws.cell(row=fila + i, column=col + j, value=v)
            cell.border = s["border"]
            if i % 2 == 0:
                cell.fill = s["band_fill"]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.number_format = _formato(h)
                cell.alignment = s["right"]
    fin = fila + len(df)
    for j, h in enumerate(headers):
        letra = ws.cell(row=fila, column=col + j).column_letter
        muestras = [len(str(h))] + [len(fmt_num(x, 2)) if isinstance(x, (int, float)) else len(str(x or "")) for x in df[h].head(60)]
        ws.column_dimensions[letra].width = min(max(12, max(muestras) + 2), 46)
    if congelar:
        ws.freeze_panes = ws.cell(row=fila + 1, column=col)
    if filtro and len(df) > 0:
        ws.auto_filter.ref = f"{ws.cell(row=fila, column=col).coordinate}:{ws.cell(row=fin, column=col + len(headers) - 1).coordinate}"
    return fin


def _kpis(ws, filas, fila=1, titulo=None):
    s = _styles()
    if titulo:
        ws.cell(row=fila, column=1, value=titulo).font = s["h2_font"]
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=4)
        fila += 1
    for j, h in enumerate(("Indicador", "Valor"), start=1):
        c = ws.cell(row=fila, column=j, value=h)
        c.font, c.fill, c.alignment, c.border = s["header_font"], s["header_fill"], s["header_align"], s["border"]
    fila += 1
    for etiqueta, valor in filas:
        if hasattr(valor, "item") and not isinstance(valor, str):
            valor = valor.item()
        c1 = ws.cell(row=fila, column=1, value=str(etiqueta))
        c2 = ws.cell(row=fila, column=2, value="—" if valor is None else valor)
        c1.font, c1.border, c2.border = s["label_font"], s["border"], s["border"]
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            c2.number_format = _formato(etiqueta)
            c2.alignment = s["right"]
        else:
            c2.alignment = s["wrap"]
        fila += 1
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width or 0, 46)
    ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 0, 32)
    return fila


# ─────────────────────────────────────────────────────────────
# Gráficas (matplotlib → PNG) con números en formato español
# ─────────────────────────────────────────────────────────────
def _insertar_png(ws, png, celda, ancho_px):
    """Inserta la imagen conservando su proporción (antes se deformaba con alto fijo)."""
    if not png:
        return False
    try:
        from openpyxl.drawing.image import Image as XLImage
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            w, h = im.size
        img = XLImage(io.BytesIO(png))
        img.width = ancho_px
        img.height = int(ancho_px * h / w)
        img.anchor = celda
        ws.add_image(img)
        return True
    except Exception:
        return False


# Las gráficas son las mismas del reporte bankable (reportes/graficas.py), con título porque el Excel no
# lleva rótulos de figura.
def _g_rosa(sectores, valores, titulo, unidad, color):
    return graficas.rosa_valores(sectores, valores, "es", unidad, color=str(color).lstrip("#"), titulo=titulo)


def _g_barras_sector(sectores, bruta, neta):
    return graficas.barras_sector(sectores, bruta, neta, "es", titulo="Producción anual por sector direccional")


def _g_cascada(pasos, neta):
    etiquetas = {p["clave"]: p["etiqueta"] for p in pasos}
    etiquetas["neta"] = "AEP neta"
    return graficas.cascada(pasos, neta, "es", etiquetas=etiquetas, titulo="Cascada de pérdidas: AEP bruta → AEP neta")


def _g_torta(titulo, items, moneda=""):
    return graficas.dona(items, moneda, "es", titulo=titulo)


def _g_flujo(anios, flujos, acumulado, moneda, vida):
    return graficas.flujo_caja(anios, flujos, acumulado, moneda, "es", etiquetas={"acumulado": "Flujo acumulado"},
                               titulo=f"Flujo de caja del proyecto — vida útil {vida} años")


def _g_tornado(filas, base, moneda, delta=15.0):
    datos = [{"clave": str(i), "npv_menos": f["npv_menos"], "npv_mas": f["npv_mas"]} for i, f in enumerate(filas)]
    return graficas.tornado(datos, base, moneda, "es", etiquetas={str(i): f["etiqueta"] for i, f in enumerate(filas)},
                            delta=delta, titulo="Sensibilidad del VPN")


def _g_layout(turbinas, diametro):
    return graficas.disposicion(turbinas, diametro, "es", titulo=f"Disposición del parque — {len(turbinas)} turbinas")


# ─────────────────────────────────────────────────────────────
# Hojas
# ─────────────────────────────────────────────────────────────
def _hoja_portada(wb, d):
    """Portada: banda azul marino, proyecto, tarjetas de cifras, control del documento, avisos y descargo."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    s = _styles()
    ws = wb.create_sheet(HOJAS[0])
    ws.column_dimensions["A"].width = 3
    for letra in "BCDEFGHI":
        ws.column_dimensions[letra].width = 15
    p, e, inc, eco, t = d["proyecto"], d["energia"], d["incertidumbre"], d["economia"], d["turbina"]
    marino = PatternFill("solid", fgColor=_NAVY)
    suave = PatternFill("solid", fgColor=estilo.MARINO_SUAVE)

    def franja(fila, texto, fuente, relleno, alto, hasta="I"):
        for col in "BCDEFGHI":
            ws[f"{col}{fila}"].fill = relleno
        celda = ws[f"B{fila}"]
        celda.value = texto
        celda.font = fuente
        celda.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.merge_cells(f"B{fila}:{hasta}{fila}")
        ws.row_dimensions[fila].height = alto

    franja(2, "EVALUACIÓN TÉCNICO-ECONÓMICA", Font(name="Calibri", size=22, bold=True, color="FFFFFF"), marino, 44)
    franja(3, "Producción de energía eólica · Excel PRO (17 hojas)", Font(name="Calibri", size=12, color="D6DEE9"), marino, 24)
    ws["B5"].value = p["nombre"]
    ws["B5"].font = Font(name="Calibri", size=18, bold=True, color=_NAVY)
    ws.merge_cells("B5:I5")
    ws.row_dimensions[5].height = 30
    ws["B6"].value = (f"{p.get('pais_nombre') or ''} · lat {fmt_num(p.get('lat'), 5)} · lon {fmt_num(p.get('lon'), 5)} · "
                      f"{datetime.now():%Y-%m-%d}")
    ws["B6"].font = Font(name="Calibri", size=11, color=estilo.GRIS)
    ws.merge_cells("B6:I6")

    f = eco.get("factor") or 1.0
    lcoe = (eco.get("lcoe_mwh") or 0) * f if eco.get("lcoe_mwh") is not None else None
    tarjetas = [
        (fmt_num(t.get("p_instalada_mw"), 1), "Potencia instalada (MW)"),
        (fmt_num(e.get("aep_neta_mwh"), 0), "AEP neta (MWh/año)"),
        (fmt_num(inc.get("p90"), 0), "AEP P90 (MWh/año)"),
        (fmt_num(lcoe, 2), f"LCOE ({eco.get('moneda') or ''}/MWh)"),
    ]
    filete = Border(left=Side(style="thick", color=_NAVY))
    for k, (valor, etiqueta) in enumerate(tarjetas):
        c1, c2 = "BDFH"[k], "CEGI"[k]
        for fila, texto, fuente, alto in ((8, valor, Font(name="Calibri", size=18, bold=True, color=_NAVY), 32),
                                          (9, etiqueta, Font(name="Calibri", size=9, color=estilo.GRIS), 18)):
            for col in (c1, c2):
                ws[f"{col}{fila}"].fill = suave
            ws[f"{c1}{fila}"].border = filete
            celda = ws[f"{c1}{fila}"]
            celda.value = texto
            celda.font = fuente
            celda.alignment = Alignment(horizontal="left", vertical="center", indent=1)
            ws.merge_cells(f"{c1}{fila}:{c2}{fila}")
            ws.row_dimensions[fila].height = alto

    ws["B11"].value = "Control del documento"
    ws["B11"].font = s["h2_font"]
    ahora = datetime.now()
    filas = [
        ("Proyecto", p["nombre"]), ("País del informe", p.get("pais_nombre")),
        ("Latitud", p.get("lat")), ("Longitud", p.get("lon")),
        ("Documento", f"SMA-EYA-{ahora:%Y%m%d}-001"), ("Revisión", "Rev A"),
        ("Fecha de generación", ahora.strftime("%Y-%m-%d %H:%M")),
        ("Autor", p.get("autor") or "SMA 2.0 (generado automáticamente)"), ("Cliente", p.get("cliente") or "—"),
        ("Estado", "Borrador para revisión"), ("Confidencialidad", "Confidencial — distribución restringida"),
    ]
    regla = Border(bottom=Side(style="thin", color=_BORDER_GRAY))
    fila = 12
    for etiqueta, valor in filas:
        ws[f"B{fila}"].value = etiqueta
        ws[f"B{fila}"].font = s["label_font"]
        ws.merge_cells(f"B{fila}:D{fila}")
        celda = ws[f"E{fila}"]
        celda.value = "—" if valor is None else valor
        if isinstance(valor, float):
            celda.number_format = "0.000000"
            celda.alignment = Alignment(horizontal="left")
        ws.merge_cells(f"E{fila}:I{fila}")
        for col in "BCDEFGHI":
            ws[f"{col}{fila}"].border = regla
        fila += 1
    fila += 1
    if d.get("avisos"):
        ws[f"B{fila}"].value = "Avisos de coherencia de los datos"
        ws[f"B{fila}"].font = s["h2_font"]
        fila += 1
        for aviso in d["avisos"]:
            celda = ws[f"B{fila}"]
            celda.value = texto_aviso(aviso)
            celda.alignment = s["wrap"]
            celda.font = Font(name="Calibri", size=10, color=estilo.TEXTO)
            for col in "BCDEFGHI":
                ws[f"{col}{fila}"].fill = PatternFill("solid", fgColor=estilo.AMBAR_SUAVE)
            ws.merge_cells(f"B{fila}:I{fila}")
            ws.row_dimensions[fila].height = 32
            fila += 1
        fila += 1
    ws[f"B{fila}"].value = "Descargo de responsabilidad"
    ws[f"B{fila}"].font = s["h2_font"]
    celda = ws[f"B{fila + 1}"]
    celda.value = ("Documento generado automáticamente por SMA 2.0 con los datos configurados en la herramienta y fuentes "
                   "externas (p. ej. NASA POWER). No sustituye una evaluación de producción (EYA) de tercera parte "
                   "certificada (DNV, UL, TÜV). P50/P90 son indicativos: para financiación de proyecto se requiere validación "
                   "independiente, campaña de medición con torre de al menos 12 meses y correlación de largo plazo (MCP).")
    celda.alignment = s["wrap"]
    celda.font = Font(name="Calibri", size=10, italic=True, color=estilo.TEXTO)
    ws.merge_cells(f"B{fila + 1}:I{fila + 1}")
    ws.row_dimensions[fila + 1].height = 64
    return ws


def _hoja_resumen(wb, d):
    ws = wb.create_sheet(HOJAS[1])
    p, t, e, r, inc, eco = d["proyecto"], d["turbina"], d["energia"], d["recurso"], d["incertidumbre"], d["economia"]
    mon, f = eco["moneda"], eco.get("factor") or 1.0
    m = (lambda v: None if v is None else v * f)
    _kpis(ws, [
        ("Método principal", e.get("metodo")), ("Número de turbinas", t.get("n_turbinas")),
        ("Potencia nominal por turbina (kW)", t.get("p_nominal_kw")), ("Potencia instalada (MW)", t.get("p_instalada_mw")),
        ("Altura de buje (m)", t.get("altura_buje_m")), ("Velocidad media a la altura de buje (m/s)", r.get("v_media_buje")),
        ("AEP bruta del parque (MWh/año)", e.get("aep_bruta_mwh")), ("AEP neta del parque (MWh/año)", e.get("aep_neta_mwh")),
        ("Pérdida por estela aplicada (%)", e.get("estela_pct")), ("Pérdidas totales (%)", e.get("perdida_total_pct")),
        ("Factor de planta bruto (%)", e.get("fp_bruto_pct")), ("Factor de planta neto (%)", e.get("fp_neto_pct")),
        ("AEP P50 (MWh/año)", inc.get("p50")), ("AEP P75 (MWh/año)", inc.get("p75")),
        ("AEP P90 (MWh/año)", inc.get("p90")), ("AEP P99 (MWh/año)", inc.get("p99")),
        ("Incertidumbre de la AEP (σ, %)", inc.get("cv_pct")),
        ("Origen de P50/P90", "Monte Carlo de la Fase 5" if inc.get("fuente") == "monte_carlo" else (
            "Estimación genérica (Monte Carlo desactualizado: vuelva a ejecutarlo en la Fase 5)" if inc.get("mc_obsoleto")
            else "Estimación genérica (sin Monte Carlo)")),
        (f"CAPEX total ({mon})", m(eco.get("capex_total"))), (f"OPEX anual ({mon})", m(eco.get("opex_total"))),
        (f"LCOE ({mon}/MWh)", m(eco.get("lcoe_mwh"))), (f"VPN ({mon})", m(eco.get("npv"))), ("TIR (%)", eco.get("irr_pct")),
        ("Payback simple (años)", eco.get("payback_simple")), ("Payback descontado (años)", eco.get("payback_desc")),
    ], fila=1, titulo=f"Resumen ejecutivo — {p['nombre']}")
    return ws


def _hoja_sitio(wb, d):
    ws = wb.create_sheet(HOJAS[2])
    p, t, r = d["proyecto"], d["turbina"], d["recurso"]
    serie = {"nasa": "NASA POWER (satélite / reanálisis)"}.get(r.get("serie_uso"), str(r.get("serie_uso") or "—").upper())
    _kpis(ws, [
        ("Latitud", p.get("lat")), ("Longitud", p.get("lon")),
        ("País según coordenadas", p.get("pais_inferido_nombre") or "—"), ("Fuente de datos", p.get("fuente")),
        ("Período", f"{p.get('inicio')} a {p.get('fin')}"), ("Serie usada", serie),
        ("Altura de referencia de la serie (m)", r.get("altura_referencia_m")),
        ("Modelo de extrapolación a buje", r.get("modelo_altura")), ("Dirección usada", r.get("direccion")),
        ("Rugosidad del terreno", r.get("rugosidad")), ("Rugosidad z0 (m)", r.get("z0")),
        ("Exponente de cizalladura α", r.get("alpha")), ("Densidad del aire en sitio (kg/m³)", r.get("densidad_sitio")),
        ("Altitud del sitio (m)", r.get("altitud_m")), ("Temperatura media (°C)", r.get("temperatura_c")),
        ("Modelo de aerogenerador", t.get("modelo") or "Curva de potencia definida en la Fase 1"),
        ("Diámetro del rotor (m)", t.get("diametro_m")), ("Área barrida (m²)", t.get("area_m2")),
        ("Altura de buje (m)", t.get("altura_buje_m")), ("Potencia nominal (kW)", t.get("p_nominal_kw")),
        ("Velocidad de arranque (m/s)", t.get("cut_in")), ("Velocidad nominal (m/s)", t.get("v_nominal")),
        ("Velocidad de parada (m/s)", t.get("cut_out")), ("Coeficiente de empuje Ct", t.get("ct")),
        ("Densidad de la curva de potencia (kg/m³)", t.get("densidad_curva")), ("Número de turbinas", t.get("n_turbinas")),
    ], fila=1, titulo="Sitio y aerogenerador")
    return ws


def _hoja_recurso(wb, d):
    ws = wb.create_sheet(HOJAS[3])
    _titulo(ws, "Recurso eólico por sector (serie a la altura de buje)", hasta=10)
    res = d["recurso"].get("resumen_sectorial")
    if res is not None and len(res) > 0:
        cols = {"Sector": "Sector", "Centro (°)": "Centro (°)", "Datos": "Datos", "Frecuencia (%)": "Frecuencia (%)",
                "Velocidad media (m/s)": "Velocidad media (m/s)", "Desv. estándar (m/s)": "Desv. estándar (m/s)",
                "k Weibull": "k Weibull", "c Weibull (m/s)": "c Weibull (m/s)", "c Rayleigh (m/s)": "c Rayleigh (m/s)",
                "Horas equivalentes anuales (h/año)": "Horas equivalentes (h/año)"}
        df = res[[c for c in cols if c in res.columns]].rename(columns=cols)
    else:
        df_s = d["energia"].get("df_aep_sector")
        df = df_s[[c for c in ("Sector", "Frecuencia (%)", "Horas equivalentes anuales (h/año)") if c in df_s.columns]].copy() \
            if df_s is not None else None
    if df is None or len(df) == 0:
        ws.cell(row=3, column=1, value="Sin datos sectoriales disponibles.")
        return ws
    _tabla(ws, df, fila=3)
    letra = ws.cell(row=3, column=len(df.columns) + 2).column_letter
    _insertar_png(ws, _g_rosa(df["Sector"].astype(str).tolist(), pd.to_numeric(df["Frecuencia (%)"], errors="coerce").fillna(0).tolist(),
                              "Rosa de vientos — frecuencia", "%", _PAL["navy"]), f"{letra}3", 430)
    if "Velocidad media (m/s)" in df.columns:
        _insertar_png(ws, _g_rosa(df["Sector"].astype(str).tolist(), pd.to_numeric(df["Velocidad media (m/s)"], errors="coerce").fillna(0).tolist(),
                                  "Velocidad media por sector", "m/s", _PAL["green"]), f"{letra}27", 430)
    return ws


def _hoja_curva(wb, d):
    ws = wb.create_sheet(HOJAS[4])
    _titulo(ws, "Curva de potencia y coeficiente Cp", hasta=6)
    t = d["turbina"]
    curva = t.get("df_curva")
    if curva is None or len(curva) == 0:
        ws.cell(row=3, column=1, value="Sin curva de potencia en la Fase 1.")
        return ws
    try:
        from calculos import calcular_cp

        cp = calcular_cp(curva.copy(), t.get("densidad_curva") or 1.225, t.get("area_m2") or math.pi * ((t.get("diametro_m") or 100) / 2) ** 2)
    except Exception:
        cp = None
    df = pd.DataFrame({
        "Velocidad (m/s)": pd.to_numeric(curva["Velocidad_num"], errors="coerce"),
        "Potencia (kW)": pd.to_numeric(curva["Potencia_W"], errors="coerce") / 1000.0,
    })
    if cp is not None and "P_viento_W" in cp.columns:
        df["Potencia del viento (kW)"] = pd.to_numeric(cp["P_viento_W"], errors="coerce").to_numpy() / 1000.0
        df["Cp"] = pd.to_numeric(cp["Cp"], errors="coerce").to_numpy()
    _tabla(ws, df, fila=3)
    _insertar_png(ws, graficas.curva_potencia(
        curva, "es", diametro=t.get("diametro_m"), densidad=t.get("densidad_curva"),
        marcas=[("Arranque", t.get("cut_in")), ("Nominal", t.get("v_nominal")), ("Parada", t.get("cut_out"))],
        titulo=f"Curva de potencia — {fmt_num(t.get('p_nominal_kw'), 0)} kW, rotor {fmt_num(t.get('diametro_m'), 1)} m",
    ), "G3", 820)
    return ws


def _hoja_sectores(wb, d):
    from openpyxl.formatting.rule import ColorScaleRule

    ws = wb.create_sheet(HOJAS[5])
    _titulo(ws, "Energía por sector direccional (Fase 5)", hasta=10)
    df_s = d["energia"].get("df_aep_sector")
    if df_s is None or len(df_s) == 0:
        ws.cell(row=3, column=1, value="Sin datos sectoriales.")
        return ws
    df = df_s.copy()
    if "Potencia media por turbina (W)" in df.columns:
        df["Potencia media por turbina (W)"] = pd.to_numeric(df["Potencia media por turbina (W)"], errors="coerce") / 1000.0
        df = df.rename(columns={"Potencia media por turbina (W)": "Potencia media por turbina (kW)"})
    fin = _tabla(ws, df, fila=3)
    cols = list(df.columns)
    escala = ColorScaleRule(start_type="min", start_color="FEE2E2", mid_type="percentile", mid_value=50,
                            mid_color="FEF3C7", end_type="max", end_color="86EFAC")
    for nombre in ("Frecuencia (%)", "AEP neta sector (MWh/año)"):
        if nombre in cols:
            letra = ws.cell(row=3, column=cols.index(nombre) + 1).column_letter
            ws.conditional_formatting.add(f"{letra}4:{letra}{fin}", escala)
    if "AEP bruta parque (MWh/año)" in cols and "AEP neta sector (MWh/año)" in cols:
        _insertar_png(ws, _g_barras_sector(df["Sector"].astype(str).tolist(), df["AEP bruta parque (MWh/año)"].astype(float).tolist(),
                                           df["AEP neta sector (MWh/año)"].astype(float).tolist()), f"A{fin + 3}", 900)
    return ws


def _hoja_cascada(wb, d):
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import PatternFill

    ws = wb.create_sheet(HOJAS[6])
    _titulo(ws, "Cascada de pérdidas (mismo cálculo secuencial que la Fase 5)", hasta=5)
    e = d["energia"]
    pasos = [p for p in e.get("cascada") or [] if p["clave"] in ("bruta", "estela", "disp_turb", "elec", "otras") or p["perdida_mwh"] > 0]
    if not pasos:
        ws.cell(row=3, column=1, value="Sin resultados de la Fase 5.")
        return ws
    neta = e.get("aep_neta_mwh") or pasos[-1]["acumulada_mwh"]
    bruta = pasos[0]["acumulada_mwh"]
    filas = [{"Etapa": "AEP bruta", "Energía (MWh/año)": bruta, "Pérdida (%)": None, "AEP acumulada (MWh/año)": bruta}]
    for p in pasos[1:]:
        filas.append({"Etapa": p["etiqueta"], "Energía (MWh/año)": -p["perdida_mwh"], "Pérdida (%)": p["pct"],
                      "AEP acumulada (MWh/año)": p["acumulada_mwh"]})
    filas.append({"Etapa": "AEP neta", "Energía (MWh/año)": neta,
                  "Pérdida (%)": (bruta - neta) / bruta * 100.0 if bruta else None, "AEP acumulada (MWh/año)": neta})
    fin = _tabla(ws, pd.DataFrame(filas), fila=3)
    rng = f"C5:C{fin - 1}"
    ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["10"], fill=PatternFill("solid", fgColor="FCA5A5")))
    ws.conditional_formatting.add(rng, CellIsRule(operator="between", formula=["5", "10"], fill=PatternFill("solid", fgColor="FDE68A")))
    _insertar_png(ws, _g_cascada(pasos, neta), "G3", 900)
    return ws


def _hoja_turbinas(wb, d):
    ws = wb.create_sheet(HOJAS[7])
    _titulo(ws, "AEP por aerogenerador (reparto uniforme)", hasta=8)
    t, e = d["turbina"], d["energia"]
    turbinas = d["layout"]["turbinas"]
    n = len(turbinas) or (t.get("n_turbinas") or 0)
    if not turbinas or not e.get("aep_neta_mwh"):
        ws.cell(row=3, column=1, value="Sin layout o sin AEP de la Fase 5.")
        return ws
    fila = _nota(ws, 2, ("La app calcula la AEP del parque completo. Aquí se reparte por igual entre turbinas; no es un cálculo "
                         "turbina a turbina (para eso se requiere un modelo de estela por turbina)."), hasta=6, alto=36)
    por_turbina = e["aep_neta_mwh"] / n
    fp = (por_turbina / (t["p_nominal_kw"] / 1000.0 * 8760.0) * 100.0) if t.get("p_nominal_kw") else None
    df = pd.DataFrame([{"Turbina": x["id"], "x (m)": x["x_m"], "y (m)": x["y_m"], "AEP neta estimada (MWh/año)": por_turbina,
                        "Factor de planta (%)": fp} for x in turbinas])
    _tabla(ws, df, fila=fila + 1)
    _insertar_png(ws, _g_layout(turbinas, t.get("diametro_m")), f"H{fila + 1}", 560)
    return ws


def _hoja_incertidumbre(wb, d):
    ws = wb.create_sheet(HOJAS[8])
    inc = d["incertidumbre"]
    if inc.get("fuente") == "monte_carlo":
        _titulo(ws, "Incertidumbre de la AEP — Monte Carlo de la Fase 5", hasta=5)
        textos = {
            "recurso": ("Recurso eólico (Weibull k y c)", "Forma y escala de la distribución del viento; la AEP varía ≈ 2,5·σc + 0,3·σk"),
            "curva": ("Curva de potencia", "Desviación de la curva de potencia garantizada"),
            "estela": ("Pérdida por estela", "Variación relativa de la pérdida por estela (su efecto en la AEP es proporcional a esa pérdida)"),
            "perdidas": ("Pérdidas operativas", "Variación relativa de cada pérdida (disponibilidad, eléctricas, otras)"),
        }
        filas = [{"Fuente de incertidumbre": textos[x["clave"]][0], "σ de entrada": x["sigma_entrada"],
                  "Qué representa": textos[x["clave"]][1], "Efecto en la AEP (σ, %)": x["sigma_aep"]} for x in inc["presupuesto"]]
        filas.append({"Fuente de incertidumbre": "Total combinado (raíz de la suma de cuadrados)", "σ de entrada": "",
                      "Qué representa": "Aproximación analítica del mismo modelo", "Efecto en la AEP (σ, %)": inc.get("sigma_rss_pct")})
        filas.append({"Fuente de incertidumbre": "Resultado del Monte Carlo (σ / media)", "σ de entrada": "",
                      "Qué representa": f"{fmt_num(inc.get('n'), 0)} muestras, semilla {fmt_num(inc.get('semilla'), 0)}",
                      "Efecto en la AEP (σ, %)": inc.get("cv_pct")})
        fin = _tabla(ws, pd.DataFrame(filas), fila=3, filtro=False)
        ws.column_dimensions["C"].width = 60
    else:
        _titulo(ws, "Incertidumbre de la AEP — estimación genérica (no se ejecutó el Monte Carlo de la Fase 5)", hasta=5)
        filas = [{"Categoría": nombre, "σ (%)": valor} for nombre, valor in inc.get("categorias", [])]
        filas.append({"Categoría": "Total combinado (RSS)", "σ (%)": inc.get("cv_pct")})
        fin = _tabla(ws, pd.DataFrame(filas), fila=3, filtro=False)
    p50 = inc.get("p50") or 0
    tabla_p = pd.DataFrame([
        {"Percentil": nombre, "AEP (MWh/año)": valor, "% de P50": (valor / p50 * 100.0) if (valor and p50) else None}
        for nombre, valor in (("P50", inc.get("p50")), ("P75", inc.get("p75")), ("P90", inc.get("p90")), ("P99", inc.get("p99")))
    ])
    ws.cell(row=fin + 2, column=1, value="Percentiles de la AEP").font = _styles()["h2_font"]
    _tabla(ws, tabla_p, fila=fin + 3, congelar=False, filtro=False)
    return ws


def _hoja_economia(wb, d):
    ws = wb.create_sheet(HOJAS[9])
    eco = d["economia"]
    mon, f = eco["moneda"], eco.get("factor") or 1.0
    _titulo(ws, f"CAPEX — desglose calculado en la Fase 5 ({mon})", hasta=4)
    items = [(_ETIQUETAS_CAPEX.get(x["concepto"], x["concepto"]), x["valor"] * f) for x in eco.get("capex_items", [])]
    total = (eco.get("capex_total") or 0) * f
    if not items:
        items = [("CAPEX total (sin desglose)", total)]
    df = pd.DataFrame([{"Concepto": k, f"Monto ({mon})": v, "% del total": (v / total * 100.0) if total else None} for k, v in items])
    df.loc[len(df)] = {"Concepto": "TOTAL", f"Monto ({mon})": total, "% del total": 100.0 if total else None}
    fin = _tabla(ws, df, fila=3, filtro=False)
    if eco.get("capex_mode") == "manual_total":
        fin = _nota(ws, fin + 1, "El CAPEX se introdujo como un total en la Fase 5; no hay desglose por componentes.", hasta=4)
    _insertar_png(ws, _g_torta(f"CAPEX total: {mon} {fmt_num(total, 0)}", items, mon), "F3", 700)
    fila = max(fin + 3, 30)
    ws.cell(row=fila, column=1, value=f"OPEX anual — desglose ({mon})").font = _styles()["h2_font"]
    items_o = [(x["concepto"], x["valor"] * f) for x in eco.get("opex_items", []) if x["valor"] > 0]
    total_o = (eco.get("opex_total") or 0) * f
    if not items_o:
        items_o = [("OPEX anual total", total_o)]
    df_o = pd.DataFrame([{"Concepto": k, f"Monto anual ({mon})": v, "% del total": (v / total_o * 100.0) if total_o else None} for k, v in items_o])
    df_o.loc[len(df_o)] = {"Concepto": "TOTAL", f"Monto anual ({mon})": total_o, "% del total": 100.0 if total_o else None}
    _tabla(ws, df_o, fila=fila + 1, congelar=False, filtro=False)
    grafica_o = _g_torta(f"OPEX anual: {mon} {fmt_num(total_o, 0)}", items_o, mon)
    if grafica_o:
        _insertar_png(ws, grafica_o, f"F{fila + 1}", 700)
    return ws


def _hoja_flujo(wb, d):
    ws = wb.create_sheet(HOJAS[10])
    eco = d["economia"]
    mon, f = eco["moneda"], eco.get("factor") or 1.0
    _titulo(ws, f"Flujo de caja — vida útil {eco.get('vida_util')} años ({mon}), mismo modelo que la Fase 5", hasta=10)
    flujo = eco.get("flujo_anual") or []
    if not flujo:
        ws.cell(row=3, column=1, value="Sin precio de venta en la Fase 5: no se puede construir el flujo de caja.")
        return ws
    df = pd.DataFrame([{
        "Año": x["anio"], "Energía (MWh)": x["energia_mwh"], f"Ingresos ({mon})": x["ingresos"] * f,
        f"OPEX ({mon})": -x["opex"] * f, f"Inversión ({mon})": -x["inversion"] * f, f"Valor residual ({mon})": x["residual"] * f,
        f"Flujo neto ({mon})": x["flujo"] * f, f"Flujo descontado ({mon})": x["flujo_desc"] * f,
        f"Acumulado ({mon})": x["acumulado"] * f, f"Acumulado descontado ({mon})": x["acumulado_desc"] * f,
    } for x in flujo])
    fin = _tabla(ws, df, fila=3)
    s = _styles()
    ws.cell(row=fin + 2, column=1, value=f"VPN (suma de flujos descontados) ({mon})").font = s["label_font"]
    ws.cell(row=fin + 2, column=2, value=flujo[-1]["acumulado_desc"] * f).number_format = "#,##0"
    ws.cell(row=fin + 3, column=1, value=f"VPN reportado en la Fase 5 ({mon})").font = s["label_font"]
    ws.cell(row=fin + 3, column=2, value=(eco.get("npv") or 0) * f).number_format = "#,##0"
    _insertar_png(ws, _g_flujo([x["anio"] for x in flujo], [x["flujo"] * f for x in flujo], [x["acumulado"] * f for x in flujo],
                               mon, eco.get("vida_util")), f"A{fin + 6}", 900)
    return ws


def _hoja_sensibilidad(wb, d):
    ws = wb.create_sheet(HOJAS[11])
    eco = d["economia"]
    mon, f, delta = eco["moneda"], eco.get("factor") or 1.0, eco.get("sens_delta_pct") or 15.0
    base = (eco.get("npv") or 0) * f
    _titulo(ws, f"Sensibilidad del VPN (±{fmt_num(delta, 0)} % en cada variable; VPN base = {mon} {fmt_num(base, 0)})", hasta=6)
    nombres = {"precio": "Precio de venta", "aep": "Producción (AEP)", "capex": "CAPEX", "opex": "OPEX"}
    filas = [{"etiqueta": f"{nombres[x['clave']]} ±{fmt_num(delta, 0)} %", "npv_menos": x["npv_menos"] * f, "npv_mas": x["npv_mas"] * f}
             for x in eco.get("sensibilidad", [])]
    if not filas:
        ws.cell(row=3, column=1, value="Sin datos económicos suficientes.")
        return ws
    df = pd.DataFrame([{"Variable": x["etiqueta"], f"VPN con −{fmt_num(delta, 0)} % ({mon})": x["npv_menos"], f"VPN base ({mon})": base,
                        f"VPN con +{fmt_num(delta, 0)} % ({mon})": x["npv_mas"], f"Rango ({mon})": abs(x["npv_mas"] - x["npv_menos"])} for x in filas])
    _tabla(ws, df, fila=3, filtro=False)
    _insertar_png(ws, _g_tornado(filas, base, mon, delta), "H3", 880)
    return ws


def _hoja_iec(wb, d):
    ws = wb.create_sheet(HOJAS[12])
    iec, r = d["iec"], d["recurso"]
    _titulo(ws, f"IEC 61400-1 — clase declarada {iec.get('clase_declarada')} / turbulencia {iec.get('categoria_declarada')} (evaluación de la Fase 5)", hasta=5)

    def _res(valor):
        return {True: "Cumple", False: "No cumple", None: "Sin datos"}[valor]

    df = pd.DataFrame([
        {"Criterio": "Velocidad media anual a la altura de buje (m/s)", "Sitio": r.get("v_media_buje"),
         "Límite de la clase": iec.get("v_avg_clase"), "Resultado": _res(iec.get("cumple_velocidad"))},
        {"Criterio": "Intensidad de turbulencia a 15 m/s (TI)", "Sitio": r.get("ti_15"),
         "Límite de la clase": iec.get("ti_clase"), "Resultado": _res(iec.get("cumple_turbulencia")) + " (indicativo)"},
        {"Criterio": "Velocidad de referencia de la clase V_ref (m/s)", "Sitio": "No calculada",
         "Límite de la clase": iec.get("v_ref_clase"), "Resultado": "Requiere análisis de extremos"},
        {"Criterio": "Veredicto global", "Sitio": "", "Límite de la clase": "", "Resultado": _res(iec.get("cumple"))},
    ])
    fin = _tabla(ws, df, fila=3, filtro=False)
    for fila in range(4, fin + 1):
        ws.cell(row=fila, column=2).number_format = "0.000" if fila == 5 else "0.00"
        ws.cell(row=fila, column=3).number_format = "0.00"
    _nota(ws, fin + 2, ("La TI se estima con la serie horaria de la app; la norma usa estadísticos de 10 minutos, por lo que la "
                        "comprobación de turbulencia es indicativa y debe confirmarse con medición."), hasta=5, alto=40)
    return ws


def _hoja_supuestos(wb, d):
    ws = wb.create_sheet(HOJAS[13])
    e, t, r, eco, inc = d["energia"], d["turbina"], d["recurso"], d["economia"], d["incertidumbre"]
    mon = eco["moneda"]
    pp = e.get("perdidas_pct") or {}
    filas = [
        ("Densidad de la curva de potencia (kg/m³)", t.get("densidad_curva")), ("Densidad del aire en sitio (kg/m³)", r.get("densidad_sitio")),
        ("Modo de estela", e.get("wake_mode")), ("Modelo de estela", e.get("wake_model")),
        ("Pérdida por estela aplicada (%)", e.get("estela_pct")),
    ]
    if not e.get("wake_automatica"):
        filas.append(("Pérdida por estela manual (%)", e.get("wake_manual_pct")))
    filas += [
        ("Coeficiente de empuje Ct", t.get("ct")),
        ("Disponibilidad de turbinas (%)", pp.get("disp_turb")), ("Disponibilidad de red (%)", pp.get("disp_red")),
        ("Pérdidas eléctricas (%)", pp.get("elec")), ("Hielo / soiling (%)", pp.get("hielo")),
        ("Histéresis (%)", pp.get("histeresis")), ("Curtailment (%)", pp.get("curtailment")), ("Otras pérdidas (%)", pp.get("otras")),
        ("Vida útil (años)", eco.get("vida_util")), ("Tasa de descuento (%)", eco.get("tasa_pct")),
        ("Degradación anual de la energía (%)", eco.get("degradacion_pct")),
        (f"Precio de venta ({mon}/MWh)", None if eco.get("precio_mwh") is None else eco["precio_mwh"] * (eco.get("factor") or 1.0)),
        (f"Valor residual ({mon})", (eco.get("valor_residual") or 0) * (eco.get("factor") or 1.0)),
        ("Variación de sensibilidad (%)", eco.get("sens_delta_pct")),
    ]
    if inc.get("fuente") == "monte_carlo":
        sig = inc.get("sigmas_entrada") or {}
        filas += [("Muestras del Monte Carlo", inc.get("n")), ("Semilla del Monte Carlo", inc.get("semilla")),
                  ("σ Weibull k (%)", sig.get("k")), ("σ Weibull c (%)", sig.get("c")), ("σ curva de potencia (%)", sig.get("curva")),
                  ("σ pérdidas, relativa (%)", sig.get("perdidas")), ("σ estela, relativa (%)", sig.get("estela"))]
    _kpis(ws, filas, fila=1, titulo="Supuestos del cálculo")
    return ws


def _hoja_glosario(wb, d):
    ws = wb.create_sheet(HOJAS[14])
    _titulo(ws, "Glosario, acrónimos y referencias normativas", hasta=2)
    glosario = pd.DataFrame([
        ("AEP", "Producción anual de energía (Annual Energy Production)"),
        ("P50 / P75 / P90 / P99", "Producción que se supera con 50 / 75 / 90 / 99 % de probabilidad"),
        ("TI", "Intensidad de turbulencia (desviación / velocidad media)"),
        ("VPN", "Valor presente neto de los flujos de caja"),
        ("TIR", "Tasa interna de retorno"),
        ("LCOE", "Costo nivelado de la energía"),
        ("WACC", "Costo promedio ponderado del capital"),
        ("DSCR", "Cobertura del servicio de la deuda"),
        ("EYA", "Evaluación de producción energética (Energy Yield Assessment)"),
        ("MCP", "Medir-correlacionar-predecir (corrección de largo plazo)"),
        ("Ct", "Coeficiente de empuje del rotor"),
        ("BOP", "Balance of Plant: obra civil, eléctrica y subestación"),
        ("EPC", "Contrato llave en mano de ingeniería, compras y construcción"),
        ("FID", "Decisión final de inversión"),
    ], columns=["Término", "Definición"])
    fin = _tabla(ws, glosario, fila=3, filtro=False)
    ws.column_dimensions["B"].width = 70
    refs = pd.DataFrame({"Referencia": [
        "IEC 61400-1 Ed. 4 (2019) — Wind energy generation systems — Part 1: Design requirements",
        "IEC 61400-12-1 Ed. 3 (2022) — Power performance measurements",
        "IEC 61400-15-1 (2025) — Site specific wind conditions assessment",
        "IEC 61400-15-2 (en desarrollo) — Energy yield assessment and reporting",
        "DNV-SE-0073 (2022) — Project certification of wind farms",
        "DNV-ST-0437 (2021) — Loads and site conditions for wind turbines",
        "ISO 9613-2:1996 — Acoustics — Attenuation of sound during propagation outdoors",
        "Jensen, N. O. (1983) — A note on wind generator interaction (Risø-M-2411)",
        "Bastankhah & Porté-Agel (2014) — A new analytical model for wind-turbine wakes",
        "Pedersen et al. (2022) — Turbulence Optimized Park (TurbOPark) model",
        "IRENA (2024) — Renewable Power Generation Costs",
        "NASA POWER — NASA Langley Research Center",
        "ERA5 — Copernicus Climate Change Service (ECMWF)",
    ]})
    ws.cell(row=fin + 2, column=1, value="Referencias").font = _styles()["h2_font"]
    _tabla(ws, refs, fila=fin + 3, congelar=False, filtro=False)
    return ws


def _hoja_diurna(wb, d):
    from openpyxl.formatting.rule import ColorScaleRule

    ws = wb.create_sheet(HOJAS[15])
    s = _styles()
    r = d["recurso"]
    df, col, etiqueta = r.get("df_analisis"), "WS_ANALISIS", f"a {fmt_num(d['turbina'].get('altura_buje_m'), 0)} m (altura de buje)"
    if df is None or col not in getattr(df, "columns", []):
        df = r.get("df_nasa")
        col = "WS50M"
        etiqueta = "a 50 m (serie NASA POWER)"
        if df is not None and "WS_MCP" in df.columns and pd.to_numeric(df["WS_MCP"], errors="coerce").notna().any() and r.get("mcp_aplicado"):
            col, etiqueta = "WS_MCP", "a 50 m (serie corregida por MCP)"
    _titulo(ws, f"Velocidad media por hora y mes {etiqueta}", hasta=14)
    if df is None or col not in getattr(df, "columns", []) or len(df) == 0:
        ws.cell(row=3, column=1, value="Sin serie horaria disponible (abra la Fase 5 en esta sesión antes de exportar).")
        return ws
    tiempos = pd.to_datetime(df["timestamp"], errors="coerce") if "timestamp" in df.columns else pd.to_datetime(df.index, errors="coerce")
    serie = pd.DataFrame({"v": pd.to_numeric(df[col], errors="coerce").to_numpy(), "t": tiempos}).dropna()
    if len(serie) == 0:
        ws.cell(row=3, column=1, value="La serie horaria no tiene fechas válidas.")
        return ws
    pivote = serie.assign(hora=serie["t"].dt.hour, mes=serie["t"].dt.month).pivot_table(values="v", index="hora", columns="mes", aggfunc="mean")
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    for j, texto in enumerate(["Hora \\ Mes"] + meses, start=1):
        c = ws.cell(row=3, column=j, value=texto)
        c.font, c.fill, c.alignment, c.border = s["header_font"], s["header_fill"], s["header_align"], s["border"]
    for h in range(24):
        ws.cell(row=4 + h, column=1, value=f"{h:02d}:00").font = s["label_font"]
        for mes in range(1, 13):
            valor = pivote.loc[h, mes] if (h in pivote.index and mes in pivote.columns) else None
            c = ws.cell(row=4 + h, column=1 + mes, value=None if valor is None or valor != valor else float(valor))
            c.number_format, c.border = "0.00", s["border"]
    ws.conditional_formatting.add("B4:M27", ColorScaleRule(start_type="min", start_color="63BE7B", mid_type="percentile",
                                                           mid_value=50, mid_color="FFEB84", end_type="max", end_color="F8696B"))
    ws.column_dimensions["A"].width = 13
    for j in range(2, 14):
        ws.column_dimensions[ws.cell(row=3, column=j).column_letter].width = 9
    ws.freeze_panes = "B4"
    for fila, (texto, valor) in enumerate((("Velocidad media global (m/s)", serie["v"].mean()),
                                           ("Máximo de la tabla (m/s)", float(pivote.values.max())),
                                           ("Mínimo de la tabla (m/s)", float(pivote.values.min()))), start=29):
        ws.cell(row=fila, column=1, value=texto).font = s["label_font"]
        ws.cell(row=fila, column=2, value=float(valor)).number_format = "0.00"
    return ws


def _huella_datos(d):
    base = {
        "proyecto": {k: d["proyecto"].get(k) for k in ("nombre", "lat", "lon", "inicio", "fin", "pais_codigo")},
        "turbina": {k: v for k, v in d["turbina"].items() if k != "df_curva"},
        "energia": {k: v for k, v in d["energia"].items() if not k.startswith("df_") and k not in ("tabla_perdidas", "cascada")},
        "incertidumbre": {k: v for k, v in d["incertidumbre"].items() if k not in ("presupuesto", "categorias")},
        "economia": {k: v for k, v in d["economia"].items() if k not in ("flujo_anual", "sensibilidad", "capex_items", "opex_items")},
    }
    texto = json.dumps(base, ensure_ascii=False, sort_keys=True, default=lambda v: round(v, 6) if isinstance(v, float) else str(v))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _git_commit():
    try:
        salida = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(Path(__file__).resolve().parents[1]),
                                capture_output=True, text=True, timeout=3)
        return salida.stdout.strip() or "—"
    except Exception:
        return "—"


def _hoja_manifiesto(wb, d):
    ws = wb.create_sheet(HOJAS[16])
    versiones = []
    for paquete in ("pandas", "numpy", "openpyxl", "streamlit"):
        try:
            import importlib.metadata as md

            versiones.append(f"{paquete} {md.version(paquete)}")
        except Exception:
            pass
    ahora = datetime.now()
    fila = _kpis(ws, [
        ("Generado (hora local)", ahora.strftime("%Y-%m-%d %H:%M:%S")),
        ("Generado (UTC)", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")),
        ("Versión de SMA", "2.0"), ("Commit de la app", _git_commit()),
        ("Proyecto", d["proyecto"]["nombre"]), ("Formato", "xlsx (Excel PRO, 17 hojas)"),
        ("Python", platform.python_version()), ("Paquetes", " · ".join(versiones) or "—"),
        ("Huella SHA-256 de los datos", _huella_datos(d)),
    ], fila=1, titulo="Manifiesto de trazabilidad")
    _nota(ws, fila + 1, ("La huella SHA-256 se calcula sobre los parámetros y resultados del proyecto (no sobre el archivo): "
                         "dos exportaciones del mismo escenario tienen la misma huella, y cualquier cambio de datos la modifica."),
          hasta=4, color="E7EEF7", alto=44)
    return ws


# ─────────────────────────────────────────────────────────────
# Entrada pública
# ─────────────────────────────────────────────────────────────
_COLORES_PESTANA = dict(zip(HOJAS, [
    "1B365D", "1B365D", "2F5F8F", "2F5F8F", "2F5F8F", "1F7A6F", "B3261E", "1F7A6F", "C98A1B", "1B365D",
    "1B365D", "C98A1B", "1F7A6F", "8C9BAB", "8C9BAB", "2F5F8F", "2B3645",
], strict=False))


def _preparar_hojas(wb, proyecto):
    """Sin cuadrícula, horizontal, ajustada al ancho de la página y con encabezado y pie."""
    from openpyxl.worksheet.properties import PageSetupProperties

    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        ws.print_options.horizontalCentered = True
        ws.page_margins.left = ws.page_margins.right = 0.5
        ws.page_margins.top = ws.page_margins.bottom = 0.7
        ws.oddHeader.left.text = f"{proyecto} · Excel PRO"
        ws.oddHeader.left.size = 8
        ws.oddHeader.left.color = _NAVY
        ws.oddHeader.right.text = "&A"
        ws.oddHeader.right.size = 8
        ws.oddFooter.center.text = "Página &P de &N"
        ws.oddFooter.center.size = 8


def exportar_excel_pro(ctx: dict[str, Any]) -> bytes:
    """Genera el Excel PRO (17 hojas) del proyecto activo. Devuelve bytes .xlsx."""
    from openpyxl import Workbook

    ctx = ctx or {}
    datos = ctx.get("datos") or construir_datos_exportacion(ctx.get("config") or {}, ctx)
    wb = Workbook()
    wb.remove(wb.active)
    for hoja in (_hoja_portada, _hoja_resumen, _hoja_sitio, _hoja_recurso, _hoja_curva, _hoja_sectores, _hoja_cascada,
                 _hoja_turbinas, _hoja_incertidumbre, _hoja_economia, _hoja_flujo, _hoja_sensibilidad, _hoja_iec,
                 _hoja_supuestos, _hoja_glosario, _hoja_diurna, _hoja_manifiesto):
        hoja(wb, datos)
    _preparar_hojas(wb, datos["proyecto"]["nombre"])
    for nombre, color in _COLORES_PESTANA.items():
        if nombre in wb.sheetnames:
            wb[nombre].sheet_properties.tabColor = color
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


__all__ = ["HOJAS", "exportar_excel_pro"]
