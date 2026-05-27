from math import pi

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .contexto import get_export_metadata, get_project_context, get_report_context
from .texto import normalize_spanish_text as _normalize_spanish_text


def _clean_figure_note(value):
    text = _normalize_spanish_text(value).strip()
    if not text:
        return ""
    boilerplate_fragments = [
        "Figura de ubicaci\u00f3n generada desde las coordenadas persistidas",
        "Mapa del sitio exportado como PNG can\u00f3nico",
        "Usar el artefacto exportado si est\u00e1 disponible",
        "Figura exportada como PNG est\u00e1tico mediante fallback compatible con matplotlib",
        "Artefacto reconstruido desde la configuraci\u00f3n persistida",
        "Complementa la discusi\u00f3n de distribuci\u00f3n por rangos y sectores",
        "Representa el arreglo actual del parque y sirve como base para documentar estelas",
        "Figura recomendada para reforzar la interpretaci\u00f3n de resultados energ\u00e9ticos",
        "Insertar si la discusi\u00f3n de sensibilidad forma parte del reporte final",
        "Mapa del sitio exportado como png can\u00f3nico",
        "Figura de ubicacion generada desde las coordenadas persistidas",
        "Artefacto reconstruido desde la configuracion persistida",
        "Complementa la discusion de distribucion por rangos y sectores",
    ]
    lowered = text.lower()
    if any(fragment.lower() in lowered for fragment in boilerplate_fragments):
        return ""
    return text


def _report_has_value(value):
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def _format_report_metric(value, decimals=2, unit=""):
    if not _report_has_value(value):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
        txt = f"{float(value):.{decimals}f}"
    else:
        txt = _normalize_spanish_text(value)
    return _normalize_spanish_text(f"{txt} {unit}".strip())


def _build_key_value_table(title, entries, note=""):
    rows = []
    for label, value in entries:
        if _report_has_value(value):
            rows.append([_normalize_spanish_text(label), _normalize_spanish_text(value)])
    if not rows:
        return None
    table = {
        "title": _normalize_spanish_text(title),
        "headers": ["Campo", "Valor"],
        "rows": rows,
    }


INFORME_TECNICO_ROUGHNESS_OPTIONS = {
    "Water / Mar": 2e-4,
    "Snow / Nieve": 1e-3,
    "Grass / CÃ©sped": 0.03,
    "Farmland / Cultivo": 0.10,
    "Forest / Bosque": 0.80,
    "City / Ciudad": 1.00,
}


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
            )
        )
    fig.add_trace(go.Scatter(x=[v_exp], y=[altura_deseada], mode="markers", name="Objetivo exp.", marker=dict(size=10, color="#3366ff")))
    fig.add_trace(go.Scatter(x=[v_log_a], y=[altura_deseada], mode="markers", name="Objetivo log A", marker=dict(size=10, color="#ff5533", symbol="diamond")))
    fig.add_trace(go.Scatter(x=[v_log_b], y=[altura_deseada], mode="markers", name="Objetivo promedio", marker=dict(size=10, color="#2ca25f", symbol="square")))
    fig.add_hline(y=float(altura_deseada), line_dash="dot", line_color="gray")
    fig.update_layout(template="plotly_white", height=620, margin=dict(l=40, r=40, t=60, b=40), xaxis_title="Velocidad del viento (m/s)", yaxis_title="Altura (m)", title="ComparaciÃ³n entre perfiles verticales")
    if yaxis_type == "log":
        fig.update_yaxes(type="log", title_text="Altura (m)")
        fig.update_layout(title="ComparaciÃ³n entre perfiles verticales en escala logarÃ­tmica")
    return fig


def _phase2_export_figure_block(fig, figure_id, title, description, stem):
    from reportes.figuras import export_plotly_figure_artifact

    image_bytes, metadata = export_plotly_figure_artifact(fig=fig, figure_id=figure_id, title=title, stem=stem, source_hint=description, preferred_format="png")
    block = {"type": "figure", "title": _normalize_spanish_text(title), "description": _normalize_spanish_text(description), "image_bytes": None, "image_format": None, "file_name": None}
    if image_bytes and str(metadata.get("export_format") or "").lower() == "png":
        block.update({"image_bytes": image_bytes, "image_format": "png", "file_name": metadata.get("file_name", f"{stem}.png")})
    return block


def _build_informe_tecnico_phase2_section(config=None, project_name="", df_nasa=None):
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
    from reportes.figuras import build_site_map_bundle

    latitude = config.get("nasa_lat")
    longitude = config.get("nasa_lon")
    start_date = config.get("nasa_inicio")
    end_date = config.get("nasa_fin")
    roughness_label = str(config.get("perfil_roughness_label") or "Grass / CÃ©sped")
    altura_deseada = float(config.get("perfil_hhub") or 80.0)
    z0_teorica = float(INFORME_TECNICO_ROUGHNESS_OPTIONS.get(roughness_label, 0.03))

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
                    {"type": "table", "title": _normalize_spanish_text("UbicaciÃ³n y consulta NASA POWER"), "description": _normalize_spanish_text("Datos geogrÃ¡ficos y temporales de la consulta NASA POWER usada para caracterizar el sitio."), "headers": ["Campo", "Valor"], "rows": [["Latitud", f"{float(latitude):.4f}" if latitude not in [None, ""] else "Sin dato"], ["Longitud", f"{float(longitude):.4f}" if longitude not in [None, ""] else "Sin dato"], ["Fecha inicial", str(start_date or "Sin dato")], ["Fecha final", str(end_date or "Sin dato")]]},
                ],
            },
            {
                "id": "fase2_resumen_horario",
                "title": _normalize_spanish_text("Resumen de datos horarios guardados"),
                "blocks": [
                    {"type": "table", "title": _normalize_spanish_text("Resumen de datos horarios guardados"), "description": _normalize_spanish_text("Resumen estadÃ­stico base de la serie horaria almacenada para el sitio seleccionado."), "headers": ["Concepto", "Valor"], "rows": [["Registros horarios", str(len(df_nasa))], ["Promedio WS10M", f"{v10:.2f} m/s"], ["Promedio WS50M", f"{v50:.2f} m/s"], ["Promedio WD10M", f"{float(df_nasa['WD10M'].dropna().mean()):.2f}Â°" if len(df_nasa['WD10M'].dropna()) > 0 else "Sin dato"]]},
                    _phase2_export_figure_block(fig=crear_grafica_nasa_hourly(df_nasa), figure_id="informe_tecnico_phase2_nasa_hourly", title="Serie horaria de velocidades", description="Serie horaria de velocidades del viento registrada en los datos horarios guardados para el sitio.", stem="informe_tecnico_fase2_serie_horaria"),
                ],
            },
            {
                "id": "fase2_perfiles_verticales",
                "title": _normalize_spanish_text("Perfiles verticales del viento"),
                "blocks": [
                    _phase2_export_figure_block(fig=crear_grafica_perfil_individual(df_exp, "Perfil exponencial ajustado con 10 m y 50 m", "Perfil exponencial", altura_objetivo=altura_deseada, v_objetivo=v_exp_deseada, color="#3366ff", yaxis_type="linear", puntos_medidos=puntos_medidos), figure_id="informe_tecnico_phase2_perfil_exp", title="Perfil exponencial", description="Perfil vertical exponencial calculado a partir de las velocidades medias a 10 m y 50 m.", stem="informe_tecnico_fase2_perfil_exponencial"),
                    _phase2_export_figure_block(fig=crear_grafica_perfil_individual(df_log_a, "Perfil logarÃ­tmico modo A - ajustado con 10 m y 50 m", "Perfil logarÃ­tmico A", altura_objetivo=altura_deseada, v_objetivo=v_log_a_deseada, color="#ff5533", dash="dash", yaxis_type="log", puntos_medidos=puntos_medidos), figure_id="informe_tecnico_phase2_perfil_log_a", title="Perfil logarÃ­tmico modo A", description="Perfil logarÃ­tmico ajustado directamente con los puntos medidos en 10 m y 50 m.", stem="informe_tecnico_fase2_perfil_log_a"),
                    _phase2_export_figure_block(fig=crear_grafica_perfil_individual(df_log_b, "Promedio Log-Exp", "Promedio Log-Exp", altura_objetivo=altura_deseada, v_objetivo=v_log_b_deseada, color="#2ca25f", dash="dot", yaxis_type="log", puntos_medidos=puntos_medidos), figure_id="informe_tecnico_phase2_perfil_log_b", title="Promedio Log-Exp", description="Perfil operativo construido como promedio entre el perfil exponencial y el perfil logar??tmico A.", stem="informe_tecnico_fase2_promedio_log_exp"),
                    _phase2_export_figure_block(fig=_build_phase2_compare_figure(df_exp, df_log_a, df_log_b, altura_deseada, v_exp_deseada, v_log_a_deseada, v_log_b_deseada, puntos_medidos, yaxis_type="linear"), figure_id="informe_tecnico_phase2_compare_linear", title="ComparaciÃ³n entre perfiles en escala normal", description="ComparaciÃ³n de los perfiles verticales en escala normal para contrastar los tres enfoques de extrapolaciÃ³n.", stem="informe_tecnico_fase2_comparacion_normal"),
                    _phase2_export_figure_block(fig=_build_phase2_compare_figure(df_exp, df_log_a, df_log_b, altura_deseada, v_exp_deseada, v_log_a_deseada, v_log_b_deseada, puntos_medidos, yaxis_type="log"), figure_id="informe_tecnico_phase2_compare_log", title="ComparaciÃ³n entre perfiles en escala logarÃ­tmica", description="ComparaciÃ³n de los perfiles verticales usando escala logarÃ­tmica en altura para resaltar diferencias de comportamiento.", stem="informe_tecnico_fase2_comparacion_log"),
                    {"type": "table", "title": _normalize_spanish_text("Tabla resumen de perfiles"), "description": _normalize_spanish_text("Resumen num??rico de los par??metros y velocidades representativas obtenidas en la caracterizaci??n vertical del viento."), "headers": ["Concepto", "Valor"], "rows": [["Velocidad media a 10 m", f"{v10:.4f}"], ["Velocidad media a 50 m", f"{v50:.4f}"], ["Alpha exponencial", f"{alpha:.6f}"], ["u* modo A", f"{float(u_star_a):.6f}"], ["z0 modo A ajustada", f"{float(z0_ajustada):.6f}"], ["Velocidad a altura deseada - Exponencial", f"{v_exp_deseada:.4f}"], ["Velocidad a altura deseada - Log A", f"{v_log_a_deseada:.4f}"], ["Velocidad a altura deseada - Promedio Log-Exp", f"{v_log_b_deseada:.4f}"]]},
                ],
            },
        ],
    }


