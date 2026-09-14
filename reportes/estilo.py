"""Estilo formal común de los entregables (Word, PDF, Excel y gráficas).

Azul marino corporativo, letra Calibri, tablas con reglas horizontales finas y gráficas sin título
interno (el rótulo «Figura N.» va en el documento). Lo usan el reporte bankable, el informe técnico
y el Excel PRO para que todos los documentos se vean como una sola familia.
"""
from __future__ import annotations

import io

from .datos_proyecto import fmt_num

# ── Paleta (hex sin «#», como la usan Word y openpyxl) ──
MARINO = "1B365D"
AZUL = "2F5F8F"
VERDE_AZULADO = "1F7A6F"
AMBAR = "C98A1B"
TEXTO = "2B3645"
GRIS = "6B7785"
GRIS_EJE = "9AA5B1"
REGLA = "C9D2DC"
CEBRA = "F3F6F9"
VERDE = "2E7D32"
ROJO = "B3261E"
MARINO_SUAVE = "E8EDF4"
AMBAR_SUAVE = "FBF3E4"
ROJO_SUAVE = "F9E9E7"
VERDE_SUAVE = "E8F3EA"

FUENTE = "Calibri"
FUENTES_MPL = ["Calibri", "Segoe UI", "DejaVu Sans"]


def c(hex6):
    """'1B365D' → '#1B365D' (matplotlib / plotly)."""
    return f"#{hex6}"


SERIE = [c(MARINO), c(VERDE_AZULADO), c(AMBAR), c(AZUL), "#8C9BAB", c(ROJO), "#5B7A99"]
# Clases de velocidad de la rosa (de calma a fuerte): azules claros → marino
ESCALA_VIENTO = ["#C9D6E6", "#93AECB", "#5F86B0", c(AZUL), c(MARINO), "#0E1F38"]


