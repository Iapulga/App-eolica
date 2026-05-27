"""Internacionalización SMA 2.0 — perfiles país + multi-currency + i18n strings.

Hace la app GLOBAL en vez de Colombia-only. Cubre:
  - Currencies: 14 monedas con FX manager
  - Country profiles: tax_rate, country_risk_premium, regulatory_mechanism
  - i18n strings: ES/EN/FR/PT (extensible)
  - Land cover global fallback (IGBP/MODIS) cuando no Colombia
"""

from __future__ import annotations

# ── CURRENCIES ──
# Code: {nombre, símbolo, decimales display}
CURRENCIES = {
    "USD": {"nombre": "US Dollar", "simbolo": "$",  "decimales": 2,  "region": "global"},
    "EUR": {"nombre": "Euro",      "simbolo": "€",  "decimales": 2,  "region": "EU"},
    "GBP": {"nombre": "British Pound", "simbolo": "£", "decimales": 2, "region": "UK"},
    "JPY": {"nombre": "Japanese Yen",  "simbolo": "¥", "decimales": 0, "region": "JP"},
    "CNY": {"nombre": "Chinese Yuan",  "simbolo": "¥", "decimales": 2, "region": "CN"},
    "INR": {"nombre": "Indian Rupee",  "simbolo": "₹", "decimales": 2, "region": "IN"},
    "BRL": {"nombre": "Brazilian Real","simbolo": "R$","decimales": 2, "region": "BR"},
    "MXN": {"nombre": "Mexican Peso",  "simbolo": "$", "decimales": 2, "region": "MX"},
    "COP": {"nombre": "Colombian Peso","simbolo": "$", "decimales": 0, "region": "CO"},
    "ARS": {"nombre": "Argentine Peso","simbolo": "$", "decimales": 0, "region": "AR"},
    "CLP": {"nombre": "Chilean Peso",  "simbolo": "$", "decimales": 0, "region": "CL"},
    "PEN": {"nombre": "Peruvian Sol",  "simbolo": "S/","decimales": 2, "region": "PE"},
    "ZAR": {"nombre": "South African Rand", "simbolo": "R", "decimales": 2, "region": "ZA"},
    "AUD": {"nombre": "Australian Dollar",  "simbolo": "A$","decimales": 2, "region": "AU"},
}