def build_informe_tecnico_model(config=None, project_name="", df_curva_raw=None, df_nasa=None, master_docx_bytes=None, master_docx_name="informe_tecnico editado por mi.docx"):
    config = config or {}
    project_name = str(project_name or config.get("project_name") or "Proyecto eolico").strip() or "Proyecto eolico"

    from calculos import calcular_cp, crear_grafica_curva, preparar_datos_curva
    from reportes.docx import load_informe_tecnico_master_docx
    from reportes.figuras import export_plotly_figure_artifact

    word_master = load_informe_tecnico_master_docx(master_docx_bytes, file_name=master_docx_name)
    phase2_section = _build_informe_tecnico_phase2_section(config=config, project_name=project_name, df_nasa=df_nasa)
    if word_master.get("available"):
        sections = list(word_master.get("sections", []) or [])
        if phase2_section:
            sections.append(phase2_section)
        return {"document_id": "informe_tecnico", "title": word_master.get("title") or _normalize_spanish_text("Informe tÃ©cnico"), "project_name": word_master.get("project_name") or _normalize_spanish_text(project_name), "intro_paragraphs": word_master.get("intro_paragraphs", []), "sections": sections, "base_blocks": word_master.get("base_blocks", []), "word_master": word_master, "appended_sections": [phase2_section] if phase2_section else [], "master_source_name": word_master.get("file_name", master_docx_name), "master_source_used": True}

    diametro = float(config.get("diametro") or 100.0)
    densidad = float(config.get("densidad") or 1.225)
    area_rotor = pi * (diametro / 2.0) ** 2
    df_curva = preparar_datos_curva(df_curva_raw)
    df_curva = df_curva.copy() if df_curva is not None else pd.DataFrame()
    df_cp = calcular_cp(df_curva, densidad, area_rotor).copy() if len(df_curva) > 0 else pd.DataFrame()
    speed_power_table = _informe_tecnico_table_from_dataframe(df_curva, "Tabla editable de velocidades y potencia", "Tabla base de velocidades y potencia actualmente definida para el aerogenerador seleccionado en Fase 1.", ["Velocidad_num", "Potencia_W"], {"Velocidad_num": 2, "Potencia_W": 2})
    if speed_power_table:
        speed_power_table["headers"] = ["Velocidad (m/s)", "Potencia (W)"]
    cp_table = _informe_tecnico_table_from_dataframe(df_cp.rename(columns={"Velocidad_num": "Velocidad (m/s)", "Potencia_W": "Potencia (W)", "P_viento_W": "Potencia del viento (W)", "Cp": "Cp"}), "Tabla de Cp calculado", "Tabla derivada de la curva de potencia actual para documentar el coeficiente de potencia calculado en cada velocidad.", ["Velocidad (m/s)", "Potencia (W)", "Potencia del viento (W)", "Cp"], {"Velocidad (m/s)": 2, "Potencia (W)": 2, "Potencia del viento (W)": 2, "Cp": 4})
    cp_figure_block = {"type": "figure", "title": _normalize_spanish_text("GrÃ¡fico de potencia y Cp"), "description": _normalize_spanish_text("GrÃ¡fico tÃ©cnico que muestra la potencia del aerogenerador y el coeficiente Cp calculado a partir de la definiciÃ³n actual de Fase 1."), "image_bytes": None, "image_format": None, "file_name": None}
    if len(df_cp) > 0:
        cp_fig = crear_grafica_curva(df_cp)
        image_bytes, metadata = export_plotly_figure_artifact(fig=cp_fig, figure_id="informe_tecnico_phase1_cp_curve", title="GrÃ¡fico de potencia y Cp", stem="informe_tecnico_potencia_cp", source_hint="Figura base del informe tÃ©cnico reconstruida desde la curva del aerogenerador.", preferred_format="png")
        if image_bytes and str(metadata.get("export_format") or "").lower() == "png":
            cp_figure_block.update({"image_bytes": image_bytes, "image_format": "png", "file_name": metadata.get("file_name", "informe_tecnico_potencia_cp.png")})
    phase1_section = {"id": "eleccion_aerogenerador", "title": _normalize_spanish_text("ElecciÃ³n del aerogenerador"), "description": _normalize_spanish_text("SecciÃ³n dedicada a documentar el aerogenerador seleccionado, sus parÃ¡metros geomÃ©tricos y la base de desempeÃ±o usada para el resto del proyecto."), "subsections": [{"id": "datos_basicos_aerogenerador", "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"), "blocks": [{"type": "table", "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"), "description": _normalize_spanish_text("ParÃ¡metros geomÃ©tricos y fÃ­sicos base empleados para la caracterizaciÃ³n inicial del aerogenerador."), "headers": [_normalize_spanish_text("ParÃ¡metro"), _normalize_spanish_text("Valor")], "rows": [[_normalize_spanish_text("DiÃ¡metro del rotor"), f"{diametro:,.2f} m".replace(',', '')], [_normalize_spanish_text("Ãrea del rotor"), f"{area_rotor:,.2f} mÂ²".replace(',', '')], [_normalize_spanish_text("Densidad del aire"), f"{densidad:,.3f} kg/mÂ³".replace(',', '')]]}]}, {"id": "tabla_velocidades_potencia", "title": _normalize_spanish_text("Tabla editable de velocidades y potencia"), "blocks": [speed_power_table] if speed_power_table else []}, {"id": "grafico_potencia_cp", "title": _normalize_spanish_text("GrÃ¡fico de potencia y Cp"), "blocks": [cp_figure_block]}, {"id": "tabla_cp_calculado", "title": _normalize_spanish_text("Tabla de Cp calculado"), "blocks": [cp_table] if cp_table else []}]}
    sections = [phase1_section]
    if phase2_section:
        sections.append(phase2_section)
    return {"document_id": "informe_tecnico", "title": _normalize_spanish_text("Informe tÃ©cnico"), "project_name": _normalize_spanish_text(project_name), "intro_paragraphs": [_normalize_spanish_text("Este documento presenta la configuraciÃ³n tÃ©cnica inicial del proyecto eÃ³lico y comienza con la definiciÃ³n del aerogenerador seleccionado y su base de desempeÃ±o.")], "sections": sections, "base_blocks": [], "word_master": {"available": False, "docx_bytes": None, "file_name": master_docx_name}, "appended_sections": [phase2_section] if phase2_section else [], "master_source_name": master_docx_name, "master_source_used": False}


def build_informe_tecnico_model(config=None, project_name="", df_curva_raw=None, df_nasa=None, master_docx_bytes=None, master_docx_name="informe_tecnico editado por mi.docx"):
    config = config or {}
    project_name = str(project_name or config.get("project_name") or "Proyecto eolico").strip() or "Proyecto eolico"

    from calculos import calcular_cp, crear_grafica_curva, preparar_datos_curva
    from reportes.docx import load_informe_tecnico_master_docx
    from reportes.figuras import export_plotly_figure_artifact

    word_master = load_informe_tecnico_master_docx(master_docx_bytes, file_name=master_docx_name)
    phase2_section = _build_informe_tecnico_phase2_section(config=config, project_name=project_name, df_nasa=df_nasa)
    if word_master.get("available"):
        sections = list(word_master.get("sections", []) or [])
        if phase2_section:
            sections.append(phase2_section)
        return {"document_id": "informe_tecnico", "title": word_master.get("title") or _normalize_spanish_text("Informe tÃ©cnico"), "project_name": word_master.get("project_name") or _normalize_spanish_text(project_name), "intro_paragraphs": word_master.get("intro_paragraphs", []), "sections": sections, "base_blocks": word_master.get("base_blocks", []), "word_master": word_master, "appended_sections": [phase2_section] if phase2_section else [], "master_source_name": word_master.get("file_name", master_docx_name), "master_source_used": True}

    diametro = float(config.get("diametro") or 100.0)
    densidad = float(config.get("densidad") or 1.225)
    area_rotor = pi * (diametro / 2.0) ** 2
    df_curva = preparar_datos_curva(df_curva_raw)
    df_curva = df_curva.copy() if df_curva is not None else pd.DataFrame()
    df_cp = calcular_cp(df_curva, densidad, area_rotor).copy() if len(df_curva) > 0 else pd.DataFrame()
    speed_power_table = _informe_tecnico_table_from_dataframe(df_curva, "Tabla editable de velocidades y potencia", "Tabla base de velocidades y potencia actualmente definida para el aerogenerador seleccionado en Fase 1.", ["Velocidad_num", "Potencia_W"], {"Velocidad_num": 2, "Potencia_W": 2})
    if speed_power_table:
        speed_power_table["headers"] = ["Velocidad (m/s)", "Potencia (W)"]
    cp_table = _informe_tecnico_table_from_dataframe(df_cp.rename(columns={"Velocidad_num": "Velocidad (m/s)", "Potencia_W": "Potencia (W)", "P_viento_W": "Potencia del viento (W)", "Cp": "Cp"}), "Tabla de Cp calculado", "Tabla derivada de la curva de potencia actual para documentar el coeficiente de potencia calculado en cada velocidad.", ["Velocidad (m/s)", "Potencia (W)", "Potencia del viento (W)", "Cp"], {"Velocidad (m/s)": 2, "Potencia (W)": 2, "Potencia del viento (W)": 2, "Cp": 4})
    cp_figure_block = {"type": "figure", "title": _normalize_spanish_text("GrÃ¡fico de potencia y Cp"), "description": _normalize_spanish_text("GrÃ¡fico tÃ©cnico que muestra la potencia del aerogenerador y el coeficiente Cp calculado a partir de la definiciÃ³n actual de Fase 1."), "image_bytes": None, "image_format": None, "file_name": None}
    if len(df_cp) > 0:
        cp_fig = crear_grafica_curva(df_cp)
        image_bytes, metadata = export_plotly_figure_artifact(fig=cp_fig, figure_id="informe_tecnico_phase1_cp_curve", title="GrÃ¡fico de potencia y Cp", stem="informe_tecnico_potencia_cp", source_hint="Figura base del informe tÃ©cnico reconstruida desde la curva del aerogenerador.", preferred_format="png")
        if image_bytes and str(metadata.get("export_format") or "").lower() == "png":
            cp_figure_block.update({"image_bytes": image_bytes, "image_format": "png", "file_name": metadata.get("file_name", "informe_tecnico_potencia_cp.png")})
    phase1_section = {"id": "eleccion_aerogenerador", "title": _normalize_spanish_text("ElecciÃ³n del aerogenerador"), "description": _normalize_spanish_text("SecciÃ³n dedicada a documentar el aerogenerador seleccionado, sus parÃ¡metros geomÃ©tricos y la base de desempeÃ±o usada para el resto del proyecto."), "subsections": [{"id": "datos_basicos_aerogenerador", "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"), "blocks": [{"type": "table", "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"), "description": _normalize_spanish_text("ParÃ¡metros geomÃ©tricos y fÃ­sicos base empleados para la caracterizaciÃ³n inicial del aerogenerador."), "headers": [_normalize_spanish_text("ParÃ¡metro"), _normalize_spanish_text("Valor")], "rows": [[_normalize_spanish_text("DiÃ¡metro del rotor"), f"{diametro:,.2f} m".replace(',', '')], [_normalize_spanish_text("Ãrea del rotor"), f"{area_rotor:,.2f} mÂ²".replace(',', '')], [_normalize_spanish_text("Densidad del aire"), f"{densidad:,.3f} kg/mÂ³".replace(',', '')]]}]}, {"id": "tabla_velocidades_potencia", "title": _normalize_spanish_text("Tabla editable de velocidades y potencia"), "blocks": [speed_power_table] if speed_power_table else []}, {"id": "grafico_potencia_cp", "title": _normalize_spanish_text("GrÃ¡fico de potencia y Cp"), "blocks": [cp_figure_block]}, {"id": "tabla_cp_calculado", "title": _normalize_spanish_text("Tabla de Cp calculado"), "blocks": [cp_table] if cp_table else []}]}
    sections = [phase1_section]
    if phase2_section:
        sections.append(phase2_section)
    return {"document_id": "informe_tecnico", "title": _normalize_spanish_text("Informe tÃ©cnico"), "project_name": _normalize_spanish_text(project_name), "intro_paragraphs": [_normalize_spanish_text("Este documento presenta la configuraciÃ³n tÃ©cnica inicial del proyecto eÃ³lico y comienza con la definiciÃ³n del aerogenerador seleccionado y su base de desempeÃ±o.")], "sections": sections, "base_blocks": [], "word_master": {"available": False, "docx_bytes": None, "file_name": master_docx_name}, "appended_sections": [phase2_section] if phase2_section else [], "master_source_name": master_docx_name, "master_source_used": False}


def _format_coordinate_pair(latitude, longitude):
    if not _report_has_value(latitude) or not _report_has_value(longitude):
        return None
    try:
        return f"{float(latitude):.4f}, {float(longitude):.4f}"
    except Exception:
        return _normalize_spanish_text(f"{latitude}, {longitude}")


