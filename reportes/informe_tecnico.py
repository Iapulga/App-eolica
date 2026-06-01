import unicodedata
from math import pi

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .docx import load_informe_tecnico_master_docx
from .figuras import (
    _create_phase4_annual_rose,
    _create_phase4_geometric_rose,
    build_site_map_bundle,
    export_plotly_figure_artifact,
)
from .manifiestos import _informe_tecnico_table_from_dataframe
from .texto import normalize_text_deep, normalize_visible_text


def _normalize_spanish_text(value):
    return normalize_visible_text(value)


ROUGHNESS_OPTIONS = {
    "Water / Mar": 2e-4,
    "Snow / Nieve": 1e-3,
    "Grass / CÃ©sped": 0.03,
    "Farmland / Cultivo": 0.10,
    "Forest / Bosque": 0.80,
    "City / Ciudad": 1.00,
}


def _style_phase2_time_series_figure(fig):
    if fig is None:
        return fig
    fig.update_layout(
        width=1220,
        height=620,
        template="plotly_white",
        margin=dict(l=70, r=40, t=70, b=80),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, bgcolor="rgba(255,255,255,0.85)"),
    )
    fig.update_xaxes(nticks=8, tickangle=0, showgrid=True, gridcolor="rgba(0,0,0,0.08)", ticklabelmode="period", rangeslider_visible=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", zeroline=False)
    return fig


def _style_phase2_profile_figure(fig, logarithmic=False):
    if fig is None:
        return fig
    fig.update_layout(
        width=860,
        height=880,
        template="plotly_white",
        margin=dict(l=80, r=70, t=80, b=70),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, bgcolor="rgba(255,255,255,0.88)"),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", zeroline=False)
    if logarithmic:
        fig.update_yaxes(type="log")
    return fig


def _style_phase2_comparison_figure(fig, logarithmic=False):
    if fig is None:
        return fig
    fig.update_layout(
        width=1180,
        height=860,
        template="plotly_white",
        margin=dict(l=80, r=70, t=40, b=70),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="rgba(0,0,0,0.08)",
            borderwidth=1,
            font=dict(size=11),
        ),
        title=None,
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", zeroline=False)
    if logarithmic:
        fig.update_yaxes(type="log")
    return fig


def _phase2_export_figure_block(fig, figure_id, title, description, stem, figure_family=None, export_options=None):
    image_bytes, metadata = export_plotly_figure_artifact(
        fig=fig,
        figure_id=figure_id,
        title=title,
        stem=stem,
        source_hint=description,
        preferred_format="png",
        export_options=export_options or {},
    )
    block = {
        "type": "figure",
        "title": _normalize_spanish_text(title),
        "description": _normalize_spanish_text(description),
        "image_bytes": None,
        "image_format": None,
        "file_name": None,
        "figure_family": str(figure_family or ""),
    }
    if image_bytes and str(metadata.get("export_format") or "").lower() == "png":
        block.update({"image_bytes": image_bytes, "image_format": "png", "file_name": metadata.get("file_name", f"{stem}.png")})
    return block


def _build_phase2_compare_figure(df_exp, df_log_a, df_log_b, altura_deseada, v_exp, v_log_a, v_log_b, puntos_medidos, yaxis_type="linear"):
    fig = go.Figure()
    traces = [
        (df_exp, "Exponencial (2 puntos)", "#3366ff", None),
        (df_log_a, "LogarÃ­tmico A (2 puntos)", "#ff5533", "dash"),
        (df_log_b, "Promedio Log-Exp", "#2ca25f", "dot"),
    ]
    for df_modelo, nombre, color, dash in traces:
        fig.add_trace(
            go.Scatter(
                x=df_modelo["Velocidad (m/s)"],
                y=df_modelo["Altura (m)"],
                mode="lines",
                name=nombre,
                line=dict(width=3, color=color, dash=dash),
                hovertemplate="Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra>" + nombre + "</extra>",
            )
        )
    if puntos_medidos:
        fig.add_trace(
            go.Scatter(
                x=[p["velocidad"] for p in puntos_medidos],
                y=[p["altura"] for p in puntos_medidos],
                mode="markers",
                name="Puntos medidos",
                marker=dict(size=10, color="black"),
                text=[p["etiqueta"] for p in puntos_medidos],
                hovertemplate="%{text}<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=[v_exp], y=[altura_deseada], mode="markers", name="Objetivo exp.",
            marker=dict(size=10, color="#3366ff"),
            hovertemplate="Objetivo exp.<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[v_log_a], y=[altura_deseada], mode="markers", name="Objetivo log A",
            marker=dict(size=10, color="#ff5533", symbol="diamond"),
            hovertemplate="Objetivo log A<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[v_log_b], y=[altura_deseada], mode="markers", name="Objetivo promedio",
            marker=dict(size=10, color="#2ca25f", symbol="square"),
            hovertemplate="Objetivo promedio<br>Velocidad: %{x:.2f} m/s<br>Altura: %{y:.2f} m<extra></extra>",
        )
    )
    fig.add_hline(y=float(altura_deseada), line_dash="dot", line_color="gray")
    fig.update_layout(
        template="plotly_white",
        height=780,
        margin=dict(l=50, r=40, t=20, b=40),
        xaxis_title="Velocidad del viento (m/s)",
        yaxis_title="Altura (m)",
        title=None,
    )
    if yaxis_type == "log":
        fig.update_yaxes(type="log", title_text="Altura (m)")
    return fig


def _build_phase2_section(config=None, project_name="", df_nasa=None):
    config = config or {}
    df_nasa = df_nasa.copy() if df_nasa is not None else pd.DataFrame()
    if len(df_nasa) == 0:
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

    latitude = config.get("nasa_lat")
    longitude = config.get("nasa_lon")
    start_date = config.get("nasa_inicio")
    end_date = config.get("nasa_fin")
    altura_deseada = float(config.get("perfil_hhub") or 80.0)

    for col in ["WS10M", "WS50M", "WD10M", "WD50M"]:
        if col in df_nasa.columns:
            df_nasa[col] = pd.to_numeric(df_nasa[col], errors="coerce")

    v10_series = df_nasa.get("WS10M", pd.Series(dtype=float)).dropna()
    v50_series = df_nasa.get("WS50M", pd.Series(dtype=float)).dropna()
    if len(v10_series) == 0 or len(v50_series) == 0:
        return None

    v10 = float(v10_series.mean())
    v50 = float(v50_series.mean())
    alpha = float(calcular_alpha_desde_dos_alturas(v10, 10.0, v50, 50.0))
    u_star_a, z0_ajustada = ajustar_logaritmico_dos_puntos(v10, 10.0, v50, 50.0, kappa=KAPPA)
    v_exp_deseada = float(v10 * (altura_deseada / 10.0) ** alpha)
    v_log_a_deseada = float(velocidad_logaritmica_en_altura(u_star_a, altura_deseada, z0_ajustada, kappa=KAPPA))
    v_log_b_deseada = float((v_exp_deseada + v_log_a_deseada) / 2.0)
    alturas = np.linspace(10.0, max(float(altura_deseada), 80.0), 60)
    df_exp = calcular_perfil_exponencial(v10, 10.0, alpha, alturas)
    df_log_a = calcular_perfil_logaritmico(u_star_a, z0_ajustada, alturas, kappa=KAPPA)
    df_log_b = df_exp.copy()
    df_log_b["Velocidad (m/s)"] = (df_exp["Velocidad (m/s)"].to_numpy(dtype=float) + df_log_a["Velocidad (m/s)"].to_numpy(dtype=float)) / 2.0
    puntos_medidos = [{"altura": 10.0, "velocidad": v10, "etiqueta": "WS10M"}, {"altura": 50.0, "velocidad": v50, "etiqueta": "WS50M"}]

    site_map_bundle = build_site_map_bundle(config=config, base_folder="04_Figuras_mapas")
    site_map_png = None
    for artifact in site_map_bundle.get("artifacts", []):
        if artifact.get("id") == "site_map" and artifact.get("export_format") == "png" and artifact.get("path"):
            site_map_png = site_map_bundle.get("files", {}).get(artifact.get("path"))
            break

    return {
        "id": "fase2_perfiles_viento",
        "title": _normalize_spanish_text("Fase 2 - Perfiles de viento"),
        "description": _normalize_spanish_text("ContinuaciÃ³n del informe tÃ©cnico dedicada a la ubicaciÃ³n del sitio, la consulta NASA POWER y la construcciÃ³n de perfiles verticales del viento."),
        "subsections": [
            {
                "id": "fase2_ubicacion_nasa",
                "title": _normalize_spanish_text("UbicaciÃ³n y consulta NASA POWER"),
                "blocks": [
                    {"type": "figure", "title": _normalize_spanish_text("Mapa del sitio"), "description": _normalize_spanish_text("Mapa de la ubicaciÃ³n seleccionada en Fase 2, alineado con la vista cartogrÃ¡fica usada por la app."), "image_bytes": site_map_png, "image_format": "png" if site_map_png else None, "file_name": "mapa_sitio.png" if site_map_png else None},
                    {"type": "table", "title": _normalize_spanish_text("UbicaciÃ³n y consulta NASA POWER"), "description": _normalize_spanish_text("Datos geogrÃ¡ficos y temporales de la consulta NASA POWER usada para caracterizar el sitio."), "headers": ["Campo", "Valor"], "rows": [["Latitud", f"{float(latitude):.2f}" if latitude not in [None, ""] else "Sin dato"], ["Longitud", f"{float(longitude):.2f}" if longitude not in [None, ""] else "Sin dato"], ["Fecha inicial", str(start_date or "Sin dato")], ["Fecha final", str(end_date or "Sin dato")]]},
                ],
            },
            {
                "id": "fase2_resumen_horario",
                "title": _normalize_spanish_text("Resumen de datos horarios guardados"),
                "blocks": [
                    {"type": "table", "title": _normalize_spanish_text("Resumen de datos horarios guardados"), "description": _normalize_spanish_text("Resumen estadÃ­stico base de la serie horaria almacenada para el sitio seleccionado."), "headers": ["Concepto", "Valor"], "rows": [["Registros horarios", str(len(df_nasa))], ["Promedio WS10M", f"{v10:.2f} m/s"], ["Promedio WS50M", f"{v50:.2f} m/s"], ["Promedio WD10M", f"{float(df_nasa['WD10M'].dropna().mean()):.2f}Â°" if len(df_nasa['WD10M'].dropna()) > 0 else "Sin dato"]]},
                    _phase2_export_figure_block(_style_phase2_time_series_figure(crear_grafica_nasa_hourly(df_nasa)), "informe_tecnico_phase2_nasa_hourly", "Serie horaria de velocidades", "Serie horaria de velocidades del viento registrada en los datos horarios guardados para el sitio.", "informe_tecnico_fase2_serie_horaria", figure_family="phase2_time_series", export_options={"width": 1220, "height": 620, "max_dimension": 1800}),
                ],
            },
            {
                "id": "fase2_perfiles_verticales",
                "title": _normalize_spanish_text("Perfiles verticales del viento"),
                "blocks": [
                    _phase2_export_figure_block(_style_phase2_profile_figure(crear_grafica_perfil_individual(df_exp, "Perfil exponencial ajustado con 10 m y 50 m", "Perfil exponencial", altura_objetivo=altura_deseada, v_objetivo=v_exp_deseada, color="#3366ff", yaxis_type="linear", puntos_medidos=puntos_medidos), logarithmic=False), "informe_tecnico_phase2_perfil_exp", "Perfil exponencial", "Perfil vertical exponencial calculado a partir de las velocidades medias a 10 m y 50 m.", "informe_tecnico_fase2_perfil_exponencial", figure_family="phase2_profile", export_options={"width": 860, "height": 880, "max_dimension": 1900}),
                    _phase2_export_figure_block(_style_phase2_profile_figure(crear_grafica_perfil_individual(df_log_a, "Perfil logarÃ­tmico modo A - ajustado con 10 m y 50 m", "Perfil logarÃ­tmico A", altura_objetivo=altura_deseada, v_objetivo=v_log_a_deseada, color="#ff5533", dash="dash", yaxis_type="log", puntos_medidos=puntos_medidos), logarithmic=True), "informe_tecnico_phase2_perfil_log_a", "Perfil logarÃ­tmico modo A", "Perfil logarÃ­tmico ajustado directamente con los puntos medidos en 10 m y 50 m.", "informe_tecnico_fase2_perfil_log_a", figure_family="phase2_profile", export_options={"width": 860, "height": 880, "max_dimension": 1900}),
                    _phase2_export_figure_block(_style_phase2_profile_figure(crear_grafica_perfil_individual(df_log_b, "Promedio Log-Exp", "Promedio Log-Exp", altura_objetivo=altura_deseada, v_objetivo=v_log_b_deseada, color="#2ca25f", dash="dot", yaxis_type="log", puntos_medidos=puntos_medidos), logarithmic=True), "informe_tecnico_phase2_perfil_log_b", "Promedio Log-Exp", "Perfil operativo construido como promedio entre el perfil exponencial y el perfil logar??tmico A.", "informe_tecnico_fase2_promedio_log_exp", figure_family="phase2_profile", export_options={"width": 860, "height": 880, "max_dimension": 1900}),
                    _phase2_export_figure_block(_style_phase2_comparison_figure(_build_phase2_compare_figure(df_exp, df_log_a, df_log_b, altura_deseada, v_exp_deseada, v_log_a_deseada, v_log_b_deseada, puntos_medidos, yaxis_type="linear"), logarithmic=False), "informe_tecnico_phase2_compare_linear", "ComparaciÃ³n entre perfiles en escala normal", "ComparaciÃ³n de los perfiles verticales en escala normal para contrastar los tres enfoques de extrapolaciÃ³n.", "informe_tecnico_fase2_comparacion_normal", figure_family="phase2_comparison", export_options={"width": 1180, "height": 860, "max_dimension": 2100}),
                    _phase2_export_figure_block(_style_phase2_comparison_figure(_build_phase2_compare_figure(df_exp, df_log_a, df_log_b, altura_deseada, v_exp_deseada, v_log_a_deseada, v_log_b_deseada, puntos_medidos, yaxis_type="log"), logarithmic=True), "informe_tecnico_phase2_compare_log", "ComparaciÃ³n entre perfiles en escala logarÃ­tmica", "ComparaciÃ³n de los perfiles verticales usando escala logarÃ­tmica en altura para resaltar diferencias de comportamiento.", "informe_tecnico_fase2_comparacion_log", figure_family="phase2_comparison", export_options={"width": 1180, "height": 860, "max_dimension": 2100}),
                    {"type": "table", "title": _normalize_spanish_text("Tabla resumen de perfiles"), "description": _normalize_spanish_text("Resumen num??rico de los par??metros y velocidades representativas obtenidas en la caracterizaci??n vertical del viento."), "headers": ["Concepto", "Valor"], "rows": [["Velocidad media a 10 m", f"{v10:.2f}"], ["Velocidad media a 50 m", f"{v50:.2f}"], ["Alpha exponencial", f"{alpha:.2f}"], ["u* modo A", f"{float(u_star_a):.2f}"], ["z0 modo A ajustada", f"{float(z0_ajustada):.2f}"], ["Velocidad a altura deseada - Exponencial", f"{v_exp_deseada:.2f}"], ["Velocidad a altura deseada - Log A", f"{v_log_a_deseada:.2f}"], ["Velocidad a altura deseada - Promedio Log-Exp", f"{v_log_b_deseada:.2f}"]]},
                ],
            },
        ],
    }


def build_informe_tecnico_model(config=None, project_name="", df_curva_raw=None, df_nasa=None, master_docx_bytes=None, master_docx_name="informe_tecnico editado por mi.docx"):
    config = config or {}
    project_name = str(project_name or config.get("project_name") or "Proyecto eolico").strip() or "Proyecto eolico"

    from calculos import calcular_cp, crear_grafica_curva, preparar_datos_curva

    word_master = load_informe_tecnico_master_docx(master_docx_bytes, file_name=master_docx_name)
    phase2_section = _build_phase2_section(config=config, project_name=project_name, df_nasa=df_nasa)
    if word_master.get("available"):
        sections = list(word_master.get("sections", []) or [])
        if phase2_section:
            sections.append(phase2_section)
        report_model = {
            "document_id": "informe_tecnico",
            "title": word_master.get("title") or _normalize_spanish_text("Informe tÃ©cnico"),
            "project_name": word_master.get("project_name") or _normalize_spanish_text(project_name),
            "intro_paragraphs": word_master.get("intro_paragraphs", []),
            "sections": sections,
            "base_blocks": word_master.get("base_blocks", []),
            "word_master": word_master,
            "appended_sections": [phase2_section] if phase2_section else [],
            "master_source_name": word_master.get("file_name", master_docx_name),
            "master_source_used": True,
        }
        return normalize_text_deep(report_model)

    diametro = float(config.get("diametro") or 100.0)
    densidad = float(config.get("densidad") or 1.225)
    area_rotor = pi * (diametro / 2.0) ** 2
    df_curva = preparar_datos_curva(df_curva_raw)
    df_curva = df_curva.copy() if df_curva is not None else pd.DataFrame()
    df_cp = calcular_cp(df_curva, densidad, area_rotor).copy() if len(df_curva) > 0 else pd.DataFrame()

    speed_power_table = _informe_tecnico_table_from_dataframe(df_curva, "Tabla editable de velocidades y potencia", "Tabla base de velocidades y potencia actualmente definida para el aerogenerador seleccionado en Fase 1.", ["Velocidad_num", "Potencia_W"], {"Velocidad_num": 2, "Potencia_W": 2})
    if speed_power_table:
        speed_power_table["headers"] = ["Velocidad (m/s)", "Potencia (W)"]
        speed_power_table["table_family"] = "split_horizontal"
    df_cp_for_table = df_cp[["Velocidad_num", "Potencia_W", "P_viento_W", "Cp"]].rename(columns={"Velocidad_num": "Velocidad (m/s)", "Potencia_W": "Potencia (W)", "P_viento_W": "Potencia del viento (W)"}) if len(df_cp) > 0 else df_cp
    cp_table = _informe_tecnico_table_from_dataframe(df_cp_for_table, "Tabla de Cp calculado", "Tabla derivada de la curva de potencia actual para documentar el coeficiente de potencia calculado en cada velocidad.", ["Velocidad (m/s)", "Potencia (W)", "Potencia del viento (W)", "Cp"], {"Velocidad (m/s)": 2, "Potencia (W)": 2, "Potencia del viento (W)": 2, "Cp": 4})
    if cp_table:
        cp_table["table_family"] = "split_horizontal"
    cp_fig = crear_grafica_curva(df_cp) if len(df_cp) > 0 else None
    cp_figure_block = _phase2_export_figure_block(cp_fig, "informe_tecnico_phase1_cp_curve", "GrÃ¡fico de potencia y Cp", "GrÃ¡fico tÃ©cnico que muestra la potencia del aerogenerador y el coeficiente Cp calculado a partir de la definiciÃ³n actual de Fase 1.", "informe_tecnico_potencia_cp")
    phase1_section = {
        "id": "fase1_eleccion_aerogenerador",
        "title": _normalize_spanish_text("Fase 1 - ElecciÃ³n del aerogenerador"),
        "description": _normalize_spanish_text("SecciÃ³n dedicada a documentar el aerogenerador seleccionado, sus parÃ¡metros geomÃ©tricos y la base de desempeÃ±o usada para el resto del proyecto."),
        "subsections": [
            {"id": "datos_basicos_aerogenerador", "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"), "blocks": [{"type": "table", "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"), "description": _normalize_spanish_text("ParÃ¡metros geomÃ©tricos y fÃ­sicos base empleados para la caracterizaciÃ³n inicial del aerogenerador."), "headers": [_normalize_spanish_text("ParÃ¡metro"), _normalize_spanish_text("Valor")], "rows": [[_normalize_spanish_text("DiÃ¡metro del rotor"), f"{diametro:,.2f} m".replace(',', '')], [_normalize_spanish_text("Ãrea del rotor"), f"{area_rotor:,.2f} mÂ²".replace(',', '')], [_normalize_spanish_text("Densidad del aire"), f"{densidad:,.2f} kg/mÂ³".replace(',', '')]]}]},
            {"id": "tabla_velocidades_potencia", "title": _normalize_spanish_text("Tabla editable de velocidades y potencia"), "blocks": [speed_power_table] if speed_power_table else []},
            {"id": "grafico_potencia_cp", "title": _normalize_spanish_text("GrÃ¡fico de potencia y Cp"), "blocks": [cp_figure_block]},
            {"id": "tabla_cp_calculado", "title": _normalize_spanish_text("Tabla de Cp calculado"), "blocks": [cp_table] if cp_table else []},
        ],
    }

    sections = [phase1_section]
    if phase2_section:
        sections.append(phase2_section)
    report_model = {
        "document_id": "informe_tecnico",
        "title": _normalize_spanish_text("Informe tÃ©cnico"),
        "project_name": _normalize_spanish_text(project_name),
        "intro_paragraphs": [_normalize_spanish_text("Este documento presenta la configuraciÃ³n tÃ©cnica inicial del proyecto eÃ³lico y comienza con la definiciÃ³n del aerogenerador seleccionado y su base de desempeÃ±o.")],
        "sections": sections,
        "base_blocks": [],
        "word_master": {"available": False, "docx_bytes": None, "file_name": master_docx_name},
        "appended_sections": [phase2_section] if phase2_section else [],
        "master_source_name": master_docx_name,
        "master_source_used": False,
    }
    return normalize_text_deep(report_model)