# ── COUNTRY PROFILES ──
# Estimaciones aprox 2024-2025. Usuario puede override.
COUNTRY_PROFILES = {
    # Country code ISO: tax_rate, country_risk_premium, default_currency, mecanismo_regulatorio
    "CO": {
        "nombre": "Colombia", "tax_rate_pct": 35.0, "country_risk_premium_pct": 2.0,
        "currency": "COP", "fx_to_usd_aprox": 4000.0,
        "mecanismo": "CREG_subasta_confiabilidad",
        "mecanismo_descripcion": "CREG cargo por confiabilidad (subasta anual)",
        "mecanismo_valor_default": 15.0,  # USD/MWh aprox
        "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 10.0,
        "limite_ruido_diurno_db": 65.0,  # CRA Resolución 627/2006
        "limite_ruido_nocturno_db": 55.0,
        "altitudes_relevantes": "0-5000m (Andes)",
    },
    "MX": {
        "nombre": "México", "tax_rate_pct": 30.0, "country_risk_premium_pct": 1.8,
        "currency": "MXN", "fx_to_usd_aprox": 18.0,
        "mecanismo": "CFE_PPA_o_mercado",
        "mecanismo_descripcion": "PPA CFE / mercado MEM",
        "mecanismo_valor_default": 50.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 9.5, "limite_ruido_diurno_db": 65.0, "limite_ruido_nocturno_db": 55.0,
        "altitudes_relevantes": "0-3000m",
    },
    "BR": {
        "nombre": "Brasil", "tax_rate_pct": 34.0, "country_risk_premium_pct": 2.5,
        "currency": "BRL", "fx_to_usd_aprox": 5.0,
        "mecanismo": "ANEEL_LER_LEN",
        "mecanismo_descripcion": "ANEEL leilões LER/LEN",
        "mecanismo_valor_default": 35.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 9.0, "limite_ruido_diurno_db": 55.0, "limite_ruido_nocturno_db": 45.0,
        "altitudes_relevantes": "0-2500m",
    },
    "CL": {
        "nombre": "Chile", "tax_rate_pct": 27.0, "country_risk_premium_pct": 1.0,
        "currency": "CLP", "fx_to_usd_aprox": 950.0,
        "mecanismo": "PPA_libre_o_licitacion",
        "mecanismo_descripcion": "Licitación pública o PPA libre",
        "mecanismo_valor_default": 55.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 8.5, "limite_ruido_diurno_db": 65.0, "limite_ruido_nocturno_db": 55.0,
        "altitudes_relevantes": "0-4500m",
    },
    "AR": {
        "nombre": "Argentina", "tax_rate_pct": 35.0, "country_risk_premium_pct": 8.0,
        "currency": "ARS", "fx_to_usd_aprox": 1000.0,
        "mecanismo": "RenovAr_o_MATER",
        "mecanismo_descripcion": "RenovAr (subasta) o MATER (mercado)",
        "mecanismo_valor_default": 40.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 14.0, "limite_ruido_diurno_db": 65.0, "limite_ruido_nocturno_db": 50.0,
        "altitudes_relevantes": "0-4000m (Patagonia, Andes)",
    },
    "PE": {
        "nombre": "Perú", "tax_rate_pct": 29.5, "country_risk_premium_pct": 1.5,
        "currency": "PEN", "fx_to_usd_aprox": 3.7,
        "mecanismo": "OSINERGMIN_subasta",
        "mecanismo_descripcion": "OSINERGMIN subastas RER",
        "mecanismo_valor_default": 45.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 9.5, "limite_ruido_diurno_db": 60.0, "limite_ruido_nocturno_db": 50.0,
        "altitudes_relevantes": "0-5000m (Andes)",
    },
    "US": {
        "nombre": "United States", "tax_rate_pct": 21.0, "country_risk_premium_pct": 0.0,
        "currency": "USD", "fx_to_usd_aprox": 1.0,
        "mecanismo": "PTC_ITC_PPA",
        "mecanismo_descripcion": "PTC/ITC tax credit + PPA bilateral",
        "mecanismo_valor_default": 26.0, "mecanismo_unidad": "USD/MWh (PTC)",
        "wacc_tipico_pct": 6.5, "limite_ruido_diurno_db": 55.0, "limite_ruido_nocturno_db": 45.0,
        "altitudes_relevantes": "0-3500m",
    },
    "ES": {
        "nombre": "España", "tax_rate_pct": 25.0, "country_risk_premium_pct": 0.5,
        "currency": "EUR", "fx_to_usd_aprox": 0.92,
        "mecanismo": "CNMC_subasta_MIBEL",
        "mecanismo_descripcion": "Subastas CNMC / MIBEL pool",
        "mecanismo_valor_default": 55.0, "mecanismo_unidad": "EUR/MWh",
        "wacc_tipico_pct": 6.0, "limite_ruido_diurno_db": 55.0, "limite_ruido_nocturno_db": 45.0,
        "altitudes_relevantes": "0-3000m (Pirineos)",
    },
    "DE": {
        "nombre": "Deutschland", "tax_rate_pct": 30.0, "country_risk_premium_pct": 0.0,
        "currency": "EUR", "fx_to_usd_aprox": 0.92,
        "mecanismo": "EEG_Bundesnetzagentur",
        "mecanismo_descripcion": "EEG Ausschreibungen Bundesnetzagentur",
        "mecanismo_valor_default": 60.0, "mecanismo_unidad": "EUR/MWh",
        "wacc_tipico_pct": 5.5, "limite_ruido_diurno_db": 50.0, "limite_ruido_nocturno_db": 40.0,
        "altitudes_relevantes": "0-2900m",
    },
    "UK": {
        "nombre": "United Kingdom", "tax_rate_pct": 25.0, "country_risk_premium_pct": 0.3,
        "currency": "GBP", "fx_to_usd_aprox": 0.79,
        "mecanismo": "CfD_BEIS",
        "mecanismo_descripcion": "Contracts for Difference (CfD)",
        "mecanismo_valor_default": 50.0, "mecanismo_unidad": "GBP/MWh",
        "wacc_tipico_pct": 6.0, "limite_ruido_diurno_db": 45.0, "limite_ruido_nocturno_db": 43.0,
        "altitudes_relevantes": "0-1300m",
    },
    "IN": {
        "nombre": "India", "tax_rate_pct": 30.0, "country_risk_premium_pct": 3.0,
        "currency": "INR", "fx_to_usd_aprox": 85.0,
        "mecanismo": "SECI_subasta",
        "mecanismo_descripcion": "SECI tender auction",
        "mecanismo_valor_default": 35.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 10.0, "limite_ruido_diurno_db": 55.0, "limite_ruido_nocturno_db": 45.0,
        "altitudes_relevantes": "0-3000m",
    },
    "ZA": {
        "nombre": "South Africa", "tax_rate_pct": 27.0, "country_risk_premium_pct": 4.0,
        "currency": "ZAR", "fx_to_usd_aprox": 19.0,
        "mecanismo": "REIPPPP",
        "mecanismo_descripcion": "REIPPPP renewable energy program",
        "mecanismo_valor_default": 50.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 12.0, "limite_ruido_diurno_db": 50.0, "limite_ruido_nocturno_db": 40.0,
        "altitudes_relevantes": "0-3500m",
    },
    "AU": {
        "nombre": "Australia", "tax_rate_pct": 30.0, "country_risk_premium_pct": 0.0,
        "currency": "AUD", "fx_to_usd_aprox": 1.53,
        "mecanismo": "LGC_PPA",
        "mecanismo_descripcion": "Large-scale Generation Certificates + PPA",
        "mecanismo_valor_default": 50.0, "mecanismo_unidad": "AUD/MWh",
        "wacc_tipico_pct": 7.0, "limite_ruido_diurno_db": 50.0, "limite_ruido_nocturno_db": 40.0,
        "altitudes_relevantes": "0-2200m",
    },
    "OTRO": {
        "nombre": "Otro / Custom", "tax_rate_pct": 25.0, "country_risk_premium_pct": 2.0,
        "currency": "USD", "fx_to_usd_aprox": 1.0,
        "mecanismo": "generico_PPA",
        "mecanismo_descripcion": "Mecanismo regulatorio genérico (PPA / Mercado / FIT)",
        "mecanismo_valor_default": 0.0, "mecanismo_unidad": "USD/MWh",
        "wacc_tipico_pct": 8.0, "limite_ruido_diurno_db": 55.0, "limite_ruido_nocturno_db": 45.0,
        "altitudes_relevantes": "configurar manualmente",
    },
}


