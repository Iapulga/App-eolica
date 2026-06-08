"""Smoke tests anti-romper: cada fase debe cargar sin lanzar excepción.

Usa st.testing.v1.AppTest para ejecutar cada script de página en proceso (sin
navegador) y verifica que el render inicial no produce una excepción Python.
NO valida números ni diseño — solo que la app no se rompe al abrir cada fase.

Correr:  python -m pytest tests/test_smoke_pages.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st
from streamlit.testing.v1 import AppTest


@pytest.fixture(autouse=True)
def _stub_multipage_nav(monkeypatch):
    """st.page_link / st.switch_page necesitan el grafo multipágina que AppTest
    (página aislada) no construye → lanzan KeyError 'url_pathname'. Son navegación
    del framework, no lógica de la app, así que los neutralizamos para el smoke."""
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(st, "switch_page", lambda *a, **k: None, raising=False)


PAGES = [
    "Inicio.py",
    "pages/1_Fase_1_Aerogenerador.py",
    "pages/2_Fase_2_Perfiles_de_viento.py",
    "pages/3_Fase_3_Velocidad_promedio.py",
    "pages/4_Fase_4_Estelas_y_arreglo.py",
    "pages/5_Fase_5_AEP_bruta_y_neta.py",
    "pages/6_Fase_6_Exportar_y_guardar.py",
]


@pytest.mark.parametrize("page", PAGES)
def test_page_loads_without_exception(page):
    at = AppTest.from_file(str(ROOT / page), default_timeout=90)
    at.run()
    assert not at.exception, f"{page} lanzó excepción: {at.exception}"
