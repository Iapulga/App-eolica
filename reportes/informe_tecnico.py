"""Informe técnico por fases (Word / PDF).

Documento técnico-descriptivo del proyecto ACTIVO. Cada fase se documenta con las mismas funciones
y parámetros que usa la app (curva y Cp de la Fase 1, perfiles de la Fase 2, rosa y Weibull de la
Fase 3, probabilidades de la Fase 3.5, estelas de la Fase 4 y AEP de la Fase 5), de modo que las
cifras coinciden con lo que se ve en pantalla. Números en formato español (1.234,56).
"""
from math import pi

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .datos_proyecto import construir_datos_exportacion, fmt_coord, fmt_num, fmt_pct, num
from .docx import load_informe_tecnico_master_docx
from .figuras import (
    _analyze_geometry_all_sectors,
    _build_probability_heatmap,
    _col,
    _create_phase4_annual_rose,
    _create_phase4_energy_bars,
    _create_phase4_geom_vs_annual,
    _create_phase4_geometric_rose,
    analisis_anual_fase4,
    build_site_map_bundle,
    export_plotly_figure_artifact,
)
from .texto import normalize_text_deep

try:
    from calculos import ROUGHNESS_OPTIONS_DEFAULT as ROUGHNESS_OPTIONS
except Exception:  # pragma: no cover
    ROUGHNESS_OPTIONS = {
        "Water / Mar": 2e-4, "Snow / Nieve": 1e-3, "Grass / Césped": 0.03,
        "Farmland / Cultivo": 0.10, "Forest / Bosque": 0.80, "City / Ciudad": 1.00,
    }

_DIRECCIONES = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
_ATRIBUCION_OSM = "Mapa base © colaboradores de OpenStreetMap (openstreetmap.org/copyright)."


# ─────────────────────────────────────────────────────────────
# Bloques
# ─────────────────────────────────────────────────────────────
def _tabla(titulo, descripcion, headers, filas, familia="compact_summary", nota=None):
    bloque = {
        "type": "table", "title": titulo, "description": descripcion, "headers": list(headers),
        "rows": [["—" if c is None else str(c) for c in fila] for fila in filas], "table_family": familia,
    }
    if nota:
        bloque["note"] = nota
    return bloque


def _parrafo(texto):
    return {"type": "paragraph", "text": texto}


def _preparar_grafica(fig, ancho, alto, leyenda_horizontal=True):
    """Copia de la figura lista para Word: tamaño fijo, letra legible y separadores decimales en español."""
    if fig is None:
        return None
    from .estilo import recolorear_plotly, registrar_plantilla_plotly

    fig = recolorear_plotly(go.Figure(fig))
    # Estilo formal común (Calibri, azul marino, rejilla suave). Sin título interno: el título y el
    # rótulo «Figura N.» los pone el documento.
    fig.update_layout(width=int(ancho), height=int(alto), template=registrar_plantilla_plotly(),
                      margin=dict(l=70, r=40, t=50, b=70), separators=",.", title=None,
                      font=dict(family="Calibri, Segoe UI, Arial, sans-serif", size=15, color="#2B3645"))
    if leyenda_horizontal:
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5,
                                      bgcolor="rgba(255,255,255,0.88)"))
    fig.update_xaxes(showgrid=True, gridcolor="#E3E8EE", zeroline=False, showline=True, linecolor="#9AA5B1")
    fig.update_yaxes(showgrid=True, gridcolor="#E3E8EE", zeroline=False, showline=True, linecolor="#9AA5B1")
    return fig


def _figura(fig, fig_id, titulo, descripcion, stem, familia="", ancho=1100, alto=760):
    bloque = {"type": "figure", "title": titulo, "description": descripcion, "image_bytes": None,
              "image_format": None, "file_name": None, "figure_family": familia}
    if fig is None:
        return bloque
    image_bytes, meta = export_plotly_figure_artifact(
        fig=fig, figure_id=fig_id, title=titulo, stem=stem, source_hint=descripcion, preferred_format="png",
        export_options={"width": ancho, "height": alto, "max_dimension": 1900},
    )
    if image_bytes and str(meta.get("export_format") or "").lower() == "png":
        bloque.update({"image_bytes": image_bytes, "image_format": "png", "file_name": meta.get("file_name", f"{stem}.png")})
    return bloque


