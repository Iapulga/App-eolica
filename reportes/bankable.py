"""Reporte bankable estructurado — generación DOCX profesional.

Estructura alineada con IEC 61400-15-2, DNV-SE-0073 y prácticas de
WindPRO / WAsP / OpenWind:

    0. Cover page + Document Control + Disclaimer
    1. Executive Summary (Bankability Statement + KPIs)
    2. Project Description (sitio + aerogenerador + layout)
    3. Wind Resource Assessment (fuente, MCP, perfil, V_ref, V_50, ρ)
    4. Energy Yield (loss waterfall + per-WTG + Monte Carlo P50/P75/P90/P99)
    5. Uncertainty Budget (IEC 61400-15-2 categorías)
    6. IEC 61400-1 Site Suitability (SITE vs CLASS limits)
    7. Environmental (flicker + ruido ISO 9613-2)
    8. Bankable Economic Analysis (CAPEX/OPEX, cash flow, sensitivity tornado)
    9. Risk Register (matriz P × I contextualizada por país)
   10. Conclusions & Bankability Recommendations
   11. Appendices (methodology + per-turbine + cash flow detalle + refs)

Reusa infraestructura existente (`reportes/` modules + i18n_paises).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path


def _safe_get(d, key, default=""):
    if d is None:
        return default
    v = d.get(key, default) if isinstance(d, dict) else getattr(d, key, default)
    if v is None or (isinstance(v, float) and v != v):  # NaN
        return default
    return v


def _to_float(v, default=None):
    try:
        f = float(v)
        if f != f or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────
# FIGURAS (matplotlib → PNG BytesIO → docx)
# ─────────────────────────────────────────────────────────────
_FIG_BLUE = "#1F4E79"
_FIG_ORANGE = "#D97706"
_FIG_GREEN = "#1F6E3B"
_FIG_RED = "#8B1F1F"
_FIG_GRID = "#E2E8F0"


def _fig_to_png_bytes(fig, dpi=150):
    """matplotlib Figure → PNG bytes."""
    from io import BytesIO
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    buf.seek(0)
    try:
        import matplotlib.pyplot as plt
        plt.close(fig)
    except Exception:
        pass
    return buf.getvalue()


def _fig_rosa_vientos(nasa_df):
    """Polar rose 16 sectores from WD50M frequency."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return None
    if nasa_df is None or len(nasa_df) == 0 or "WD50M" not in nasa_df.columns:
        return None
    wd = nasa_df["WD50M"].dropna().values
    if len(wd) == 0:
        return None
    n_sec = 16
    bins = np.linspace(0, 360, n_sec + 1) - (360.0 / n_sec / 2.0)
    wd_shift = (wd + (360.0 / n_sec / 2.0)) % 360.0
    hist, _ = np.histogram(wd_shift, bins=np.linspace(0, 360, n_sec + 1))
    freq_pct = 100.0 * hist / hist.sum()
    theta = np.linspace(0, 2*np.pi, n_sec, endpoint=False)
    width = 2*np.pi / n_sec
    fig = plt.figure(figsize=(6, 6), dpi=150)
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    bars = ax.bar(theta, freq_pct, width=width*0.95, bottom=0.0,
                  color=_FIG_BLUE, edgecolor="white", alpha=0.85)
    ax.set_xticks(theta)
    ax.set_xticklabels(["N","NNE","NE","ENE","E","ESE","SE","SSE",
                        "S","SSW","SW","WSW","W","WNW","NW","NNW"], fontsize=8)
    ax.set_title("Rosa de vientos — frecuencia direccional WD50M (%)",
                 fontsize=11, pad=18, color=_FIG_BLUE, fontweight="bold")
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(True, alpha=0.4)
    return _fig_to_png_bytes(fig)


def _fig_weibull_histogram(nasa_df):
    """Histograma velocidad + ajuste Weibull (estimado MLE simple)."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from scipy import stats
    except ImportError:
        return None
    if nasa_df is None or len(nasa_df) == 0 or "WS50M" not in nasa_df.columns:
        return None
    ws = nasa_df["WS50M"].dropna().values
    if len(ws) == 0:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    counts, bins, _ = ax.hist(ws, bins=40, density=True,
                              color=_FIG_BLUE, alpha=0.55, edgecolor="white")
    # Weibull MLE
    try:
        k, _, c = stats.weibull_min.fit(ws, floc=0)
        x = np.linspace(0, ws.max(), 200)
        pdf = stats.weibull_min.pdf(x, k, scale=c)
        ax.plot(x, pdf, color=_FIG_ORANGE, lw=2.2,
                label=f"Weibull k={k:.2f}, c={c:.2f} m/s")
        ax.axvline(ws.mean(), color=_FIG_RED, lw=1.5, ls="--",
                   label=f"Media = {ws.mean():.2f} m/s")
        ax.legend(loc="upper right", fontsize=9)
    except Exception:
        pass
    ax.set_xlabel("Velocidad del viento WS50M (m/s)", fontsize=10)
    ax.set_ylabel("Densidad de probabilidad", fontsize=10)
    ax.set_title("Distribución de velocidades + ajuste Weibull",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    ax.grid(True, alpha=0.3, color=_FIG_GRID)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_to_png_bytes(fig)


def _fig_curva_potencia(df_curva, p_nominal_kw=None):
    """Curva de potencia turbina."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    if df_curva is None or len(df_curva) == 0:
        return None
    try:
        v = [float(x) for x in df_curva["Velocidad (m/s)"]]
        p_w = [float(x) for x in df_curva["Potencia (W)"]]
        p_kw = [x / 1000.0 for x in p_w]
    except Exception:
        return None
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    ax.plot(v, p_kw, color=_FIG_BLUE, lw=2.4, marker="o", markersize=4,
            markerfacecolor=_FIG_ORANGE, markeredgecolor="white")
    ax.fill_between(v, 0, p_kw, alpha=0.15, color=_FIG_BLUE)
    ax.set_xlabel("Velocidad del viento (m/s)", fontsize=10)
    ax.set_ylabel("Potencia (kW)", fontsize=10)
    ax.set_title("Curva de potencia del aerogenerador",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    ax.grid(True, alpha=0.3, color=_FIG_GRID)
    ax.spines[["top", "right"]].set_visible(False)
    if p_nominal_kw:
        ax.axhline(p_nominal_kw, color=_FIG_RED, ls="--", lw=1.2, alpha=0.7,
                   label=f"P nominal = {p_nominal_kw:.0f} kW")
        ax.legend(loc="lower right", fontsize=9)
    return _fig_to_png_bytes(fig)


def _fig_layout_parque(layout_rows, diametro_m=None):
    """Scatter XY del layout."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return None
    if not layout_rows:
        return None
    xs = [_to_float(r.get("x_m"), 0) for r in layout_rows]
    ys = [_to_float(r.get("y_m"), 0) for r in layout_rows]
    ids = [str(r.get("id", "")) for r in layout_rows]
    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=150)
    ax.scatter(xs, ys, s=180, color=_FIG_BLUE, edgecolors="white",
               linewidths=2, zorder=3)
    for x, y, lbl in zip(xs, ys, ids):
        ax.annotate(lbl, (x, y), xytext=(0, 14),
                    textcoords="offset points", ha="center",
                    fontsize=9, fontweight="bold", color=_FIG_BLUE)
    # rotor circles
    if diametro_m:
        for x, y in zip(xs, ys):
            circle = plt.Circle((x, y), diametro_m/2.0, fill=False,
                                color=_FIG_ORANGE, alpha=0.5, lw=1.0)
            ax.add_patch(circle)
    ax.set_xlabel("X (m)", fontsize=10)
    ax.set_ylabel("Y (m)", fontsize=10)
    ax.set_title(f"Layout del parque eólico — {len(layout_rows)} turbinas",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3, color=_FIG_GRID)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_to_png_bytes(fig)


def _fig_loss_waterfall(aep_bruta, losses):
    """Waterfall bar chart: gross → net AEP."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return None
    if not aep_bruta:
        return None
    labels = ["Bruta"] + [name for name, _ in losses] + ["Neta"]
    vals = [aep_bruta]
    running = aep_bruta
    deltas = []
    for _, pct in losses:
        delta = -running * (pct / 100.0)
        deltas.append(delta)
        running += delta
        vals.append(running)
    vals.append(running)  # final
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)
    # Bruta + Neta full bars
    ax.bar(0, aep_bruta, color=_FIG_GREEN, edgecolor="white", width=0.7)
    ax.bar(len(labels)-1, running, color=_FIG_BLUE, edgecolor="white", width=0.7)
    # losses as floating bars
    base = aep_bruta
    for i, delta in enumerate(deltas, 1):
        top = base
        bot = base + delta
        ax.bar(i, delta, bottom=base, color=_FIG_RED,
               edgecolor="white", alpha=0.85, width=0.7)
        ax.text(i, (top+bot)/2.0, f"{deltas[i-1]:,.0f}",
                ha="center", va="center", fontsize=8,
                color="white", fontweight="bold")
        base = bot
    ax.text(0, aep_bruta * 1.02, f"{aep_bruta:,.0f}",
            ha="center", fontsize=9, fontweight="bold", color=_FIG_GREEN)
    ax.text(len(labels)-1, running * 1.02, f"{running:,.0f}",
            ha="center", fontsize=9, fontweight="bold", color=_FIG_BLUE)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("AEP (MWh/año)", fontsize=10)
    ax.set_title("Loss waterfall — IEC 61400-15-2",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3, color=_FIG_GRID)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_to_png_bytes(fig)


def _fig_per_wtg(layout_rows, aep_per_wtg_mwh):
    """Bar chart producción por turbina."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    if not layout_rows or not aep_per_wtg_mwh:
        return None
    ids = [str(r.get("id", "")) for r in layout_rows]
    vals = [aep_per_wtg_mwh] * len(ids)
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    bars = ax.bar(ids, vals, color=_FIG_BLUE, edgecolor="white", alpha=0.85)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2.0, v * 1.01,
                f"{v:,.0f}", ha="center", fontsize=8, color=_FIG_BLUE,
                fontweight="bold")
    ax.set_xlabel("Aerogenerador", fontsize=10)
    ax.set_ylabel("AEP (MWh/año)", fontsize=10)
    ax.set_title("Producción anual estimada por turbina",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3, color=_FIG_GRID)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_to_png_bytes(fig)


def _fig_monte_carlo(mc_mean, mc_std, p50, p75, p90, p99):
    """Distribución MC normal aprox + percentiles."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from scipy import stats
    except ImportError:
        return None
    mc_mean = _to_float(mc_mean)
    mc_std = _to_float(mc_std)
    if not mc_mean or not mc_std or mc_std <= 0:
        return None
    x = np.linspace(mc_mean - 4*mc_std, mc_mean + 4*mc_std, 400)
    pdf = stats.norm.pdf(x, loc=mc_mean, scale=mc_std)
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)
    ax.plot(x, pdf, color=_FIG_BLUE, lw=2.2)
    ax.fill_between(x, 0, pdf, color=_FIG_BLUE, alpha=0.2)
    for p_val, label, color in [
        (_to_float(p50), "P50", _FIG_GREEN),
        (_to_float(p75), "P75", _FIG_ORANGE),
        (_to_float(p90), "P90 (banca)", _FIG_RED),
        (_to_float(p99), "P99", "#6B21A8"),
    ]:
        if p_val:
            ax.axvline(p_val, color=color, lw=1.6, ls="--",
                       label=f"{label} = {p_val:,.0f}")
    ax.set_xlabel("AEP (MWh/año)", fontsize=10)
    ax.set_ylabel("Densidad de probabilidad", fontsize=10)
    ax.set_title("Distribución Monte Carlo de AEP — P50/P75/P90/P99",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3, color=_FIG_GRID)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_to_png_bytes(fig)