def _build_site_data_table(title, calculation_context, project_name="", note=""):
    calculation_context = calculation_context or {}
    latitude = calculation_context.get("site_latitude")
    longitude = calculation_context.get("site_longitude")
    start_date = calculation_context.get("site_start_date")
    end_date = calculation_context.get("site_end_date")
    pending = []

    if not _report_has_value(latitude) or not _report_has_value(longitude):
        pending.append("coordenadas")
    if not _report_has_value(calculation_context.get("site_source")):
        pending.append("fuente de datos")
    if not _report_has_value(start_date) or not _report_has_value(end_date):
        pending.append("rango temporal")

    return _build_key_value_table(
        title,
        [
            ("Proyecto / sitio", project_name or None),
            ("Coordenadas", _format_coordinate_pair(latitude, longitude)),
            ("Latitud", _format_report_metric(latitude, 4)),
            ("Longitud", _format_report_metric(longitude, 4)),
            ("Fuente de datos", calculation_context.get("site_source")),
            ("Fecha inicial", start_date),
            ("Fecha final", end_date),
            ("Base de viento", calculation_context.get("base_viento")),
            ("Direcci\u00f3n usada", calculation_context.get("direccion_usada")),
            ("Altura objetivo", _format_report_metric(calculation_context.get("altura_deseada_m"), 2, "m")),
            ("Rugosidad / terreno", calculation_context.get("roughness_label")),
            ("Campos pendientes", ", ".join(pending) if pending else "Ninguno"),
        ],
        note=note,
    )


def _build_data_provenance_table(calculation_context, note=""):
    calculation_context = calculation_context or {}
    return _build_key_value_table(
        "Procedencia de datos y trazabilidad",
        [
            ("Fuente principal", calculation_context.get("site_source")),
            ("Coordenadas del sitio", _format_coordinate_pair(calculation_context.get("site_latitude"), calculation_context.get("site_longitude"))),
            ("Per\u00edodo analizado", (
                f"{calculation_context.get('site_start_date') or 'sin definir'} a {calculation_context.get('site_end_date') or 'sin definir'}"
                if _report_has_value(calculation_context.get("site_start_date")) or _report_has_value(calculation_context.get("site_end_date"))
                else None
            )),
            ("Base de viento usada", calculation_context.get("base_viento")),
            ("Direcci\u00f3n usada", calculation_context.get("direccion_usada")),
            ("Altura objetivo", _format_report_metric(calculation_context.get("altura_deseada_m"), 2, "m")),
            ("Rugosidad / terreno", calculation_context.get("roughness_label")),
        ],
        note=note,
    )


def _first_sentence(items, fallback):
    return items[0] if items else fallback


def _build_summary_paragraphs(project_name, calculation_context, result_summary, loss_summary):
    project_name = project_name or "el proyecto eolico analizado"
    base_viento = calculation_context.get("base_viento") or "la base de viento configurada"
    metodo = calculation_context.get("metodo_detalle") or calculation_context.get("modo_estadistico") or "el metodo configurado"
    n_turbinas = _format_report_metric(calculation_context.get("n_turbinas"), 0)
    aep_bruta = _format_report_metric(result_summary.get("aep_bruta_total_mwh"), 2, "MWh/ano")
    aep_neta = _format_report_metric(result_summary.get("aep_neta_total_mwh"), 2, "MWh/ano")
    fp_neto = _format_report_metric(result_summary.get("factor_planta_neto_pct"), 2, "%")
    perdida_estela = _format_report_metric(loss_summary.get("perdida_estela_mwh"), 2, "MWh/ano")

    return [
        (
            f"Este informe resume el analisis energetico de {project_name}, construido a partir de {base_viento} "
            f"y procesado con {metodo}. "
            + (f"El escenario actual considera {n_turbinas} turbinas en el parque. " if n_turbinas else "")
        ).strip(),
        (
            "El documento integra la caracterizacion del sitio, la procedencia de datos, la metodologia de modelado "
            "y los resultados energeticos del escenario actual para servir como borrador tecnico editable."
        ),
        (
            f"En los resultados disponibles se obtuvo una AEP bruta de {aep_bruta or 'sin dato'}, una AEP neta de {aep_neta or 'sin dato'} "
            f"y un factor de planta neto de {fp_neto or 'sin dato'}."
            + (f" La perdida energetica por estela reportada es {perdida_estela}." if perdida_estela else "")
        ),
    ]


def _build_introduction_paragraphs(project_name, calculation_context, result_summary):
    project_label = project_name or "el proyecto eolico analizado"
    source = calculation_context.get("site_source") or "la fuente de recurso configurada"
    base_viento = calculation_context.get("base_viento") or "la base de viento disponible"
    metodo = calculation_context.get("metodo_detalle") or calculation_context.get("modo_estadistico") or "el metodo configurado"
    n_turbinas = _format_report_metric(calculation_context.get("n_turbinas"), 0)
    potencia = _format_report_metric(result_summary.get("potencia_nominal_turbina_kw"), 2, "kW")

    return [
        (
            f"El presente documento consolida un borrador tecnico del estudio energetico de {project_label}. "
            f"Su objetivo es dejar trazable la configuracion del caso, la fuente de recurso usada y los resultados principales "
            "obtenidos en el flujo de trabajo del proyecto."
        ),
        (
            f"El analisis se apoya en {source} y en {base_viento} como base de entrada para la estimacion del comportamiento del parque. "
            f"Sobre esa informacion se estructuraron las etapas de caracterizacion del sitio, modelado metodologico y calculo de AEP con {metodo}."
        ),
        (
            "El reporte se organiza en secciones de sitio y datos, procedencia de informacion, metodologia, resultados, discusion y conclusiones. "
            + (
                f"En el escenario vigente se trabaja con {n_turbinas} turbinas"
                + (f" de {potencia} nominales por unidad." if potencia else ".")
                if n_turbinas
                else "La configuracion del parque puede seguir ajustandose antes de una version final."
            )
        ),
    ]


def _build_site_data_paragraphs(project_name, calculation_context):
    coords = _format_coordinate_pair(calculation_context.get("site_latitude"), calculation_context.get("site_longitude"))
    source = calculation_context.get("site_source") or "fuente no especificada"
    start = calculation_context.get("site_start_date") or "sin definir"
    end = calculation_context.get("site_end_date") or "sin definir"
    base_viento = calculation_context.get("base_viento") or "base de viento no especificada"
    altura = _format_report_metric(calculation_context.get("altura_deseada_m"), 2, "m") or "altura no especificada"
    roughness = calculation_context.get("roughness_label") or "rugosidad no especificada"

    paragraphs = []
    if project_name or coords:
        paragraphs.append(
            f"El sitio de estudio corresponde a {project_name or 'la ubicacion seleccionada en el proyecto'}"
            + (f", ubicado en las coordenadas {coords}." if coords else ".")
        )
    paragraphs.append(
        f"La procedencia principal de datos corresponde a {source}, con un periodo disponible entre {start} y {end} cuando esta informacion existe en la configuracion persistida."
    )
    paragraphs.append(
        f"Para el escenario actual se trabajo con {base_viento}, una altura objetivo de {altura} y una condicion de terreno reportada como {roughness}. "
        "La redaccion final puede ampliar acceso, entorno territorial, cercania a red y uso del suelo si el proyecto lo requiere."
    )
    return paragraphs


def _build_methodology_paragraphs(calculation_context):
    base_viento = calculation_context.get("base_viento") or "la base de viento configurada"
    estadistico = calculation_context.get("modo_estadistico") or "el esquema estadistico activo"
    detalle = calculation_context.get("metodo_detalle") or "el metodo de detalle configurado"
    wake_mode = calculation_context.get("wake_mode") or "el modo de estelas configurado"
    ct = _format_report_metric(calculation_context.get("ct"), 3)
    kw = _format_report_metric(calculation_context.get("kw"), 3)
    disp = _format_report_metric(calculation_context.get("disponibilidad_pct"), 2, "%")
    elec = _format_report_metric(calculation_context.get("electricas_pct"), 2, "%")
    otras = _format_report_metric(calculation_context.get("otras_pct"), 2, "%")
    sens = calculation_context.get("sens_variable")

    return [
        f"La metodologia parte de {base_viento} para construir la serie de analisis a la altura objetivo y propagarla hacia el calculo energetico del parque.",
        f"El tratamiento estadistico principal se realizo con {estadistico}, mientras que las tablas y comparaciones del escenario actual se consolidaron con {detalle}.",
        (
            f"El modelo de estelas se configuro como {wake_mode}"
            + (f", con Ct={ct}" if ct else "")
            + (f" y kw={kw}" if kw else "")
            + "."
        ),
        (
            "Las perdidas adicionales consideradas en la estimacion de AEP incluyen"
            + (f" disponibilidad={disp}," if disp else "")
            + (f" electricas={elec}," if elec else "")
            + (f" otras={otras}" if otras else "")
            + "."
        ).replace(",.", "."),
        (
            f"Cuando hay sensibilidad configurada, el analisis se orienta a la variable {sens} para explorar el impacto de cambios razonables sobre el AEP neto."
            if _report_has_value(sens)
            else "La sensibilidad puede completarse con escenarios adicionales si se desea ampliar la discusion tecnica."
        ),
    ]


def _build_results_paragraphs(result_summary, loss_summary):
    aep_bruta = _format_report_metric(result_summary.get("aep_bruta_total_mwh"), 2, "MWh/ano")
    aep_neta = _format_report_metric(result_summary.get("aep_neta_total_mwh"), 2, "MWh/ano")
    fp_bruto = _format_report_metric(result_summary.get("factor_planta_bruto_pct"), 2, "%")
    fp_neto = _format_report_metric(result_summary.get("factor_planta_neto_pct"), 2, "%")
    aep_turbina = _format_report_metric(result_summary.get("aep_neta_turbina_mwh"), 2, "MWh/ano")
    perdida_estela = _format_report_metric(loss_summary.get("perdida_estela_mwh"), 2, "MWh/ano")
    perdida_disp = _format_report_metric(loss_summary.get("perdida_disponibilidad_mwh"), 2, "MWh/ano")
    perdida_elec = _format_report_metric(loss_summary.get("perdida_electrica_mwh"), 2, "MWh/ano")

    return [
        f"Los resultados consolidados del escenario indican una AEP bruta de {aep_bruta or 'sin dato'} y una AEP neta de {aep_neta or 'sin dato'}.",
        f"El factor de planta bruto reportado es {fp_bruto or 'sin dato'} y el factor de planta neto es {fp_neto or 'sin dato'}, lo que permite contextualizar el desempeno energetico del parque.",
        (
            f"La AEP neta por turbina se estima en {aep_turbina}. " if aep_turbina else ""
        ) + (
            f"Entre las perdidas energeticas disponibles destacan estelas={perdida_estela or 'sin dato'}, disponibilidad={perdida_disp or 'sin dato'} y perdidas electricas={perdida_elec or 'sin dato'}."
        ),
    ]


