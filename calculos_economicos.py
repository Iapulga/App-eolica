import json
from datetime import datetime, UTC
import math

import requests
import streamlit as st


CAPEX_MODE_OPTIONS = {
    "manual_total": "Manual total",
    "semi_auto_mw": "Semiautomático por MW",
    "detailed": "Detallado",
}

OPEX_MODE_OPTIONS = {
    "manual_total": "Manual anual total",
    "fixed_variable": "Fijo + variable",
    "detailed": "Detallado anual",
}

MONEDA_OPTIONS = ["USD", "COP"]
FX_MODE_OPTIONS = {
    "manual": "Manual",
    "automatic": "Automática",
}

CAPEX_COMPONENT_DEFAULTS = {
    "costo_turbinas": 0.0,
    "costo_fundaciones": 0.0,
    "costo_vias": 0.0,
    "costo_red_colectora": 0.0,
    "costo_subestacion": 0.0,
    "costo_interconexion": 0.0,
    "costo_ingenieria_licencias": 0.0,
    "costo_contingencia": 0.0,
}

OPEX_COMPONENT_DEFAULTS = {
    "mantenimiento_programado": 0.0,
    "mantenimiento_correctivo": 0.0,
    "seguros": 0.0,
    "arrendamiento_terreno": 0.0,
    "administracion": 0.0,
    "vigilancia": 0.0,
    "otros": 0.0,
}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return int(default)


def load_component_values(raw_json, defaults):
    values = dict(defaults)
    if not raw_json:
        return values
    try:
        loaded = json.loads(raw_json)
    except Exception:
        return values
    if not isinstance(loaded, dict):
        return values
    for key, default in defaults.items():
        values[key] = _safe_float(loaded.get(key), default)
    return values


def dumps_component_values(values):
    normalized = {key: _safe_float(value) for key, value in values.items()}
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


@st.cache_data(show_spinner=False)
def calcular_metricas_base_economicas(
    potencia_nominal_turbina_w,
    n_turbinas,
    aep_neta_mwh_anio,
    factor_planta_neto_pct,
):
    warnings = []

    potencia_nominal_turbina_mw = max(0.0, _safe_float(potencia_nominal_turbina_w) / 1e6)
    n_turbinas_int = max(0, _safe_int(n_turbinas))
    potencia_instalada_mw = potencia_nominal_turbina_mw * n_turbinas_int
    energia_neta = max(0.0, _safe_float(aep_neta_mwh_anio))
    factor_planta = _safe_float(factor_planta_neto_pct)

    if potencia_nominal_turbina_mw <= 0:
        warnings.append("No fue posible determinar una potencia nominal por turbina válida desde la curva de potencia.")
    if n_turbinas_int <= 0:
        warnings.append("No fue posible determinar un número de turbinas válido para la evaluación económica.")
    if potencia_instalada_mw <= 0:
        warnings.append("La potencia instalada calculada es cero; revise curva de potencia y número de turbinas.")
    if energia_neta <= 0:
        warnings.append("El AEP neto calculado es cero o no está disponible; el LCOE no será representativo.")

    return {
        "potencia_nominal_turbina_mw": potencia_nominal_turbina_mw,
        "n_turbinas": n_turbinas_int,
        "potencia_instalada_mw": potencia_instalada_mw,
        "aep_neta_mwh_anio": energia_neta,
        "factor_planta_neto_pct": factor_planta,
        "warnings": warnings,
    }


@st.cache_data(show_spinner=False)
def calcular_capex(mode, potencia_instalada_mw, inputs=None, components=None):
    inputs = inputs or {}
    components = components or {}
    potencia_instalada = max(0.0, _safe_float(potencia_instalada_mw))

    if mode == "manual_total":
        capex_total = max(0.0, _safe_float(inputs.get("capex_total")))
        breakdown = [
            {"Concepto": "CAPEX manual total", "Valor": capex_total},
        ]
        return {
            "mode": mode,
            "capex_total": capex_total,
            "breakdown": breakdown,
        }

    if mode == "detailed":
        values = {key: max(0.0, _safe_float(value)) for key, value in components.items()}
        capex_total = sum(values.values())
        breakdown = [{"Concepto": key.replace("_", " ").title(), "Valor": value} for key, value in values.items()]
        breakdown.append({"Concepto": "CAPEX total", "Valor": capex_total})
        return {
            "mode": mode,
            "capex_total": capex_total,
            "breakdown": breakdown,
            "components": values,
        }

    costo_turbina_por_mw = max(0.0, _safe_float(inputs.get("costo_turbina_por_mw")))
    costo_bop_por_mw = max(0.0, _safe_float(inputs.get("costo_bop_por_mw")))
    costo_red_por_mw = max(0.0, _safe_float(inputs.get("costo_red_por_mw")))
    porcentaje_desarrollo = max(0.0, _safe_float(inputs.get("porcentaje_desarrollo")))
    porcentaje_contingencia = max(0.0, _safe_float(inputs.get("porcentaje_contingencia")))

    capex_turbinas = potencia_instalada * costo_turbina_por_mw
    capex_bop = potencia_instalada * costo_bop_por_mw
    capex_red = potencia_instalada * costo_red_por_mw
    subtotal_directo = capex_turbinas + capex_bop + capex_red
    capex_desarrollo = subtotal_directo * porcentaje_desarrollo / 100.0
    subtotal = subtotal_directo + capex_desarrollo
    capex_contingencia = subtotal * porcentaje_contingencia / 100.0
    capex_total = subtotal + capex_contingencia

    breakdown = [
        {"Concepto": "Turbinas", "Valor": capex_turbinas},
        {"Concepto": "BOP", "Valor": capex_bop},
        {"Concepto": "Red", "Valor": capex_red},
        {"Concepto": "Desarrollo", "Valor": capex_desarrollo},
        {"Concepto": "Contingencia", "Valor": capex_contingencia},
        {"Concepto": "CAPEX total", "Valor": capex_total},
    ]

    return {
        "mode": "semi_auto_mw",
        "capex_total": capex_total,
        "capex_turbinas": capex_turbinas,
        "capex_bop": capex_bop,
        "capex_red": capex_red,
        "capex_desarrollo": capex_desarrollo,
        "capex_contingencia": capex_contingencia,
        "breakdown": breakdown,
    }


