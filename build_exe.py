"""
build_exe.py - Script de compilación de la Alfa App a .exe
===========================================================

USO:
    python build_exe.py

Qué hace:
  0. Verifica/instala PyInstaller.
  1. Parcha el index.html de Streamlit con anti-FOUC (background inicial
     en color del tema, fade-in de 120ms al montar). El parche se aplica al
     paquete instalado ANTES de empaquetar, así el .exe ya viene con un
     Streamlit pre-parchado y nunca muestra fondo blanco crudo al cargar.
  2. Limpia carpetas dist/ y build/ anteriores.
  3. Compila con el spec completo (AppEolica.spec).
  4. Verifica el resultado.

Notas de robustez:
  - Forza UTF-8 en stdout para que los caracteres ✓ ⚠ no rompan la consola
    de Windows con codepage cp1252.
  - Si PyInstaller falla con errores claros, los muestra. Si crashea por
    Unicode, el wrapper de prints lo evita.

Requisito: pip install pyinstaller (se instala automático si falta).
"""

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Forzar UTF-8 en stdout/stderr para que ✓ ⚠ no crasheen en Windows. ──
# Hacerlo lo antes posible, antes del primer print().
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
else:
    # Fallback para Python < 3.7 (no debería pasar pero por si acaso)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parent
SPEC = BASE / "AppEolica.spec"
DIST = BASE / "dist"
BUILD = BASE / "build"
PATCH_SCRIPT = BASE / "patch_streamlit_index.py"


def asegurar_pyinstaller():
    print("\n[0/5] Verificando PyInstaller...")
    try:
        import PyInstaller  # noqa: F401
        print("    [OK] PyInstaller ya instalado")
    except ImportError:
        print("    [!] PyInstaller no encontrado. Instalando...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
        if r.returncode != 0:
            print("\n[X] No se pudo instalar PyInstaller.")
            sys.exit(1)
        print("    [OK] PyInstaller instalado")


def parchar_streamlit_index():
    """Aplicar parche anti-FOUC al index.html de Streamlit instalado.

    Es idempotente: si ya está parchado, lo re-parcha igual sin duplicar.
    Si falla por algún motivo (Streamlit no encontrado, permisos), avisa
    pero no aborta el build — el .exe seguirá funcionando, solo perderá
    la optimización a nivel del framework.
    """
    print("\n[1/5] Parchando index.html de Streamlit (anti-FOUC)...")
    if not PATCH_SCRIPT.exists():
        print(f"    [!] {PATCH_SCRIPT.name} no encontrado — se omite el parche.")
        return
    try:
        r = subprocess.run(
            [sys.executable, str(PATCH_SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode == 0:
            print(f"    [OK] {r.stdout.strip() or 'parche aplicado'}")
        else:
            print("    [!] El parche devolvió error pero el build continúa:")
            print(f"        stdout: {r.stdout.strip()}")
            print(f"        stderr: {r.stderr.strip()}")
    except Exception as e:
        print(f"    [!] No se pudo ejecutar el parche ({e}) — el build continúa.")


def matar_procesos_previos():
    """Cierra cualquier instancia previa del .exe que bloquee archivos."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/IM", "Alfa App.exe"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def limpiar():
    print("\n[2/5] Limpiando compilaciones anteriores...")
    matar_procesos_previos()
    for carpeta in (DIST, BUILD):
        if carpeta.exists():
            try:
                shutil.rmtree(carpeta)
                print(f"    Eliminado: {carpeta}")
            except PermissionError as e:
                print(f"    [!] No se pudo borrar {carpeta}: {e}")
                print("       Cierra el .exe y reintenta.")
                sys.exit(1)
    print("    [OK] Listo")


def compilar():
    print("\n[3/5] Compilando con PyInstaller (puede tardar 2-3 min)...")
    print(f"    Spec: {SPEC}")
    # Pasar UTF-8 al subprocess también
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--clean", str(SPEC)],
        cwd=str(BASE),
        env=env,
    )
    if result.returncode != 0:
        print("\n[X] La compilación falló. Revisa los errores arriba.")
        sys.exit(1)


def verificar():
    exe = DIST / "Alfa App" / "Alfa App.exe"
    print("\n[4/5] Verificando resultado del PyInstaller...")
    if not exe.exists():
        print(f"\n[X] No se encontró el .exe en {exe}")
        print("   Revisa los mensajes de error de PyInstaller.\n")
        sys.exit(1)
    size_mb = exe.stat().st_size / (1024 * 1024)
    print(f"    [OK] Ejecutable creado: {exe}")
    print(f"    [OK] Tamaño: {size_mb:.1f} MB")


def verificar_archivos_clave_empaquetados():
    """Smoke check: que el bundle contenga los archivos críticos.

    Si falta algo, el .exe arrancaría con bugs raros en producción. Mejor
    detectarlo aquí y avisar antes de distribuir.
    """
    print("\n[5/5] Verificando archivos críticos en el bundle...")
    internal = DIST / "Alfa App" / "_internal"
    requeridos = [
        ("Inicio.py", internal / "Inicio.py"),
        ("db.py", internal / "db.py"),
        ("navigation.py", internal / "navigation.py"),
        ("assets_loader.py", internal / "assets_loader.py"),
        ("pages/1_Fase_1_Aerogenerador.py", internal / "pages" / "1_Fase_1_Aerogenerador.py"),
        ("pages/6_Fase_6_Exportar_y_guardar.py", internal / "pages" / "6_Fase_6_Exportar_y_guardar.py"),
        ("assets/style.css", internal / "assets" / "style.css"),
        (".streamlit/config.toml", internal / ".streamlit" / "config.toml"),
    ]
    faltantes = [name for name, path in requeridos if not path.exists()]
    if faltantes:
        print("    [X] Faltan archivos críticos en el bundle:")
        for n in faltantes:
            print(f"        - {n}")
        print("    El .exe puede tener comportamiento errático. NO distribuir.")
        sys.exit(1)

    # Verificar que el código bundled tenga los fixes clave (no una versión vieja)
    smoke_checks = [
        (internal / "db.py", "_seed_empty_curve_if_needed",
         "fix defensivo de guardar_tabla_curva"),
        (internal / "assets_loader.py", "preload_all_phases_css",
         "preload de CSS de todas las fases"),
        (internal / "navigation.py", "_preload_all_phases_css",
         "llamada al preload desde el sidebar"),
    ]
    fallos = []
    for path, needle, desc in smoke_checks:
        try:
            if needle not in path.read_text(encoding="utf-8"):
                fallos.append(f"{path.name} no contiene '{needle}' ({desc})")
        except Exception as e:
            fallos.append(f"no se pudo leer {path}: {e}")
    if fallos:
        print("    [X] El bundle parece estar usando código viejo:")
        for f in fallos:
            print(f"        - {f}")
        sys.exit(1)

    print("    [OK] Todos los archivos críticos están presentes y al día")


if __name__ == "__main__":
    print("=" * 55)
    print("   Alfa App - Compilador de .exe")
    print("=" * 55)
    asegurar_pyinstaller()
    parchar_streamlit_index()
    limpiar()
    compilar()
    verificar()
    verificar_archivos_clave_empaquetados()
    exe = DIST / "Alfa App" / "Alfa App.exe"
    print(f"\n{'='*55}")
    print("  LISTO. Tu .exe está en:")
    print(f"  {exe.parent}")
    print(f"{'='*55}\n")