def _build_discussion_paragraphs(calculation_context, result_summary, loss_summary):
    aep_neta = _format_report_metric(result_summary.get("aep_neta_total_mwh"), 2, "MWh/ano")
    fp_neto = _format_report_metric(result_summary.get("factor_planta_neto_pct"), 2, "%")
    perdida_estela = _format_report_metric(loss_summary.get("perdida_estela_mwh"), 2, "MWh/ano")
    base_viento = calculation_context.get("base_viento") or "la base de viento configurada"
    wake_mode = calculation_context.get("wake_mode") or "el tratamiento de estelas activo"
    sens = calculation_context.get("sens_variable")

    paragraphs = [
        (
            f"Desde una lectura preliminar, los resultados netos del escenario se explican por la combinacion entre {base_viento}, "
            f"las hipotesis de conversion energetica y el tratamiento de perdidas adoptado en {wake_mode}."
        ),
        (
            f"La AEP neta reportada ({aep_neta or 'sin dato'}) y el factor de planta neto ({fp_neto or 'sin dato'}) deben interpretarse "
            "como una sintesis del escenario actual, no como una afirmacion cerrada de factibilidad."
        ),
    ]
    if perdida_estela:
        paragraphs.append(
            f"La magnitud de la perdida por estela ({perdida_estela}) sugiere revisar la interaccion entre layout, separaciones y distribucion direccional para identificar mejoras potenciales."
        )
    else:
        paragraphs.append(
            "Cuando no se dispone todavia de una perdida por estela consolidada, conviene revisar el layout y la distribucion direccional antes de cerrar una lectura comparativa del parque."
        )
    if _report_has_value(sens):
        paragraphs.append(
            f"El escenario incluye sensibilidad sobre {sens}, por lo que esta seccion puede ampliarse con una lectura comparativa del efecto de esa variable sobre el rendimiento neto."
        )
    else:
        paragraphs.append(
            "Si se habilitan escenarios de sensibilidad adicionales, esta discusion puede enriquecerse con comparaciones directas entre supuestos y respuesta del AEP neto."
        )
    return paragraphs


def _build_conclusion_paragraphs(project_name, result_summary, loss_summary):
    aep_neta = _format_report_metric(result_summary.get("aep_neta_total_mwh"), 2, "MWh/ano")
    fp_neto = _format_report_metric(result_summary.get("factor_planta_neto_pct"), 2, "%")
    perdida_estela = _format_report_metric(loss_summary.get("perdida_estela_mwh"), 2, "MWh/ano")

    return [
        f"Como borrador tecnico, este informe sugiere concluir que {project_name or 'el proyecto analizado'} presenta un desempeno neto de {aep_neta or 'sin dato'} con un factor de planta neto de {fp_neto or 'sin dato'}.",
        (
            f"La perdida por estela del escenario actual ({perdida_estela}) merece revisarse junto con el layout y la distribucion direccional para identificar oportunidades de optimizacion."
            if perdida_estela
            else "Conviene contrastar las perdidas del escenario con alternativas de layout, disponibilidad y supuestos electricos antes de cerrar conclusiones finales."
        ),
        "La version final debe complementar esta sintesis con juicio ingenieril, validacion del sitio, criterio de factibilidad y cualquier restriccion externa relevante para la toma de decisiones.",
    ]


def _build_provenance_paragraphs(calculation_context):
    coords = _format_coordinate_pair(calculation_context.get("site_latitude"), calculation_context.get("site_longitude")) or "coordenadas no disponibles"
    source = calculation_context.get("site_source") or "fuente no especificada"
    start = calculation_context.get("site_start_date") or "sin definir"
    end = calculation_context.get("site_end_date") or "sin definir"
    base_viento = calculation_context.get("base_viento") or "base no especificada"
    direccion = calculation_context.get("direccion_usada") or "direccion no especificada"

    return [
        f"La procedencia de datos del escenario actual se apoya en {source}, asociada al sitio seleccionado en Fase 2 y ubicado en {coords}.",
        f"El intervalo temporal disponible para el recurso corresponde a {start} a {end} cuando esa informacion se encuentra persistida en el proyecto.",
        f"Sobre esa base se construyo la serie de analisis empleando {base_viento} y la direccion {direccion}, de modo que la trazabilidad entre seleccion del sitio, recurso utilizado y calculo energetico quede explicitada en el reporte.",
        "Cuando el proyecto incorpora figuras, tablas o anexos complementarios, estos deben interpretarse como derivados del mismo conjunto persistido de configuracion y resultados, salvo que el usuario reemplace manualmente algun activo para la version final.",
    ]


def build_row_table(title, headers, rows, note=""):
    headers = [_normalize_spanish_text(h) for h in (headers or [])]
    clean_rows = []
    for row in rows or []:
        clean_row = [_normalize_spanish_text(cell) for cell in row]
        if clean_row:
            clean_rows.append(clean_row)
    if not headers or not clean_rows:
        return None
    table = {
        "title": _normalize_spanish_text(title),
        "headers": headers,
        "rows": clean_rows,
    }
    if note:
        table["note"] = _normalize_spanish_text(note)
    return table


def _format_table_value(value, column_name=""):
    if not _report_has_value(value):
        return ""
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (np.floating, float)) and not isinstance(value, bool):
        column_name = str(column_name or "").lower()
        number = float(value)
        decimals = 2
        if abs(number) < 1 and number != 0:
            decimals = 4
        if "k weibull" in column_name or "ct" in column_name or "kw" in column_name:
            decimals = 3
        return f"{number:.{decimals}f}"
    return _normalize_spanish_text(value)


def _compact_table_header(value):
    text = _normalize_spanish_text(value).strip()
    replacements = {
        "Horas equivalentes anuales (h/aÃ±o)": "Horas eq. (h/a)",
        "AEP bruta parque (MWh/aÃ±o)": "AEP bruta parque (MWh/a)",
        "AEP neta sector (MWh/aÃ±o)": "AEP neta sector (MWh/a)",
        "EnergÃ­a perdida (MWh/aÃ±o)": "EnergÃ­a perdida (MWh/a)",
        "Probabilidad Weibull (%)": "Prob. Weibull (%)",
        "Probabilidad Rayleigh (%)": "Prob. Rayleigh (%)",
        "Probabilidad real (%)": "Prob. real (%)",
        "Velocidad media (m/s)": "Vel. media (m/s)",
        "Potencia media por turbina (W)": "P media turbina (W)",
    }
    return _normalize_spanish_text(replacements.get(text, text))


def dataframe_to_table_payload(df, title, columns=None, max_rows=12, note=""):
    if df is None or len(df) == 0:
        return None

    table_df = df.copy()
    if columns:
        available_columns = [col for col in columns if col in table_df.columns]
        if not available_columns:
            return None
        table_df = table_df[available_columns].copy()

    table_df = table_df.head(max_rows).copy()
    for col in table_df.columns:
        table_df[col] = table_df[col].map(lambda value, column_name=col: _format_table_value(value, column_name))

    return build_row_table(
        title=title,
        headers=[_compact_table_header(col) for col in table_df.columns],
        rows=table_df.values.tolist(),
        note=note,
    )


def get_report_manifest(
    config=None,
    project_name="",
    calculation_context=None,
    result_summary=None,
    loss_summary=None,
    table_payloads=None,
    artifact_context=None,
    export_format="excel",
):
    project_context = get_project_context(config)
    report_context = get_report_context(config)
    export_metadata = get_export_metadata(config=config, export_format=export_format)

    calculation_context = calculation_context or {}
    result_summary = result_summary or {}
    loss_summary = loss_summary or {}
    table_payloads = table_payloads or {}
    artifact_context = artifact_context or {}

    return {
        "generated_at_utc": export_metadata["generated_at_utc"],
        "project_name": str(project_name or "").strip(),
        "project_context": {
            "project_mode": project_context["mode"],
            "project_mode_label": project_context["mode_label"],
            "project_profile": project_context["profile"] or "",
            "project_profile_label": project_context["profile_label"],
        },
        "report_context": {
            "report_style": report_context["report_style"],
            "report_style_label": report_context["report_style_label"],
            "citation_style": report_context["citation_style"],
            "include_ai_declaration": report_context["include_ai_declaration"],
            "suggested_sections": list(report_context["report_sections"]),
            "template_hint": report_context["template_hint"],
            "export_targets": list(report_context["export_targets"]),
            "notes": list(report_context["notes"]),
        },
        "export_metadata": export_metadata,
        "calculation_context": calculation_context,
        "result_summary": result_summary,
        "loss_summary": loss_summary,
        "table_payloads": table_payloads,
        "artifact_context": artifact_context,
    }


def _resolve_figure_refs(default_refs, artifact_context):
    artifact_context = artifact_context or {}
    exported_figures = artifact_context.get("exported_figures", []) or []
    figure_map = {
        str(item.get("id")): item
        for item in exported_figures
        if str(item.get("id") or "").strip()
    }

    resolved = []
    for item in default_refs or []:
        figure_id = str(item.get("id") or "")
        exported = figure_map.get(figure_id, {})
        export_format = str(exported.get("export_format") or "").lower()
        path = exported.get("path") or item.get("path", "")
        render_mode = "placeholder"
        if export_format in ["png", "pdf"] and path:
            render_mode = "includegraphics"
        elif export_format == "svg" and path:
            render_mode = "static_reference"
        elif export_format == "html" and path:
            render_mode = "html_reference"

        note_parts = []
        if item.get("note"):
            cleaned = _clean_figure_note(item["note"])
            if cleaned:
                note_parts.append(cleaned)
        if exported.get("note"):
            cleaned = _clean_figure_note(exported["note"])
            if cleaned:
                note_parts.append(cleaned)

        resolved.append({
            "id": figure_id,
            "title": _normalize_spanish_text(item.get("title", "Figura")),
            "label": item.get("label", f"fig:{figure_id or 'placeholder'}"),
            "path": path,
            "render_mode": render_mode,
            "caption": _normalize_spanish_text(item.get("caption", item.get("title", "Figura"))),
            "note": _normalize_spanish_text(" ".join(part for part in note_parts if part).strip()),
            "export_format": export_format or None,
        })
    return resolved


