import pandas as pd

PROJECT_MODE_FREE = "free"

PROJECT_PROFILE_OPTIONS = [
    {
        "value": None,
        "label": "Sin perfil",
        "description": "Configuracion general y abierta, sin plantilla especifica.",
    },
    {
        "value": "academic",
        "label": "Academico",
        "description": "Perfil opcional para futuras plantillas academicas, sin restricciones automaticas por ahora.",
    },
]

DEFAULT_REPORT_SECTIONS = [
    "Resumen ejecutivo",
    "Configuracion del proyecto",
    "Aerogenerador",
    "Recurso eolico",
    "Distribucion direccional",
    "Estelas y perdidas",
    "AEP y resultados",
]

ACADEMIC_REPORT_SECTIONS = [
    "Portada",
    "Resumen",
    "Objetivos y alcance",
    "Metodologia",
    "Datos de entrada",
    "Resultados",
    "Discusion",
    "Conclusiones",
    "Referencias",
    "Anexos",
]


def normalizar_project_mode(project_mode):
    mode = str(project_mode or "").strip().lower()
    if mode == "":
        return PROJECT_MODE_FREE
    if mode != PROJECT_MODE_FREE:
        return PROJECT_MODE_FREE
    return mode


def normalizar_project_profile(project_profile):
    profile = str(project_profile or "").strip().lower()
    if profile == "":
        return None

    profile_values = {
        option["value"]
        for option in PROJECT_PROFILE_OPTIONS
        if option["value"] is not None
    }
    if profile not in profile_values:
        return None
    return profile


def get_project_mode(config=None):
    if isinstance(config, dict):
        return normalizar_project_mode(config.get("project_mode"))
    return PROJECT_MODE_FREE


def get_project_profile(config=None):
    if isinstance(config, dict):
        return normalizar_project_profile(config.get("project_profile"))
    return None


def get_project_profile_options():
    return [option.copy() for option in PROJECT_PROFILE_OPTIONS]


def get_project_constraints(config=None):
    profile = get_project_profile(config)

    return {
        "mode": get_project_mode(config),
        "profile": profile,
        "warnings": [],
        "hard_limits": {},
        "report_presets": [profile] if profile else [],
    }


def get_project_context(config=None):
    mode = get_project_mode(config)
    profile = get_project_profile(config)
    constraints = get_project_constraints(config)

    profile_meta = next(
        (option for option in PROJECT_PROFILE_OPTIONS if option["value"] == profile),
        PROJECT_PROFILE_OPTIONS[0],
    )

    return {
        "mode": mode,
        "mode_label": "Modo libre",
        "profile": profile,
        "profile_label": profile_meta["label"],
        "profile_description": profile_meta["description"],
        "constraints": constraints,
        "is_free_mode": mode == PROJECT_MODE_FREE,
    }


def get_report_context(config=None):
    project_context = get_project_context(config)
    profile = project_context["profile"]

    report_context = {
        "mode": project_context["mode"],
        "profile": profile,
        "report_style": "general",
        "report_style_label": "Informe general flexible",
        "report_sections": list(DEFAULT_REPORT_SECTIONS),
        "citation_style": "Opcional",
        "include_ai_declaration": False,
        "export_targets": ["CSV", "Excel", "JSON"],
        "template_hint": "Plantilla libre",
        "notes": [
            "La exportacion permanece abierta y configurable.",
            "No se aplican secciones obligatorias ni formatos rigidos por defecto.",
        ],
    }

    if profile == "academic":
        report_context.update({
            "report_style": "academic_outline",
            "report_style_label": "Plantilla academica opcional",
            "report_sections": list(ACADEMIC_REPORT_SECTIONS),
            "citation_style": "APA (sugerido)",
            "include_ai_declaration": True,
            "export_targets": ["CSV", "Excel", "JSON", "DOCX/LaTeX (futuro)"],
            "template_hint": "Borrador para informe academico",
            "notes": [
                "El perfil academico solo ajusta metadatos de reporte y exportacion.",
                "Todavia no activa restricciones globales ni bloquea el flujo libre.",
            ],
        })

    return report_context


def get_export_metadata(config=None, export_format="excel"):
    project_context = get_project_context(config)
    report_context = get_report_context(config)

    return {
        "project_mode": project_context["mode"],
        "project_profile": project_context["profile"] or "",
        "report_style": report_context["report_style"],
        "report_style_label": report_context["report_style_label"],
        "citation_style": report_context["citation_style"],
        "include_ai_declaration": report_context["include_ai_declaration"],
        "suggested_sections": " | ".join(report_context["report_sections"]),
        "export_targets": " | ".join(report_context["export_targets"]),
        "export_format": str(export_format).strip().lower(),
        "template_hint": report_context["template_hint"],
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
    }