# ─────────────────────────────────────────────────────────────
# matplotlib
# ─────────────────────────────────────────────────────────────
def aplicar_estilo_mpl():
    """Configura matplotlib con el estilo formal y devuelve pyplot."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from cycler import cycler

    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": FUENTES_MPL, "font.size": 9.5,
        "axes.titlesize": 10.5, "axes.titleweight": "bold", "axes.titlecolor": c(MARINO),
        "axes.labelsize": 9.5, "axes.labelcolor": c(TEXTO), "axes.edgecolor": c(GRIS_EJE), "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": c(REGLA), "grid.linewidth": 0.6, "grid.alpha": 0.8,
        "axes.axisbelow": True, "axes.prop_cycle": cycler(color=SERIE),
        "xtick.color": c(GRIS), "ytick.color": c(GRIS), "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "legend.fontsize": 8.5, "legend.frameon": False,
        "figure.facecolor": "white", "savefig.facecolor": "white", "figure.dpi": 100,
    })
    return plt


def formateador(lang="es", dec=0):
    from matplotlib.ticker import FuncFormatter

    return FuncFormatter(lambda v, _p: fmt_num(v, dec, lang))


def png(fig, dpi=200):
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white", pad_inches=0.08)
    plt.close(fig)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# plotly (informe técnico y pack de anexos)
# ─────────────────────────────────────────────────────────────
PLANTILLA_PLOTLY = "sma_formal"


def registrar_plantilla_plotly():
    """Plantilla «sma_formal»: Calibri, paleta corporativa, fondo blanco y rejilla suave."""
    import plotly.graph_objects as go
    import plotly.io as pio

    if PLANTILLA_PLOTLY in pio.templates:
        return PLANTILLA_PLOTLY
    plantilla = go.layout.Template(pio.templates["plotly_white"])
    eje = dict(showline=True, linecolor=c(GRIS_EJE), linewidth=1, ticks="outside", tickcolor=c(GRIS_EJE), ticklen=4,
               gridcolor="#E3E8EE", zeroline=False, title=dict(font=dict(color=c(TEXTO))))
    plantilla.layout.update(
        font=dict(family="Calibri, Segoe UI, Arial, sans-serif", size=15, color=c(TEXTO)),
        colorway=SERIE, paper_bgcolor="white", plot_bgcolor="white",
        title=dict(font=dict(size=17, color=c(MARINO))),
        xaxis=eje, yaxis=eje,
        legend=dict(bgcolor="rgba(255,255,255,0.9)", borderwidth=0, font=dict(size=13)),
        polar=dict(bgcolor="white", angularaxis=dict(linecolor=c(GRIS_EJE), gridcolor="#E3E8EE"),
                   radialaxis=dict(linecolor=c(GRIS_EJE), gridcolor="#E3E8EE")),
    )
    pio.templates[PLANTILLA_PLOTLY] = plantilla
    return PLANTILLA_PLOTLY


# ─────────────────────────────────────────────────────────────
# Diagrama de metodología (cajas y flechas)
# ─────────────────────────────────────────────────────────────
def diagrama_metodologia_png(pasos, por_fila=3, destacados=()):
    """Flujo de trabajo del estudio. `pasos` = [(título, detalle), …]; recorre las filas en serpentina."""
    if not pasos:
        return None
    plt = aplicar_estilo_mpl()
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    n = len(pasos)
    filas = -(-n // por_fila)
    ancho, alto, sep_x, sep_y = 2.35, 1.0, 0.62, 0.5
    total_w = por_fila * ancho + (por_fila - 1) * sep_x
    total_h = filas * alto + (filas - 1) * sep_y
    fig, ax = plt.subplots(figsize=(total_w * 0.95, total_h * 0.95 + 0.15))
    ax.set_xlim(-0.05, total_w + 0.05)
    ax.set_ylim(-0.05, total_h + 0.05)
    ax.axis("off")
    esquinas = []
    for i, (titulo, detalle) in enumerate(pasos):
        fila, col = divmod(i, por_fila)
        if fila % 2 == 1:
            col = por_fila - 1 - col
        x = col * (ancho + sep_x)
        y = total_h - (fila + 1) * alto - fila * sep_y
        relleno = c(MARINO) if i in destacados else c(MARINO_SUAVE)
        color_titulo = "white" if i in destacados else c(MARINO)
        ax.add_patch(FancyBboxPatch((x, y), ancho, alto, boxstyle="round,pad=0,rounding_size=0.08",
                                    linewidth=1.0, edgecolor=c(MARINO), facecolor=relleno))
        ax.text(x + 0.1, y + alto - 0.1, str(i + 1), ha="left", va="top", fontsize=7.5, fontweight="bold",
                color=color_titulo if i in destacados else c(AZUL))
        ax.text(x + ancho / 2, y + alto * 0.6, titulo, ha="center", va="center", fontsize=9.2, fontweight="bold",
                color=color_titulo)
        if detalle:
            ax.text(x + ancho / 2, y + alto * 0.27, detalle, ha="center", va="center", fontsize=7.3,
                    color="#DCE4EE" if i in destacados else c(GRIS), linespacing=1.15)
        esquinas.append((x, y))
    for i in range(n - 1):
        (x0, y0), (x1, y1) = esquinas[i], esquinas[i + 1]
        if abs(y0 - y1) < 1e-9:
            inicio, fin = ((x0 + ancho, y0 + alto / 2), (x1, y1 + alto / 2)) if x1 > x0 else \
                          ((x0, y0 + alto / 2), (x1 + ancho, y1 + alto / 2))
        else:
            inicio, fin = (x0 + ancho / 2, y0), (x1 + ancho / 2, y1 + alto)
        ax.add_patch(FancyArrowPatch(inicio, fin, arrowstyle="-|>", mutation_scale=11, color=c(MARINO),
                                     linewidth=1.1, shrinkA=1, shrinkB=1))
    return png(fig)


# ─────────────────────────────────────────────────────────────
# Colores de las figuras de la app (plotly) → paleta formal
# ─────────────────────────────────────────────────────────────
_EQUIVALENCIAS = {}
for _colores, _destino in (
    (("#1f77b4", "#636efa", "blue", "#2563eb", "#3b82f6", "#1e40af", "#1d4ed8", "#0ea5e9", "royalblue", "steelblue", "#3366ff", "#2f6df6"), MARINO),
    (("#ff7f0e", "#ffa15a", "orange", "#f59e0b", "#d97706", "#fb923c", "darkorange", "#ff5533"), AMBAR),
    (("#2ca02c", "#00cc96", "green", "#16a34a", "#22c55e", "#10b981", "#059669", "seagreen", "mediumseagreen", "#2ca25f"),
     VERDE_AZULADO),
    (("#d62728", "#ef553b", "red", "#dc2626", "#ef4444", "crimson", "firebrick"), ROJO),
    (("#9467bd", "#ab63fa", "purple", "#7c3aed", "#8b5cf6", "#6b21a8", "mediumpurple"), AZUL),
    (("#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#19d3f3", "#ff6692", "#b6e880", "#ff97ff", "#fecb52",
      "gray", "grey"), "8C9BAB"),
):
    for _color in _colores:
        _EQUIVALENCIAS[_color] = c(_destino)


def _formal(color):
    if isinstance(color, str):
        return _EQUIVALENCIAS.get(color.strip().lower(), color)
    if isinstance(color, (list, tuple)):
        return [_formal(x) for x in color]
    return color


def recolorear_plotly(fig):
    """Pasa a la paleta formal los colores por defecto de plotly/D3 que traen las figuras de la app. Solo
    cambia colores de trazas (tartas, barras, líneas, marcadores); las escalas de color no se tocan."""
    for traza in fig.data:
        marker = getattr(traza, "marker", None)
        if marker is not None:
            try:
                if getattr(marker, "colors", None) is not None:
                    marker.colors = _formal(list(marker.colors))
                elif isinstance(marker.color, str):
                    marker.color = _formal(marker.color)
                elif marker.color is not None and all(isinstance(x, str) for x in list(marker.color)):
                    marker.color = _formal(list(marker.color))
            except Exception:
                pass
        linea = getattr(traza, "line", None)
        if linea is not None:
            try:
                if isinstance(linea.color, str):
                    linea.color = _formal(linea.color)
            except Exception:
                pass
        for parte in ("increasing", "decreasing", "totals"):  # cascadas (go.Waterfall)
            try:
                marcador = getattr(getattr(traza, parte, None), "marker", None)
                if marcador is not None:
                    if isinstance(marcador.color, str):
                        marcador.color = _formal(marcador.color)
                    if isinstance(marcador.line.color, str):
                        marcador.line.color = _formal(marcador.line.color)
            except Exception:
                pass
    return fig


# ── FIN ESTILO ──