def _build_dynamic_appendix_sections(artifact_context, table_payloads):
    artifact_context = artifact_context or {}
    table_payloads = table_payloads or {}
    appendix_specs = artifact_context.get("appendix_specs", []) or []
    appendix_specs = sorted(
        appendix_specs,
        key=lambda item: (
            str(item.get("appendix_file_name", "")),
            _normalize_spanish_text(item.get("title", "")),
        ),
    )
    appendix_sections = []

    def _phase_key_for_spec(spec):
        text = " ".join(
            str(spec.get(key, "") or "")
            for key in ["id", "appendix_file_name", "title", "purpose"]
        ).lower()
        if "fase 3.5" in text or "fase3.5" in text or "fase35" in text:
            return "fase35"
        for phase_key in ["fase1", "fase2", "fase3", "fase4"]:
            if phase_key in text or phase_key.replace("fase", "fase ") in text:
                return phase_key
        return None

    def _phase_order(phase_key):
        return {
            "fase1": 1,
            "fase2": 2,
            "fase3": 3,
            "fase35": 4,
            "fase4": 5,
        }.get(str(phase_key or ""), 99)

    def _is_phase_parent_spec(spec):
        file_name = str(spec.get("appendix_file_name", "") or "").lower()
        appendix_id = str(spec.get("id", "") or "").lower()
        return "_00_" in file_name or appendix_id in {
            "anexo_fase1_curva_cp",
            "anexo_fase2_series_perfiles",
            "anexo_fase3_recurso_direccional",
            "anexo_fase35_probabilidad_direccional",
            "anexo_fase4_estelas_y_arreglo",
        }

    def _child_title_for_spec(spec):
        title = _normalize_spanish_text(spec.get("title", "Detalle"))
        parts = [part.strip() for part in title.split(" - ") if part.strip()]
        if len(parts) >= 3 and parts[0].lower().startswith("anexo"):
            return " - ".join(parts[2:])
        if len(parts) >= 2 and parts[0].lower().startswith("anexo"):
            return parts[-1]
        return title

    def _section_from_spec(spec, include_file_name=True, title_override=None):
        table_keys = spec.get("table_keys", []) or []
        latex_tables = [table_payloads.get(key) for key in table_keys if table_payloads.get(key)]
        figure_refs = _resolve_figure_refs(spec.get("figure_refs", []), artifact_context)
        if not latex_tables and not figure_refs and not (spec.get("draft_paragraphs") or []):
            return None
        section = {
            "id": spec.get("id", "appendix_extra"),
            "title": _normalize_spanish_text(title_override or spec.get("title", "Anexo")),
            "purpose": _normalize_spanish_text(spec.get("purpose", "")),
            "suggested_content": [_normalize_spanish_text(item) for item in (spec.get("suggested_content", []) or [])],
            "available_data_keys": list(spec.get("available_data_keys", ["artifact_context", "table_payloads"])),
            "notes": [_normalize_spanish_text(item) for item in (spec.get("notes", []) or [])],
            "draft_paragraphs": [_normalize_spanish_text(item) for item in (spec.get("draft_paragraphs", []) or [])],
            "latex_tables": latex_tables,
            "figure_refs": figure_refs,
            "child_sections": [],
        }
        if include_file_name:
            section["appendix_file_name"] = spec.get("appendix_file_name", "")
        return section

    def _synthetic_phase_section(phase_key, parent_spec=None):
        defaults = {
            "fase1": {
                "id": "anexo_fase1",
                "appendix_file_name": "appendix_fase1.tex",
                "title": "Anexo A - Fase 1",
                "purpose": "Reunir los contenidos exportables de la Fase 1 dentro de un unico anexo principal.",
            },
            "fase2": {
                "id": "anexo_fase2",
                "appendix_file_name": "appendix_fase2.tex",
                "title": "Anexo B - Fase 2",
                "purpose": "Reunir los contenidos exportables de la Fase 2 dentro de un unico anexo principal.",
            },
            "fase3": {
                "id": "anexo_fase3",
                "appendix_file_name": "appendix_fase3.tex",
                "title": "Anexo C - Fase 3 - Recurso direccional",
                "purpose": "Agrupar la rosa de vientos y el detalle por sector dentro de un unico anexo principal.",
            },
            "fase35": {
                "id": "anexo_fase35",
                "appendix_file_name": "appendix_fase35.tex",
                "title": "Anexo D - Fase 3.5 - Probabilidad de ocurrencia por direccion",
                "purpose": "Agrupar el mapa de probabilidad y el detalle por sector dentro de un unico anexo principal.",
            },
            "fase4": {
                "id": "anexo_fase4",
                "appendix_file_name": "appendix_fase4.tex",
                "title": "Anexo E - Fase 4 - Estelas y arreglo del parque",
                "purpose": "Agrupar el analisis de estelas y el detalle por direccion dentro de un unico anexo principal.",
            },
        }
        base = defaults.get(phase_key, {
            "id": f"anexo_{phase_key}",
            "appendix_file_name": f"appendix_{phase_key}.tex",
            "title": f"Anexo - {phase_key}",
            "purpose": "Anexo principal generado automaticamente.",
        }).copy()
        if parent_spec:
            if parent_spec.get("id"):
                base["id"] = parent_spec.get("id")
            if parent_spec.get("appendix_file_name"):
                base["appendix_file_name"] = parent_spec.get("appendix_file_name")
            if parent_spec.get("title"):
                base["title"] = _normalize_spanish_text(parent_spec.get("title"))
            if parent_spec.get("purpose"):
                base["purpose"] = _normalize_spanish_text(parent_spec.get("purpose"))
        base.update({
            "suggested_content": [],
            "available_data_keys": ["artifact_context", "table_payloads"],
            "notes": [],
            "draft_paragraphs": [],
            "latex_tables": [],
            "figure_refs": [],
            "child_sections": [],
        })
        return base

    grouped_specs = {}
    ungrouped_specs = []
    for spec in appendix_specs:
        phase_key = _phase_key_for_spec(spec)
        if phase_key:
            grouped_specs.setdefault(phase_key, []).append(spec)
        else:
            ungrouped_specs.append(spec)

    for phase_key in sorted(grouped_specs.keys(), key=_phase_order):
        specs = grouped_specs.get(phase_key, [])
        parent_spec = next((spec for spec in specs if _is_phase_parent_spec(spec)), None)

        top_section = _section_from_spec(parent_spec, include_file_name=True) if parent_spec else None
        if top_section is None:
            top_section = _synthetic_phase_section(phase_key, parent_spec=parent_spec)

        child_sections = []
        for spec in specs:
            if spec is parent_spec:
                continue
            child_section = _section_from_spec(spec, include_file_name=False, title_override=_child_title_for_spec(spec))
            if child_section is not None:
                child_sections.append(child_section)

        top_section["child_sections"] = child_sections
        appendix_sections.append(top_section)

    for spec in ungrouped_specs:
        section = _section_from_spec(spec, include_file_name=True)
        if section is not None:
            appendix_sections.append(section)

    return appendix_sections


def _build_report_content_blocks(manifest, profile):
    project_context = manifest.get("project_context", {}) or {}
    calculation_context = manifest.get("calculation_context", {}) or {}
    result_summary = manifest.get("result_summary", {}) or {}
    loss_summary = manifest.get("loss_summary", {}) or {}
    project_name = str(manifest.get("project_name") or "").strip()

    config_items = []
    mode_label = project_context.get("project_mode_label")
    profile_label = project_context.get("project_profile_label")
    if _report_has_value(mode_label):
        config_items.append(f"Modo del proyecto: {mode_label}.")
    if _report_has_value(profile_label):
        config_items.append(f"Perfil activo: {profile_label}.")

    config_map = [
        ("base_viento", "Base de viento"),
        ("modo_estadistico", "Modo estadistico"),
        ("metodo_detalle", "Metodo principal de detalle"),
        ("altura_deseada_m", "Altura deseada"),
        ("direccion_usada", "Direccion usada"),
        ("roughness_label", "Rugosidad/terreno"),
        ("n_turbinas", "Numero de turbinas"),
    ]
    for key, label in config_map:
        value = calculation_context.get(key)
        if key == "altura_deseada_m":
            formatted = _format_report_metric(value, decimals=2, unit="m")
        else:
            formatted = _format_report_metric(value, decimals=2)
        if formatted:
            config_items.append(f"{label}: {formatted}.")

    methodology_items = []
    method_map = [
        ("base_viento", "La serie de analisis se construyo usando"),
        ("modo_estadistico", "El tratamiento estadistico principal fue"),
        ("metodo_detalle", "El metodo usado para tablas y sensibilidad fue"),
        ("wake_mode", "El tratamiento de estelas se configuro como"),
        ("ct", "Ct del modelo"),
        ("kw", "kw del modelo"),
    ]
    for key, prefix in method_map:
        value = calculation_context.get(key)
        if key in ["ct", "kw"]:
            formatted = _format_report_metric(value, decimals=3)
        else:
            formatted = _format_report_metric(value, decimals=2)
        if formatted:
            methodology_items.append(f"{prefix} {formatted}.")

    loss_input_items = []
    for key, label in [
        ("wake_manual_pct", "Perdida manual por estela"),
        ("disponibilidad_pct", "Perdida por disponibilidad"),
        ("electricas_pct", "Perdidas electricas"),
        ("otras_pct", "Otras perdidas"),
    ]:
        formatted = _format_report_metric(calculation_context.get(key), decimals=2, unit="%")
        if formatted:
            loss_input_items.append(f"{label}: {formatted}.")

    result_items = []
    for key, label, unit, decimals in [
        ("aep_bruta_total_mwh", "AEP bruta total", "MWh/ano", 2),
        ("aep_neta_total_mwh", "AEP neta total", "MWh/ano", 2),
        ("factor_planta_bruto_pct", "Factor de planta bruto", "%", 2),
        ("factor_planta_neto_pct", "Factor de planta neto", "%", 2),
        ("aep_bruta_turbina_mwh", "AEP bruta por turbina", "MWh/ano", 2),
        ("aep_neta_turbina_mwh", "AEP neta por turbina", "MWh/ano", 2),
        ("potencia_nominal_turbina_kw", "Potencia nominal por turbina", "kW", 2),
    ]:
        formatted = _format_report_metric(result_summary.get(key), decimals=decimals, unit=unit)
        if formatted:
            result_items.append(f"{label}: {formatted}.")

    loss_items = []
    for key, label in [
        ("perdida_estela_mwh", "Perdida por estela"),
        ("perdida_disponibilidad_mwh", "Perdida por disponibilidad"),
        ("perdida_electrica_mwh", "Perdida electrica"),
        ("otras_perdidas_mwh", "Otras perdidas"),
    ]:
        formatted = _format_report_metric(loss_summary.get(key), decimals=2, unit="MWh/ano")
        if formatted:
            loss_items.append(f"{label}: {formatted}.")

    site_items = []
    if project_name:
        site_items.append(f"Proyecto / sitio: {project_name}.")
    coords = _format_coordinate_pair(calculation_context.get("site_latitude"), calculation_context.get("site_longitude"))
    if coords:
        site_items.append(f"Coordenadas del sitio: {coords}.")
    if _report_has_value(calculation_context.get("site_source")):
        site_items.append(f"Fuente de datos: {calculation_context.get('site_source')}.")
    if _report_has_value(calculation_context.get("site_start_date")) or _report_has_value(calculation_context.get("site_end_date")):
        start = calculation_context.get("site_start_date") or "sin definir"
        end = calculation_context.get("site_end_date") or "sin definir"
        site_items.append(f"Rango temporal disponible: {start} a {end}.")
    if _report_has_value(calculation_context.get("base_viento")):
        site_items.append(f"Base de viento usada en el analisis: {calculation_context.get('base_viento')}.")
    if _report_has_value(calculation_context.get("altura_deseada_m")):
        site_items.append(
            f"Altura de analisis reportada: {_format_report_metric(calculation_context.get('altura_deseada_m'), 2, 'm')}."
        )
    site_items.append("Si falta contexto territorial, completar manualmente acceso, uso del suelo, red cercana y condicion del terreno.")

    return {
        "resumen": [],
        "introduccion": [],
        "sitio_datos": [],
        "configuracion": [
            {"title": "Parametros principales", "items": config_items or ["Completar la configuracion principal del escenario."]},
        ],
        "metodologia": [],
        "resultados": [],
        "portada": [
            {"title": "Metadatos del documento", "items": config_items[:2] or ["Completar titulo, autoria y contexto institucional."]},
        ],
        "resultados_discusion": [
            {"title": "Resultados principales", "items": result_items or ["Completar los resultados principales del estudio."]},
            {"title": "Discusion inicial de perdidas", "items": loss_items or ["Completar la interpretacion de perdidas y sensibilidad."]},
        ],
        "discusion": [
            {"title": "Resultados principales", "items": result_items or ["Completar los resultados principales del estudio."]},
            {"title": "Interpretacion de perdidas", "items": loss_items or ["Completar la interpretacion de perdidas y sensibilidad."]},
        ],
        "conclusiones": [],
    }


