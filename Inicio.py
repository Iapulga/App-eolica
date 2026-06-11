import html

import pandas as pd
import streamlit as st

from db import (
    cargar_config,
    cargar_layout_parque,
    cargar_nasa_hourly,
    cargar_proyecto,
    cargar_tabla_curva,
    eliminar_proyecto,
    guardar_config_values,
    importar_proyecto_desde_json_texto,
    init_db,
    listar_proyectos_guardados,
)
from navigation import (
    _icon_svg as nav_icon_svg,
)
from navigation import (
    render_dropdown_visibility_fix,
    render_sidebar_navigation,
)
from perf import timed
from reportes import (
    get_project_context,
    get_project_profile_options,
    get_report_context,
)

st.set_page_config(
    page_title="SMA 2.0 · Wind Project Analyzer",
    layout="wide",
)

# Sidebar custom + CSS global ANTES de cualquier cómputo pesado, para que el
# navegador nunca llegue a pintar con el diseño por defecto de Streamlit.
render_sidebar_navigation("Inicio.py")


@st.cache_resource(show_spinner="Preparando aplicación…")
def precargar_todo() -> bool:
    """Warm-up cache: ejecuta queries DB clave + figura layout una sola vez.

    Usa @st.cache_resource para garantizar ejecución única por proceso.
    Llamadas posteriores son no-op. Los datos quedan en el cache de
    _read_sql_cached (db.py) y disponibles instantáneos para todas las fases.
    """
    with timed("warmup.total"):
        with timed("warmup.init_db"):
            init_db()
        # Calienta los caches de lectura de la BD (config, curva, NASA, layout).
        # Son baratos y los necesita la propia página de Inicio o la primera fase.
        with timed("warmup.cargar_config"):
            cargar_config()
        with timed("warmup.cargar_tabla_curva"):
            cargar_tabla_curva()
        with timed("warmup.cargar_nasa_hourly"):
            cargar_nasa_hourly()
        with timed("warmup.cargar_layout_parque"):
            cargar_layout_parque()
        # Pre-import de módulos pesados para evitar el cold-start de import
        # (sobre todo plotly, que arrastra `calculos`) cuando el usuario navega
        # por primera vez. Esto es lo barato del warmup; las FIGURAS ya NO se
        # precomputan aquí — la página de Inicio no las usa y bloqueaban su
        # primer render. Siguen bajo @st.cache_data, así que se calculan (una
        # sola vez) en la primera visita real a Fase 3/4.
        try:
            with timed("warmup.import_calculos"):
                import calculos  # noqa: F401  (también calienta plotly)
            with timed("warmup.import_calculos_energia"):
                import calculos_energia  # noqa: F401
            with timed("warmup.import_calculos_economicos"):
                import calculos_economicos  # noqa: F401
        except Exception:
            pass
    return True


precargar_todo()

# -----------------------------------------------------------------------------
# Estado de mensajes y confirmaciones
# -----------------------------------------------------------------------------
if "project_message" not in st.session_state:
    st.session_state.project_message = ""

if "project_message_type" not in st.session_state:
    st.session_state.project_message_type = "info"

if "confirm_delete_project" not in st.session_state:
    st.session_state.confirm_delete_project = False

if "project_to_delete" not in st.session_state:
    st.session_state.project_to_delete = ""



# -----------------------------------------------------------------------------
# Helpers visuales locales
# -----------------------------------------------------------------------------
def _escape(value) -> str:
    return html.escape("" if value is None else str(value))


def _format_datetime(value) -> str:
    if value is None or str(value).strip() == "":
        return "N/D"
    try:
        return pd.to_datetime(value).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