@st.cache_data(show_spinner=False)
def calcular_opex(mode, potencia_instalada_mw, energia_mwh_anio, inputs=None, components=None):
    inputs = inputs or {}
    components = components or {}
    potencia_instalada = max(0.0, _safe_float(potencia_instalada_mw))
    energia_anual = max(0.0, _safe_float(energia_mwh_anio))

    if mode == "manual_total":
        opex_total = max(0.0, _safe_float(inputs.get("opex_total_anual")))
        return {
            "mode": mode,
            "opex_total_anual": opex_total,
            "opex_fijo_anual": opex_total,
            "opex_variable_por_mwh": 0.0,
            "breakdown": [{"Concepto": "OPEX anual total", "Valor": opex_total}],
        }

    if mode == "detailed":
        values = {key: max(0.0, _safe_float(value)) for key, value in components.items()}
        opex_total = sum(values.values())
        breakdown = [{"Concepto": key.replace("_", " ").title(), "Valor": value} for key, value in values.items()]
        breakdown.append({"Concepto": "OPEX anual total", "Valor": opex_total})
        return {
            "mode": mode,
            "opex_total_anual": opex_total,
            "opex_fijo_anual": opex_total,
            "opex_variable_por_mwh": 0.0,
            "breakdown": breakdown,
            "components": values,
        }

    opex_fijo_por_mw_anio = max(0.0, _safe_float(inputs.get("opex_fijo_por_mw_anio")))
    opex_variable_por_mwh = max(0.0, _safe_float(inputs.get("opex_variable_por_mwh")))
    seguros_anuales = max(0.0, _safe_float(inputs.get("seguros_anuales")))
    terreno_anual = max(0.0, _safe_float(inputs.get("terreno_anual")))
    administracion_anual = max(0.0, _safe_float(inputs.get("administracion_anual")))

    opex_fijo = potencia_instalada * opex_fijo_por_mw_anio
    opex_variable = energia_anual * opex_variable_por_mwh
    opex_total = opex_fijo + opex_variable + seguros_anuales + terreno_anual + administracion_anual

    breakdown = [
        {"Concepto": "OPEX fijo por MW", "Valor": opex_fijo},
        {"Concepto": "OPEX variable por energía", "Valor": opex_variable},
        {"Concepto": "Seguros", "Valor": seguros_anuales},
        {"Concepto": "Terreno", "Valor": terreno_anual},
        {"Concepto": "Administración", "Valor": administracion_anual},
        {"Concepto": "OPEX anual total", "Valor": opex_total},
    ]

    return {
        "mode": "fixed_variable",
        "opex_total_anual": opex_total,
        "opex_fijo_anual": opex_fijo + seguros_anuales + terreno_anual + administracion_anual,
        "opex_variable_por_mwh": opex_variable_por_mwh,
        "opex_variable_anual": opex_variable,
        "breakdown": breakdown,
    }


