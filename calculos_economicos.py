import json
import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd
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


def calcular_flujos_caja(
    capex_total,
    opex_fijo_anual,
    opex_variable_por_mwh,
    energia_base_mwh_anio,
    vida_util_anios,
    degradacion_energia_pct=0.0,
    valor_residual=0.0,
    precio_energia_mwh=60.0,
):
    capex = max(0.0, _safe_float(capex_total))
    opex_fijo = max(0.0, _safe_float(opex_fijo_anual))
    opex_var = max(0.0, _safe_float(opex_variable_por_mwh))
    energia_base = max(0.0, _safe_float(energia_base_mwh_anio))
    vida = max(1, _safe_int(vida_util_anios, 20))
    degr = max(0.0, _safe_float(degradacion_energia_pct)) / 100.0
    residual = max(0.0, _safe_float(valor_residual))
    precio = _safe_float(precio_energia_mwh)

    flujos = np.zeros(vida + 1, dtype=float)
    flujos[0] = -capex
    for t in range(1, vida + 1):
        energia_t = energia_base * ((1.0 - degr) ** (t - 1))
        revenue_t = energia_t * precio
        opex_t = opex_fijo + opex_var * energia_t
        flujos[t] = revenue_t - opex_t
    flujos[vida] += residual
    return flujos


def calcular_npv(flujos, tasa_pct):
    flujos = np.asarray(flujos, dtype=float)
    r = max(0.0, _safe_float(tasa_pct)) / 100.0
    if flujos.size == 0:
        return float("nan")
    t = np.arange(flujos.size, dtype=float)
    return float(np.sum(flujos / ((1.0 + r) ** t)))


def calcular_irr(flujos, tol=1e-6, max_iter=200):
    flujos = np.asarray(flujos, dtype=float)
    if flujos.size < 2:
        return float("nan")
    if not (np.any(flujos > 0) and np.any(flujos < 0)):
        return float("nan")

    def npv_at(r):
        if r <= -0.9999:
            return float("inf")
        t = np.arange(flujos.size, dtype=float)
        return float(np.sum(flujos / ((1.0 + r) ** t)))

    r0, r1 = 0.05, 0.15
    f0 = npv_at(r0)
    f1 = npv_at(r1)
    for _ in range(max_iter):
        if abs(f1 - f0) < 1e-12:
            break
        r2 = r1 - f1 * (r1 - r0) / (f1 - f0)
        if not math.isfinite(r2):
            return float("nan")
        if r2 <= -0.9999:
            r2 = -0.99
        f2 = npv_at(r2)
        if abs(f2) < tol:
            return float(r2 * 100.0)
        r0, f0 = r1, f1
        r1, f1 = r2, f2
    if abs(f1) < 0.01 * abs(flujos[0] if flujos[0] != 0 else 1.0):
        return float(r1 * 100.0)
    return float("nan")


def calcular_payback(flujos):
    flujos = np.asarray(flujos, dtype=float)
    if flujos.size < 2:
        return float("nan")
    cum = np.cumsum(flujos)
    for i in range(1, cum.size):
        if cum[i] >= 0 and cum[i - 1] < 0:
            cf_i = flujos[i]
            if cf_i == 0:
                return float(i)
            frac = -cum[i - 1] / cf_i
            return float((i - 1) + frac)
    return float("nan")


def calcular_payback_descontado(flujos, tasa_pct):
    flujos = np.asarray(flujos, dtype=float)
    if flujos.size < 2:
        return float("nan")
    r = max(0.0, _safe_float(tasa_pct)) / 100.0
    t = np.arange(flujos.size, dtype=float)
    flujos_desc = flujos / ((1.0 + r) ** t)
    cum = np.cumsum(flujos_desc)
    for i in range(1, cum.size):
        if cum[i] >= 0 and cum[i - 1] < 0:
            cf_i = flujos_desc[i]
            if cf_i == 0:
                return float(i)
            frac = -cum[i - 1] / cf_i
            return float((i - 1) + frac)
    return float("nan")