def _svg_icon(name: str, size: int = 22, color: str = "#2563eb") -> str:
    stroke = 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    if name == "info":
        body = (
            f'<circle cx="12" cy="12" r="10" {stroke}/>'
            f'<path d="M12 16v-4" {stroke}/>'
            f'<path d="M12 8h.01" {stroke}/>'
        )
    elif name == "database":
        body = (
            f'<ellipse cx="12" cy="5" rx="9" ry="3" {stroke}/>'
            f'<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" {stroke}/>'
            f'<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" {stroke}/>'
        )
    elif name == "folder":
        body = (
            f'<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" {stroke}/>'
        )
    elif name == "trash":
        body = (
            f'<path d="M3 6h18" {stroke}/>'
            f'<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" {stroke}/>'
            f'<line x1="10" y1="11" x2="10" y2="17" {stroke}/>'
            f'<line x1="14" y1="11" x2="14" y2="17" {stroke}/>'
        )
    elif name == "settings":
        body = (
            f'<circle cx="12" cy="12" r="3" {stroke}/>'
            f'<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" {stroke}/>'
        )
    elif name == "upload":
        body = (
            f'<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" {stroke}/>'
            f'<polyline points="17 8 12 3 7 8" {stroke}/>'
            f'<line x1="12" y1="3" x2="12" y2="15" {stroke}/>'
        )
    elif name == "turbine":
        body = (
            f'<circle cx="12" cy="12" r="7.6" {stroke}/>'
            f'<path d="M12 12V4.4" {stroke}/>'
            f'<path d="M12 12 18.6 15.8" {stroke}/>'
            f'<path d="M12 4.4a7.6 7.6 0 0 1 6.6 11.4L12 12Z" fill="{color}" opacity="0.18"/>'
            f'<path d="M12 4.4a7.6 7.6 0 0 1 6.6 11.4" {stroke}/>'
            f'<circle cx="12" cy="12" r="1.15" fill="{color}"/>'
        )
    elif name == "profile":
        body = (
            f'<path d="M5 19h14" {stroke}/>'
            f'<path d="M6 8.1c3.7 0 5.7 1.7 7.9 5.1" {stroke}/>'
            f'<path d="M6 16.4c3.7 0 5.7-1.7 7.9-5.1" {stroke}/>'
            f'<path d="M13.8 12.2c1.7 2.5 3.1 3.9 4.9 4.4" {stroke}/>'
            f'<path d="M13.8 12.2c1.7-2.5 3.1-3.9 4.9-4.4" {stroke}/>'
            f'<circle cx="13.8" cy="12.2" r="1.2" fill="{color}"/>'
        )
    elif name == "waves":
        body = (
            f'<path d="M3.8 13.5c1.8-3.5 3.5-4.8 5.2-4.8 1.5 0 2.4.9 3.2 2 .8 1 1.6 2 2.9 2 1.3 0 2.4-.9 4-3" {stroke}/>'
            f'<path d="M4.2 18c1.2-1.8 2.3-2.6 3.5-2.6 1 0 1.7.6 2.3 1.3.7.7 1.3 1.4 2.4 1.4 1 0 1.8-.6 3-2" {stroke}/>'
            f'<circle cx="18.2" cy="18.1" r="1.35" fill="{color}"/>'
        )
    elif name == "layout":
        body = (
            f'<circle cx="12" cy="12" r="2" fill="{color}"/>'
            f'<path d="M12 4.2v4.9M12 14.9v4.9M4.2 12h4.9M14.9 12h4.9M6.7 6.7l3.1 3.1M14.2 14.2l3.1 3.1M17.3 6.7l-3.1 3.1M9.8 14.2l-3.1 3.1" {stroke}/>'
        )
    elif name == "document":
        body = (
            f'<path d="M7 4h7l4 4v11a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" {stroke}/>'
            f'<path d="M14 4v4h4" {stroke}/>'
            f'<path d="M9 16.5 11.6 12l1.6 2.2h2l-2.4 4.2-1.5-2.2-2.3-.1Z" stroke="{color}" stroke-width="1.7" stroke-linejoin="round" fill="none"/>'
        )
    elif name == "export":
        body = (
            f'<path d="M12 4v9" {stroke}/>'
            f'<path d="m8.6 10.5 3.4 3.5 3.4-3.5" {stroke}/>'
            f'<path d="M5 16.5v1.2A1.3 1.3 0 0 0 6.3 19h11.4a1.3 1.3 0 0 0 1.3-1.3v-1.2" {stroke}/>'
        )
    elif name == "trophy":
        body = (
            f'<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" {stroke}/>'
            f'<path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" {stroke}/>'
            f'<path d="M4 22h16" {stroke}/>'
            f'<path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22" {stroke}/>'
            f'<path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" {stroke}/>'
            f'<path d="M18 2H6v7a6 6 0 0 0 12 0V2z" {stroke}/>'
        )
    else:
        body = f'<circle cx="12" cy="12" r="8" {stroke}/>'
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'style="color:{color};display:block" xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    )


