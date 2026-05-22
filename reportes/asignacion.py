import pandas as pd

from .latex import _append_latex_section, _escape_latex_text
from .manifiestos import (
    _build_key_value_table,
    _build_site_data_table,
    _format_coordinate_pair,
    _format_report_metric,
    _report_has_value,
    _resolve_figure_refs,
    build_report_payload,
)


def build_assignment_report_payload(report_manifest):
    manifest = report_manifest or {}
    general_payload = build_report_payload(manifest)

    project_context = manifest.get("project_context", {}) or {}
    calculation_context = manifest.get("calculation_context", {}) or {}
    result_summary = manifest.get("result_summary", {}) or {}
    loss_summary = manifest.get("loss_summary", {}) or {}

    project_name = str(manifest.get("project_name") or "").strip()
    profile_label = project_context.get("project_profile_label", "Sin perfil")
    table_payloads = manifest.get("table_payloads", {}) or {}
    artifact_context = manifest.get("artifact_context", {}) or {}
    site_data_table = _build_site_data_table(
        "Resumen del sitio y la fuente de datos",
        calculation_context=calculation_context,
        project_name=project_name,
        note="Tabla base para la seccion de sitio y datos en la ruta academica.",
    )
    coords = _format_coordinate_pair(calculation_context.get("site_latitude"), calculation_context.get("site_longitude"))
    site_map_caption = "Mapa del sitio de estudio"
    if coords:
        site_map_caption += f" ({coords})"
    if _report_has_value(calculation_context.get("site_source")):
        site_map_caption += f" - fuente: {calculation_context.get('site_source')}"
    data_source = [
        ("Proyecto / sitio", project_name or None),
        ("Coordenadas", coords),
        ("Fuente de datos", calculation_context.get("site_source")),
        ("Fecha inicial", calculation_context.get("site_start_date")),
        ("Fecha final", calculation_context.get("site_end_date")),
        ("Base de viento", calculation_context.get("base_viento")),
        ("Direccion usada", calculation_context.get("direccion_usada")),
        ("Altura de analisis", _format_report_metric(calculation_context.get("altura_deseada_m"), 2, "m")),
        ("Rugosidad / terreno", calculation_context.get("roughness_label")),
    ]
    turbine_table = _build_key_value_table(
        "Resumen del aerogenerador y parque",
        [
            ("Numero de turbinas", _format_report_metric(calculation_context.get("n_turbinas"), 0)),
            ("Potencia nominal por turbina", _format_report_metric(result_summary.get("potencia_nominal_turbina_kw"), 2, "kW")),
            ("Potencia total estimada", _format_report_metric(
                (float(calculation_context.get("n_turbinas")) * float(result_summary.get("potencia_nominal_turbina_kw")) / 1000.0)
                if _report_has_value(calculation_context.get("n_turbinas")) and _report_has_value(result_summary.get("potencia_nominal_turbina_kw"))
                else None,
                2,
                "MW",
            )),
        ],
    )
    methodology_table = _build_key_value_table(
        "Parametros metodologicos",
        [
            ("Base de viento / perfil", calculation_context.get("base_viento")),
            ("Modo estadistico", calculation_context.get("modo_estadistico")),
            ("Metodo de detalle", calculation_context.get("metodo_detalle")),
            ("Tratamiento de estelas", calculation_context.get("wake_mode")),
            ("Ct", _format_report_metric(calculation_context.get("ct"), 3)),
            ("kw", _format_report_metric(calculation_context.get("kw"), 3)),
        ],
    )
    result_table = _build_key_value_table(
        "Resumen AEP",
        [
            ("AEP bruta total", _format_report_metric(result_summary.get("aep_bruta_total_mwh"), 2, "MWh/ano")),
            ("AEP neta total", _format_report_metric(result_summary.get("aep_neta_total_mwh"), 2, "MWh/ano")),
            ("Factor de planta bruto", _format_report_metric(result_summary.get("factor_planta_bruto_pct"), 2, "%")),
            ("Factor de planta neto", _format_report_metric(result_summary.get("factor_planta_neto_pct"), 2, "%")),
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
    checklist_table = _build_key_value_table(
        "Chequeos informativos de la consigna",
        [
            ("Potencia total <= 10 MW", "Validar con la tabla de turbinas y potencia."),
            ("Sitio en La Guajira", "Completar con coordenadas, mapa y justificacion."),
            ("Sectores direccionales >= 12", "La app trabaja con 16 sectores."),
            ("Correccion por densidad", "Explicar el criterio usado o justificar si queda pendiente."),
        ],
    )
    figure_refs = {
        "site_data": _resolve_figure_refs([
            {
                "id": "site_map",
                "title": "Mapa del sitio",
                "label": "fig:mapa_sitio",
                "path": "04_Figuras_mapas/mapa_sitio.(png|html)",
                "note": "Si no hay mapa exportado, insertar un mapa manual o una referencia cartografica equivalente.",
                "caption": site_map_caption,
            },
            {
                "id": "wind_rose",
                "title": "Rosa de vientos",
                "label": "fig:rosa_vientos",
                "path": "04_Figuras_mapas/rosa_vientos.(png|html)",
                "note": "Usar el artefacto exportado desde Fase 5 cuando este disponible.",
            },
        ], artifact_context),
        "directional_distribution": _resolve_figure_refs([
            {
                "id": "wind_rose",
                "title": "Rosa de vientos y distribucion sectorial",
                "label": "fig:direccion_rosa",
                "path": "04_Figuras_mapas/rosa_vientos.(png|html)",
                "note": "Complementar con comentario sobre los sectores dominantes.",
            },
        ], artifact_context),
        "layout_wakes": _resolve_figure_refs([
            {
                "id": "layout_wakes",
                "title": "Layout del parque",
                "label": "fig:layout_parque",
                "path": "04_Figuras_mapas/layout_parque.(png|html)",
                "note": "Si la superposicion de estelas no esta disponible, describir esta limitacion en el texto.",
            },
        ], artifact_context),
        "gross_net_aep": _resolve_figure_refs([
            {
                "id": "aep_losses",
                "title": "Resumen AEP y perdidas",
                "label": "fig:resumen_aep_perdidas",
                "path": "04_Figuras_mapas/resumen_aep_perdidas.(png|html)",
                "note": "Figura recomendada para apoyar la lectura del balance energetico.",
            },
        ], artifact_context),
        "sensitivities_uncertainty": _resolve_figure_refs([
            {
                "id": "sensibilidad_aep",
                "title": "Sensibilidad del AEP neto",
                "label": "fig:sensibilidad_aep",
                "path": "04_Figuras_mapas/sensibilidad_aep.(png|html)",
                "note": "Usar si se desea apoyar la discusion de incertidumbre con una curva simple.",
            },
        ], artifact_context),
        "probability_curves": _resolve_figure_refs([
            {
                "id": "probability_curves",
                "title": "Curva de probabilidad por sector",
                "label": "fig:curva_probabilidad_sector",
                "path": "04_Figuras_mapas/curva_probabilidad_sector.(png|html)",
                "note": "Reutilizar este artefacto para la discusion de ocurrencia por intervalos y ajuste Weibull/Rayleigh.",
            },
            {
                "id": "probability_heatmap",
                "title": "Mapa sectorial de probabilidad",
                "label": "fig:mapa_probabilidad_sectorial",
                "path": "04_Figuras_mapas/mapa_probabilidad_sectorial.(png|html)",
                "note": "Complementa la lectura de la distribucion direccional y de las zonas de operacion.",
            },
        ], artifact_context),
    }
    losses_detail_table = table_payloads.get("losses_detail")
    sector_summary_table = table_payloads.get("sector_summary")
    sensitivity_table = table_payloads.get("sensitivity_summary")
    probability_intervals_table = table_payloads.get("probability_intervals")
    probability_operation_table = table_payloads.get("probability_operation")
    probability_sector_table = table_payloads.get("probability_sector_summary")

    def items_for(*texts):
        return [text for text in texts if _report_has_value(text)]

    sections = [
        {
            "id": "cover",
            "title": "Cover Page",
            "purpose": "Presentar el titulo del trabajo, el proyecto y los metadatos basicos del informe.",
            "suggested_content": ["Titulo del informe", "Nombre del proyecto", "Curso, institucion y autores cuando aplique"],
            "available_data_keys": ["project_context", "report_context"],
            "notes": ["Mantener esta portada editable para adaptarla al formato exigido por la asignacion."],
            "content_blocks": [{"title": "Metadatos disponibles", "items": items_for(
                f"Nombre del proyecto: {project_name}." if project_name else None,
                f"Perfil de proyecto activo: {profile_label}.",
                "Ruta dedicada a la asignacion academica, separada del flujo libre de la app.",
            )}],
            "latex_tables": [checklist_table] if checklist_table else [],
        },
        {
            "id": "abstract",
            "title": "Abstract and Keywords",
            "purpose": "Preparar un resumen corto del estudio y las palabras clave.",
            "suggested_content": ["Objetivo del estudio eolico", "Metodologia resumida", "Resultado energetico principal", "Lista breve de palabras clave"],
            "available_data_keys": ["result_summary", "calculation_context"],
            "notes": ["Agregar palabras clave manualmente en la version final."],
            "content_blocks": [{"title": "Puntos sugeridos para el abstract", "items": items_for(
                f"Metodo principal: {result_summary.get('metodo_principal')}." if _report_has_value(result_summary.get("metodo_principal")) else None,
                f"AEP neta total: {_format_report_metric(result_summary.get('aep_neta_total_mwh'), 2, 'MWh/ano')}." if _report_has_value(result_summary.get("aep_neta_total_mwh")) else None,
                "Completar una frase de contexto del sitio y una frase de cierre con hallazgos principales.",
            )}],
            "latex_tables": [table for table in [result_table, sector_summary_table] if table],
        },
        {
            "id": "introduction",
            "title": "1) Introduction and Objectives",
            "purpose": "Introducir el problema, el contexto y los objetivos del trabajo.",
            "suggested_content": ["Contexto general del estudio", "Motivacion del analisis", "Objetivo general y objetivos especificos"],
            "available_data_keys": ["project_context"],
            "notes": ["Puede reutilizar la introduccion tecnica del flujo libre y adaptarla al formato academico."],
            "content_blocks": [{"title": "Objetivos sugeridos", "items": items_for(
                "Presentar el potencial energetico del escenario evaluado.",
                "Justificar la seleccin de modelos, parametros y supuestos principales.",
                "Sintetizar resultados brutos, netos y sensibilidad para la entrega.",
            )}],
        },
        {
            "id": "site_data",
            "title": "2) Site and Data",
            "purpose": "Describir la localizacion, la fuente de datos y el recurso eolico base.",
            "suggested_content": ["Ubicacion del sitio", "Fuente y rango temporal de datos", "Descripcion del recurso eolico"],
            "available_data_keys": ["calculation_context"],
            "notes": ["Incluir mapas y anexos reproducibles en versiones futuras."],
            "content_blocks": [{"title": "Datos disponibles para esta seccion", "items": items_for(
                f"Proyecto / sitio: {project_name}." if project_name else None,
                f"Coordenadas del sitio: {coords}." if coords else None,
                f"Fuente de datos: {calculation_context.get('site_source')}." if _report_has_value(calculation_context.get("site_source")) else None,
                (
                    f"Rango temporal: {calculation_context.get('site_start_date')} a {calculation_context.get('site_end_date')}."
                    if _report_has_value(calculation_context.get("site_start_date")) or _report_has_value(calculation_context.get("site_end_date"))
                    else None
                ),
                f"Base de viento: {calculation_context.get('base_viento')}." if _report_has_value(calculation_context.get("base_viento")) else None,
                f"Direccion usada: {calculation_context.get('direccion_usada')}." if _report_has_value(calculation_context.get("direccion_usada")) else None,
                f"Altura deseada: {_format_report_metric(calculation_context.get('altura_deseada_m'), 2, 'm')}." if _report_has_value(calculation_context.get("altura_deseada_m")) else None,
                "Describir manualmente la justificacion del sitio, el acceso, la cercania a red, el uso del suelo y cualquier restriccion territorial relevante.",
                "Si la consigna exige argumentacion sobre La Guajira u otra localizacion especifica, completarla manualmente con fuentes y criterio tecnico.",
            )}],
            "latex_tables": [table for table in [site_data_table, _build_key_value_table("Datos base del sitio y recurso", data_source), sector_summary_table] if table],
            "figure_refs": figure_refs["site_data"],
        },
        {
            "id": "turbine",
            "title": "3) Turbine",
            "purpose": "Describir el aerogenerador base utilizado en el estudio.",
            "suggested_content": ["Caracteristicas generales del aerogenerador", "Potencia nominal y numero de turbinas"],
            "available_data_keys": ["calculation_context", "result_summary"],
            "notes": ["La curva de potencia detallada puede quedar en anexos mas adelante."],
            "content_blocks": [{"title": "Resumen del aerogenerador", "items": items_for(
                f"Numero de turbinas: {_format_report_metric(calculation_context.get('n_turbinas'), 0)}." if _report_has_value(calculation_context.get("n_turbinas")) else None,
                f"Potencia nominal por turbina: {_format_report_metric(result_summary.get('potencia_nominal_turbina_kw'), 2, 'kW')}." if _report_has_value(result_summary.get("potencia_nominal_turbina_kw")) else None,
                "Completar fabricante/modelo si la entrega exige identificacion explicita del equipo.",
            )}],
            "latex_tables": [turbine_table] if turbine_table else [],
        },
        {
            "id": "vertical_profiles",
            "title": "4) Vertical Profiles",
            "purpose": "Explicar el tratamiento del perfil vertical del viento.",
            "suggested_content": ["Modelo de perfil seleccionado", "Altura de analisis y supuestos"],
            "available_data_keys": ["calculation_context"],
            "notes": ["Conectar luego perfiles y figuras exportables desde Fase 2."],
            "content_blocks": [{"title": "Parametros disponibles", "items": items_for(
                f"Base de viento / extrapolacion: {calculation_context.get('base_viento')}." if _report_has_value(calculation_context.get("base_viento")) else None,
                f"Rugosidad/terreno: {calculation_context.get('roughness_label')}." if _report_has_value(calculation_context.get("roughness_label")) else None,
                "Explicar si se utilizo perfil exponencial, logaritmico o velocidades directas a 10 m / 50 m.",
            )}],
            "latex_tables": [table for table in [methodology_table, sensitivity_table] if table],
        },
        {
            "id": "directional_distribution",
            "title": "5) Directional Distribution",
            "purpose": "Documentar la caracterizacion direccional del recurso.",
            "suggested_content": ["Sectores direccionales utilizados", "Comportamiento direccional del recurso"],
            "available_data_keys": ["calculation_context"],
            "notes": ["La app trabaja con una base de 16 sectores; en esta ruta se puede advertir si la consigna pide minimo 12."],
            "content_blocks": [{"title": "Orientacion para la redaccion", "items": items_for(
                "Describir los sectores dominantes y su impacto sobre la energia capturada.",
                "Relacionar la distribucion direccional con el layout y la estimacion de estelas.",
            )}],
            "figure_refs": figure_refs["directional_distribution"] + figure_refs["probability_curves"],
        },
        {
            "id": "power_density",
            "title": "6) Power Curve and Density Correction",
            "purpose": "Relacionar la curva de potencia y la correccion por densidad del aire.",
            "suggested_content": ["Descripcion de la curva de potencia", "Criterio de correccion por densidad"],
            "available_data_keys": ["result_summary"],
            "notes": ["Agregar la ecuacion y la tabla de correccion en una version mas completa."],
            "content_blocks": [{"title": "Puntos a completar", "items": items_for(
                "Explicar la curva de potencia adoptada y sus puntos caracteristicos.",
                "Indicar si la correccion por densidad se aplico explicitamente o queda documentada como supuesto.",
            )}],
            "latex_tables": [turbine_table] if turbine_table else [],
        },
        {
            "id": "layout_wakes",
            "title": "7) Layout and Wakes",
            "purpose": "Describir el arreglo del parque y el tratamiento de estelas.",
            "suggested_content": ["Configuracion del layout", "Modelo de estelas y parametros"],
            "available_data_keys": ["calculation_context", "loss_summary"],
            "notes": ["Mantener este bloque desacoplado del flujo libre; aqui solo se especializa la plantilla."],
            "content_blocks": [{"title": "Datos disponibles para layout y estelas", "items": items_for(
                f"Modo de estelas: {calculation_context.get('wake_mode')}." if _report_has_value(calculation_context.get("wake_mode")) else None,
                f"Ct: {_format_report_metric(calculation_context.get('ct'), 3)}." if _report_has_value(calculation_context.get("ct")) else None,
                f"kw: {_format_report_metric(calculation_context.get('kw'), 3)}." if _report_has_value(calculation_context.get("kw")) else None,
                f"Perdida por estela: {_format_report_metric(loss_summary.get('perdida_estela_mwh'), 2, 'MWh/ano')}." if _report_has_value(loss_summary.get("perdida_estela_mwh")) else None,
                "Complementar con una explicacion breve del criterio de ubicacion de turbinas y del alcance del modelo de estelas.",
            )}],
            "latex_tables": [table for table in [methodology_table, loss_table, losses_detail_table] if table],
            "figure_refs": figure_refs["layout_wakes"],
        },
        {
            "id": "gross_net_aep",
            "title": "8) Gross and Net AEP",
            "purpose": "Presentar la produccion energetica anual bruta y neta.",
            "suggested_content": ["AEP bruta total", "AEP neta total", "Factor de planta"],
            "available_data_keys": ["result_summary", "loss_summary"],
            "notes": ["Seccion candidata para futuras tablas automaticas."],
            "content_blocks": [{"title": "Resumen energetico", "items": items_for(
                f"AEP bruta total: {_format_report_metric(result_summary.get('aep_bruta_total_mwh'), 2, 'MWh/ano')}." if _report_has_value(result_summary.get("aep_bruta_total_mwh")) else None,
                f"AEP neta total: {_format_report_metric(result_summary.get('aep_neta_total_mwh'), 2, 'MWh/ano')}." if _report_has_value(result_summary.get("aep_neta_total_mwh")) else None,
                f"Factor de planta bruto: {_format_report_metric(result_summary.get('factor_planta_bruto_pct'), 2, '%')}." if _report_has_value(result_summary.get("factor_planta_bruto_pct")) else None,
                f"Factor de planta neto: {_format_report_metric(result_summary.get('factor_planta_neto_pct'), 2, '%')}." if _report_has_value(result_summary.get("factor_planta_neto_pct")) else None,
            )}],
            "latex_tables": [table for table in [result_table, loss_table, losses_detail_table] if table],
            "figure_refs": figure_refs["gross_net_aep"],
        },
        {
            "id": "sensitivities_uncertainty",
            "title": "9) Sensitivities and Uncertainty",
            "purpose": "Registrar sensibilidades y notas para futura discusion de incertidumbre.",
            "suggested_content": ["Sensibilidades del AEP", "Observaciones de incertidumbre"],
            "available_data_keys": ["calculation_context", "loss_summary"],
            "notes": ["La incertidumbre puede empezar como discusion cualitativa mientras se prepara una capa mas formal."],
            "content_blocks": [{"title": "Puntos disponibles", "items": items_for(
                f"Perdida por disponibilidad: {_format_report_metric(loss_summary.get('perdida_disponibilidad_mwh'), 2, 'MWh/ano')}." if _report_has_value(loss_summary.get("perdida_disponibilidad_mwh")) else None,
                f"Perdida electrica: {_format_report_metric(loss_summary.get('perdida_electrica_mwh'), 2, 'MWh/ano')}." if _report_has_value(loss_summary.get("perdida_electrica_mwh")) else None,
                f"Otras perdidas: {_format_report_metric(loss_summary.get('otras_perdidas_mwh'), 2, 'MWh/ano')}." if _report_has_value(loss_summary.get("otras_perdidas_mwh")) else None,
                "Cerrar con una nota sobre incertidumbre cualitativa y posibles escenarios a contrastar.",
            )}],
            "latex_tables": [table for table in [loss_table, sensitivity_table] if table],
            "figure_refs": figure_refs["sensitivities_uncertainty"],
        },
        {
            "id": "conclusions",
            "title": "10) Conclusions",
            "purpose": "Cerrar el informe con una sintesis de resultados y proximos pasos.",
            "suggested_content": ["Hallazgos principales", "Recomendaciones o lineas futuras"],
            "available_data_keys": ["result_summary", "loss_summary"],
            "notes": ["Redactar de manera breve y verificable."],
            "content_blocks": [{"title": "Pistas para las conclusiones", "items": items_for(
                f"Destacar el AEP neto total: {_format_report_metric(result_summary.get('aep_neta_total_mwh'), 2, 'MWh/ano')}." if _report_has_value(result_summary.get("aep_neta_total_mwh")) else None,
                "Relacionar el resultado con las principales perdidas y con la sensibilidad observada.",
                "Indicar mejoras futuras: mas figuras, anexos reproducibles y validacion de incertidumbre.",
            )}],
        },
        {
            "id": "references",
            "title": "11) References (APA)",
            "purpose": "Reservar el espacio para las referencias del trabajo.",
            "suggested_content": ["Fuentes de datos", "Modelos utilizados", "Bibliografia tecnica y academica"],
            "available_data_keys": ["report_context"],
            "notes": ["Usar APA como convencion sugerida en esta ruta especifica."],
            "content_blocks": [{"title": "Guia para referencias APA", "items": items_for(
                "Citar la fuente de viento utilizada, manuales del aerogenerador y bibliografia del modelo de estelas.",
                "Mantener consistencia entre citas en texto, anexos y lista final de referencias.",
            )}],
        },
    ]

    return {
        "title": "Plantilla de informe para consigna academica de parque eolico",
        "subtitle": "Ruta opcional y especifica para la entrega de la asignacion",
        "project_name": project_name,
        "report_style": "assignment_academic",
        "citation_style": "APA",
        "include_ai_declaration": True,
        "sections": sections,
        "appendix_sections": [
            {
                "id": "assignment_appendix_results",
                "appendix_file_name": "appendix_assignment_results.tex",
                "title": "Anexo A - Tablas reproducibles del escenario",
                "purpose": "Agrupar tablas compactas del escenario principal para apoyar la entrega y los anexos.",
                "suggested_content": [],
                "available_data_keys": ["table_payloads"],
                "notes": ["La tabla completa por sector y los resultados originales siguen disponibles en los exportes Excel/CSV."],
                "latex_tables": [table for table in [sector_summary_table, losses_detail_table, sensitivity_table] if table],
            },
            {
                "id": "assignment_appendix_probability",
                "appendix_file_name": "appendix_probability_tables.tex",
                "title": "Anexo B - Soporte de curvas de probabilidad",
                "purpose": "Vincular la discusion de Fase 3.5 con la ruta academica sin exigir una recompilacion manual separada.",
                "suggested_content": [],
                "available_data_keys": ["table_payloads", "artifact_context"],
                "notes": ["Si faltan figuras estaticas, el informe conserva referencias editables a los artefactos HTML o a la insercion manual."],
                "latex_tables": [table for table in [probability_sector_table, probability_intervals_table, probability_operation_table] if table],
                "figure_refs": figure_refs["probability_curves"],
            },
            {
                "id": "assignment_appendix_checks",
                "appendix_file_name": "appendix_assignment_checks.tex",
                "title": "Anexo C - Chequeos y trazabilidad de la entrega",
                "purpose": "Dejar una base editable para completar el estado de cumplimiento, anexos reproducibles y referencias de la consigna.",
                "suggested_content": [],
                "available_data_keys": ["project_context", "table_payloads"],
                "notes": ["Mantener este anexo como lista de control editable antes de la entrega final."],
                "latex_tables": [table for table in [checklist_table] if table],
            },
        ],
        "appendix_hints": [
            "Anexos reproducibles con parametros, tablas y resultados complementarios",
            "Evidencias de mapas, figuras y configuraciones exportadas",
        ],
        "references_hint": "Completar referencias en formato APA antes de la entrega final.",
        "ai_declaration_text": "Incluir una declaracion explicita de uso de IA antes de la seccion de referencias, segun la consigna.",
        "package_plan": ["01_Informe", "02_Anexos", "03_Datos_crudos", "04_Figuras_mapas"],
        "general_payload": general_payload,
    }


def build_assignment_checklist(report_manifest):
    manifest = report_manifest or {}
    calculation_context = manifest.get("calculation_context", {}) or {}
    result_summary = manifest.get("result_summary", {}) or {}
    project_context = manifest.get("project_context", {}) or {}

    n_turbinas = calculation_context.get("n_turbinas")
    potencia_kw = result_summary.get("potencia_nominal_turbina_kw")
    total_power_mw = None
    if _report_has_value(n_turbinas) and _report_has_value(potencia_kw):
        total_power_mw = float(n_turbinas) * float(potencia_kw) / 1000.0

    def item(name, status, detail):
        return {"item": name, "status": status, "detail": detail}

    return [
        item("Minimo 5 turbinas", "available" if _report_has_value(n_turbinas) and float(n_turbinas) >= 5 else "warning", f"Valor detectado: {int(float(n_turbinas))}." if _report_has_value(n_turbinas) else "No se pudo verificar automaticamente."),
        item("Potencia total <= 10 MW", "available" if _report_has_value(total_power_mw) and total_power_mw <= 10.0 else "warning", f"Potencia estimada: {total_power_mw:.2f} MW." if _report_has_value(total_power_mw) else "No se pudo estimar automaticamente."),
        item("Sitio en La Guajira", "warning", "Verificacion manual recomendada con coordenadas, mapa y justificacion del sitio."),
        item("Sectores direccionales >= 12", "available", "La base actual de la aplicacion trabaja con 16 sectores direccionales."),
        item("Informacion de perfiles verticales", "available" if _report_has_value(calculation_context.get("base_viento")) and _report_has_value(calculation_context.get("altura_deseada_m")) else "missing", "Se detectaron base de viento y altura deseada." if _report_has_value(calculation_context.get("base_viento")) and _report_has_value(calculation_context.get("altura_deseada_m")) else "Falta contexto minimo para describir perfiles verticales."),
        item("Contexto de correccion por densidad", "suggested", "La correccion por densidad debe explicitarse en la seccion 6 de esta ruta de entrega."),
        item("Contexto de modelo de estelas", "available" if _report_has_value(calculation_context.get("wake_mode")) else "missing", f"Configuracion detectada: {calculation_context.get('wake_mode')}." if _report_has_value(calculation_context.get("wake_mode")) else "No se detecto configuracion de estelas."),
        item("Contexto de AEP bruto y neto", "available" if _report_has_value(result_summary.get("aep_bruta_total_mwh")) and _report_has_value(result_summary.get("aep_neta_total_mwh")) else "missing", "Resultados principales disponibles en Fase 5." if _report_has_value(result_summary.get("aep_bruta_total_mwh")) and _report_has_value(result_summary.get("aep_neta_total_mwh")) else "Faltan resultados energeticos para documentar."),
        item("Contexto de sensibilidad/incertidumbre", "available" if _report_has_value(calculation_context.get("modo_estadistico")) else "suggested", "Existe contexto para redactar sensibilidad y una discusion inicial de incertidumbre." if _report_has_value(calculation_context.get("modo_estadistico")) else "Agregar una discusion cualitativa de incertidumbre en la entrega."),
        item("Declaracion de IA antes de referencias", "available" if str(project_context.get("project_profile", "")).lower() == "academic" else "suggested", "La ruta de asignacion ya prepara una seccion de declaracion de IA antes de referencias."),
    ]


def build_assignment_data_provenance(config=None, report_manifest=None):
    config = config or {}
    manifest = report_manifest or {}
    calculation_context = manifest.get("calculation_context", {}) or {}

    notes = [
        "Este archivo resume la procedencia de datos conocida en la aplicacion al momento de exportar.",
        "Los archivos crudos originales pueden no estar empaquetados todavia en esta version.",
    ]
    if not _report_has_value(config.get("nasa_fuente")):
        notes.append("No se detecto una fuente de viento persistida de forma explicita.")

    return {
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "source_type": config.get("nasa_fuente", ""),
        "latitude": config.get("nasa_lat", ""),
        "longitude": config.get("nasa_lon", ""),
        "start_date": config.get("nasa_inicio", ""),
        "end_date": config.get("nasa_fin", ""),
        "base_viento": calculation_context.get("base_viento", ""),
        "modo_estadistico": calculation_context.get("modo_estadistico", ""),
        "metodo_detalle": calculation_context.get("metodo_detalle", ""),
        "direccion_usada": calculation_context.get("direccion_usada", ""),
        "notes": notes,
    }


def build_assignment_data_provenance_text(provenance):
    data = provenance or {}
    notes = data.get("notes", []) or []
    lines = [
        "Procedencia de datos para la ruta de asignacion",
        "",
        f"Fuente: {data.get('source_type', '') or 'No especificada'}",
        f"Latitud: {data.get('latitude', '') or 'No disponible'}",
        f"Longitud: {data.get('longitude', '') or 'No disponible'}",
        f"Fecha inicial: {data.get('start_date', '') or 'No disponible'}",
        f"Fecha final: {data.get('end_date', '') or 'No disponible'}",
        f"Base de viento: {data.get('base_viento', '') or 'No disponible'}",
        f"Modo estadistico: {data.get('modo_estadistico', '') or 'No disponible'}",
        f"Metodo detalle: {data.get('metodo_detalle', '') or 'No disponible'}",
        "",
        "Notas:",
    ]
    for note in notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def build_assignment_figure_manifest(report_manifest=None, exported_figures=None):
    manifest = report_manifest or {}
    calculation_context = manifest.get("calculation_context", {}) or {}
    result_summary = manifest.get("result_summary", {}) or {}
    exported_figures = exported_figures or []
    exported_map = {
        str(item.get("id")): item
        for item in exported_figures
        if str(item.get("id") or "").strip()
    }

    def merge_export_state(figure_id, default_status, source_hint):
        exported = exported_map.get(figure_id, {})
        status = exported.get("status") or default_status
        note = exported.get("note", "")
        files = [exported.get("path")] if exported.get("path") else []
        if figure_id == "layout_wakes" and files:
            note = (note + " " if note else "") + "Se exporta el layout actual; la superposicion explicita de estelas sigue pendiente."
        return {
            "id": figure_id,
            "status": status,
            "source_hint": source_hint,
            "exported_files": files,
            "note": note,
        }

    figures = [
        {
            "title": "Mapa del sitio",
            **merge_export_state(
                "site_map",
                "suggested",
                "Integrar la figura generada desde las coordenadas persistidas del proyecto o complementar con cartografia manual si hiciera falta.",
            ),
        },
        {
            "title": "Rosa de vientos",
            **merge_export_state(
                "wind_rose",
                "available",
                "Resultado visual reconstruido desde la caracterizacion direccional disponible en Fase 5.",
            ),
        },
        {
            "title": "Curvas de probabilidad",
            **merge_export_state(
                "probability_curves",
                "available",
                "Resultado visual derivado de Fase 3.5; en Fase 5 aun no se reconstruye de forma dedicada para exportacion.",
            ),
        },
        {
            "title": "Mapa sectorial de probabilidad",
            **merge_export_state(
                "probability_heatmap",
                "available",
                "Heatmap derivado de la distribucion por sectores e intervalos de Fase 3.5.",
            ),
        },
        {
            "title": "Layout y estelas",
            **merge_export_state(
                "layout_wakes",
                "available" if _report_has_value(calculation_context.get("wake_mode")) else "suggested",
                "Resultado visual derivado del layout actual del parque y del contexto de estelas.",
            ),
        },
        {
            "title": "Resumen AEP y perdidas",
            **merge_export_state(
                "aep_losses",
                "available" if _report_has_value(result_summary.get("aep_neta_total_mwh")) else "suggested",
                "Resultado visual derivado de Fase 5.",
            ),
        },
    ]
    return {
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "figures": figures,
        "notes": [
            "Este manifiesto lista figuras sugeridas para la entrega.",
            "Cuando el entorno permite imagen estatica se exporta PNG; en caso contrario se genera HTML interactivo editable.",
        ],
    }


def build_assignment_figure_manifest_text(figure_manifest):
    data = figure_manifest or {}
    figures = data.get("figures", []) or []
    notes = data.get("notes", []) or []
    lines = ["Manifiesto de figuras y mapas sugeridos", ""]
    for fig in figures:
        exported_files = fig.get("exported_files", []) or []
        suffix = f" | archivos: {', '.join(exported_files)}" if exported_files else ""
        note = f" | nota: {fig.get('note', '')}" if fig.get("note") else ""
        lines.append(f"- {fig.get('title', 'Figura')} [{fig.get('status', 'suggested')}]: {fig.get('source_hint', '')}{suffix}{note}")
    lines.extend(["", "Notas:"])
    for note in notes:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def build_assignment_latex_skeleton(assignment_report_payload):
    payload = assignment_report_payload or {}
    title = _escape_latex_text(payload.get("title", "Plantilla de asignacion"))
    subtitle = _escape_latex_text(payload.get("subtitle", "Borrador editable"))
    project_name = _escape_latex_text(payload.get("project_name", ""))
    citation_style = _escape_latex_text(payload.get("citation_style", "APA"))
    sections = payload.get("sections", []) or []
    appendix_sections = payload.get("appendix_sections", []) or []
    appendix_hints = payload.get("appendix_hints", []) or []
    references_hint = _escape_latex_text(payload.get("references_hint", ""))
    ai_declaration_text = _escape_latex_text(payload.get("ai_declaration_text", ""))
    package_plan = payload.get("package_plan", []) or []

    lines = [
        r"\documentclass[12pt]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[spanish]{babel}",
        r"\usepackage{geometry}",
        r"\geometry{margin=2.5cm}",
        r"\usepackage{graphicx}",
        r"\usepackage{hyperref}",
        r"\usepackage{booktabs}",
        r"\usepackage{tabularx}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
        r"\usepackage{float}",
        r"\newcolumntype{Y}{>{\raggedright\arraybackslash}X}",
        "",
        f"% Plantilla de asignacion con citas sugeridas en estilo {citation_style}",
        "% Este exporte single-file prioriza compilacion segura y deja las figuras externas como referencias editables.",
        "",
        r"\title{" + title + r"\\[0.5em]\large " + subtitle + r"}",
        r"\author{Proyecto eolico}",
        r"\date{\today}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
    ]
    if project_name:
        lines.extend([
            r"\noindent\textbf{Nombre del proyecto:} " + project_name + r"\\",
            r"\textbf{Ruta:} Workspace opcional para la asignacion academica" + r"\\",
            r"\textbf{Citas sugeridas:} " + citation_style,
            "",
        ])
    if package_plan:
        lines.extend([r"\subsection*{Paquete sugerido de entrega}", r"\begin{itemize}"])
        for folder in package_plan:
            lines.append(r"\item " + _escape_latex_text(folder))
        lines.extend([r"\end{itemize}", ""])
    lines.extend([r"\tableofcontents", r"\newpage", ""])

    non_reference_sections = [s for s in sections if s.get("id") != "references"]
    reference_sections = [s for s in sections if s.get("id") == "references"]
    for section in non_reference_sections:
        _append_latex_section(lines, section, include_static_figures=False)
    if ai_declaration_text:
        lines.extend([r"\section*{Declaracion de uso de IA}", ai_declaration_text, ""])
    for section in reference_sections:
        _append_latex_section(lines, section, include_static_figures=False)
    if appendix_sections or appendix_hints:
        lines.extend([r"\appendix", ""])
        for appendix in appendix_sections:
            _append_latex_section(lines, appendix, include_static_figures=False)
        if appendix_hints:
            lines.extend([r"\section{Anexos sugeridos}", r"\begin{itemize}"])
            for hint in appendix_hints:
                lines.append(r"\item " + _escape_latex_text(hint))
            lines.extend([r"\end{itemize}", ""])
    if references_hint:
        lines.extend([r"% Nota para referencias", f"% {references_hint}", ""])
    lines.extend([r"\end{document}", ""])
    return "\n".join(lines)
