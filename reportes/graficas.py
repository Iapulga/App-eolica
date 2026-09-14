"""Gráficas formales de los informes (reporte bankable y Excel PRO).

Mismo estilo (`reportes.estilo`) y mismos datos del proyecto en todos los documentos. Las etiquetas
llegan ya traducidas desde quien llama y los números usan el formato del idioma (`fmt_num`).
Ninguna figura lleva título interno salvo que se pida con `titulo`: el rótulo va en el documento.
"""
from __future__ import annotations

import math
import textwrap

import numpy as np

from .datos_proyecto import fmt_num, num
from .estilo import (
    AMBAR,
    AZUL,
    ESCALA_VIENTO,
    GRIS,
    GRIS_EJE,
    MARINO,
    REGLA,
    ROJO,
    SERIE,
    TEXTO,
    VERDE_AZULADO,
    aplicar_estilo_mpl,
    c,
    formateador,
    png,
)

_SECTORES_EN = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def sectores_16(lang="es"):
    """Nombres de los 16 sectores (N, NNE…); en español, portugués y francés el oeste es «O»."""
    return list(_SECTORES_EN) if lang == "en" else [s.replace("W", "O") for s in _SECTORES_EN]


def _indice_sector(wd):
    return np.floor(((np.asarray(wd, dtype=float) % 360.0 + 11.25) % 360.0) / 22.5).astype(int)


def estadistica_sectores(ws, wd):
    """Frecuencia (%) y velocidad media por sector de 22,5° (sector 0 centrado en el norte)."""
    ws = np.asarray(ws, dtype=float)
    wd = np.asarray(wd, dtype=float)
    ok = np.isfinite(ws) & np.isfinite(wd)
    ws, wd = ws[ok], wd[ok]
    if ws.size == 0:
        return []
    idx = _indice_sector(wd)
    filas = []
    for s in range(16):
        mask = idx == s
        filas.append((s, 100.0 * mask.sum() / ws.size, float(ws[mask].mean()) if mask.any() else None))
    return filas


def _titulo(ax, titulo):
    if titulo:
        ax.set_title(titulo, loc="left", pad=8)


def _escala(valores, moneda):
    """(divisor, unidad): millones si los valores son grandes."""
    grande = max((abs(v) for v in valores if v is not None), default=0.0) >= 1e6
    return (1e6, f"M {moneda}") if grande else (1.0, moneda)


def _paso_redondo(tope, max_marcas=5):
    for paso in (1, 2, 2.5, 5, 10, 15, 20, 25, 50, 100):
        if tope / paso <= max_marcas:
            return paso
    return 10 ** math.ceil(math.log10(tope))


def _envolver(texto, ancho=14):
    return "\n".join(textwrap.wrap(str(texto), ancho)) or str(texto)


# ─────────────────────────────────────────────────────────────
# Recurso eólico
# ─────────────────────────────────────────────────────────────
def rosa_por_clases(ws, wd, lang="es", limites=(4, 8, 12, 16), unidad="m/s", titulo=None):
    """Rosa de vientos apilada por clases de velocidad (frecuencia en %)."""
    ws = np.asarray(ws, dtype=float)
    wd = np.asarray(wd, dtype=float)
    ok = np.isfinite(ws) & np.isfinite(wd)
    ws, wd = ws[ok], wd[ok]
    if ws.size == 0:
        return None
    plt = aplicar_estilo_mpl()
    sector = _indice_sector(wd)
    bordes = [0.0, *limites, np.inf]
    frec = np.zeros((len(bordes) - 1, 16))
    for k in range(len(bordes) - 1):
        mask = (ws >= bordes[k]) & (ws < bordes[k + 1])
        frec[k] = np.bincount(sector[mask], minlength=16)[:16] / ws.size * 100.0
    theta = np.deg2rad(np.arange(16) * 22.5)
    fig = plt.figure(figsize=(5.6, 5.5))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    base = np.zeros(16)
    for k in range(len(bordes) - 1):
        if np.isinf(bordes[k + 1]):
            etiqueta = f"≥ {fmt_num(bordes[k], 0, lang)} {unidad}"
        else:
            etiqueta = f"{fmt_num(bordes[k], 0, lang)}–{fmt_num(bordes[k + 1], 0, lang)} {unidad}"
        ax.bar(theta, frec[k], width=np.deg2rad(22.5) * 0.9, bottom=base, color=ESCALA_VIENTO[k % len(ESCALA_VIENTO)],
               edgecolor="white", linewidth=0.6, label=etiqueta)
        base += frec[k]
    ax.set_xticks(theta)
    ax.set_xticklabels(sectores_16(lang), fontsize=8.5, color=c(TEXTO))
    paso = _paso_redondo(max(base.max(), 1.0))
    marcas = np.arange(paso, base.max() * 1.001 + paso, paso)
    ax.set_yticks(marcas)
    ax.set_yticklabels([f"{fmt_num(m, 0 if paso >= 1 else 1, lang)} %" for m in marcas], fontsize=7.5, color=c(GRIS))
    ax.set_rlabel_position(11.25)
    ax.grid(True, color=c(REGLA), linewidth=0.6)
    ax.spines["polar"].set_color(c(GRIS_EJE))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=len(bordes) - 1, fontsize=8, handlelength=1.1,
              columnspacing=0.9)
    _titulo(ax, titulo)
    return png(fig)


