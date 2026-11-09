"""Exportación PNG de respaldo (matplotlib) con series horarias largas.

Antes, cada marca de tiempo de la serie horaria se trataba como una categoría
con su propia etiqueta rotada, y savefig se quedaba colgado (más de 6 min con
52 608 horas). Ahora las fechas se grafican como eje temporal y los ejes
categóricos rotulan como mucho unas pocas etiquetas.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("matplotlib")

from reportes.figuras import _export_plotly_figure_matplotlib, _x_como_fechas_matplotlib

N_HORAS = 50_000
LIMITE_S = 30.0
PNG = b"\x89PNG\r\n\x1a\n"


def _serie_horaria(x):
    rng = np.random.default_rng(0)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=rng.weibull(2.0, N_HORAS) * 6.0, mode="lines", name="WS10M"))
    fig.add_trace(go.Scatter(x=x, y=rng.weibull(2.0, N_HORAS) * 8.0, mode="lines", name="WS50M"))
    return fig


def _exportar_a_tiempo(fig):
    inicio = time.perf_counter()
    png = _export_plotly_figure_matplotlib(
        fig, title="Serie horaria", export_options={"width": 1250, "height": 620}
    )
    duracion = time.perf_counter() - inicio
    assert png.startswith(PNG)
    assert duracion < LIMITE_S, f"La exportación tardó {duracion:.1f} s"


def test_serie_horaria_con_fechas_en_texto():
    # Así llega desde la base de datos: marcas de tiempo como cadenas ISO.
    fechas = pd.date_range("2020-01-01", periods=N_HORAS, freq="h").strftime("%Y-%m-%d %H:%M:%S")
    _exportar_a_tiempo(_serie_horaria(list(fechas)))


def test_serie_horaria_con_datetime64():
    _exportar_a_tiempo(_serie_horaria(pd.date_range("2020-01-01", periods=N_HORAS, freq="h")))


def test_eje_categorico_con_muchas_categorias():
    categorias = [f"cat-{i}" for i in range(N_HORAS)]
    _exportar_a_tiempo(_serie_horaria(categorias))


def test_deteccion_de_fechas():
    assert _x_como_fechas_matplotlib(["2020-01-01 00:00", "2020-01-01 01:00"]) is not None
    assert _x_como_fechas_matplotlib(np.array(["2020-01-01"], dtype="datetime64[ns]")) is not None
    # Categorías que no son fechas ISO no deben convertirse.
    assert _x_como_fechas_matplotlib(["N", "NE", "E"]) is None
    assert _x_como_fechas_matplotlib(["3-4", "4-5"]) is None
    assert _x_como_fechas_matplotlib([1.0, 2.0]) is None
