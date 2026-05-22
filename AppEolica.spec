# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  AppEolica.spec  —  Build completo con metadatos corregidos
#  Ejecutar:  python build_exe.py   (o:  python -m PyInstaller AppEolica.spec)
# ============================================================
from PyInstaller.utils.hooks import collect_all, copy_metadata
import os

# ── 1. Archivos del proyecto ─────────────────────────────────
datas = [
    ('pages',               'pages'),
    ('reportes',            'reportes'),
    ('assets',              'assets'),
    ('Inicio.py',           '.'),
    ('calculos.py',         '.'),
    ('calculos_economicos.py', '.'),
    ('calculos_energia.py', '.'),
    ('db.py',               '.'),
    ('assets_loader.py',    '.'),
    ('perf.py',             '.'),
    ('navigation.py',       '.'),
    ('data_helpers.py',     '.'),
    ('session_helpers.py',  '.'),
    ('widget_helpers.py',   '.'),
    ('patch_streamlit_index.py', '.'),
]

# Incluir config de Streamlit si existe
if os.path.isdir('.streamlit'):
    datas.append(('.streamlit', '.streamlit'))

binaries = []
hiddenimports = [
    # Módulos del proyecto
    'assets_loader', 'perf', 'navigation', 'db', 'calculos',
    'calculos_economicos', 'calculos_energia', 'data_helpers',
    'session_helpers', 'widget_helpers', 'patch_streamlit_index',
    'reportes',
    # Streamlit internals necesarios
    'streamlit.web.bootstrap',
    'streamlit.web.cli',
    'streamlit.runtime.scriptrunner',
    'streamlit.runtime.caching',
    # Otros
    'requests',
    'sqlite3',
    'xml.etree.ElementTree',
]

# ── 2. collect_all: binarios + datos + hidden imports ────────
COLLECT_PKGS = (
    'streamlit', 'plotly', 'pandas', 'numpy',
    'folium', 'streamlit_folium', 'branca',
    'PIL', 'altair', 'pyarrow', 'requests',
)
for pkg in COLLECT_PKGS:
    try:
        tmp = collect_all(pkg)
        datas     += tmp[0]
        binaries  += tmp[1]
        hiddenimports += tmp[2]
    except Exception:
        pass

# ── 3. copy_metadata: dist-info para importlib.metadata ──────
#    ESTA es la línea que corrige "No package metadata was found"
METADATA_PKGS = (
    'streamlit', 'pandas', 'numpy', 'plotly', 'pyarrow',
    'altair', 'folium', 'streamlit_folium', 'branca',
    'Pillow', 'requests', 'click', 'rich', 'tornado',
    'watchdog', 'packaging', 'pydeck', 'validators',
    'toml', 'blinker', 'cachetools', 'gitpython',
    'protobuf', 'pyzmq', 'typing_extensions',
)
for pkg in METADATA_PKGS:
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# ── 4. Analysis ───────────────────────────────────────────────
a = Analysis(
    ['launcher.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'tkinter', 'scipy', 'IPython', 'jupyter'],
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
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX puede causar falsos positivos en antivirus
    console=True,       # True = ventana de consola visible (útil para ver errores)
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
