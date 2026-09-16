"""
fase2_toggle_demo.py — Demo AISLADO de la mejora propuesta para la Fase 2.
=========================================================================

NO toca tu app ni su diseño: vive en `demos/`, no lo importa nadie y el .exe no lo
incluye (el spec solo toma .py de la raíz). Sirve para VER cómo quedaría el panel
de gráficas de la Fase 2 con `st.fragment` antes de tocar el archivo real.

    python -m streamlit run demos/fase2_toggle_demo.py

Qué reproduce
-------------
Los 5 "chips" reales de la Fase 2 (mismo estilo pill) que muestran/ocultan figuras
de perfiles de viento. Hoy, pulsar un chip re-ejecuta TODA la Fase 2 (rerun
completo). La mejora: meter chips + figuras en un `@st.fragment` para que pulsar
solo re-dibuje ese panel, al instante, sin recargar la fase.

- IZQUIERDA  ❌ Antes  : chips fuera de fragment → el contador de arriba SUBE.
- DERECHA    ✅ Después: chips dentro de fragment → el contador NO se mueve.
"""
import time

import numpy as np
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Demo · Fase 2 chips + fragment", layout="wide")

# ── Estilo "pill" copiado de la Fase 2 real (_render_fase2_plot_chip_controls) ──
st.markdown(
    """
    <style>
    [class*="st-key-demo_chip_panel"] [data-testid="stHorizontalBlock"]{
        display:flex !important; flex-wrap:wrap !important; gap:.55rem !important;
        align-items:flex-start !important;
    }
    [class*="st-key-demo_chip_panel"] [data-testid="stButton"] > button{
        display:inline-flex !important; align-items:center !important; gap:.55rem !important;
        border-radius:999px; border:1px solid #93c5fd !important; background:#ffffff !important;
        color:#1e3a8a !important; font-size:.88rem !important; font-weight:700 !important;
        padding:.34rem .9rem !important; min-height:2.5rem !important; width:auto !important;
        box-shadow:0 8px 18px rgba(15,23,42,.06) !important; white-space:nowrap !important;
    }
    [class*="st-key-demo_chip_panel"] [data-testid="stButton"] > button[kind="primary"]{
        background:#dbeafe !important; border-color:#60a5fa !important; color:#1e40af !important;
    }
    [class*="st-key-demo_chip_panel"] [data-testid="stButton"] > button:hover{
        border-color:#3b82f6 !important; color:#1e3a8a !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Contador de EJECUCIONES COMPLETAS del script (detector de rerun total) ──────
st.session_state.setdefault("full_runs", 0)
st.session_state["full_runs"] += 1

st.title("Fase 2 · panel de gráficas con st.fragment (demo)")
st.write(
    "Pulsa los **chips** en cada lado y vigila el contador. A la izquierda (hoy) "
    "sube en cada clic = recarga toda la fase. A la derecha (mejora) no se mueve."
)
box = st.container(border=True)
m1, m2 = box.columns(2)
m1.metric("🔁 Ejecuciones COMPLETAS del script", st.session_state["full_runs"],
          help="Si sube al pulsar un chip, recargó toda la página.")
m2.metric("🕒 Última ejecución completa", time.strftime("%H:%M:%S"))

# ── Figuras de ejemplo: perfiles de viento (velocidad vs altura) ───────────────
_ALTURAS = np.linspace(2, 120, 60)


def _perfil(v_ref, alpha, color, nombre, dash=None, yaxis_type="linear"):
    v = v_ref * (_ALTURAS / 50.0) ** alpha
    fig = go.Figure(go.Scatter(x=v, y=_ALTURAS, mode="lines", name=nombre,
                               line=dict(color=color, width=3, dash=dash)))
    fig.update_layout(height=260, margin=dict(t=36, b=30, l=40, r=12),
                      paper_bgcolor="#fff", plot_bgcolor="#fff",
                      title=dict(text=f"<b>{nombre}</b>", x=0.5, font=dict(size=14)),
                      showlegend=False)
    fig.update_xaxes(title_text="<b>Velocidad (m/s)</b>")
    fig.update_yaxes(title_text="<b>Altura (m)</b>", type=yaxis_type)
    return fig


def _comparacion(yaxis_type="linear"):
    fig = go.Figure()
    for v_ref, alpha, color, nombre, dash in [
        (8, 0.14, "#3366ff", "Exponencial", None),
        (8, 0.20, "#ff5533", "Log A", "dash"),
        (8, 0.17, "#2ca25f", "Promedio Log-Exp", "dot"),
    ]:
        v = v_ref * (_ALTURAS / 50.0) ** alpha
        fig.add_trace(go.Scatter(x=v, y=_ALTURAS, mode="lines", name=nombre,
                                 line=dict(color=color, width=3, dash=dash)))
    fig.update_layout(height=300, margin=dict(t=40, b=30, l=40, r=12),
                      paper_bgcolor="#fff", plot_bgcolor="#fff",
                      legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"))
    fig.update_xaxes(title_text="<b>Velocidad (m/s)</b>")
    fig.update_yaxes(title_text="<b>Altura (m)</b>", type=yaxis_type)
    return fig


# (label, clave corta) — los 5 chips reales de la Fase 2
CHIPS = [
    ("Perfil exponencial", "exp"),
    ("Log A", "log_a"),
    ("Promedio", "prom"),
    ("Comparación", "comp"),
    ("Escala log", "comp_log"),
]
DEFAULT_ON = {"exp", "comp"}  # algo visible al abrir


def _toggle(flag):
    st.session_state[flag] = not st.session_state.get(flag, False)


def _chips(scope):
    panel = st.container(horizontal=True, horizontal_alignment="left",
                         gap="small", key=f"demo_chip_panel_{scope}")
    with panel:
        for label, short in CHIPS:
            flag = f"demo_{scope}_{short}"
            st.session_state.setdefault(flag, short in DEFAULT_ON)
            st.button(label, key=f"demo_btn_{scope}_{short}",
                      type="primary" if st.session_state[flag] else "secondary",
                      on_click=_toggle, args=(flag,))


def _charts(scope):
    g = lambda short: st.session_state.get(f"demo_{scope}_{short}", False)
    cols = st.columns(3, gap="medium")
    if g("exp"):
        with cols[0]:
            with st.container(border=True):
                st.plotly_chart(_perfil(8, 0.14, "#3366ff", "F1 · Exponencial"),
                                use_container_width=True, key=f"{scope}_exp")
    if g("log_a"):
        with cols[1]:
            with st.container(border=True):
                st.plotly_chart(_perfil(8, 0.20, "#ff5533", "F2 · Log A", "dash", "log"),
                                use_container_width=True, key=f"{scope}_loga")
    if g("prom"):
        with cols[2]:
            with st.container(border=True):
                st.plotly_chart(_perfil(8, 0.17, "#2ca25f", "F3 · Promedio", "dot", "log"),
                                use_container_width=True, key=f"{scope}_prom")
    comp_cols = st.columns(2, gap="medium")
    if g("comp"):
        with comp_cols[0]:
            with st.container(border=True):
                st.markdown("**G1 · Comparación (escala normal)**")
                st.plotly_chart(_comparacion("linear"), use_container_width=True, key=f"{scope}_comp")
    if g("comp_log"):
        with comp_cols[1]:
            with st.container(border=True):
                st.markdown("**G2 · Comparación (escala log)**")
                st.plotly_chart(_comparacion("log"), use_container_width=True, key=f"{scope}_complog")


col_a, col_b = st.columns(2, gap="large")

with col_a:
    st.subheader("❌ Antes (cómo es hoy)")
    st.caption("Chips FUERA de fragment → cada clic re-ejecuta toda la fase (el contador sube).")
    _chips("a")
    _charts("a")

with col_b:
    st.subheader("✅ Después (con la mejora)")
    st.caption("Chips + figuras DENTRO de @st.fragment → solo se re-dibuja este panel, al instante.")

    @st.fragment
    def panel_vivo():
        st.session_state["frag_runs"] = st.session_state.get("frag_runs", 0) + 1
        _chips("b")
        _charts("b")
        st.caption(f"Re-ejecuciones de SOLO este fragment: **{st.session_state['frag_runs']}** "
                   "(el contador grande de arriba no cambió al pulsar estos chips).")

    panel_vivo()

st.divider()
st.success(
    "En la Fase 2 real: pulsar un chip mostraría/ocultaría su gráfica al instante, sin "
    "recargar ni hacer parpadear toda la fase. Mismo aspecto (mismos chips pill), pero 'vivo'."
)
