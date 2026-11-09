"""Curva de potencia: potencia nula fuera del rango [primer punto, cut-out].

El cut-out es el último punto de la curva (inferir_puntos_operacion_curva). Por
encima de él la turbina se detiene, así que la interpolación debe devolver 0 y la
integración Weibull hasta 35 m/s no debe sumar energía en ese tramo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calculos import interpolar_potencia_curva_preparada, weibull_pdf
from calculos_energia import potencia_media_sector


def _curva_simple():
    # cut-in 3 m/s, nominal 2 MW desde 12 m/s, cut-out 25 m/s.
    return pd.DataFrame(
        {
            "Velocidad_num": [3.0, 6.0, 9.0, 12.0, 25.0],
            "Potencia_W": [0.0, 400e3, 1200e3, 2000e3, 2000e3],
        }
    )


def test_interpolacion_cero_fuera_del_rango():
    v = np.array([0.0, 2.9, 12.0, 25.0, 25.1, 30.0, 35.0])
    p = interpolar_potencia_curva_preparada(_curva_simple(), v)
    np.testing.assert_allclose(p, [0.0, 0.0, 2000e3, 2000e3, 0.0, 0.0, 0.0])


def test_potencia_media_no_suma_energia_tras_cut_out():
    curva = _curva_simple()
    # Viento muy fuerte: buena parte de la probabilidad cae por encima de 25 m/s.
    fila = pd.Series({"k Weibull": 2.0, "c Weibull (m/s)": 20.0})
    p_media = potencia_media_sector(curva, fila, metodo="Weibull")

    v = np.arange(0.0, 25.0 + 0.1, 0.1)
    y = interpolar_potencia_curva_preparada(curva, v) * weibull_pdf(v, 2.0, 20.0)
    esperado = float(np.sum((y[:-1] + y[1:]) * 0.5 * np.diff(v)))

    # Solo puede diferir por el trapecio que cruza 25 m/s (paso de 0,1 m/s).
    assert abs(p_media - esperado) / esperado < 0.01
    # Con la potencia nominal mantenida tras el cut-out daría mucho más.
    prob_sobre_cut_out = float(np.exp(-((25.0 / 20.0) ** 2.0)))
    assert p_media < esperado + 0.5 * 2000e3 * prob_sobre_cut_out