def rosa_valores(sectores, valores, lang="es", unidad="%", color=MARINO, titulo=None):
    """Rosa de 16 sectores con un valor por sector (frecuencia, velocidad o energía)."""
    if not sectores:
        return None
    plt = aplicar_estilo_mpl()
    valores = [num(v, 0.0) or 0.0 for v in valores]
    theta = np.linspace(0, 2 * np.pi, len(sectores), endpoint=False)
    fig = plt.figure(figsize=(5.4, 5.4))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.bar(theta, valores, width=2 * np.pi / len(sectores) * 0.9, color=c(color), edgecolor="white", alpha=0.9)
    ax.set_xticks(theta)
    ax.set_xticklabels(sectores, fontsize=8.5, color=c(TEXTO))
    tope = max(valores) if valores else 1.0
    ax.yaxis.set_major_formatter(formateador(lang, 0 if tope >= 20 else 1))
    ax.tick_params(axis="y", labelsize=7.5, colors=c(GRIS))
    ax.grid(True, color=c(REGLA), linewidth=0.6)
    ax.spines["polar"].set_color(c(GRIS_EJE))
    _titulo(ax, f"{titulo} ({unidad})" if titulo else None)
    return png(fig)


def histograma_weibull(ws, lang="es", eje_x="Velocidad del viento (m/s)", eje_y="Frecuencia relativa",
                       etiqueta_media="Media = {v} m/s", titulo=None):
    ws = np.asarray(ws, dtype=float)
    ws = ws[np.isfinite(ws) & (ws >= 0)]
    if ws.size < 10:
        return None
    plt = aplicar_estilo_mpl()
    fig, ax = plt.subplots(figsize=(7.2, 3.3))
    vmax = float(np.ceil(np.percentile(ws, 99.9)))
    ax.hist(ws, bins=np.arange(0, vmax + 0.5, 0.5), density=True, color=c(AZUL), alpha=0.35, edgecolor="white",
            linewidth=0.5)
    try:
        from scipy import stats

        k, _, escala = stats.weibull_min.fit(ws[ws > 0], floc=0)
        x = np.linspace(0, vmax, 300)
        ax.plot(x, stats.weibull_min.pdf(x, k, scale=escala), color=c(MARINO), lw=2.0,
                label=f"Weibull: k = {fmt_num(k, 2, lang)} · c = {fmt_num(escala, 2, lang)} m/s")
    except Exception:
        pass
    media = float(ws.mean())
    ax.axvline(media, color=c(AMBAR), lw=1.4, ls="--", label=etiqueta_media.format(v=fmt_num(media, 2, lang)))
    ax.set_xlim(0, vmax)
    ax.set_xlabel(eje_x)
    ax.set_ylabel(eje_y)
    ax.xaxis.set_major_formatter(formateador(lang, 0))
    ax.yaxis.set_major_formatter(formateador(lang, 2))
    ax.legend(loc="upper right")
    _titulo(ax, titulo)
    return png(fig)