def build_report_payload(report_manifest):
    manifest = report_manifest or {}
    project_name = str(manifest.get("project_name") or "").strip()
    project_context = manifest.get("project_context", {}) or {}
    report_context = manifest.get("report_context", {}) or {}
    profile = project_context.get("project_profile") or ""
    report_style = report_context.get("report_style", "general")
    include_ai_declaration = bool(report_context.get("include_ai_declaration", False))
    artifact_context = manifest.get("artifact_context", {}) or {}
    table_payloads = manifest.get("table_payloads", {}) or {}

    title = "Informe tecnico del proyecto eolico"
    subtitle = "Sintesis estructurada para futura exportacion documental"

    if profile == "academic":
        title = "Borrador de informe academico del proyecto eolico"
        subtitle = "Estructura normalizada para futura plantilla academica"

    common_data_keys = [
        "project_context",
        "report_context",
        "calculation_context",
        "result_summary",
        "loss_summary",
    ]
    content_blocks = _build_report_content_blocks(manifest, profile)
    calculation_context = manifest.get("calculation_context", {}) or {}
    result_summary = manifest.get("result_summary", {}) or {}
    loss_summary = manifest.get("loss_summary", {}) or {}
    site_data_table = _build_site_data_table(
        "Resumen del sitio y de la fuente de datos",
        calculation_context=calculation_context,
        project_name=project_name,
        note="Tabla generada desde coordenadas y metadatos persistidos del proyecto cuando estan disponibles.",
    )
    site_map_caption = "Mapa del sitio del proyecto"
    coords = _format_coordinate_pair(calculation_context.get("site_latitude"), calculation_context.get("site_longitude"))
    if coords:
        site_map_caption += f" ({coords})"
    if _report_has_value(calculation_context.get("site_source")):
        site_map_caption += f" - fuente: {calculation_context.get('site_source')}"

    config_table = _build_key_value_table(
        "Resumen de configuracion",
        [
            ("Modo del proyecto", project_context.get("project_mode_label")),
            ("Perfil activo", project_context.get("project_profile_label")),
            ("Base de viento", calculation_context.get("base_viento")),
            ("Modo estadistico", calculation_context.get("modo_estadistico")),
            ("Metodo de detalle", calculation_context.get("metodo_detalle")),
            ("Altura deseada", _format_report_metric(calculation_context.get("altura_deseada_m"), 2, "m")),
            ("Direccion usada", calculation_context.get("direccion_usada")),
            ("Rugosidad", calculation_context.get("roughness_label")),
            ("Numero de turbinas", _format_report_metric(calculation_context.get("n_turbinas"), 0)),
        ],
        note="Tabla generada automaticamente a partir del contexto actual de Fase 5.",
    )
    methodology_table = _build_key_value_table(
        "Resumen metodologico",
        [
            ("Base de viento / perfil", calculation_context.get("base_viento")),
            ("Modo estadistico", calculation_context.get("modo_estadistico")),
            ("Metodo de detalle", calculation_context.get("metodo_detalle")),
            ("Tratamiento de estelas", calculation_context.get("wake_mode")),
            ("Ct", _format_report_metric(calculation_context.get("ct"), 3)),
            ("kw", _format_report_metric(calculation_context.get("kw"), 3)),
            ("Perdida manual por estela", _format_report_metric(calculation_context.get("wake_manual_pct"), 2, "%")),
            ("Disponibilidad", _format_report_metric(calculation_context.get("disponibilidad_pct"), 2, "%")),
            ("Perdidas electricas", _format_report_metric(calculation_context.get("electricas_pct"), 2, "%")),
            ("Otras perdidas", _format_report_metric(calculation_context.get("otras_pct"), 2, "%")),
        ],
    )
    result_table = _build_key_value_table(
        "Indicadores energeticos clave",
        [
            ("AEP bruta total", _format_report_metric(result_summary.get("aep_bruta_total_mwh"), 2, "MWh/ano")),
            ("AEP neta total", _format_report_metric(result_summary.get("aep_neta_total_mwh"), 2, "MWh/ano")),
            ("Factor de planta bruto", _format_report_metric(result_summary.get("factor_planta_bruto_pct"), 2, "%")),
            ("Factor de planta neto", _format_report_metric(result_summary.get("factor_planta_neto_pct"), 2, "%")),
            ("AEP bruta por turbina", _format_report_metric(result_summary.get("aep_bruta_turbina_mwh"), 2, "MWh/ano")),
            ("AEP neta por turbina", _format_report_metric(result_summary.get("aep_neta_turbina_mwh"), 2, "MWh/ano")),
            ("Potencia nominal por turbina", _format_report_metric(result_summary.get("potencia_nominal_turbina_kw"), 2, "kW")),
        ],
    )
    loss_table = _build_key_value_table(
        "Resumen de perdidas",
        [
            ("Perdida por estela", _format_report_metric(loss_summary.get("perdida_estela_mwh"), 2, "MWh/ano")),
            ("Perdida por disponibilidad", _format_report_metric(loss_summary.get("perdida_disponibilidad_mwh"), 2, "MWh/ano")),
            ("Perdida electrica", _format_report_metric(loss_summary.get("perdida_electrica_mwh"), 2, "MWh/ano")),
            ("Otras perdidas", _format_report_metric(loss_summary.get("otras_perdidas_mwh"), 2, "MWh/ano")),
        ],
    )
    provenance_table = _build_data_provenance_table(
        calculation_context,
        note="Trazabilidad resumida entre la seleccion del sitio en Fase 2, la fuente de datos persistida y el escenario usado en Fase 5.",
    )
    summary_paragraphs = _build_summary_paragraphs(project_name, calculation_context, result_summary, loss_summary)
    introduction_paragraphs = _build_introduction_paragraphs(project_name, calculation_context, result_summary)
    site_paragraphs = _build_site_data_paragraphs(project_name, calculation_context)
    methodology_paragraphs = _build_methodology_paragraphs(calculation_context)
    results_paragraphs = _build_results_paragraphs(result_summary, loss_summary)
    discussion_paragraphs = _build_discussion_paragraphs(calculation_context, result_summary, loss_summary)
    conclusion_paragraphs = _build_conclusion_paragraphs(project_name, result_summary, loss_summary)
    provenance_paragraphs = _build_provenance_paragraphs(calculation_context)

    general_figures = _resolve_figure_refs([
        {
            "id": "site_map",
            "title": "Mapa del sitio",
            "label": "fig:mapa_sitio",
            "path": "04_Figuras_mapas/mapa_sitio.(png|html)",
            "note": "Figura de ubicacion generada desde las coordenadas persistidas del proyecto cuando estan disponibles.",
            "caption": site_map_caption,
        },
        {
            "id": "wind_rose",
            "title": "Rosa de vientos",
            "label": "fig:rosa_vientos",
            "path": "04_Figuras_mapas/rosa_vientos.(png|html)",
            "note": "Usar el artefacto exportado si esta disponible; en caso contrario insertar la figura manualmente.",
        },
        {
            "id": "layout_wakes",
            "title": "Layout del parque",
            "label": "fig:layout_parque",
            "path": "04_Figuras_mapas/layout_parque.(png|html)",
            "note": "Representa el arreglo actual del parque y sirve como base para documentar estelas.",
        },
        {
            "id": "aep_losses",
            "title": "Resumen AEP y perdidas",
            "label": "fig:resumen_aep_perdidas",
            "path": "04_Figuras_mapas/resumen_aep_perdidas.(png|html)",
            "note": "Figura recomendada para reforzar la interpretacion de resultados energeticos.",
        },
        {
            "id": "sensibilidad_aep",
            "title": "Sensibilidad del AEP neto",
            "label": "fig:sensibilidad_aep",
            "path": "04_Figuras_mapas/sensibilidad_aep.(png|html)",
            "note": "Insertar si la discusion de sensibilidad forma parte del reporte final.",
        },
        {
            "id": "probability_curves",
            "title": "Curva de probabilidad por sector",
            "label": "fig:curva_probabilidad_sector",
            "path": "04_Figuras_mapas/curva_probabilidad_sector.(png|html)",
            "note": "Artefacto reconstruido desde la configuracion persistida de Fase 3.5 cuando esta disponible.",
        },
        {
            "id": "probability_heatmap",
            "title": "Mapa sectorial de probabilidad",
            "label": "fig:mapa_probabilidad_sectorial",
            "path": "04_Figuras_mapas/mapa_probabilidad_sectorial.(png|html)",
            "note": "Complementa la discusion de distribucion por rangos y sectores.",
        },
    ], artifact_context)

    losses_detail_table = table_payloads.get("losses_detail")
    sector_summary_table = table_payloads.get("sector_summary")
    sensitivity_table = table_payloads.get("sensitivity_summary")
    probability_intervals_table = table_payloads.get("probability_intervals")
    probability_operation_table = table_payloads.get("probability_operation")
    probability_sector_table = table_payloads.get("probability_sector_summary")
    site_map_ref = general_figures[0]
    wind_rose_ref = general_figures[1]
    layout_ref = general_figures[2]
    aep_ref = general_figures[3]
    sensitivity_ref = general_figures[4]
    probability_refs = general_figures[5:]

    appendix_sections = _build_dynamic_appendix_sections(
        artifact_context=artifact_context,
        table_payloads=table_payloads,
    )

    def _find_appendix_target(*tokens):
        for section in appendix_sections:
            text = " ".join([
                str(section.get("id", "") or ""),
                str(section.get("appendix_file_name", "") or ""),
                str(section.get("title", "") or ""),
            ]).lower()
            if any(token in text for token in tokens):
                return section
        return appendix_sections[-1] if appendix_sections else None

    summary_child = {
        "id": "anexo_resultados_sectoriales",
        "title": "Resultados sectoriales del escenario",
        "purpose": "Conservar tablas compactas listas para trasladar al informe final o a anexos reproducibles.",
        "suggested_content": [],
        "available_data_keys": ["table_payloads"],
        "notes": ["Las tablas completas siguen disponibles en Excel y CSV cuando se necesite mayor detalle."],
        "latex_tables": [table for table in [sector_summary_table, losses_detail_table] if table],
        "figure_refs": [],
        "child_sections": [],
    }
    if summary_child["latex_tables"]:
        summary_target = _find_appendix_target("fase4", "fase35", "fase3")
        if summary_target is not None:
            summary_target.setdefault("child_sections", []).append(summary_child)
        else:
            summary_child["appendix_file_name"] = "appendix_sector_tables.tex"
            appendix_sections.append(summary_child)

    probability_child = {
        "id": "anexo_probabilidad",
        "title": "Curvas y tablas de probabilidad",
        "purpose": "Documentar la informacion reconstruida desde Fase 3.5 para facilitar la integracion en reportes tecnicos o academicos.",
        "suggested_content": [],
        "available_data_keys": ["table_payloads", "artifact_context"],
        "notes": ["Si la curva o el heatmap no se exportan como imagen estatica, se mantiene la referencia al artefacto HTML o la nota de insercion manual."],
        "latex_tables": [table for table in [probability_sector_table, probability_intervals_table, probability_operation_table] if table],
        "figure_refs": probability_refs,
        "child_sections": [],
    }
    if probability_child["latex_tables"] or probability_child["figure_refs"]:
        probability_target = _find_appendix_target("fase35")
        if probability_target is not None:
            probability_target.setdefault("child_sections", []).append(probability_child)
        else:
            probability_child["appendix_file_name"] = "appendix_probability_tables.tex"
            appendix_sections.append(probability_child)

    sections = [
        {
            "id": "resumen",
            "title": "Resumen",
            "purpose": "Presentar el contexto general del proyecto y los resultados principales.",
            "suggested_content": [
                "Descripcion breve del estudio y del objetivo del analisis.",
                "Resumen de AEP bruta, AEP neta y factor de planta.",
            ],
            "available_data_keys": ["project_context", "result_summary"],
            "notes": ["Adecuado para apertura ejecutiva o abstract tecnico."],
            "content_blocks": content_blocks.get("resumen", []),
            "draft_paragraphs": summary_paragraphs,
            "latex_tables": [table for table in [result_table, sector_summary_table] if table],
            "figure_refs": [],
        },
        {
            "id": "introduccion",
            "title": "Introduccion",
            "purpose": "Abrir el documento con el alcance del estudio, su objetivo tecnico y la estructura general del analisis desarrollado en el proyecto.",
            "suggested_content": [
                "Alcance del estudio y objetivo del analisis energetico.",
                "Estructura general del flujo de trabajo y del reporte.",
            ],
            "available_data_keys": ["project_context", "calculation_context", "result_summary"],
            "notes": [],
            "content_blocks": content_blocks.get("introduccion", []),
            "draft_paragraphs": introduction_paragraphs,
        },
        {
            "id": "configuracion",
            "title": "Configuracion del proyecto",
            "purpose": "Documentar el modo del proyecto, el perfil y las decisiones base del estudio.",
            "suggested_content": [
                "Modo del proyecto y perfil seleccionado.",
                "Supuestos de velocidad, metodologia estadistica y parametros de perdidas.",
            ],
            "available_data_keys": ["project_context", "report_context", "calculation_context"],
            "notes": ["Mantener tono descriptivo; no imponer plantillas rigidas en modo libre."],
            "content_blocks": content_blocks.get("configuracion", []),
            "latex_tables": [config_table] if config_table else [],
            "figure_refs": [],
        },
        {
            "id": "sitio_datos",
            "title": "Sitio y datos",
            "purpose": "Documentar la ubicacion del proyecto, la procedencia de los datos y el contexto basico del recurso usado en el escenario.",
            "suggested_content": [
                "Ubicacion del sitio y coordenadas de referencia.",
                "Fuente de datos y rango temporal disponible.",
                "Relacion entre la fuente de viento, la altura de analisis y el contexto del terreno.",
            ],
            "available_data_keys": ["calculation_context", "artifact_context"],
            "notes": ["Si algun campo falta, mantener la seccion editable y completar manualmente la descripcion territorial."],
            "content_blocks": content_blocks.get("sitio_datos", []),
            "draft_paragraphs": site_paragraphs,
            "latex_tables": [table for table in [site_data_table] if table],
            "figure_refs": [site_map_ref],
        },
        {
            "id": "procedencia_datos",
            "title": "Procedencia de datos",
            "purpose": "Explicar la trazabilidad entre la seleccion del sitio, la fuente de datos y la serie de analisis usada en el reporte.",
            "suggested_content": [
                "Fuente principal del recurso y rango temporal utilizado.",
                "Relacion entre la seleccion del sitio, coordenadas y base de viento usada en el analisis.",
            ],
            "available_data_keys": ["calculation_context"],
            "notes": ["Mantener editable si se requiere incorporar referencias externas o anexos de datos crudos."],
            "content_blocks": [],
            "draft_paragraphs": provenance_paragraphs,
            "latex_tables": [table for table in [provenance_table] if table],
            "figure_refs": [],
        },
        {
            "id": "metodologia",
            "title": "Metodologia",
            "purpose": "Explicar como se construyo la serie de analisis y como se estimo el AEP.",
            "suggested_content": [
                "Base de viento utilizada y modelo de extrapolacion.",
                "Metodo estadistico principal y tratamiento de perdidas.",
            ],
            "available_data_keys": ["calculation_context", "report_context"],
            "notes": ["Preparado para futuras plantillas LaTeX o DOCX."],
            "content_blocks": content_blocks.get("metodologia", []),
            "draft_paragraphs": methodology_paragraphs,
            "latex_tables": [table for table in [methodology_table, sensitivity_table] if table],
            "figure_refs": [wind_rose_ref] + probability_refs,
        },
        {
            "id": "resultados",
            "title": "Resultados",
            "purpose": "Resumir indicadores energeticos y perdidas relevantes del parque.",
            "suggested_content": [
                "Resultados principales del AEP y factor de planta.",
                "Resumen de perdidas por estela, disponibilidad, electricas y otras.",
            ],
            "available_data_keys": ["result_summary", "loss_summary"],
            "notes": ["Puede alimentar tablas y figuras futuras."],
            "content_blocks": content_blocks.get("resultados", []),
            "draft_paragraphs": results_paragraphs,
            "latex_tables": [table for table in [result_table, loss_table, losses_detail_table] if table],
            "figure_refs": [layout_ref, aep_ref, sensitivity_ref] + probability_refs,
        },
        {
            "id": "discusion",
            "title": "Discusion basica de resultados",
            "purpose": "Interpretar de forma cauta los resultados del escenario actual y resaltar que aspectos conviene revisar antes de una conclusion final.",
            "suggested_content": [
                "Lectura tecnica preliminar de AEP, factor de planta y perdidas.",
                "Relacion entre base de viento, estelas y sensibilidad disponible.",
            ],
            "available_data_keys": ["calculation_context", "result_summary", "loss_summary"],
            "notes": [],
            "content_blocks": content_blocks.get("discusion", []),
            "draft_paragraphs": discussion_paragraphs,
            "latex_tables": [table for table in [sensitivity_table] if table],
            "figure_refs": [aep_ref, sensitivity_ref] + probability_refs,
        },
        {
            "id": "conclusiones",
            "title": "Conclusiones",
            "purpose": "Cerrar el borrador con una sintesis tecnica basada en los resultados disponibles y en los aspectos que conviene revisar manualmente.",
            "suggested_content": [
                "Lectura general del desempeno energetico del escenario.",
                "Aspectos a revisar o contrastar antes de cerrar el informe final.",
            ],
            "available_data_keys": ["result_summary", "loss_summary"],
            "notes": ["Mantener esta seccion como borrador tecnico editable, no como conclusion cerrada."],
            "content_blocks": content_blocks.get("conclusiones", []),
            "draft_paragraphs": conclusion_paragraphs,
        },
    ]

    if profile == "academic":
        sections = [
            {
                "id": "portada",
                "title": "Portada",
                "purpose": "Reservar metadatos del documento academico y la identificacion del proyecto.",
                "suggested_content": [
                    "Titulo del trabajo, nombre del proyecto y fecha de generacion.",
                    "Informacion institucional o de curso cuando aplique.",
                ],
                "available_data_keys": ["project_context", "report_context"],
                "notes": ["Opcional y no obligatoria para el modo libre."],
                "content_blocks": content_blocks.get("portada", []),
            },
            {
                "id": "resumen",
                "title": "Resumen",
                "purpose": "Sintetizar objetivo, metodologia y resultados clave en formato academico.",
                "suggested_content": [
                    "Proposito del estudio y alcance tecnico.",
                    "AEP bruto/neto y perdidas mas relevantes.",
                ],
                "available_data_keys": ["project_context", "result_summary", "loss_summary"],
                "notes": ["Base para abstract o resumen ejecutivo."],
                "content_blocks": content_blocks.get("resumen", []),
                "draft_paragraphs": summary_paragraphs,
                "latex_tables": [table for table in [result_table, sector_summary_table] if table],
                "figure_refs": [site_map_ref],
            },
            {
                "id": "introduccion",
                "title": "Introduccion",
                "purpose": "Introducir el objetivo tecnico del estudio y la estructura del documento a partir del caso efectivamente configurado.",
                "suggested_content": [
                    "Objetivo del estudio y alcance del flujo de trabajo.",
                    "Componentes del analisis y organizacion del reporte.",
                ],
                "available_data_keys": ["project_context", "calculation_context", "result_summary"],
                "notes": [],
                "content_blocks": content_blocks.get("introduccion", []),
                "draft_paragraphs": introduction_paragraphs,
            },
            {
                "id": "sitio_datos",
                "title": "Sitio y datos",
                "purpose": "Resumir la localizacion, la fuente de datos y el contexto base del estudio antes de entrar a la metodologia.",
                "suggested_content": [
                    "Coordenadas y referencia espacial del sitio.",
                    "Fuente de datos, fechas y alcance del conjunto utilizado.",
                    "Contexto de terreno, altura y base de viento usada.",
                ],
                "available_data_keys": ["calculation_context", "artifact_context"],
                "notes": ["Mantener la redaccion abierta: la app aporta datos persistidos, pero la justificacion territorial sigue siendo editable."],
                "content_blocks": content_blocks.get("sitio_datos", []),
                "draft_paragraphs": site_paragraphs,
                "latex_tables": [table for table in [site_data_table] if table],
                "figure_refs": [site_map_ref],
            },
            {
                "id": "procedencia_datos",
                "title": "Procedencia de datos",
                "purpose": "Dejar explicita la trazabilidad entre el sitio seleccionado, la fuente de recurso y la serie usada en el analisis.",
                "suggested_content": [
                    "Fuente principal del recurso, coordenadas y periodo disponible.",
                    "Relacion entre seleccion del sitio, base de viento y analisis posterior.",
                ],
                "available_data_keys": ["calculation_context"],
                "notes": [],
                "content_blocks": [],
                "draft_paragraphs": provenance_paragraphs,
                "latex_tables": [table for table in [provenance_table] if table],
                "figure_refs": [site_map_ref],
            },
            {
                "id": "metodologia",
                "title": "Metodologia",
                "purpose": "Describir los metodos y supuestos utilizados en el calculo.",
                "suggested_content": [
                    "Serie de viento, metodo estadistico y tratamiento de perdidas.",
                    "Parametros seleccionados para el escenario actual.",
                ],
                "available_data_keys": ["calculation_context", "report_context"],
                "notes": ["Compatible con futura plantilla APA/LaTeX."],
                "content_blocks": content_blocks.get("metodologia", []),
                "draft_paragraphs": methodology_paragraphs,
                "latex_tables": [table for table in [config_table, methodology_table, sensitivity_table] if table],
                "figure_refs": [site_map_ref, wind_rose_ref] + probability_refs,
            },
            {
                "id": "resultados_discusion",
                "title": "Resultados y discusion",
                "purpose": "Presentar resultados e interpretar sus implicaciones tecnicas.",
                "suggested_content": [
                    "Indicadores de produccion energetica y perdidas.",
                    "Lectura critica de resultados y sensibilidad.",
                ],
                "available_data_keys": ["result_summary", "loss_summary"],
                "notes": ["Seccion preparada para expansion posterior con figuras y referencias."],
                "content_blocks": content_blocks.get("resultados_discusion", []),
                "draft_paragraphs": results_paragraphs + discussion_paragraphs,
                "latex_tables": [table for table in [result_table, loss_table, losses_detail_table] if table],
                "figure_refs": [layout_ref, aep_ref, sensitivity_ref] + probability_refs,
            },
            {
                "id": "conclusiones",
                "title": "Conclusiones",
                "purpose": "Cerrar el documento con hallazgos principales y lineas futuras.",
                "suggested_content": [
                    "Sintesis de resultados relevantes.",
                    "Siguientes pasos o mejoras del estudio.",
                ],
                "available_data_keys": common_data_keys,
                "notes": ["No impone una estructura academica rigida; solo la sugiere."],
                "content_blocks": content_blocks.get("conclusiones", []),
                "draft_paragraphs": conclusion_paragraphs,
            },
        ]

    return {
        "title": title,
        "subtitle": subtitle,
        "project_name": project_name,
        "report_style": report_style,
        "citation_style": report_context.get("citation_style", "Opcional"),
        "include_ai_declaration": include_ai_declaration,
        "sections": sections,
        "appendix_sections": appendix_sections,
        "appendix_hints": [
            "Tablas de resultados sectoriales",
            "Parametros de configuracion usados en Fase 5",
        ],
        "references_hint": (
            "Usar referencias tecnicas y academicas cuando el perfil academico este activo."
            if profile == "academic"
            else "Las referencias son opcionales y pueden adaptarse al objetivo del proyecto."
        ),
        "ai_declaration_text": (
            "Se sugiere incluir una declaracion de uso de IA como apoyo en redaccion o estructuracion del informe."
            if include_ai_declaration
            else ""
        ),
    }