def calcular_metricas_financieras(
    capex_total,
    opex_fijo_anual,
    opex_variable_por_mwh,
    energia_base_mwh_anio,
    vida_util_anios,
    tasa_descuento_pct,
    degradacion_energia_pct=0.0,
    valor_residual=0.0,
    precio_energia_mwh=60.0,
):
    flujos = calcular_flujos_caja(
        capex_total=capex_total,
        opex_fijo_anual=opex_fijo_anual,
        opex_variable_por_mwh=opex_variable_por_mwh,
        energia_base_mwh_anio=energia_base_mwh_anio,
        vida_util_anios=vida_util_anios,
        degradacion_energia_pct=degradacion_energia_pct,
        valor_residual=valor_residual,
        precio_energia_mwh=precio_energia_mwh,
    )
    return {
        "flujos": flujos,
        "npv": calcular_npv(flujos, tasa_descuento_pct),
        "irr_pct": calcular_irr(flujos),
        "payback_simple_anios": calcular_payback(flujos),
        "payback_descontado_anios": calcular_payback_descontado(flujos, tasa_descuento_pct),
    }


def calcular_wacc(
    cost_equity_pct=12.0,
    cost_debt_pct=7.0,
    debt_ratio_pct=60.0,
    tax_rate_pct=33.0,
    country_risk_premium_pct=2.0,
):
    """WACC = (E/V)·Ke + (D/V)·Kd·(1-tax). Colombia tax_rate típico 33%, country risk ~2-3%."""
    e_ratio = max(0.0, 1.0 - _safe_float(debt_ratio_pct) / 100.0)
    d_ratio = _safe_float(debt_ratio_pct) / 100.0
    ke = (_safe_float(cost_equity_pct) + _safe_float(country_risk_premium_pct)) / 100.0
    kd = _safe_float(cost_debt_pct) / 100.0
    tax = _safe_float(tax_rate_pct) / 100.0
    wacc = e_ratio * ke + d_ratio * kd * (1.0 - tax)
    return {
        "wacc_pct": float(wacc * 100.0),
        "componente_equity": float(e_ratio * ke * 100.0),
        "componente_debt_neto_tax": float(d_ratio * kd * (1.0 - tax) * 100.0),
        "ke_efectivo_pct": float(ke * 100.0),
        "kd_efectivo_pct": float(kd * (1.0 - tax) * 100.0),
        "tax_shield_pct": float(d_ratio * kd * tax * 100.0),
    }


def calcular_depreciacion(capex, vida_util_anios=20, metodo="lineal"):
    """Devuelve array de depreciación por año.
    Métodos: lineal | MACRS_5yr | acelerada_colombia (10 años).
    """
    capex_v = max(0.0, _safe_float(capex))
    vida = max(1, _safe_int(vida_util_anios, 20))

    if metodo == "MACRS_5yr":
        # MACRS 5-year, US tax wind classification
        rates = [0.20, 0.32, 0.192, 0.1152, 0.1152, 0.0576]
        dep = np.zeros(vida)
        for i, r in enumerate(rates[:min(len(rates), vida)]):
            dep[i] = capex_v * r
    elif metodo == "acelerada_colombia":
        # 10 años acelerada Colombia (estimado)
        n_acelerado = min(10, vida)
        dep = np.zeros(vida)
        dep[:n_acelerado] = capex_v / n_acelerado
    else:  # lineal
        dep = np.full(vida, capex_v / vida)

    return dep