# ─────────────────────────────────────────────────────────────
# Aerogenerador y parque
# ─────────────────────────────────────────────────────────────
def curva_potencia(df_curva, lang="es", diametro=None, densidad=None, marcas=None, eje_x="Velocidad del viento (m/s)",
                   eje_p="Potencia (kW)", eje_cp="Coeficiente de potencia Cp", leyenda=("Potencia", "Cp"), titulo=None):
    """Curva de potencia (kW) con Cp en el eje derecho (misma función `calcular_cp` de la app) y las
    velocidades de arranque, nominal y parada marcadas. `marcas` = [(etiqueta, velocidad), …]."""
    if df_curva is None or len(df_curva) == 0 or not {"Velocidad_num", "Potencia_W"} <= set(df_curva.columns):
        return None
    plt = aplicar_estilo_mpl()
    v = np.asarray(df_curva["Velocidad_num"], dtype=float)
    p = np.asarray(df_curva["Potencia_W"], dtype=float) / 1000.0
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    linea_p, = ax.plot(v, p, color=c(MARINO), lw=2.2, label=leyenda[0])
    ax.fill_between(v, 0, p, color=c(MARINO), alpha=0.06)
    ax.set_xlabel(eje_x)
    ax.set_ylabel(eje_p)
    ax.set_ylim(0, max(p.max() * 1.18, 1.0))
    ax.set_xlim(0, max(v.max(), 1.0))
    ax.xaxis.set_major_formatter(formateador(lang, 0))
    ax.yaxis.set_major_formatter(formateador(lang, 0))
    manejadores = [linea_p]
    if diametro:
        try:
            from calculos import calcular_cp

            cp = np.asarray(calcular_cp(df_curva, densidad or 1.225, math.pi * (diametro / 2.0) ** 2)["Cp"], dtype=float)
            ax2 = ax.twinx()
            linea_cp, = ax2.plot(v, cp, color=c(AMBAR), lw=1.6, ls="--", label=leyenda[1])
            ax2.set_ylabel(eje_cp, color=c(TEXTO))
            ax2.set_ylim(0, max(0.6, float(np.nanmax(cp)) * 1.25))
            ax2.yaxis.set_major_formatter(formateador(lang, 2))
            ax2.spines["right"].set_visible(True)
            ax2.spines["right"].set_color(c(GRIS_EJE))
            ax2.grid(False)
            manejadores.append(linea_cp)
        except Exception:
            pass
    tope = ax.get_ylim()[1]
    for etiqueta, vel in marcas or []:
        vel = num(vel)
        if vel is None:
            continue
        ax.axvline(vel, color=c(GRIS), lw=0.8, ls=":")
        ax.text(vel, tope * 0.985, f"{etiqueta}\n{fmt_num(vel, 1, lang)} m/s", ha="center", va="top", fontsize=7.3,
                color=c(GRIS), bbox=dict(facecolor="white", edgecolor="none", pad=1.0))
    ax.legend(manejadores, [m.get_label() for m in manejadores], loc="center left")
    _titulo(ax, titulo)
    return png(fig)


def disposicion(turbinas, diametro=None, lang="es", titulo=None):
    """Planta del parque: aerogeneradores, círculo del rotor a escala, flecha de norte y barra de escala."""
    if not turbinas:
        return None
    plt = aplicar_estilo_mpl()
    xs = np.array([t["x_m"] for t in turbinas], dtype=float)
    ys = np.array([t["y_m"] for t in turbinas], dtype=float)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.grid(True, axis="both", color=c(REGLA), linewidth=0.5)
    ax.scatter(xs, ys, s=38, color=c(MARINO), edgecolors="white", linewidths=1.2, zorder=3)
    for t in turbinas:
        ax.annotate(t["id"], (t["x_m"], t["y_m"]), xytext=(7, 5), textcoords="offset points", fontsize=8,
                    fontweight="bold", color=c(MARINO))
        if diametro:
            ax.add_patch(plt.Circle((t["x_m"], t["y_m"]), diametro / 2.0, fill=False, color=c(AMBAR), lw=0.9))
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.15)
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.xaxis.set_major_formatter(formateador(lang, 0))
    ax.yaxis.set_major_formatter(formateador(lang, 0))
    fig.canvas.draw()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    ax.set_autoscale_on(False)
    largo = next((paso for paso in (50, 100, 200, 250, 500, 1000, 2000, 5000, 10000) if paso >= (x1 - x0) * 0.15), 10000)
    bx, by = x0 + (x1 - x0) * 0.05, y0 + (y1 - y0) * 0.07
    ax.plot([bx, bx + largo], [by, by], color=c(TEXTO), lw=2.2, solid_capstyle="butt", scalex=False, scaley=False)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.text(bx + largo / 2, by + (y1 - y0) * 0.025, f"{fmt_num(largo / 1000, 1, lang)} km" if largo >= 1000 else f"{largo} m",
            ha="center", va="bottom", fontsize=7.5, color=c(TEXTO))
    ax.annotate("N", xy=(0.95, 0.93), xytext=(0.95, 0.78), xycoords="axes fraction", ha="center", va="center",
                fontsize=9, fontweight="bold", color=c(MARINO),
                arrowprops=dict(arrowstyle="-|>", color=c(MARINO), lw=1.3))
    _titulo(ax, titulo)
    return png(fig)


