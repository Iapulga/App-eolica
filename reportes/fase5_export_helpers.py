import hashlib
import io
import json
import re

import pandas as pd

from .contexto import get_export_metadata, get_project_context, get_report_context
from .docx import build_informe_tecnico_docx
from .figuras import (
    build_figure_export_bundle,
    build_indexed_appendix_annex_bundle,
    build_probability_curve_bundle,
    build_site_map_bundle,
)
from .informe_tecnico import build_informe_tecnico_word_model
from .latex import build_latex_appendix_pack, build_latex_skeleton
from .manifiestos import build_report_payload, dataframe_to_table_payload, get_report_manifest
from .paquete import build_appendix_pack_files, build_appendix_pack_zip_bytes
from .pdf_tecnico import build_informe_tecnico_pdf

RUNTIME_CONTEXT_STATE_KEY = "fase5_runtime_export_context"
HEAVY_EXPORT_STATE_KEY = "fase5_heavy_export_artifacts"
INFORME_TECNICO_PDF_STATE_KEY = "fase5_informe_tecnico_pdf_artifact"
INFORME_TECNICO_DOCX_STATE_KEY = "fase5_informe_tecnico_docx_artifact"
INFORME_TECNICO_META_STATE_KEY = "fase5_informe_tecnico_meta"


def exportar_excel(
    resumen_df,
    perdidas_df,
    sector_df,
    export_metadata_df=None,
    report_manifest_df=None,
    comparacion_df=None,
    comparacion_sector_df=None,
):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        resumen_df.to_excel(writer, index=False, sheet_name="Resumen")
        perdidas_df.to_excel(writer, index=False, sheet_name="Perdidas")
        sector_df.to_excel(writer, index=False, sheet_name="Sectorial")
        if export_metadata_df is not None:
            export_metadata_df.to_excel(writer, index=False, sheet_name="Metadata_exportacion")
        if report_manifest_df is not None:
            report_manifest_df.to_excel(writer, index=False, sheet_name="Manifiesto_reporte")
        if comparacion_df is not None:
            comparacion_df.to_excel(writer, index=False, sheet_name="Comparacion_metodos")
        if comparacion_sector_df is not None:
            comparacion_sector_df.to_excel(writer, index=False, sheet_name="Comparacion_sectorial")
    output.seek(0)
    return output.getvalue()