def _grilla_16_sectores(datos_sector, titulo, descripcion, stem, tipo="histograma"):
    """Grilla 4×4 (matplotlib) con histograma + ajustes Weibull/Rayleigh o curvas de probabilidad por sector."""
    try:
        import io

        from scipy import stats

        from .estilo import aplicar_estilo_mpl
    except ImportError:
        return None
    plt = aplicar_estilo_mpl()  # estilo formal común (Calibri, azul marino)
    fig, axes = plt.subplots(4, 4, figsize=(14, 12), dpi=130)
    axes = axes.flatten()
    por_sector = {d.get("sector"): d for d in datos_sector}
    for i, sec in enumerate(_DIRECCIONES):
        ax = axes[i]
        d = por_sector.get(sec)
        ax.set_title(sec, fontsize=11, fontweight="bold", color="#1B365D", loc="left")
        ax.tick_params(labelsize=8)
        ax.grid(True, color="#C9D2DC", linewidth=0.5)
        if not d:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", transform=ax.transAxes, fontsize=9, color="#6B7785")
            ax.set_xticks([])
            ax.set_yticks([])
            continue
        if tipo == "histograma":
            v = np.asarray(d.get("velocidades", []), dtype=float)
            v = v[np.isfinite(v) & (v >= 0)]
            if len(v) == 0:
                continue
            ax.hist(v, bins=20, density=True, color="#2F5F8F", alpha=0.4, edgecolor="white")
            x = np.linspace(0, max(v.max(), 1.0), 120)
            k, c, cr = d.get("k"), d.get("c"), d.get("c_rayleigh")
            if k and c:
                ax.plot(x, stats.weibull_min.pdf(x, k, scale=c), color="#1B365D", lw=1.7,
                        label=f"Weibull k={fmt_num(k, 2)} c={fmt_num(c, 2)}")
            if cr:
                ax.plot(x, stats.rayleigh.pdf(x, scale=cr / np.sqrt(2)), color="#1F7A6F", lw=1.4, ls="--",
                        label=f"Rayleigh c={fmt_num(cr, 2)}")
            ax.legend(fontsize=7, loc="upper right")
        else:
            x = np.asarray(d.get("x", []), dtype=float)
            ax.plot(x, d.get("y_weibull"), color="#1B365D", lw=1.7, label="Weibull")
            ax.plot(x, d.get("y_rayleigh"), color="#1F7A6F", lw=1.4, ls="--", label="Rayleigh")
            ax.set_ylabel("p(v)", fontsize=8)
            ax.legend(fontsize=7, loc="upper right")
        ax.set_xlabel("v (m/s)", fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    familia = "phase3_histogram_grid" if tipo == "histograma" else "phase35_probability_grid"
    return {"type": "figure", "title": titulo, "description": descripcion, "image_bytes": buf.getvalue(),
            "image_format": "png", "file_name": f"{stem}.png", "figure_family": familia}


def _seccion(sid, titulo, descripcion, subsecciones):
    subsecciones = [s for s in subsecciones if s and s.get("blocks")]
    if not subsecciones:
        return None
    return {"id": sid, "title": titulo, "description": descripcion, "subsections": subsecciones}


def _sub(sid, titulo, bloques):
    return {"id": sid, "title": titulo, "blocks": [b for b in bloques if b]}


# ─────────────────────────────────────────────────────────────
# Fase 1 — Aerogenerador
# ─────────────────────────────────────────────────────────────
def _seccion_fase1(config, datos, df_curva_raw):
    from calculos import calcular_cp, crear_grafica_curva, preparar_datos_curva

    t = datos["turbina"]
    diametro = t.get("diametro_m") or 100.0
    densidad = t.get("densidad_curva") or 1.225
    area = pi * (diametro / 2.0) ** 2
    curva = preparar_datos_curva(df_curva_raw) if df_curva_raw is not None else pd.DataFrame()
    curva = curva.copy() if curva is not None else pd.DataFrame()
    df_cp = calcular_cp(curva, densidad, area).copy() if len(curva) > 0 else pd.DataFrame()

    datos_basicos = _tabla(
        "Datos básicos del aerogenerador",
        "Parámetros geométricos y de desempeño definidos en la Fase 1.",
        ["Parámetro", "Valor"],
        [
            ["Modelo / referencia", t.get("modelo") or "Curva de potencia definida en la Fase 1"],
            ["Diámetro del rotor", f"{fmt_num(diametro, 1)} m"],
            ["Área barrida", f"{fmt_num(area, 0)} m²"],
            ["Altura de buje", f"{fmt_num(t.get('altura_buje_m'), 1)} m"],
            ["Potencia nominal", f"{fmt_num(t.get('p_nominal_kw'), 0)} kW"],
            ["Velocidad de arranque (cut-in)", f"{fmt_num(t.get('cut_in'), 1)} m/s"],
            ["Velocidad nominal", f"{fmt_num(t.get('v_nominal'), 1)} m/s"],
            ["Velocidad de parada (cut-out)", f"{fmt_num(t.get('cut_out'), 1)} m/s"],
            ["Densidad del aire de la curva", f"{fmt_num(densidad, 3)} kg/m³"],
        ],
    )
    tabla_curva = None
    if len(curva) > 0:
        tabla_curva = _tabla(
            "Curva de potencia", "Pares velocidad–potencia de la curva usada en todo el proyecto.",
            ["Velocidad (m/s)", "Potencia (kW)"],
            [[fmt_num(v, 1), fmt_num(p / 1000.0, 1)] for v, p in zip(curva["Velocidad_num"], curva["Potencia_W"], strict=False)],
            familia="split_horizontal",
        )
    figura_cp = None
    tabla_cp = None
    if len(df_cp) > 0:
        figura_cp = _figura(_preparar_grafica(crear_grafica_curva(df_cp), 1150, 700), "informe_tecnico_phase1_cp_curve",
                            "Curva de potencia y coeficiente Cp",
                            "Potencia eléctrica del aerogenerador y coeficiente de potencia Cp calculado con la densidad de la curva.",
                            "informe_tecnico_potencia_cp", ancho=1150, alto=700)
        filas = []
        for _, r in df_cp.iterrows():
            cp = num(r.get("Cp"))
            filas.append([fmt_num(r.get("Velocidad_num"), 1), fmt_num(num(r.get("Potencia_W"), 0) / 1000.0, 1),
                          fmt_num(num(r.get("P_viento_W"), 0) / 1000.0, 1), fmt_num(cp, 3) if cp is not None else "—"])
        tabla_cp = _tabla("Coeficiente de potencia (Cp)",
                          "Cp = potencia eléctrica / potencia del viento para cada velocidad de la curva.",
                          ["Velocidad (m/s)", "Potencia (kW)", "P. del viento (kW)", "Cp"], filas, familia="split_horizontal")
    return _seccion("fase1_aerogenerador", "Fase 1 – Aerogenerador",
                    "Aerogenerador seleccionado, su geometría y la curva de potencia que se usa en el resto del estudio.", [
                        _sub("f1_datos", "Datos básicos", [datos_basicos]),
                        _sub("f1_curva", "Curva de potencia", [tabla_curva]),
                        _sub("f1_cp", "Curva de potencia y Cp", [figura_cp, tabla_cp]),
                    ])


# ─────────────────────────────────────────────────────────────
# Fase 2 — Perfiles de viento
# ─────────────────────────────────────────────────────────────
def _figura_comparacion_perfiles(df_exp, df_log_a, df_log_b, altura, v_exp, v_log_a, v_log_b, puntos, eje="linear"):
    fig = go.Figure()
    for df_m, nombre, color, dash in [(df_exp, "Exponencial", "#3366ff", None),
                                      (df_log_a, "Logarítmico A (2 puntos)", "#ff5533", "dash"),
                                      (df_log_b, "Promedio Log-Exp", "#2ca25f", "dot")]:
        fig.add_trace(go.Scatter(x=df_m["Velocidad (m/s)"], y=df_m["Altura (m)"], mode="lines", name=nombre,
                                 line=dict(width=3, color=color, dash=dash)))
    fig.add_trace(go.Scatter(x=[p["velocidad"] for p in puntos], y=[p["altura"] for p in puntos], mode="markers",
                             name="Puntos medidos", marker=dict(size=10, color="black")))
    for v, nombre, color, simbolo in [(v_exp, "Buje · exponencial", "#3366ff", "circle"),
                                      (v_log_a, "Buje · log A", "#ff5533", "diamond"),
                                      (v_log_b, "Buje · promedio", "#2ca25f", "square")]:
        fig.add_trace(go.Scatter(x=[v], y=[altura], mode="markers", name=nombre, marker=dict(size=10, color=color, symbol=simbolo)))
    fig.add_hline(y=float(altura), line_dash="dot", line_color="gray")
    fig.update_layout(template="plotly_white", xaxis_title="Velocidad del viento (m/s)", yaxis_title="Altura (m)", title=None)
    if eje == "log":
        fig.update_yaxes(type="log")
    return fig


def _seccion_fase2(config, datos, df_nasa):
    if df_nasa is None or len(df_nasa) == 0:
        return None
    from calculos import (
        KAPPA,
        ajustar_logaritmico_dos_puntos,
        calcular_alpha_desde_dos_alturas,
        calcular_perfil_exponencial,
        calcular_perfil_logaritmico,
        crear_grafica_nasa_hourly,
        crear_grafica_perfil_individual,
        velocidad_logaritmica_en_altura,
    )

    df = df_nasa.copy()
    for col in ["WS10M", "WS50M", "WD10M", "WD50M"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    v10_s = df.get("WS10M", pd.Series(dtype=float)).dropna()
    v50_s = df.get("WS50M", pd.Series(dtype=float)).dropna()
    if len(v10_s) == 0 or len(v50_s) == 0:
        return None
    r = datos["recurso"]
    altura = datos["turbina"].get("altura_buje_m") or float(config.get("perfil_hhub") or 80.0)
    v10 = float(v10_s.mean())
    v50 = float(v50_s.mean())
    alpha = float(calcular_alpha_desde_dos_alturas(v10, 10.0, v50, 50.0))
    u_star, z0 = ajustar_logaritmico_dos_puntos(v10, 10.0, v50, 50.0, kappa=KAPPA)
    v_exp = float(v10 * (altura / 10.0) ** alpha)
    v_log_a = float(velocidad_logaritmica_en_altura(u_star, altura, z0, kappa=KAPPA))
    v_log_b = (v_exp + v_log_a) / 2.0
    alturas = np.linspace(10.0, max(float(altura), 80.0), 60)
    df_exp = calcular_perfil_exponencial(v10, 10.0, alpha, alturas)
    df_log_a = calcular_perfil_logaritmico(u_star, z0, alturas, kappa=KAPPA)
    df_log_b = df_exp.copy()
    df_log_b["Velocidad (m/s)"] = (df_exp["Velocidad (m/s)"].to_numpy(float) + df_log_a["Velocidad (m/s)"].to_numpy(float)) / 2.0
    puntos = [{"altura": 10.0, "velocidad": v10, "etiqueta": "WS10M"}, {"altura": 50.0, "velocidad": v50, "etiqueta": "WS50M"}]

    mapa = build_site_map_bundle(config=config, base_folder="04_Figuras_mapas")
    mapa_png = None
    for art in mapa.get("artifacts", []):
        if art.get("id") == "site_map" and art.get("export_format") == "png" and art.get("path"):
            mapa_png = mapa.get("files", {}).get(art.get("path"))
            break
    p = datos["proyecto"]
    bloques_ubicacion = [
        {"type": "figure", "title": "Mapa del sitio",
         "description": f"Ubicación seleccionada en la Fase 2. {_ATRIBUCION_OSM}",
         "image_bytes": mapa_png, "image_format": "png" if mapa_png else None,
         "file_name": "mapa_sitio.png" if mapa_png else None, "figure_family": "phase2_map"},
        _tabla("Ubicación y consulta de datos", "Coordenadas y período de la serie de viento usada para caracterizar el sitio.",
               ["Campo", "Valor"], [
                   ["Latitud", fmt_coord(p.get("lat"))], ["Longitud", fmt_coord(p.get("lon"))],
                   ["Fuente de datos", p.get("fuente")], ["Fecha inicial", p.get("inicio")], ["Fecha final", p.get("fin")],
               ]),
    ]
    resumen_horario = _tabla("Resumen de la serie horaria", "Estadísticos básicos de la serie guardada para el sitio.",
                             ["Concepto", "Valor"], [
                                 ["Registros horarios", fmt_num(len(df), 0)],
                                 ["Velocidad media a 10 m (WS10M)", f"{fmt_num(v10, 2)} m/s"],
                                 ["Velocidad media a 50 m (WS50M)", f"{fmt_num(v50, 2)} m/s"],
                             ])
    fig_serie = _preparar_grafica(crear_grafica_nasa_hourly(df), 1250, 620)
    if fig_serie is not None:
        fig_serie.update_xaxes(nticks=8, tickangle=0, rangeslider_visible=False)

    def _perfil(df_m, titulo_fig, nombre, v_obj, color, dash=None, eje="linear"):
        fig = crear_grafica_perfil_individual(df_m, titulo_fig, nombre, altura_objetivo=altura, v_objetivo=v_obj,
                                              color=color, dash=dash, yaxis_type=eje, puntos_medidos=puntos)
        fig = _preparar_grafica(fig, 880, 800)
        if eje == "log":
            fig.update_yaxes(type="log")
        return fig

    alpha_tabla = num(r.get("alpha"), alpha)
    tabla_perfiles = _tabla(
        "Resumen de perfiles verticales",
        "Parámetros de extrapolación y velocidades estimadas a la altura de buje con cada modelo.",
        ["Concepto", "Valor"], [
            ["Velocidad media a 10 m", f"{fmt_num(num(r.get('v10'), v10), 2)} m/s"],
            ["Velocidad media a 50 m", f"{fmt_num(num(r.get('v50'), v50), 2)} m/s"],
            ["Exponente de cizalladura α", fmt_num(alpha_tabla, 3)],
            ["Velocidad de fricción u* (log A)", f"{fmt_num(num(r.get('u_star'), float(u_star)), 3)} m/s"],
            ["Rugosidad z0 ajustada (log A)", f"{fmt_num(num(r.get('z0'), float(z0)), 4)} m"],
            [f"Velocidad a {fmt_num(altura, 0)} m · exponencial", f"{fmt_num(v_exp, 2)} m/s"],
            [f"Velocidad a {fmt_num(altura, 0)} m · logarítmico A", f"{fmt_num(v_log_a, 2)} m/s"],
            [f"Velocidad a {fmt_num(altura, 0)} m · promedio Log-Exp", f"{fmt_num(v_log_b, 2)} m/s"],
            ["Modelo usado para la AEP (Fase 5)", r.get("modelo_altura") or "—"],
        ])
    return _seccion("fase2_perfiles", "Fase 2 – Perfiles de viento",
                    "Ubicación del sitio, serie de viento y perfiles verticales usados para llevar la velocidad a la altura de buje.", [
                        _sub("f2_ubicacion", "Ubicación y datos de viento", bloques_ubicacion),
                        _sub("f2_serie", "Serie horaria", [resumen_horario, _figura(
                            fig_serie, "informe_tecnico_phase2_nasa_hourly", "Serie horaria de velocidades",
                            "Velocidad del viento horaria a 10 m y 50 m de la serie guardada.", "informe_tecnico_fase2_serie_horaria",
                            "phase2_time_series", ancho=1250, alto=620)]),
                        _sub("f2_perfiles", "Perfiles verticales", [
                            _figura(_perfil(df_exp, "Perfil exponencial (10 m y 50 m)", "Perfil exponencial", v_exp, "#3366ff"),
                                    "informe_tecnico_phase2_perfil_exp", "Perfil exponencial",
                                    "Perfil exponencial ajustado con las velocidades medias a 10 m y 50 m.",
                                    "informe_tecnico_fase2_perfil_exponencial", "phase2_profile", 880, 800),
                            _figura(_perfil(df_log_a, "Perfil logarítmico A (10 m y 50 m)", "Perfil logarítmico A", v_log_a, "#ff5533", "dash", "log"),
                                    "informe_tecnico_phase2_perfil_log_a", "Perfil logarítmico A",
                                    "Perfil logarítmico ajustado directamente con los puntos de 10 m y 50 m.",
                                    "informe_tecnico_fase2_perfil_log_a", "phase2_profile", 880, 800),
                            _figura(_perfil(df_log_b, "Promedio Log-Exp", "Promedio Log-Exp", v_log_b, "#2ca25f", "dot", "log"),
                                    "informe_tecnico_phase2_perfil_log_b", "Promedio Log-Exp",
                                    "Perfil operativo: promedio entre el perfil exponencial y el logarítmico A.",
                                    "informe_tecnico_fase2_promedio_log_exp", "phase2_profile", 880, 800),
                            _figura(_preparar_grafica(_figura_comparacion_perfiles(df_exp, df_log_a, df_log_b, altura, v_exp, v_log_a, v_log_b, puntos), 1180, 820),
                                    "informe_tecnico_phase2_compare_linear", "Comparación de perfiles (escala normal)",
                                    "Los tres enfoques de extrapolación en escala lineal de altura.",
                                    "informe_tecnico_fase2_comparacion_normal", "phase2_comparison", 1180, 820),
                            _figura(_preparar_grafica(_figura_comparacion_perfiles(df_exp, df_log_a, df_log_b, altura, v_exp, v_log_a, v_log_b, puntos, "log"), 1180, 820),
                                    "informe_tecnico_phase2_compare_log", "Comparación de perfiles (escala logarítmica)",
                                    "Los tres enfoques en escala logarítmica de altura para resaltar sus diferencias.",
                                    "informe_tecnico_fase2_comparacion_log", "phase2_comparison", 1180, 820),
                            tabla_perfiles,
                        ]),
                    ])


# ─────────────────────────────────────────────────────────────
# Fase 3 — Distribución direccional
# ─────────────────────────────────────────────────────────────
def _serie_fase3(config, df_nasa, prefijo="f3"):
    from calculos import construir_serie_viento_analisis, preparar_datos_rosa, resumir_sectores_rosa

    altura = float(config.get("perfil_hhub") or 80.0)
    if prefijo == "f35":
        modelo = str(config.get("f35_modelo") or config.get("f3_modelo_altura") or "Exponencial")
        direccion = str(config.get("f35_direccion_fuente") or config.get("f3_direccion_fuente") or "WD50M")
        rugosidad = str(config.get("f35_roughness_label") or config.get("f3_roughness_label") or "Grass / Césped")
    else:
        modelo = str(config.get("f3_modelo_altura") or "Exponencial")
        direccion = str(config.get("f3_direccion_fuente") or "WD50M")
        rugosidad = str(config.get("f3_roughness_label") or "Grass / Césped")
    df_serie, meta = construir_serie_viento_analisis(
        df_nasa=df_nasa, modelo=modelo, altura_deseada=altura, roughness_label=rugosidad,
        direccion_fuente=direccion, roughness_options=ROUGHNESS_OPTIONS,
        output_speed_col="WS_ALTURA", output_direction_col="WD_USADA",
    )
    df_rosa = preparar_datos_rosa(df_serie, ws_col="WS_ALTURA", wd_col="WD_USADA")
    resumen = resumir_sectores_rosa(df_rosa, ws_col="WS_ALTURA").copy()
    return {"altura": altura, "modelo": modelo, "direccion": direccion, "rugosidad": rugosidad,
            "df": df_serie, "df_rosa": df_rosa, "resumen": resumen, "meta": meta}


def _seccion_fase3(config, df_nasa):
    if df_nasa is None or len(df_nasa) == 0:
        return None
    from calculos import crear_rosa_vientos_16

    s3 = _serie_fase3(config, df_nasa)
    resumen = s3["resumen"]
    if len(resumen) == 0:
        return None
    ws = pd.to_numeric(s3["df"].get("WS_ALTURA"), errors="coerce").dropna()
    con_datos = resumen[pd.to_numeric(resumen["Datos"], errors="coerce").fillna(0) > 0]
    predominante = str(resumen.sort_values("Frecuencia (%)", ascending=False).iloc[0]["Sector"]) if len(resumen) else "—"
    config_tabla = _tabla("Configuración del análisis direccional", "Parámetros usados en la Fase 3 y resultados de conjunto.",
                          ["Campo", "Valor"], [
                              ["Altura de análisis", f"{fmt_num(s3['altura'], 1)} m"],
                              ["Modelo de extrapolación", s3["modelo"]],
                              ["Dirección usada", s3["direccion"]],
                              ["Rugosidad del terreno", s3["rugosidad"]],
                              ["Registros válidos", fmt_num(len(ws), 0)],
                              ["Velocidad media", f"{fmt_num(ws.mean(), 2)} m/s"],
                              ["Sectores con datos", fmt_num(len(con_datos), 0)],
                              ["Dirección predominante", predominante],
                          ])
    rosa = _preparar_grafica(crear_rosa_vientos_16(resumen.copy()), 900, 800, leyenda_horizontal=False)
    filas = []
    for _, r in resumen.iterrows():
        filas.append([r["Sector"], fmt_num(r.get("Centro (°)"), 1), fmt_num(r.get("Datos"), 0), fmt_num(r.get("Frecuencia (%)"), 2),
                      fmt_num(r.get("Velocidad media (m/s)"), 2), fmt_num(r.get("Desv. estándar (m/s)"), 2),
                      fmt_num(r.get("k Weibull"), 2), fmt_num(r.get("c Weibull (m/s)"), 2), fmt_num(r.get("c Rayleigh (m/s)"), 2),
                      fmt_num(num(r.get("Frecuencia (%)"), 0) / 100.0 * 8760.0, 0)])
    tabla_sector = _tabla("Tabla sectorial", "Frecuencia, ajuste Weibull/Rayleigh y horas equivalentes por sector.",
                          ["Sector", "Centro (°)", "Datos", "Frec. (%)", "V media (m/s)", "Desv. (m/s)", "k", "c Weibull (m/s)",
                           "c Rayleigh (m/s)", "Horas eq. (h/año)"], filas, familia="wide_sector_table")
    datos_grilla = []
    for sector in _DIRECCIONES:
        fila = resumen[resumen["Sector"] == sector]
        if len(fila) == 0 or int(fila.iloc[0]["Datos"]) <= 0:
            continue
        datos_grilla.append({
            "sector": sector,
            "velocidades": s3["df_rosa"].loc[s3["df_rosa"]["Sector"] == sector, "WS_ALTURA"].dropna().to_numpy(float),
            "k": num(fila.iloc[0]["k Weibull"]), "c": num(fila.iloc[0]["c Weibull (m/s)"]),
            "c_rayleigh": num(fila.iloc[0]["c Rayleigh (m/s)"]),
        })
    grilla = _grilla_16_sectores(datos_grilla, "Histogramas sectoriales (16 direcciones)",
                                 "Histograma de velocidades con ajustes Weibull y Rayleigh en cada sector.",
                                 "word_fase3_histogramas_grid", "histograma")
    return _seccion("fase3_direccional", "Fase 3 – Distribución direccional del viento",
                    "Caracterización direccional del recurso a la altura y con el modelo seleccionados.", [
                        _sub("f3_config", "Configuración", [config_tabla]),
                        _sub("f3_rosa", "Rosa de vientos", [_figura(rosa, "word_phase3_wind_rose", "Rosa de vientos",
                                                                    "Frecuencia y velocidad media por sector (16 direcciones).",
                                                                    "word_fase3_rosa_vientos", "phase3_wind_rose", 900, 800)]),
                        _sub("f3_tabla", "Tabla sectorial", [tabla_sector]),
                        _sub("f3_graficas", "Histogramas por sector", [grilla]),
                    ])


# ─────────────────────────────────────────────────────────────
# Fase 3.5 — Probabilidad de ocurrencia
# ─────────────────────────────────────────────────────────────
def _seccion_fase35(config, df_nasa):
    if df_nasa is None or len(df_nasa) == 0:
        return None
    from scipy import stats

    s35 = _serie_fase3(config, df_nasa, prefijo="f35")
    resumen = s35["resumen"]
    if len(resumen) == 0:
        return None
    vmax = float(config.get("f35_vmax") or config.get("f3_prob_vmax") or 25.0)
    ancho_bin = float(config.get("f35_bin_width") or config.get("f3_prob_bin_width") or 0.5)
    df_rosa = s35["df_rosa"].rename(columns={"WS_ALTURA": "WS_ANALISIS"})
    heatmap, _ = _build_probability_heatmap(df_rosa, vmax=vmax, bin_width=ancho_bin)
    heatmap = _preparar_grafica(heatmap, 1100, 720, leyenda_horizontal=False)
    try:
        categorias = list(heatmap.data[0].x)
        paso = max(1, len(categorias) // 12)
        heatmap.update_xaxes(tickmode="array", tickvals=categorias[::paso], ticktext=categorias[::paso], tickangle=-35)
    except Exception:
        pass
    x = np.linspace(0.05, vmax, 200)
    datos_grilla = []
    for sector in _DIRECCIONES:
        fila = resumen[resumen["Sector"] == sector]
        if len(fila) == 0 or int(fila.iloc[0]["Datos"]) <= 0:
            continue
        k = num(fila.iloc[0].get("k Weibull"), 2.0)
        c = num(fila.iloc[0].get("c Weibull (m/s)"), 1.0)
        cr = num(fila.iloc[0].get("c Rayleigh (m/s)"), 1.0)
        datos_grilla.append({"sector": sector, "x": x, "y_weibull": stats.weibull_min.pdf(x, k, scale=c),
                             "y_rayleigh": stats.rayleigh.pdf(x, scale=cr / np.sqrt(2))})
    grilla = _grilla_16_sectores(datos_grilla, "Curvas de probabilidad por sector (16 direcciones)",
                                 "Densidad de probabilidad Weibull y Rayleigh de la velocidad en cada sector.",
                                 "word_fase35_curvas_grid", "probabilidad")
    return _seccion("fase35_probabilidad", "Fase 3.5 – Probabilidad de ocurrencia",
                    "Curvas de probabilidad por sector y mapa de probabilidad para las 16 direcciones.", [
                        _sub("f35_curvas", "Curvas por sector", [grilla]),
                        _sub("f35_mapa", "Mapa de probabilidad", [_figura(
                            heatmap, "word_phase35_heatmap", "Probabilidad por dirección e intervalo de velocidad",
                            f"Probabilidad de ocurrencia por sector e intervalo de {fmt_num(ancho_bin, 1)} m/s.",
                            "word_fase35_mapa_probabilidad", "phase35_heatmap", 1100, 720)]),
                    ])


# ─────────────────────────────────────────────────────────────
# Fase 4 — Estelas y arreglo (mismo cálculo que la página de Fase 4)
# ─────────────────────────────────────────────────────────────
def _tabla_detalle_turbinas(df_detalle, titulo, descripcion):
    if df_detalle is None or len(df_detalle) == 0:
        return None
    filas = []
    for _, r in df_detalle.iterrows():
        v_libre = num(r.get("velocidad_libre"))
        v_ef = num(r.get("velocidad_efectiva"))
        deficit = (1.0 - v_ef / v_libre) * 100.0 if (v_libre and v_ef is not None) else None
        filas.append([str(r.get("turbina_id")), fmt_num(r.get("x_m"), 0), fmt_num(r.get("y_m"), 0), fmt_num(v_libre, 2),
                      fmt_num(v_ef, 2), fmt_num(deficit, 2), fmt_num(r.get("perdida_potencia_pct"), 2),
                      fmt_num(num(r.get("potencia_base_W"), 0) / 1000.0, 0), fmt_num(num(r.get("potencia_wake_W"), 0) / 1000.0, 0)])
    return _tabla(titulo, descripcion, ["Turbina", "x (m)", "y (m)", "V libre (m/s)", "V efectiva (m/s)", "Déficit (%)",
                                        "Pérdida de potencia (%)", "P sin estela (kW)", "P con estela (kW)"],
                  filas, familia="phase4_detail_table")


def _seccion_fase4(config, df_nasa, df_curva_raw, df_layout):
    if df_layout is None or len(df_layout) == 0 or df_nasa is None or len(df_nasa) == 0:
        return None
    from calculos import crear_figura_direccion_estela, crear_figura_layout_parque

    analisis = analisis_anual_fase4(df_nasa, config, df_curva_raw, df_layout)
    if analisis is None:
        return None
    resumen_anual, detalles_anual, perdida_ponderada, energia_f4 = analisis
    diametro = float(config.get("diametro") or 100.0)
    ct = float(config.get("f4_ct") or 0.80)
    kw = float(config.get("f4_kw") or 0.05)
    v_geom = float(config.get("f4_geom_speed") or 8.0)
    resumen_geom, detalles_geom = _analyze_geometry_all_sectors(df_layout=df_layout, curva_df=df_curva_raw, diametro=diametro,
                                                                ct=ct, kw=kw, velocidad_ref=v_geom)
    col_geom = _col(resumen_geom, "Pérdida geométrica (%)")
    col_dir_geom = _col(resumen_geom, "Dirección centro (°)")
    col_dir_anual = _col(resumen_anual, "Dirección centro (°)")
    col_pond = _col(resumen_anual, "Pérdida ponderada (%)")
    col_sector = _col(resumen_anual, "Pérdida por estela (%)")

    geom = pd.to_numeric(resumen_geom[col_geom], errors="coerce")
    criticos = str(config.get("f4_geom_critical_sectors") or "—")
    tabla_geom = _tabla("Indicadores geométricos", "Pérdida por estela de cada dirección con viento a la velocidad de referencia.",
                        ["Indicador", "Valor"], [
                            ["Direcciones analizadas", fmt_num(len(resumen_geom), 0)],
                            ["Velocidad de referencia", f"{fmt_num(v_geom, 1)} m/s"],
                            ["Pérdida geométrica media", fmt_pct(geom.mean(), 2)],
                            ["Pérdida geométrica máxima", fmt_pct(geom.max(), 2)],
                            ["Sectores críticos", criticos],
                        ])
    peor = resumen_anual.sort_values(col_pond, ascending=False).iloc[0]
    bruta_f4 = num(energia_f4.get("aep_bruta_total"), 0.0) or 0.0
    estela_f4 = num(energia_f4.get("perdida_estela_mwh"), 0.0) or 0.0
    tabla_anual = _tabla(
        "Indicadores anuales", "Pérdidas ponderadas por la frecuencia de cada dirección (mismo cálculo que la Fase 4).",
        ["Indicador", "Valor"], [
            ["Pérdida anual ponderada por frecuencia", fmt_pct(perdida_ponderada, 2)],
            ["Dirección más crítica", f"{peor['Sector']} ({fmt_pct(peor[col_sector], 1)} de pérdida en ese sector)"],
            ["Energía bruta del análisis de estelas", f"{fmt_num(bruta_f4, 0)} MWh/año"],
            ["Pérdida energética por estela", f"{fmt_num(estela_f4, 0)} MWh/año ({fmt_pct(estela_f4 / bruta_f4 * 100.0 if bruta_f4 else None, 2)})"],
        ],
        nota=("La Fase 4 pondera la pérdida de cada dirección por su frecuencia; la Fase 5 aplica la pérdida de cada sector "
              "sobre la energía de ese sector. Por eso los porcentajes pueden diferir. La AEP oficial del proyecto es la de la Fase 5."),
    )
    sector_detalle = str(config.get("f4_worst_sector") or peor["Sector"])
    detalle = []
    fila_g = resumen_geom[resumen_geom["Sector"] == sector_detalle]
    fila_a = resumen_anual[resumen_anual["Sector"] == sector_detalle]
    df_det_g = detalles_geom.get(sector_detalle, pd.DataFrame())
    df_det_a = detalles_anual.get(sector_detalle, pd.DataFrame())
    try:
        if len(fila_g) and len(df_det_g):
            detalle.append(_figura(_preparar_grafica(crear_figura_direccion_estela(
                df_detalle=df_det_g, sector=sector_detalle, direction_deg=float(fila_g.iloc[0][col_dir_geom]), diametro=diametro), 900, 780, False),
                f"word_phase4_geom_detail_{sector_detalle.lower()}", f"Detalle geométrico – dirección {sector_detalle}",
                f"Estela sobre cada turbina con viento del {sector_detalle} a {fmt_num(v_geom, 1)} m/s (dirección más crítica).",
                f"word_fase4_detalle_geom_{sector_detalle.lower()}", "phase4_direction_detail", 900, 780))
            detalle.append(_tabla_detalle_turbinas(df_det_g, f"Detalle geométrico por turbina – dirección {sector_detalle}",
                                                   "Velocidades, déficit y potencia de cada turbina en esa dirección."))
        if len(fila_a) and len(df_det_a):
            detalle.append(_figura(_preparar_grafica(crear_figura_direccion_estela(
                df_detalle=df_det_a, sector=sector_detalle, direction_deg=float(fila_a.iloc[0][col_dir_anual]), diametro=diametro), 900, 780, False),
                f"word_phase4_annual_detail_{sector_detalle.lower()}", f"Detalle anual – dirección {sector_detalle}",
                f"Estela con la velocidad media anual del sector {sector_detalle}.",
                f"word_fase4_detalle_anual_{sector_detalle.lower()}", "phase4_direction_detail", 900, 780))
            detalle.append(_tabla_detalle_turbinas(df_det_a, f"Detalle anual por turbina – dirección {sector_detalle}",
                                                   "Velocidades, déficit y potencia de cada turbina con el viento medio del sector."))
    except Exception:
        pass
    layout_fig = _preparar_grafica(crear_figura_layout_parque(df_layout=df_layout, diametro=diametro, titulo="Vista en planta del parque"),
                                   950, 780, False)
    return _seccion("fase4_estelas", "Fase 4 – Estelas y arreglo del parque",
                    "Disposición de las turbinas y pérdidas por estela por dirección.", [
                        _sub("f4_layout", "Vista en planta", [_figura(layout_fig, "word_phase4_layout", "Vista en planta del parque",
                                                                      f"Posiciones de las {len(df_layout)} turbinas (coordenadas del layout de la Fase 4).",
                                                                      "word_fase4_layout", "phase4_layout", 950, 780)]),
                        _sub("f4_geom", "Análisis geométrico", [
                            _figura(_preparar_grafica(_create_phase4_geometric_rose(resumen_geom), 860, 780, False), "word_phase4_geometric",
                                    "Rosa geométrica de pérdidas", "Pérdida por estela de cada dirección a la velocidad de referencia.",
                                    "word_fase4_geometrico", "phase4_polar", 860, 780),
                            tabla_geom]),
                        _sub("f4_anual", "Análisis anual ponderado", [
                            _figura(_preparar_grafica(_create_phase4_annual_rose(resumen_anual), 860, 780, False), "word_phase4_annual",
                                    "Rosa anual ponderada", "Longitud: pérdida ponderada por frecuencia · color: pérdida del sector.",
                                    "word_fase4_anual", "phase4_polar", 860, 780),
                            tabla_anual]),
                        _sub("f4_comparacion", "Criticidad geométrica frente a anual", [
                            _figura(_preparar_grafica(_create_phase4_geom_vs_annual(resumen_geom, resumen_anual), 1100, 680), "word_phase4_compare",
                                    "Criticidad geométrica frente a anual", "Pérdida geométrica y pérdida anual ponderada por dirección.",
                                    "word_fase4_comparacion", "phase4_comparison", 1100, 680)]),
                        _sub("f4_energia", "Energía por dirección", [
                            _figura(_preparar_grafica(_create_phase4_energy_bars(resumen_anual), 1100, 680), "word_phase4_energy",
                                    "Energía anual por dirección", "Energía bruta y con estela de cada dirección (análisis de la Fase 4).",
                                    "word_fase4_energia", "phase4_energy", 1100, 680)]),
                        _sub("f4_detalle", f"Detalle de la dirección más crítica ({sector_detalle})", detalle),
                    ])


# ─────────────────────────────────────────────────────────────
# Fase 5 — Resultados energéticos
# ─────────────────────────────────────────────────────────────
def _seccion_fase5(datos, phase5_context):
    phase5_context = phase5_context or {}
    e = datos["energia"]
    t = datos["turbina"]
    if e.get("aep_bruta_mwh") is None:
        return None
    metodo = e.get("metodo") or "Weibull"
    estela_modo = ("Automática desde la Fase 4" if e.get("wake_automatica") else "Manual") + f" · modelo {e.get('wake_model')}"
    principales = _tabla("Resultados principales", "Indicadores energéticos del escenario calculado en la Fase 5.",
                         ["Indicador", "Valor"], [
                             ["AEP bruta del parque", f"{fmt_num(e['aep_bruta_mwh'], 0)} MWh/año"],
                             ["AEP con estela", f"{fmt_num(e.get('aep_con_estela_mwh'), 0)} MWh/año"],
                             ["AEP neta del parque", f"{fmt_num(e.get('aep_neta_mwh'), 0)} MWh/año"],
                             ["Pérdida por estela aplicada", f"{fmt_pct(e.get('estela_pct'), 2)} ({estela_modo})"],
                             ["Pérdidas totales", fmt_pct(e.get("perdida_total_pct"), 2)],
                             ["Factor de planta bruto", fmt_pct(e.get("fp_bruto_pct"), 2)],
                             ["Factor de planta neto", fmt_pct(e.get("fp_neto_pct"), 2)],
                             ["Número de turbinas", fmt_num(t.get("n_turbinas"), 0)],
                             ["Potencia nominal por turbina", f"{fmt_num(t.get('p_nominal_kw'), 0)} kW"],
                             ["Método estadístico", metodo],
                         ])
    bloques_perdidas = []
    fig_loss = phase5_context.get("fig_loss_distribution")
    if fig_loss is not None:
        fig_loss = _preparar_grafica(fig_loss, 880, 720, False)
        # La dona de la Fase 5 trae letra de 11-12 px: en las 4,8 in del Word quedaba ilegible.
        fig_loss.update_traces(textfont_size=20)
        fig_loss.update_layout(legend_font_size=18)
        for anotacion in fig_loss.layout.annotations:
            anotacion.font.size = 22
        bloques_perdidas.append(_figura(fig_loss, "word_phase5_loss_distribution",
                                        f"Distribución de pérdidas ({metodo})", "Peso relativo de cada tipo de pérdida sobre el total.",
                                        "word_fase5_distribucion_perdidas", "phase5_loss_distribution", 880, 720))
    tabla_perdidas = e.get("tabla_perdidas")
    if tabla_perdidas is None:
        tabla_perdidas = phase5_context.get("tabla_perdidas")
    if tabla_perdidas is not None and len(tabla_perdidas) > 0:
        filas = [[str(r.get("Concepto")), fmt_num(r.get("Pérdida (%)"), 2), fmt_num(r.get("Energía perdida (MWh/año)"), 1)]
                 for _, r in tabla_perdidas.iterrows()]
        bloques_perdidas.append(_tabla("Pérdidas energéticas", "Pérdidas aplicadas en secuencia sobre la AEP bruta.",
                                       ["Concepto", "Pérdida (%)", "Energía perdida (MWh/año)"], filas))
    df_sector = e.get("df_aep_sector")
    if df_sector is None:
        df_sector = phase5_context.get("df_aep_sector")
    bloques_sector = []
    if df_sector is not None and len(df_sector) > 0:
        filas = []
        for _, r in df_sector.iterrows():
            filas.append([r.get("Sector"), fmt_num(r.get("Frecuencia (%)"), 2), fmt_num(r.get("Horas equivalentes anuales (h/año)"), 0),
                          fmt_num(num(r.get("Potencia media por turbina (W)"), 0) / 1000.0, 0),
                          fmt_num(r.get("AEP bruta parque (MWh/año)"), 1), fmt_num(r.get("Pérdida estela sector (%)"), 2),
                          fmt_num(r.get("AEP con estela (MWh/año)"), 1), fmt_num(r.get("AEP neta sector (MWh/año)"), 1)])
        filas.append(["Total", fmt_num(df_sector["Frecuencia (%)"].sum(), 2), fmt_num(df_sector["Horas equivalentes anuales (h/año)"].sum(), 0), "—",
                      fmt_num(df_sector["AEP bruta parque (MWh/año)"].sum(), 1), "—",
                      fmt_num(df_sector["AEP con estela (MWh/año)"].sum(), 1), fmt_num(df_sector["AEP neta sector (MWh/año)"].sum(), 1)])
        bloques_sector.append(_tabla("Resultados por sector", "Energía bruta, con estela y neta de cada dirección.",
                                     ["Sector", "Frec. (%)", "Horas eq. (h/año)", "P media turbina (kW)", "AEP bruta (MWh)",
                                      "Pérd. estela (%)", "AEP con estela (MWh)", "AEP neta (MWh)"], filas, familia="phase5_sector_table"))
    fig_sector = phase5_context.get("fig_sectorial")
    bloques_grafica = []
    if fig_sector is not None:
        bloques_grafica.append(_figura(_preparar_grafica(fig_sector, 1100, 680), "word_phase5_aep_sector", f"AEP por sector ({metodo})",
                                       "AEP bruta y neta por dirección.", "word_fase5_aep_sector", "phase5_sector_chart", 1100, 680))
    return _seccion("fase5_resultados", "Fase 5 – Resultados energéticos",
                    "AEP, factor de planta y pérdidas del escenario calculado.", [
                        _sub("f5_principales", "Resultados principales", [principales]),
                        _sub("f5_perdidas", "Pérdidas", bloques_perdidas),
                        _sub("f5_sectores", "Resultados por sector", bloques_sector),
                        _sub("f5_grafica", "AEP por sector", bloques_grafica),
                    ])


# ─────────────────────────────────────────────────────────────
# Fase 6 — Estudios avanzados (solo lo que se haya ejecutado)
# ─────────────────────────────────────────────────────────────
def _seccion_fase6(datos):
    a = datos["ambiental"]
    iec = datos["iec"]
    r = datos["recurso"]
    filas = []
    if a.get("ruido_analizado"):
        cumple = (a["ruido_max_db"] <= a["ruido_lim_noche"]) if a.get("ruido_lim_noche") is not None else None
        filas.append(["Ruido máximo en receptores (ISO 9613-2)", f"{fmt_num(a['ruido_max_db'], 1)} dB(A)",
                      f"día {fmt_num(a.get('ruido_lim_dia'), 0)} / noche {fmt_num(a.get('ruido_lim_noche'), 0)} dB(A)",
                      "Cumple (también de noche)" if cumple else ("Supera el límite nocturno" if cumple is False else "—")])
    if a.get("flicker_analizado"):
        cumple = a["flicker_max_h"] <= a["flicker_lim_h"] if a.get("flicker_lim_h") is not None else None
        filas.append(["Parpadeo de sombra máximo", f"{fmt_num(a['flicker_max_h'], 1)} h/año", f"{fmt_num(a.get('flicker_lim_h'), 0)} h/año",
                      "Cumple" if cumple else ("Supera el límite" if cumple is False else "—")])
    if iec.get("cumple") is not None or r.get("ti_15") is not None:
        veredicto = {True: "Cumple", False: "No cumple", None: "Sin datos suficientes"}[iec.get("cumple")]
        filas.append([f"IEC 61400-1 · clase {iec.get('clase_declarada')}{iec.get('categoria_declarada')} (Fase 5)",
                      f"V media buje {fmt_num(r.get('v_media_buje'), 2)} m/s · TI15 {fmt_num(r.get('ti_15'), 3)}",
                      f"V ≤ {fmt_num(iec.get('v_avg_clase'), 1)} m/s · TI ≤ {fmt_num(iec.get('ti_clase'), 2)}", veredicto])
    if not filas:
        return None
    tabla = _tabla("Resultados disponibles de la Fase 6", "Solo se listan los estudios que se ejecutaron en la app.",
                   ["Estudio", "Resultado", "Límite / referencia", "Estado"], filas,
                   nota=("La intensidad de turbulencia se estima con la serie horaria de la app; la norma usa estadísticos de 10 minutos, "
                         "por lo que la TI es indicativa y el veredicto de turbulencia debe confirmarse con medición."))
    return _seccion("fase6_estudios", "Fase 6 – Estudios avanzados (resumen)",
                    "Resultados de los estudios complementarios ejecutados en la app.", [_sub("f6_resumen", "", [tabla])])


# ─────────────────────────────────────────────────────────────
# Portada, resumen y cierre
# ─────────────────────────────────────────────────────────────
def _seccion_identificacion(datos, titulos):
    p, t = datos["proyecto"], datos["turbina"]
    from datetime import datetime

    filas = [
        ["Documento", "Informe técnico — análisis exploratorio por fases"],
        ["Proyecto", p["nombre"]],
        ["Ubicación", f"lat {fmt_coord(p.get('lat'))} · lon {fmt_coord(p.get('lon'))}"
                      + (f" ({p['pais_inferido_nombre']})" if p.get("pais_inferido_nombre") else "")],
        ["Aerogeneradores", f"{fmt_num(t.get('n_turbinas'), 0)} × {fmt_num(t.get('p_nominal_kw'), 0)} kW · rotor "
                            f"{fmt_num(t.get('diametro_m'), 1)} m · buje {fmt_num(t.get('altura_buje_m'), 0)} m"],
        ["Período de datos", f"{p.get('inicio')} a {p.get('fin')} ({p.get('fuente')})"],
        ["Tipo de informe", "Técnico-descriptivo (no bankable)"],
        ["Audiencia", "Equipo de ingeniería / soporte interno"],
        ["Contenido", " · ".join(titulos)],
        ["Generado", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Herramienta", "SMA 2.0"],
        ["Diferencia con el bankable", "No incluye P50/P90, incertidumbre, análisis económico ni registro de riesgos: "
                                       "para eso use el «Reporte bankable» de la Fase 7."],
    ]
    from .estilo import diagrama_metodologia_png

    pasos = [
        ("Fase 1 · Aerogenerador", "Curva de potencia y Cp"), ("Fase 2 · Perfiles", "Serie de viento y\nextrapolación vertical"),
        ("Fase 3 · Dirección", "Rosa y Weibull\npor sector"), ("Fase 3.5 · Probabilidad", "Ocurrencia por sector\ny velocidad"),
        ("Fase 4 · Estelas", "Disposición y pérdidas\npor dirección"), ("Fase 5 · Energía", "AEP bruta y neta"),
        ("Fase 6 · Estudios", "Ruido, parpadeo e IEC"),
    ]
    diagrama = {"type": "figure", "title": "Estructura del estudio: fases de la aplicación y resultado de cada una",
                "description": "", "image_bytes": diagrama_metodologia_png(pasos, por_fila=4, destacados=(5,)),
                "image_format": "png", "file_name": "estructura_del_estudio.png", "figure_family": "diagrama"}
    return _seccion("identificacion", "Identificación del documento",
                    "", [_sub("id_tabla", "", [_tabla("Datos del informe", "", ["Campo", "Valor"], filas), diagrama])])


def _portada_modelo(datos):
    """Datos de la portada formal (banda, proyecto, ubicación y datos clave)."""
    from datetime import datetime

    p, t = datos["proyecto"], datos["turbina"]
    lugar = p.get("pais_inferido_nombre") or p.get("pais_nombre") or ""
    return {
        "cover_title": "INFORME TÉCNICO",
        "cover_subtitle": "Análisis exploratorio por fases del proyecto eólico",
        "cover_line": f"{lugar} · lat {fmt_coord(p.get('lat'))} · lon {fmt_coord(p.get('lon'))} · {datetime.now():%Y-%m-%d}",
        "cover_rows": [
            ["Aerogeneradores", f"{fmt_num(t.get('n_turbinas'), 0)} × {fmt_num(t.get('p_nominal_kw'), 0)} kW · rotor "
                                f"{fmt_num(t.get('diametro_m'), 1)} m · buje {fmt_num(t.get('altura_buje_m'), 0)} m"],
            ["Potencia instalada", f"{fmt_num(t.get('p_instalada_mw'), 2)} MW"],
            ["Datos de viento", f"{p.get('fuente')} · {p.get('inicio')} a {p.get('fin')}"],
            ["Tipo de documento", "Informe técnico-descriptivo (no bankable)"],
            ["Herramienta", "SMA 2.0"],
        ],
    }


def _seccion_resumen(datos):
    p, t, e, r = datos["proyecto"], datos["turbina"], datos["energia"], datos["recurso"]
    filas = [
        ["Sitio", f"lat {fmt_coord(p.get('lat'))} · lon {fmt_coord(p.get('lon'))}"],
        ["Aerogeneradores", f"{fmt_num(t.get('n_turbinas'), 0)} turbinas de {fmt_num(t.get('p_nominal_kw'), 0)} kW"],
        ["Potencia instalada", f"{fmt_num(t.get('p_instalada_mw'), 2)} MW"],
        ["Altura de buje", f"{fmt_num(t.get('altura_buje_m'), 0)} m"],
    ]
    if r.get("v_media_buje") is not None:
        filas.append(["Velocidad media a la altura de buje", f"{fmt_num(r['v_media_buje'], 2)} m/s"])
    filas += [
        ["Método estadístico", e.get("metodo") or "—"],
        ["AEP bruta del parque", f"{fmt_num(e.get('aep_bruta_mwh'), 0)} MWh/año"],
        ["Pérdida por estela aplicada", fmt_pct(e.get("estela_pct"), 2)],
        ["Pérdidas totales", f"{fmt_num((e.get('aep_bruta_mwh') or 0) - (e.get('aep_neta_mwh') or 0), 0)} MWh/año ({fmt_pct(e.get('perdida_total_pct'), 2)})"],
        ["AEP neta del parque", f"{fmt_num(e.get('aep_neta_mwh'), 0)} MWh/año"],
        ["Factor de planta bruto / neto", f"{fmt_pct(e.get('fp_bruto_pct'), 1)} / {fmt_pct(e.get('fp_neto_pct'), 1)}"],
    ]
    return _seccion("resumen_ejecutivo", "Resumen ejecutivo",
                    "Indicadores técnicos principales del proyecto. Para P50/P90, VPN, TIR e incertidumbre use el «Reporte bankable».",
                    [_sub("res_tabla", "", [_tabla("Indicadores principales", "", ["Concepto", "Valor"], filas)])])


def _seccion_cierre(datos, config):
    from datetime import datetime

    eco = datos["economia"]
    p = datos["proyecto"]
    filas = [
        ["Documento generado", "Informe técnico por fases"],
        ["Formatos disponibles", "PDF · Word (.docx) · Excel · JSON · GIS (KML/GeoJSON/CSV)"],
        ["Fuente meteorológica", p.get("fuente")],
        ["Período analizado", f"{p.get('inicio')} a {p.get('fin')}"],
        ["Generado", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Herramienta", "SMA 2.0 — modo informe técnico"],
    ]
    nota = None
    if eco.get("lcoe_mwh") is not None:
        filas.insert(4, ["LCOE estimado (Fase 5)", f"{eco['moneda']} {fmt_num(eco['lcoe_mwh'] * (eco.get('factor') or 1.0), 2)}/MWh"])
        if any(a.get("clave") == "capex" for a in datos.get("avisos", [])):
            nota = ("Revise la moneda de la Fase 5: el CAPEX equivale a menos de 500 USD/kW (lo típico en eólica terrestre es "
                    "1.000–2.500 USD/kW), así que el LCOE podría estar en otra moneda.")
    siguientes = [
        ["1. Validar la Fase 2", "Confirmar que la serie cubre el período de interés y revisar el perfil vertical"],
        ["2. Validar la Fase 3", "Verificar la rosa de vientos y el ajuste Weibull por sector"],
        ["3. Refinar la Fase 4", "Iterar el layout para reducir las pérdidas por estela"],
        ["4. Cerrar la Fase 5", "Confirmar pérdidas (disponibilidad, eléctricas, otras) con O&M y el diseño eléctrico"],
        ["5. Reporte bankable", "Para FID o project finance, generar el «Reporte bankable» de la Fase 7"],
        ["6. Validación de tercera parte", "EYA bankable con consultor certificado (WAsP / WindPRO / openWind)"],
    ]
    return _seccion("cierre", "Cierre del informe",
                    "Trazabilidad de la exportación y próximos pasos recomendados. El análisis económico detallado y la "
                    "incertidumbre P50/P90 están en el «Reporte bankable».", [
                        _sub("cierre_config", "Configuración de la exportación", [_tabla("Exportación", "", ["Campo", "Valor"], filas, nota=nota)]),
                        _sub("cierre_pasos", "Próximos pasos", [_tabla("Próximos pasos recomendados",
                                                                       "Plan sugerido para pasar del informe técnico a un EYA bankable.",
                                                                       ["Paso", "Acción"], siguientes)]),
                    ])


# ─────────────────────────────────────────────────────────────
# Modelos públicos
# ─────────────────────────────────────────────────────────────
def build_informe_tecnico_model(config=None, project_name="", df_curva_raw=None, df_nasa=None, master_docx_bytes=None,
                                master_docx_name="informe_tecnico editado por mi.docx", datos=None):
    """Modelo base (Fases 1 y 2). Se mantiene por compatibilidad."""
    config = config or {}
    datos = datos or construir_datos_exportacion(config, {"df_curva_raw": df_curva_raw, "df_nasa": df_nasa,
                                                          "project_name_default": project_name})
    secciones = [s for s in (_seccion_fase1(config, datos, df_curva_raw), _seccion_fase2(config, datos, df_nasa)) if s]
    return normalize_text_deep({
        "document_id": "informe_tecnico", "title": "Informe técnico", "project_name": datos["proyecto"]["nombre"],
        "intro_paragraphs": [], "sections": secciones, "base_blocks": [],
        "word_master": {"available": False, "docx_bytes": None, "file_name": master_docx_name},
        "appended_sections": secciones[1:], "master_source_name": master_docx_name, "master_source_used": False,
    })


def build_informe_tecnico_word_model(config=None, project_name="", df_curva_raw=None, df_nasa=None, df_layout=None,
                                     master_docx_bytes=None, master_docx_name="informe_tecnico editado por mi.docx",
                                     phase5_context=None, datos=None):
    config = config or {}
    datos = datos or construir_datos_exportacion(config, {
        "df_curva_raw": df_curva_raw, "df_nasa": df_nasa, "df_layout": df_layout, "project_name_default": project_name,
    })
    nombre = datos["proyecto"]["nombre"]
    word_master = load_informe_tecnico_master_docx(master_docx_bytes, file_name=master_docx_name)

    fases = [
        _seccion_fase1(config, datos, df_curva_raw),
        _seccion_fase2(config, datos, df_nasa),
        _seccion_fase3(config, df_nasa),
        _seccion_fase35(config, df_nasa),
        _seccion_fase4(config, df_nasa, df_curva_raw, df_layout),
        _seccion_fase5(datos, phase5_context),
        _seccion_fase6(datos),
    ]
    fases = [s for s in fases if s]
    cierre = _seccion_cierre(datos, config)
    resumen = _seccion_resumen(datos)
    titulos = [s["title"].split(" – ")[0] for s in fases]
    identificacion = _seccion_identificacion(datos, titulos)
    intro = [
        f"Proyecto {nombre}. Documento técnico-descriptivo organizado por las fases del estudio: aerogenerador, recurso "
        "eólico, distribución direccional, estelas y resultados energéticos.",
        "Aviso: este informe no es un EYA bankable. No incluye incertidumbre P50/P90, análisis económico ni registro de "
        "riesgos; para una decisión de inversión (FID o project finance) genere el «Reporte bankable» en la Fase 7.",
    ]
    portada = _portada_modelo(datos)
    if word_master.get("available"):
        secciones = [identificacion, resumen] + list(word_master.get("sections", []) or []) + fases[2:] + [cierre]
        modelo = {**portada,
            "document_id": "informe_tecnico", "title": "Informe técnico — Análisis exploratorio por fases",
            "project_name": nombre, "intro_paragraphs": intro, "sections": [s for s in secciones if s],
            "base_blocks": word_master.get("base_blocks", []), "word_master": word_master,
            "appended_sections": [s for s in fases[2:] + [cierre] if s],
            "master_source_name": word_master.get("file_name", master_docx_name), "master_source_used": True,
        }
        return normalize_text_deep(modelo)
    modelo = {
        **portada,
        "document_id": "informe_tecnico", "title": "Informe técnico — Análisis exploratorio por fases",
        "project_name": nombre, "intro_paragraphs": intro,
        "sections": [s for s in [identificacion, resumen] + fases + [cierre] if s],
        "base_blocks": [], "word_master": {"available": False, "docx_bytes": None, "file_name": master_docx_name},
        "appended_sections": fases[1:] + [cierre], "master_source_name": master_docx_name, "master_source_used": False,
    }
    return normalize_text_deep(modelo)


__all__ = ["build_informe_tecnico_model", "build_informe_tecnico_word_model", "ROUGHNESS_OPTIONS"]
