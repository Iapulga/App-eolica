"""End-of-life analysis: decommission vs repowering vs life extension.

Compara 3 escenarios económicos al final de vida útil (típ. año 20):
  - Decommission: desmantelamiento total + valor scrap
  - Repowering: turbinas nuevas mismo sitio (reusa terreno + conexión)
  - Life extension: O&M mayor + upgrades selectivos + monitoreo intensivo
"""

from __future__ import annotations

import pandas as pd


def _safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def escenario_decommission(
    capacidad_instalada_mw,
    costo_decom_usd_por_mw=40_000,
    valor_scrap_usd_por_mw=15_000,
):
    """Decommission típico: 30-50k USD/MW costo + ~10-20k USD/MW scrap recovery."""
    capex_decom = float(capacidad_instalada_mw) * float(costo_decom_usd_por_mw)
    scrap = float(capacidad_instalada_mw) * float(valor_scrap_usd_por_mw)
    return {
        "escenario": "decommission",
        "capex_decom_usd": capex_decom,
        "valor_scrap_usd": scrap,
        "flujo_neto_usd": -(capex_decom - scrap),  # negativo: costo neto
        "vida_adicional_anios": 0,
        "aep_anual_post_mwh": 0.0,
        "ingreso_anual_post_usd": 0.0,
    }


def escenario_repowering(
    capacidad_instalada_mw,
    aep_actual_mwh_anio,
    capex_decom_actual_usd_por_mw=40_000,
    capex_new_turbines_usd_por_mw=900_000,  # reuso terreno+conexión ~60-70% greenfield
    aep_uplift_pct=30,  # turbinas modernas más eficientes
    vida_extendida_anios=25,
    opex_anual_nuevo_usd_por_mw=40_000,
    precio_ppa_usd_mwh=60.0,
):
    """Repowering: decommission actual + nuevas turbinas. AEP +20-50% típicamente."""
    capacidad = float(capacidad_instalada_mw)
    capex_decom = capacidad * float(capex_decom_actual_usd_por_mw)
    capex_new = capacidad * float(capex_new_turbines_usd_por_mw)
    capex_total = capex_decom + capex_new

    aep_nuevo = float(aep_actual_mwh_anio) * (1.0 + float(aep_uplift_pct) / 100.0)
    opex_anual = capacidad * float(opex_anual_nuevo_usd_por_mw)
    ingreso_anual = aep_nuevo * float(precio_ppa_usd_mwh)
    fcf_anual = ingreso_anual - opex_anual

    return {
        "escenario": "repowering",
        "capex_total_usd": capex_total,
        "capex_decom_usd": capex_decom,
        "capex_turbines_usd": capex_new,
        "vida_adicional_anios": int(vida_extendida_anios),
        "aep_anual_post_mwh": aep_nuevo,
        "opex_anual_post_usd": opex_anual,
        "ingreso_anual_post_usd": ingreso_anual,
        "fcf_anual_post_usd": fcf_anual,
    }


def escenario_life_extension(
    capacidad_instalada_mw,
    aep_actual_mwh_anio,
    capex_upgrades_usd_por_mw=200_000,  # 20-40% capex original
    vida_extension_anios=10,
    derate_aep_pct=5.0,
    opex_mayor_usd_por_mw=60_000,  # ~50% más que OPEX normal
    precio_ppa_usd_mwh=60.0,
):
    """Life extension: mantener turbinas con upgrades + monitoring intensivo + OPEX mayor."""
    capacidad = float(capacidad_instalada_mw)
    capex_total = capacidad * float(capex_upgrades_usd_por_mw)
    aep_extendido = float(aep_actual_mwh_anio) * (1.0 - float(derate_aep_pct) / 100.0)
    opex_anual = capacidad * float(opex_mayor_usd_por_mw)
    ingreso_anual = aep_extendido * float(precio_ppa_usd_mwh)
    fcf_anual = ingreso_anual - opex_anual

    return {
        "escenario": "life_extension",
        "capex_total_usd": capex_total,
        "vida_adicional_anios": int(vida_extension_anios),
        "aep_anual_post_mwh": aep_extendido,
        "opex_anual_post_usd": opex_anual,
        "ingreso_anual_post_usd": ingreso_anual,
        "fcf_anual_post_usd": fcf_anual,
    }


def calcular_npv_escenario(escenario_dict, tasa_descuento_pct=8.0):
    """NPV del escenario sobre su vida_adicional_anios."""
    capex = float(escenario_dict.get("capex_total_usd", escenario_dict.get("capex_decom_usd", 0)))
    fcf = float(escenario_dict.get("fcf_anual_post_usd", 0))
    vida = int(escenario_dict.get("vida_adicional_anios", 0))
    tasa = float(tasa_descuento_pct) / 100.0

    if vida == 0:
        # decommission puro
        return float(escenario_dict.get("flujo_neto_usd", -capex))

    # year 0: -capex; years 1..vida: +fcf
    npv = -capex
    for t in range(1, vida + 1):
        npv += fcf / ((1.0 + tasa) ** t)
    return float(npv)


def comparar_escenarios_fin_vida(
    capacidad_instalada_mw,
    aep_actual_mwh_anio,
    tasa_descuento_pct=8.0,
    precio_ppa_usd_mwh=60.0,
):
    """Compara los 3 escenarios. Returns DataFrame ordenada por NPV desc."""
    e_decom = escenario_decommission(capacidad_instalada_mw)
    e_repow = escenario_repowering(capacidad_instalada_mw, aep_actual_mwh_anio, precio_ppa_usd_mwh=precio_ppa_usd_mwh)
    e_life = escenario_life_extension(capacidad_instalada_mw, aep_actual_mwh_anio, precio_ppa_usd_mwh=precio_ppa_usd_mwh)

    rows = []
    for esc in [e_decom, e_repow, e_life]:
        npv = calcular_npv_escenario(esc, tasa_descuento_pct)
        rows.append({
            "Escenario": esc["escenario"],
            "CAPEX (USD)": esc.get("capex_total_usd", esc.get("capex_decom_usd", 0)),
            "Vida adicional (años)": esc.get("vida_adicional_anios", 0),
            "AEP post (MWh/año)": esc.get("aep_anual_post_mwh", 0),
            "FCF anual (USD)": esc.get("fcf_anual_post_usd", esc.get("flujo_neto_usd", 0)),
            "NPV (USD)": npv,
        })
    df = pd.DataFrame(rows).sort_values("NPV (USD)", ascending=False).reset_index(drop=True)
    recomendado = df.iloc[0]["Escenario"]
    return df, recomendado
