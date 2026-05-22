"""Centralized loader for global CSS assets.

Caches the CSS file content via @st.cache_data, keyed on file mtime so
edits to assets/style.css invalidate automatically without restarting.

Adicionalmente expone `preload_all_phases_css()` que:
  - Lee el código fuente de TODAS las páginas (`pages/*.py`)
  - Extrae con regex cada bloque `<style>...</style>` que cada página inyecta
    vía `st.markdown(...)`
  - Concatena todo en un único string cacheado por mtime de todos los archivos
  - Lo inyecta como UN SOLO `<style>` al inicio de la página actual

Resultado: cuando el usuario navega entre fases, el CSS de TODAS las fases ya
está aplicado desde el primer frame — no hay flash del diseño anterior porque
las reglas que estilizan los `st-key-fN_*` de cada fase están presentes en
la página actual aunque pertenezcan a otra fase.
"""
import re
from pathlib import Path

import streamlit as st

_BASE_DIR = Path(__file__).resolve().parent
_CSS_PATH = _BASE_DIR / "assets" / "style.css"
_PAGES_DIR = _BASE_DIR / "pages"
# Regex no-greedy + DOTALL para capturar el contenido de cada bloque <style>.
# CSS no contiene literal "</style>" así que el matching es seguro.
_STYLE_BLOCK_RE = re.compile(r"<style>(.*?)</style>", re.DOTALL)

_ANTI_FOUC = """
/* Anti-FOUC para navegación rápida */
[data-testid="stAppViewContainer"] {
    opacity: 0;
    animation: revealApp 0.15s ease 0.08s forwards;
}
@keyframes revealApp {
    to { opacity: 1; }
}
/* Colapsar contenedores que solo inyectan <style> (sin contenido visible) para alinear el hero entre fases */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] > div > style:only-child) {
    display: none !important;
}
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style):not(:has([data-testid="stMarkdown"] p)):not(:has([data-testid="stMarkdown"] h1)):not(:has([data-testid="stMarkdown"] h2)):not(:has([data-testid="stMarkdown"] h3)):not(:has([data-testid="stMarkdown"] li)):not(:has([data-testid="stMarkdown"] table)) {
    display: none !important;
}
"""


@st.cache_data(show_spinner=False)
def _read_css(_mtime_ns: int) -> str:
    """Read style.css from disk. Cached by mtime so edits auto-invalidate."""
    if not _CSS_PATH.exists():
        return ""
    return _CSS_PATH.read_text(encoding="utf-8")


@st.cache_data(show_spinner=False)
def _build_style_block(_mtime_ns: int, include_anti_fouc: bool) -> str:
    css = _read_css(_mtime_ns)
    if not css:
        return ""
    if include_anti_fouc:
        return f"<style>{_ANTI_FOUC}\n{css}</style>"
    return f"<style>{css}</style>"


def load_global_css(include_anti_fouc: bool = False) -> None:
    """Inject the global stylesheet into the current page.

    Args:
        include_anti_fouc: True for sidebar/navigation contexts that need the
            opacity-fade trick to hide layout reflow between phase changes.
    """
    if not _CSS_PATH.exists():
        return
    mtime_ns = _CSS_PATH.stat().st_mtime_ns
    block = _build_style_block(mtime_ns, include_anti_fouc)
    if block:
        st.markdown(block, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Preload del CSS de TODAS las fases en una sola inyección.
# ─────────────────────────────────────────────────────────────────────────────

def _pages_mtime_stamp() -> tuple:
    """Stamp basado en mtime de todos los archivos .py de pages/.

    Se usa como clave del cache: si editas cualquier página, el cache se
    invalida y el CSS combinado se recalcula automáticamente.
    """
    if not _PAGES_DIR.exists():
        return ()
    stamps = []
    for py_file in sorted(_PAGES_DIR.glob("*.py")):
        try:
            stamps.append((py_file.name, py_file.stat().st_mtime_ns))
        except OSError:
            stamps.append((py_file.name, 0))
    return tuple(stamps)


@st.cache_data(show_spinner=False)
def _build_all_phases_css(_stamp: tuple) -> str:
    """Lee todas las pages/*.py, extrae cada bloque <style> y los concatena.

    Cacheado por mtime de todos los archivos. Costo real solo al primer
    arranque o cuando editas alguna página.
    """
    if not _PAGES_DIR.exists():
        return ""
    parts: list[str] = []
    for py_file in sorted(_PAGES_DIR.glob("*.py")):
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _STYLE_BLOCK_RE.findall(source):
            css = match.strip()
            if css:
                parts.append(f"/* === {py_file.name} === */\n{css}")
    return "\n\n".join(parts)


def preload_all_phases_css() -> None:
    """Inyecta el CSS combinado de TODAS las fases en un solo `<style>`.

    Idempotente y barata gracias al cache: llamarla al inicio de cada página
    cuesta esencialmente cero después del primer render del proceso.

    Beneficio: aunque el usuario esté en Fase 1, las reglas que estilizan
    Fase 2..6 también están aplicadas en el DOM. Cuando navega a otra fase,
    el navegador no espera nada — los selectores `.st-key-fN_*` ya tienen
    sus reglas, no hay flash del diseño anterior entre páginas.
    """
    combined = _build_all_phases_css(_pages_mtime_stamp())
    if combined:
        st.markdown(f"<style>\n{combined}\n</style>", unsafe_allow_html=True)
