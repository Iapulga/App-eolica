"""Bird/bat collision risk — Band 2007 model (SNH UK estándar).

Calcula colisiones esperadas año/turbina/parque basado en:
  - Tasa de paso de aves observadas
  - Geometría del rotor + buje
  - Probabilidad geométrica de paso por área barrida
  - Probabilidad de evasión (species-dependent)

Referencia: Band, W. (2007). Using a collision risk model to assess bird
collision risks for offshore windfarms. SNH Report.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Defaults aves comunes Guajira (literatura/observaciones generales)
AVES_DEFAULT_COLOMBIA = [
    # Especies observadas en La Guajira (literatura general + IUCN)
    {"especie": "Buteogallus aequinoctialis (Cangrejero)", "longitud_m": 0.50, "envergadura_m": 1.20,
     "velocidad_vuelo_ms": 13, "p_evasion": 0.95, "rapaz": True},
    {"especie": "Coragyps atratus (Zopilote)", "longitud_m": 0.65, "envergadura_m": 1.55,
     "velocidad_vuelo_ms": 11, "p_evasion": 0.94, "rapaz": False},
    {"especie": "Caracara plancus (Caracara)", "longitud_m": 0.59, "envergadura_m": 1.25,
     "velocidad_vuelo_ms": 12, "p_evasion": 0.93, "rapaz": True},
    {"especie": "Pelecanus occidentalis (Pelícano)", "longitud_m": 1.30, "envergadura_m": 2.30,
     "velocidad_vuelo_ms": 14, "p_evasion": 0.95, "rapaz": False},
    {"especie": "Pandion haliaetus (Águila pescadora)", "longitud_m": 0.58, "envergadura_m": 1.70,
     "velocidad_vuelo_ms": 14, "p_evasion": 0.96, "rapaz": True},
]


def probabilidad_paso_geometrico_band(
    longitud_ave_m, envergadura_ave_m, velocidad_vuelo_ave_ms,
    diametro_rotor_m, n_palas=3, cuerda_pala_m=3.5,
    velocidad_rotor_rpm=12, angulo_paso_pala_deg=5,
):
    """P_collision geométrica (Band 2007 eq. 2).

    Probabilidad que ave atravesando el plano del rotor sea golpeada por una pala.
    Depende: relación tamaño ave vs disco rotor + frecuencia de palas.
    """
    R = diametro_rotor_m / 2.0
    omega_rad_s = float(velocidad_rotor_rpm) * 2.0 * np.pi / 60.0  # rad/s

    # Tiempo que ave tarda en atravesar área rotor (frontalmente)
    t_paso = float(longitud_ave_m) / max(float(velocidad_vuelo_ave_ms), 0.1)

    # Distancia barrida por una pala durante paso ave (en el borde, peor caso)
    dist_pala = omega_rad_s * R * t_paso

    # Probabilidad geométrica: si dist_pala / (perímetro/n_palas) >= 1, hit garantizado
    perimetro = 2.0 * np.pi * R
    p_geom = min(1.0, float(n_palas) * dist_pala / perimetro)

    # Ajuste por ángulo de paso (palas inclinadas reducen riesgo)
    factor_angulo = max(0.5, 1.0 - float(angulo_paso_pala_deg) / 30.0)

    # Factor envergadura (aves grandes más vulnerables)
    factor_env = min(1.5, float(envergadura_ave_m) / 1.0)

    return float(p_geom * factor_angulo * factor_env)


def calcular_riesgo_colision_band_2007(
    n_aves_paso_anual,
    longitud_ave_m=0.6, envergadura_ave_m=1.5, velocidad_vuelo_ave_ms=12,
    diametro_rotor_m=100, altura_buje_m=80,
    altura_min_vuelo_m=10, altura_max_vuelo_m=200,
    velocidad_rotor_rpm=12, n_palas=3, cuerda_pala_m=3.5,
    angulo_paso_pala_deg=5,
    tiempo_operacion_horas_anuales=8000,
    p_evasion=0.95,
):
    """Band 2007 collision risk model.

    Returns dict con:
      - colisiones_anuales: número esperado colisiones/turbina/año
      - p_paso_rotor: fracción aves vuelan a altura rotor
      - p_geometrica: P de colisión dado paso
      - operacion_pct: % tiempo turbina operando
    """
    # 1. Fracción aves volando dentro del swept area (vertical)
    h_min_rotor = altura_buje_m - diametro_rotor_m / 2.0
    h_max_rotor = altura_buje_m + diametro_rotor_m / 2.0

    h_min_vuelo = max(float(altura_min_vuelo_m), h_min_rotor)
    h_max_vuelo = min(float(altura_max_vuelo_m), h_max_rotor)
    rango_vuelo = max(0.1, float(altura_max_vuelo_m) - float(altura_min_vuelo_m))
    fraccion_altura_rotor = max(0.0, (h_max_vuelo - h_min_vuelo) / rango_vuelo) if h_max_vuelo > h_min_vuelo else 0.0

    # 2. Probabilidad geométrica de colisión
    p_geom = probabilidad_paso_geometrico_band(
        longitud_ave_m, envergadura_ave_m, velocidad_vuelo_ave_ms,
        diametro_rotor_m, n_palas, cuerda_pala_m,
        velocidad_rotor_rpm, angulo_paso_pala_deg,
    )

    # 3. Tiempo operación (turbinas no operan todo el año)
    operacion_frac = float(tiempo_operacion_horas_anuales) / 8760.0

    # 4. Colisiones = N_aves × P_altura × P_geom × (1 - P_evasion) × tiempo_op
    colisiones = (
        float(n_aves_paso_anual) * fraccion_altura_rotor
        * p_geom * (1.0 - float(p_evasion))
        * operacion_frac
    )

    return {
        "colisiones_anuales_turbina": float(colisiones),
        "p_paso_altura_rotor": float(fraccion_altura_rotor),
        "p_geometrica": float(p_geom),
        "operacion_frac": float(operacion_frac),
        "p_evasion_usado": float(p_evasion),
    }


def estimar_colisiones_anuales_parque(
    df_aves_observadas, n_turbinas, diametro_rotor, altura_buje,
    p_evasion_default=0.95, tiempo_operacion_h=8000,
):
    """Tabla colisiones esperadas por especie + total parque.

    df_aves_observadas: DataFrame con columnas:
      especie, n_aves_paso_anual, longitud_m, envergadura_m, velocidad_vuelo_ms,
      p_evasion (opcional, default 0.95).
    """
    if df_aves_observadas is None or len(df_aves_observadas) == 0:
        return pd.DataFrame()

    rows = []
    for _, ave in df_aves_observadas.iterrows():
        n_paso = float(ave.get("n_aves_paso_anual", 0))
        if n_paso <= 0:
            continue
        p_ev = float(ave.get("p_evasion", p_evasion_default))
        res = calcular_riesgo_colision_band_2007(
            n_aves_paso_anual=n_paso,
            longitud_ave_m=float(ave.get("longitud_m", 0.5)),
            envergadura_ave_m=float(ave.get("envergadura_m", 1.2)),
            velocidad_vuelo_ave_ms=float(ave.get("velocidad_vuelo_ms", 12)),
            diametro_rotor_m=diametro_rotor,
            altura_buje_m=altura_buje,
            p_evasion=p_ev,
            tiempo_operacion_horas_anuales=tiempo_operacion_h,
        )
        col_parque = res["colisiones_anuales_turbina"] * int(n_turbinas)
        rows.append({
            "especie": ave.get("especie", "?"),
            "n_aves_paso_anual": n_paso,
            "p_evasion": p_ev,
            "colisiones_turbina_anio": res["colisiones_anuales_turbina"],
            "colisiones_parque_anio": col_parque,
            "p_geometrica": res["p_geometrica"],
            "p_paso_altura_rotor": res["p_paso_altura_rotor"],
        })
    df_out = pd.DataFrame(rows)
    if len(df_out) > 0:
        df_out["riesgo_categoria"] = df_out["colisiones_parque_anio"].apply(
            lambda x: "BAJO" if x < 1 else ("MEDIO" if x < 5 else "ALTO")
        )
    return df_out


def get_aves_default_dataframe():
    """Devuelve DataFrame con aves default Colombia para usar como template."""
    return pd.DataFrame(AVES_DEFAULT_COLOMBIA)