def _word_direction_order():
    return [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]


def _word_table_block_from_dataframe(df, title, description, columns=None, rounding=None, table_family=""):
    payload = _informe_tecnico_table_from_dataframe(
        df.copy() if df is not None else pd.DataFrame(),
        title=title,
        description=description,
        columns=columns,
        decimals_map=rounding or {},
    )
    if not payload:
        return None
    payload["type"] = "table"
    payload["table_family"] = str(table_family or "")
    payload["title"] = _normalize_spanish_text(payload.get("title", title))
    payload["description"] = _normalize_spanish_text(payload.get("description", description))
    return payload


def _word_grid_4x4_block(sector_data, title, description, stem, kind="histogram"):
    """4x4 grid PNG block — kind in {'histogram', 'probability'}.

    sector_data: list of dicts with keys depending on kind:
      histogram: {'sector', 'velocities', 'k', 'c_weibull', 'c_rayleigh'}
      probability: {'sector', 'x', 'y_weibull', 'y_rayleigh', 'y_hist'}
    """
    try:
        import io
        import matplotlib.pyplot as plt
        import numpy as np
        from scipy import stats
    except ImportError:
        return None

    sectors_16 = list(_word_direction_order())
    fig, axes = plt.subplots(4, 4, figsize=(14, 12), dpi=130)
    axes = axes.flatten()
    by_sector = {d.get("sector"): d for d in sector_data}

    for i, sec in enumerate(sectors_16):
        ax = axes[i]
        d = by_sector.get(sec)
        ax.set_title(sec, fontsize=10, fontweight="bold", color="#1F4E79")
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.25, color="#E2E8F0")
        ax.spines[["top", "right"]].set_visible(False)
        if not d:
            ax.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                    transform=ax.transAxes, fontsize=8, color="gray")
            ax.set_xticks([]); ax.set_yticks([])
            continue
        if kind == "histogram":
            v = np.asarray(d.get("velocities", []), dtype=float)
            v = v[np.isfinite(v) & (v >= 0)]
            if len(v) == 0:
                ax.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                        transform=ax.transAxes, fontsize=8, color="gray")
                continue
            ax.hist(v, bins=20, density=True, color="#1F4E79",
                    alpha=0.55, edgecolor="white")
            try:
                k = float(d.get("k") or 2.0); c = float(d.get("c_weibull") or v.mean())
                xline = np.linspace(0, max(v.max(), 1.0), 120)
                ax.plot(xline, stats.weibull_min.pdf(xline, k, scale=c),
                        color="#D97706", lw=1.6, label=f"W k={k:.2f},c={c:.2f}")
            except Exception:
                pass
            try:
                cr = float(d.get("c_rayleigh") or v.mean())
                xline = np.linspace(0, max(v.max(), 1.0), 120)
                ax.plot(xline, stats.rayleigh.pdf(xline, scale=cr / np.sqrt(2)),
                        color="#1F6E3B", lw=1.4, ls="--", label=f"R c={cr:.2f}")
            except Exception:
                pass
            ax.legend(fontsize=6, loc="upper right")
            ax.set_xlabel("v (m/s)", fontsize=7)
        else:  # probability
            x = np.asarray(d.get("x", []), dtype=float)
            yw = np.asarray(d.get("y_weibull", []), dtype=float)
            yr = np.asarray(d.get("y_rayleigh", []), dtype=float)
            if len(x) == 0:
                ax.text(0.5, 0.5, "Sin datos", ha="center", va="center",
                        transform=ax.transAxes, fontsize=8, color="gray")
                continue
            if len(yw) == len(x):
                ax.plot(x, yw, color="#D97706", lw=1.6, label="Weibull")
            if len(yr) == len(x):
                ax.plot(x, yr, color="#1F6E3B", lw=1.4, ls="--", label="Rayleigh")
            ax.legend(fontsize=6, loc="upper right")
            ax.set_xlabel("v (m/s)", fontsize=7)
            ax.set_ylabel("p(v)", fontsize=7)

    fig.suptitle(title, fontsize=13, color="#1F4E79", fontweight="bold", y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    image_bytes = buf.getvalue()
    return {
        "type": "figure",
        "title": _normalize_spanish_text(title),
        "description": _normalize_spanish_text(description),
        "image_bytes": image_bytes,
        "image_format": "png",
        "file_name": f"{stem}.png",
        "figure_family": "phase3_histogram_grid" if kind == "histogram" else "phase35_probability_grid",
    }


def _word_export_figure_block(fig, figure_id, title, description, stem, figure_family="", export_options=None):
    image_bytes, metadata = export_plotly_figure_artifact(
        fig=fig,
        figure_id=figure_id,
        title=title,
        stem=stem,
        source_hint=description,
        preferred_format="png",
        export_options=export_options or {},
    )
    block = {
        "type": "figure",
        "title": _normalize_spanish_text(title),
        "description": _normalize_spanish_text(description),
        "image_bytes": None,
        "image_format": None,
        "file_name": None,
        "figure_family": str(figure_family or ""),
    }
    if image_bytes and str(metadata.get("export_format") or "").lower() == "png":
        block.update({
            "image_bytes": image_bytes,
            "image_format": "png",
            "file_name": metadata.get("file_name", f"{stem}.png"),
        })
    return block


def _word_chart_layout(fig, width, height, legend_horizontal=True, xgrid=True, ygrid=True):
    if fig is None:
        return fig
    fig.update_layout(
        width=int(width),
        height=int(height),
        template="plotly_white",
        margin=dict(l=70, r=40, t=80, b=70),
    )
    if legend_horizontal:
        fig.update_layout(
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5,
                bgcolor="rgba(255,255,255,0.88)",
            )
        )
    if xgrid:
        fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", zeroline=False)
    if ygrid:
        fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.10)", zeroline=False)
    return fig


