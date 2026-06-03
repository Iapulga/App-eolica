import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _redirect_output_when_windowed() -> None:
    """En el .exe compilado sin consola (console=False), Windows no asigna una
    consola y PyInstaller deja `sys.stdout`/`sys.stderr` en None. Cualquier
    `print(...)` (p.ej. perf.py) o log a stderr lanzaría una excepción y podría
    romper el arranque. Redirigimos la salida a un archivo de log en
    %LOCALAPPDATA%/AppEolica/app_log.txt — así nada crashea y, si hace falta
    depurar, los mensajes quedan guardados. En dev (no frozen) no se toca nada.
    """
    if not getattr(sys, "frozen", False):
        return
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        log_dir = (Path(base) / "AppEolica") if base else (Path.home() / "AppEolica")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_dir / "app_log.txt", "w", encoding="utf-8", errors="replace")
        sys.stdout = log_handle
        sys.stderr = log_handle
    except Exception:
        # Último recurso: descartar la salida para no dejar stdout/stderr en None.
        try:
            devnull = open(os.devnull, "w")
            sys.stdout = devnull
            sys.stderr = devnull
        except Exception:
            pass


_redirect_output_when_windowed()

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


# Contador de websockets VIVOS (pestañas abiertas). Es la señal fiable de
# "hay una pestaña abierta": el websocket se cierra al instante al cerrar la
# pestaña (a diferencia de las conexiones HTTP keep-alive, que quedan en el pool;
# y a diferencia del 'estado' del runtime, que Streamlit retiene tras desconectar).
_WS_STATE = {"count": 0, "seen": False}


def _install_ws_counter() -> bool:
    """Monkeypatch del handler de websockets de Streamlit para contar pestañas
    vivas. Debe instalarse ANTES de que el servidor acepte conexiones. Idempotente.
    """
    try:
        import streamlit.web.server.browser_websocket_handler as bwh
    except Exception:
        return False
    H = bwh.BrowserWebSocketHandler
    if getattr(H, "_sma_patched", False):
        return True
    orig_open = H.open
    orig_close = H.on_close

    def _open(self, *a, **k):
        try:
            _WS_STATE["count"] += 1
            _WS_STATE["seen"] = True
        except Exception:
            pass
        return orig_open(self, *a, **k)

    def _on_close(self, *a, **k):
        try:
            _WS_STATE["count"] = max(0, _WS_STATE["count"] - 1)
        except Exception:
            pass
        return orig_close(self, *a, **k)

    H.open = _open
    H.on_close = _on_close
    H._sma_patched = True
    return True


def _shutdown_when_no_sessions(port: int = 8501) -> None:
    """Cierra el proceso cuando se cierra la pestaña del navegador.

    Sin consola, al cerrar la pestaña el servidor quedaría corriendo en segundo
    plano. Usamos el contador de websockets vivos (`_WS_STATE`): una vez que se
    abrió al menos una pestaña, si quedan 0 websockets durante un margen (para
    tolerar la breve desconexión de las recargas al cambiar de fase, que reabren
    el websocket enseguida), detenemos el runtime y terminamos el proceso.

    Antes de la primera conexión NO hace nada, así que no se cierra al arrancar.
    """
    _install_ws_counter()
    POLL = 1.0
    GRACE_SECONDS = 6.0  # tolera recargas/navegación entre fases (reconexión rápida)
    empty_for = 0.0

    while True:
        time.sleep(POLL)
        if not _WS_STATE["seen"]:
            continue  # aún no se ha conectado ninguna pestaña
        if _WS_STATE["count"] > 0:
            empty_for = 0.0
        else:
            empty_for += POLL
            if empty_for >= GRACE_SECONDS:
                try:
                    from streamlit.runtime import exists, get_instance
                    if exists():
                        get_instance().stop()
                except Exception:
                    pass
                time.sleep(0.3)
                os._exit(0)
        # Estado INITIAL o NO_SESSIONS_CONNECTED antes de la 1ª conexión: no hacer nada.


def run_app() -> None:
    app_file = resource_path("Inicio.py")

    if not os.path.exists(app_file):
        raise FileNotFoundError(f"No se encontró el archivo principal: {app_file}")

    host = "127.0.0.1"
    port = 8501

    # ── CLAVE anti-FOUC del .exe ──────────────────────────────────────────
    # Streamlit busca `.streamlit/config.toml` en el CWD. En `streamlit run`
    # (VS Code) el CWD es la carpeta del proyecto → encuentra la config y aplica
    # showSidebarNavigation=false, toolbarMode=minimal y el tema DESDE el primer
    # frame. En el .exe el CWD es donde está el ejecutable, NO la carpeta del
    # bundle (`_internal`), así que NO encontraba la config y el primer pintado
    # mostraba el diseño por defecto de Streamlit (el sidebar-nav automático y la
    # barra "Deploy"). Las env vars de cliente NO sustituyen esto (Streamlit las
    # ignora para client.*). Solución: en modo frozen, cambiar el CWD a la carpeta
    # del bundle (que contiene `.streamlit/config.toml`) y re-parsear la config.
    if getattr(sys, "frozen", False):
        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir and os.path.isdir(os.path.join(bundle_dir, ".streamlit")):
            try:
                os.chdir(bundle_dir)
                st_config.get_config_options(force_reparse=True)
            except Exception:
                pass

    # Refuerza configuración en tiempo de ejecución (tras el reparse, para que
    # estos valores ganen). showSidebarNavigation y toolbarMode se fijan también
    # por código: son los que causaban el flash del diseño por defecto.
    st_config.set_option("global.developmentMode", False)
    st_config.set_option("server.headless", True)
    st_config.set_option("server.address", host)
    st_config.set_option("server.port", port)
    st_config.set_option("browser.gatherUsageStats", False)
    st_config.set_option("server.fileWatcherType", "none")
    st_config.set_option("server.runOnSave", False)
    st_config.set_option("runner.magicEnabled", False)
    st_config.set_option("client.toolbarMode", "minimal")
    st_config.set_option("client.showSidebarNavigation", False)
    # Log limpio en producción (el cmd mostraba DEBUG muy verboso). Solo
    # warnings/errores al archivo de log.
    st_config.set_option("logger.level", "warning")

    # Parchear el contador de websockets ANTES de levantar el servidor.
    _install_ws_counter()

    # No abrir el navegador del sistema cuando la carcasa de escritorio
    # (desktop_shell.py) es la dueña de la UI: el server corre como proceso hijo
    # con ALFA_NO_BROWSER=1 y la ventana Qt ya muestra la app. Sin esta guarda
    # saldrían a la vez la ventana de escritorio y una pestaña del navegador.
    if os.environ.get("ALFA_NO_BROWSER") != "1":
        threading.Thread(
            target=open_browser_when_ready,
            args=(host, port),
            daemon=True,
        ).start()

    threading.Thread(
        target=_preload_heavy_modules,
        daemon=True,
    ).start()

    # Vigilante: cierra el .exe cuando se cierra la pestaña del navegador
    # (para que no quede el servidor corriendo en segundo plano sin consola).
    threading.Thread(
        target=_shutdown_when_no_sessions,
        args=(port,),
        daemon=True,
    ).start()

    bootstrap.run(app_file, False, [], {})


if __name__ == "__main__":
    run_app()