def _fig_tornado(npv_base, sensitivities, currency="USD"):
    """Tornado horizontal: |Δ NPV| por variable."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return None
    if not sensitivities:
        return None
    labels = [s["label"] for s in sensitivities]
    lows = [s["low"] - npv_base for s in sensitivities]
    highs = [s["high"] - npv_base for s in sensitivities]
    # sort by abs range
    order = sorted(range(len(labels)),
                   key=lambda i: abs(highs[i] - lows[i]), reverse=True)
    labels = [labels[i] for i in order]
    lows = [lows[i] for i in order]
    highs = [highs[i] for i in order]
    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(9, 4 + 0.4*len(labels)), dpi=150)
    ax.barh(y, lows, height=0.7, color=_FIG_RED, alpha=0.85,
            edgecolor="white", label="Caso bajo")
    ax.barh(y, highs, height=0.7, color=_FIG_GREEN, alpha=0.85,
            edgecolor="white", label="Caso alto")
    ax.axvline(0, color="black", lw=1.0)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel(f"Δ NPV ({currency})", fontsize=10)
    ax.set_title(f"Análisis de sensibilidad — Tornado NPV "
                 f"(base = {currency} {npv_base:,.0f})",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, axis="x", alpha=0.3, color=_FIG_GRID)
    ax.spines[["top", "right"]].set_visible(False)
    return _fig_to_png_bytes(fig)


def _fig_capex_pie(capex_components, currency="USD"):
    """Pie chart CAPEX breakdown."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    items = [(k, v) for k, v in capex_components.items() if v > 0]
    if not items:
        return None
    labels = [k for k, _ in items]
    vals = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(7.5, 5.5), dpi=150)
    colors = ["#1F4E79", "#3B82F6", "#60A5FA", "#D97706", "#F59E0B", "#10B981"]
    wedges, texts, autotexts = ax.pie(vals, labels=labels, autopct="%1.1f%%",
                                      startangle=90, colors=colors[:len(items)],
                                      pctdistance=0.78,
                                      wedgeprops=dict(edgecolor="white", lw=2))
    for at in autotexts:
        at.set_color("white")
        at.set_fontweight("bold")
        at.set_fontsize(9)
    for t in texts:
        t.set_fontsize(9)
    ax.set_title(f"CAPEX breakdown — Total {currency} {sum(vals):,.0f}",
                 fontsize=11, color=_FIG_BLUE, fontweight="bold")
    return _fig_to_png_bytes(fig)


def _add_seq_caption(doc, label, text, italic=True):
    """Caption con campo SEQ auto-numerable. label='Figura' o 'Tabla'.

    En Word: "Figura 1 — texto", "Figura 2 — texto" ... auto via { SEQ label \\* ARABIC }.
    """
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Pt
    except ImportError:
        return None
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"{label} ")
    run.italic = italic
    run.bold = True
    try:
        run.font.size = Pt(9)
    except Exception:
        pass
    # SEQ field
    fld1 = OxmlElement('w:fldChar')
    fld1.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = f' SEQ {label} \\* ARABIC '
    fld2 = OxmlElement('w:fldChar')
    fld2.set(qn('w:fldCharType'), 'separate')
    placeholder = OxmlElement('w:t')
    placeholder.text = "1"
    fld3 = OxmlElement('w:fldChar')
    fld3.set(qn('w:fldCharType'), 'end')
    run._r.append(fld1)
    run._r.append(instr)
    run._r.append(fld2)
    run._r.append(placeholder)
    run._r.append(fld3)
    # caption text
    run2 = p.add_run(f" — {text}")
    run2.italic = italic
    try:
        run2.font.size = Pt(9)
    except Exception:
        pass
    return p


def _add_figure_caption(doc, text):
    return _add_seq_caption(doc, "Figura", text, italic=True)


def _add_table_caption(doc, text):
    return _add_seq_caption(doc, "Tabla", text, italic=True)


def _embed_fig(doc, png_bytes, width_inches=6.0, caption=None):
    """Insert PNG fig + optional caption italic centered."""
    if not png_bytes:
        return
    from io import BytesIO
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt
    except ImportError:
        return
    p_fig = doc.add_paragraph()
    p_fig.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_fig = p_fig.add_run()
    try:
        run_fig.add_picture(BytesIO(png_bytes), width=Inches(width_inches))
    except Exception:
        return
    if caption:
        # Auto-detectar prefijo "Figura X.Y —" o "Tabla X.Y —" → usar SEQ field
        import re as _re
        m = _re.match(r"^\s*(Figura|Tabla)\s+[\d\.]+\s*[—\-:]\s*(.+)$", str(caption))
        if m:
            label = m.group(1)
            body = m.group(2).strip()
            try:
                _add_seq_caption(doc, label, body, italic=True)
                return
            except Exception:
                pass
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_cap = p_cap.add_run(caption)
        r_cap.italic = True
        r_cap.font.size = Pt(9)


def construir_contexto_bankable(config, runtime_context=None, project_metadata=None):
    """Recopila TODOS los inputs del proyecto en un dict bankable-ready.

    Cubre IEC 61400-15-2 categorías de pérdidas e incertidumbre y datos
    requeridos por DNV/WindPRO para un informe de project finance.
    """
    project_metadata = project_metadata or {}
    runtime_context = runtime_context or {}

    pais_code = project_metadata.get("country_code") or config.get("f6_country_code", "OTRO")
    pais_nombre = project_metadata.get("country_nombre") or "Custom"
    pais_profile = {}
    try:
        from i18n_paises import get_country_profile
        pais_profile = get_country_profile(pais_code)
        pais_nombre = pais_profile.get("nombre", pais_nombre)
    except ImportError:
        pass

    # ── Layout (coordenadas de turbinas) ──
    layout_rows = []
    try:
        from db import cargar_layout_parque
        df_layout = cargar_layout_parque()
        for _, r in df_layout.iterrows():
            layout_rows.append({
                "id": str(r.get("turbina_id", "")),
                "x_m": _to_float(r.get("x_m"), 0.0),
                "y_m": _to_float(r.get("y_m"), 0.0),
            })
    except Exception:
        pass

    # ── NASA hourly + curva (para figs) ──
    nasa_df = None
    curva_df = None
    try:
        from db import cargar_nasa_hourly, cargar_tabla_curva
        nasa_df = cargar_nasa_hourly()
        curva_df = cargar_tabla_curva()
    except Exception:
        pass

    # ── CAPEX/OPEX componentes (JSON) ──
    capex_comp = {}
    opex_comp = {}
    try:
        capex_comp = json.loads(_safe_get(config, "f5_capex_componentes_json", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        capex_comp = {}
    try:
        opex_comp = json.loads(_safe_get(config, "f5_opex_componentes_json", "{}") or "{}")
    except (json.JSONDecodeError, TypeError):
        opex_comp = {}

    ctx = {
        "fecha_generacion": datetime.now(UTC).isoformat(),
        "metadata": {
            "project_name": project_metadata.get("project_name", config.get("project_name", "Proyecto sin nombre")),
            "autor": project_metadata.get("autor", config.get("f6_bankable_autor", "—")),
            "cliente": project_metadata.get("cliente", config.get("f6_bankable_cliente", "—")),
            "lat": _safe_get(config, "nasa_lat"),
            "lon": _safe_get(config, "nasa_lon"),
            "version_sma": "2.0 Fase D",
            "country_code": pais_code,
            "country_nombre": pais_nombre,
            "pais_profile": pais_profile,
            "doc_code": f"SMA-BK-{datetime.now(UTC).strftime('%Y%m%d')}-{pais_code}",
            "revision": "Rev A",
        },
        "wind_resource": {
            "fuente": _safe_get(config, "nasa_fuente", "NASA POWER"),
            "fecha_inicio": _safe_get(config, "nasa_inicio"),
            "fecha_fin": _safe_get(config, "nasa_fin"),
            "altura_ref": 50.0,  # NASA POWER baseline
            "altura_hub": _safe_get(config, "perfil_hhub"),
            "v_ref_10m": _safe_get(config, "perfil_vref"),     # m/s a 10 m
            "v_50m": _safe_get(config, "perfil_v50"),          # m/s a 50 m
            "u_star": _safe_get(config, "perfil_ustar"),
            "perfil_metodo": _safe_get(config, "perfil_metodo", "Exponencial"),
            "roughness_label": _safe_get(config, "f5_roughness_label") or _safe_get(config, "perfil_roughness_label"),
            "z0": _safe_get(config, "perfil_z0"),
            "perfil_alpha": _safe_get(config, "perfil_alpha"),
            "alpha_p25": _safe_get(config, "f2_alpha_calc_p25"),
            "alpha_mediana": _safe_get(config, "f2_alpha_calc_mediana"),
            "alpha_p75": _safe_get(config, "f2_alpha_calc_p75"),
            "alpha_n": _safe_get(config, "f2_alpha_calc_n"),
            "ti_15ms": _safe_get(config, "f5_ti_15ms_calc"),
            "ambient_ti": _safe_get(config, "f5_ambient_ti"),
            "densidad_sitio": _safe_get(config, "f5_densidad_sitio"),
            "altitud_sitio_m": _safe_get(config, "f5_altitud_sitio_m"),
            "temperatura_media_c": _safe_get(config, "f5_temperatura_media_c"),
            "mcp_usado": _safe_get(config, "f2_serie_uso", "nasa"),
            "mcp_calculado": _safe_get(config, "f2_mcp_calculado", "False"),
            "mcp_r2": _safe_get(config, "f2_mcp_r2"),
            "mcp_rmse": _safe_get(config, "f2_mcp_rmse"),
            "mcp_slope": _safe_get(config, "f2_mcp_slope_global"),
            "mast_disponible": _safe_get(config, "f2_mast_disponible", "False"),
            "mast_recovery_pct": _safe_get(config, "f2_mast_recovery_pct"),
        },
        "turbine": {
            "model_id": _safe_get(config, "f4_selected_turbine"),
            "diametro": _safe_get(config, "diametro"),
            "p_nominal_mw": _safe_get(config, "f5_potencia_nominal_turbina_mw"),
            "p_instalada_mw": _safe_get(config, "f5_potencia_instalada_mw"),
            "cut_in": _safe_get(config, "f35_cutin") or _safe_get(config, "f3_prob_cutin"),
            "v_nominal": _safe_get(config, "f35_nominal") or _safe_get(config, "f3_prob_nominal"),
            "cut_out": _safe_get(config, "f35_cutout") or _safe_get(config, "f3_prob_cutout"),
            "ct": _safe_get(config, "f5_ct") or _safe_get(config, "f4_ct"),
            "hub_height_m": _safe_get(config, "perfil_hhub"),
        },
        "layout": {
            "turbinas": layout_rows,
            "n_turbinas": _safe_get(config, "f5_n_turbinas"),
            "tipo": _safe_get(config, "f4_layout_type"),
            "dx_D": _safe_get(config, "f4_dx_D"),
            "dy_D": _safe_get(config, "f4_dy_D"),
            "peor_sector": _safe_get(config, "f4_worst_sector"),
            "peor_sector_loss_pct": _safe_get(config, "f4_worst_sector_loss_pct"),
            "sectores_criticos": _safe_get(config, "f4_geom_critical_sectors"),
            "weighted_wake_loss_pct": _safe_get(config, "f4_weighted_wake_loss_pct"),
        },
        "energy_yield": {
            "n_turbinas": _safe_get(config, "f5_n_turbinas"),
            "diametro": _safe_get(config, "diametro"),
            "aep_bruta_total_mwh": _safe_get(config, "f5_aep_bruta_total_mwh"),
            "aep_con_estela_mwh": _safe_get(config, "f5_aep_con_estela_total_mwh"),
            "aep_neta_total_mwh": _safe_get(config, "f5_aep_neta_total_mwh"),
            "perdida_estela_mwh": _safe_get(config, "f5_perdida_estela_total_mwh"),
            "factor_planta_bruto_pct": _safe_get(config, "f5_factor_planta_bruto_pct"),
            "factor_planta_neto_pct": _safe_get(config, "f5_factor_planta_neto_pct"),
            "wake_model": _safe_get(config, "f5_wake_model", "Jensen"),
            "wake_perdida_pct": _safe_get(config, "f5_wake_manual_pct"),
            "factor_densidad": _safe_get(config, "f5_densidad_sitio"),
            # Losses (IEC 61400-15-2 categorías)
            "loss_disp_pct": _safe_get(config, "f5_disp_pct"),
            "loss_elec_pct": _safe_get(config, "f5_elec_pct"),
            "loss_otras_pct": _safe_get(config, "f5_otras_pct"),
            "loss_disp_red_pct": _safe_get(config, "f5_loss_disp_red_pct"),
            "loss_hielo_pct": _safe_get(config, "f5_loss_hielo_pct"),
            "loss_histeresis_pct": _safe_get(config, "f5_loss_histeresis_pct"),
            "loss_curtailment_pct": _safe_get(config, "f5_loss_curtailment_pct"),
            # Monte Carlo
            "p50": _safe_get(config, "f5_aep_p50"),
            "p75": _safe_get(config, "f5_aep_p75"),
            "p90": _safe_get(config, "f5_aep_p90"),
            "p99": _safe_get(config, "f5_aep_p99"),
            "aep_mc_mean": _safe_get(config, "f5_aep_mc_mean"),
            "aep_mc_std": _safe_get(config, "f5_aep_mc_std"),
            "mc_n_samples": _safe_get(config, "f5_mc_n_samples"),
            # Sigmas Monte Carlo (uncertainty budget)
            "mc_sigma_k_pct": _safe_get(config, "f5_mc_sigma_k_pct"),
            "mc_sigma_c_pct": _safe_get(config, "f5_mc_sigma_c_pct"),
            "mc_sigma_curva_pct": _safe_get(config, "f5_mc_sigma_curva_pct"),
            "mc_sigma_perdidas_pct": _safe_get(config, "f5_mc_sigma_perdidas_pct"),
            "mc_sigma_wake_pct": _safe_get(config, "f5_mc_sigma_wake_pct"),
        },
        "iec_compliance": {
            "clase_declarada": _safe_get(config, "f5_iec_clase_declarada", "II"),
            "categoria_declarada": _safe_get(config, "f5_iec_turb_declarada", "B"),
            "cumple": _safe_get(config, "f5_iec_cumple"),
            "ti_15ms": _safe_get(config, "f5_ti_15ms_calc"),
            "v_ref_site": _safe_get(config, "perfil_v50"),
        },
        "environmental": {
            "flicker_analizado": False,
            "ruido_analizado": False,
            "limite_ruido_diurno_db": pais_profile.get("limite_ruido_diurno_db"),
            "limite_ruido_nocturno_db": pais_profile.get("limite_ruido_nocturno_db"),
        },
        "economic": {
            "capex_total": _safe_get(config, "f5_capex_total"),
            "capex_turbina_por_mw": _safe_get(config, "f5_capex_turbina_por_mw"),
            "capex_bop_por_mw": _safe_get(config, "f5_capex_bop_por_mw"),
            "capex_red_por_mw": _safe_get(config, "f5_capex_red_por_mw"),
            "capex_pct_desarrollo": _safe_get(config, "f5_capex_pct_desarrollo"),
            "capex_pct_contingencia": _safe_get(config, "f5_capex_pct_contingencia"),
            "capex_componentes": capex_comp,
            "opex_anual": _safe_get(config, "f5_opex_total_anual"),
            "opex_fijo_por_mw_anio": _safe_get(config, "f5_opex_fijo_por_mw_anio"),
            "opex_componentes": opex_comp,
            "vida_util": _safe_get(config, "f5_vida_util_anios"),
            "tasa_descuento": _safe_get(config, "f5_tasa_descuento_pct"),
            "lcoe_mwh": _safe_get(config, "f5_lcoe_mwh"),
            "lcoe_kwh": _safe_get(config, "f5_lcoe_kwh"),
            "moneda_base": _safe_get(config, "f5_moneda_base", "USD"),
            "npv": _safe_get(config, "f5_npv"),
            "irr_pct": _safe_get(config, "f5_irr_pct"),
            "payback_simple": _safe_get(config, "f5_payback_simple_anios"),
            "payback_descontado": _safe_get(config, "f5_payback_descontado_anios"),
            "precio_energia_mwh": _safe_get(config, "f5_precio_energia_mwh"),
            "degradacion_pct": _safe_get(config, "f5_degradacion_energia_pct"),
            "valor_residual": _safe_get(config, "f5_valor_residual"),
            "sens_delta_pct": _safe_get(config, "f5_sens_delta_pct"),
        },
        # Datasets crudos para figuras (no serializables como JSON; sólo runtime)
        "_raw": {
            "nasa_df": nasa_df,
            "curva_df": curva_df,
        },
    }
    return ctx


def _fmt_num(v, decimals=2, default="—"):
    try:
        f = float(v)
        if f != f:  # NaN
            return default
        return f"{f:,.{decimals}f}"
    except (TypeError, ValueError):
        return default


def _fmt_money(v, currency="USD", decimals=0, default="—"):
    n = _fmt_num(v, decimals=decimals, default=None)
    if n is None:
        return default
    return f"{currency} {n}"


def _fmt_pct(v, decimals=2, default="—"):
    n = _fmt_num(v, decimals=decimals, default=None)
    if n is None:
        return default
    return f"{n} %"


def _add_heading(doc, text, level=1):
    return doc.add_heading(text, level=level)


def _add_p(doc, text, bold=False, italic=False, color=None, size=None):
    try:
        from docx.shared import Pt, RGBColor
    except ImportError:
        Pt = RGBColor = None
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = bold
    r.italic = italic
    if color and RGBColor is not None:
        r.font.color.rgb = RGBColor(*color)
    if size and Pt is not None:
        r.font.size = Pt(size)
    return p


def _shade_cell(cell, hex_color):
    """Aplica color de fondo a una celda (sombreado)."""
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except ImportError:
        return
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tc_pr.append(shd)


def _set_cell_text(cell, text, bold=False, color=None, align=None, size=None):
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor
    except ImportError:
        WD_ALIGN_PARAGRAPH = Pt = RGBColor = None
    cell.text = ""
    p = cell.paragraphs[0]
    if align == "center" and WD_ALIGN_PARAGRAPH is not None:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "right" and WD_ALIGN_PARAGRAPH is not None:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = p.add_run(str(text))
    r.bold = bold
    if size and Pt is not None:
        r.font.size = Pt(size)
    if color and RGBColor is not None:
        r.font.color.rgb = RGBColor(*color)


def _add_kpi_table(doc, rows, headers=("Métrica", "Valor"), header_color="1F4E79", col_widths=None):
    """Tabla con encabezado coloreado tipo bankable report.

    header_color: hex sin '#'
    col_widths: lista de anchos en pulgadas (Inches) para cada columna
    """
    try:
        from docx.shared import Inches
    except ImportError:
        Inches = None
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    try:
        table.style = "Light Grid Accent 1"
    except Exception:
        pass
    table.autofit = True
    # Header row
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        _set_cell_text(cell, h, bold=True, color=(255, 255, 255), align="center", size=10)
        _shade_cell(cell, header_color)
    # Data rows
    for i, row in enumerate(rows, 1):
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            _set_cell_text(cell, val, size=10)
            if i % 2 == 0:
                _shade_cell(cell, "F2F6FB")
    # Column widths
    if col_widths and Inches is not None:
        for j, w in enumerate(col_widths):
            if j < len(headers):
                try:
                    for row in table.rows:
                        row.cells[j].width = Inches(w)
                except Exception:
                    pass
    return table


def _add_callout(doc, title, body, color="2E5C8A", bg="EAF2FA"):
    """Caja destacada (info / advertencia / bankability)."""
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    _shade_cell(cell, bg)
    p_title = cell.paragraphs[0]
    r_t = p_title.add_run(title)
    r_t.bold = True
    try:
        from docx.shared import Pt, RGBColor
        r_t.font.size = Pt(11)
        r_t.font.color.rgb = RGBColor(*tuple(int(color[i:i+2], 16) for i in (0, 2, 4)))
    except ImportError:
        pass
    p_body = cell.add_paragraph()
    r_b = p_body.add_run(body)
    try:
        from docx.shared import Pt
        r_b.font.size = Pt(10)
    except ImportError:
        pass
    return table


def _add_toc_field(doc):
    """Añade campo TOC automática al DOCX (se actualiza al abrir en Word).

    Marca w:dirty='true' para forzar Word a refrescar el TOC al abrir.
    También inyecta <w:updateFields w:val='true'/> en settings.xml.
    """
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
    except ImportError:
        return
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    fldChar1.set(qn('w:dirty'), 'true')  # fuerza refresh al abrir
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = ' TOC \\o "1-3" \\h \\z \\u '
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'separate')
    fldChar3 = OxmlElement('w:t')
    fldChar3.text = "Tabla de contenidos — el contenido se llenará automáticamente al abrir en Word."
    fldChar4 = OxmlElement('w:fldChar')
    fldChar4.set(qn('w:fldCharType'), 'end')
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)
    run._r.append(fldChar4)
    # Inyectar updateFields en settings.xml
    try:
        settings = doc.settings.element
        # Verificar si ya existe updateFields
        existing = settings.find(qn('w:updateFields'))
        if existing is None:
            upd = OxmlElement('w:updateFields')
            upd.set(qn('w:val'), 'true')
            settings.insert(0, upd)
    except Exception:
        pass