# ─────────────────────────────────────────────────────────────
# Energía e incertidumbre
# ─────────────────────────────────────────────────────────────
def cascada(pasos, neta, lang="es", etiquetas=None, eje_y="AEP (MWh/año)", titulo=None):
    """Cascada AEP bruta → neta con conectores; `etiquetas` = {clave: texto} (incluye 'bruta' y 'neta')."""
    if not pasos:
        return None
    etiquetas = etiquetas or {}
    plt = aplicar_estilo_mpl()
    bruta = pasos[0]["acumulada_mwh"]
    perdidas = [p for p in pasos[1:] if abs(p["perdida_mwh"]) > 1e-9]
    final = neta if neta is not None else pasos[-1]["acumulada_mwh"]
    nombres = [etiquetas.get("bruta", "AEP bruta")] + [etiquetas.get(p["clave"], p["clave"]) for p in perdidas] + \
              [etiquetas.get("neta", "AEP neta")]
    fig, ax = plt.subplots(figsize=(7.4, 3.8))
    ancho = 0.62
    ax.bar(0, bruta, width=ancho, color=c(MARINO))
    ax.text(0, bruta, fmt_num(bruta, 0, lang), ha="center", va="bottom", fontsize=8.5, fontweight="bold", color=c(MARINO))
    nivel = bruta
    for i, paso in enumerate(perdidas, 1):
        ax.plot([i - 1 + ancho / 2, i - ancho / 2], [nivel, nivel], color=c(GRIS_EJE), lw=0.8, ls="--")
        ax.bar(i, -paso["perdida_mwh"], bottom=nivel, width=ancho, color=c(ROJO), alpha=0.82)
        pct = paso["perdida_mwh"] / bruta * 100.0 if bruta else 0.0
        ax.text(i, nivel, f"−{fmt_num(paso['perdida_mwh'], 0, lang)}\n({fmt_num(pct, 2, lang)} %)", ha="center",
                va="bottom", fontsize=7.5, color=c(ROJO))
        nivel -= paso["perdida_mwh"]
    n = len(nombres) - 1
    ax.plot([n - 1 + ancho / 2, n - ancho / 2], [nivel, nivel], color=c(GRIS_EJE), lw=0.8, ls="--")
    ax.bar(n, final, width=ancho, color=c(VERDE_AZULADO))
    ax.text(n, final, fmt_num(final, 0, lang), ha="center", va="bottom", fontsize=8.5, fontweight="bold",
            color=c(VERDE_AZULADO))
    ax.set_xticks(range(len(nombres)))
    ax.set_xticklabels([_envolver(t, 15) for t in nombres], fontsize=8)
    ax.set_ylabel(eje_y)
    rango = max(bruta - min(final, nivel), bruta * 0.02)
    ax.set_ylim(max(0.0, min(final, nivel) - rango * 0.9), bruta + rango * 0.35)
    ax.yaxis.set_major_formatter(formateador(lang, 0))
    _titulo(ax, titulo)
    return png(fig)


