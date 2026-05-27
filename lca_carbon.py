"""LCA Carbon Footprint — ISO 14040 / IEA WCC Task 12 simplificado.

Calcula huella de carbono lifecycle del proyecto eólico:
  Manufactura turbinas + transporte + instalación + O&M + desmantelamiento
  + transmisión eléctrica → gCO2eq/kWh.

Factor típico turbina onshore: 9-12 gCO2eq/kWh
Comparación gas: ~490 gCO2/kWh, carbón: ~820 gCO2/kWh
Grid emisión Colombia 2024: ~210 gCO2/kWh (mezcla hidro + térmico)
"""

from __future__ import annotations

import pandas as pd

# Factores de emisión por componente lifetime (gCO2eq/kWh)
# Basado en IEA WCC Task 12 + Vestas LCA reports + literatura
EMISSION_FACTORS_ONSHORE_GCO2EQ_KWH = {
    "manufactura_turbina": 5.0,       # acero, hormigón, electrónica
    "transporte": 0.8,                # ship + truck a sitio
    "instalacion": 1.2,               # grúas, hormigón fundación
    "om_lifetime": 1.5,               # mantenimiento, repuestos 20 años
    "transmision_local": 0.8,         # red colectora + subestación
    "desmantelamiento": 0.5,          # demolición + reciclaje
}

# Factor emisión grid Colombia (XM 2024 aprox)
GRID_EMISSION_COLOMBIA_GCO2_KWH = 210.0
GRID_EMISSION_USA_GCO2_KWH = 380.0
GRID_EMISSION_EU_GCO2_KWH = 230.0

EMISSION_ALTERNATIVAS = {
    "Gas combinado": 490.0,
    "Carbón": 820.0,
    "Diésel": 730.0,
    "Solar fotovoltaica": 41.0,
    "Hidroeléctrica embalse": 24.0,
    "Hidroeléctrica filo agua": 5.0,
    "Nuclear": 12.0,
    "Eólica onshore (referencia)": 11.0,
    "Eólica offshore": 12.0,
    "Biomasa": 230.0,
    "Geotérmica": 38.0,
}


def calcular_huella_carbono_proyecto(
    capacidad_instalada_mw,
    aep_total_mwh_anio,
    vida_util_anios=20,
    factor_manufactura_g_kwh=None,
    factores_custom=None,
    grid_emission_factor_g_kwh=None,
):
    """Calcula huella de carbono lifecycle del proyecto eólico.

    Returns dict con:
      - huella_g_kwh: emisiones totales / energía total lifetime
      - emisiones_totales_tCO2eq: emisiones totales del proyecto
      - co2_evitado_anual_tCO2eq: vs grid baseline
      - payback_co2_anios: años para evitar CO2 emitido en construcción
      - desglose_componentes
    """
    factores = dict(EMISSION_FACTORS_ONSHORE_GCO2EQ_KWH)
    if factor_manufactura_g_kwh is not None:
        factores["manufactura_turbina"] = float(factor_manufactura_g_kwh)
    if factores_custom:
        factores.update(factores_custom)

    huella_g_kwh = sum(factores.values())

    energia_total_kwh = float(aep_total_mwh_anio) * float(vida_util_anios) * 1000.0
    emisiones_totales_g = huella_g_kwh * energia_total_kwh
    emisiones_totales_t = emisiones_totales_g / 1e6  # tCO2eq

    # Emisiones de manufactura + instalación (pre-operación) → CO2 inicial
    emisiones_iniciales_g_kwh = factores["manufactura_turbina"] + factores["transporte"] + factores["instalacion"]
    emisiones_iniciales_total_t = emisiones_iniciales_g_kwh * energia_total_kwh / 1e6

    # CO2 evitado anual vs grid baseline
    grid_factor = float(grid_emission_factor_g_kwh) if grid_emission_factor_g_kwh else GRID_EMISSION_COLOMBIA_GCO2_KWH
    co2_evitado_anual_g = (grid_factor - huella_g_kwh) * float(aep_total_mwh_anio) * 1000.0
    co2_evitado_anual_t = co2_evitado_anual_g / 1e6

    # Payback CO2: años para que el proyecto evite el mismo CO2 que emitió construyéndose
    payback_co2_anios = emisiones_iniciales_total_t / co2_evitado_anual_t if co2_evitado_anual_t > 0 else float("inf")

    return {
        "huella_g_kwh": float(huella_g_kwh),
        "huella_kg_mwh": float(huella_g_kwh),  # g/kWh = kg/MWh
        "emisiones_totales_tCO2eq": float(emisiones_totales_t),
        "emisiones_iniciales_tCO2eq": float(emisiones_iniciales_total_t),
        "co2_evitado_anual_tCO2eq": float(co2_evitado_anual_t),
        "co2_evitado_lifetime_tCO2eq": float(co2_evitado_anual_t * vida_util_anios),
        "payback_co2_anios": float(payback_co2_anios),
        "grid_factor_g_kwh": float(grid_factor),
        "desglose_componentes": factores,
    }


def comparar_vs_alternativas(huella_proyecto_g_kwh):
    """Tabla comparativa proyecto vs alternativas energéticas."""
    rows = []
    for nombre, valor in EMISSION_ALTERNATIVAS.items():
        ratio = huella_proyecto_g_kwh / valor if valor > 0 else 0
        rows.append({
            "Tecnología": nombre,
            "gCO2eq/kWh": valor,
            "Ratio (proyecto/alt)": round(ratio, 3),
            "Veces más limpio que": round(valor / huella_proyecto_g_kwh, 1) if huella_proyecto_g_kwh > 0 else 0,
        })
    df = pd.DataFrame(rows).sort_values("gCO2eq/kWh")
    return df


def calcular_co2_equivalente_arboles(co2_evitado_anual_t):
    """1 árbol secuestra ~22 kg CO2/año (estimación FAO).
    Útil para storytelling reportes."""
    n_arboles = float(co2_evitado_anual_t) * 1000.0 / 22.0
    return {
        "n_arboles_equivalentes_anuales": int(n_arboles),
        "hectareas_bosque_equivalentes": float(n_arboles / 400),  # ~400 árboles/ha
    }