def _safe_float(value, default=np.nan):
    try:
        return float(value)
    except Exception:
        return float(default)


def _word_selected_direction(config, fallback="N"):
    return str(
        config.get("f4_selected_sector")
        or config.get("f35_selected_sector")
        or config.get("f3_selected_sector")
        or fallback
    )


def _find_column(frame, candidates):
    if frame is None:
        return None
    def _norm(text):
        text = unicodedata.normalize("NFKD", str(text or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text.lower()
    columns = {str(col): str(col) for col in frame.columns}
    normalized = {_norm(col): str(col) for col in frame.columns}
    for candidate in candidates:
        if candidate in columns:
            return columns[candidate]
        lookup = _norm(candidate)
        if lookup in normalized:
            return normalized[lookup]
    return None


def _rename_columns_if_present(frame, mapping):
    renamed = frame.copy()
    rename_map = {}
    for canonical, candidates in (mapping or {}).items():
        found = _find_column(renamed, [canonical] + list(candidates))
        if found and found != canonical:
            rename_map[found] = canonical
    if rename_map:
        renamed = renamed.rename(columns=rename_map)
    return renamed


def _build_phase3_section(config, df_nasa):
    if df_nasa is None or len(df_nasa) == 0:
        return None

    from calculos import (
        construir_serie_viento_analisis,
        crear_histograma_sector_con_ajustes,
        crear_rosa_vientos_16,
        preparar_datos_rosa,
        resumir_sectores_rosa,
    )

    altura_deseada = float(config.get("perfil_hhub") or 80.0)
    modelo_f3 = str(config.get("f3_modelo_altura") or "Exponencial")
    direccion_f3 = str(config.get("f3_direccion_fuente") or "WD50M")
    roughness_f3 = str(config.get("f3_roughness_label") or "Grass / C?sped")
    df_f3, meta_f3 = construir_serie_viento_analisis(
        df_nasa=df_nasa,
        modelo=modelo_f3,
        altura_deseada=altura_deseada,
        roughness_label=roughness_f3,
        direccion_fuente=direccion_f3,
        roughness_options=ROUGHNESS_OPTIONS,
        output_speed_col="WS_ALTURA",
        output_direction_col="WD_USADA",
    )
    df_rosa_f3 = preparar_datos_rosa(df_f3, ws_col="WS_ALTURA", wd_col="WD_USADA")
    resumen_f3 = resumir_sectores_rosa(df_rosa_f3, ws_col="WS_ALTURA").copy()
    if len(resumen_f3) == 0:
        return None

    valid_records = int(pd.to_numeric(df_f3.get("WS_ALTURA"), errors="coerce").dropna().shape[0])
    mean_speed = float(pd.to_numeric(df_f3.get("WS_ALTURA"), errors="coerce").dropna().mean())
    sectors_with_data = int((pd.to_numeric(resumen_f3["Datos"], errors="coerce").fillna(0) > 0).sum())
    ustar_avg = "No disponible para este modelo"
    z0_avg = "No disponible para este modelo"
    if str(meta_f3.get("parametro_1_nombre") or "").lower().startswith("u*"):
        ustar_avg = f"{_safe_float(meta_f3.get('parametro_1_valor')):.2f}"
    if "z0" in str(meta_f3.get("parametro_2_nombre") or "").lower():
        z0_avg = f"{_safe_float(meta_f3.get('parametro_2_valor')):.2f}"
    elif "z0" in str(meta_f3.get("parametro_1_nombre") or "").lower():
        z0_avg = f"{_safe_float(meta_f3.get('parametro_1_valor')):.2f}"

    rose_fig = _word_chart_layout(
        crear_rosa_vientos_16(resumen_f3.copy()),
        860,
        760,
        legend_horizontal=False,
    )
    rose_fig.update_layout(title="Rosa de vientos para el modelo seleccionado")

    histogram_grid_data = []
    for sector in _word_direction_order():
        row = resumen_f3[resumen_f3["Sector"] == sector]
        if len(row) == 0 or int(row.iloc[0]["Datos"]) <= 0:
            continue
        velocidades = df_rosa_f3.loc[df_rosa_f3["Sector"] == sector, "WS_ALTURA"].dropna().to_numpy(dtype=float)
        histogram_grid_data.append({
            "sector": sector,
            "velocities": velocidades,
            "k": row.iloc[0]["k Weibull"],
            "c_weibull": row.iloc[0]["c Weibull (m/s)"],
            "c_rayleigh": row.iloc[0]["c Rayleigh (m/s)"],
        })
    histogram_grid_block = _word_grid_4x4_block(
        histogram_grid_data,
        title="Histogramas sectoriales (16 direcciones)",
        description="Grid 4x4 con histograma de velocidades + ajustes Weibull y Rayleigh por sector.",
        stem="word_fase3_histogramas_grid",
        kind="histogram",
    )
    histogram_blocks = [histogram_grid_block] if histogram_grid_block else []

    config_df = pd.DataFrame([
        {"Campo": "Altura deseada", "Valor": f"{altura_deseada:.2f} m"},
        {"Campo": "Modelo seleccionado", "Valor": modelo_f3},
        {"Campo": "Direcci?n usada", "Valor": direccion_f3},
        {"Campo": "Modelo combinado", "Valor": roughness_f3},
        {"Campo": "Registros v?lidos", "Valor": str(valid_records)},
        {"Campo": "Velocidad media", "Valor": f"{mean_speed:.2f} m/s"},
        {"Campo": "Sectores con datos", "Valor": str(sectors_with_data)},
        {"Campo": "u* promedio", "Valor": ustar_avg},
        {"Campo": "z0 efectiva promedio", "Valor": z0_avg},
    ])
    resumen_f3["Horas equivalentes anuales (h/a?o)"] = resumen_f3["Frecuencia (%)"] / 100.0 * 8760.0

    return {
        "id": "fase3_distribucion_direccional",
        "title": _normalize_spanish_text("Fase 3 - Distribuci?n direccional del viento"),
        "description": _normalize_spanish_text("Caracterizaci?n direccional del recurso e?lico a la altura y modelo seleccionados para el proyecto."),
        "subsections": [
            {
                "id": "fase3_configuracion",
                "title": _normalize_spanish_text("Configuraci?n de Fase 3"),
                "blocks": [
                    _word_table_block_from_dataframe(config_df, "Configuraci?n de Fase 3", "Resumen de la configuraci?n y de los indicadores base usados para la distribuci?n direccional del viento.", ["Campo", "Valor"], table_family="compact_summary"),
                ],
            },
            {
                "id": "fase3_rosa_vientos",
                "title": _normalize_spanish_text("Rosa de vientos"),
                "blocks": [
                    _word_export_figure_block(rose_fig, "word_phase3_wind_rose", "Rosa de vientos", "Rosa de vientos correspondiente al modelo seleccionado en Fase 3.", "word_fase3_rosa_vientos", figure_family="phase3_wind_rose", export_options={"width": 860, "height": 760, "max_dimension": 1600}),
                ],
            },
            {
                "id": "fase3_tabla_sectorial",
                "title": _normalize_spanish_text("Tabla sectorial completa"),
                "blocks": [
                    _word_table_block_from_dataframe(resumen_f3, "Tabla sectorial completa", "Resumen completo de frecuencias, ajuste estad?stico y horas equivalentes por sector.", list(resumen_f3.columns), table_family="wide_sector_table"),
                ],
            },
            {
                "id": "fase3_graficas_16_sectores",
                "title": _normalize_spanish_text("Gr?ficas de los 16 sectores"),
                "blocks": histogram_blocks,
            },
        ],
    }


def _build_phase35_section(config, df_nasa, df_curva_raw):
    if df_nasa is None or len(df_nasa) == 0:
        return None

    from calculos import (
        construir_serie_viento_analisis,
        inferir_puntos_operacion_curva,
        preparar_datos_curva,
        preparar_datos_rosa,
        resumir_sectores_rosa,
    )

    from .figuras import _build_probability_heatmap, _build_probability_sector_figure

    altura_deseada = float(config.get("perfil_hhub") or 80.0)
    modelo_f35 = str(config.get("f35_modelo") or config.get("f3_modelo_altura") or "Exponencial")
    direccion_f35 = str(config.get("f35_direccion_fuente") or config.get("f3_direccion_fuente") or "WD50M")
    roughness_f35 = str(config.get("f35_roughness_label") or config.get("f3_roughness_label") or "Grass / C?sped")
    vmax = float(config.get("f35_vmax") or 25.0)
    bin_width = float(config.get("f35_bin_width") or 0.5)
    mostrar_cdf = str(config.get("f35_show_cdf") or "False") == "True"
    curva_df = preparar_datos_curva(df_curva_raw)
    cut_in_inf, nominal_inf, cut_out_inf = inferir_puntos_operacion_curva(curva_df)
    cut_in = float(config.get("f35_cutin") or cut_in_inf)
    nominal = float(config.get("f35_nominal") or nominal_inf)
    cut_out = float(config.get("f35_cutout") or cut_out_inf)

    df_f35, _ = construir_serie_viento_analisis(
        df_nasa=df_nasa,
        modelo=modelo_f35,
        altura_deseada=altura_deseada,
        roughness_label=roughness_f35,
        direccion_fuente=direccion_f35,
        roughness_options=ROUGHNESS_OPTIONS,
        output_speed_col="WS_ANALISIS",
        output_direction_col="WD_USADA",
    )
    df_rosa_f35 = preparar_datos_rosa(df_f35, ws_col="WS_ANALISIS", wd_col="WD_USADA")
    resumen_f35 = resumir_sectores_rosa(df_rosa_f35, ws_col="WS_ANALISIS").copy()
    if len(resumen_f35) == 0:
        return None

    heatmap_fig, bins = _build_probability_heatmap(df_rosa_f35, vmax=vmax, bin_width=bin_width)
    heatmap_fig = _word_chart_layout(heatmap_fig, 980, 700, legend_horizontal=False)

    import numpy as np
    from scipy import stats

    probability_grid_data = []
    x_grid = np.linspace(0.05, vmax, 200)
    for sector in _word_direction_order():
        row = resumen_f35[resumen_f35["Sector"] == sector]
        if len(row) == 0 or int(row.iloc[0]["Datos"]) <= 0:
            continue
        try:
            k = float(row.iloc[0].get("k Weibull") or 2.0)
            c_w = float(row.iloc[0].get("c Weibull (m/s)") or 1.0)
            c_r = float(row.iloc[0].get("c Rayleigh (m/s)") or 1.0)
            y_w = stats.weibull_min.pdf(x_grid, k, scale=c_w)
            y_r = stats.rayleigh.pdf(x_grid, scale=c_r / np.sqrt(2))
        except Exception:
            y_w = np.zeros_like(x_grid)
            y_r = np.zeros_like(x_grid)
        probability_grid_data.append({
            "sector": sector,
            "x": x_grid,
            "y_weibull": y_w,
            "y_rayleigh": y_r,
        })
    curve_grid_block = _word_grid_4x4_block(
        probability_grid_data,
        title="Curvas de probabilidad por sector (16 direcciones)",
        description="Grid 4x4 con curva de probabilidad Weibull y Rayleigh por sector.",
        stem="word_fase35_curvas_grid",
        kind="probability",
    )
    curve_blocks = [curve_grid_block] if curve_grid_block else []

    return {
        "id": "fase35_probabilidad_ocurrencia",
        "title": _normalize_spanish_text("Fase 3.5 - Curva de probabilidad de ocurrencia"),
        "description": _normalize_spanish_text("Construcci?n de curvas de probabilidad de ocurrencia por sector y del mapa visual global para las 16 direcciones."),
        "subsections": [
            {
                "id": "fase35_curvas",
                "title": _normalize_spanish_text("Curvas de probabilidad por sector"),
                "blocks": curve_blocks,
            },
            {
                "id": "fase35_mapa_visual",
                "title": _normalize_spanish_text("Mapa visual para las 16 direcciones"),
                "blocks": [
                    _word_export_figure_block(heatmap_fig, "word_phase35_heatmap", "Mapa visual para las 16 direcciones", "Mapa de probabilidad de ocurrencia por intervalo y por sector para las 16 direcciones.", "word_fase35_mapa_probabilidad", figure_family="phase35_heatmap", export_options={"width": 980, "height": 700, "max_dimension": 1700}),
                ],
            },
        ],
    }


def _build_phase4_section(config, df_nasa, df_curva_raw, df_layout):
    if df_layout is None or len(df_layout) == 0 or df_nasa is None or len(df_nasa) == 0:
        return None

    from calculos import analizar_estelas_parque_16, crear_figura_direccion_estela, crear_figura_layout_parque

    from .figuras import _analyze_geometry_all_sectors, _build_phase4_wind_analysis

    diametro = float(config.get("diametro") or 100.0)
    ct = float(config.get("f4_ct") or 0.80)
    kw = float(config.get("f4_kw") or 0.05)
    velocidad_geom = float(config.get("f4_geom_speed") or 8.0)
    selected_sector = _word_selected_direction(config, fallback="N")
    df_f4_analisis, _ = _build_phase4_wind_analysis(df_nasa=df_nasa, config=config, roughness_options=ROUGHNESS_OPTIONS)
    if df_f4_analisis is None:
        return None

    resumen_geom, detalles_geom = _analyze_geometry_all_sectors(df_layout=df_layout, curva_df=df_curva_raw, diametro=diametro, ct=ct, kw=kw, velocidad_ref=velocidad_geom)
    resumen_anual, detalles_anual, _ = analizar_estelas_parque_16(df_layout=df_layout, df_nasa=df_f4_analisis, curva_df=df_curva_raw, diametro=diametro, ct=ct, kw=kw, ws_col="WS_ANALISIS", wd_col="WD_ANALISIS")
    if len(resumen_geom) == 0 or len(resumen_anual) == 0:
        return None
    resumen_geom = _rename_columns_if_present(resumen_geom, {
        "DirecciÃ³n centro (Â°)": ["Direcci?n centro (Ãƒâ€š?)"],
        "PÃ©rdida geomÃ©trica (%)": ["Perdida GeomÃ©trica (%)"],
    })
    resumen_anual = _rename_columns_if_present(resumen_anual, {
        "DirecciÃ³n centro (Â°)": ["Direcci?n centro (Ãƒâ€š?)"],
        "PÃ©rdida por estela (%)": ["P?rdida por estela (%)"],
        "PÃ©rdida ponderada (%)": ["P?rdida ponderada (%)"],
        "Horas equivalentes anuales (h/aÃ±o)": ["Horas equivalentes anuales (h/a?o)"],
        "Frecuencia (%)": [],
        "Sector": [],
        "Potencia parque sin estela (W)": [],
        "Potencia parque con estela (W)": [],
    }).copy()
    horas_col = _find_column(resumen_anual, ["Horas equivalentes anuales (h/ano)"])
    p_sin_col = _find_column(resumen_anual, ["Potencia parque sin estela (W)"])
    p_con_col = _find_column(resumen_anual, ["Potencia parque con estela (W)"])
    perdida_pond_col = _find_column(resumen_anual, ["Perdida ponderada (%)"])
    dir_centro_col = _find_column(resumen_geom, ["Direccion centro (Â°)"])
    dir_centro_anual_col = _find_column(resumen_anual, ["Direccion centro (Â°)"])
    perdida_sector_col = _find_column(resumen_anual, ["Perdida por estela (%)"])
    geom_loss_col = _find_column(resumen_geom, ["Perdida geometrica (%)"])
    dir_centro_col = dir_centro_col or (str(resumen_geom.columns[1]) if len(resumen_geom.columns) > 1 else None)
    geom_loss_col = geom_loss_col or (str(resumen_geom.columns[5]) if len(resumen_geom.columns) > 5 else None)
    dir_centro_anual_col = dir_centro_anual_col or (str(resumen_anual.columns[1]) if len(resumen_anual.columns) > 1 else None)
    horas_col = horas_col or (str(resumen_anual.columns[4]) if len(resumen_anual.columns) > 4 else None)
    p_sin_col = p_sin_col or (str(resumen_anual.columns[6]) if len(resumen_anual.columns) > 6 else None)
    p_con_col = p_con_col or (str(resumen_anual.columns[7]) if len(resumen_anual.columns) > 7 else None)
    perdida_sector_col = perdida_sector_col or (str(resumen_anual.columns[8]) if len(resumen_anual.columns) > 8 else None)
    perdida_pond_col = perdida_pond_col or (str(resumen_anual.columns[10]) if len(resumen_anual.columns) > 10 else None)
    resumen_anual["energy_gross_mwh"] = resumen_anual[p_sin_col] * resumen_anual[horas_col] / 1e6
    resumen_anual["energy_wake_mwh"] = resumen_anual[p_con_col] * resumen_anual[horas_col] / 1e6
    resumen_anual["energy_loss_mwh"] = resumen_anual["energy_gross_mwh"] - resumen_anual["energy_wake_mwh"]

    fig_layout = _word_chart_layout(
        crear_figura_layout_parque(df_layout=df_layout, diametro=diametro, titulo="Vista en planta del parque"),
        900,
        760,
        legend_horizontal=False,
    )

    resumen_geom_for_rose = resumen_geom.rename(
        columns={
            dir_centro_col: "Direcci?n centro (?)",
            geom_loss_col: "Perdida GeomÃ©trica (%)",
        }
    ).copy()
    resumen_anual_for_rose = resumen_anual.rename(
        columns={
            dir_centro_anual_col: "Direcci?n centro (?)",
            perdida_pond_col: "P?rdida ponderada (%)",
            perdida_sector_col: "P?rdida por estela (%)",
        }
    ).copy()

    fig_geom = _word_chart_layout(
        _create_phase4_geometric_rose(resumen_geom_for_rose),
        820,
        760,
        legend_horizontal=False,
    )
    fig_anual = _word_chart_layout(
        _create_phase4_annual_rose(resumen_anual_for_rose),
        820,
        760,
        legend_horizontal=False,
    )
    df_plot_compare = resumen_geom[["Sector", geom_loss_col]].merge(resumen_anual[["Sector", perdida_pond_col]], on="Sector", how="left")
    fig_compare = go.Figure()
    fig_compare.add_trace(go.Bar(x=df_plot_compare["Sector"], y=df_plot_compare[geom_loss_col], name="GeomÃ©trica (%)"))
    fig_compare.add_trace(go.Bar(x=df_plot_compare["Sector"], y=df_plot_compare[perdida_pond_col], name="Anual ponderada (%)"))
    fig_compare.update_layout(title="ComparaciÃ³n: criticidad geomÃ©trica vs criticidad anual", template="plotly_white", barmode="group", xaxis_title="Sector", yaxis_title="PÃ©rdida (%)")
    fig_compare = _word_chart_layout(fig_compare, 980, 700, legend_horizontal=True)
    fig_energy = go.Figure()
    fig_energy.add_trace(go.Bar(x=resumen_anual["Sector"], y=resumen_anual["energy_gross_mwh"], name="Bruta"))
    fig_energy.add_trace(go.Bar(x=resumen_anual["Sector"], y=resumen_anual["energy_wake_mwh"], name="Con estela"))
    fig_energy.update_layout(title="EnergÃ­a anual por direcciÃ³n", template="plotly_white", barmode="group", xaxis_title="Sector", yaxis_title="EnergÃ­a (MWh/aÃ±o)")
    fig_energy = _word_chart_layout(fig_energy, 980, 700, legend_horizontal=True)

    geom_indicators = pd.DataFrame([
        {"Indicador": "Direcciones analizadas", "Valor": str(len(resumen_geom))},
        {"Indicador": "Perdida GeomÃ©trica media", "Valor": f"{pd.to_numeric(resumen_geom[geom_loss_col], errors='coerce').mean():.2f}%"},
        {"Indicador": "Perdida GeomÃ©trica m?xima", "Valor": f"{pd.to_numeric(resumen_geom[geom_loss_col], errors='coerce').max():.2f}%"},
    ])
    annual_indicators = pd.DataFrame([
        {"Indicador": "Direcciones analizadas", "Valor": str(len(resumen_anual))},
        {"Indicador": "P?rdida ponderada media", "Valor": f"{pd.to_numeric(resumen_anual[perdida_pond_col], errors='coerce').mean():.2f}%"},
        {"Indicador": "Energ?a bruta total", "Valor": f"{pd.to_numeric(resumen_anual['energy_gross_mwh'], errors='coerce').sum():.2f} MWh/a?o"},
        {"Indicador": "Energ?a con estela total", "Valor": f"{pd.to_numeric(resumen_anual['energy_wake_mwh'], errors='coerce').sum():.2f} MWh/a?o"},
    ])

    detail_blocks = []
    row_sel_geom = resumen_geom[resumen_geom["Sector"] == selected_sector]
    row_sel_anual = resumen_anual[resumen_anual["Sector"] == selected_sector]
    df_detalle_geom = detalles_geom.get(selected_sector, pd.DataFrame())
    df_detalle_anual = detalles_anual.get(selected_sector, pd.DataFrame())
    if len(row_sel_geom) > 0:
        fig_sel_geom = _word_chart_layout(crear_figura_direccion_estela(df_detalle=df_detalle_geom, sector=selected_sector, direction_deg=float(row_sel_geom.iloc[0][dir_centro_col]), diametro=diametro), 860, 760, legend_horizontal=False)
        detail_blocks.append(_word_export_figure_block(fig_sel_geom, f"word_phase4_geom_detail_{selected_sector.lower()}", f"Detalle geom?trico - Direcci?n {selected_sector}", f"Detalle geom?trico del arreglo para la direcci?n actualmente seleccionada ({selected_sector}).", f"word_fase4_detalle_geom_{selected_sector.lower()}", figure_family="phase4_direction_detail", export_options={"width": 860, "height": 760, "max_dimension": 1700}))
    if len(df_detalle_geom) > 0:
        detail_blocks.append(_word_table_block_from_dataframe(df_detalle_geom[["turbina_id", "x_m", "y_m", "velocidad_libre", "velocidad_efectiva", "deficit_total", "perdida_potencia_pct", "potencia_base_W", "potencia_wake_W"]].copy(), f"Detalle geom?trico por turbina - Direcci?n {selected_sector}", "Detalle geom?trico por turbina para la direcci?n actualmente seleccionada.", table_family="phase4_detail_table"))
    if len(row_sel_anual) > 0:
        fig_sel_anual = _word_chart_layout(crear_figura_direccion_estela(df_detalle=df_detalle_anual, sector=selected_sector, direction_deg=float(row_sel_anual.iloc[0][dir_centro_anual_col]), diametro=diametro), 860, 760, legend_horizontal=False)
        detail_blocks.append(_word_export_figure_block(fig_sel_anual, f"word_phase4_annual_detail_{selected_sector.lower()}", f"Detalle anual - Direcci?n {selected_sector}", f"Detalle anual ponderado del arreglo para la direcci?n actualmente seleccionada ({selected_sector}).", f"word_fase4_detalle_anual_{selected_sector.lower()}", figure_family="phase4_direction_detail", export_options={"width": 860, "height": 760, "max_dimension": 1700}))
    if len(df_detalle_anual) > 0:
        detail_blocks.append(_word_table_block_from_dataframe(df_detalle_anual[["turbina_id", "x_m", "y_m", "velocidad_libre", "velocidad_efectiva", "deficit_total", "perdida_potencia_pct", "potencia_base_W", "potencia_wake_W"]].copy(), f"Detalle anual por turbina - Direcci?n {selected_sector}", "Detalle anual por turbina para la direcci?n actualmente seleccionada.", table_family="phase4_detail_table"))

    return {
        "id": "fase4_estelas_arreglo",
        "title": _normalize_spanish_text("Fase 4 - Estelas y arreglo del parque"),
        "description": _normalize_spanish_text("Documentaci?n del layout del parque y del an?lisis de estelas del proyecto."),
        "subsections": [
            {"id": "fase4_layout", "title": _normalize_spanish_text("Vista en planta del parque"), "blocks": [_word_export_figure_block(fig_layout, "word_phase4_layout", "Vista en planta del parque", "Vista en planta del parque con posiciones y rotor representado cuando est? disponible.", "word_fase4_layout", figure_family="phase4_layout", export_options={"width": 900, "height": 760, "max_dimension": 1700})]},
            {"id": "fase4_geom", "title": _normalize_spanish_text("AnÃ¡lisis geometrico puro del arreglo"), "blocks": [_word_export_figure_block(fig_geom, "word_phase4_geometric", "An?lisis geom?trico puro", "Distribuci?n polar de la criticidad geom?trica del arreglo.", "word_fase4_geometrico", figure_family="phase4_polar", export_options={"width": 820, "height": 760, "max_dimension": 1600}), _word_table_block_from_dataframe(geom_indicators, "Indicadores geom?tricos clave", "Indicadores resumidos del an?lisis geom?trico puro.", ["Indicador", "Valor"], table_family="compact_summary")]},
            {"id": "fase4_anual", "title": _normalize_spanish_text("Analisis anual ponderado"), "blocks": [_word_export_figure_block(fig_anual, "word_phase4_annual", "Analisis anual ponderado", "Distribuci?n polar de p?rdidas ponderadas y criticidad anual.", "word_fase4_anual", figure_family="phase4_polar", export_options={"width": 820, "height": 760, "max_dimension": 1600}), _word_table_block_from_dataframe(annual_indicators, "Indicadores anuales clave", "Indicadores resumidos del Analisis anual ponderado.", ["Indicador", "Valor"], table_family="compact_summary")]},
            {"id": "fase4_comparacion", "title": _normalize_spanish_text("Comparaci?n criticidad geom?trica vs criticidad anual"), "blocks": [_word_export_figure_block(fig_compare, "word_phase4_compare", "Comparaci?n criticidad geom?trica vs criticidad anual", "Comparaci?n directa entre la criticidad geom?trica y la criticidad anual ponderada por direcci?n.", "word_fase4_comparacion", figure_family="phase4_comparison", export_options={"width": 980, "height": 700, "max_dimension": 1700})]},
            {"id": "fase4_energia", "title": _normalize_spanish_text("Energ?a anual por direcci?n"), "blocks": [_word_export_figure_block(fig_energy, "word_phase4_energy", "Energ?a anual por direcci?n", "Comparaci?n de energ?a bruta y energ?a con estela por direcci?n.", "word_fase4_energia", figure_family="phase4_energy", export_options={"width": 980, "height": 700, "max_dimension": 1700})]},
            {"id": "fase4_detalle_direccion", "title": _normalize_spanish_text("Detalle por direcci?n"), "blocks": detail_blocks},
        ],
    }


def _build_phase5_section(config, phase5_context):
    phase5_context = phase5_context or {}
    df_sector = phase5_context.get("df_aep_sector")
    tabla_perdidas = phase5_context.get("tabla_perdidas")
    summary = phase5_context.get("summary") or {}
    method_label = str(phase5_context.get("method_label") or "Weibull")
    fig_loss = phase5_context.get("fig_loss_distribution")
    fig_sector = phase5_context.get("fig_sectorial")
    if df_sector is None or len(df_sector) == 0:
        return None

    summary_df = pd.DataFrame([
        {"Indicador": "AEP bruta", "Valor": f"{_safe_float(summary.get('aep_bruta_total')):.2f} MWh/a?o"},
        {"Indicador": "AEP neta", "Valor": f"{_safe_float(summary.get('aep_neta_total')):.2f} MWh/a?o"},
        {"Indicador": "Factor de planta bruto", "Valor": f"{_safe_float(summary.get('factor_planta_bruto')):.2f}%"},
        {"Indicador": "Factor de planta neto", "Valor": f"{_safe_float(summary.get('factor_planta_neto')):.2f}%"},
        {"Indicador": "Potencia nominal por turbina", "Valor": f"{_safe_float(summary.get('potencia_nominal_turbina_kw')):.2f} kW"},
        {"Indicador": "N?mero de turbinas", "Valor": str(int(summary.get('n_turbinas') or 0))},
    ])

    loss_blocks = []
    if fig_loss is not None:
        fig_loss = _word_chart_layout(fig_loss, 820, 700, legend_horizontal=False)
        loss_blocks.append(_word_export_figure_block(fig_loss, "word_phase5_loss_distribution", f"Distribuci?n de p?rdidas ({method_label})", f"Distribuci?n relativa de p?rdidas energ?ticas para el escenario {method_label}.", "word_fase5_distribucion_perdidas", figure_family="phase5_loss_distribution", export_options={"width": 820, "height": 700, "max_dimension": 1600}))
    if tabla_perdidas is not None and len(tabla_perdidas) > 0:
        loss_blocks.append(_word_table_block_from_dataframe(tabla_perdidas, "Tabla de p?rdidas energ?ticas", "Detalle de p?rdidas energ?ticas por concepto para el escenario evaluado.", table_family="compact_summary"))

    sector_result_blocks = [_word_table_block_from_dataframe(df_sector, "Resultados por sector", "Tabla completa de resultados energ?ticos por sector.", table_family="phase5_sector_table")]
    aep_sector_blocks = []
    if fig_sector is not None:
        fig_sector = _word_chart_layout(fig_sector, 980, 700, legend_horizontal=True)
        aep_sector_blocks.append(_word_export_figure_block(fig_sector, "word_phase5_aep_sector", f"AEP por sector ({method_label})", f"Comparaci?n de AEP bruto y neto por sector para el escenario {method_label}.", "word_fase5_aep_sector", figure_family="phase5_sector_chart", export_options={"width": 980, "height": 700, "max_dimension": 1700}))

    return {
        "id": "fase5_resultados_energeticos",
        "title": _normalize_spanish_text("Fase 5 - Resultados energ?ticos"),
        "description": _normalize_spanish_text("Resultados energ?ticos consolidados del proyecto, incluyendo AEP, factor de planta y distribuci?n de p?rdidas."),
        "subsections": [
            {"id": "fase5_resultados_principales", "title": _normalize_spanish_text("Resultados principales"), "blocks": [_word_table_block_from_dataframe(summary_df, "Resultados principales", "Indicadores principales disponibles en Fase 5 para el escenario energ?tico actual.", ["Indicador", "Valor"], table_family="compact_summary")]},
            {"id": "fase5_perdidas", "title": _normalize_spanish_text(f"Distribuci?n de p?rdidas ({method_label})"), "blocks": loss_blocks},
            {"id": "fase5_resultados_sector", "title": _normalize_spanish_text("Resultados por sector"), "blocks": sector_result_blocks},
            {"id": "fase5_aep_sector", "title": _normalize_spanish_text(f"AEP por sector ({method_label})"), "blocks": aep_sector_blocks},
        ],
    }


def _sf_local(v, default=0.0):
    try:
        f = float(v)
        if f != f or f == float("inf") or f == float("-inf"):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _build_executive_summary_section(project_name, config, phase5_context):
    """Resumen ejecutivo lightweight para INFORME TECNICO (no bankable).

    Solo KPIs basicos: AEP bruto/neto, factor planta, n_turbinas, perdidas totales.
    NO incluye P50/P90 (eso es bankable).
    """
    phase5_context = phase5_context or {}
    summary = phase5_context.get("summary") or {}
    method_label = str(phase5_context.get("method_label") or "Weibull")
    aep_b = _sf_local(summary.get("aep_bruta_total"))
    aep_n = _sf_local(summary.get("aep_neta_total"))
    fp_b = _sf_local(summary.get("factor_planta_bruto"))
    fp_n = _sf_local(summary.get("factor_planta_neto"))
    p_kw = _sf_local(summary.get("potencia_nominal_turbina_kw"))
    n_t = int(summary.get("n_turbinas") or 0)
    p_inst_mw = (p_kw * n_t / 1000.0) if (p_kw and n_t) else 0.0
    perdidas = (aep_b - aep_n) if (aep_b and aep_n) else 0.0
    perdidas_pct = (perdidas / aep_b * 100.0) if aep_b else 0.0
    rows = [
        ["Proyecto", str(project_name)],
        ["Sitio", f"Lat {config.get('nasa_lat', '—')}, Lon {config.get('nasa_lon', '—')}"],
        ["Periodo de datos", f"{config.get('nasa_inicio', '—')} a {config.get('nasa_fin', '—')}"],
        ["Aerogeneradores", f"{n_t} turbinas"],
        ["Potencia nominal por turbina", f"{p_kw:,.0f} kW".replace(",", ".") if p_kw else "—"],
        ["Potencia instalada total", f"{p_inst_mw:,.2f} MW" if p_inst_mw else "—"],
        ["Metodo estadistico", method_label],
        ["AEP bruta parque", f"{aep_b:,.0f} MWh/año".replace(",", ".") if aep_b else "—"],
        ["AEP neta parque", f"{aep_n:,.0f} MWh/año".replace(",", ".") if aep_n else "—"],
        ["Perdidas totales", f"{perdidas:,.0f} MWh/año ({perdidas_pct:.2f} %)".replace(",", ".") if perdidas else "—"],
        ["Factor de planta bruto", f"{fp_b:.2f} %" if fp_b else "—"],
        ["Factor de planta neto", f"{fp_n:.2f} %" if fp_n else "—"],
    ]
    return {
        "id": "resumen_ejecutivo",
        "title": _normalize_spanish_text("Resumen ejecutivo"),
        "description": _normalize_spanish_text(
            "Resumen de alto nivel con los principales indicadores tecnicos del proyecto. "
            "Para indicadores bankable (P50/P75/P90, NPV, IRR, LCOE detallado, IEC 61400-15-2, risk register) "
            "genere el Reporte BANKABLE desde el modulo dedicado."
        ),
        "subsections": [
            {
                "id": "exec_kpis",
                "title": _normalize_spanish_text("Indicadores principales"),
                "blocks": [
                    {
                        "type": "table",
                        "title": _normalize_spanish_text("Resumen tecnico del proyecto"),
                        "description": _normalize_spanish_text("Indicadores claves del estudio tecnico, agregados por fases."),
                        "headers": [_normalize_spanish_text("Concepto"), _normalize_spanish_text("Valor")],
                        "rows": rows,
                    },
                ],
            },
        ],
    }


def _build_phase6_section(config, phase5_context):
    """Fase 6 - Exportacion y manifiesto del informe tecnico.

    Cierra el ciclo: documenta config de exportacion, formatos generados, LCOE
    basico (si disponible), y manifiesto de trazabilidad sin overlap con bankable.
    """
    from datetime import UTC, datetime
    phase5_context = phase5_context or {}
    summary = phase5_context.get("summary") or {}
    lcoe = _sf_local(summary.get("lcoe_mwh"))
    moneda = str(summary.get("unidad_monetaria") or "USD")
    aep_n = _sf_local(summary.get("aep_neta_total"))
    fecha = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    export_rows = [
        ["Documento generado", "Informe tecnico exploratorio por fases"],
        ["Formatos disponibles", "PDF + Word (.docx) + Excel/CSV + JSON"],
        ["Fuente datos meteo", str(config.get("nasa_fuente") or "NASA POWER API")],
        ["Periodo analisis", f"{config.get('nasa_inicio', '—')} a {config.get('nasa_fin', '—')}"],
        ["Generado en (UTC)", fecha],
        ["Herramienta", "SMA 2.0 — modo informe tecnico"],
        ["Diferencia vs bankable", "Sin P50/P90, sin IEC 61400-15-2, sin risk register, sin cash flow"],
    ]
    if lcoe:
        export_rows.insert(5, ["LCOE estimado", f"{lcoe:.2f} {moneda}/MWh"])

    blocks_main = [{
        "type": "table",
        "title": _normalize_spanish_text("Configuracion de exportacion"),
        "description": _normalize_spanish_text("Resumen de los formatos generados y trazabilidad del informe tecnico."),
        "headers": [_normalize_spanish_text("Campo"), _normalize_spanish_text("Valor")],
        "rows": export_rows,
    }]

    next_steps_rows = [
        ["1. Validar Fase 2", "Confirmar que NASA POWER cubre el periodo de interes y revisar perfil vertical"],
        ["2. Validar Fase 3", "Verificar rosa de vientos y ajuste Weibull por sector"],
        ["3. Refinar Fase 4", "Iterar layout para minimizar perdidas por estela"],
        ["4. Cerrar Fase 5", "Confirmar perdidas (disp, electricas, otras) con O&M y eléctrico"],
        ["5. Bankable", "Para FID / project finance, generar Reporte BANKABLE separado"],
        ["6. Validacion 3a parte", "EYA bankable con consultor certificado (WAsP / WindPRO / OpenWind)"],
    ]
    blocks_next = [{
        "type": "table",
        "title": _normalize_spanish_text("Proximos pasos recomendados"),
        "description": _normalize_spanish_text("Plan de trabajo sugerido para evolucionar del informe tecnico a un EYA bankable."),
        "headers": [_normalize_spanish_text("Paso"), _normalize_spanish_text("Accion")],
        "rows": next_steps_rows,
    }]

    return {
        "id": "fase6_exportacion",
        "title": _normalize_spanish_text("Fase 6 - Exportacion y cierre del informe"),
        "description": _normalize_spanish_text(
            "Cierre formal del informe tecnico: configuracion de exportacion, trazabilidad y proximos pasos. "
            "Esta fase NO incluye analisis economico bankable (CAPEX/OPEX/NPV/LCOE detallado). "
            "Para project finance use el modulo 'Reporte BANKABLE' en Fase 6 de la app."
        ),
        "subsections": [
            {"id": "fase6_config_export", "title": _normalize_spanish_text("Configuracion de exportacion"), "blocks": blocks_main},
            {"id": "fase6_next_steps", "title": _normalize_spanish_text("Proximos pasos y recomendaciones"), "blocks": blocks_next},
        ],
    }


def _build_informe_cover_section(project_name, config):
    """Cover diferenciada para INFORME TECNICO (vs reporte bankable).

    Color teal/verde + subtitulo 'Analisis exploratorio por fases' para
    contrastar con bankable navy + 'Evaluacion bankable para project finance'.
    """
    from datetime import UTC, datetime
    fecha = datetime.now(UTC).strftime("%Y-%m-%d")
    cover_rows = [
        ["Documento", "Informe tecnico — Analisis exploratorio"],
        ["Proyecto", str(project_name)],
        ["Tipo de informe", "Tecnico-descriptivo (no bankable)"],
        ["Audiencia", "Equipo de ingenieria / soporte interno"],
        ["Estructura", "Por fases del estudio (Fase 1 a Fase 5)"],
        ["Latitud / Longitud", f"{config.get('nasa_lat', '—')}, {config.get('nasa_lon', '—')}"],
        ["Periodo", f"{config.get('nasa_inicio', '—')} a {config.get('nasa_fin', '—')}"],
        ["Fuente datos", "NASA POWER API"],
        ["Generado (UTC)", fecha],
        ["Herramienta", "SMA 2.0 — modo INFORME TECNICO"],
        ["Diferencia con bankable", "Este informe NO incluye P50/P75/P90, ni IEC 61400-15-2, ni analisis economico CAPEX/OPEX, ni risk register. Para evaluacion bankable use el modulo 'Reporte BANKABLE' en Fase 6."],
    ]
    return {
        "id": "cover_informe_tecnico",
        "title": _normalize_spanish_text("INFORME TECNICO — Analisis exploratorio por fases"),
        "description": _normalize_spanish_text(
            "Documento tecnico-descriptivo del proyecto eolico organizado por fases del estudio. "
            "Sirve como soporte interno para revisar configuracion, recurso eolico, estelas y "
            "resultados energeticos. NO sustituye el Reporte BANKABLE para project finance."
        ),
        "subsections": [
            {
                "id": "cover_informe_metadata",
                "title": _normalize_spanish_text("Identificacion del documento"),
                "blocks": [
                    {
                        "type": "table",
                        "title": _normalize_spanish_text("Datos del informe"),
                        "description": _normalize_spanish_text("Metadatos generales del informe tecnico exploratorio."),
                        "headers": [_normalize_spanish_text("Campo"), _normalize_spanish_text("Valor")],
                        "rows": cover_rows,
                    },
                ],
            },
        ],
    }


def build_informe_tecnico_word_model(config=None, project_name="", df_curva_raw=None, df_nasa=None, df_layout=None, master_docx_bytes=None, master_docx_name="informe_tecnico editado por mi.docx", phase5_context=None):
    config = config or {}
    project_name = str(project_name or config.get("project_name") or "Proyecto eolico").strip() or "Proyecto eolico"
    word_master = load_informe_tecnico_master_docx(master_docx_bytes, file_name=master_docx_name)
    cover_section = _build_informe_cover_section(project_name, config)
    exec_summary_section = _build_executive_summary_section(project_name, config, phase5_context)
    phase6_section = _build_phase6_section(config, phase5_context)
    appended_sections = [
        section for section in [
            _build_phase3_section(config=config, df_nasa=df_nasa),
            _build_phase35_section(config=config, df_nasa=df_nasa, df_curva_raw=df_curva_raw),
            _build_phase4_section(config=config, df_nasa=df_nasa, df_curva_raw=df_curva_raw, df_layout=df_layout),
            _build_phase5_section(config=config, phase5_context=phase5_context),
            phase6_section,
        ]
        if section
    ]

    informe_title = _normalize_spanish_text("INFORME TECNICO — Analisis exploratorio por fases")
    informe_intro = [
        _normalize_spanish_text(
            f"Proyecto: {project_name}. Documento tecnico-descriptivo organizado por fases "
            f"del estudio. Foco: configuracion del aerogenerador, recurso eolico, "
            f"distribucion direccional, estelas y resultados energeticos sin pretensiones "
            f"de bankability."
        ),
        _normalize_spanish_text(
            "AVISO: Este informe NO es un EYA bankable. No contiene Monte Carlo P50/P75/P90, "
            "ni analisis IEC 61400-15-2 de incertidumbre, ni analisis economico CAPEX/OPEX, "
            "ni risk register. Para soportar decision de inversion (FID, project finance) "
            "genere el 'Reporte BANKABLE' desde la misma Fase 6."
        ),
    ]

    if word_master.get("available"):
        sections = [cover_section, exec_summary_section] + list(word_master.get("sections", []) or [])
        sections.extend(appended_sections)
        report_model = {
            "document_id": "informe_tecnico",
            "title": informe_title,
            "project_name": _normalize_spanish_text(project_name),
            "intro_paragraphs": informe_intro,
            "sections": sections,
            "base_blocks": word_master.get("base_blocks", []),
            "word_master": word_master,
            "appended_sections": appended_sections,
            "master_source_name": word_master.get("file_name", master_docx_name),
            "master_source_used": True,
        }
        return normalize_text_deep(report_model)

    base_model = build_informe_tecnico_model(
        config=config,
        project_name=project_name,
        df_curva_raw=df_curva_raw,
        df_nasa=df_nasa,
        master_docx_bytes=None,
        master_docx_name=master_docx_name,
    )
    base_sections = list(base_model.get("sections", []) or [])
    base_model["title"] = informe_title
    base_model["intro_paragraphs"] = informe_intro
    base_model["sections"] = [cover_section, exec_summary_section] + base_sections + appended_sections
    base_model["appended_sections"] = appended_sections
    return normalize_text_deep(base_model)