@st.cache_data(show_spinner=False)
def calcular_lcoe_descontado(
    capex_total,
    opex_fijo_anual,
    opex_variable_por_mwh,
    energia_base_mwh_anio,
    vida_util_anios,
    tasa_descuento_pct,
    degradacion_energia_pct=0.0,
    valor_residual=0.0,
):
    capex = max(0.0, _safe_float(capex_total))
    opex_fijo = max(0.0, _safe_float(opex_fijo_anual))
    opex_variable = max(0.0, _safe_float(opex_variable_por_mwh))
    energia_base = max(0.0, _safe_float(energia_base_mwh_anio))
    vida_util = max(1, _safe_int(vida_util_anios, 20))
    tasa = max(0.0, _safe_float(tasa_descuento_pct)) / 100.0
    degradacion = max(0.0, _safe_float(degradacion_energia_pct)) / 100.0
    residual = max(0.0, _safe_float(valor_residual))

    valor_presente_costos = capex
    valor_presente_energia = 0.0

    for year in range(1, vida_util + 1):
        energia_t = energia_base * ((1.0 - degradacion) ** (year - 1))
        factor_descuento = ((1.0 + tasa) ** year) if tasa > 0 else 1.0
        opex_t = opex_fijo + opex_variable * energia_t
        valor_presente_costos += opex_t / factor_descuento
        valor_presente_energia += energia_t / factor_descuento

    descuento_residual = ((1.0 + tasa) ** vida_util) if tasa > 0 else 1.0
    valor_presente_costos -= residual / descuento_residual

    lcoe_mwh = valor_presente_costos / valor_presente_energia if valor_presente_energia > 0 else float("nan")
    lcoe_kwh = lcoe_mwh / 1000.0 if valor_presente_energia > 0 else float("nan")

    return {
        "valor_presente_costos": valor_presente_costos,
        "valor_presente_energia": valor_presente_energia,
        "lcoe_mwh": lcoe_mwh,
        "lcoe_kwh": lcoe_kwh,
    }


def obtener_factor_conversion(moneda_base, moneda_display, fx_cop_per_usd):
    base = str(moneda_base or "USD").upper()
    display = str(moneda_display or base).upper()
    fx = _safe_float(fx_cop_per_usd, 0.0)

    if base == display:
        return 1.0
    if fx <= 0:
        return None
    if base == "USD" and display == "COP":
        return fx
    if base == "COP" and display == "USD":
        return 1.0 / fx
    return None


def convertir_valor_moneda(valor, moneda_base, moneda_display, fx_cop_per_usd):
    factor = obtener_factor_conversion(moneda_base, moneda_display, fx_cop_per_usd)
    if factor is None:
        return None
    return _safe_float(valor) * factor


@st.cache_data(show_spinner=False)
def convertir_resumen_economico(summary, moneda_base, moneda_display, fx_cop_per_usd):
    factor = obtener_factor_conversion(moneda_base, moneda_display, fx_cop_per_usd)
    if factor is None:
        return {
            "factor_conversion": None,
            "capex_total_display": None,
            "opex_total_anual_display": None,
            "vp_costos_display": None,
            "lcoe_display_mwh": None,
            "lcoe_display_kwh": None,
        }

    return {
        "factor_conversion": factor,
        "capex_total_display": _safe_float(summary.get("capex_total")) * factor,
        "opex_total_anual_display": _safe_float(summary.get("opex_total_anual")) * factor,
        "vp_costos_display": _safe_float(summary.get("vp_costos")) * factor,
        "lcoe_display_mwh": _safe_float(summary.get("lcoe_mwh")) * factor,
        "lcoe_display_kwh": _safe_float(summary.get("lcoe_kwh")) * factor,
    }


def obtener_tasa_cop_usd_online():
    timestamp = datetime.now(UTC).isoformat()
    urls = [
        "https://open.er-api.com/v6/latest/USD",
        "https://api.exchangerate.host/latest?base=USD&symbols=COP",
    ]
    last_error = ""

    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            payload = response.json()
            rates = payload.get("rates") or {}
            fx = _safe_float(rates.get("COP"), 0.0)
            if fx > 0:
                return {
                    "success": True,
                    "fx_cop_per_usd": fx,
                    "timestamp": payload.get("time_last_update_utc") or payload.get("date") or timestamp,
                    "source": url,
                    "message": "Tasa COP/USD actualizada automáticamente.",
                }
            last_error = "La respuesta del servicio no incluyó una tasa COP válida."
        except Exception as exc:
            last_error = str(exc)

    return {
        "success": True,
        "fx_cop_per_usd": 4000.0,
        "timestamp": timestamp,
        "source": "Fallback Local",
        "message": f"No fue posible obtener una tasa online ({last_error}). Se usará el valor de respaldo de 4000.0 COP/USD.",
    }


def format_currency_amount(value, currency):
    if value is None:
        return "N/D"
    number = _safe_float(value)
    if not math.isfinite(number):
        return "N/D"
    decimals = 0 if str(currency).upper() == "COP" else 2
    return f"{str(currency).upper()} {number:,.{decimals}f}"


def format_lcoe_value(value, currency, unit):
    if value is None:
        return "N/D"
    number = _safe_float(value)
    if not math.isfinite(number):
        return "N/D"
    currency = str(currency).upper()
    unit = str(unit)
    if unit == "kWh":
        decimals = 2 if currency == "COP" else 4
    else:
        decimals = 0 if currency == "COP" else 2
    return f"{currency} {number:,.{decimals}f}/{unit}"
