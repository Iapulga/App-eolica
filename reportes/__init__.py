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
from .docx import build_informe_tecnico_docx
from .figuras import (
    build_figure_export_bundle,
    build_indexed_appendix_annex_bundle,
    build_probability_curve_bundle,
    build_site_map_bundle,
    export_plotly_figure_artifact,
)
from .informe_tecnico import build_informe_tecnico_model, build_informe_tecnico_word_model
from .latex import (
    build_appendix_snippet_files,
    build_latex_appendix_pack,
    build_latex_skeleton,
    build_table_snippet_files,
)
from .manifiestos import build_report_payload, dataframe_to_table_payload, get_report_manifest
from .paquete import (
    build_appendix_pack_files,
    build_appendix_pack_zip_bytes,
)
from .pdf import build_direct_pdf_report, compile_latex_to_pdf, get_latex_compiler_info
from .pdf_tecnico import build_informe_tecnico_pdf
from .texto import normalize_text_deep, normalize_visible_text