def _informe_tecnico_table_from_dataframe(df, title, description, columns=None, decimals_map=None):
    if df is None or len(df) == 0:
        return None
    decimals_map = decimals_map or {}
    frame = df.copy()
    if columns:
        available = [col for col in columns if col in frame.columns]
        if available:
            frame = frame[available].copy()
    headers = [_normalize_spanish_text(str(col)) for col in frame.columns]
    rows = []
    for _, row in frame.iterrows():
        row_cells = []
        for column, value in zip(frame.columns, row.tolist()):
            if pd.isna(value):
                row_cells.append("")
            elif isinstance(value, (int, np.integer)):
                row_cells.append(str(int(value)))
            elif isinstance(value, (float, np.floating)):
                decimals = int(decimals_map.get(column, 4))
                row_cells.append(f"{float(value):,.{decimals}f}".replace(",", ""))
            else:
                row_cells.append(_normalize_spanish_text(str(value)))
        rows.append(row_cells)
    return {
        "type": "table",
        "title": _normalize_spanish_text(title),
        "description": _normalize_spanish_text(description),
        "headers": headers,
        "rows": rows,
    }


def build_informe_tecnico_model(config=None, project_name="", df_curva_raw=None):
    config = config or {}
    project_name = str(project_name or config.get("project_name") or "Proyecto eolico").strip() or "Proyecto eolico"

    from calculos import calcular_cp, crear_grafica_curva, preparar_datos_curva
    from reportes.figuras import export_plotly_figure_artifact

    diametro = float(config.get("diametro") or 100.0)
    densidad = float(config.get("densidad") or 1.225)
    area_rotor = pi * (diametro / 2.0) ** 2

    df_curva = preparar_datos_curva(df_curva_raw)
    df_curva = df_curva.copy() if df_curva is not None else pd.DataFrame()
    df_cp = calcular_cp(df_curva, densidad, area_rotor).copy() if len(df_curva) > 0 else pd.DataFrame()

    speed_power_table = _informe_tecnico_table_from_dataframe(
        df_curva,
        title="Tabla editable de velocidades y potencia",
        description="Tabla base de velocidades y potencia actualmente definida para el aerogenerador seleccionado en Fase 1.",
        columns=["Velocidad_num", "Potencia_W"],
        decimals_map={"Velocidad_num": 2, "Potencia_W": 2},
    )
    if speed_power_table:
        speed_power_table["headers"] = ["Velocidad (m/s)", "Potencia (W)"]

    cp_table = _informe_tecnico_table_from_dataframe(
        df_cp.rename(columns={
            "Velocidad_num": "Velocidad (m/s)",
            "Potencia_W": "Potencia (W)",
            "P_viento_W": "Potencia del viento (W)",
            "Cp": "Cp",
        }),
        title="Tabla de Cp calculado",
        description="Tabla derivada de la curva de potencia actual para documentar el coeficiente de potencia calculado en cada velocidad.",
        columns=["Velocidad (m/s)", "Potencia (W)", "Potencia del viento (W)", "Cp"],
        decimals_map={
            "Velocidad (m/s)": 2,
            "Potencia (W)": 2,
            "Potencia del viento (W)": 2,
            "Cp": 4,
        },
    )

    cp_figure_block = {
        "type": "figure",
        "title": "GrÃ¡fico de potencia y Cp",
        "description": "GrÃ¡fico tÃ©cnico que muestra la potencia del aerogenerador y el coeficiente Cp calculado a partir de la definiciÃ³n actual de Fase 1.",
        "image_bytes": None,
        "image_format": None,
        "file_name": None,
    }
    if len(df_cp) > 0:
        cp_fig = crear_grafica_curva(df_cp)
        image_bytes, metadata = export_plotly_figure_artifact(
            fig=cp_fig,
            figure_id="informe_tecnico_phase1_cp_curve",
            title="GrÃ¡fico de potencia y Cp",
            stem="informe_tecnico_potencia_cp",
            source_hint="Figura base del informe tÃ©cnico reconstruida desde la curva del aerogenerador.",
            preferred_format="png",
        )
        if image_bytes and str(metadata.get("export_format") or "").lower() == "png":
            cp_figure_block.update({
                "image_bytes": image_bytes,
                "image_format": "png",
                "file_name": metadata.get("file_name", "informe_tecnico_potencia_cp.png"),
            })

    basic_data_table = {
        "type": "table",
        "title": "Datos bÃ¡sicos del aerogenerador",
        "description": "ParÃ¡metros geomÃ©tricos y fÃ­sicos base empleados para la caracterizaciÃ³n inicial del aerogenerador.",
        "headers": ["ParÃ¡metro", "Valor"],
        "rows": [
            ["DiÃ¡metro del rotor", f"{diametro:,.2f} m".replace(",", "")],
            ["Ãrea del rotor", f"{area_rotor:,.2f} mÂ²".replace(",", "")],
            ["Densidad del aire", f"{densidad:,.3f} kg/mÂ³".replace(",", "")],
        ],
    }


