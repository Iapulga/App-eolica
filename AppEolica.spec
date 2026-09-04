# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  AppEolica.spec  —  Build completo con metadatos corregidos
#  Ejecutar:  python build_exe.py   (o:  python -m PyInstaller AppEolica.spec)
# ============================================================
from PyInstaller.utils.hooks import collect_all, copy_metadata
import glob
import os

# ── 1. Archivos del proyecto ─────────────────────────────────
# Se incluyen AUTOMÁTICAMENTE todos los .py de la raíz (excepto el script de
# build y el entry-point), para que el .exe tenga EXACTAMENTE los mismos módulos
# que el entorno de desarrollo (VS Code). Las páginas y `reportes` importan en
# runtime muchos de estos módulos (i18n_paises, gis_helpers, calculos_iec_site,
# calculos_uncertainty, shadow_flicker, ruido_iso9613, etc.); si falta alguno,
# la función que lo usa rompe en el .exe aunque funcione en VS Code.
# desktop_shell.py = entry (PyInstaller lo analiza como script); build_exe.py = herramienta de build.
# launcher.py SÍ se incluye ahora (antes era el entry): el proceso hijo del servidor —que lanza la
# carcasa de escritorio— hace `import launcher`, así que debe quedar como módulo importable.
_EXCLUDE_ROOT_PY = {'build_exe.py', 'desktop_shell.py'}
_root_py = sorted(f for f in glob.glob('*.py') if f not in _EXCLUDE_ROOT_PY)

# Icono opcional de la app (taskbar / ejecutable). Si no existe, PyInstaller usa el icono por defecto.
_icon = 'assets/app.ico' if os.path.isfile('assets/app.ico') else None

datas = [(f, '.') for f in _root_py]
datas += [
    ('pages',    'pages'),
    ('reportes', 'reportes'),
    ('assets',   'assets'),
]

# Incluir config de Streamlit si existe
if os.path.isdir('.streamlit'):
    datas.append(('.streamlit', '.streamlit'))

# ── 2. Hidden imports ────────────────────────────────────────
# Módulos locales de la raíz: agregarlos al import frozen garantiza que estén
# disponibles y que PyInstaller analice sus dependencias. Se excluyen los
# scripts/utilidades que NO deben ejecutarse durante el análisis (siguen
# empaquetados como datos, importables si hiciera falta).
# pre_audit_checklist salió de la lista: ahora lo importa la Fase 6 (Estudios
# avanzados) y es seguro de analizar (solo depende de pandas).
_NO_HIDDENIMPORT = {'_verify_and_patch'}
_root_modules = [
    os.path.splitext(f)[0] for f in _root_py
    if os.path.splitext(f)[0] not in _NO_HIDDENIMPORT
]

binaries = []
hiddenimports = [
    # ── Carcasa de escritorio: PySide6 + Qt WebEngine (Chromium incrustado) ──
    # Estos hiddenimports disparan los hooks oficiales de PyInstaller para PySide6,
    # que recolectan automáticamente QtWebEngineProcess.exe + resources (icudtl.dat,
    # *.pak) + qtwebengine_locales. Sin ellos el .exe abriría una ventana en blanco.
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'PySide6.QtNetwork', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
    # Streamlit internals necesarios
    'streamlit.web.bootstrap',
    'streamlit.web.cli',
    'streamlit.runtime.scriptrunner',
    'streamlit.runtime.caching',
    # Terceros usados de forma PEREZOSA (imports dentro de funciones), que el
    # análisis estático no detecta: exportación Word/bankable (python-docx +
    # lxml), Excel (openpyxl), imágenes de figuras para PDF/Word (kaleido),
    # exportación GIS (simplekml), mapas (folium/branca).
    'requests', 'sqlite3', 'xml.etree.ElementTree',
    'docx', 'lxml', 'lxml.etree', 'lxml._elementpath',
    'openpyxl', 'openpyxl.styles', 'openpyxl.cell', 'openpyxl.utils', 'et_xmlfile',
    'kaleido',
    'simplekml',
    'PIL', 'PIL.Image', 'PIL.ImageChops',
    'folium', 'streamlit_folium', 'branca',
] + _root_modules + ['reportes']

# ── 3. collect_all: binarios + datos + hidden imports ────────
COLLECT_PKGS = (
    'streamlit', 'plotly', 'pandas', 'numpy',
    'folium', 'streamlit_folium', 'branca',
    'PIL', 'altair', 'pyarrow', 'requests',
    # Añadidos: stack de exportación (docx/Excel/PDF-imagen/GIS).
    'docx', 'openpyxl', 'kaleido', 'simplekml', 'lxml',
)
for pkg in COLLECT_PKGS:
    try:
        tmp = collect_all(pkg)
        datas     += tmp[0]
        binaries  += tmp[1]
        hiddenimports += tmp[2]
    except Exception:
        pass

# collect_all() también devuelve suites de pruebas y módulos de desarrollo de
# pandas/numpy/plotly. No son necesarios para ejecutar la app y hacen que el
# análisis de PyInstaller sea muy lento; conservar solo imports de runtime.
hiddenimports = [
    name for name in hiddenimports
    if not (
        ".tests" in name
        or name.endswith(".conftest")
        or name in {"pandas.conftest", "numpy.conftest", "plotly.conftest"}
        or name.startswith("streamlit.testing")
        or name.startswith("streamlit.hello")
    )
]

# ── 4. copy_metadata: dist-info para importlib.metadata ──────
#    ESTA es la línea que corrige "No package metadata was found"
METADATA_PKGS = (
    'streamlit', 'pandas', 'numpy', 'plotly', 'pyarrow',
    'altair', 'folium', 'streamlit_folium', 'branca',
    'Pillow', 'requests', 'click', 'rich', 'tornado',
    'watchdog', 'packaging', 'pydeck', 'validators',
    'toml', 'blinker', 'cachetools', 'gitpython',
    'protobuf', 'pyzmq', 'typing_extensions',
    # Añadidos: usar el NOMBRE DE DISTRIBUCIÓN (no el de import).
    'python-docx', 'openpyxl', 'kaleido', 'simplekml', 'lxml', 'et_xmlfile',
)
for pkg in METADATA_PKGS:
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# ── 5. Analysis ───────────────────────────────────────────────
a = Analysis(
    ['desktop_shell.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # scipy YA NO se excluye: el optimizador de layout de Fase 6 requiere
    # scipy.optimize.differential_evolution, y el ajuste Gumbel (calculos.py) +
    # stats del bankable lo usan. Costo: ~80-120 MB más de bundle.
    excludes=['matplotlib', 'tkinter', 'IPython', 'jupyter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Alfa App',
    icon=_icon,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX puede causar falsos positivos en antivirus
    console=False,      # False = sin ventana de consola (cmd oculto). Los logs se
                        # redirigen a %LOCALAPPDATA%/AppEolica/app_log.txt desde
                        # launcher.py (ver _redirect_output_when_windowed).
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Alfa App',    # Carpeta en dist/
)