def _stable_frame_hash(df, columns=None):
    if df is None or len(df) == 0:
        return "empty"
    frame = df.copy()
    if columns:
        available_columns = [col for col in columns if col in frame.columns]
        if available_columns:
            frame = frame[available_columns].copy()
    for col in frame.columns:
        if str(frame[col].dtype).startswith("datetime"):
            frame[col] = frame[col].astype(str)
    frame = frame.sort_index(axis=1)
    return hashlib.md5(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()


def build_basic_export_bundle(config, context):
    project_name_default = context["project_name_default"]
    report_context = get_report_context(config)

    resumen_export = pd.DataFrame({
        "Indicador": [
            "Método principal",
            "AEP bruta parque (MWh/año)",
            "AEP neta parque (MWh/año)",
            "Factor de planta bruto (%)",
            "Factor de planta neto (%)",
            "AEP bruta por turbina (MWh/año)",
            "AEP neta por turbina (MWh/año)",
            "Potencia nominal por turbina (kW)",
            "Número de turbinas",
            "Potencia instalada (MW)",
            "Moneda base",
            "Moneda visualización",
            "Tasa COP/USD",
            "CAPEX total",
            "OPEX anual total",
            "VP costos",
            "LCOE (display, kWh)",
            "LCOE (display, MWh)",
        ],
        "Valor": [
            context["metodo_detalle"],
            context["res"]["aep_bruta_total"],
            context["res"]["aep_neta_total"],
            context["res"]["factor_planta_bruto"],
            context["res"]["factor_planta_neto"],
            context["res"]["aep_bruta_turbina"],
            context["res"]["aep_neta_turbina"],
            context["res"]["potencia_nominal_turbina_w"] / 1000.0,
            context["n_turbinas"],
            context.get("economics", {}).get("base_metrics", {}).get("potencia_instalada_mw"),
            context.get("economics", {}).get("moneda_base"),
            context.get("economics", {}).get("moneda_visualizacion"),
            context.get("economics", {}).get("fx_rate_cop_per_usd"),
            context.get("economics", {}).get("capex_total_display", context.get("economics", {}).get("capex_total")),
            context.get("economics", {}).get("opex_total_anual_display", context.get("economics", {}).get("opex_total_anual")),
            context.get("economics", {}).get("vp_costos_display", context.get("economics", {}).get("vp_costos")),
            context.get("economics", {}).get("lcoe_display_kwh", context.get("economics", {}).get("lcoe_kwh")),
            context.get("economics", {}).get("lcoe_display_mwh", context.get("economics", {}).get("lcoe_mwh")),
        ],
    })

    metadata_export = get_export_metadata(config=config, export_format="excel")
    metadata_export["project_name"] = project_name_default
    metadata_export_df = pd.DataFrame({"Campo": list(metadata_export.keys()), "Valor": list(metadata_export.values())})

    lightweight_table_payloads = {
        "losses_detail": dataframe_to_table_payload(
            context["tabla_perdidas"],
            title="Detalle de pérdidas del escenario",
            columns=["Concepto", "Pérdida (%)", "Energía perdida (MWh/año)"],
            max_rows=10,
            note="Tabla derivada directamente de los resultados de pérdidas calculados en Fase 5.",
        ),
        "sector_summary": dataframe_to_table_payload(
            context["df_aep_sector"],
            title="Resumen sectorial del AEP",
            columns=["Sector", "Frecuencia (%)", "AEP bruta parque (MWh/año)", "AEP neta sector (MWh/año)"],
            max_rows=8,
            note="Se muestran los primeros sectores para mantener el reporte compacto; la tabla completa sigue disponible en Excel/CSV.",
        ),
        "sensitivity_summary": dataframe_to_table_payload(
            pd.DataFrame([
                {"Parametro": "Variable analizada", "Valor": context["sens_variable"]},
                {"Parametro": "Base AEP con estela", "Valor": f"{context['res']['base_sens']:.2f} MWh/año"},
                {"Parametro": "Disponibilidad base", "Valor": f"{context['disp_pct']:.2f}%"},
                {"Parametro": "Pérdidas eléctricas base", "Valor": f"{context['elec_pct']:.2f}%"},
                {"Parametro": "Otras pérdidas base", "Valor": f"{context['otras_pct']:.2f}%"},
            ]),
            title="Resumen de sensibilidad configurada",
            columns=["Parametro", "Valor"],
            max_rows=10,
            note="Resumen directo de la configuración de sensibilidad simple mostrada en Fase 5.",
        ),
    }

    report_manifest = get_report_manifest(
        config=config,
        project_name=project_name_default,
        calculation_context={
            "base_viento": context["base_viento"],
            "modo_estadistico": context["modo_estadistico"],
            "metodo_detalle": context["metodo_detalle"],
            "altura_deseada_m": context["altura_deseada"],
            "direccion_usada": context["dir_altura"],
            "roughness_label": context["roughness_label"],
            "n_turbinas": context["n_turbinas"],
            "wake_mode": context["wake_mode"],
            "wake_manual_pct": context["wake_manual_pct"],
            "disponibilidad_pct": context["disp_pct"],
            "electricas_pct": context["elec_pct"],
            "otras_pct": context["otras_pct"],
            "sens_variable": context["sens_variable"],
            "ct": context["ct"],
            "kw": context["kw"],
            "site_latitude": config.get("nasa_lat"),
            "site_longitude": config.get("nasa_lon"),
            "site_source": config.get("nasa_fuente"),
            "site_start_date": config.get("nasa_inicio"),
            "site_end_date": config.get("nasa_fin"),
        },
        result_summary={
            "aep_bruta_total_mwh": context["res"]["aep_bruta_total"],
            "aep_neta_total_mwh": context["res"]["aep_neta_total"],
            "factor_planta_bruto_pct": context["res"]["factor_planta_bruto"],
            "factor_planta_neto_pct": context["res"]["factor_planta_neto"],
            "aep_bruta_turbina_mwh": context["res"]["aep_bruta_turbina"],
            "aep_neta_turbina_mwh": context["res"]["aep_neta_turbina"],
            "potencia_nominal_turbina_kw": context["res"]["potencia_nominal_turbina_w"] / 1000.0,
            "metodo_principal": context["metodo_detalle"],
        },
        loss_summary={
            "perdida_estela_mwh": context["res"]["perdida_estela_mwh"],
            "perdida_disponibilidad_mwh": context["res"]["perdida_disp_mwh"],
            "perdida_electrica_mwh": context["res"]["perdida_elec_mwh"],
            "otras_perdidas_mwh": context["res"]["perdida_otras_mwh"],
        },
        table_payloads=lightweight_table_payloads,
        artifact_context={"exported_figures": []},
        export_format="excel",
    )

    report_manifest_rows = [("generated_at_utc", report_manifest.get("generated_at_utc", ""))]
    for section_name in [
        "project_context",
        "report_context",
        "export_metadata",
        "calculation_context",
        "result_summary",
        "loss_summary",
    ]:
        section_data = report_manifest.get(section_name, {})
        for key, value in section_data.items():
            if isinstance(value, list):
                value = " | ".join(str(item) for item in value)
            report_manifest_rows.append((f"{section_name}.{key}", value))

    report_manifest_df = pd.DataFrame(report_manifest_rows, columns=["Campo", "Valor"])
    report_manifest_json = json.dumps(report_manifest, ensure_ascii=False, indent=2)
    report_payload = build_report_payload(report_manifest)
    latex_skeleton = build_latex_skeleton(report_payload)

    csv_bytes = context["df_aep_sector"].to_csv(index=False).encode("utf-8-sig")
    excel_bytes = exportar_excel(
        resumen_df=resumen_export,
        perdidas_df=context["tabla_perdidas"],
        sector_df=context["df_aep_sector"],
        export_metadata_df=metadata_export_df,
        report_manifest_df=report_manifest_df,
        comparacion_df=context.get("comp_df"),
        comparacion_sector_df=context.get("comp_sector_df"),
    )

    return {
        "project_context": get_project_context(config),
        "report_context": report_context,
        "resumen_export": resumen_export,
        "metadata_export": metadata_export,
        "metadata_export_df": metadata_export_df,
        "lightweight_table_payloads": lightweight_table_payloads,
        "report_manifest": report_manifest,
        "report_manifest_df": report_manifest_df,
        "report_manifest_json": report_manifest_json,
        "report_payload": report_payload,
        "latex_skeleton": latex_skeleton,
        "csv_bytes": csv_bytes,
        "excel_bytes": excel_bytes,
    }


def build_export_signature(config, context, basic_bundle=None):
    basic_bundle = basic_bundle or build_basic_export_bundle(config, context)
    payload = {
        "config": {
            key: config.get(key)
            for key in [
                "diametro", "densidad",
                "nasa_lat", "nasa_lon", "nasa_inicio", "nasa_fin", "nasa_fuente",
                "perfil_hhub", "perfil_roughness_label",
                "f3_modelo_altura", "f3_direccion_fuente", "f3_roughness_label", "f3_selected_sector",
                "f3_prob_vmax", "f3_prob_bin_width", "f3_prob_show_cdf", "f3_prob_cutin", "f3_prob_nominal", "f3_prob_cutout",
                "f4_ct", "f4_kw", "f4_base_viento", "f4_dir_altura", "f4_roughness_label", "f4_geom_speed",
                "f5_aep_bruta_total_mwh", "f5_aep_neta_total_mwh", "f5_factor_planta_bruto_pct", "f5_factor_planta_neto_pct",
                "f5_potencia_instalada_mw", "f5_capex_total", "f5_opex_total_anual", "f5_vp_costos", "f5_vp_energia",
                "f5_moneda_base", "f5_moneda_visualizacion", "f5_fx_mode", "f5_fx_rate_cop_per_usd", "f5_fx_timestamp",
                "f5_capex_total_display", "f5_opex_total_anual_display", "f5_vp_costos_display", "f5_lcoe_display_mwh", "f5_lcoe_display_kwh",
                "f5_lcoe_mwh", "f5_lcoe_kwh", "f5_unidad_monetaria",
            ]
        },
        "resumen": {
            "metodo_detalle": context["metodo_detalle"],
            "modo_estadistico": context["modo_estadistico"],
            "sens_variable": context["sens_variable"],
            "n_turbinas": context["n_turbinas"],
            "aep_bruta": context["res"]["aep_bruta_total"],
            "aep_neta": context["res"]["aep_neta_total"],
            "fp_bruto": context["res"]["factor_planta_bruto"],
            "fp_neto": context["res"]["factor_planta_neto"],
            "base_sens": context["res"]["base_sens"],
            "disp_pct": context["disp_pct"],
            "elec_pct": context["elec_pct"],
            "otras_pct": context["otras_pct"],
            "wake_mode": context["wake_mode"],
            "wake_manual_pct": context["wake_manual_pct"],
            "lcoe_mwh": context.get("lcoe", {}).get("lcoe_mwh"),
            "capex_total": context.get("economics", {}).get("capex_total"),
            "opex_total_anual": context.get("economics", {}).get("opex_total_anual"),
            "potencia_instalada_mw": context.get("economics", {}).get("base_metrics", {}).get("potencia_instalada_mw"),
            "moneda_base": context.get("economics", {}).get("moneda_base"),
            "moneda_visualizacion": context.get("economics", {}).get("moneda_visualizacion"),
            "fx_rate_cop_per_usd": context.get("economics", {}).get("fx_rate_cop_per_usd"),
            "lcoe_display_kwh": context.get("economics", {}).get("lcoe_display_kwh"),
        },
        "hashes": {
            "df_curva": _stable_frame_hash(context["df_curva_raw"]),
            "df_nasa": _stable_frame_hash(context["df_nasa"], ["timestamp", "WS10M", "WS50M", "WD10M", "WD50M"]),
            "df_layout": _stable_frame_hash(context["df_layout"]),
            "df_sector": _stable_frame_hash(context["df_aep_sector"]),
            "tabla_perdidas": _stable_frame_hash(context["tabla_perdidas"]),
        },
    }
    return hashlib.md5(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def build_informe_tecnico_signature(config, context):
    payload = {
        "config": {
            "project_name": context["project_name_default"],
            "diametro": config.get("diametro"),
            "densidad": config.get("densidad"),
            "nasa_lat": config.get("nasa_lat"),
            "nasa_lon": config.get("nasa_lon"),
            "nasa_inicio": config.get("nasa_inicio"),
            "nasa_fin": config.get("nasa_fin"),
            "perfil_hhub": config.get("perfil_hhub"),
            "perfil_roughness_label": config.get("perfil_roughness_label"),
            "f3_modelo_altura": config.get("f3_modelo_altura"),
            "f3_direccion_fuente": config.get("f3_direccion_fuente"),
            "f3_roughness_label": config.get("f3_roughness_label"),
            "f3_selected_sector": config.get("f3_selected_sector", config.get("f35_selected_sector")),
            "f3_prob_vmax": config.get("f3_prob_vmax", config.get("f35_vmax")),
            "f3_prob_bin_width": config.get("f3_prob_bin_width", config.get("f35_bin_width")),
            "f3_prob_show_cdf": config.get("f3_prob_show_cdf", config.get("f35_show_cdf")),
            "f3_prob_cutin": config.get("f3_prob_cutin", config.get("f35_cutin")),
            "f3_prob_nominal": config.get("f3_prob_nominal", config.get("f35_nominal")),
            "f3_prob_cutout": config.get("f3_prob_cutout", config.get("f35_cutout")),
            "f4_ct": config.get("f4_ct"),
            "f4_kw": config.get("f4_kw"),
            "f4_geom_speed": config.get("f4_geom_speed"),
            "f4_selected_sector": config.get("f4_selected_sector"),
            "f5_lcoe_mwh": config.get("f5_lcoe_mwh"),
            "f5_unidad_monetaria": config.get("f5_unidad_monetaria"),
        },
        "curve_hash": _stable_frame_hash(context["df_curva_raw"]),
        "nasa_hash": _stable_frame_hash(context["df_nasa"], ["timestamp", "WS10M", "WS50M", "WD10M", "WD50M"]),
        "layout_hash": _stable_frame_hash(context["df_layout"]),
        "sector_hash": _stable_frame_hash(context["df_aep_sector"]),
        "loss_hash": _stable_frame_hash(context["tabla_perdidas"]),
        "master_docx_hash": hashlib.md5(context.get("master_docx_bytes") or b"").hexdigest() if context.get("master_docx_bytes") else "no-master-docx",
        "master_docx_name": context.get("master_docx_name"),
    }
    return hashlib.md5(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def office_safe_file_name(base_name, extension):
    text = str(base_name or "informe_tecnico").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_") or "informe_tecnico"
    extension = str(extension or "").lstrip(".") or "bin"
    return f"{text}.{extension}"


def generate_heavy_export_artifacts(config, context, basic_bundle=None):
    basic_bundle = basic_bundle or build_basic_export_bundle(config, context)
    figure_export_bundle = build_figure_export_bundle([
        {
            "id": "wind_rose",
            "title": "Rosa de vientos",
            "stem": "rosa_vientos",
            "figure": context.get("fig_wind_rose_export"),
            "source_hint": "Rosa de vientos reconstruida desde la caracterizacion sectorial disponible en Fase 5.",
        },
        {
            "id": "layout_wakes",
            "title": "Layout del parque",
            "stem": "layout_parque",
            "figure": context.get("fig_layout_export"),
            "source_hint": "Layout actual del parque con diametro de rotor dibujado cuando esta disponible.",
        },
        {
            "id": "aep_losses",
            "title": "Resumen AEP y perdidas",
            "stem": "resumen_aep_perdidas",
            "figure": context.get("fig_resumen"),
            "source_hint": "Resumen energetico bruto y neto disponible en Fase 5.",
        },
        {
            "id": "loss_distribution",
            "title": "Distribucion de perdidas",
            "stem": "distribucion_perdidas",
            "figure": context.get("fig_dona"),
            "source_hint": "Distribucion relativa de perdidas energeticas.",
        },
        {
            "id": "sectorial_aep",
            "title": "AEP por sector",
            "stem": "aep_sectorial",
            "figure": context.get("fig_sectorial"),
            "source_hint": "Comparacion sectorial de AEP bruta y neta.",
        },
        {
            "id": "sensibilidad_aep",
            "title": "Sensibilidad del AEP neto",
            "stem": "sensibilidad_aep",
            "figure": context.get("fig_sens"),
            "source_hint": "Curva de sensibilidad simple disponible en Fase 5.",
        },
    ])
    probability_export_bundle = build_probability_curve_bundle(
        df_nasa=context["df_nasa"],
        config=config,
        df_curva_raw=context["df_curva_raw"],
        roughness_options=context["roughness_options"],
    )
    phase_annex_bundle = build_indexed_appendix_annex_bundle(
        df_nasa=context["df_nasa"],
        config=config,
        df_curva_raw=context["df_curva_raw"],
        df_layout=context["df_layout"],
        roughness_options=context["roughness_options"],
    )
    site_map_export_bundle = build_site_map_bundle(config=config)

    combined_figure_files = {}
    combined_figure_files.update(figure_export_bundle["files"])
    combined_figure_files.update(probability_export_bundle["files"])
    combined_figure_files.update(phase_annex_bundle["files"])
    combined_figure_files.update(site_map_export_bundle["files"])
    figure_export_artifacts = (
        list(figure_export_bundle["artifacts"])
        + list(probability_export_bundle["artifacts"])
        + list(phase_annex_bundle["artifacts"])
        + list(site_map_export_bundle["artifacts"])
    )

    heavy_table_payloads = dict(basic_bundle["lightweight_table_payloads"])
    for key, df_table, title, columns, max_rows, note in [
        ("probability_intervals", probability_export_bundle.get("tables", {}).get("probability_intervals"), "Probabilidades por intervalos de velocidad", ["Rango", "Probabilidad real (%)", "Probabilidad Weibull (%)", "Probabilidad Rayleigh (%)"], 12, probability_export_bundle.get("summary", {}).get("note", "")),
        ("probability_operation", probability_export_bundle.get("tables", {}).get("probability_operation"), "Probabilidades por zona de operacion", ["Zona de operacion", "Probabilidad real (%)", "Probabilidad Weibull (%)", "Probabilidad Rayleigh (%)"], 10, "Tabla reconstruida desde la configuracion persistida de Fase 3 integrada."),
        ("probability_sector_summary", probability_export_bundle.get("tables", {}).get("probability_sector_summary"), "Resumen sectorial de probabilidad", ["Sector", "Frecuencia (%)", "Velocidad media (m/s)", "k Weibull", "c Weibull (m/s)"], 10, "Resumen compacto de la distribucion sectorial usado por la curva de probabilidad."),
    ]:
        payload = dataframe_to_table_payload(df_table, title=title, columns=columns, max_rows=max_rows, note=note)
        if payload:
            heavy_table_payloads[key] = payload

    for table_key, table_meta in (phase_annex_bundle.get("tables", {}) or {}).items():
        df_table = table_meta.get("df")
        if df_table is None or len(df_table) == 0:
            continue
        payload = dataframe_to_table_payload(
            df_table,
            title=table_meta.get("title", table_key),
            columns=table_meta.get("columns"),
            max_rows=table_meta.get("max_rows", 12),
            note=table_meta.get("note", ""),
        )
        if payload:
            heavy_table_payloads[table_key] = payload

    heavy_report_manifest = get_report_manifest(
        config=config,
        project_name=context["project_name_default"],
        calculation_context=basic_bundle["report_manifest"]["calculation_context"],
        result_summary=basic_bundle["report_manifest"]["result_summary"],
        loss_summary=basic_bundle["report_manifest"]["loss_summary"],
        table_payloads=heavy_table_payloads,
        artifact_context={"exported_figures": figure_export_artifacts},
        export_format="latex",
    )
    heavy_report_payload = build_report_payload(heavy_report_manifest)
    general_appendix_pack = build_latex_appendix_pack(
        report_payload=heavy_report_payload,
        report_manifest=heavy_report_manifest,
        main_latex_text=build_latex_skeleton(heavy_report_payload),
        appendix_files={},
        table_files={},
        export_metadata=basic_bundle["metadata_export"],
        generated_artifacts={
            "excel_bytes": basic_bundle["excel_bytes"],
            "csv_bytes": basic_bundle["csv_bytes"],
            "figure_files": combined_figure_files,
        },
        main_file_name="main.tex",
    )
    general_appendix_pack_files = build_appendix_pack_files(
        report_payload=heavy_report_payload,
        report_manifest=heavy_report_manifest,
        main_latex_text=general_appendix_pack["main_text"],
        appendix_files=general_appendix_pack["appendix_files"],
        table_files=general_appendix_pack["table_files"],
        export_metadata=basic_bundle["metadata_export"],
        generated_artifacts={
            "excel_bytes": basic_bundle["excel_bytes"],
            "csv_bytes": basic_bundle["csv_bytes"],
            "figure_files": combined_figure_files,
        },
        main_file_name=general_appendix_pack["main_file_name"],
    )
    return {
        "combined_figure_files": combined_figure_files,
        "figure_export_artifacts": figure_export_artifacts,
        "site_map_summary": site_map_export_bundle.get("summary", {}),
        "general_appendix_pack": general_appendix_pack,
        "general_appendix_pack_zip": build_appendix_pack_zip_bytes(general_appendix_pack_files),
        "report_manifest": heavy_report_manifest,
        "report_payload": heavy_report_payload,
    }


def generate_informe_tecnico_exports(config, context):
    informe_tecnico_word_model = build_informe_tecnico_word_model(
        config=config,
        project_name=context["project_name_default"],
        df_curva_raw=context["df_curva_raw"],
        df_nasa=context["df_nasa"],
        df_layout=context["df_layout"],
        master_docx_bytes=context.get("master_docx_bytes"),
        master_docx_name=context.get("master_docx_name"),
        phase5_context={
            "method_label": context["metodo_detalle"],
            "summary": {
                "aep_bruta_total": context["res"]["aep_bruta_total"],
                "aep_neta_total": context["res"]["aep_neta_total"],
                "factor_planta_bruto": context["res"]["factor_planta_bruto"],
                "factor_planta_neto": context["res"]["factor_planta_neto"],
                "potencia_nominal_turbina_kw": context["res"]["potencia_nominal_turbina_w"] / 1000.0,
                "n_turbinas": context["n_turbinas"],
                "lcoe_mwh": context.get("lcoe", {}).get("lcoe_mwh"),
                "unidad_monetaria": context.get("lcoe", {}).get("unidad_monetaria"),
            },
            "df_aep_sector": context["df_aep_sector"],
            "tabla_perdidas": context["tabla_perdidas"],
            "fig_loss_distribution": context.get("fig_dona"),
            "fig_sectorial": context.get("fig_sectorial"),
        },
    )
    pdf_result = build_informe_tecnico_pdf(
        report_model=informe_tecnico_word_model,
        file_name=office_safe_file_name("informe_tecnico", "pdf"),
    )
    docx_result = build_informe_tecnico_docx(
        report_model=informe_tecnico_word_model,
        file_name=office_safe_file_name("informe_tecnico", "docx"),
    )
    return {
        "pdf": pdf_result,
        "docx": docx_result,
        "meta": {
            "master_source_used": bool(informe_tecnico_word_model.get("master_source_used")),
            "master_source_name": informe_tecnico_word_model.get("master_source_name", context.get("master_docx_name")),
            "master_requested": bool(context.get("master_docx_bytes")),
            "master_warning": (
                "Se cargó un DOCX maestro, pero no se pudo reutilizar como base; se usó la estructura generada del informe técnico."
                if context.get("master_docx_bytes") and not informe_tecnico_word_model.get("master_source_used")
                else ""
            ),
        },
    }


def rank_export_artifact(item):
    export_format = str(item.get("export_format") or "").lower()
    status = str(item.get("status") or "").lower()
    rank = 0
    if status == "exported":
        rank += 10
    if export_format in ["png", "pdf"]:
        rank += 5
    elif export_format == "svg":
        rank += 4
    elif export_format == "html":
        rank += 2
    if item.get("path"):
        rank += 1
    return rank


def dedupe_figure_export_artifacts(artifacts):
    selected = {}
    ordered_signatures = []
    for idx, item in enumerate(artifacts or []):
        signature = (
            str(item.get("id") or "").strip(),
            str(item.get("file_name") or "").strip(),
            str(item.get("path") or "").replace("\\", "/").strip(),
            str(item.get("title") or "").strip(),
        )
        candidate = dict(item)
        candidate["_original_index"] = idx
        current = selected.get(signature)
        if current is None:
            selected[signature] = candidate
            ordered_signatures.append(signature)
            continue
        if rank_export_artifact(candidate) > rank_export_artifact(current):
            selected[signature] = candidate
    return [selected[signature] for signature in ordered_signatures]


def infer_figure_phase(item):
    export_id = str(item.get("id") or "").lower()
    filename = str(item.get("file_name") or "").lower()
    path = str(item.get("path") or "").lower()
    text = " ".join([export_id, filename, path])
    if "phase35" in text or "fase35" in text or export_id.startswith("probability"):
        return "phase35"
    if "phase4" in text or "fase4" in text or export_id == "layout_wakes":
        return "phase4"
    if "phase3" in text or "fase3" in text or export_id == "wind_rose":
        return "phase3"
    if "phase2" in text or "fase2" in text or export_id == "site_map":
        return "phase2"
    if "phase1" in text or "fase1" in text:
        return "phase1"
    return "phase5"


def build_figure_download_key(item, loop_index):
    phase_hint = infer_figure_phase(item)
    export_id = str(item.get("id") or "figura").strip().lower() or "figura"
    file_name = str(item.get("file_name") or "").strip().lower()
    path = str(item.get("path") or "").replace("\\", "/").strip().lower()
    fingerprint = hashlib.md5(f"{file_name}|{path}".encode()).hexdigest()[:10]
    return f"figure_export_{phase_hint}_{export_id}_{fingerprint}_{loop_index}"