def calcular_flujos_caja_bankable(
    capex, opex_fijo, opex_variable_por_mwh, energia_base,
    vida_util, degradacion_pct, valor_residual, precio_energia_mwh,
    ppa_escalation_pct=0.0,
    depreciacion_metodo="lineal", tax_rate_pct=33.0,
    debt_service_anual=0.0,
):
    """Flujos de caja bankable incluyendo depreciación + tax + servicio deuda.

    Returns DataFrame con columnas:
    year, revenue, opex, depreciacion, ebt, taxes, net_income, cfads, debt_service, dscr, free_cash_flow.
    """
    vida = max(1, _safe_int(vida_util, 20))
    capex_v = max(0.0, _safe_float(capex))
    opex_fijo_v = max(0.0, _safe_float(opex_fijo))
    opex_var_v = max(0.0, _safe_float(opex_variable_por_mwh))
    energia0 = max(0.0, _safe_float(energia_base))
    degr = max(0.0, _safe_float(degradacion_pct)) / 100.0
    precio0 = max(0.0, _safe_float(precio_energia_mwh))
    esc = _safe_float(ppa_escalation_pct) / 100.0
    tax = _safe_float(tax_rate_pct) / 100.0
    residual = max(0.0, _safe_float(valor_residual))
    debt_serv = max(0.0, _safe_float(debt_service_anual))

    dep_arr = calcular_depreciacion(capex_v, vida, metodo=depreciacion_metodo)

    rows = []
    rows.append({
        "year": 0, "revenue": 0.0, "opex": 0.0, "depreciacion": 0.0,
        "ebt": -capex_v, "taxes": 0.0, "net_income": -capex_v,
        "cfads": -capex_v, "debt_service": 0.0, "dscr": float("nan"),
        "free_cash_flow": -capex_v,
    })

    for t in range(1, vida + 1):
        energia_t = energia0 * ((1.0 - degr) ** (t - 1))
        precio_t = precio0 * ((1.0 + esc) ** (t - 1))
        revenue_t = energia_t * precio_t
        opex_t = opex_fijo_v + opex_var_v * energia_t
        dep_t = dep_arr[t - 1] if (t - 1) < len(dep_arr) else 0.0

        ebt = revenue_t - opex_t - dep_t
        taxes_t = max(0.0, ebt * tax)
        net_income = ebt - taxes_t

        # CFADS = Cash Flow Available for Debt Service = NI + depreciación
        cfads = net_income + dep_t
        dscr = cfads / debt_serv if debt_serv > 0 else float("inf")
        fcf = cfads - debt_serv
        if t == vida:
            fcf += residual

        rows.append({
            "year": t, "revenue": revenue_t, "opex": opex_t, "depreciacion": dep_t,
            "ebt": ebt, "taxes": taxes_t, "net_income": net_income,
            "cfads": cfads, "debt_service": debt_serv, "dscr": dscr,
            "free_cash_flow": fcf,
        })

    return pd.DataFrame(rows)


def calcular_dscr_metricas(df_flujos):
    """Métricas DSCR clave para banca: min, mediano, año problemático."""
    df_only_years = df_flujos[df_flujos["year"] > 0]
    if len(df_only_years) == 0:
        return {"dscr_min": float("nan"), "dscr_mediano": float("nan"), "dscr_promedio": float("nan"), "anio_min_dscr": 0}
    dscrs = df_only_years["dscr"].replace([np.inf, -np.inf], np.nan).dropna()
    if len(dscrs) == 0:
        return {"dscr_min": float("inf"), "dscr_mediano": float("inf"), "dscr_promedio": float("inf"), "anio_min_dscr": 0}
    return {
        "dscr_min": float(dscrs.min()),
        "dscr_mediano": float(dscrs.median()),
        "dscr_promedio": float(dscrs.mean()),
        "anio_min_dscr": int(df_only_years.loc[df_only_years["dscr"].idxmin(), "year"]),
    }


def calcular_ingreso_mecanismo_regulatorio(
    aep_neta_mwh_anio,
    factor_aplicacion_pct=80.0,
    valor_mecanismo_per_mwh=15.0,
    nombre_mecanismo="generico",
    moneda="USD",
):
    """Ingreso por mecanismo regulatorio GENÉRICO (no solo Colombia).

    Ejemplos:
      - Colombia: CREG cargo confiabilidad (factor_aplicacion = energía firme %)
      - USA: PTC tax credit (factor_aplicacion = 100%, valor = $26/MWh)
      - UK: CfD strike price spread (factor = 100%, valor = spread vs market)
      - España: subasta MIBEL
      - Brasil: LER/LEN leilão
      - México: PPA CFE
      - India: SECI tender
      - Otro: PPA bilateral / mercado libre
    """
    aep = max(0.0, _safe_float(aep_neta_mwh_anio))
    factor_pct = max(0.0, min(100.0, _safe_float(factor_aplicacion_pct))) / 100.0
    valor = max(0.0, _safe_float(valor_mecanismo_per_mwh))
    energia_aplicable = aep * factor_pct
    ingreso_anual = energia_aplicable * valor
    return {
        "energia_aplicable_mwh_anio": float(energia_aplicable),
        "valor_unitario_per_mwh": float(valor),
        "ingreso_regulatorio_anual": float(ingreso_anual),
        "mecanismo": str(nombre_mecanismo),
        "moneda": str(moneda),
    }