# ── I18N STRINGS ──
# Para bankable report + UI keys
STRINGS_I18N = {
    "es": {
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
                            "comercial certificado (WAsP, WindPRO, OpenWind). Para project finance, los resultados "
                            "deben ser validados por un consultor certificado independiente."),
        "aep_p50": "AEP P50", "aep_p90": "AEP P90 (banca)", "lcoe": "LCOE",
        "npv": "VPN", "irr": "TIR", "payback": "Período de recuperación",
        "ready_for_auditor": "Listo para auditor externo",
    },
    "en": {
        "report_title": "BANKABLE REPORT",
        "report_subtitle": "Technical-Economic Assessment of Wind Project",
        "section_1_exec": "Executive Summary",
        "section_2_proj": "Project Description",
        "section_3_wind": "Wind Resource Assessment",
        "section_4_energy": "Energy Yield (Monte Carlo P50/P90)",
        "section_5_iec": "IEC 61400-1 Compliance",
        "section_6_env": "Environmental Analysis",
        "section_7_econ": "Bankable Economic Analysis",
        "section_8_risk": "Risk Register",
        "section_9_concl": "Conclusions & Recommendations",
        "section_10_app": "Appendices",
        "metric": "Metric", "value": "Value",
        "client": "Client", "author": "Author", "date": "Generation Date",
        "disclaimer_title": "DISCLAIMER:",
        "disclaimer_body": ("This report is generated by SMA 2.0, an open-source pre-feasibility tool. "
                            "It does NOT replace formal certification by DNV/UL/TÜV nor assessments with "
                            "certified commercial software (WAsP, WindPRO, OpenWind). For project finance, "
                            "results must be validated by an independent certified consultant."),
        "aep_p50": "AEP P50", "aep_p90": "AEP P90 (banking)", "lcoe": "LCOE",
        "npv": "NPV", "irr": "IRR", "payback": "Payback period",
        "ready_for_auditor": "Ready for external auditor",
    },
    "pt": {
        "report_title": "RELATÓRIO BANCÁVEL",
        "report_subtitle": "Avaliação técnico-econômica de projeto eólico",
        "section_1_exec": "Resumo Executivo",
        "section_2_proj": "Descrição do Projeto",
        "section_3_wind": "Avaliação do Recurso Eólico",
        "section_4_energy": "Produção de Energia (Monte Carlo P50/P90)",
        "section_5_iec": "Conformidade IEC 61400-1",
        "section_6_env": "Análise Ambiental",
        "section_7_econ": "Análise Econômica Bancável",
        "section_8_risk": "Registro de Riscos",
        "section_9_concl": "Conclusões e Recomendações",
        "section_10_app": "Apêndices",
        "metric": "Métrica", "value": "Valor",
        "client": "Cliente", "author": "Autor", "date": "Data de geração",
        "disclaimer_title": "AVISO LEGAL:",
        "disclaimer_body": ("Este relatório é gerado pelo SMA 2.0, ferramenta open-source de pré-viabilidade. "
                            "NÃO substitui certificação formal de DNV/UL/TÜV nem avaliações com software comercial "
                            "certificado (WAsP, WindPRO, OpenWind). Para project finance, os resultados devem ser "
                            "validados por consultor certificado independente."),
        "aep_p50": "AEP P50", "aep_p90": "AEP P90 (bancário)", "lcoe": "LCOE",
        "npv": "VPL", "irr": "TIR", "payback": "Período de retorno",
        "ready_for_auditor": "Pronto para auditor externo",
    },
    "fr": {
        "report_title": "RAPPORT BANCABLE",
        "report_subtitle": "Évaluation technico-économique de projet éolien",
        "section_1_exec": "Résumé Exécutif",
        "section_2_proj": "Description du Projet",
        "section_3_wind": "Évaluation de la Ressource Éolienne",
        "section_4_energy": "Production d'Énergie (Monte Carlo P50/P90)",
        "section_5_iec": "Conformité CEI 61400-1",
        "section_6_env": "Analyse Environnementale",
        "section_7_econ": "Analyse Économique Bancable",
        "section_8_risk": "Registre des Risques",
        "section_9_concl": "Conclusions et Recommandations",
        "section_10_app": "Annexes",
        "metric": "Métrique", "value": "Valeur",
        "client": "Client", "author": "Auteur", "date": "Date de génération",
        "disclaimer_title": "AVERTISSEMENT:",
        "disclaimer_body": ("Ce rapport est généré par SMA 2.0, outil open-source de pré-faisabilité. "
                            "Il ne remplace PAS la certification formelle de DNV/UL/TÜV ni les évaluations "
                            "avec logiciels commerciaux certifiés (WAsP, WindPRO, OpenWind). Pour le financement "
                            "de projet, les résultats doivent être validés par un consultant certifié indépendant."),
        "aep_p50": "AEP P50", "aep_p90": "AEP P90 (bancaire)", "lcoe": "LCOE",
        "npv": "VAN", "irr": "TRI", "payback": "Retour sur investissement",
        "ready_for_auditor": "Prêt pour auditeur externe",
    },
}


