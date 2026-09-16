"""
fragment_demo.py — Demostración AISLADA de st.fragment.
========================================================

Este archivo NO toca tu app ni su diseño: vive en `demos/`, no lo importa nadie
y el empaquetado (.exe) no lo incluye (el spec solo toma los .py de la raíz).

Para verlo en acción:

    streamlit run demos/fragment_demo.py

Qué demuestra
-------------
El "no se siente vivo" de Streamlit viene de que CADA interacción re-ejecuta TODO
el script de arriba a abajo. `st.fragment` permite que UNA sección se re-ejecute
sola, sin recargar el resto.

- Columna IZQUIERDA (sin fragment): mover el slider re-ejecuta TODO el script →
  el contador de "ejecuciones completas" sube y toda la página parpadea.
- Columna DERECHA (con @st.fragment): mover el slider re-ejecuta SOLO ese bloque →
  el contador de arriba NO sube; solo cambia su propia gráfica, al instante.
"""
import time

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Demo · st.fragment", layout="wide")

# ── Contador de EJECUCIONES COMPLETAS del script ──────────────────────────────
# Se incrementa en CADA re-ejecución total del script. Es nuestro "detector" de
# recargas de página: si sube al mover un control, es que recargó todo.
st.session_state.setdefault("full_runs", 0)
st.session_state["full_runs"] += 1

st.title("¿Qué hace st.fragment? (demo en vivo)")
st.write(
    "Vigila el contador de abajo: **sube solo cuando se re-ejecuta TODO el script**. "
    "Mueve cada slider y compara."
)

box = st.container(border=True)
cc1, cc2 = box.columns(2)
cc1.metric(
    "🔁 Ejecuciones COMPLETAS del script",
    st.session_state["full_runs"],
    help="Si esto sube al mover un slider, recargó toda la página.",
)
cc2.metric("🕒 Última ejecución completa", time.strftime("%H:%M:%S"))


def curva(freq: float, n: int = 400) -> pd.DataFrame:
    x = np.linspace(0, 4 * np.pi, n)
    return pd.DataFrame({"sin(freq·x)": np.sin(freq * x)}, index=x)


col_a, col_b = st.columns(2, gap="large")

# ── IZQUIERDA: SIN fragment ───────────────────────────────────────────────────
with col_a:
    st.subheader("❌ Sin fragment")
    st.caption(
        "Mover este slider re-ejecuta **todo** el script → el contador de arriba sube "
        "y toda la página se repinta."
    )
    freq_a = st.slider("Frecuencia A", 0.5, 5.0, 1.0, 0.1, key="freq_a")
    st.line_chart(curva(freq_a), height=260)

# ── DERECHA: CON @st.fragment ─────────────────────────────────────────────────
with col_b:
    st.subheader("✅ Con @st.fragment")
    st.caption(
        "Mover este slider re-ejecuta **solo este recuadro** → el contador de arriba "
        "NO se mueve; la gráfica cambia al instante."
    )

SMA 2.0
Wind Project Analyzer
Inicio
Panel inicial
Fase 1
Aerogenerador
Fase 2
Perfiles de viento
Fase 3
Velocidad promedio
Fase 4
Estelas y arreglo
Fase 5
AEP bruta y neta
Fase 6
Exportar y guardar
Fase 1 · Aerogenerador 
    @st.fragment
    def bloque_vivo():
        st.session_state["frag_runs"] = st.session_state.get("frag_runs", 0) + 1
        freq_b = st.slider("Frecuencia B", 0.5, 5.0, 1.0, 0.1, key="freq_b")
        st.line_chart(curva(freq_b), height=260)
        st.caption(
            f"Re-ejecuciones de SOLO este fragment: **{st.session_state['frag_runs']}** "
            "(el contador grande de arriba no cambió al mover este slider)."
        )

    bloque_vivo()

st.divider()
st.success(
    "En una app real esto significa: cambiar un parámetro y que solo se actualice su "
    "gráfica/tabla, sin recargar ni hacer parpadear toda la fase. Eso es la 'vida' que "
    "buscabas — y se logra sin JavaScript, con una función nativa de Streamlit."
)