# Alias backward-compat para no romper código existente
def calcular_creg_cargo_confiabilidad(aep_neta_mwh_anio, energia_firme_pct=80.0, cargo_usd_mwh=15.0):
    """DEPRECATED: usar calcular_ingreso_mecanismo_regulatorio (genérico, multi-país).

    Mantenido como alias para no romper código previo.
    """
    res = calcular_ingreso_mecanismo_regulatorio(
        aep_neta_mwh_anio, energia_firme_pct, cargo_usd_mwh,
        nombre_mecanismo="CREG_subasta_confiabilidad", moneda="USD",
    )
    return {
        "energia_firme_mwh_anio": res["energia_aplicable_mwh_anio"],
        "cargo_usd_mwh": res["valor_unitario_per_mwh"],
        "ingreso_creg_anual_usd": res["ingreso_regulatorio_anual"],
    }


def calcular_fx_risk_montecarlo(
    flujos_usd, fx_base_cop_per_usd, sigma_fx_pct=10.0, n_samples=1000, seed=42,
):
    """Monte Carlo riesgo FX para conversión USD → COP.
    sigma_fx_pct = volatilidad anual % del FX.
    """
    rng = np.random.default_rng(int(seed))
    flujos = np.asarray(flujos_usd, dtype=float)
    n_years = flujos.size
    fx_paths = np.zeros((n_samples, n_years))
    fx0 = max(1.0, _safe_float(fx_base_cop_per_usd))
    sig = max(0.0, _safe_float(sigma_fx_pct)) / 100.0

    for s in range(n_samples):
        # geometric brownian motion approx
        log_returns = rng.normal(0, sig, n_years)
        fx_paths[s] = fx0 * np.exp(np.cumsum(log_returns))

    flujos_cop_samples = flujos[None, :] * fx_paths
    npv_samples = np.sum(flujos_cop_samples, axis=1)  # raw sum, sin descontar
    return {
        "npv_cop_p50": float(np.percentile(npv_samples, 50)),
        "npv_cop_p10": float(np.percentile(npv_samples, 10)),
        "npv_cop_p90": float(np.percentile(npv_samples, 90)),
        "fx_mean_final": float(fx_paths[:, -1].mean()),
        "fx_p10_final": float(np.percentile(fx_paths[:, -1], 10)),
        "fx_p90_final": float(np.percentile(fx_paths[:, -1], 90)),
        "n_samples": int(n_samples),
    }