def t(key: str, lang: str = "es") -> str:
    """Translate string key. Fallback a key si no encuentra."""
    if lang not in STRINGS_I18N:
        lang = "es"
    return STRINGS_I18N[lang].get(key, key)


def get_country_profile(country_code: str) -> dict:
    """Devuelve perfil país. Default OTRO si no encuentra."""
    code = str(country_code or "OTRO").upper()
    return COUNTRY_PROFILES.get(code, COUNTRY_PROFILES["OTRO"])


def get_currency_info(currency_code: str) -> dict:
    """Devuelve info moneda. Default USD si no encuentra."""
    code = str(currency_code or "USD").upper()
    return CURRENCIES.get(code, CURRENCIES["USD"])


def listar_paises() -> list:
    """Lista de tuplas (code, nombre) para selectbox."""
    return [(code, info["nombre"]) for code, info in COUNTRY_PROFILES.items()]


def listar_monedas() -> list:
    """Lista de tuplas (code, nombre completo) para selectbox."""
    return [(code, f"{info['simbolo']} {info['nombre']}") for code, info in CURRENCIES.items()]


def listar_idiomas() -> list:
    """Lista de tuplas (code, nombre nativo)."""
    return [
        ("es", "Español"),
        ("en", "English"),
        ("pt", "Português"),
        ("fr", "Français"),
    ]


def country_to_default_currency(country_code: str) -> str:
    """Helper: dado country code, devuelve moneda default."""
    return get_country_profile(country_code).get("currency", "USD")


def country_to_default_mecanismo_regulatorio(country_code: str) -> dict:
    """Devuelve mecanismo regulatorio default del país."""
    p = get_country_profile(country_code)
    return {
        "nombre": p.get("mecanismo", "generico"),
        "descripcion": p.get("mecanismo_descripcion", ""),
        "valor_default": p.get("mecanismo_valor_default", 0.0),
        "unidad": p.get("mecanismo_unidad", "USD/MWh"),
    }