def _show_project_message() -> None:
    if st.session_state.project_message:
        tipo = st.session_state.project_message_type
        mensaje = st.session_state.project_message
        if tipo == "success":
            st.success(mensaje)
        elif tipo == "error":
            st.error(mensaje)
        elif tipo == "warning":
            st.warning(mensaje)
        else:
            st.info(mensaje)
        st.session_state.project_message = ""
        st.session_state.project_message_type = "info"


def _build_projects_display_df(projects_df, active_project=""):
    """Build a display DataFrame for st.dataframe with Estado column."""
    display_rows = []
    for idx, row in projects_df.reset_index(drop=True).iterrows():
        name_raw = str(row.get("name", "Proyecto"))
        updated = _format_datetime(row.get("updated_at", ""))
        is_active = name_raw.strip() == str(active_project).strip()
        estado = "\u25cf Activo" if is_active else "\u25cb Guardado"
        display_rows.append({
            "#": idx + 1,
            "Nombre del proyecto": name_raw,
            "\u00daltima actualizaci\u00f3n": updated,
            "Estado": estado,
        })
    return pd.DataFrame(display_rows)


def _style_projects_df(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Apply visual styling to the projects display DataFrame."""
    col_estado = "\u00daltima actualizaci\u00f3n"  # noqa — only used for subset below
    estado_col = "Estado"

    def _estado_style(col):
        styles = []
        for v in col:
            s = str(v)
            if "\u25cf" in s:          # ● Activo
                styles.append("color: #16a34a; font-weight: 400")
            elif "\u25cb" in s:        # ○ Guardado
                styles.append("color: #000000")
            else:
                styles.append("")
        return styles

    def _stripe(row):
        bg = "#f0f6ff" if row.name % 2 == 1 else "#ffffff"
        return [f"background-color: {bg}" for _ in row]

    styled = (
        df.style
        .set_table_styles([
            {"selector": "thead th", "props": [
                ("background-color", "#0b2a5b"),
                ("color", "#ffffff"),
                ("font-weight", "700"),
                ("font-size", "13px"),
                ("padding", "10px 12px"),
                ("letter-spacing", "0.02em"),
            ]},
            {"selector": "tbody td", "props": [
                ("padding", "10px 12px"),
                ("font-size", "13.5px"),
            ]},
            {"selector": "tbody tr:hover td", "props": [
                ("background-color", "#dbeafe !important"),
            ]},
        ])
        .apply(_stripe, axis=1)
        .apply(_estado_style, subset=[estado_col], axis=0)
    )
    return styled


def _phase_cards_html(fases: list[dict]) -> str:
    cards = []
    icons = ["turbine", "wind", "chart", "settings", "report", "upload"]
    for idx, fase in enumerate(fases):
        tags = "".join([f'<span class="home-chip">{_escape(tag)}</span>' for tag in fase["etiquetas"][:4]])
        entrada = _escape(fase["necesita"][0]) if fase.get("necesita") else "Datos de entrada"
        proceso = _escape(fase["encuentra"][0]) if fase.get("encuentra") else "Proceso técnico"
        salida = _escape(fase["obtiene"][0]) if fase.get("obtiene") else "Resultado"
        cards.append(
            '<div class="home-phase-card">'
            '<div class="home-phase-card-top">'
            f'<div class="home-phase-number">F{idx + 1}</div>'
            f'<div class="home-phase-icon">{_svg_icon(icons[idx], 24)}</div>'
            '</div>'
            f'<h3>{_escape(fase["nombre"])}</h3>'
            f'<p>{_escape(fase["descripcion"])}</p>'
            f'<div class="home-chip-row">{tags}</div>'
            '<div class="home-phase-lines">'
            f'<div><b>Entrada:</b> {entrada}</div>'
            f'<div><b>Proceso:</b> {proceso}</div>'
            f'<div><b>Salida:</b> {salida}</div>'
            '</div>'
            '</div>'
        )
    return f'<div class="home-phase-grid">{"".join(cards)}</div>'


# -----------------------------------------------------------------------------
# CSS local
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
.home-ref-hero{position:relative;display:flex;align-items:center;background:#ffffff;
border:1.4px solid #cbd5e1;border-radius:26px;padding:32px 36px;box-shadow:0 1px 4px rgba(15,23,42,.045);margin-bottom:18px;overflow:hidden;min-height:146px}
.home-ref-hero-text{flex:1;z-index:1}
.home-ref-hero-title{margin:0;font-size:30px;font-weight:900;color:#0b2a5b;letter-spacing:-.03em;line-height:1.1}
.home-ref-hero-sub{margin-top:8px;color:#000000;font-size:14.5px;font-weight:400;line-height:1.55}
.home-ref-hero-illust{position:absolute;right:0;top:0;bottom:0;width:390px;pointer-events:none;opacity:.62}
.home-ref-card{background:#ffffff;border:1.4px solid #cbd5e1;border-radius:24px;padding:22px 24px;box-shadow:0 1px 4px rgba(15,23,42,.045);margin-bottom:16px}
.home-ref-section-title{display:flex;align-items:center;gap:11px;color:#0b2a5b;font-size:22px;font-weight:900;margin:16px 0 12px;letter-spacing:-.02em}
.home-ref-card-title{display:flex;align-items:center;gap:13px;color:#0b2a5b;font-size:17px;font-weight:900;margin-bottom:14px}
.home-ref-icon-soft{width:42px;height:42px;border-radius:999px;background:#eff6ff;border:1px solid #bfdbfe;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 8px 18px rgba(37,99,235,.08)}
.home-ref-desc{color:#000000;font-size:14.5px;line-height:1.65;margin:0}
.home-table-wrap{border:1px solid #cbd5e1;border-radius:16px;overflow:hidden;background:#fff;box-shadow:0 1px 4px rgba(15,23,42,.045)}
.home-table{width:100%;border-collapse:collapse;color:#0b2a5b;font-size:13.5px}
.home-table th{text-align:left;background:#f4f8ff;color:#000000;font-weight:850;padding:11px 14px;border-bottom:1px solid #cbd5e1}
.home-table td{padding:12px 14px;border-bottom:1px solid #eaf1f9}
.home-status-badge{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.home-status-active{background:#dcfce7;color:#16a34a;border:1px solid #86efac}
.home-status-saved{background:#f1f5f9;color:#000000;border:1px solid #cbd5e1}
.home-status-dot{width:7px;height:7px;border-radius:999px;display:inline-block;flex-shrink:0}
.home-status-dot-active{background:#22c55e}
.home-status-dot-saved{background:#94a3b8}

.home-empty-state{display:flex;gap:12px;align-items:center;background:#f8fbff;border:1px dashed #bfdbfe;border-radius:14px;padding:16px;color:#0b2a5b}
.home-empty-icon{width:42px;height:42px;border-radius:999px;background:#eff6ff;border:1px solid #bfdbfe;display:flex;align-items:center;justify-content:center}
.home-confirm-box{background:#fff7f7;border:1px solid #fecaca;border-radius:16px;padding:16px 18px;color:#7f1d1d;margin:12px 0}
.home-upload-detected{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:16px;padding:16px 18px;color:#14532d;margin:12px 0}
/* Action buttons: Cargar = filled blue, Eliminar = ghost */
.st-key-btn_cargar_proyecto > button {
    background-color: #2563eb !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    transition: background-color .15s;
}
.st-key-btn_cargar_proyecto > button:hover {
    background-color: #1d4ed8 !important;
}
.st-key-btn_eliminar_proyecto > button {
    background-color: #ffffff !important;
    color: #000000 !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: border-color .15s, color .15s;
}
.st-key-btn_eliminar_proyecto > button:hover {
    border-color: #fca5a5 !important;
    color: #dc2626 !important;
}
.home-ref-phases-container{background:#ffffff;border:1.4px solid #cbd5e1;border-radius:24px;padding:20px 22px;box-shadow:0 1px 4px rgba(15,23,42,.045);margin-bottom:16px}
.home-ref-phases-row{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:10px}
.home-ref-phase-mini{display:flex;align-items:center;gap:16px;background:#f8fbff;border:1px solid #cbd5e1;border-radius:18px;padding:18px 20px;transition:box-shadow .18s;min-height:92px}
.home-ref-phase-mini:hover{box-shadow:0 6px 16px rgba(15,45,90,.09)}
.home-ref-phase-mini-icon{width:74px;height:74px;border-radius:999px;background:#eff6ff;border:1px solid #bfdbfe;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 8px 18px rgba(37,99,235,.08)}
.home-ref-phase-mini-text{flex:1;min-width:0}
.home-ref-phase-mini-num{font-size:14.5px;font-weight:900;color:#2563eb;margin-bottom:3px}
.home-ref-phase-mini-name{font-size:15.5px;font-weight:800;color:#0b2a5b;line-height:1.25}
.home-ref-phase-mini-chevron{color:#93b4e0;font-size:22px;flex-shrink:0}
.home-ref-final-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
.home-ref-final-card{background:#ffffff;border:1.4px solid #cbd5e1;border-radius:22px;padding:22px 24px;display:flex;align-items:center;gap:18px;color:#0b2a5b;box-shadow:0 1px 4px rgba(15,23,42,.045);min-height:106px}
.home-ref-final-card b{font-weight:900;font-size:17.5px}
.home-ref-final-icon{width:60px;height:60px;border-radius:999px;background:#eff6ff;border:1px solid #bfdbfe;display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 8px 18px rgba(37,99,235,.08)}
.st-key-home_card_projects,
.st-key-home_card_projects > div,
.st-key-home_card_projects [data-testid="stVerticalBlock"],
.st-key-home_card_config,
.st-key-home_card_config > div,
.st-key-home_card_config [data-testid="stVerticalBlock"],
.st-key-home_card_import,
.st-key-home_card_import > div,
.st-key-home_card_import [data-testid="stVerticalBlock"] {
    background-color: #ffffff !important;
    border-radius: 22px !important;
}
.st-key-home_card_config [data-testid="stVerticalBlockBorderWrapper"],
.st-key-home_card_import [data-testid="stVerticalBlockBorderWrapper"] {
    padding-bottom: 45px !important;
    min-height: 240px !important;
}
/* Make right column cards fill equal height as left column */
div[data-testid="stHorizontalBlock"] {
    align-items: stretch !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    display: flex !important;
    flex-direction: column !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {
    display: flex !important;
    flex-direction: column !important;
    flex: 1 !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:nth-child(2) > div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] > div {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] {
    display: none !important;
}
[data-testid="stFileUploader"] small {
    display: none !important;
}
@media(max-width:1100px){.home-ref-phases-row{grid-template-columns:repeat(3,1fr)}.home-ref-final-row{grid-template-columns:1fr}}
@media(max-width:700px){.home-ref-phases-row{grid-template-columns:repeat(2,1fr)}}

/* --- FORZADO: Sombra con volumen estilo Fase 3 --- */
.home-ref-hero,
.home-ref-card,
.home-ref-phases-container,
.home-ref-final-card,
.st-key-home_card_projects,
.st-key-home_card_config,
.st-key-home_card_import {
    border: 1px solid #cbd5e1 !important;
    border-radius: 20px !important;
    background-color: #ffffff !important;
    box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.15), 0 6px 14px rgba(15, 23, 42, 0.08), 0 2px 6px rgba(37, 99, 235, 0.06) !important;
}
</style>
""",
    unsafe_allow_html=True,
)

