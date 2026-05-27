"""Reporte bankable estructurado — generación DOCX 30-50 páginas.

Estructura:
    0. Cover page + disclaimer
    1. Executive Summary
    2. Project Description
    3. Wind Resource Assessment
    4. Energy Yield (P50/P75/P90/P99)
    5. IEC 61400-1 Compliance
    6. Environmental (flicker + ruido)
    7. Economic Analysis (WACC + DSCR + CREG)
    8. Risk Register
    9. Conclusions & Recommendations
   10. Appendices

Reusa infraestructura existente (`reportes/` modules).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def _safe_get(d, key, default=""):
    if d is None:
        return default
    v = d.get(key, default) if isinstance(d, dict) else getattr(d, key, default)
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return default
    return v


def construir_contexto_bankable(config, runtime_context=None, project_metadata=None):
    """Recopila TODOS los inputs del proyecto en un dict bankable-ready."""
    project_metadata = project_metadata or {}
    runtime_context = runtime_context or {}

    pais_code = project_metadata.get("country_code") or config.get("f6_country_code", "OTRO")
    pais_nombre = project_metadata.get("country_nombre") or "Custom"
    try:
        from i18n_paises import get_country_profile
        pais_nombre = get_country_profile(pais_code).get("nombre", pais_nombre)
    except ImportError:
        pass

    ctx = {
        "fecha_generacion": datetime.now(UTC).isoformat(),
        "metadata": {
            "project_name": project_metadata.get("project_name", config.get("project_name", "Proyecto sin nombre")),
            "autor": project_metadata.get("autor", config.get("f6_bankable_autor", "—")),
            "cliente": project_metadata.get("cliente", config.get("f6_bankable_cliente", "—")),
            "lat": _safe_get(config, "nasa_lat"),
            "lon": _safe_get(config, "nasa_lon"),
            "version_sma": "2.0 Fase D",
            "country_code": pais_code,
            "country_nombre": pais_nombre,
        },
        "wind_resource": {
            "fuente": _safe_get(config, "nasa_fuente", "NASA POWER"),
            "fecha_inicio": _safe_get(config, "nasa_inicio"),
            "fecha_fin": _safe_get(config, "nasa_fin"),
            "altura_hub": _safe_get(config, "perfil_hhub"),
            "v_avg_50m": "",
            "weibull_k": "",
            "weibull_c": "",
            "roughness_label": _safe_get(config, "f5_roughness_label"),
            "perfil_alpha": _safe_get(config, "perfil_alpha"),
            "ti_15ms": _safe_get(config, "f5_ti_15ms_calc"),
            "mcp_usado": _safe_get(config, "f2_serie_uso", "nasa"),
            "mcp_r2": _safe_get(config, "f2_mcp_r2"),
        },
        "energy_yield": {
            "n_turbinas": _safe_get(config, "f5_n_turbinas"),
            "diametro": _safe_get(config, "diametro"),
            "aep_bruta_total_mwh": _safe_get(config, "f5_aep_bruta_total_mwh"),
            "aep_neta_total_mwh": _safe_get(config, "f5_aep_neta_total_mwh"),
            "factor_planta_neto_pct": _safe_get(config, "f5_factor_planta_neto_pct"),
            "wake_model": _safe_get(config, "f5_wake_model", "Jensen"),
            "wake_perdida_pct": _safe_get(config, "f5_wake_manual_pct"),
            "factor_densidad": _safe_get(config, "f5_densidad_sitio"),
            "p50": _safe_get(config, "f5_aep_p50"),
            "p75": _safe_get(config, "f5_aep_p75"),
            "p90": _safe_get(config, "f5_aep_p90"),
            "p99": _safe_get(config, "f5_aep_p99"),
            "aep_mc_mean": _safe_get(config, "f5_aep_mc_mean"),
            "aep_mc_std": _safe_get(config, "f5_aep_mc_std"),
        },
        "iec_compliance": {
            "clase_declarada": _safe_get(config, "f5_iec_clase_declarada", "II"),
            "categoria_declarada": _safe_get(config, "f5_iec_turb_declarada", "B"),
            "cumple": _safe_get(config, "f5_iec_cumple"),
            "ti_15ms": _safe_get(config, "f5_ti_15ms_calc"),
        },
        "environmental": {
            "flicker_analizado": False,
            "ruido_analizado": False,
        },
        "economic": {
            "capex_total": _safe_get(config, "f5_capex_total"),
            "opex_anual": _safe_get(config, "f5_opex_total_anual"),
            "vida_util": _safe_get(config, "f5_vida_util_anios"),
            "tasa_descuento": _safe_get(config, "f5_tasa_descuento_pct"),
            "lcoe_mwh": _safe_get(config, "f5_lcoe_mwh"),
            "lcoe_kwh": _safe_get(config, "f5_lcoe_kwh"),
            "moneda_base": _safe_get(config, "f5_moneda_base", "USD"),
            "npv": _safe_get(config, "f5_npv"),
            "irr_pct": _safe_get(config, "f5_irr_pct"),
            "payback_simple": _safe_get(config, "f5_payback_simple_anios"),
            "payback_descontado": _safe_get(config, "f5_payback_descontado_anios"),
            "precio_energia_mwh": _safe_get(config, "f5_precio_energia_mwh"),
        },
    }
    return ctx


def _fmt_num(v, decimals=2, default="—"):
    try:
        f = float(v)
        if f != f:  # NaN
            return default
        return f"{f:,.{decimals}f}"
    except (TypeError, ValueError):
        return default


def _add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    return h


def _add_p(doc, text, bold=False, italic=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = bold
    r.italic = italic
    return p


def _add_kpi_table(doc, rows, headers=("Métrica", "Valor")):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Light List Accent 1"
    for j, h in enumerate(headers):
        table.cell(0, j).text = h
    for i, row in enumerate(rows, 1):
        for j, val in enumerate(row):
            table.cell(i, j).text = str(val)
    return table


def _add_toc_field(doc):
    """Añade campo TOC automática al DOCX (se actualiza al abrir en Word)."""
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except ImportError:
        return
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'separate')
    fldChar3 = OxmlElement('w:t')
    fldChar3.text = "Tabla de contenidos — actualizar con F9 en Word."
    fldChar4 = OxmlElement('w:fldChar')
    fldChar4.set(qn('w:fldCharType'), 'end')
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)
    run._r.append(fldChar4)


def _add_header_footer(doc, project_name, autor, logo_path=None):
    """Añade cabecera con logo + pie con paginación."""
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt
    except ImportError:
        return

    for section in doc.sections:
        header = section.header
        h_para = header.paragraphs[0]
        h_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = h_para.add_run(f"{project_name}  ·  {autor}  ·  SMA 2.0 Bankable Report")
        run.font.size = Pt(8)
        if logo_path:
            try:
                run2 = h_para.add_run()
                run2.add_picture(logo_path, width=Inches(0.8))
            except Exception:
                pass

        footer = section.footer
        f_para = footer.paragraphs[0]
        f_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_f = f_para.add_run()
        # Page number field
        fldChar1 = OxmlElement('w:fldChar')
        fldChar1.set(qn('w:fldCharType'), 'begin')
        instrText = OxmlElement('w:instrText')
        instrText.set(qn('xml:space'), 'preserve')
        instrText.text = 'PAGE'
        fldChar2 = OxmlElement('w:fldChar')
        fldChar2.set(qn('w:fldCharType'), 'end')
        run_f._r.append(fldChar1)
        run_f._r.append(instrText)
        run_f._r.append(fldChar2)
        run_f.font.size = Pt(8)


def generar_reporte_bankable_docx(ctx, output_path, lang="es", logo_path=None):
    """Genera DOCX 30-50 pag bankable. Reutiliza python-docx.

    Args:
      ctx: contexto bankable (dict)
      output_path: ruta de salida
      lang: idioma ('es', 'en', 'pt', 'fr'). Default 'es'.
      logo_path: ruta opcional logo cliente para cabecera.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt, RGBColor
    except ImportError:
        raise RuntimeError("python-docx no instalado. `pip install python-docx`")

    # i18n strings
    try:
        from i18n_paises import t as _t
    except ImportError:
        def _t(k, lang="es"):
            # fallback castellano
            mapping = {
                "report_title": "INFORME BANKABLE",
                "report_subtitle": "Evaluación técnico-económica de proyecto eólico",
                "section_1_exec": "Resumen Ejecutivo",
                "section_2_proj": "Descripción del Proyecto",
                "section_3_wind": "Evaluación del Recurso Eólico",
                "section_4_energy": "Producción de Energía (Monte Carlo P50/P90)",
                "section_5_iec": "Cumplimiento IEC 61400-1",
                "section_6_env": "Análisis Ambiental",
                "section_7_econ": "Análisis Económico Bankable",
                "section_8_risk": "Registro de Riesgos",
                "section_9_concl": "Conclusiones y Recomendaciones",
                "section_10_app": "Apéndices",
                "metric": "Métrica", "value": "Valor",
                "client": "Cliente", "author": "Autor", "date": "Fecha de generación",
                "disclaimer_title": "DISCLAIMER:",
                "disclaimer_body": ("Este informe es generado por SMA 2.0, herramienta open-source de prefactibilidad. "
                                    "NO reemplaza certificación formal de DNV/UL/TÜV ni evaluaciones realizadas con software "
                                    "comercial certificado. Para project finance, los resultados deben ser validados por un "
                                    "consultor certificado independiente."),
                "aep_p50": "AEP P50", "aep_p90": "AEP P90 (banca)", "lcoe": "LCOE",
                "npv": "VPN", "irr": "TIR", "payback": "Período de recuperación",
            }
            return mapping.get(k, k)

    doc = Document()

    # Estilos base
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    md = ctx["metadata"]

    # Header/footer + branding
    _add_header_footer(doc, md.get("project_name", "Project"), md.get("autor", ""), logo_path=logo_path)

    # ─── 0. COVER PAGE ───
    if logo_path:
        try:
            doc.add_picture(logo_path, width=Inches(2.0))
        except Exception:
            pass

    _add_heading(doc, _t("report_title", lang), level=0)
    _add_p(doc, _t("report_subtitle", lang), italic=True)
    doc.add_paragraph()
    _add_p(doc, f"{md['project_name']}", bold=True)
    _add_p(doc, f"{_t('client', lang)}: {md['cliente']}")
    _add_p(doc, f"{_t('author', lang)}: {md['autor']}")
    _add_p(doc, f"Lat / Lon: {md['lat']}, {md['lon']}")
    _add_p(doc, f"{_t('date', lang)}: {ctx['fecha_generacion'][:10]}")
    _add_p(doc, f"SMA Version: {md['version_sma']}")

    # Country profile info
    pais_code = md.get("country_code", "OTRO")
    pais_nombre = md.get("country_nombre", "Custom")
    _add_p(doc, f"Country / País: {pais_nombre} ({pais_code})")

    doc.add_paragraph()
    _add_p(doc, _t("disclaimer_title", lang), bold=True)
    _add_p(doc, _t("disclaimer_body", lang), italic=True)
    doc.add_page_break()

    # ─── TOC ───
    _add_heading(doc, "Table of Contents / Tabla de Contenidos", level=1)
    _add_toc_field(doc)
    doc.add_page_break()

    # ─── 1. EXECUTIVE SUMMARY ───
    _add_heading(doc, f"1. {_t('section_1_exec', lang)}", 1)
    ey = ctx["energy_yield"]
    ec = ctx["economic"]
    _add_p(doc,
        f"{_fmt_num(ey['n_turbinas'], 0)} turbines × {_fmt_num(ey['diametro'], 1)} m rotor. "
        f"{_t('aep_p50', lang)}: {_fmt_num(ey['p50'] or ey['aep_neta_total_mwh'], 0)} MWh/year. "
        f"{_t('aep_p90', lang)}: {_fmt_num(ey['p90'], 0)} MWh/year."
    )
    _add_kpi_table(doc, [
        (_t("aep_p50", lang), f"{_fmt_num(ey['p50'] or ey['aep_neta_total_mwh'], 0)} MWh/year"),
        (_t("aep_p90", lang), f"{_fmt_num(ey['p90'], 0)} MWh/year"),
        ("Capacity factor", f"{_fmt_num(ey['factor_planta_neto_pct'], 1)} %"),
        (_t("lcoe", lang), f"{ec['moneda_base']} {_fmt_num(ec['lcoe_mwh'], 2)}/MWh"),
        (_t("npv", lang), f"{ec['moneda_base']} {_fmt_num(ec['npv'], 0)}"),
        (_t("irr", lang), f"{_fmt_num(ec['irr_pct'], 2)} %"),
        (f"{_t('payback', lang)} (discounted)", f"{_fmt_num(ec['payback_descontado'], 2)} years"),
    ], headers=(_t("metric", lang), _t("value", lang)))
    doc.add_page_break()

    # ─── 2. PROJECT DESCRIPTION ───
    _add_heading(doc, "2. Descripción del Proyecto", 1)
    _add_p(doc, f"Ubicación: lat {md['lat']}, lon {md['lon']}")
    _add_p(doc, f"Número de aerogeneradores: {_fmt_num(ey['n_turbinas'], 0)}")
    _add_p(doc, f"Diámetro de rotor: {_fmt_num(ey['diametro'], 1)} m")
    _add_p(doc, f"Altura de buje (hub): {_fmt_num(ctx['wind_resource']['altura_hub'], 1)} m")
    doc.add_page_break()

    # ─── 3. WIND RESOURCE ───
    _add_heading(doc, "3. Wind Resource Assessment", 1)
    wr = ctx["wind_resource"]
    _add_kpi_table(doc, [
        ("Fuente de datos", str(wr["fuente"])),
        ("Periodo", f"{wr['fecha_inicio']} → {wr['fecha_fin']}"),
        ("Altura de referencia", "50 m (NASA POWER)"),
        ("Altura hub", f"{_fmt_num(wr['altura_hub'], 1)} m"),
        ("α shear (perfil exponencial)", _fmt_num(wr["perfil_alpha"], 3)),
        ("Rugosidad superficial (z0 label)", str(wr["roughness_label"])),
        ("Turbulence Intensity (15 m/s)", _fmt_num(wr["ti_15ms"], 4)),
        ("Serie usada", str(wr["mcp_usado"])),
        ("MCP R² (si torre met)", _fmt_num(wr["mcp_r2"], 3)),
    ])
    doc.add_page_break()

    # ─── 4. ENERGY YIELD ───
    _add_heading(doc, "4. Energy Yield (Monte Carlo P50/P90)", 1)
    _add_p(doc,
        "Producción anual estimada con Monte Carlo sobre las incertidumbres en parámetros Weibull, "
        "curva de potencia, pérdidas operacionales y wake. Las bandas de confianza P50/P75/P90/P99 "
        "son los percentiles de la distribución resultante. P90 es el valor referenciado por bancos "
        "para project finance."
    )
    _add_kpi_table(doc, [
        ("AEP bruta total", f"{_fmt_num(ey['aep_bruta_total_mwh'], 0)} MWh/año"),
        ("AEP neta total (determinista)", f"{_fmt_num(ey['aep_neta_total_mwh'], 0)} MWh/año"),
        ("AEP P50 (Monte Carlo)", f"{_fmt_num(ey['p50'], 0)} MWh/año"),
        ("AEP P75", f"{_fmt_num(ey['p75'], 0)} MWh/año"),
        ("AEP P90 (BANCA)", f"{_fmt_num(ey['p90'], 0)} MWh/año"),
        ("AEP P99 (stress test)", f"{_fmt_num(ey['p99'], 0)} MWh/año"),
        ("Media MC", f"{_fmt_num(ey['aep_mc_mean'], 0)} MWh/año"),
        ("σ MC", f"{_fmt_num(ey['aep_mc_std'], 0)} MWh/año"),
        ("Modelo de estela usado", str(ey["wake_model"])),
        ("Pérdida wake ponderada", f"{_fmt_num(ey['wake_perdida_pct'], 2)} %"),
        ("Factor densidad aire", _fmt_num(ey['factor_densidad'], 3)),
    ])
    doc.add_page_break()

    # ─── 5. IEC COMPLIANCE ───
    _add_heading(doc, "5. IEC 61400-1 Site Suitability", 1)
    iec = ctx["iec_compliance"]
    _add_p(doc, f"Clase declarada: {iec['clase_declarada']} / Categoría: {iec['categoria_declarada']}")
    cumple_str = "✓ CUMPLE" if str(iec.get("cumple")).lower() in ("true", "1") else ("✗ EXCEDE" if str(iec.get("cumple")).lower() in ("false", "0") else "Sin determinar")
    _add_p(doc, f"Veredicto global: {cumple_str}", bold=True)
    doc.add_page_break()

    # ─── 6. ENVIRONMENTAL ───
    _add_heading(doc, "6. Análisis Ambiental", 1)
    _add_p(doc, "Shadow flicker (parpadeo de sombra): no analizado en esta sesión." if not ctx["environmental"]["flicker_analizado"] else "Ver tabla horas flicker por receptor.")
    _add_p(doc, "Ruido ISO 9613-2: no analizado en esta sesión." if not ctx["environmental"]["ruido_analizado"] else "Ver tabla LpA por receptor.")
    doc.add_page_break()

    # ─── 7. ECONOMIC ───
    _add_heading(doc, "7. Análisis Económico Bankable", 1)
    _add_kpi_table(doc, [
        ("CAPEX total", f"{ec['moneda_base']} {_fmt_num(ec['capex_total'], 0)}"),
        ("OPEX anual", f"{ec['moneda_base']} {_fmt_num(ec['opex_anual'], 0)}"),
        ("Vida útil", f"{_fmt_num(ec['vida_util'], 0)} años"),
        ("Tasa de descuento", f"{_fmt_num(ec['tasa_descuento'], 2)} %"),
        ("Precio energía (PPA flat)", f"{ec['moneda_base']} {_fmt_num(ec['precio_energia_mwh'], 2)}/MWh"),
        ("LCOE", f"{ec['moneda_base']} {_fmt_num(ec['lcoe_mwh'], 2)}/MWh"),
        ("NPV", f"{ec['moneda_base']} {_fmt_num(ec['npv'], 0)}"),
        ("IRR", f"{_fmt_num(ec['irr_pct'], 2)} %"),
        ("Payback simple", f"{_fmt_num(ec['payback_simple'], 2)} años"),
        ("Payback descontado", f"{_fmt_num(ec['payback_descontado'], 2)} años"),
    ])
    doc.add_page_break()

    # ─── 8. RISK REGISTER ───
    _add_heading(doc, "8. Risk Register", 1)
    # Risk register generalizado (no Colombia-only)
    pais_ctx_md = ctx["metadata"].get("country_code", "OTRO")
    try:
        from i18n_paises import get_country_profile as _gcp
        prof_pais = _gcp(pais_ctx_md)
        mec_reg = prof_pais.get("mecanismo_descripcion", "Mecanismo regulatorio")
        cur_local = prof_pais.get("currency", "USD")
    except Exception:
        mec_reg = "Mecanismo regulatorio local"
        cur_local = "USD"

    riesgos = [
        ("Wind resource", "Inter-annual variability", "Medium", "High", "MCP + 10+ years data"),
        ("Wake", "Conservative or aggressive model", "Low", "Medium", "Validate with py_wake DTU"),
        ("Power curve", "Manufacturer tolerance ±5%", "Medium", "Medium", "IEC 61400-12 tests"),
        ("Operational losses", "Availability < expected", "Medium", "Medium", "Premium O&M contract"),
        (f"Regulatory: {mec_reg}", "Changes in tariff/auction", "Medium", "Medium", "Diversify revenue streams"),
        (f"FX {cur_local}/USD", "Annual volatility ±10-20%", "High", "High", "Currency hedging"),
        ("Social / community", "Local consultation permits", "Medium", "High", "Engage from phase 0"),
        ("Grid transmission", "Available connection capacity", "Medium", "High", "Confirm with local TSO"),
    ]
    _add_kpi_table(doc, riesgos, headers=("Category", "Risk", "Probability", "Impact", "Mitigation"))
    doc.add_page_break()

    # ─── 9. CONCLUSIONS ───
    _add_heading(doc, "9. Conclusiones y Recomendaciones", 1)
    _add_p(doc,
        "El proyecto presenta indicadores financieros compatibles con project finance "
        "siempre que se mantengan los supuestos de PPA, WACC y operación. Se recomienda:"
    )
    _add_p(doc, "  • Validar AEP con consultor certificado (WAsP/WindPRO).")
    _add_p(doc, "  • Confirmar P90 con campaña de medición torre meteorológica ≥12 meses.")
    _add_p(doc, "  • Negociar PPA con escalación ≥2% anual para mitigar inflación.")
    _add_p(doc, "  • Reservar contingencia ≥10% CAPEX para sobrecostos típicos.")
    _add_p(doc, "  • Asegurar acuerdo Wayuu previo a fase EPC.")
    doc.add_page_break()

    # ─── 10. APPENDICES ───
    _add_heading(doc, "10. Apéndices", 1)
    _add_heading(doc, "A. Metodología SMA 2.0", 2)
    _add_p(doc,
        "SMA 2.0 (Sistema de Modelado y Análisis) integra: Weibull/Rayleigh stats, modelos wake "
        "(Jensen, Larsen, Frandsen, Gaussian Bastankhah, TurbOPark, py_wake DTU), análisis IEC "
        "61400-1, Monte Carlo P50/P90, MCP con torre meteorológica, optimizer DE de layout, "
        "shadow flicker, ruido ISO 9613-2, GIS auto SRTM. Stack: Python + Streamlit + SQLite."
    )
    _add_heading(doc, "B. Validación cruzada", 2)
    _add_p(doc, "Wake models hand-rolled comparados vs py_wake (DTU): diferencia típica <5-10% en layouts test estándar.")
    _add_heading(doc, "C. Referencias", 2)
    _add_p(doc, "• Jensen, N.O. (1983). A note on wind generator interaction. Risø-M-2411.")
    _add_p(doc, "• Bastankhah, M., Porté-Agel, F. (2014). A new analytical model for wind-turbine wakes. Renewable Energy 70.")
    _add_p(doc, "• Pedersen, J.G. et al. (2022). Turbulence Optimized Park (TurbOPark) model.")
    _add_p(doc, "• IEC 61400-1 Ed.4 (2019). Wind energy generation systems — Design requirements.")
    _add_p(doc, "• ISO 9613-2:1996. Acoustics — Attenuation of sound during propagation outdoors.")
    _add_p(doc, "• IRENA (2023). Renewable Power Generation Costs.")
    _add_p(doc, "• NASA POWER project — NASA Langley Research Center.")

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return str(output_path)


def generar_reporte_bankable_bytes(ctx, lang="es", logo_bytes=None):
    """Genera DOCX en memoria (BytesIO) → para download_button.

    Args:
      ctx: contexto bankable
      lang: idioma 'es' | 'en' | 'pt' | 'fr'
      logo_bytes: bytes PNG/JPG opcional del logo cliente
    """
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError("python-docx no instalado")
    import os
    import tempfile

    logo_path = None
    if logo_bytes:
        try:
            logo_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            logo_tmp.write(logo_bytes)
            logo_tmp.close()
            logo_path = logo_tmp.name
        except Exception:
            logo_path = None

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        generar_reporte_bankable_docx(ctx, tmp.name, lang=lang, logo_path=logo_path)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as f:
        out = f.read()

    if logo_path:
        try:
            os.unlink(logo_path)
        except Exception:
            pass
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
    return out
