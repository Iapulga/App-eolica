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
    render_dropdown_visibility_fix,
    render_sidebar_navigation,
    render_stepper,
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
# El stepper se pinta aparte DEBAJO del hero (orden del mockup Aurora).
render_sidebar_navigation("Inicio.py", stepper=False)


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


# -----------------------------------------------------------------------------
# CSS local
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
/* ═══════ Paridad 1:1 con el mockup 00_inicio (Aurora) ═══════ */

/* Hero */
.home-ref-hero{position:relative;display:flex;align-items:center;gap:18px;
background:linear-gradient(118deg,var(--ac,#2563eb) 0%, var(--ac2,#1e40af) 80%);
border:none;border-radius:26px;padding:22px 28px;margin-bottom:14px;overflow:hidden;
box-shadow:0 22px 44px color-mix(in srgb, var(--ac,#2563eb) 32%, transparent), inset 0 1px 0 rgba(255,255,255,.25)}
.home-ref-hero::after{content:"";position:absolute;inset:0;pointer-events:none;background:
radial-gradient(circle at 86% 12%, rgba(255,255,255,.20) 0 54px, transparent 55px),
radial-gradient(circle at 95% 70%, rgba(255,255,255,.12) 0 86px, transparent 87px),
linear-gradient(180deg, rgba(255,255,255,.08), transparent 40%)}
.home-wind{position:absolute;left:-30px;top:0;bottom:0;width:58%;opacity:.32;pointer-events:none;z-index:1}
.home-wind path{stroke:rgba(255,255,255,.5);stroke-width:1.6;fill:none;stroke-dasharray:16 11;animation:homewindmove 2.6s linear infinite}
.home-wind path:nth-child(2){animation-duration:3.4s;opacity:.7}
.home-wind path:nth-child(3){animation-duration:4.2s;opacity:.5}
@keyframes homewindmove{to{stroke-dashoffset:-54}}
.home-ref-hero-badge{width:62px;height:62px;border-radius:19px;background:rgba(255,255,255,.17);
border:1.5px solid rgba(255,255,255,.4);display:flex;align-items:center;justify-content:center;font-size:31px;
flex-shrink:0;z-index:2;box-shadow:inset 0 1px 0 rgba(255,255,255,.35), 0 8px 18px rgba(0,0,0,.12)}
.home-ref-hero-text{flex:1;z-index:2}
.home-ref-hero h1.home-ref-hero-title{margin:0 !important;padding:0 !important;font-size:25px !important;
font-weight:900 !important;color:#fff !important;letter-spacing:-.025em !important;line-height:1.15 !important}
.home-ref-hero-sub{margin-top:4px;font-size:12.5px;font-weight:500;line-height:1.45;max-width:840px}
.home-ref-hero-pills{display:flex;gap:9px;z-index:2;flex-shrink:0;margin-left:auto}
.home-ref-hpill{background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.4);border-radius:15px;
padding:8px 15px;text-align:center;box-shadow:inset 0 1px 0 rgba(255,255,255,.25);color:#fff}
.home-ref-hpill b{display:block;font-size:16.5px;letter-spacing:-.01em}
.home-ref-hpill span{font-size:9px;opacity:.92;text-transform:uppercase;letter-spacing:.07em;font-weight:700}

/* Card HTML genérica (idéntica a .card del mockup) */
.home-card{position:relative;background:linear-gradient(180deg,#fff,#fcfdff);border:1.5px solid #c7d8ee;
border-radius:26px;padding:20px 22px 18px;margin-bottom:16px;overflow:hidden;
box-shadow:0 1px 2px rgba(11,36,71,.05), 0 12px 30px rgba(11,36,71,.10)}
.home-card::before{content:"";position:absolute;left:0;right:0;top:0;height:4px;
background:linear-gradient(90deg, var(--acl,var(--ac,#2563eb)), color-mix(in srgb, var(--acl,var(--ac,#2563eb)) 25%, #fff) 70%, transparent)}
.home-card-head{display:flex;align-items:center;gap:13px;margin-bottom:14px}
.home-cicon{width:46px;height:46px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;
background:linear-gradient(135deg, color-mix(in srgb, var(--acl,var(--ac,#2563eb)) 16%, #fff), color-mix(in srgb, var(--acl,var(--ac,#2563eb)) 7%, #fff));
border:1.5px solid color-mix(in srgb, var(--acl,var(--ac,#2563eb)) 35%, #fff);
box-shadow:0 5px 12px color-mix(in srgb, var(--acl,var(--ac,#2563eb)) 16%, transparent)}
.home-card-head h2{margin:0;font-size:16.5px;font-weight:900;color:#0b2447;letter-spacing:-.02em}
.home-card-head p{margin:2px 0 0;font-size:11px;color:#5a6b85;font-weight:600}
.home-muted, .stMarkdown p.home-muted{color:#5a6b85 !important;font-size:11px !important;font-weight:600 !important;line-height:1.55 !important;margin:0 !important}

/* Cards reales (st.container con key): en esta versión de Streamlit la clase
   st-key-* cae en el propio stVerticalBlock (no hay BorderWrapper). El look del
   card (#d3e0f0 r26, degradado, sombra) se aplica DIRECTO a ese elemento. */
.st-key-home_card_projects,
.st-key-home_card_config,
.st-key-home_card_import{
position:relative !important;overflow:hidden !important;
background:linear-gradient(180deg,#fff,#fcfdff) !important;
border:1.5px solid #c7d8ee !important;border-radius:26px !important;
padding:20px 22px 18px !important;gap:.55rem !important;
box-shadow:0 1px 2px rgba(11,36,71,.05), 0 12px 30px rgba(11,36,71,.10) !important}

/* Columnas c21 del mockup (gap 14px), ambas columnas estiradas a la misma altura */
div[data-testid="stHorizontalBlock"]{gap:14px !important;align-items:stretch !important}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]{display:flex !important;flex-direction:column !important;min-width:0}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"]{display:flex !important;flex-direction:column !important;flex:1 !important}

/* Card Gestión: estira a la altura de la fila (la fija la columna derecha
   Config+Importar) y deja que la TABLA (último elemento) absorba el espacio
   sobrante → alto INDEPENDIENTE del nº de proyectos; escala con zoom.
   Cadena real: stColumn(497) → stVerticalBlock(497,flex:1) → stLayoutWrapper
   (eslabón roto: flex:0 1 auto) → stVerticalBlock.st-key(card). Se fuerza el
   stLayoutWrapper a flex:1 1 auto para que el card herede la altura completa. */
div[data-testid="stLayoutWrapper"]:has(> .st-key-home_card_projects){
flex:1 1 auto !important;display:flex !important;flex-direction:column !important;min-height:0 !important}
.st-key-home_card_projects{flex:1 1 auto !important;min-height:0 !important}
/* El element-container de la tabla NO se comprime: altura natural, sin scroll
   propio (overflow visible). Con pocos proyectos queda arriba y el aire del card
   estirado va debajo; con muchos, el wrapper interno limita y scrollea. */
.st-key-home_card_projects > [data-testid="stElementContainer"]:last-child{
flex:0 0 auto !important;overflow:visible !important;max-height:none !important}
/* El SCROLL vive en el wrapper con tope fijo (en px → escala con zoom). Con
   pocas filas la tabla cabe sin barra; con muchas, scrollea por dentro y el
   card NO crece (≈ altura de la columna derecha). 255 ≈ alto der − controles. */
.home-tbl-wrap{max-height:255px;overflow-y:auto;border-radius:14px}
.home-tbl-wrap::-webkit-scrollbar{width:8px}
.home-tbl-wrap::-webkit-scrollbar-thumb{background:#cfe0f5;border-radius:8px}
.home-tbl-wrap::-webkit-scrollbar-track{background:transparent}
/* Label "PROYECTO GUARDADO": su element-container colapsa a h=0 → reservar alto */
.st-key-home_card_projects [data-testid="stElementContainer"]:has(.home-flabel){min-height:16px !important;margin-bottom:3px !important}

/* Label de campo en mayúsculas (PROYECTO GUARDADO) */
.home-flabel{font-size:9.5px;font-weight:900;color:#64748b;margin:0;line-height:1.5;text-transform:uppercase;letter-spacing:.06em}

/* Selectbox como .input del mockup, con conteo dentro a la derecha */
.st-key-home_project_selectbox{position:relative}
.st-key-home_project_selectbox [data-baseweb="select"] > div:first-child{
background:#fff !important;border:1.5px solid #cfe0f5 !important;border-radius:12px !important;
box-shadow:inset 0 1px 3px rgba(11,36,71,.04) !important;min-height:42px !important}
.st-key-home_project_selectbox [data-baseweb="select"] [data-baseweb="single-value"],
.st-key-home_project_selectbox [data-baseweb="select"] [data-baseweb="single-value"] div{
font-size:13.5px !important;font-weight:800 !important;color:#0b2447 !important}
.st-key-home_project_selectbox::after{content:var(--home-nproj,"");position:absolute;right:46px;top:50%;transform:translateY(-50%);
font-size:10.5px;font-weight:700;color:#94a3b8;pointer-events:none;z-index:3}

/* Botones del mockup: Cargar = gradiente del acento, Eliminar = danger blanco/rojo */
.st-key-btn_cargar_proyecto button{
background:linear-gradient(120deg,var(--ac,#2563eb),var(--ac2,#1e40af)) !important;color:#fff !important;
border:1.5px solid transparent !important;border-radius:13px !important;padding:11px 18px !important;
font-weight:800 !important;font-size:12.5px !important;letter-spacing:.01em !important;
box-shadow:0 10px 20px color-mix(in srgb, var(--ac,#2563eb) 35%, transparent), inset 0 1px 0 rgba(255,255,255,.28) !important}
.st-key-btn_cargar_proyecto button:hover{filter:brightness(1.06)}
.st-key-btn_cargar_proyecto button p{font-weight:800 !important;font-size:12.5px !important;color:#fff !important}
.st-key-btn_eliminar_proyecto button{
background:#fff !important;border:1.5px solid #fecaca !important;color:#dc2626 !important;
border-radius:13px !important;padding:11px 18px !important;font-weight:800 !important;font-size:12.5px !important;
box-shadow:0 2px 6px rgba(11,36,71,.05) !important}
.st-key-btn_eliminar_proyecto button p{font-weight:800 !important;font-size:12.5px !important;color:#dc2626 !important}
.st-key-btn_eliminar_proyecto button:hover{border-color:#fca5a5 !important;background:#fef2f2 !important}

/* Tabla .tbl del mockup */
.home-tbl{width:100%;border-collapse:separate;border-spacing:0;border:1px solid #d8e5f5;border-radius:14px;overflow:hidden;font-size:11.5px;color:#0b2447}
.home-tbl th{background:linear-gradient(180deg, color-mix(in srgb, var(--ac,#2563eb) 9%, #fff), color-mix(in srgb, var(--ac,#2563eb) 5%, #fff));
color:#0b2447;text-align:left;padding:9px 12px;font-size:9.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:900}
.home-tbl td{padding:8px 12px;border-top:1px solid #eef4fb;font-weight:650}
.home-tbl tr:nth-child(even) td{background:#fafcff}
.home-tbl td.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:750}
.home-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border-radius:999px;font-size:10.5px;font-weight:800;border:1px solid;white-space:nowrap}
.home-pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 0 3px color-mix(in srgb, currentColor 18%, transparent)}
.home-pill.ok{color:#15803d;background:#f0fdf4;border-color:#bbf7d0}

/* Expanders de configuración como chips del mockup */
.st-key-home_chip_mode [data-testid="stExpander"] details,
.st-key-home_chip_vista [data-testid="stExpander"] details{
border:1.5px solid #cfe0f5 !important;border-radius:999px !important;background:#fff !important;
box-shadow:0 2px 6px rgba(11,36,71,.04) !important}
.st-key-home_chip_mode [data-testid="stExpander"] details:not([open]),
.st-key-home_chip_vista [data-testid="stExpander"] details:not([open]){width:fit-content}
.st-key-home_chip_mode [data-testid="stExpander"] details[open],
.st-key-home_chip_vista [data-testid="stExpander"] details[open]{border-radius:18px !important}
.st-key-home_chip_mode [data-testid="stExpander"] summary,
.st-key-home_chip_vista [data-testid="stExpander"] summary{padding:9px 15px !important;min-height:0 !important}
.st-key-home_chip_mode [data-testid="stExpander"] summary span,
.st-key-home_chip_mode [data-testid="stExpander"] summary p,
.st-key-home_chip_vista [data-testid="stExpander"] summary span,
.st-key-home_chip_vista [data-testid="stExpander"] summary p{
font-size:12px !important;font-weight:800 !important;color:#5a6b85 !important}
.st-key-home_chip_mode [data-testid="stExpander"] summary svg,
.st-key-home_chip_vista [data-testid="stExpander"] summary svg,
.st-key-home_chip_mode [data-testid="stExpander"] summary [data-testid="stIconMaterial"],
.st-key-home_chip_vista [data-testid="stExpander"] summary [data-testid="stIconMaterial"],
.st-key-home_chip_mode [data-testid="stExpanderToggleIcon"],
.st-key-home_chip_vista [data-testid="stExpanderToggleIcon"]{display:none !important}
html body .st-key-home_chip_mode [data-testid="stExpander"] details{
background:linear-gradient(120deg, color-mix(in srgb, var(--ac,#2563eb) 13%, #fff), color-mix(in srgb, var(--ac,#2563eb) 6%, #fff)) !important;
border-color:var(--ac,#2563eb) !important;
box-shadow:0 6px 14px color-mix(in srgb, var(--ac,#2563eb) 18%, transparent) !important}
.st-key-home_chip_mode [data-testid="stExpander"] summary span,
.st-key-home_chip_mode [data-testid="stExpander"] summary p{color:var(--ac,#2563eb) !important}

/* Upload del mockup (la dropzone real queda invisible encima, clic/arrastre intactos) */
.st-key-home_upload_zone{position:relative}
.home-upload{border:2px dashed color-mix(in srgb, var(--ac,#2563eb) 42%, #fff);
background:linear-gradient(180deg, color-mix(in srgb, var(--ac,#2563eb) 5%, #fff), #fff);
border-radius:18px;padding:18px 24px;text-align:center;height:138px;
display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
.home-ui{width:52px;height:52px;margin:0 auto;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px;
background:#fff;border:1.5px solid color-mix(in srgb, var(--ac,#2563eb) 30%, #fff);
box-shadow:0 8px 18px color-mix(in srgb, var(--ac,#2563eb) 14%, transparent)}
.home-upload b{display:block;font-size:13px;margin-top:8px;color:#0b2447}
.home-upload span{display:block;font-size:10.5px;color:#5a6b85;font-weight:600}
.st-key-home_uploader{position:absolute !important;left:0;right:0;top:0;height:138px;z-index:6}
.st-key-home_uploader [data-testid="stFileUploader"]{height:100%}
.st-key-home_uploader [data-testid="stFileUploader"] section{height:100% !important;opacity:0 !important;cursor:pointer}
.st-key-home_uploader [data-testid="stFileUploaderFile"],
.st-key-home_uploader [data-testid="stFileUploaderDeleteBtn"]{display:none !important}
[data-testid="stFileUploaderDropzoneInstructions"]{display:none !important}
[data-testid="stFileUploader"] small{display:none !important}

/* Tiles KPI de fases (mockup .kpi, icono circular tintado por fase) */
.home-kgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:4px 0 2px}
.home-kpi{background:#fff;border:1px solid #d8e5f5;border-radius:18px;padding:13px 14px;display:flex;gap:12px;align-items:center;
box-shadow:0 1px 2px rgba(11,36,71,.04), 0 6px 16px rgba(11,36,71,.06)}
.home-ki{width:50px;height:50px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0;
background:linear-gradient(135deg, color-mix(in srgb, var(--kc,#2563eb) 17%, #fff), color-mix(in srgb, var(--kc,#2563eb) 6%, #fff));
border:1.5px solid color-mix(in srgb, var(--kc,#2563eb) 38%, #fff);
box-shadow:0 5px 12px color-mix(in srgb, var(--kc,#2563eb) 18%, transparent)}
.home-kpi small{display:block;font-size:9px;font-weight:900;color:#64748b;text-transform:uppercase;letter-spacing:.07em}
.home-kpi b{font-size:13.5px;letter-spacing:-.025em;line-height:1.08;display:block;margin-top:3px;color:#0b2447}
.home-kpi i{font-style:normal;font-size:10px;color:#5a6b85;display:block;margin-top:2.5px;font-weight:600}

/* Fila final c2 + chips de flujo (todos con acento azul, flechas sueltas) */
.home-final-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.home-final-row .home-card{margin-bottom:0}
.home-chips{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 0;align-items:center}
.home-chip{padding:9px 15px;border-radius:999px;border:1.5px solid #cfe0f5;background:#fff;font-size:12px;font-weight:800;
color:#5a6b85;display:flex;gap:7px;align-items:center;box-shadow:0 2px 6px rgba(11,36,71,.04)}
.home-chip.on{background:linear-gradient(120deg, color-mix(in srgb, var(--ac,#2563eb) 13%, #fff), color-mix(in srgb, var(--ac,#2563eb) 6%, #fff));
border-color:var(--ac,#2563eb);color:var(--ac,#2563eb);box-shadow:0 6px 14px color-mix(in srgb, var(--ac,#2563eb) 18%, transparent)}
.home-chip.arrow{border:none;background:none;box-shadow:none;padding:9px 2px;color:#5a6b85}

/* Footer fino del mockup */
.home-footer{margin-top:28px;color:#94a3b8;font-size:10px;text-align:center;font-weight:600}

/* Estados auxiliares existentes (mensajes/confirmaciones) */
.home-empty-state{display:flex;gap:12px;align-items:center;background:#f8fbff;border:1px dashed #bfdbfe;border-radius:14px;padding:16px;color:#0b2447}
.home-confirm-box{background:#fff7f7;border:1px solid #fecaca;border-radius:16px;padding:16px 18px;color:#7f1d1d;margin:12px 0}
.home-upload-detected{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:16px;padding:12px 16px;color:#14532d;margin:0}

@media(max-width:1100px){.home-kgrid{grid-template-columns:repeat(3,1fr)}.home-final-row{grid-template-columns:1fr}}
@media(max-width:700px){.home-kgrid{grid-template-columns:repeat(2,1fr)}}

/* ── Refuerzos de cascada (assets/style.css usa selectores más específicos) ── */
.st-key-btn_cargar_proyecto div[data-testid="stButton"]>button{
background:linear-gradient(120deg,var(--ac,#2563eb),var(--ac2,#1e40af)) !important;color:#fff !important;
border:1.5px solid transparent !important;border-radius:13px !important;padding:11px 18px !important;
min-height:0 !important;font-weight:800 !important;font-size:12.5px !important;letter-spacing:.01em !important;
box-shadow:0 10px 20px color-mix(in srgb, var(--ac,#2563eb) 35%, transparent), inset 0 1px 0 rgba(255,255,255,.28) !important}
.st-key-btn_cargar_proyecto div[data-testid="stButton"]>button:hover{
background:linear-gradient(120deg,var(--ac,#2563eb),var(--ac2,#1e40af)) !important;color:#fff !important;
border-color:transparent !important;filter:brightness(1.07)}
.st-key-btn_cargar_proyecto div[data-testid="stButton"]>button p{color:#fff !important;font-weight:800 !important;font-size:12.5px !important}
.st-key-btn_eliminar_proyecto div[data-testid="stButton"]>button{
background:#fff !important;border:1.5px solid #fecaca !important;color:#dc2626 !important;
border-radius:13px !important;padding:11px 18px !important;min-height:0 !important;
font-weight:800 !important;font-size:12.5px !important;box-shadow:0 2px 6px rgba(11,36,71,.05) !important}
.st-key-btn_eliminar_proyecto div[data-testid="stButton"]>button:hover{
background:#fef2f2 !important;border-color:#fca5a5 !important;color:#dc2626 !important}
.st-key-btn_eliminar_proyecto div[data-testid="stButton"]>button p{color:#dc2626 !important;font-weight:800 !important;font-size:12.5px !important}
html body div.st-key-home_chip_mode [data-testid="stExpander"],
html body div.st-key-home_chip_vista [data-testid="stExpander"]{
background:transparent !important;border:none !important;box-shadow:none !important;border-radius:999px !important}
#root .st-key-home_chip_mode [data-testid="stExpander"] summary,
#root .st-key-home_chip_mode [data-testid="stExpander"] summary span,
#root .st-key-home_chip_mode [data-testid="stExpander"] summary p{color:var(--ac,#2563eb) !important}
#root .st-key-home_chip_vista [data-testid="stExpander"] summary,
#root .st-key-home_chip_vista [data-testid="stExpander"] summary span,
#root .st-key-home_chip_vista [data-testid="stExpander"] summary p{color:#5a6b85 !important}
</style>
""",
    unsafe_allow_html=True,
)

render_dropdown_visibility_fix()

_show_project_message()

# -----------------------------------------------------------------------------
# SVG de líneas de viento del hero (idéntico al mockup)
# -----------------------------------------------------------------------------
_WIND_SVG = (
    '<svg class="home-wind" viewBox="0 0 600 190" preserveAspectRatio="none">'
    '<path d="M0 42 Q150 24 300 44 T600 34"/>'
    '<path d="M0 100 Q180 82 340 102 T600 92"/>'
    '<path d="M0 156 Q140 142 300 158 T600 150"/></svg>'
)

# -----------------------------------------------------------------------------
# Hero y descripción
# -----------------------------------------------------------------------------
# Datos rápidos del hero (lecturas cacheadas — costo ~0 tras el warmup)
try:
    _n_proyectos = len(listar_proyectos_guardados())
except Exception:
    _n_proyectos = 0
try:
    _df_nasa_hero = cargar_nasa_hourly()
    _n_anios_nasa = max(1, round(len(_df_nasa_hero) / 8760)) if _df_nasa_hero is not None and len(_df_nasa_hero) else 0
except Exception:
    _n_anios_nasa = 0
_pill_nasa = f"{_n_anios_nasa} años" if _n_anios_nasa else "—"

st.markdown(
    f"""
<style>:root{{--home-nproj:"{_n_proyectos} proyectos"}}</style>
<div class="home-ref-hero">
    {_WIND_SVG}
    <div class="home-ref-hero-badge">🏠</div>
    <div class="home-ref-hero-text">
        <h1 class="home-ref-hero-title">Aplicación para cálculos de parques eólicos</h1>
        <div class="home-ref-hero-sub">Plataforma integrada para análisis del recurso eólico y estimación del AEP, pérdidas, estelas y economía.</div>
    </div>
    <div class="home-ref-hero-pills">
        <div class="home-ref-hpill"><b>{_n_proyectos}</b><span>Proyectos</span></div>
        <div class="home-ref-hpill"><b>7</b><span>Fases</span></div>
        <div class="home-ref-hpill"><b>{_pill_nasa}</b><span>Datos NASA</span></div>
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# Stepper DEBAJO del hero, como en el mockup
render_stepper("Inicio.py")

st.markdown(
    """
<div class="home-card">
    <div class="home-card-head"><div class="home-cicon">ℹ️</div>
        <div><h2>Descripción general</h2><p>Qué hace la aplicación y cómo trabajar por fases</p></div>
    </div>
    <p class="home-muted">Análisis completo de un parque eólico por fases: desde el aerogenerador y el recurso de viento hasta pérdidas, AEP neto, estudios avanzados y reportes. Lo guardado en cada fase alimenta a las siguientes.</p>
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

col_left, col_right = st.columns([2, 1], gap="small")

# --- IZQUIERDA: Gestión de proyectos ---
with col_left:
    with st.container(border=True, key="home_card_projects"):
        st.markdown(
            '<div class="home-card-head"><div class="home-cicon">🗂️</div>'
            '<div><h2>Gestión de proyectos</h2><p>Cargue, elimine o continúe un proyecto guardado</p></div></div>',
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

            # Label en mayúsculas sobre el input (el conteo "N proyectos" lo
            # define --home-nproj, inyectada junto al hero).
            st.markdown('<div class="home-flabel">Proyecto guardado</div>', unsafe_allow_html=True)
            proyecto_sel = st.selectbox(
                "Seleccione un proyecto guardado",
                nombres_proyectos,
                key="home_project_selectbox",
                label_visibility="collapsed",
            )
            btn_c1, btn_c2, _btn_sp = st.columns([1.35, 1, 3.1], gap="small")
            with btn_c1:
                if st.button("📂 Cargar proyecto", key="btn_cargar_proyecto", use_container_width=True):
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
                if st.button("🗑️ Eliminar", key="btn_eliminar_proyecto", use_container_width=True):
                    st.session_state.confirm_delete_project = True
                    st.session_state.project_to_delete = proyecto_sel or nombres_proyectos[0]

            # ── Tabla de proyectos HTML, idéntica a .tbl del mockup ──
            filas = []
            for _idx, _row in proyectos_df.reset_index(drop=True).iterrows():
                _name_raw = str(_row.get("name", "Proyecto"))
                _updated = _format_datetime(_row.get("updated_at", ""))
                _estado = '<span class="home-pill ok">Activo</span>' if _name_raw.strip() == nombre_activo else ""
                filas.append(
                    f'<tr><td class="num">{_idx + 1}</td><td>{_escape(_name_raw)}</td>'
                    f'<td>{_escape(_updated)}</td><td>{_estado}</td></tr>'
                )
            st.markdown(
                '<div class="home-tbl-wrap"><table class="home-tbl"><thead><tr><th>#</th><th>Nombre del proyecto</th>'
                '<th>\u00daltima actualizaci\u00f3n</th><th>Estado</th></tr></thead>'
                f'<tbody>{"".join(filas)}</tbody></table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Todavía no hay proyectos guardados.")

# --- DERECHA: Configuración + Importar ---
with col_right:
    with st.container(border=True, key="home_card_config"):
        st.markdown(
            '<div class="home-card-head"><div class="home-cicon">⚙️</div>'
            '<div><h2>Configuración general</h2><p>Modo, perfil y vista previa del reporte</p></div></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="home_chip_mode"), st.expander("Modo y perfil del proyecto"):
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
        with st.container(key="home_chip_vista"), st.expander("Vista previa de reporte y exportación"):
            st.caption(f"Estilo: {report_context['report_style_label']} · Citas: {report_context['citation_style']}")
            for section in report_context["report_sections"][:4]:
                st.markdown(f"- {section}")
            st.caption(report_context["template_hint"])
        st.markdown(
            '<p class="home-muted">Perfil académico o bancable; define qué secciones llevará el informe.</p>',
            unsafe_allow_html=True,
        )

    with st.container(border=True, key="home_card_import"):
        st.markdown(
            '<div class="home-card-head"><div class="home-cicon">📥</div>'
            '<div><h2>Importar proyecto</h2><p>Restaurar desde archivo .json</p></div></div>',
            unsafe_allow_html=True,
        )
        with st.container(key="home_upload_zone"):
            st.markdown(
                '<div class="home-upload"><div class="home-ui">☁️</div>'
                '<b>Arrastre su archivo .json aquí</b>'
                '<span>o haga clic para seleccionar · máx. 200 MB</span></div>',
                unsafe_allow_html=True,
            )
            archivo_proyecto = st.file_uploader(
                "Suba un archivo .json de proyecto",
                type=["json"],
                key="home_uploader",
                label_visibility="collapsed",
            )
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
# (etiqueta, nombre, emoji, color de la fase — misma paleta Aurora de navigation)
_phase_mini = [
    ("Fase 1", "Aerogenerador", "🌀", "#0284c7"),
    ("Fase 2", "Perfiles de viento", "🌬️", "#0891b2"),
    ("Fase 3", "Rosa y velocidad", "🧭", "#4f46e5"),
    ("Fase 4", "Estelas y arreglo", "🌪️", "#7c3aed"),
    ("Fase 5", "AEP y economía", "⚡", "#059669"),
    ("Fase 6", "Estudios avanzados", "🔬", "#0d9488"),
    ("Fase 7", "Exportar y guardar", "📦", "#d97706"),
]

_tiles_html = "".join(
    f'<div class="home-kpi" style="--kc:{color}"><div class="home-ki">{emoji}</div>'
    f'<div><small>{_escape(num)}</small><b>{_escape(nombre)}</b><i>›</i></div></div>'
    for num, nombre, emoji, color in _phase_mini
)

st.markdown(
    f"""
<div class="home-card">
    <div class="home-card-head"><div class="home-cicon">🧩</div>
        <div><h2>Fases de la aplicación</h2><p>Recorrido completo del análisis</p></div>
    </div>
    <div class="home-kgrid">{_tiles_html}</div>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Cards finales (c2 del mockup) + footer
# -----------------------------------------------------------------------------
_flow_chips_html = '<div class="home-chip arrow">→</div>'.join(
    f'<div class="home-chip on">{emoji} {_escape(num)}</div>'
    for num, _nombre, emoji, _color in _phase_mini
)

st.markdown(
    f"""
<div class="home-final-row">
    <div class="home-card" style="--acl:#16a34a">
        <div class="home-card-head"><div class="home-cicon">🏆</div>
            <div><h2>Resultado final esperado</h2><p>Lo que obtendrá al completar las siete fases</p></div>
        </div>
        <p class="home-muted">AEP bruto y neto del parque con pérdidas por estelas y disponibilidad, estudios de sitio y ambientales, economía (LCOE, VPN, TIR) y reportes ejecutivos, técnicos y bancables listos para descargar.</p>
    </div>
    <div class="home-card">
        <div class="home-card-head"><div class="home-cicon">🧭</div>
            <div><h2>Flujo recomendado</h2><p>Orden sugerido de trabajo</p></div>
        </div>
        <div class="home-chips">{_flow_chips_html}</div>
    </div>
</div>
<footer class="home-footer">SMA 2.0 · Wind Project Analyzer</footer>
""",
    unsafe_allow_html=True,
)