def distribucion_mc(media, desv, percentiles, lang="es", eje_x="AEP (MWh/año)", etiqueta_area="90 %", titulo=None):
    """Densidad de la AEP (normal con media y desviación del Monte Carlo); área sombreada a la derecha del P90."""
    media, desv = num(media), num(desv)
    if not media or not desv or desv <= 0:
        return None
    plt = aplicar_estilo_mpl()
    x = np.linspace(media - 4 * desv, media + 4 * desv, 500)
    pdf = np.exp(-0.5 * ((x - media) / desv) ** 2) / (desv * np.sqrt(2 * np.pi))
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.plot(x, pdf, color=c(MARINO), lw=1.8)
    p90 = num((percentiles or {}).get("p90"))
    if p90:
        zona = x >= p90
        ax.fill_between(x[zona], 0, pdf[zona], color=c(MARINO), alpha=0.12)
        ax.text(media + 1.35 * desv, pdf.max() * 0.16, etiqueta_area, ha="center", va="center", fontsize=8.5,
                color=c(MARINO), fontweight="bold")
    colores = {"p50": c(MARINO), "p75": c(AZUL), "p90": c(AMBAR), "p99": c(ROJO)}
    for clave, color in colores.items():
        valor = num((percentiles or {}).get(clave))
        if valor:
            altura = float(np.interp(valor, x, pdf))
            ax.plot([valor, valor], [0, altura], color=color, lw=1.4)
            ax.text(valor, altura + pdf.max() * 0.05, f"{clave.upper()}\n{fmt_num(valor, 0, lang)}", ha="center",
                    va="bottom", fontsize=7.5, color=color, fontweight="bold",
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.8, alpha=0.9))
    ax.set_ylim(0, pdf.max() * 1.35)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.grid(False)
    ax.set_xlabel(eje_x)
    ax.xaxis.set_major_formatter(formateador(lang, 0))
    _titulo(ax, titulo)
    return png(fig)


def barras_sector(sectores, bruta, neta, lang="es", leyenda=("AEP bruta", "AEP neta"), eje_y="Energía anual (MWh/año)",
                  titulo=None):
    if not sectores:
        return None
    plt = aplicar_estilo_mpl()
    x = np.arange(len(sectores))
    fig, ax = plt.subplots(figsize=(8.8, 3.6))
    ax.bar(x - 0.2, bruta, width=0.4, color=c(MARINO), label=leyenda[0])
    ax.bar(x + 0.2, neta, width=0.4, color=c(VERDE_AZULADO), label=leyenda[1])
    ax.set_xticks(x)
    ax.set_xticklabels(sectores, fontsize=8)
    ax.set_ylabel(eje_y)
    ax.yaxis.set_major_formatter(formateador(lang, 0))
    ax.legend(loc="upper right")
    _titulo(ax, titulo)
    return png(fig)


# ─────────────────────────────────────────────────────────────
# Economía
# ─────────────────────────────────────────────────────────────
def flujo_caja(anios, flujos, acumulado, moneda, lang="es", etiquetas=None, titulo=None):
    """Barras del flujo neto anual y línea del acumulado descontado; marca el año de recuperación.
    `etiquetas` = {"flujo", "acumulado", "anio", "eje" (con {moneda}), "recuperacion" (con {a})}."""
    if not anios:
        return None
    e = {"flujo": "Flujo neto", "acumulado": "Acumulado descontado", "anio": "Año", "eje": "Flujo ({moneda})",
         "recuperacion": "Recuperación ≈ año {a}", **(etiquetas or {})}
    plt = aplicar_estilo_mpl()
    div, unidad = _escala(list(flujos) + list(acumulado), moneda)
    f = [v / div for v in flujos]
    a = [v / div for v in acumulado]
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.bar(anios, f, width=0.7, color=[c(ROJO) if v < 0 else c(MARINO) for v in f], alpha=0.88, label=e["flujo"])
    ax.plot(anios, a, color=c(AMBAR), lw=2.0, marker="o", ms=3, label=e["acumulado"])
    ax.axhline(0, color=c(TEXTO), lw=0.8)
    for i in range(1, len(a)):
        if a[i - 1] < 0 <= a[i]:
            ax.axvline(anios[i], color=c(GRIS), lw=0.9, ls=":")
            ax.text(anios[i] + 0.25, min(a) * 0.55, e["recuperacion"].format(a=anios[i]), fontsize=8, color=c(GRIS))
            break
    ax.set_xlabel(e["anio"])
    ax.set_ylabel(e["eje"].format(moneda=unidad))
    ax.yaxis.set_major_formatter(formateador(lang, 1 if div > 1 else 0))
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    ax.legend([Patch(color=c(MARINO)), Line2D([0], [0], color=c(AMBAR), lw=2.0, marker="o", ms=3)],
              [e["flujo"], e["acumulado"]], loc="upper left")
    _titulo(ax, titulo)
    return png(fig)