render_dropdown_visibility_fix()

_show_project_message()

# -----------------------------------------------------------------------------
# SVG de ilustración eólica reutilizable
# -----------------------------------------------------------------------------
_WIND_ILLUST_SVG = '''<svg viewBox="0 0 320 140" width="320" height="140" xmlns="http://www.w3.org/2000/svg" style="display:block">
<defs><linearGradient id="hg1" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#dbeafe" stop-opacity=".35"/><stop offset="100%" stop-color="#eff6ff" stop-opacity=".18"/></linearGradient></defs>
<path d="M0 110 Q80 85 160 95 T320 80 V140 H0Z" fill="url(#hg1)"/>
<g stroke="#93c5fd" stroke-width="1.2" fill="none" opacity=".7"><line x1="180" y1="95" x2="180" y2="42"/><circle cx="180" cy="40" r="3" fill="#93c5fd"/><line x1="180" y1="40" x2="170" y2="22"/><line x1="180" y1="40" x2="195" y2="25"/><line x1="180" y1="40" x2="175" y2="56"/></g>
<g stroke="#93c5fd" stroke-width="1.2" fill="none" opacity=".55"><line x1="240" y1="88" x2="240" y2="50"/><circle cx="240" cy="48" r="2.5" fill="#93c5fd"/><line x1="240" y1="48" x2="232" y2="34"/><line x1="240" y1="48" x2="252" y2="36"/><line x1="240" y1="48" x2="237" y2="62"/></g>
<g stroke="#93c5fd" stroke-width="1" fill="none" opacity=".4"><line x1="290" y1="82" x2="290" y2="55"/><circle cx="290" cy="53" r="2" fill="#93c5fd"/><line x1="290" y1="53" x2="284" y2="42"/><line x1="290" y1="53" x2="298" y2="44"/><line x1="290" y1="53" x2="288" y2="64"/></g>
<g stroke="#bfdbfe" stroke-width=".8" opacity=".5"><path d="M140 50 Q170 46 200 50" fill="none"/><path d="M160 38 Q195 33 230 38" fill="none"/><path d="M200 28 Q230 24 260 28" fill="none"/></g>
<g fill="#bfdbfe" opacity=".3"><circle cx="270" cy="30" r="1.5"/><circle cx="280" cy="22" r="1.2"/><circle cx="290" cy="32" r="1"/><circle cx="300" cy="18" r="1.3"/><circle cx="260" cy="20" r="1"/><circle cx="305" cy="28" r=".9"/></g>
</svg>'''