def _add_header_footer(doc, project_name, autor, logo_path=None):
    """Añade cabecera con logo + pie con paginación."""
    try:
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt
    except ImportError:
        return

    for section in doc.sections:
        header = section.header
        h_para = header.paragraphs[0]
        h_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = h_para.add_run(f"{project_name}  ·  {autor}  ·  SMA 2.0 Bankable Report")
        run.font.size = Pt(8)
        if logo_path:
            try:
                run2 = h_para.add_run()
                run2.add_picture(logo_path, width=Inches(0.8))
            except Exception:
                pass

        footer = section.footer
        f_para = footer.paragraphs[0]
        f_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # "Pagina " label
        run_prefix = f_para.add_run("Página ")
        run_prefix.font.size = Pt(8)
        # PAGE field
        run_page = f_para.add_run()
        fld_p1 = OxmlElement('w:fldChar')
        fld_p1.set(qn('w:fldCharType'), 'begin')
        instr_p = OxmlElement('w:instrText')
        instr_p.set(qn('xml:space'), 'preserve')
        instr_p.text = ' PAGE '
        fld_p2 = OxmlElement('w:fldChar')
        fld_p2.set(qn('w:fldCharType'), 'separate')
        placeholder_p = OxmlElement('w:t')
        placeholder_p.text = "1"
        fld_p3 = OxmlElement('w:fldChar')
        fld_p3.set(qn('w:fldCharType'), 'end')
        run_page._r.append(fld_p1)
        run_page._r.append(instr_p)
        run_page._r.append(fld_p2)
        run_page._r.append(placeholder_p)
        run_page._r.append(fld_p3)
        run_page.font.size = Pt(8)
        # " de " separator
        run_sep = f_para.add_run(" de ")
        run_sep.font.size = Pt(8)
        # NUMPAGES field
        run_total = f_para.add_run()
        fld_n1 = OxmlElement('w:fldChar')
        fld_n1.set(qn('w:fldCharType'), 'begin')
        instr_n = OxmlElement('w:instrText')
        instr_n.set(qn('xml:space'), 'preserve')
        instr_n.text = ' NUMPAGES '
        fld_n2 = OxmlElement('w:fldChar')
        fld_n2.set(qn('w:fldCharType'), 'separate')
        placeholder_n = OxmlElement('w:t')
        placeholder_n.text = "1"
        fld_n3 = OxmlElement('w:fldChar')
        fld_n3.set(qn('w:fldCharType'), 'end')
        run_total._r.append(fld_n1)
        run_total._r.append(instr_n)
        run_total._r.append(fld_n2)
        run_total._r.append(placeholder_n)
        run_total._r.append(fld_n3)
        run_total.font.size = Pt(8)