def tornado(filas, base, moneda, lang="es", etiquetas=None, delta=15.0, eje_x="Variación del VPN ({moneda})", titulo=None):
    """Sensibilidad del VPN: una barra por variable con −δ y +δ; `etiquetas` = {clave: nombre}."""
    if not filas or base is None:
        return None
    plt = aplicar_estilo_mpl()
    filas = list(reversed(filas))
    div, unidad = _escala([s["npv_menos"] - base for s in filas] + [s["npv_mas"] - base for s in filas], moneda)
    fig, ax = plt.subplots(figsize=(7.2, 0.8 + 0.6 * len(filas)))
    ax.grid(True, axis="x", color=c(REGLA), linewidth=0.6)
    ax.grid(False, axis="y")
    d_txt = fmt_num(delta, 0, lang)
    for i, s in enumerate(filas):
        for valor, signo in ((s["npv_menos"], "−"), (s["npv_mas"], "+")):
            dv = (valor - base) / div
            ax.barh(i, dv, height=0.58, color=c(VERDE_AZULADO) if dv >= 0 else c(ROJO), alpha=0.85)
            ax.text(dv, i, f" {signo}{d_txt} %: {fmt_num(dv, 1 if div > 1 else 0, lang).replace('-', '−')} ",
                    va="center", ha="left" if dv >= 0 else "right", fontsize=7.5, color=c(TEXTO))
    ax.axvline(0, color=c(TEXTO), lw=0.9)
    ax.set_yticks(range(len(filas)))
    ax.set_yticklabels([(etiquetas or {}).get(s["clave"], s["clave"]) for s in filas], fontsize=8.5)
    ax.set_xlabel(eje_x.format(moneda=unidad))
    ax.xaxis.set_major_formatter(formateador(lang, 1 if div > 1 else 0))
    ax.margins(x=0.28)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    _titulo(ax, titulo)
    return png(fig)


def dona(items, moneda, lang="es", etiqueta_total="Total", titulo=None):
    """Dona con el total en el centro y la leyenda con valor y porcentaje. `items` = [(nombre, valor), …]."""
    items = [(k, v) for k, v in items if v and v > 0]
    if len(items) < 2:
        return None
    plt = aplicar_estilo_mpl()
    total = sum(v for _, v in items)
    div, unidad = _escala([total], moneda)
    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    colores = [SERIE[i % len(SERIE)] for i in range(len(items))]
    cunas, _ = ax.pie([v for _, v in items], colors=colores, startangle=90, counterclock=False,
                      wedgeprops=dict(width=0.36, edgecolor="white", linewidth=1.5))
    ax.text(0, 0.08, etiqueta_total, ha="center", va="center", fontsize=8.5, color=c(GRIS))
    total_txt = f"{moneda} {fmt_num(total / div, 1, lang)} M" if div > 1 else f"{moneda} {fmt_num(total, 0, lang)}"
    ax.text(0, -0.1, total_txt, ha="center", va="center", fontsize=10.5, fontweight="bold", color=c(MARINO))
    ax.legend(cunas, [f"{k} — {fmt_num(v / div, 1 if div > 1 else 0, lang)} ({fmt_num(v / total * 100, 1, lang)} %)"
                      for k, v in items], loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=8.5, title=unidad,
              title_fontsize=8.5, alignment="left")
    ax.axis("equal")
    _titulo(ax, titulo)
    return png(fig)


__all__ = [
    "barras_sector", "cascada", "curva_potencia", "disposicion", "distribucion_mc", "dona", "estadistica_sectores",
    "flujo_caja", "histograma_weibull", "rosa_por_clases", "rosa_valores", "sectores_16", "tornado",
]
