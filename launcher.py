import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Fuerza modo producción ANTES de cargar Streamlit
os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
os.environ["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"
os.environ["STREAMLIT_SERVER_PORT"] = "8501"
# Producción: sin file watcher, sin runOnSave, sin magic. Reduce CPU idle.
os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
os.environ["STREAMLIT_SERVER_RUN_ON_SAVE"] = "false"
os.environ["STREAMLIT_RUNNER_MAGIC_ENABLED"] = "false"
os.environ["STREAMLIT_CLIENT_TOOLBAR_MODE"] = "minimal"
os.environ["STREAMLIT_CLIENT_SHOW_ERROR_DETAILS"] = "false"
# Anti-FOUC: apagar el sidebar auto-generado por la carpeta `pages/` desde el
# arranque del proceso. Antes lo escondíamos con CSS desde navigation.py, pero
# ese CSS llegaba después del primer render, dejando ver el sidebar default
# por unos ms. Con esta env var Streamlit ni lo monta.
os.environ["STREAMLIT_CLIENT_SHOW_SIDEBAR_NAVIGATION"] = "false"
# Tema base: el navegador pinta con estos colores DESDE el primer frame,
# antes de que llegue nuestro CSS custom — elimina el flash blanco.
os.environ["STREAMLIT_THEME_BASE"] = "light"
os.environ["STREAMLIT_THEME_PRIMARY_COLOR"] = "#2563eb"
os.environ["STREAMLIT_THEME_BACKGROUND_COLOR"] = "#F5F9FF"
os.environ["STREAMLIT_THEME_SECONDARY_BACKGROUND_COLOR"] = "#F3F8FF"
os.environ["STREAMLIT_THEME_TEXT_COLOR"] = "#0F172A"

from streamlit import config as st_config
from streamlit.web import bootstrap


def _ensure_streamlit_index_patched() -> None:
    """Auto-parchar el index.html de Streamlit en runtime si no está parchado.

    Defensa en profundidad: build_exe.py ya intenta parcharlo antes de
    empaquetar, pero si por algún motivo el bundle quedó sin parche (o el
    usuario está corriendo desde dev sin haber ejecutado patch_streamlit_index.py),
    esta función lo aplica al vuelo en el primer arranque.

    Idempotente: si ya está parchado, no hace nada.
    """
    try:
        import streamlit
        index_path = Path(streamlit.__file__).parent / "static" / "index.html"
        if not index_path.is_file():
            return
        content = index_path.read_text(encoding="utf-8")
        if "SMA 2.0 anti-FOUC" in content:
            return  # ya parchado
        # Importar y ejecutar el patcher
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            import patch_streamlit_index
            patch_streamlit_index.patch(str(index_path))
        except Exception:
            pass
    except Exception:
        # Anti-FOUC es nice-to-have; nunca bloquear arranque
        pass


_ensure_streamlit_index_patched()


def _preload_heavy_modules() -> None:
    """Import módulos pesados en thread paralelo antes de levantar Streamlit.

    Reduce el cold-start visible: cuando bootstrap.run arranca el servidor,
    estos imports ya están en memoria y Inicio.py los re-usa sin coste.
    """
    try:
        import numpy  # noqa: F401
        import pandas  # noqa: F401
        import plotly.express  # noqa: F401
        import plotly.graph_objects  # noqa: F401
    except Exception:
        pass
    try:
        # Imports del proyecto (deben funcionar desde sys.path normal)
        import calculos  # noqa: F401
        import calculos_economicos  # noqa: F401
        import calculos_energia  # noqa: F401
        import db  # noqa: F401
    except Exception:
        pass


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative_path)
    return str(Path(__file__).resolve().parent / relative_path)


def wait_for_server(host: str, port: int, timeout: float = 25.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def open_browser_when_ready(host: str, port: int) -> None:
    if wait_for_server(host, port):
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            pass


def run_app() -> None:
    app_file = resource_path("Inicio.py")

    if not os.path.exists(app_file):
        raise FileNotFoundError(f"No se encontró el archivo principal: {app_file}")

    host = "127.0.0.1"
    port = 8501

    # Refuerza configuración en tiempo de ejecución
    st_config.set_option("global.developmentMode", False)
    st_config.set_option("server.headless", True)
    st_config.set_option("server.address", host)
    st_config.set_option("server.port", port)
    st_config.set_option("browser.gatherUsageStats", False)
    st_config.set_option("server.fileWatcherType", "none")
    st_config.set_option("server.runOnSave", False)
    st_config.set_option("runner.magicEnabled", False)
    st_config.set_option("client.toolbarMode", "minimal")

    threading.Thread(
        target=open_browser_when_ready,
        args=(host, port),
        daemon=True,
    ).start()

    threading.Thread(
        target=_preload_heavy_modules,
        daemon=True,
    ).start()

    bootstrap.run(app_file, False, [], {})


if __name__ == "__main__":
    run_app()
