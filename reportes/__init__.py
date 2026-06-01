"""Superficie pública del paquete `reportes` con carga perezosa (PEP 562).

EAGER (se importa siempre): solo `contexto`, que es liviano y lo usan todas las
páginas en el arranque (`get_project_context`, `get_report_context`, …).

PEREZOSO (se importa al primer uso): todo el stack pesado de reportes
(`docx`, `figuras`, `informe_tecnico`, `latex`, `manifiestos`, `paquete`, `pdf`,
`pdf_tecnico`, `texto`). Antes este `__init__` los importaba TODOS al importar el
paquete, así que abrir la app (Inicio importa `from reportes import …`) arrastraba
docx/pdf/latex/plotly aunque el usuario nunca exportara. Con `__getattr__` a nivel
de módulo, cada símbolo importa su submódulo solo cuando se accede por primera vez.

Compatibilidad: `from reportes import build_informe_tecnico_docx` (y cualquier
otro símbolo del antiguo `__init__`) sigue funcionando idéntico — Python resuelve
el nombre vía `__getattr__`, que importa el submódulo y cachea el símbolo.
"""
import importlib

# EAGER: contexto es liviano y lo necesitan las páginas desde el arranque.
from .contexto import (
    ACADEMIC_REPORT_SECTIONS,
    DEFAULT_REPORT_SECTIONS,
    PROJECT_MODE_FREE,
    PROJECT_PROFILE_OPTIONS,
    get_export_metadata,
    get_project_constraints,
    get_project_context,
    get_project_mode,
    get_project_profile,
    get_project_profile_options,
    get_report_context,
    normalizar_project_mode,
    normalizar_project_profile,
)

# PEREZOSO: símbolo -> submódulo (relativo). Se importa al primer acceso.
_LAZY_EXPORTS = {
    "build_informe_tecnico_docx": ".docx",
    "build_figure_export_bundle": ".figuras",
    "build_indexed_appendix_annex_bundle": ".figuras",
    "build_probability_curve_bundle": ".figuras",
    "build_site_map_bundle": ".figuras",
    "export_plotly_figure_artifact": ".figuras",
    "build_informe_tecnico_model": ".informe_tecnico",
    "build_informe_tecnico_word_model": ".informe_tecnico",
    "build_appendix_snippet_files": ".latex",
    "build_latex_appendix_pack": ".latex",
    "build_latex_skeleton": ".latex",
    "build_table_snippet_files": ".latex",
    "build_report_payload": ".manifiestos",
    "dataframe_to_table_payload": ".manifiestos",
    "get_report_manifest": ".manifiestos",
    "build_appendix_pack_files": ".paquete",
    "build_appendix_pack_zip_bytes": ".paquete",
    "build_direct_pdf_report": ".pdf",
    "compile_latex_to_pdf": ".pdf",
    "get_latex_compiler_info": ".pdf",
    "build_informe_tecnico_pdf": ".pdf_tecnico",
    "normalize_text_deep": ".texto",
    "normalize_visible_text": ".texto",
}

_EAGER_EXPORTS = [
    "ACADEMIC_REPORT_SECTIONS",
    "DEFAULT_REPORT_SECTIONS",
    "PROJECT_MODE_FREE",
    "PROJECT_PROFILE_OPTIONS",
    "get_export_metadata",
    "get_project_constraints",
    "get_project_context",
    "get_project_mode",
    "get_project_profile",
    "get_project_profile_options",
    "get_report_context",
    "normalizar_project_mode",
    "normalizar_project_profile",
]

__all__ = _EAGER_EXPORTS + list(_LAZY_EXPORTS.keys())


def __getattr__(name: str):
    """PEP 562: importa el submódulo pesado solo cuando se accede al símbolo."""
    module_rel = _LAZY_EXPORTS.get(name)
    if module_rel is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_rel, __name__)
    value = getattr(module, name)
    globals()[name] = value  # cachea: accesos posteriores son directos, sin __getattr__
    return value


def __dir__():
    return sorted(__all__)