# -----------------------------------------------------------------------------
# Hero y descripción
# -----------------------------------------------------------------------------
st.markdown(
    f"""
<div class="home-ref-hero">
    <div class="home-ref-hero-text">
        <h1 class="home-ref-hero-title">Aplicación para cálculos de parques eólicos</h1>
        <div class="home-ref-hero-sub">
            Plataforma integrada para el análisis de recursos eólicos y la estimación del AEP, pérdidas, estelas y AEP bruto y neto.<br>
            Trabaje por fases para obtener resultados precisos y confiables para su proyecto.
        </div>
    </div>
    <div class="home-ref-hero-illust">{_WIND_ILLUST_SVG}</div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
<div class="home-ref-card">
    <div class="home-ref-card-title"><span class="home-ref-icon-soft">{_svg_icon("info", 20)}</span>Descripción general</div>
    <p class="home-ref-desc">
        Esta aplicación está organizada por fases para desarrollar el análisis de un parque eólico de manera ordenada, desde la selección del aerogenerador y el procesamiento del recurso viento, hasta el cálculo de pérdidas, estelas y AEP bruto y neto.<br>
        Los datos guardados en cada fase quedan enlazados con las siguientes fases del proyecto.
    </p>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Gestión de proyectos + Configuración (2 columnas como referencia)
# -----------------------------------------------------------------------------
config = cargar_config()
project_context = get_project_context(config)
report_context = get_report_context(config)
profile_options = get_project_profile_options()
profile_values = [option["value"] for option in profile_options]
profile_index = profile_values.index(project_context["profile"])

proyectos_df = listar_proyectos_guardados()
proyecto_sel = None

col_left, col_right = st.columns([1.15, 1], gap="large")

# --- IZQUIERDA: Gestión de proyectos ---
with col_left:
    with st.container(border=True, key="home_card_projects"):
        st.markdown(
            f'<div class="home-ref-card-title"><span class="home-ref-icon-soft">{_svg_icon("database", 20)}</span>Gestión de proyectos</div>',
            unsafe_allow_html=True,
        )
        if len(proyectos_df) > 0:
            nombres_proyectos = proyectos_df["name"].tolist()
            nombre_activo = config.get("project_name", "").strip()

            # Seed the selectbox widget value on first load
            if "home_project_selectbox" not in st.session_state:
                st.session_state.home_project_selectbox = (
                    nombre_activo if nombre_activo in nombres_proyectos else nombres_proyectos[0]
                )

            # ── Read PREVIOUS table selection (from last rerun) and sync
            #    to selectbox BEFORE the selectbox widget is instantiated ──
            if "projects_table" in st.session_state:
                prev_sel = st.session_state.projects_table.get("selection", {}).get("rows", [])
                if prev_sel:
                    clicked_name = nombres_proyectos[prev_sel[0]]
                    if clicked_name != st.session_state.home_project_selectbox:
                        st.session_state.home_project_selectbox = clicked_name

            project_select_col, btn_c1, btn_c2 = st.columns([1.45, 1.15, 1.15], gap="medium")
            with project_select_col:
                proyecto_sel = st.selectbox(
                    "Seleccione un proyecto guardado",
                    nombres_proyectos,
                    key="home_project_selectbox",
                )
            with btn_c1:
                st.markdown("<div style='height:1.65rem'></div>", unsafe_allow_html=True)
                if st.button("Cargar proyecto seleccionado", key="btn_cargar_proyecto", use_container_width=True, icon=":material/folder_open:"):
                    try:
                        cargar_proyecto(proyecto_sel)
                        st.session_state.project_message = f"Proyecto '{proyecto_sel}' cargado correctamente."
                        st.session_state.project_message_type = "success"
                        st.rerun()
                    except Exception as e:
                        st.session_state.project_message = f"No pude cargar el proyecto: {e}"
                        st.session_state.project_message_type = "error"
                        st.rerun()
            with btn_c2:
                st.markdown("<div style='height:1.65rem'></div>", unsafe_allow_html=True)
                if st.button("Eliminar proyecto seleccionado", key="btn_eliminar_proyecto", use_container_width=True, icon=":material/delete:"):
                    st.session_state.confirm_delete_project = True
                    st.session_state.project_to_delete = proyecto_sel or nombres_proyectos[0]

            # ── Interactive project table with native row selection + Styler ──
            display_df = _build_projects_display_df(proyectos_df, active_project=nombre_activo)
            styled_df = _style_projects_df(display_df)
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="projects_table",
                column_config={
                    "#": st.column_config.NumberColumn("#", width="small"),
                    "Nombre del proyecto": st.column_config.TextColumn(
                        "Nombre del proyecto", width="large"
                    ),
                    "\u00daltima actualizaci\u00f3n": st.column_config.TextColumn(
                        "\u00daltima actualizaci\u00f3n", width="medium"
                    ),
                    "Estado": st.column_config.TextColumn("Estado", width="small"),
                },
            )
        else:
            st.info("Todavía no hay proyectos guardados.")

# --- DERECHA: Configuración + Importar ---
with col_right:
    with st.container(border=True, key="home_card_config"):
        st.markdown(
            f'<div class="home-ref-card-title"><span class="home-ref-icon-soft">{_svg_icon("settings", 20)}</span>Configuración general del proyecto</div>',
            unsafe_allow_html=True,
        )
        with st.expander("Modo y perfil del proyecto"):
            perfil_seleccionado = st.selectbox(
                "Perfil opcional del proyecto",
                options=profile_values,
                index=profile_index,
                format_func=lambda value: next(
                    option["label"] for option in profile_options if option["value"] == value
                ),
            )
            perfil_descripcion = next(
                option["description"]
                for option in profile_options
                if option["value"] == perfil_seleccionado
            )
            st.caption(perfil_descripcion)
            if st.button("Guardar configuración del proyecto", use_container_width=True):
                try:
                    guardar_config_values({
                        "project_mode": "free",
                        "project_profile": perfil_seleccionado or "",
                    })
                    st.session_state.project_message = "Configuración del proyecto guardada correctamente."
                    st.session_state.project_message_type = "success"
                    st.rerun()
                except Exception as e:
                    st.session_state.project_message = f"No pude guardar la configuración del proyecto: {e}"
                    st.session_state.project_message_type = "error"
                    st.rerun()
        with st.expander("Vista previa de reporte y exportación"):
            st.caption(f"Estilo: {report_context['report_style_label']} · Citas: {report_context['citation_style']}")
            for section in report_context["report_sections"][:4]:
                st.markdown(f"- {section}")
            st.caption(report_context["template_hint"])

    with st.container(border=True, key="home_card_import"):
        st.markdown(
            f'<div class="home-ref-card-title"><span class="home-ref-icon-soft">{_svg_icon("upload", 20)}</span>Importar proyecto desde archivo</div>',
            unsafe_allow_html=True,
        )
        archivo_proyecto = st.file_uploader("Suba un archivo .json de proyecto", type=["json"])
        if archivo_proyecto is not None:
            tamanio_kb = archivo_proyecto.size / 1024
            st.markdown(
                f'<div class="home-upload-detected"><strong>Archivo detectado</strong><br>Nombre: <strong>{_escape(archivo_proyecto.name)}</strong> · Tamaño: <strong>{tamanio_kb:.1f} KB</strong></div>',
                unsafe_allow_html=True,
            )
            if st.button("Importar y cargar proyecto", use_container_width=True):
                try:
                    texto_json = archivo_proyecto.read().decode("utf-8")
                    importar_proyecto_desde_json_texto(texto_json)
                    st.session_state.project_message = f"Proyecto importado correctamente desde '{archivo_proyecto.name}'."
                    st.session_state.project_message_type = "success"
                    st.rerun()
                except Exception as e:
                    st.session_state.project_message = f"No pude importar el proyecto: {e}"
                    st.session_state.project_message_type = "error"
                    st.rerun()
        else:
            pass

# --- Confirmación de eliminación (fuera de columnas) ---
if st.session_state.confirm_delete_project and st.session_state.project_to_delete:
    st.markdown(
        f'<div class="home-confirm-box"><strong>Confirmación de eliminación</strong><br>Está a punto de eliminar el proyecto: <strong>{_escape(st.session_state.project_to_delete)}</strong><br>Esta acción no se puede deshacer.</div>',
        unsafe_allow_html=True,
    )
    d1, d2 = st.columns(2)
    with d1:
        if st.button("Sí, eliminar definitivamente", use_container_width=True):
            try:
                eliminar_proyecto(st.session_state.project_to_delete)
                nombre_borrado = st.session_state.project_to_delete
                st.session_state.confirm_delete_project = False
                st.session_state.project_to_delete = ""
                st.session_state.project_message = f"Proyecto '{nombre_borrado}' eliminado correctamente."
                st.session_state.project_message_type = "success"
                st.rerun()
            except Exception as e:
                st.session_state.project_message = f"No pude eliminar el proyecto: {e}"
                st.session_state.project_message_type = "error"
                st.rerun()
    with d2:
        if st.button("Cancelar eliminación", use_container_width=True):
            st.session_state.confirm_delete_project = False
            st.session_state.project_to_delete = ""
            st.session_state.project_message = "Eliminación cancelada."
            st.session_state.project_message_type = "info"
            st.rerun()

# -----------------------------------------------------------------------------
# Fases de la aplicación
# -----------------------------------------------------------------------------
_phase_mini = [
    ("Fase 1", "Elección del aerogenerador", "turbine"),
    ("Fase 2", "Perfiles de viento", "profile"),
    ("Fase 3", "Rosa de vientos y probabilidad de ocurrencia", "waves"),
    ("Fase 4", "Estelas y arreglo", "layout"),
    ("Fase 5", "AEP bruta y neta", "document"),
    ("Fase 6", "Estudios avanzados", "activity"),
    ("Fase 7", "Exportar y guardar", "export"),
]

_mini_cards_html = ""
for num, nombre, icono in _phase_mini:
    _mini_cards_html += (
        f'<div class="home-ref-phase-mini">'
        f'<div class="home-ref-phase-mini-icon">{nav_icon_svg(icono, 40, "#2563eb")}</div>'
        f'<div class="home-ref-phase-mini-text">'
        f'<div class="home-ref-phase-mini-num">{_escape(num)}</div>'
        f'<div class="home-ref-phase-mini-name">{_escape(nombre)}</div>'
        f'</div>'
        f'<span class="home-ref-phase-mini-chevron">›</span>'
        f'</div>'
    )

st.markdown(
    f"""
<div class="home-ref-phases-container">
    <div class="home-ref-card-title"><span class="home-ref-icon-soft">{nav_icon_svg("layout", 20, "#2563eb")}</span>Fases de la aplicación</div>
    <div class="home-ref-phases-row">{_mini_cards_html}</div>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Cards finales
# -----------------------------------------------------------------------------
st.markdown(
    f"""
<div class="home-ref-final-row">
    <div class="home-ref-final-card">
        <div class="home-ref-final-icon">{_svg_icon("trophy", 32)}</div>
        <div>
            <b>Resultado final esperado</b><br>
            <div style="font-size:15.5px;color:#000000;margin-top:4px">Al completar las siete fases obtendrá el AEP bruto y neto estimado del parque eólico, incluyendo las pérdidas por estelas, disponibilidad y otros factores, junto con estudios avanzados de sitio y la capacidad de exportar reportes y datos para documentación del proyecto.</div>
        </div>
    </div>
    <div class="home-ref-final-card">
        <div class="home-ref-final-icon">{_svg_icon("info", 32)}</div>
        <div>
            <b style="font-size:19px">Flujo recomendado de trabajo:</b>
            <span style="font-size:18px;color:#2563eb;font-weight:700"> Fase 1 → Fase 2 → Fase 3 → Fase 4 → Fase 5 → Fase 6 → Fase 7</span>
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