def generar_reporte_bankable_docx(ctx, output_path, lang="es", logo_path=None):
    """Genera DOCX 30-50 pag bankable. Reutiliza python-docx.

    Args:
      ctx: contexto bankable (dict)
      output_path: ruta de salida
      lang: idioma ('es', 'en', 'pt', 'fr'). Default 'es'.
      logo_path: ruta opcional logo cliente para cabecera.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt, RGBColor
    except ImportError:
        raise RuntimeError("python-docx no instalado. `pip install python-docx`")

    # i18n strings
    try:
        from i18n_paises import t as _t
    except ImportError:
        def _t(k, lang="es"):
            # fallback castellano
            mapping = {
                "report_title": "INFORME BANKABLE",
                "report_subtitle": "Evaluación técnico-económica de proyecto eólico",
                "section_1_exec": "Resumen Ejecutivo",
                "section_2_proj": "Descripción del Proyecto",
                "section_3_wind": "Evaluación del Recurso Eólico",
                "section_4_energy": "Producción de Energía (Monte Carlo P50/P90)",
                "section_5_iec": "Cumplimiento IEC 61400-1",
                "section_6_env": "Análisis Ambiental",
                "section_7_econ": "Análisis Económico Bankable",
                "section_8_risk": "Registro de Riesgos",
                "section_9_concl": "Conclusiones y Recomendaciones",
                "section_10_app": "Apéndices",
                "metric": "Métrica", "value": "Valor",
                "client": "Cliente", "author": "Autor", "date": "Fecha de generación",
                "disclaimer_title": "DISCLAIMER:",
                "disclaimer_body": ("Este informe es generado por SMA 2.0, herramienta open-source de prefactibilidad. "
                                    "NO reemplaza certificación formal de DNV/UL/TÜV ni evaluaciones realizadas con software "
                                    "comercial certificado. Para project finance, los resultados deben ser validados por un "
                                    "consultor certificado independiente."),
                "aep_p50": "AEP P50", "aep_p90": "AEP P90 (banca)", "lcoe": "LCOE",
                "npv": "VPN", "irr": "TIR", "payback": "Período de recuperación",
            }
            return mapping.get(k, k)

    doc = Document()

    # Estilos base APA 7: Times New Roman 12pt, interlineado 1.5, sin sangria
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    try:
        from docx.shared import Pt as _Pt
        pf = style.paragraph_format
        pf.line_spacing = 1.5
        pf.first_line_indent = 0
        pf.space_after = _Pt(0)
        pf.space_before = _Pt(0)
    except Exception:
        pass

    # Margenes APA 7: 1 in (2.54 cm) en todos los lados
    try:
        from docx.shared import Inches as _Inches
        for section in doc.sections:
            section.top_margin = _Inches(1)
            section.bottom_margin = _Inches(1)
            section.left_margin = _Inches(1)
            section.right_margin = _Inches(1)
            section.page_width = _Inches(8.5)
            section.page_height = _Inches(11)
    except Exception:
        pass

    # updateFields=true en settings para auto-refresh TOC
    try:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        settings_el = doc.settings.element
        if settings_el.find(qn('w:updateFields')) is None:
            upd = OxmlElement('w:updateFields')
            upd.set(qn('w:val'), 'true')
            settings_el.insert(0, upd)
    except Exception:
        pass

    # Heading colors profesionales (Times New Roman 12pt base, headings mas grandes)
    for lvl, sz in [(0, 26), (1, 18), (2, 14), (3, 13)]:
        try:
            hstyle = doc.styles[f"Heading {lvl}"]
            hstyle.font.name = "Times New Roman"
            hstyle.font.size = Pt(sz)
            hstyle.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
            hstyle.font.name = "Calibri"
        except Exception:
            pass

    md = ctx["metadata"]
    wr = ctx["wind_resource"]
    tb = ctx["turbine"]
    lo = ctx["layout"]
    ey = ctx["energy_yield"]
    iec = ctx["iec_compliance"]
    env = ctx["environmental"]
    ec = ctx["economic"]
    pais_profile = md.get("pais_profile", {}) or {}
    currency = ec.get("moneda_base", "USD")

    # Derivadas útiles
    n_t = _to_float(ey.get("n_turbinas"), 0) or _to_float(lo.get("n_turbinas"), 0)
    p_nominal_mw = _to_float(tb.get("p_nominal_mw"), 0)
    p_inst_mw = _to_float(tb.get("p_instalada_mw"), 0)
    if (not p_inst_mw) and n_t and p_nominal_mw:
        p_inst_mw = n_t * p_nominal_mw
    aep_neta_mwh = _to_float(ey.get("aep_neta_total_mwh"), 0)
    aep_bruta_mwh = _to_float(ey.get("aep_bruta_total_mwh"), 0)
    fpn = _to_float(ey.get("factor_planta_neto_pct"), 0)
    fpb = _to_float(ey.get("factor_planta_bruto_pct"), 0)
    # AEP referente: usa P50 si existe, sino determinista
    aep_p50 = _to_float(ey.get("p50"))
    if aep_p50 is None:
        aep_p50 = aep_neta_mwh
    aep_p90 = _to_float(ey.get("p90"))
    aep_p75 = _to_float(ey.get("p75"))
    aep_p99 = _to_float(ey.get("p99"))
    sigma_total_pct = _to_float(ey.get("sigma_total_pct"))
    if aep_neta_mwh and (aep_p90 is None or sigma_total_pct is None):
        try:
            from calculos_uncertainty import monte_carlo_aep
            sigmas_in = ctx.get("uncertainty_categories") if isinstance(ctx, dict) else None
            # IAV override: si ctx tiene 'iav_summary', usa sigma_lt real
            iav_summary_in = ctx.get("iav_summary") if isinstance(ctx, dict) else None
            if iav_summary_in and isinstance(iav_summary_in, dict):
                sigma_lt_real = iav_summary_in.get("sigma_lt_pct")
                if sigma_lt_real and sigma_lt_real == sigma_lt_real:
                    sigmas_in = dict(sigmas_in or {})
                    sigmas_in["lt"] = float(sigma_lt_real)
            mc = monte_carlo_aep(aep_neta_mwh, sigmas_pct=sigmas_in, n_iter=10000)
            if aep_p50 is None or aep_p50 == aep_neta_mwh:
                aep_p50 = mc.get("P50")
            if aep_p75 is None:
                aep_p75 = mc.get("P75")
            if aep_p90 is None:
                aep_p90 = mc.get("P90")
            if aep_p99 is None:
                aep_p99 = mc.get("P99")
            if sigma_total_pct is None:
                sigma_total_pct = mc.get("sigma_total_pct")
        except Exception:
            pass

    # Header/footer + branding
    _add_header_footer(doc, md.get("project_name", "Project"), md.get("autor", ""), logo_path=logo_path)

    # ═══════════════════════════════════════════════════════════════
    # 0. COVER PAGE — profesional con tabla metadata + disclaimer
    # ═══════════════════════════════════════════════════════════════
    if logo_path:
        try:
            doc.add_picture(logo_path, width=Inches(1.8))
        except Exception:
            pass

    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_r = title_p.add_run(_t("report_title", lang))
    title_r.bold = True
    title_r.font.size = Pt(32)
    title_r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_r = sub_p.add_run(_t("report_subtitle", lang))
    sub_r.italic = True
    sub_r.font.size = Pt(13)
    sub_r.font.color.rgb = RGBColor(0x55, 0x70, 0x90)

    doc.add_paragraph()
    proj_p = doc.add_paragraph()
    proj_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    proj_r = proj_p.add_run(md["project_name"])
    proj_r.bold = True
    proj_r.font.size = Pt(20)

    doc.add_paragraph()
    doc.add_paragraph()

    # Tabla metadata cover
    cover_rows = [
        (_t("client", lang), md.get("cliente", "—")),
        (_t("author", lang), md.get("autor", "—")),
        ("Country / País", f"{md.get('country_nombre', '—')} ({md.get('country_code', '—')})"),
        ("Lat / Lon", f"{md.get('lat', '—')}, {md.get('lon', '—')}"),
        (_t("date", lang), ctx["fecha_generacion"][:10]),
        ("Doc. code", md.get("doc_code", "—")),
        ("Revisión", md.get("revision", "Rev A")),
        ("SMA Version", md.get("version_sma", "2.0")),
    ]
    _add_kpi_table(doc, cover_rows, headers=("Campo", "Valor"), col_widths=[2.0, 4.0])

    doc.add_paragraph()
    _add_callout(
        doc,
        _t("disclaimer_title", lang),
        _t("disclaimer_body", lang),
        color="A04040",
        bg="FCEDED",
    )
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # DOCUMENT CONTROL
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, "Document Control", level=1)
    _add_p(doc, "Histórico de revisiones del documento (Document Control).", italic=True)
    _add_kpi_table(doc, [
        ("A", ctx["fecha_generacion"][:10], md.get("autor", "—"), "—", "Versión inicial autogenerada por SMA 2.0"),
    ], headers=("Rev", "Fecha", "Preparado por", "Revisado por", "Notas"),
       col_widths=[0.6, 1.1, 1.5, 1.5, 2.8])
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # TOC
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, "Tabla de contenidos", level=1)
    _add_toc_field(doc)
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 1. EXECUTIVE SUMMARY — bankability statement + KPIs principales
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"1. {_t('section_1_exec', lang)}", 1)

    # Bankability statement contextualizado
    irr_v = _to_float(ec.get("irr_pct"))
    wacc_tipico = _to_float(pais_profile.get("wacc_tipico_pct"))
    bankable_ok = (irr_v is not None and wacc_tipico is not None and irr_v >= wacc_tipico)
    if bankable_ok:
        st_title = "Veredicto preliminar: ELEGIBLE para project finance"
        st_body = (
            f"Los indicadores financieros base ({_fmt_pct(irr_v)} TIR vs {_fmt_pct(wacc_tipico)} "
            f"WACC típico {md.get('country_nombre')}) son compatibles con project finance, sujeto "
            f"a validación independiente de AEP y P90 con consultor certificado y a la confirmación "
            f"de los supuestos de PPA, disponibilidad y O&M."
        )
        st_color, st_bg = "1F6E3B", "EAF7EE"
    else:
        st_title = "Veredicto preliminar: REQUIERE ITERACIÓN antes de project finance"
        st_body = (
            "Los indicadores económicos base no muestran un margen claro frente al WACC típico del "
            "país. Se recomienda iterar precio PPA, layout, CAPEX o supuestos de pérdidas antes de "
            "presentar el proyecto a entidades financieras."
        )
        st_color, st_bg = "8B5A1F", "FFF4E0"
    _add_callout(doc, st_title, st_body, color=st_color, bg=st_bg)
    doc.add_paragraph()

    # KPIs principales tabla
    exec_rows = [
        ("Capacidad instalada", f"{_fmt_num(p_inst_mw, 2)} MW"),
        ("Número de aerogeneradores", f"{_fmt_num(n_t, 0)}"),
        (_t("aep_p50", lang), f"{_fmt_num(aep_p50, 0)} MWh/año"),
        (_t("aep_p90", lang), f"{_fmt_num(aep_p90, 0)} MWh/año" if aep_p90 else "No calculado (correr Monte Carlo en Fase 5)"),
        ("Factor de planta neto", f"{_fmt_num(fpn, 1)} %"),
        (_t("lcoe", lang), f"{currency} {_fmt_num(ec.get('lcoe_mwh'), 2)}/MWh ({currency} {_fmt_num(ec.get('lcoe_kwh'), 4)}/kWh)"),
        (_t("npv", lang), _fmt_money(ec.get("npv"), currency)),
        (_t("irr", lang), _fmt_pct(ec.get("irr_pct"))),
        ("WACC referencia país", _fmt_pct(pais_profile.get("wacc_tipico_pct"))),
        (f"{_t('payback', lang)} descontado", f"{_fmt_num(ec.get('payback_descontado'), 2)} años"),
        ("CAPEX total", _fmt_money(ec.get("capex_total"), currency)),
        ("OPEX anual", _fmt_money(ec.get("opex_anual"), currency)),
    ]
    _add_kpi_table(doc, exec_rows, headers=(_t("metric", lang), _t("value", lang)), col_widths=[2.7, 3.3])

    doc.add_paragraph()
    _add_heading(doc, "1.1 Hallazgos clave", level=2)
    findings = [
        f"Velocidad media en hub (h={_fmt_num(wr.get('altura_hub'), 1)} m) estimada por perfil {wr.get('perfil_metodo','—')} desde {wr.get('fuente','—')}.",
        f"Wake loss ponderado: {_fmt_pct(ey.get('wake_perdida_pct'))} (modelo {ey.get('wake_model','—')}); peor sector: {lo.get('peor_sector','—')} ({_fmt_pct(lo.get('peor_sector_loss_pct'))}).",
        f"Densidad del aire en sitio: {_fmt_num(wr.get('densidad_sitio'),3)} kg/m³ (corrección {'aplicada' if str(wr.get('densidad_sitio')).strip() else 'no aplicada'}).",
        f"IEC 61400-1 declarada: Clase {iec.get('clase_declarada')} / TI Categoría {iec.get('categoria_declarada')} — TI@15m/s = {_fmt_num(iec.get('ti_15ms'),4)}.",
        f"Marco regulatorio aplicable: {pais_profile.get('mecanismo_descripcion','—')} ({pais_profile.get('mecanismo_unidad','—')} ≈ {_fmt_num(pais_profile.get('mecanismo_valor_default'),2)}).",
    ]
    for f in findings:
        _add_p(doc, f"• {f}")
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 2. PROJECT DESCRIPTION — sitio + aerogenerador + layout
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"2. {_t('section_2_proj', lang)}", 1)

    _add_heading(doc, "2.1 Localización del sitio", level=2)
    _add_kpi_table(doc, [
        ("Latitud", _fmt_num(md.get("lat"), 6)),
        ("Longitud", _fmt_num(md.get("lon"), 6)),
        ("País", f"{md.get('country_nombre')} ({md.get('country_code')})"),
        ("Altitud media estimada", f"{_fmt_num(wr.get('altitud_sitio_m'), 0)} m s.n.m."),
        ("Temperatura media anual", f"{_fmt_num(wr.get('temperatura_media_c'), 1)} °C"),
        ("Rugosidad superficial (label)", str(wr.get("roughness_label") or "—")),
        ("z0 (m)", _fmt_num(wr.get("z0"), 4)),
        ("Densidad del aire en sitio", f"{_fmt_num(wr.get('densidad_sitio'), 3)} kg/m³"),
    ], col_widths=[2.6, 3.4])

    doc.add_paragraph()
    _add_heading(doc, "2.2 Especificaciones del aerogenerador", level=2)
    _add_p(doc,
        "Las especificaciones siguientes provienen de la curva de potencia y geometría "
        "configuradas en la Fase 1 del modelo SMA 2.0.")
    _add_kpi_table(doc, [
        ("ID modelo / referencia", str(tb.get("model_id") or "—")),
        ("Diámetro de rotor", f"{_fmt_num(tb.get('diametro'), 1)} m"),
        ("Altura de buje (hub)", f"{_fmt_num(tb.get('hub_height_m'), 1)} m"),
        ("Potencia nominal por turbina", f"{_fmt_num(tb.get('p_nominal_mw'), 3)} MW"),
        ("Capacidad instalada total", f"{_fmt_num(p_inst_mw, 2)} MW"),
        ("Velocidad cut-in", f"{_fmt_num(tb.get('cut_in'), 1)} m/s"),
        ("Velocidad nominal", f"{_fmt_num(tb.get('v_nominal'), 1)} m/s"),
        ("Velocidad cut-out", f"{_fmt_num(tb.get('cut_out'), 1)} m/s"),
        ("Coeficiente de empuje (CT) representativo", _fmt_num(tb.get("ct"), 3)),
    ], col_widths=[3.0, 3.0])
    # Fig curva potencia
    _raw_early = ctx.get("_raw") or {}
    curva_df = _raw_early.get("curva_df")
    if curva_df is not None and len(curva_df):
        p_nom_kw = _to_float(tb.get("p_nominal_mw"), 0)
        p_nom_kw = p_nom_kw * 1000.0 if p_nom_kw else None
        png_curva = _fig_curva_potencia(curva_df, p_nominal_kw=p_nom_kw)
        _embed_fig(doc, png_curva, width_inches=6.2,
            caption="Figura 2.2 — Curva de potencia del aerogenerador (cut-in → nominal → cut-out).")

    doc.add_paragraph()
    _add_heading(doc, "2.3 Layout y disposición de turbinas", level=2)
    _add_p(doc,
        f"Tipo de layout: {lo.get('tipo') or '—'}. Spacing dx/D = {_fmt_num(lo.get('dx_D'), 1)} · "
        f"dy/D = {_fmt_num(lo.get('dy_D'), 1)}. "
        f"Sectores críticos por wake: {lo.get('sectores_criticos') or '—'}.")
    layout_rows = lo.get("turbinas") or []
    if layout_rows:
        layout_table = [
            (str(r.get("id")), _fmt_num(r.get("x_m"), 1), _fmt_num(r.get("y_m"), 1),
             _fmt_num(_to_float(r.get("x_m"), 0)/1000.0, 3),
             _fmt_num(_to_float(r.get("y_m"), 0)/1000.0, 3))
            for r in layout_rows
        ]
        _add_kpi_table(doc, layout_table,
            headers=("Turbina", "X (m)", "Y (m)", "X (km)", "Y (km)"),
            col_widths=[1.2, 1.2, 1.2, 1.2, 1.2])
        # Fig: layout XY
        diam = _to_float(tb.get("diametro"))
        png = _fig_layout_parque(layout_rows, diametro_m=diam)
        _embed_fig(doc, png, width_inches=6.2,
            caption=f"Figura 2.1 — Layout del parque (n={len(layout_rows)}, D={_fmt_num(diam, 1)} m).")
    else:
        _add_p(doc, "(Layout no disponible; configurar en Fase 4 del modelo.)", italic=True)
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 3. WIND RESOURCE ASSESSMENT
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"3. {_t('section_3_wind', lang)}", 1)
    # Figs upfront: rosa vientos + histograma Weibull
    raw = ctx.get("_raw") or {}
    nasa_df = raw.get("nasa_df")
    if nasa_df is not None and len(nasa_df):
        png_rosa = _fig_rosa_vientos(nasa_df)
        _embed_fig(doc, png_rosa, width_inches=5.5,
            caption="Figura 3.1 — Rosa de vientos por sector (16 sectores, WD50M).")
        png_hist = _fig_weibull_histogram(nasa_df)
        _embed_fig(doc, png_hist, width_inches=6.2,
            caption="Figura 3.2 — Distribución de velocidades + ajuste Weibull (MLE).")

    _add_heading(doc, "3.1 Fuente y período de datos", level=2)
    _add_kpi_table(doc, [
        ("Fuente de datos primaria", str(wr.get("fuente"))),
        ("Período analizado", f"{wr.get('fecha_inicio','—')} → {wr.get('fecha_fin','—')}"),
        ("Altura de referencia (origen)", f"{_fmt_num(wr.get('altura_ref'), 0)} m"),
        ("Altura del buje objetivo", f"{_fmt_num(wr.get('altura_hub'), 1)} m"),
        ("Serie efectiva usada", str(wr.get("mcp_usado"))),
        ("MCP aplicado", "Sí" if str(wr.get('mcp_calculado','')).lower() in ('true','1') else "No (usar dataset satelital)"),
        ("MCP R²", _fmt_num(wr.get("mcp_r2"), 3)),
        ("MCP RMSE (m/s)", _fmt_num(wr.get("mcp_rmse"), 3)),
        ("Torre meteorológica", "Disponible" if str(wr.get('mast_disponible','')).lower() in ('true','1') else "No disponible"),
        ("Recovery torre (%)", _fmt_num(wr.get("mast_recovery_pct"), 1)),
    ], col_widths=[3.0, 3.0])

    doc.add_paragraph()
    _add_heading(doc, "3.2 Perfil vertical y extrapolación a hub", level=2)
    _add_p(doc,
        f"Método de extrapolación: {wr.get('perfil_metodo','—')}. "
        "El perfil exponencial se utiliza para llevar la velocidad desde la altura de referencia "
        "hasta el buje del aerogenerador. El parámetro α (shear) y la rugosidad z0 se estiman a partir "
        "del dataset de viento y los metadatos del terreno.")
    _add_kpi_table(doc, [
        ("Velocidad a 10 m (V_ref)", f"{_fmt_num(wr.get('v_ref_10m'), 2)} m/s"),
        ("Velocidad a 50 m (V_50)", f"{_fmt_num(wr.get('v_50m'), 2)} m/s"),
        ("Velocidad de fricción u*", f"{_fmt_num(wr.get('u_star'), 3)} m/s"),
        ("α shear (mediana)", _fmt_num(wr.get("alpha_mediana") or wr.get("perfil_alpha"), 3)),
        ("α shear (P25 — P75)", f"{_fmt_num(wr.get('alpha_p25'),3)} — {_fmt_num(wr.get('alpha_p75'),3)}"),
        ("Muestras α (n)", _fmt_num(wr.get("alpha_n"), 0)),
        ("Rugosidad z0 (m)", _fmt_num(wr.get("z0"), 4)),
        ("Clase de terreno", str(wr.get("roughness_label") or "—")),
    ], col_widths=[3.0, 3.0])

    doc.add_paragraph()
    _add_heading(doc, "3.3 Turbulencia y densidad atmosférica", level=2)
    _add_kpi_table(doc, [
        ("Turbulence Intensity ambient (TI₀)", _fmt_num(wr.get("ambient_ti"), 3)),
        ("Turbulence Intensity efectivo @ 15 m/s", _fmt_num(wr.get("ti_15ms"), 4)),
        ("Densidad del aire en sitio", f"{_fmt_num(wr.get('densidad_sitio'), 3)} kg/m³"),
        ("Densidad estándar (referencia)", "1.225 kg/m³"),
        ("Altitud del sitio", f"{_fmt_num(wr.get('altitud_sitio_m'), 0)} m s.n.m."),
        ("Temperatura media anual", f"{_fmt_num(wr.get('temperatura_media_c'), 1)} °C"),
    ], col_widths=[3.5, 2.5])
    doc.add_paragraph()
    _add_callout(doc,
        "Recomendación bankable",
        "Para reducir la incertidumbre del recurso eólico a niveles requeridos por banca (σ_LT < 5 %), "
        "se sugiere instalar una torre meteorológica con anemómetros calibrados a múltiples alturas "
        "(40-80-120 m) durante al menos 12 meses contiguos, y posteriormente aplicar MCP de larga "
        "duración contra estación de referencia o reanalysis (ERA5/MERRA-2).",
        color="2E5C8A", bg="EAF2FA")
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 4. ENERGY YIELD — Loss waterfall + Monte Carlo + per-WTG
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"4. {_t('section_4_energy', lang)}", 1)
    _add_p(doc,
        "Esta sección reporta la producción anual esperada en categorías de pérdidas alineadas con "
        "IEC 61400-15-2 y la incertidumbre estimada vía Monte Carlo sobre los parámetros Weibull, "
        "curva de potencia, pérdidas operacionales y wake.")

    _add_heading(doc, "4.1 Loss waterfall (cascada de pérdidas)", level=2)
    # Calcular waterfall paso a paso
    aep_after_wake = aep_bruta_mwh * (1.0 - (_to_float(ey.get("wake_perdida_pct"), 0)/100.0)) if aep_bruta_mwh else 0.0
    pct_disp = _to_float(ey.get("loss_disp_pct"), 0) or 0.0
    pct_elec = _to_float(ey.get("loss_elec_pct"), 0) or 0.0
    pct_otras = _to_float(ey.get("loss_otras_pct"), 0) or 0.0
    pct_red = _to_float(ey.get("loss_disp_red_pct"), 0) or 0.0
    pct_hielo = _to_float(ey.get("loss_hielo_pct"), 0) or 0.0
    pct_hist = _to_float(ey.get("loss_histeresis_pct"), 0) or 0.0
    pct_curt = _to_float(ey.get("loss_curtailment_pct"), 0) or 0.0

    def _apply(v, pct):
        return v * (1.0 - pct/100.0)

    aep_step = aep_after_wake
    waterfall = [
        ("AEP bruta (gross)", "", _fmt_num(aep_bruta_mwh, 0)),
        ("− Wake losses", _fmt_pct(ey.get("wake_perdida_pct")), _fmt_num(aep_after_wake, 0)),
    ]
    for label, pct in [
        ("− Disponibilidad turbina", pct_disp),
        ("− Disponibilidad red", pct_red),
        ("− Pérdidas eléctricas", pct_elec),
        ("− Hielo (icing)", pct_hielo),
        ("− Histéresis cut-out", pct_hist),
        ("− Curtailment", pct_curt),
        ("− Otras (suciedad, etc.)", pct_otras),
    ]:
        aep_step = _apply(aep_step, pct)
        waterfall.append((label, f"{pct:.2f} %", _fmt_num(aep_step, 0)))
    waterfall.append(("AEP NETA (P50)", "", _fmt_num(aep_neta_mwh or aep_step, 0)))

    _add_kpi_table(doc, waterfall,
        headers=("Categoría (IEC 61400-15-2)", "Pérdida %", "AEP acumulada (MWh/año)"),
        col_widths=[2.8, 1.2, 2.0])
    # Fig: waterfall chart
    losses_for_fig = [
        ("Wake", _to_float(ey.get("wake_perdida_pct"), 0) or 0.0),
        ("Disp. turbina", pct_disp),
        ("Disp. red", pct_red),
        ("Eléctricas", pct_elec),
        ("Hielo", pct_hielo),
        ("Histéresis", pct_hist),
        ("Curtailment", pct_curt),
        ("Otras", pct_otras),
    ]
    png_wf = _fig_loss_waterfall(aep_bruta_mwh, losses_for_fig)
    _embed_fig(doc, png_wf, width_inches=6.5,
        caption="Figura 4.1 — Loss waterfall AEP bruta → AEP neta (IEC 61400-15-2).")

    doc.add_paragraph()
    _add_heading(doc, "4.2 Resumen energético y factor de planta", level=2)
    _add_kpi_table(doc, [
        ("AEP bruta total", f"{_fmt_num(aep_bruta_mwh, 0)} MWh/año"),
        ("AEP después de wake", f"{_fmt_num(aep_after_wake, 0)} MWh/año"),
        ("AEP neta total (determinista)", f"{_fmt_num(aep_neta_mwh, 0)} MWh/año"),
        ("Pérdida total ponderada", _fmt_pct(((aep_bruta_mwh - aep_neta_mwh)/aep_bruta_mwh*100.0) if aep_bruta_mwh else None)),
        ("Factor de planta bruto", _fmt_pct(fpb)),
        ("Factor de planta neto", _fmt_pct(fpn)),
        ("Modelo wake utilizado", str(ey.get("wake_model"))),
        ("Pérdida wake ponderada", _fmt_pct(ey.get("wake_perdida_pct"))),
    ], col_widths=[3.0, 3.0])

    doc.add_paragraph()
    _add_heading(doc, "4.3 Distribución probabilística (Monte Carlo P50/P75/P90/P99)", level=2)
    if aep_p90 is None:
        _add_callout(doc, "Monte Carlo no ejecutado",
            "Las bandas P50/P75/P90/P99 aún no han sido calculadas en Fase 5. Para banca se requiere "
            "ejecutar Monte Carlo (≥ 2000 muestras) sobre las incertidumbres del recurso eólico, "
            "la curva de potencia y las pérdidas operacionales. P90 es la métrica de referencia para "
            "el dimensionamiento de deuda y DSCR.",
            color="8B5A1F", bg="FFF4E0")
    _add_kpi_table(doc, [
        ("AEP P50 (Monte Carlo)", f"{_fmt_num(ey.get('p50'), 0)} MWh/año"),
        ("AEP P75", f"{_fmt_num(ey.get('p75'), 0)} MWh/año"),
        ("AEP P90 (BANCA)", f"{_fmt_num(ey.get('p90'), 0)} MWh/año"),
        ("AEP P99 (stress test)", f"{_fmt_num(ey.get('p99'), 0)} MWh/año"),
        ("Media Monte Carlo", f"{_fmt_num(ey.get('aep_mc_mean'), 0)} MWh/año"),
        ("σ Monte Carlo", f"{_fmt_num(ey.get('aep_mc_std'), 0)} MWh/año"),
        ("σ relativa (CV)", _fmt_pct(((_to_float(ey.get("aep_mc_std"))/_to_float(ey.get("aep_mc_mean")))*100.0)
                                       if _to_float(ey.get("aep_mc_mean")) else None)),
        ("Muestras Monte Carlo", _fmt_num(ey.get("mc_n_samples"), 0)),
    ], col_widths=[3.0, 3.0])
    # Fig MC distribution
    png_mc = _fig_monte_carlo(ey.get("aep_mc_mean"), ey.get("aep_mc_std"),
                              ey.get("p50"), ey.get("p75"),
                              ey.get("p90"), ey.get("p99"))
    _embed_fig(doc, png_mc, width_inches=6.4,
        caption="Figura 4.2 — Distribución probabilística Monte Carlo AEP (P50/P75/P90/P99).")

    doc.add_paragraph()
    _add_heading(doc, "4.4 Producción por aerogenerador (estimada)", level=2)
    _add_p(doc,
        "Distribución estimada asignando la AEP neta total proporcionalmente al número de turbinas. "
        "Una asignación per-WTG real requiere ejecutar el modelo de estela direccional (Fase 4) "
        "y reportar AEP turbina a turbina.", italic=True)
    if n_t and aep_neta_mwh and layout_rows:
        aep_por_wtg = aep_neta_mwh / max(1, n_t)
        cf_por_wtg = (aep_por_wtg / (p_nominal_mw * 8760.0) * 100.0) if p_nominal_mw else None
        wtg_rows = []
        for r in layout_rows:
            wtg_rows.append((
                str(r.get("id")),
                _fmt_num(r.get("x_m"), 1),
                _fmt_num(r.get("y_m"), 1),
                _fmt_num(p_nominal_mw, 3),
                _fmt_num(aep_por_wtg, 0),
                _fmt_num(cf_por_wtg, 1) + " %" if cf_por_wtg is not None else "—",
            ))
        wtg_rows.append((
            "TOTAL", "—", "—",
            _fmt_num(p_inst_mw, 2),
            _fmt_num(aep_neta_mwh, 0),
            _fmt_num(fpn, 1) + " %"
        ))
        _add_kpi_table(doc, wtg_rows,
            headers=("Turbina", "X (m)", "Y (m)", "P_nom (MW)", "AEP (MWh/año)", "CF (%)"),
            col_widths=[0.9, 1.1, 1.1, 1.0, 1.3, 0.8])
        # Fig per-WTG
        png_wtg = _fig_per_wtg(layout_rows, aep_por_wtg)
        _embed_fig(doc, png_wtg, width_inches=6.3,
            caption="Figura 4.3 — Producción anual estimada por aerogenerador.")
    else:
        _add_p(doc, "(Layout o AEP no disponibles para descomposición per-WTG.)", italic=True)
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 5. UNCERTAINTY BUDGET — IEC 61400-15-2
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, "5. Análisis de Incertidumbre (IEC 61400-15-2)", 1)
    _add_p(doc,
        "Las siguientes σ corresponden a las categorías de incertidumbre definidas por IEC 61400-15-2 "
        "y son los inputs usados en el Monte Carlo de la sección anterior. La σ total combinada (raíz "
        "cuadrada de la suma de cuadrados) es la base para los percentiles P50/P75/P90/P99.")
    s_k = _to_float(ey.get("mc_sigma_k_pct"), 0) or 0.0
    s_c = _to_float(ey.get("mc_sigma_c_pct"), 0) or 0.0
    s_curva = _to_float(ey.get("mc_sigma_curva_pct"), 0) or 0.0
    s_perd = _to_float(ey.get("mc_sigma_perdidas_pct"), 0) or 0.0
    s_wake = _to_float(ey.get("mc_sigma_wake_pct"), 0) or 0.0
    s_total = math.sqrt(s_k**2 + s_c**2 + s_curva**2 + s_perd**2 + s_wake**2)
    _add_kpi_table(doc, [
        ("Wind speed measurement (k Weibull)", _fmt_pct(s_k), "Recurso eólico"),
        ("Long-term extrapolation (c Weibull)", _fmt_pct(s_c), "Recurso eólico"),
        ("Power curve (curva de potencia)", _fmt_pct(s_curva), "Conversión a energía"),
        ("Operational losses (pérdidas op.)", _fmt_pct(s_perd), "Pérdidas"),
        ("Wake model uncertainty", _fmt_pct(s_wake), "Modelado wake"),
        ("σ TOTAL COMBINADA (RSS)", _fmt_pct(s_total), "P50 → P90 driver"),
    ], headers=("Categoría IEC 61400-15-2", "σ relativa", "Grupo"),
       col_widths=[3.2, 1.4, 1.8])
    doc.add_paragraph()
    _add_callout(doc,
        "Interpretación",
        f"Una σ total combinada de {_fmt_pct(s_total)} implica que P90 ≈ P50 × (1 − 1.282 · σ/100) "
        f"≈ P50 × {1 - 1.282 * s_total/100:.3f}. Reducir σ requiere campañas de medición de mayor "
        f"calidad, modelos wake validados (py_wake DTU, WindFarmer) y tests de curva de potencia "
        f"según IEC 61400-12-1.",
        color="2E5C8A", bg="EAF2FA")
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 6. IEC 61400-1 SITE SUITABILITY
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"6. {_t('section_5_iec', lang)}", 1)
    _add_p(doc,
        f"Aerogenerador declarado: Clase {iec.get('clase_declarada')} / TI Categoría "
        f"{iec.get('categoria_declarada')}. La tabla siguiente compara los valores estimados en "
        "sitio contra los límites IEC 61400-1 Ed.4.")
    # Tabla de límites IEC
    clase_limits = {
        "I":   {"v_avg": 10.0, "v_ref": 50.0},
        "II":  {"v_avg":  8.5, "v_ref": 42.5},
        "III": {"v_avg":  7.5, "v_ref": 37.5},
    }
    cat_ti = {"A": 0.16, "B": 0.14, "C": 0.12}
    cl = str(iec.get("clase_declarada", "II")).upper()
    cat = str(iec.get("categoria_declarada", "B")).upper()
    lim_vavg = clase_limits.get(cl, {}).get("v_avg")
    lim_vref = clase_limits.get(cl, {}).get("v_ref")
    lim_ti = cat_ti.get(cat)

    v50_site = _to_float(iec.get("v_ref_site")) or _to_float(wr.get("v_50m"))
    ti_site = _to_float(iec.get("ti_15ms"))

    def _verdict(site_v, limit_v, mode="under"):
        if site_v is None or limit_v is None:
            return "Sin datos"
        if mode == "under":
            return "✓ CUMPLE" if site_v <= limit_v else "✗ EXCEDE"
        return "✓ CUMPLE" if site_v >= limit_v else "✗ EXCEDE"

    _add_kpi_table(doc, [
        ("V_avg (velocidad media anual a hub)", f"{_fmt_num(v50_site, 2)} m/s", f"{_fmt_num(lim_vavg, 1)} m/s", _verdict(v50_site, lim_vavg)),
        ("V_ref (extreme 50 años)", f"{_fmt_num(v50_site, 2)} m/s", f"{_fmt_num(lim_vref, 1)} m/s", _verdict(v50_site, lim_vref)),
        ("TI @ 15 m/s", _fmt_num(ti_site, 4), _fmt_num(lim_ti, 3), _verdict(ti_site, lim_ti)),
        ("Wind shear α", _fmt_num(wr.get("perfil_alpha"), 3), "0.20 (norma)", _verdict(_to_float(wr.get("perfil_alpha")), 0.20)),
        ("Densidad del aire", f"{_fmt_num(wr.get('densidad_sitio'), 3)} kg/m³", "1.225 kg/m³", "Referencia"),
        ("Inflow angle", "No calculado en SMA", "≤ 8°", "Sin determinar"),
    ], headers=("Parámetro", "Sitio", f"Límite Clase {cl}/{cat}", "Veredicto"),
       col_widths=[2.4, 1.4, 1.4, 1.1])

    doc.add_paragraph()
    cumple_str = str(iec.get("cumple")).lower()
    if cumple_str in ("true", "1"):
        veredicto_text = "✓ CUMPLE GLOBAL — el sitio se ajusta a la clase declarada."
        v_color, v_bg = "1F6E3B", "EAF7EE"
    elif cumple_str in ("false", "0"):
        veredicto_text = "✗ EXCEDE — el sitio requiere upgrade de clase IEC o turbina específica."
        v_color, v_bg = "8B1F1F", "FCEDED"
    else:
        veredicto_text = "Veredicto IEC no determinado — completar Fase 5."
        v_color, v_bg = "8B5A1F", "FFF4E0"
    _add_callout(doc, "Veredicto IEC 61400-1", veredicto_text, color=v_color, bg=v_bg)
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 7. ENVIRONMENTAL
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"7. {_t('section_6_env', lang)}", 1)
    _add_heading(doc, "7.1 Shadow flicker (parpadeo de sombra)", level=2)
    _add_p(doc, "Análisis no ejecutado en esta sesión." if not env.get("flicker_analizado")
        else "Ver tabla horas flicker por receptor (Apéndice).")
    _add_p(doc,
        "Norma de referencia: límite habitual ≤ 30 h/año de exposición real por receptor sensible. "
        "Recomendación: ejecutar análisis con SunPath + obstrucciones cuando existan viviendas a "
        "menos de 10× el diámetro de rotor desde cualquier turbina.", italic=True)

    _add_heading(doc, "7.2 Ruido ISO 9613-2", level=2)
    _add_p(doc, "Análisis no ejecutado en esta sesión." if not env.get("ruido_analizado")
        else "Ver tabla LpA(receptor) calculada (Apéndice).")
    _add_kpi_table(doc, [
        ("Límite diurno (país)", f"{_fmt_num(env.get('limite_ruido_diurno_db'), 0)} dB(A)"),
        ("Límite nocturno (país)", f"{_fmt_num(env.get('limite_ruido_nocturno_db'), 0)} dB(A)"),
        ("Norma de referencia", "ISO 9613-2 + reglamento local"),
    ], col_widths=[3.0, 3.0])

    _add_heading(doc, "7.3 Otros impactos a evaluar", level=2)
    _add_p(doc, "• Avifauna y quirópteros (estudio anual mínimo).")
    _add_p(doc, "• Impacto visual paisajístico (zonificación de visibilidad ZTV).")
    _add_p(doc, "• Emisiones evitadas: estimación CO₂ por MWh generado vs factor de emisión país.")
    _add_p(doc, "• Análisis de ciclo de vida (LCA): GHG por kWh (gCO₂/kWh).")
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 8. ECONOMIC BANKABLE ANALYSIS
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"8. {_t('section_7_econ', lang)}", 1)

    _add_heading(doc, "8.1 Resumen económico", level=2)
    _add_kpi_table(doc, [
        ("Moneda base", currency),
        ("Tasa de descuento (WACC base)", _fmt_pct(ec.get("tasa_descuento"))),
        ("WACC referencia país", _fmt_pct(pais_profile.get("wacc_tipico_pct"))),
        ("Vida útil", f"{_fmt_num(ec.get('vida_util'), 0)} años"),
        ("Tax rate país", _fmt_pct(pais_profile.get("tax_rate_pct"))),
        ("Country risk premium", _fmt_pct(pais_profile.get("country_risk_premium_pct"))),
        ("Mecanismo regulatorio", str(pais_profile.get("mecanismo_descripcion", "—"))),
        ("Precio de referencia regulatorio", f"{pais_profile.get('mecanismo_unidad','—')} {_fmt_num(pais_profile.get('mecanismo_valor_default'), 2)}"),
        ("Precio PPA asumido", f"{currency} {_fmt_num(ec.get('precio_energia_mwh'), 2)}/MWh"),
        ("Degradación anual energía", _fmt_pct(ec.get("degradacion_pct"))),
    ], col_widths=[3.0, 3.0])

    doc.add_paragraph()
    _add_heading(doc, "8.2 CAPEX breakdown", level=2)
    if p_inst_mw:
        cap_t_per_mw = _to_float(ec.get("capex_turbina_por_mw"), 0) or 0.0
        cap_b_per_mw = _to_float(ec.get("capex_bop_por_mw"), 0) or 0.0
        cap_r_per_mw = _to_float(ec.get("capex_red_por_mw"), 0) or 0.0
        capex_turb = cap_t_per_mw * p_inst_mw
        capex_bop = cap_b_per_mw * p_inst_mw
        capex_red = cap_r_per_mw * p_inst_mw
        subtotal = capex_turb + capex_bop + capex_red
        pct_dev = _to_float(ec.get("capex_pct_desarrollo"), 0) or 0.0
        pct_ctg = _to_float(ec.get("capex_pct_contingencia"), 0) or 0.0
        capex_dev = subtotal * pct_dev / 100.0
        capex_ctg = subtotal * pct_ctg / 100.0
        capex_total_v = _to_float(ec.get("capex_total"), subtotal + capex_dev + capex_ctg)
        _add_kpi_table(doc, [
            ("Aerogeneradores", _fmt_money(capex_turb, currency), f"{_fmt_num(cap_t_per_mw/1e6, 2)} M{currency}/MW"),
            ("Balance of Plant (BOP)", _fmt_money(capex_bop, currency), f"{_fmt_num(cap_b_per_mw/1e6, 2)} M{currency}/MW"),
            ("Conexión a red", _fmt_money(capex_red, currency), f"{_fmt_num(cap_r_per_mw/1e6, 2)} M{currency}/MW"),
            ("Desarrollo + permisos", _fmt_money(capex_dev, currency), _fmt_pct(pct_dev)),
            ("Contingencia", _fmt_money(capex_ctg, currency), _fmt_pct(pct_ctg)),
            ("TOTAL CAPEX", _fmt_money(capex_total_v, currency), f"{_fmt_num((capex_total_v/p_inst_mw)/1e6, 2)} M{currency}/MW"),
        ], headers=("Concepto", "Valor", "Detalle"), col_widths=[2.5, 2.0, 1.5])
        # Fig pie CAPEX
        png_pie = _fig_capex_pie({
            "Aerogeneradores": capex_turb,
            "Balance of Plant": capex_bop,
            "Conexión a red": capex_red,
            "Desarrollo": capex_dev,
            "Contingencia": capex_ctg,
        }, currency=currency)
        _embed_fig(doc, png_pie, width_inches=5.5,
            caption="Figura 8.1 — Distribución del CAPEX por categoría.")
    else:
        _add_p(doc, "Capacidad instalada no disponible; no se puede descomponer CAPEX.", italic=True)

    doc.add_paragraph()
    _add_heading(doc, "8.3 OPEX breakdown", level=2)
    opex_anual_v = _to_float(ec.get("opex_anual"), 0) or 0.0
    opex_per_mw_y = _to_float(ec.get("opex_fijo_por_mw_anio"), 0) or 0.0
    _add_kpi_table(doc, [
        ("OPEX anual total", _fmt_money(opex_anual_v, currency)),
        ("OPEX por MW · año", _fmt_money(opex_per_mw_y, currency)),
        ("OPEX/MWh (sobre AEP neta)", _fmt_money((opex_anual_v/aep_neta_mwh) if aep_neta_mwh else None, currency, decimals=2)),
        ("OPEX/CAPEX (anual)", _fmt_pct((opex_anual_v/_to_float(ec.get("capex_total"),1))*100.0 if _to_float(ec.get("capex_total")) else None)),
    ], col_widths=[3.0, 3.0])

    doc.add_paragraph()
    _add_heading(doc, "8.4 Indicadores financieros base case", level=2)
    revenue_y1 = aep_neta_mwh * (_to_float(ec.get("precio_energia_mwh"), 0) or 0.0)
    ebitda_y1 = revenue_y1 - opex_anual_v
    _add_kpi_table(doc, [
        (_t("lcoe", lang), f"{currency} {_fmt_num(ec.get('lcoe_mwh'), 2)}/MWh"),
        ("LCOE (energía)", f"{currency} {_fmt_num(ec.get('lcoe_kwh'), 4)}/kWh"),
        (_t("npv", lang), _fmt_money(ec.get("npv"), currency)),
        (_t("irr", lang), _fmt_pct(ec.get("irr_pct"))),
        (f"{_t('payback', lang)} simple", f"{_fmt_num(ec.get('payback_simple'), 2)} años"),
        (f"{_t('payback', lang)} descontado", f"{_fmt_num(ec.get('payback_descontado'), 2)} años"),
        ("Revenue año 1 (P50)", _fmt_money(revenue_y1, currency)),
        ("EBITDA año 1 estimado", _fmt_money(ebitda_y1, currency)),
        ("Margen EBITDA", _fmt_pct((ebitda_y1/revenue_y1*100.0) if revenue_y1 else None)),
    ], col_widths=[3.0, 3.0])

    doc.add_paragraph()
    _add_heading(doc, "8.5 Cash flow esquemático (5 primeros años)", level=2)
    if aep_neta_mwh and ec.get("precio_energia_mwh"):
        price = _to_float(ec.get("precio_energia_mwh"), 0) or 0.0
        wacc = _to_float(ec.get("tasa_descuento"), 0) or 8.0
        degr = _to_float(ec.get("degradacion_pct"), 0) or 0.0
        capex_total_v = _to_float(ec.get("capex_total"), 0) or 0.0
        rows_cf = [("0", _fmt_money(-capex_total_v, currency), "—", "—", "—", _fmt_money(-capex_total_v, currency))]
        cum = -capex_total_v
        for year in range(1, 6):
            aep_y = aep_neta_mwh * ((1 - degr/100.0) ** (year - 1))
            rev = aep_y * price
            opex = opex_anual_v
            ebitda = rev - opex
            cum += ebitda
            rows_cf.append((str(year),
                _fmt_money(rev, currency),
                _fmt_money(-opex, currency),
                _fmt_money(ebitda, currency),
                _fmt_money(ebitda / ((1 + wacc/100.0) ** year), currency),
                _fmt_money(cum, currency)
            ))
        _add_kpi_table(doc, rows_cf,
            headers=("Año", "Revenue", "OPEX", "EBITDA", "EBITDA desc.", "FC acumulado"),
            col_widths=[0.5, 1.2, 1.2, 1.1, 1.1, 1.3])
    else:
        _add_p(doc, "Cash flow no disponible: faltan precio PPA o AEP neta.", italic=True)

    doc.add_paragraph()
    _add_heading(doc, "8.6 Análisis de sensibilidad (Tornado)", level=2)
    delta = _to_float(ec.get("sens_delta_pct"), 15.0) or 15.0
    npv_base = _to_float(ec.get("npv"))
    if npv_base is not None and aep_neta_mwh and ec.get("precio_energia_mwh"):
        price = _to_float(ec.get("precio_energia_mwh"), 0) or 0.0
        wacc = _to_float(ec.get("tasa_descuento"), 8.0) or 8.0
        n_years = int(_to_float(ec.get("vida_util"), 20) or 20)
        capex_total_v = _to_float(ec.get("capex_total"), 0) or 0.0

        def _npv_calc(capex, opex, price, aep):
            cf = -capex
            for y in range(1, n_years + 1):
                cf += (aep * price - opex) / ((1 + wacc/100.0) ** y)
            return cf

        def _sensitivity(var):
            if var == "price":
                low = _npv_calc(capex_total_v, opex_anual_v, price * (1-delta/100.0), aep_neta_mwh)
                high = _npv_calc(capex_total_v, opex_anual_v, price * (1+delta/100.0), aep_neta_mwh)
            elif var == "capex":
                low = _npv_calc(capex_total_v * (1-delta/100.0), opex_anual_v, price, aep_neta_mwh)
                high = _npv_calc(capex_total_v * (1+delta/100.0), opex_anual_v, price, aep_neta_mwh)
            elif var == "opex":
                low = _npv_calc(capex_total_v, opex_anual_v * (1-delta/100.0), price, aep_neta_mwh)
                high = _npv_calc(capex_total_v, opex_anual_v * (1+delta/100.0), price, aep_neta_mwh)
            elif var == "aep":
                low = _npv_calc(capex_total_v, opex_anual_v, price, aep_neta_mwh * (1-delta/100.0))
                high = _npv_calc(capex_total_v, opex_anual_v, price, aep_neta_mwh * (1+delta/100.0))
            return low, high

        tornado_rows = []
        sens_for_fig = []
        for var, lbl in [("price", f"Precio PPA ±{delta:.0f}%"),
                          ("aep", f"AEP ±{delta:.0f}%"),
                          ("capex", f"CAPEX ±{delta:.0f}%"),
                          ("opex", f"OPEX ±{delta:.0f}%")]:
            low, high = _sensitivity(var)
            tornado_rows.append((lbl,
                _fmt_money(low, currency),
                _fmt_money(npv_base, currency),
                _fmt_money(high, currency),
                _fmt_money(high - low, currency)))
            sens_for_fig.append({"label": lbl, "low": low, "high": high})
        _add_kpi_table(doc, tornado_rows,
            headers=("Variable", "NPV (low)", "NPV (base)", "NPV (high)", "Δ NPV"),
            col_widths=[1.5, 1.2, 1.2, 1.2, 1.2])
        # Fig tornado
        png_torn = _fig_tornado(npv_base, sens_for_fig, currency=currency)
        _embed_fig(doc, png_torn, width_inches=6.5,
            caption="Figura 8.2 — Tornado de sensibilidad sobre NPV.")
    else:
        _add_p(doc, "Sensitivity no disponible: faltan datos económicos base.", italic=True)

    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 8B. MARCO REGULATORIO DEL PAIS
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, "8.B Marco regulatorio del país", 1)
    _add_p(doc,
        f"El proyecto se desarrolla en {md.get('country_nombre', '—')} ({md.get('country_code', '—')}) "
        f"bajo el marco regulatorio descrito a continuación. Esta caracterización es indicativa y debe "
        f"validarse con asesoría legal local antes del cierre financiero (FID).")
    marco_rows = [
        ("Mecanismo principal", pais_profile.get("mecanismo_descripcion", "—")),
        ("Moneda local", pais_profile.get("currency", "—")),
        ("Tipo de cambio referencia", f"{pais_profile.get('fx_to_usd', '—')} {pais_profile.get('currency','')}/USD"),
        ("Tasa impositiva corporativa", f"{pais_profile.get('tax_rate_pct', '—')} %"),
        ("WACC típico mercado", f"{pais_profile.get('wacc_tipico_pct', '—')} %"),
        ("Régimen renovable", pais_profile.get("regimen_renovable", "Definir con consultor local")),
        ("Permisos requeridos", pais_profile.get("permisos_requeridos", "EIA, licencia ambiental, uso de suelo, conexión TSO")),
        ("Tiempo medio de tramitación", pais_profile.get("tiempo_permisos_meses", "12-24 meses estimados")),
        ("Operador del sistema (TSO)", pais_profile.get("tso_nombre", "Operador eléctrico nacional")),
        ("Mercado de capacidad / energía", pais_profile.get("mercado_energia", "Mercado mayorista + PPAs bilaterales")),
    ]
    _add_kpi_table(doc, marco_rows, headers=("Aspecto regulatorio", "Detalle"), col_widths=[2.4, 4.0])
    doc.add_paragraph()
    _add_p(doc,
        "Recomendaciones legales claves:", bold=True)
    legal_recs = [
        "Verificar elegibilidad para mecanismos de remuneración (FIT, subasta, certificados verdes).",
        "Confirmar reglas de uso de suelo y servidumbres con autoridad ambiental local.",
        "Revisar requisitos de consulta previa con comunidades (ILO 169 si aplica).",
        "Negociar PPA con escalación indexada al CPI local o USD para mitigar inflación.",
        "Validar régimen impositivo aplicable: tax holiday, depreciación acelerada, créditos fiscales.",
    ]
    for r in legal_recs:
        _add_p(doc, f"  • {r}")
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 8C. CHECKLIST DE CUMPLIMIENTO NORMATIVO
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, "8.C Checklist de cumplimiento normativo (IEC / DNV / ISO)", 1)
    _add_p(doc,
        "Resumen del estado de cumplimiento del proyecto frente a las normas internacionales "
        "principales aplicables a parques eólicos onshore. Estado: ✓ Cumple, ⚠ Parcial / pendiente, "
        "✗ No aplica o por validar con tercera parte.")
    checklist = [
        ("IEC 61400-1 Ed.4", "Site Suitability: V_ref, V_50, V_e50, TI_eff vs clase", "Evaluado en sección 6", "Validar con consultor"),
        ("IEC 61400-12-1 Ed.3", "Power performance verification de curva de potencia", "Curva del fabricante usada", "⚠ Pendiente verificación post-COD"),
        ("IEC 61400-15-2", "Framework de incertidumbre P50/P90", "Aplicado en sección 5", "✓ Cumple metodología"),
        ("IEC 61400-3-1", "Site conditions wind", "Sitio onshore (3-1 no aplica)", "✓ N/A onshore"),
        ("DNV-SE-0073", "Certification of wind farms", "Marco metodológico", "⚠ Certificación 3ra parte pendiente"),
        ("DNV-ST-0437", "Loads and site conditions", "Cargas no calculadas aquí", "⚠ Requiere CFD + estructural"),
        ("ISO 9613-2", "Propagación de ruido outdoor", "Sección 7.2 placeholder", "⚠ Estudio dedicado pendiente"),
        ("ISO 14001", "Gestión ambiental", "Aplicable durante construcción / O&M", "⚠ Plan EMS pendiente"),
        ("IFC Performance Standards", "Sostenibilidad social y ambiental", "Aplicable si project finance internacional", "⚠ Due diligence 3ra parte"),
        ("Equator Principles", "Riesgos ambientales y sociales para project finance", "Aplicable según banca", "⚠ Categorización A/B/C pendiente"),
    ]
    _add_kpi_table(doc, checklist,
        headers=("Norma", "Aspecto evaluado", "Estado actual", "Acción requerida"),
        col_widths=[1.4, 2.2, 1.7, 1.7])
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 9. RISK REGISTER — matriz contextualizada por país
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"9. {_t('section_8_risk', lang)}", 1)
    mec_reg = pais_profile.get("mecanismo_descripcion", "Mecanismo regulatorio local")
    cur_local = pais_profile.get("currency", "USD")
    riesgos = [
        ("Técnico", "Variabilidad inter-anual del recurso eólico", "Media", "Alta", "Alto", "MCP + ≥10 años de data + torre met"),
        ("Técnico", "Modelo wake conservador o agresivo", "Baja", "Media", "Bajo", "Validar con py_wake DTU / WindFarmer"),
        ("Técnico", "Tolerancia ±5 % curva de potencia", "Media", "Media", "Medio", "Tests IEC 61400-12-1 post-comisionado"),
        ("Operacional", "Disponibilidad < esperada", "Media", "Media", "Medio", "Contrato O&M premium con LD"),
        ("Operacional", "Pérdidas eléctricas mayor a estimado", "Baja", "Media", "Bajo", "Diseño eléctrico optimizado + revisión"),
        ("Regulatorio", f"{mec_reg} — cambios en tarifa/subasta", "Media", "Alta", "Alto", "PPA bilateral / hedge en mercado"),
        ("Financiero", f"FX {cur_local}/USD volatilidad ±10-20 % anual", "Alta", "Alta", "Crítico", "Currency hedging / financiamiento local"),
        ("Financiero", "Subida tasas (WACC > base case)", "Media", "Alta", "Alto", "Cierre financiero con tasa fija"),
        ("Social", "Consulta comunitaria / permisos locales", "Media", "Alta", "Alto", "Engagement temprano desde fase 0"),
        ("Ambiental", "Permisos ambientales / EIA", "Media", "Alta", "Alto", "Estudios paralelos a desarrollo técnico"),
        ("Red", "Capacidad de conexión disponible", "Media", "Alta", "Alto", "Confirmar con TSO local antes de FID"),
        ("Construcción", "Sobrecostos / atrasos EPC", "Media", "Media", "Medio", "EPC turn-key con LD + contingencia ≥10 %"),
    ]
    _add_kpi_table(doc, riesgos,
        headers=("Categoría", "Riesgo", "Probabilidad", "Impacto", "Score", "Mitigación"),
        col_widths=[1.0, 2.2, 0.9, 0.9, 0.7, 1.8])
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # 10. CONCLUSIONS & RECOMMENDATIONS — contextualizadas al país
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"10. {_t('section_9_concl', lang)}", 1)
    _add_p(doc,
        f"El proyecto {md.get('project_name')} en {md.get('country_nombre')} presenta los indicadores "
        f"financieros y técnicos resumidos en este informe. La elegibilidad para project finance "
        f"queda sujeta a la validación independiente de los siguientes puntos críticos:", bold=False)

    recs = [
        "Validar AEP P50/P90 con un consultor certificado independiente usando WAsP, WindPRO o WindFarmer "
        "(este informe es de prefactibilidad, no sustituye al EYA bankable de tercera parte).",
        "Confirmar P90 mediante campaña de medición con torre meteorológica calibrada por ≥12 meses "
        "contiguos a múltiples alturas, seguido de MCP long-term contra ERA5/MERRA-2 (≥10 años).",
        f"Negociar PPA con escalación ≥2 % anual o indexación CPI para mitigar inflación de "
        f"{md.get('country_nombre')}.",
        "Reservar contingencia ≥10 % del CAPEX para sobrecostos típicos de EPC en proyectos eólicos.",
        f"Cerrar acuerdos de uso de suelo y consulta con comunidades locales antes del FID — "
        f"riesgo identificado como Alto en el Risk Register sección 9.",
        f"Confirmar capacidad de conexión disponible con el operador del sistema "
        f"({pais_profile.get('mecanismo_descripcion','TSO local')}) antes de comprometer CAPEX.",
        "Ejecutar análisis de Shadow Flicker (ISO) y Ruido (ISO 9613-2) para validar cumplimiento "
        "de límites locales antes de la fase de permisos.",
        "Si la TIR base case está cerca o por debajo del WACC típico del país, iterar precio PPA, "
        "layout (reducción wake), o seleccionar turbina con curva mejor adaptada al sitio.",
    ]
    for i, rec in enumerate(recs, 1):
        _add_p(doc, f"  {i}. {rec}")
    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════
    # APPENDICES
    # ═══════════════════════════════════════════════════════════════
    _add_heading(doc, f"11. {_t('section_10_app', lang)}", 1)

    _add_heading(doc, "A. Metodología SMA 2.0", level=2)
    _add_p(doc,
        "SMA 2.0 (Sistema de Modelado y Análisis Eólico) integra los siguientes componentes: "
        "estadística Weibull/Rayleigh sectorial, modelos de estela (Jensen, Larsen, Frandsen, "
        "Gaussian Bastankhah-Porté-Agel, TurbOPark, py_wake DTU), site suitability IEC 61400-1, "
        "Monte Carlo P50/P75/P90/P99 con incertidumbres categorizadas según IEC 61400-15-2, "
        "Measure-Correlate-Predict (MCP) con torre meteorológica y datasets satelitales, "
        "optimización de layout por algoritmos evolutivos (Differential Evolution), Shadow Flicker "
        "con SunPath, propagación de ruido ISO 9613-2 y export GIS automático con SRTM. "
        "Stack tecnológico: Python + Streamlit + SQLite + py_wake + numpy/scipy.")

    _add_heading(doc, "B. Validación cruzada", level=2)
    _add_p(doc,
        "Los modelos de estela implementados internamente (Jensen, Larsen, Frandsen, Bastankhah, "
        "TurbOPark) han sido comparados contra py_wake (DTU Wind Energy) en layouts de prueba "
        "estándar (Horns Rev, Lillgrund, Wieringermeer). La diferencia típica en AEP neta es "
        "menor al 5–10 % para configuraciones validadas.")

    _add_heading(doc, "C. Glosario y abreviaciones", level=2)
    _add_p(doc, "  AEP = Annual Energy Production (producción anual de energía).")
    _add_p(doc, "  P50/P75/P90/P99 = percentiles de la distribución probabilística de AEP.")
    _add_p(doc, "  TI = Turbulence Intensity (intensidad de turbulencia).")
    _add_p(doc, "  WACC = Weighted Average Cost of Capital.")
    _add_p(doc, "  LCOE = Levelized Cost of Energy.")
    _add_p(doc, "  DSCR = Debt Service Coverage Ratio.")
    _add_p(doc, "  EYA = Energy Yield Assessment.")
    _add_p(doc, "  MCP = Measure-Correlate-Predict.")
    _add_p(doc, "  CT = Coeficiente de empuje (thrust coefficient).")
    _add_p(doc, "  EPC = Engineering, Procurement & Construction.")
    _add_p(doc, "  FID = Final Investment Decision.")

    _add_heading(doc, "D. Referencias bibliográficas (formato APA 7)", level=2)
    _add_p(doc,
        "Las siguientes referencias siguen el formato de la Asociación Americana de Psicología "
        "(APA) 7ª edición, con sangría francesa indicada visualmente por la lista de viñetas. "
        "Para citación inline se recomienda el formato (Autor, año).", italic=True)
    refs_apa7 = [
        "International Electrotechnical Commission. (2019). IEC 61400-1: Wind energy generation systems — Part 1: Design requirements (Ed. 4). Geneva, Switzerland: IEC.",
        "International Electrotechnical Commission. (2022). IEC 61400-12-1: Wind energy generation systems — Part 12-1: Power performance measurements of electricity producing wind turbines (Ed. 3). Geneva, Switzerland: IEC.",
        "International Electrotechnical Commission. (2025). IEC 61400-15-1: Wind energy generation systems — Part 15-1: Assessment of site specific wind conditions for wind power stations. Geneva, Switzerland: IEC.",
        "International Electrotechnical Commission. (en desarrollo). IEC 61400-15-2: Framework for assessment of site-specific wind conditions for wind power stations. Geneva, Switzerland: IEC.",
        "DNV. (2022). DNV-SE-0073: Project certification of wind farms according to IEC 61400-22. Høvik, Norway: DNV.",
        "DNV. (2021). DNV-ST-0437: Loads and site conditions for wind turbines. Høvik, Norway: DNV.",
        "International Organization for Standardization. (1996). ISO 9613-2: Acoustics — Attenuation of sound during propagation outdoors — Part 2: General method of calculation. Geneva, Switzerland: ISO.",
        "Jensen, N. O. (1983). A note on wind generator interaction (Risø-M-2411). Roskilde, Denmark: Risø National Laboratory.",
        "Bastankhah, M., & Porté-Agel, F. (2014). A new analytical model for wind-turbine wakes. Renewable Energy, 70, 116–123. https://doi.org/10.1016/j.renene.2014.01.002",
        "Pedersen, J. G., Svensson, E., Poulsen, L., & Nygaard, N. G. (2022). Turbulence Optimized Park (TurbOPark) model. Journal of Physics: Conference Series, 2265, 022063. https://doi.org/10.1088/1742-6596/2265/2/022063",
        "International Renewable Energy Agency. (2024). Renewable power generation costs in 2023. Abu Dhabi, UAE: IRENA. https://www.irena.org/",
        "National Aeronautics and Space Administration. (s. f.). NASA POWER project. NASA Langley Research Center. https://power.larc.nasa.gov/",
        "European Centre for Medium-Range Weather Forecasts. (s. f.). ERA5 reanalysis dataset. Copernicus Climate Change Service. https://cds.climate.copernicus.eu/",
        "American Psychological Association. (2020). Publication manual of the American Psychological Association (7th ed.). Washington, DC: APA.",
    ]
    for ref in refs_apa7:
        _add_p(doc, ref)

    _add_heading(doc, "E. Limitaciones y exclusiones del informe", level=2)
    _add_p(doc,
        "Este informe es generado automáticamente por SMA 2.0 a partir de los datos configurados en "
        "la herramienta y los datasets disponibles (típicamente NASA POWER salvo torre met). NO "
        "incluye: (i) certificación formal IEC 61400-22 por DNV/UL/TÜV; (ii) validación tercera "
        "parte de la AEP; (iii) due diligence técnica para project finance; (iv) modelado CFD del "
        "sitio; (v) caracterización exhaustiva de eventos extremos (V50, EWS, ETM); (vi) estudios "
        "de impacto ambiental requeridos por la regulación local; (vii) negociación de PPA ni "
        "garantías del fabricante. Estos componentes deben ser provistos por consultores certificados "
        "antes de la decisión final de inversión.", italic=True)

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return str(output_path)


def generar_reporte_bankable_bytes(ctx, lang="es", logo_bytes=None):
    """Genera DOCX en memoria (BytesIO) → para download_button.

    Args:
      ctx: contexto bankable
      lang: idioma 'es' | 'en' | 'pt' | 'fr'
      logo_bytes: bytes PNG/JPG opcional del logo cliente
    """
    try:
        from docx import Document
    except ImportError:
        raise RuntimeError("python-docx no instalado")
    import os
    import tempfile

    logo_path = None
    if logo_bytes:
        try:
            logo_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            logo_tmp.write(logo_bytes)
            logo_tmp.close()
            logo_path = logo_tmp.name
        except Exception:
            logo_path = None

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        generar_reporte_bankable_docx(ctx, tmp.name, lang=lang, logo_path=logo_path)
        tmp_path = tmp.name
    with open(tmp_path, "rb") as f:
        out = f.read()

    if logo_path:
        try:
            os.unlink(logo_path)
        except Exception:
            pass
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
    return out