def build_informe_tecnico_model(config=None, project_name="", df_curva_raw=None):
    config = config or {}
    project_name = str(project_name or config.get("project_name") or "Proyecto eolico").strip() or "Proyecto eolico"

    from calculos import calcular_cp, crear_grafica_curva, preparar_datos_curva
    from reportes.figuras import export_plotly_figure_artifact

    diametro = float(config.get("diametro") or 100.0)
    densidad = float(config.get("densidad") or 1.225)
    area_rotor = pi * (diametro / 2.0) ** 2

    df_curva = preparar_datos_curva(df_curva_raw)
    df_curva = df_curva.copy() if df_curva is not None else pd.DataFrame()
    df_cp = calcular_cp(df_curva, densidad, area_rotor).copy() if len(df_curva) > 0 else pd.DataFrame()

    speed_power_table = _informe_tecnico_table_from_dataframe(
        df_curva,
        title="Tabla editable de velocidades y potencia",
        description="Tabla base de velocidades y potencia actualmente definida para el aerogenerador seleccionado en Fase 1.",
        columns=["Velocidad_num", "Potencia_W"],
        decimals_map={"Velocidad_num": 2, "Potencia_W": 2},
    )
    if speed_power_table:
        speed_power_table["headers"] = [
            _normalize_spanish_text("Velocidad (m/s)"),
            _normalize_spanish_text("Potencia (W)"),
        ]

    cp_table = _informe_tecnico_table_from_dataframe(
        df_cp.rename(
            columns={
                "Velocidad_num": "Velocidad (m/s)",
                "Potencia_W": "Potencia (W)",
                "P_viento_W": "Potencia del viento (W)",
                "Cp": "Cp",
            }
        ),
        title="Tabla de Cp calculado",
        description="Tabla derivada de la curva de potencia actual para documentar el coeficiente de potencia calculado en cada velocidad.",
        columns=["Velocidad (m/s)", "Potencia (W)", "Potencia del viento (W)", "Cp"],
        decimals_map={
            "Velocidad (m/s)": 2,
            "Potencia (W)": 2,
            "Potencia del viento (W)": 2,
            "Cp": 4,
        },
    )

    cp_figure_block = {
        "type": "figure",
        "title": _normalize_spanish_text("GrÃ¡fico de potencia y Cp"),
        "description": _normalize_spanish_text(
            "GrÃ¡fico tÃ©cnico que muestra la potencia del aerogenerador y el coeficiente Cp calculado a partir de la definiciÃ³n actual de Fase 1."
        ),
        "image_bytes": None,
        "image_format": None,
        "file_name": None,
    }
    if len(df_cp) > 0:
        cp_fig = crear_grafica_curva(df_cp)
        image_bytes, metadata = export_plotly_figure_artifact(
            fig=cp_fig,
            figure_id="informe_tecnico_phase1_cp_curve",
            title="GrÃ¡fico de potencia y Cp",
            stem="informe_tecnico_potencia_cp",
            source_hint="Figura base del informe tÃ©cnico reconstruida desde la curva del aerogenerador.",
            preferred_format="png",
        )
        if image_bytes and str(metadata.get("export_format") or "").lower() == "png":
            cp_figure_block.update(
                {
                    "image_bytes": image_bytes,
                    "image_format": "png",
                    "file_name": metadata.get("file_name", "informe_tecnico_potencia_cp.png"),
                }
            )

    basic_data_table = {
        "type": "table",
        "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"),
        "description": _normalize_spanish_text(
            "ParÃ¡metros geomÃ©tricos y fÃ­sicos base empleados para la caracterizaciÃ³n inicial del aerogenerador."
        ),
        "headers": [
            _normalize_spanish_text("ParÃ¡metro"),
            _normalize_spanish_text("Valor"),
        ],
        "rows": [
            [_normalize_spanish_text("DiÃ¡metro del rotor"), f"{diametro:,.2f} m".replace(",", "")],
            [_normalize_spanish_text("Ãrea del rotor"), f"{area_rotor:,.2f} mÂ²".replace(",", "")],
            [_normalize_spanish_text("Densidad del aire"), f"{densidad:,.3f} kg/mÂ³".replace(",", "")],
        ],
    }

    return {
        "document_id": "informe_tecnico",
        "title": _normalize_spanish_text("Informe tÃ©cnico"),
        "project_name": _normalize_spanish_text(project_name),
        "file_stem": "informe_tecnico",
        "intro_paragraphs": [
            _normalize_spanish_text(
                "Este documento presenta la configuraciÃ³n tÃ©cnica inicial del proyecto eÃ³lico y comienza con la definiciÃ³n del aerogenerador seleccionado y su base de desempeÃ±o."
            ),
        ],
        "sections": [
            {
                "id": "eleccion_aerogenerador",
                "title": _normalize_spanish_text("ElecciÃ³n del aerogenerador"),
                "description": _normalize_spanish_text(
                    "SecciÃ³n dedicada a documentar el aerogenerador seleccionado, sus parÃ¡metros geomÃ©tricos y la base de desempeÃ±o usada para el resto del proyecto."
                ),
                "subsections": [
                    {
                        "id": "datos_basicos_aerogenerador",
                        "title": _normalize_spanish_text("Datos bÃ¡sicos del aerogenerador"),
                        "blocks": [basic_data_table],
                    },
                    {
                        "id": "tabla_velocidades_potencia",
                        "title": _normalize_spanish_text("Tabla editable de velocidades y potencia"),
                        "blocks": [speed_power_table] if speed_power_table else [],
                    },
                    {
                        "id": "grafico_potencia_cp",
                        "title": _normalize_spanish_text("GrÃ¡fico de potencia y Cp"),
                        "blocks": [cp_figure_block],
                    },
                    {
                        "id": "tabla_cp_calculado",
                        "title": _normalize_spanish_text("Tabla de Cp calculado"),
                        "blocks": [cp_table] if cp_table else [],
                    },
                ],
            }
        ],
    }

    return {
        "document_id": "informe_tecnico",
        "title": "Informe tÃ©cnico",
        "project_name": _normalize_spanish_text(project_name),
        "file_stem": "informe_tecnico",
        "intro_paragraphs": [
            "Este documento presenta la configuraciÃ³n tÃ©cnica inicial del proyecto eÃ³lico y comienza con la definiciÃ³n del aerogenerador seleccionado y su base de desempeÃ±o.",
        ],
        "sections": [
            {
                "id": "eleccion_aerogenerador",
                "title": "ElecciÃ³n del aerogenerador",
                "description": "SecciÃ³n dedicada a documentar el aerogenerador seleccionado, sus parÃ¡metros geomÃ©tricos y la base de desempeÃ±o usada para el resto del proyecto.",
                "subsections": [
                    {
                        "id": "datos_basicos_aerogenerador",
                        "title": "Datos bÃ¡sicos del aerogenerador",
                        "blocks": [basic_data_table],
                    },
                    {
                        "id": "tabla_velocidades_potencia",
                        "title": "Tabla editable de velocidades y potencia",
                        "blocks": [speed_power_table] if speed_power_table else [],
                    },
                    {
                        "id": "grafico_potencia_cp",
                        "title": "GrÃ¡fico de potencia y Cp",
                        "blocks": [cp_figure_block],
                    },
                    {
                        "id": "tabla_cp_calculado",
                        "title": "Tabla de Cp calculado",
                        "blocks": [cp_table] if cp_table else [],
                    },
                ],
            }
        ],
    }