def calcular_metricas_bankables(
    capex_total, opex_fijo_anual, opex_variable_por_mwh, energia_base_mwh_anio,
    vida_util_anios, tasa_descuento_pct,
    degradacion_energia_pct=0.0, valor_residual=0.0,
    precio_energia_mwh=60.0, ppa_escalation_pct=2.0,
    cost_equity_pct=12.0, cost_debt_pct=7.0, debt_ratio_pct=60.0, tax_rate_pct=33.0,
    country_risk_pct=2.0, depreciacion_metodo="lineal",
    debt_term_anios=15, energia_firme_pct=80.0, cargo_creg_usd_mwh=15.0,
):
    """Wrapper bankable: LCOE + WACC + DSCR + NPV + IRR + CREG."""
    wacc_res = calcular_wacc(cost_equity_pct, cost_debt_pct, debt_ratio_pct, tax_rate_pct, country_risk_pct)

    # Servicio de deuda nominal (anualidad PMT)
    debt_principal = _safe_float(capex_total) * (_safe_float(debt_ratio_pct) / 100.0)
    kd = max(0.0001, _safe_float(cost_debt_pct) / 100.0)
    n_debt = max(1, _safe_int(debt_term_anios, 15))
    annuity_factor = (kd * (1 + kd) ** n_debt) / ((1 + kd) ** n_debt - 1)
    debt_service_anual = debt_principal * annuity_factor

    df_flujos = calcular_flujos_caja_bankable(
        capex=capex_total, opex_fijo=opex_fijo_anual,
        opex_variable_por_mwh=opex_variable_por_mwh, energia_base=energia_base_mwh_anio,
        vida_util=vida_util_anios, degradacion_pct=degradacion_energia_pct,
        valor_residual=valor_residual, precio_energia_mwh=precio_energia_mwh,
        ppa_escalation_pct=ppa_escalation_pct, depreciacion_metodo=depreciacion_metodo,
        tax_rate_pct=tax_rate_pct,
        debt_service_anual=debt_service_anual,
    )

    fcf = df_flujos["free_cash_flow"].to_numpy()
    npv_val = calcular_npv(fcf, wacc_res["wacc_pct"])
    irr_val = calcular_irr(fcf)
    payback_s = calcular_payback(fcf)
    payback_d = calcular_payback_descontado(fcf, wacc_res["wacc_pct"])

    dscr_m = calcular_dscr_metricas(df_flujos)
    # Backward-compat: cargo_creg_usd_mwh sigue funcionando, pero ahora es genérico
    reg_res = calcular_ingreso_mecanismo_regulatorio(
        aep_neta_mwh_anio=energia_base_mwh_anio,
        factor_aplicacion_pct=energia_firme_pct,
        valor_mecanismo_per_mwh=cargo_creg_usd_mwh,
        nombre_mecanismo="regulatorio",
        moneda="USD",
    )

    return {
        "wacc": wacc_res,
        "df_flujos": df_flujos,
        "debt_service_anual": float(debt_service_anual),
        "debt_principal": float(debt_principal),
        "npv": float(npv_val),
        "irr_pct": float(irr_val),
        "payback_simple": float(payback_s),
        "payback_descontado": float(payback_d),
        "dscr": dscr_m,
        "regulatorio": reg_res,
        "creg": reg_res,  # backward-compat alias
    }


def calcular_sensibilidad_lcoe(base_kwargs, variables_pct=15.0):
    import pandas as pd

    delta = max(0.1, _safe_float(variables_pct, 15.0)) / 100.0
    base_res = calcular_lcoe_descontado(**base_kwargs)
    lcoe_base = float(base_res.get("lcoe_mwh", float("nan")))

    variables = [
        ("CAPEX", "capex_total", "pct"),
        ("OPEX fijo", "opex_fijo_anual", "pct"),
        ("Energía AEP", "energia_base_mwh_anio", "pct"),
        ("Tasa descuento", "tasa_descuento_pct", "abs"),
        ("Vida útil", "vida_util_anios", "anios"),
    ]

    filas = []
    for nombre, key, modo in variables:
        base_val = _safe_float(base_kwargs.get(key))
        if modo == "pct":
            v_minus = base_val * (1.0 - delta)
            v_plus = base_val * (1.0 + delta)
        elif modo == "abs":
            v_minus = max(0.0, base_val - delta * 100.0)
            v_plus = base_val + delta * 100.0
        else:
            v_minus = max(1, int(round(base_val - 3)))
            v_plus = int(round(base_val + 3))

        kw_minus = dict(base_kwargs)
        kw_minus[key] = v_minus
        kw_plus = dict(base_kwargs)
        kw_plus[key] = v_plus

        try:
            lcoe_minus = float(calcular_lcoe_descontado(**kw_minus).get("lcoe_mwh", float("nan")))
        except Exception:
            lcoe_minus = float("nan")
        try:
            lcoe_plus = float(calcular_lcoe_descontado(**kw_plus).get("lcoe_mwh", float("nan")))
        except Exception:
            lcoe_plus = float("nan")

        impacto = 0.0
        if math.isfinite(lcoe_minus) and math.isfinite(lcoe_plus):
            impacto = abs(lcoe_plus - lcoe_minus)

        filas.append({
            "Variable": nombre,
            "LCOE_minus": lcoe_minus,
            "LCOE_plus": lcoe_plus,
            "LCOE_base": lcoe_base,
            "Impacto_abs": impacto,
            "Valor_minus": v_minus,
            "Valor_plus": v_plus,
        })

    df = pd.DataFrame(filas).sort_values("Impacto_abs", ascending=True).reset_index(drop=True)
    return df, lcoe_base
