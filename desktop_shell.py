"""
desktop_shell.py — Carcasa de escritorio (PySide6 + Qt WebEngine/Chromium) para la Alfa App.
================================================================================

Envuelve la app Streamlit en una ventana SIN MARCO estilo Discord/Steam, SIN tocar
la capa web: Chromium (el que trae Qt WebEngine) renderiza http://127.0.0.1:8501
EXACTAMENTE igual que hoy. Toda la personalización (barra de título propia, botones,
arrastre, resize, splash, etc.) vive en este archivo. La app Streamlit —Inicio.py,
pages/, navigation.py, assets/style.css, db.py— no se modifica.

Dos roles en un solo archivo, según la variable de entorno ALFA_RUN_SERVER:

  • ALFA_RUN_SERVER=1  → proceso HIJO: arranca el servidor Streamlit reutilizando
    launcher.run_app() (en su propio hilo principal → los signal handlers de
    Streamlit funcionan). No abre el navegador del sistema (ALFA_NO_BROWSER=1).

  • (sin la variable) → proceso PADRE: la carcasa Qt. Lanza al hijo, espera a que
    el servidor responda y muestra la ventana con el QWebEngineView.

Variables de entorno opcionales:
  • ALFA_DEBUG=1  → habilita menú contextual + DevTools remoto (puerto 9222) para
    depurar. En producción (sin la variable) ambos quedan bloqueados.
"""

import os
import sys

HOST = "127.0.0.1"
PORT = 8501
URL = f"http://{HOST}:{PORT}"
APP_TITLE = "SMA 2.0 · Wind Project Analyzer"
SINGLETON_KEY = "AlfaApp_SMA2_singleton_v1"
DEBUG = os.environ.get("ALFA_DEBUG") == "1"


# ──────────────────────────────────────────────────────────────────────────────
# ROL: SERVIDOR (proceso hijo). Se resuelve ANTES de importar Qt, para que el
# hijo nunca cargue PySide6 (solo necesita Streamlit).
# ──────────────────────────────────────────────────────────────────────────────
if os.environ.get("ALFA_RUN_SERVER") == "1":
    import launcher  # importa y arranca Streamlit (ver launcher.run_app)

    launcher.run_app()
    sys.exit(0)


# ──────────────────────────────────────────────────────────────────────────────
# ROL: CARCASA (proceso padre). A partir de aquí sí importamos Qt.
# ──────────────────────────────────────────────────────────────────────────────
import json
import socket
import subprocess
import time
from pathlib import Path

# DevTools remoto: debe fijarse ANTES de crear el QApplication.
if DEBUG:
    os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9222")

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWebEngineCore import (
    QWebEngineDownloadRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineSettings,
    qWebEngineChromiumVersion,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

# ── Paleta (tema CLARO, combina con la app) ───────────────────────────────────
COL_BG = "#F5F9FF"          # fondo app (igual que .streamlit/config.toml)
COL_TITLEBAR = "#FFFFFF"    # barra de título
COL_PRIMARY = "#2563eb"     # azul primario
COL_NAVY = "#0b2a5b"        # títulos navy
COL_BORDER = "#cbd5e1"      # borde sutil
COL_HOVER = "#eff6ff"       # hover botones
COL_TEXT = "#0F172A"
COL_CLOSE_HOVER = "#dc2626"  # rojo cierre

# ── Paletas de tema de la CARCASA. La app arranca en CLARO; el botón ☾/☀ alterna. ──
LIGHT = {
    "bg": COL_BG, "titlebar": COL_TITLEBAR, "text": COL_NAVY,
    "border": COL_BORDER, "hover": COL_HOVER, "icon": COL_NAVY, "page": COL_BG,
    "sub": "#64748b",
}
DARK = {
    "bg": "#0e1117", "titlebar": "#161b22", "text": "#e6edf3",
    "border": "#30363d", "hover": "#21262d", "icon": "#c9d1d9", "page": "#0e1117",
    "sub": "#8b949e",
}

# Modo oscuro del CONTENIDO web SIN tocar el CSS de la app: filtro "invert + hue-rotate"
# a nivel de página (preserva los tonos), recontra-invirtiendo imágenes/gráficas/mapas
# para que NO se vean invertidos. Es un overlay del navegador, 100% reversible.
_DARK_CSS = (
    "html{filter:invert(1) hue-rotate(180deg) !important;background:#0e1117 !important;}"
    "img,video,canvas,[data-testid='stImage'] img,.js-plotly-plot,.stPlotlyChart,"
    "[data-testid='stPlotlyChart'],iframe,[style*='background-image']"
    "{filter:invert(1) hue-rotate(180deg) !important;}"
)
_DARK_JS_ON = (
    '(function(){var I="__alfa_dark__";var e=document.getElementById(I);'
    'if(!e){e=document.createElement("style");e.id=I;'
    '(document.head||document.documentElement).appendChild(e);}'
    'e.textContent="' + _DARK_CSS + '";})();'
)
_DARK_JS_OFF = "(function(){var e=document.getElementById('__alfa_dark__');if(e)e.remove();})();"

TITLEBAR_H = 40
GRIP = 6            # grosor de las zonas de resize en el borde
MIN_W, MIN_H = 1024, 660

# Pasos de zoom (factor). 1.0 = 100%. Igual filosofía que un navegador.
ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5]


def _appdata_dir() -> Path:
    """Carpeta %LOCALAPPDATA%/AppEolica (misma que usan los logs en launcher.py)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    d = (Path(base) / "AppEolica") if base else (Path.home() / "AppEolica")
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


WINDOW_STATE_FILE = _appdata_dir() / "window_state.json"


def _shell_dir() -> Path:
    """Carpeta del bundle (frozen) o del script (dev)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _app_icon() -> QIcon:
    """Icono de la app: assets/app.ico si existe, si no uno generado."""
    ico = _shell_dir() / "assets" / "app.ico"
    if ico.is_file():
        return QIcon(str(ico))
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(COL_PRIMARY))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(6, 6, 52, 52, 14, 14)
    p.setPen(QColor("#ffffff"))
    f = QFont()
    f.setBold(True)
    f.setPointSize(26)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "α")
    p.end()
    return QIcon(pix)


def _magnifier_pixmap(size: int = 16, color: str = COL_NAVY) -> QPixmap:
    """Dibuja una lupa monocroma (lente + mango) crujiente a cualquier tamaño."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    d = int(size * 0.58)
    p.drawEllipse(2, 2, d, d)                       # lente
    p.drawLine(d, d, size - 2, size - 2)            # mango
    p.end()
    return pix


def _wait_for_server(host: str, port: int, timeout: float = 1.0) -> bool:
    """¿Responde ya el servidor? (un intento, no bloqueante para el event loop)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Página web: abre enlaces EXTERNOS en el navegador del sistema (no dentro de la
# app), y deja la navegación interna (127.0.0.1) intacta.
# ──────────────────────────────────────────────────────────────────────────────
class _WebPage(QWebEnginePage):
    def _is_internal(self, url: QUrl) -> bool:
        if url.scheme() in ("", "data", "blob", "about", "chrome", "file"):
            return True
        return url.host() in ("127.0.0.1", "localhost", "")

    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame) -> bool:  # noqa: N802
        if url.scheme() in ("http", "https") and not self._is_internal(url):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _wtype):  # noqa: N802
        # Enlaces target=_blank / window.open(): capturar la URL y abrirla fuera.
        holder = QWebEnginePage(self.profile(), self)

        def _open(url: QUrl):
            if url.isValid() and url.scheme() in ("http", "https") and not self._is_internal(url):
                QDesktopServices.openUrl(url)
            holder.deleteLater()

        holder.urlChanged.connect(_open)
        return holder


# ──────────────────────────────────────────────────────────────────────────────
# Botón de la barra de título (estilo limpio + hover; cierre en rojo).
# ──────────────────────────────────────────────────────────────────────────────
class _CaptionButton(QPushButton):
    def __init__(self, glyph: str, *, danger: bool = False, width: int = 46, parent=None):
        super().__init__(glyph, parent)
        self._danger = danger
        self.setFixedSize(width, TITLEBAR_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_theme(LIGHT)

    def apply_theme(self, pal: dict) -> None:
        hover_bg = COL_CLOSE_HOVER if self._danger else pal["hover"]
        hover_fg = "#ffffff" if self._danger else pal["text"]
        self.setStyleSheet(
            f"""
            QPushButton {{
                border: none; background: transparent; color: {pal["text"]};
                font-size: 14px; font-family: 'Segoe UI', sans-serif;
            }}
            QPushButton:hover {{ background: {hover_bg}; color: {hover_fg}; }}
            QPushButton:pressed {{ background: {hover_bg}; }}
            """
        )


# ──────────────────────────────────────────────────────────────────────────────
# Barra de título propia: logo + título + min/max/cerrar. Arrastre nativo
# (startSystemMove → Aero Snap incluido) y doble-clic = maximizar/restaurar.
# ──────────────────────────────────────────────────────────────────────────────
class _TitleBar(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self._win = window
        self.setFixedHeight(TITLEBAR_H)
        self.setObjectName("titlebar")
        self.setStyleSheet(
            f"#titlebar {{ background: {COL_TITLEBAR}; border-bottom: 1px solid {COL_BORDER}; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(8)

        logo = QLabel(self)
        logo.setPixmap(_app_icon().pixmap(18, 18))
        logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(logo)

        self._title = QLabel(APP_TITLE, self)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._title.setStyleSheet(
            f"color:{COL_NAVY}; font-size:13px; font-weight:600; font-family:'Segoe UI',sans-serif;"
        )
        lay.addWidget(self._title)
        lay.addStretch(1)

        # ── Control de zoom: lupa + alejar + porcentaje + acercar ──
        self._zoom_icon = QLabel(self)
        self._zoom_icon.setPixmap(_magnifier_pixmap(16))
        self._zoom_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._zoom_icon.setContentsMargins(6, 0, 2, 0)
        lay.addWidget(self._zoom_icon)

        self._btn_zoom_out = _CaptionButton("−", width=30, parent=self)
        self._btn_zoom_out.setToolTip("Alejar (Ctrl −)")
        self._btn_zoom_out.clicked.connect(window.zoom_out)
        self._btn_zoom_pct = _CaptionButton("100 %", width=58, parent=self)
        self._btn_zoom_pct.setToolTip("Restablecer zoom (Ctrl 0)")
        self._btn_zoom_pct.clicked.connect(window.zoom_reset)
        self._btn_zoom_in = _CaptionButton("+", width=30, parent=self)
        self._btn_zoom_in.setToolTip("Acercar (Ctrl +)")
        self._btn_zoom_in.clicked.connect(window.zoom_in)
        for b in (self._btn_zoom_out, self._btn_zoom_pct, self._btn_zoom_in):
            lay.addWidget(b)

        sep = QLabel(self)
        sep.setFixedWidth(10)
        sep.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(sep)

        # ── Alternar modo claro/oscuro ──
        self._btn_theme = _CaptionButton("☾", parent=self)   # ☾ luna / ☀ sol
        self._btn_theme.setToolTip("Modo oscuro")
        self._btn_theme.clicked.connect(window.toggle_theme)
        lay.addWidget(self._btn_theme)

        self._btn_about = _CaptionButton("ℹ", parent=self)   # ℹ
        self._btn_about.setToolTip("Acerca de")
        self._btn_about.clicked.connect(window.show_about)
        self._btn_min = _CaptionButton("—", parent=self)     # —
        self._btn_min.setToolTip("Minimizar")
        self._btn_min.clicked.connect(window.showMinimized)
        self._btn_max = _CaptionButton("□", parent=self)     # □
        self._btn_max.setToolTip("Maximizar")
        self._btn_max.clicked.connect(window.toggle_max_restore)
        self._btn_close = _CaptionButton("✕", danger=True, parent=self)  # ✕
        self._btn_close.setToolTip("Cerrar")
        self._btn_close.clicked.connect(window.close)

        for b in (self._btn_about, self._btn_min, self._btn_max, self._btn_close):
            lay.addWidget(b)

    def sync_max_glyph(self, is_max: bool) -> None:
        self._btn_max.setText("❐" if is_max else "□")  # ❐ / □
        self._btn_max.setToolTip("Restaurar" if is_max else "Maximizar")

    def update_zoom_label(self, pct: int) -> None:
        self._btn_zoom_pct.setText(f"{pct} %")

    def apply_theme(self, pal: dict, dark: bool) -> None:
        self.setStyleSheet(
            f"#titlebar {{ background: {pal['titlebar']}; border-bottom: 1px solid {pal['border']}; }}"
        )
        self._title.setStyleSheet(
            f"color:{pal['text']}; font-size:13px; font-weight:600; font-family:'Segoe UI',sans-serif;"
        )
        self._zoom_icon.setPixmap(_magnifier_pixmap(16, pal["icon"]))
        for b in (self._btn_zoom_out, self._btn_zoom_pct, self._btn_zoom_in,
                  self._btn_theme, self._btn_about, self._btn_min,
                  self._btn_max, self._btn_close):
            b.apply_theme(pal)
        self._btn_theme.setText("☀" if dark else "☾")
        self._btn_theme.setToolTip("Modo claro" if dark else "Modo oscuro")

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemMove()  # arrastre nativo (incluye Aero Snap)
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._win.toggle_max_restore()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


# ──────────────────────────────────────────────────────────────────────────────
# Asas de resize: 8 widgets finos por encima del web view. Usan
# startSystemResize → resize nativo (Windows hace el hit-testing por nosotros),
# así funciona aunque el cursor esté sobre el área del navegador.
# ──────────────────────────────────────────────────────────────────────────────
class _ResizeGrip(QWidget):
    def __init__(self, window: "MainWindow", edges: Qt.Edge, cursor: Qt.CursorShape):
        super().__init__(window)
        self._win = window
        self._edges = edges
        self.setCursor(cursor)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and not self._win.isMaximized():
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemResize(self._edges)
                e.accept()
                return
        super().mousePressEvent(e)


# ──────────────────────────────────────────────────────────────────────────────
# Diálogo "Acerca de" (frameless, tema claro).
# ──────────────────────────────────────────────────────────────────────────────
class _AboutDialog(QDialog):
    def __init__(self, parent=None, dark: bool = False):
        super().__init__(parent)
        pal = DARK if dark else LIGHT
        self.setWindowTitle("Acerca de")
        self.setFixedSize(420, 220)
        self.setStyleSheet(f"background:{pal['bg']};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(8)

        h = QLabel(APP_TITLE, self)
        h.setStyleSheet(f"color:{pal['text']}; font-size:18px; font-weight:800;")
        lay.addWidget(h)

        info = QLabel(
            "Aplicación para cálculos de parques eólicos.\n\n"
            f"Motor: Qt WebEngine (Chromium {qWebEngineChromiumVersion()})\n"
            "Interfaz: Streamlit",
            self,
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{pal['sub']}; font-size:13px;")
        lay.addWidget(info)
        lay.addStretch(1)

        ok = QPushButton("Cerrar", self)
        ok.setFixedHeight(34)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(
            f"QPushButton{{background:{COL_PRIMARY};color:#fff;border:none;border-radius:8px;"
            f"font-weight:600;padding:0 18px;}} QPushButton:hover{{background:#1d4ed8;}}"
        )
        ok.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(ok)
        lay.addLayout(row)


# ──────────────────────────────────────────────────────────────────────────────
# Ventana principal frameless.
# ──────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, server_proc):
        super().__init__()
        self._proc = server_proc
        self._stopped = False
        self._zoom = 1.0
        self._dark = False

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(MIN_W, MIN_H)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        central = QWidget(self)
        central.setObjectName("central")
        central.setStyleSheet(
            f"#central {{ background:{COL_BG}; border:1px solid {COL_BORDER}; }}"
        )
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = _TitleBar(self)
        root.addWidget(self.titlebar)

        # ── Perfil persistente: cachea en disco los assets estáticos de Streamlit
        #    (su bundle JS + Plotly, varios MB) entre lanzamientos → los arranques
        #    siguientes cargan bastante más rápido. Sin esto, cada inicio rebaja
        #    todo de nuevo. ──
        self._profile = QWebEngineProfile("AlfaApp", self)
        try:
            self._profile.setCachePath(str(_appdata_dir() / "webcache"))
            self._profile.setPersistentStoragePath(str(_appdata_dir() / "webstore"))
            self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
            self._profile.setHttpCacheMaximumSize(256 * 1024 * 1024)
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
            )
            self._profile.setSpellCheckEnabled(False)  # no se usa → menos trabajo
        except Exception:
            pass

        # ── Web view + página con Chromium incrustado ──
        self.view = QWebEngineView(self)
        self.page = _WebPage(self._profile, self.view)
        self.view.setPage(self.page)
        self.page.setBackgroundColor(QColor(COL_BG))  # evita flash blanco
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if not DEBUG:
            self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        # Ajustes seguros del motor: apaga lo que la app no usa (plugins, visor PDF,
        # captura de pantalla) y suaviza el scroll.
        try:
            s = self.view.settings()
            W = QWebEngineSettings.WebAttribute
            s.setAttribute(W.PluginsEnabled, False)
            s.setAttribute(W.PdfViewerEnabled, False)
            s.setAttribute(W.ScreenCaptureEnabled, False)
            s.setAttribute(W.ScrollAnimatorEnabled, True)
        except Exception:
            pass

        root.addWidget(self.view, 1)

        # Descargas (st.download_button → Word/Excel/PDF/KML). Sin esto se pierden.
        self._profile.downloadRequested.connect(self._on_download)

        # Reaplicar el zoom guardado tras cada carga (las navegaciones de Streamlit
        # recargan la página).
        self.view.loadFinished.connect(self._reapply_zoom)

        # Atajos de teclado de zoom (Ctrl +/−/0), activos tenga foco quien tenga.
        for seq, fn in (
            (QKeySequence.StandardKey.ZoomIn, self.zoom_in),
            (QKeySequence.StandardKey.ZoomOut, self.zoom_out),
            (QKeySequence("Ctrl+="), self.zoom_in),
            (QKeySequence("Ctrl+0"), self.zoom_reset),
        ):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)

        # ── Asas de resize (encima del web view) ──
        E = Qt.Edge
        C = Qt.CursorShape
        self._grips = [
            _ResizeGrip(self, E.LeftEdge, C.SizeHorCursor),
            _ResizeGrip(self, E.RightEdge, C.SizeHorCursor),
            _ResizeGrip(self, E.TopEdge, C.SizeVerCursor),
            _ResizeGrip(self, E.BottomEdge, C.SizeVerCursor),
            _ResizeGrip(self, E.LeftEdge | E.TopEdge, C.SizeFDiagCursor),
            _ResizeGrip(self, E.RightEdge | E.BottomEdge, C.SizeFDiagCursor),
            _ResizeGrip(self, E.RightEdge | E.TopEdge, C.SizeBDiagCursor),
            _ResizeGrip(self, E.LeftEdge | E.BottomEdge, C.SizeBDiagCursor),
        ]
        for g in self._grips:
            g.raise_()

        self._start_maximized = False
        self._restore_window_state()
        self.apply_theme()  # aplica claro/oscuro según lo guardado

    # ── Cargar la URL del servidor ──
    def load_app(self) -> None:
        self.view.setUrl(QUrl(URL))

    def apply_initial_show(self) -> None:
        """Mostrar la ventana por primera vez (tras cargar), respetando maximizado."""
        if self._start_maximized:
            self.showMaximized()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    # ── Zoom ──
    def _apply_zoom(self, factor: float) -> None:
        factor = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], factor))
        self._zoom = factor
        self.view.setZoomFactor(factor)
        self.titlebar.update_zoom_label(round(factor * 100))

    def zoom_in(self) -> None:
        self._apply_zoom(next((z for z in ZOOM_STEPS if z > self._zoom + 1e-3), ZOOM_STEPS[-1]))

    def zoom_out(self) -> None:
        self._apply_zoom(next((z for z in reversed(ZOOM_STEPS) if z < self._zoom - 1e-3), ZOOM_STEPS[0]))

    def zoom_reset(self) -> None:
        self._apply_zoom(1.0)

    def _reapply_zoom(self, ok: bool) -> None:
        if ok:
            self.view.setZoomFactor(self._zoom)

    # ── Tema claro / oscuro ──
    def apply_theme(self) -> None:
        pal = DARK if self._dark else LIGHT
        self.centralWidget().setStyleSheet(
            f"#central {{ background:{pal['bg']}; border:1px solid {pal['border']}; }}"
        )
        self.titlebar.apply_theme(pal, self._dark)
        try:
            self.page.setBackgroundColor(QColor(pal["page"]))
        except Exception:
            pass
        self._apply_content_filter()

    def toggle_theme(self) -> None:
        self._dark = not self._dark
        self.apply_theme()

    def _apply_content_filter(self) -> None:
        """Oscurece/aclara el CONTENIDO web sin tocar su CSS. Un QWebEngineScript
        persistente reaplica el filtro en cada navegación de Streamlit; además se
        aplica al instante sobre la página actual."""
        try:
            coll = self._profile.scripts()
            for s in coll.find("alfa-dark"):
                coll.remove(s)
            if self._dark:
                sc = QWebEngineScript()
                sc.setName("alfa-dark")
                sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
                sc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
                sc.setRunsOnSubFrames(False)
                sc.setSourceCode(_DARK_JS_ON)
                coll.insert(sc)
        except Exception:
            pass
        try:
            self.page.runJavaScript(_DARK_JS_ON if self._dark else _DARK_JS_OFF)
        except Exception:
            pass

    # ── Resize: reposicionar las asas ──
    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        w, h, m = self.width(), self.height(), GRIP
        show = not self.isMaximized()
        rects = [
            QRect(0, m, m, h - 2 * m),              # left
            QRect(w - m, m, m, h - 2 * m),          # right
            QRect(m, 0, w - 2 * m, m),              # top
            QRect(m, h - m, w - 2 * m, m),          # bottom
            QRect(0, 0, m, m),                      # top-left
            QRect(w - m, h - m, m, m),              # bottom-right
            QRect(w - m, 0, m, m),                  # top-right
            QRect(0, h - m, m, m),                  # bottom-left
        ]
        for g, r in zip(self._grips, rects):
            g.setGeometry(r)
            g.setVisible(show)
            g.raise_()

    # ── Maximizar / restaurar ──
    def toggle_max_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, e):  # noqa: N802
        super().changeEvent(e)
        if not hasattr(self, "_grips"):
            return
        is_max = self.isMaximized()
        self.titlebar.sync_max_glyph(is_max)
        for g in self._grips:
            g.setVisible(not is_max)

    # ── Descargas → "Guardar como" ──
    def _on_download(self, dl: QWebEngineDownloadRequest) -> None:
        suggested = dl.suggestedFileName() or "descarga"
        start_dir = str(Path.home() / "Downloads" / suggested)
        path, _ = QFileDialog.getSaveFileName(self, "Guardar como", start_dir)
        if not path:
            dl.cancel()
            return
        p = Path(path)
        dl.setDownloadDirectory(str(p.parent))
        dl.setDownloadFileName(p.name)
        dl.accept()

    # ── Acerca de ──
    def show_about(self) -> None:
        _AboutDialog(self, self._dark).exec()

    # ── Estado de ventana (Deluxe): guardar/restaurar ──
    def _restore_window_state(self) -> None:
        try:
            data = json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        rect = None
        try:
            rect = QRect(int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))
        except Exception:
            rect = None

        if rect and rect.width() >= MIN_W and rect.height() >= MIN_H and self._on_some_screen(rect):
            self.setGeometry(rect)
        else:
            self.resize(1280, 820)
            self._center_on_primary()

        self._start_maximized = bool(data.get("maximized"))

        try:
            self._zoom = max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], float(data.get("zoom", 1.0))))
        except Exception:
            self._zoom = 1.0
        self.titlebar.update_zoom_label(round(self._zoom * 100))

        self._dark = bool(data.get("dark", False))

    def _on_some_screen(self, rect: QRect) -> bool:
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().intersects(rect):
                return True
        return False

    def _center_on_primary(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        avail = screen.availableGeometry()
        self.move(
            avail.x() + (avail.width() - self.width()) // 2,
            avail.y() + (avail.height() - self.height()) // 2,
        )

    def _save_window_state(self) -> None:
        try:
            g = self.normalGeometry()  # geometría NO maximizada
            payload = {
                "x": g.x(), "y": g.y(), "w": g.width(), "h": g.height(),
                "maximized": self.isMaximized(),
                "zoom": self._zoom,
                "dark": self._dark,
            }
            WINDOW_STATE_FILE.write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    # ── Cierre limpio: guardar estado + matar el servidor hijo ──
    def _stop_server(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        proc = self._proc
        if not proc or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                else:
                    proc.kill()
            except Exception:
                pass

    def closeEvent(self, e):  # noqa: N802
        self._save_window_state()
        self._stop_server()
        super().closeEvent(e)


# ──────────────────────────────────────────────────────────────────────────────
# Lanzar el proceso hijo del servidor Streamlit.
# ──────────────────────────────────────────────────────────────────────────────
def _start_server_process() -> subprocess.Popen:
    env = {**os.environ, "ALFA_RUN_SERVER": "1", "ALFA_NO_BROWSER": "1"}
    if getattr(sys, "frozen", False):
        args = [sys.executable]  # el propio .exe se re-ejecuta en modo servidor
    else:
        args = [sys.executable, os.path.abspath(__file__)]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, env=env, creationflags=creationflags)


# ──────────────────────────────────────────────────────────────────────────────
# Splash de arranque (respeta el tema guardado: claro u oscuro).
# ──────────────────────────────────────────────────────────────────────────────
def _saved_dark() -> bool:
    """Lee el tema persistido (para que el splash arranque ya en el color correcto)."""
    try:
        return bool(json.loads(WINDOW_STATE_FILE.read_text(encoding="utf-8")).get("dark", False))
    except Exception:
        return False


def _make_splash(dark: bool = False) -> QSplashScreen:
    pal = DARK if dark else LIGHT
    pix = QPixmap(440, 240)
    pix.fill(QColor(pal["bg"]))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(pal["border"]))
    p.drawRoundedRect(0, 0, 440, 240, 18, 18)
    p.setBrush(QColor(pal["titlebar"]))
    p.drawRoundedRect(1, 1, 438, 238, 17, 17)
    # logo
    p.setBrush(QColor(COL_PRIMARY))
    p.drawRoundedRect(186, 56, 68, 68, 18, 18)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI")
    f.setBold(True)
    f.setPointSize(30)
    p.setFont(f)
    p.drawText(QRect(186, 56, 68, 68), Qt.AlignmentFlag.AlignCenter, "α")
    # título
    p.setPen(QColor(pal["text"]))
    f.setPointSize(15)
    p.setFont(f)
    p.drawText(QRect(0, 140, 440, 26), Qt.AlignmentFlag.AlignCenter, "SMA 2.0")
    p.setPen(QColor(pal["sub"]))
    f.setBold(False)
    f.setPointSize(10)
    p.setFont(f)
    p.drawText(QRect(0, 172, 440, 22), Qt.AlignmentFlag.AlignCenter, "Iniciando aplicación…")
    p.end()
    splash = QSplashScreen(pix)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return splash


# ──────────────────────────────────────────────────────────────────────────────
# Punto de entrada de la carcasa.
# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    # Flags de Chromium (deben fijarse ANTES de crear el QApplication). Conservadoras
    # por defecto; con ALFA_GPU=1 se fuerza rasterización por GPU (útil si tu tarjeta
    # está en la blocklist de Chromium y el render va lento por software).
    _flags = "--disable-features=Translate"
    if os.environ.get("ALFA_GPU") == "1":
        _flags += " --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy"
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", _flags)

    # Recomendado para QtWebEngine (debe ir antes de crear el QApplication).
    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Alfa App")
    app.setWindowIcon(_app_icon())

    # Agrupar correctamente en la barra de tareas de Windows.
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AlfaApp.SMA2")
        except Exception:
            pass

    # ── Instancia única (Deluxe): si ya hay una abierta, enfocarla y salir ──
    probe = QLocalSocket()
    probe.connectToServer(SINGLETON_KEY)
    if probe.waitForConnected(250):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(250)
        probe.disconnectFromServer()
        return 0
    QLocalServer.removeServer(SINGLETON_KEY)
    local_server = QLocalServer()
    local_server.listen(SINGLETON_KEY)

    splash = _make_splash(_saved_dark())
    splash.show()
    app.processEvents()

    # Lanzar el servidor Streamlit (proceso hijo).
    server_proc = _start_server_process()

    window = MainWindow(server_proc)

    # Al recibir una conexión de una 2ª instancia → traer la ventana al frente.
    def _on_new_connection():
        conn = local_server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(conn.deleteLater)
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()

    local_server.newConnection.connect(_on_new_connection)

    # Cuando termine la primera carga del web view → cerrar splash y mostrar ventana.
    def _on_load(ok: bool):
        if state.get("shown"):
            return
        if not ok:
            QTimer.singleShot(600, window.load_app)  # reintento corto
            return
        state["shown"] = True
        splash.finish(window)
        window.apply_initial_show()

    window.view.loadFinished.connect(_on_load)

    # Esperar a que el servidor responda y entonces cargar la URL (no bloqueante).
    state = {"elapsed": 0.0, "loaded": False, "shown": False}

    def _poll():
        if state["loaded"]:
            return
        if _wait_for_server(HOST, PORT, timeout=0.3):
            state["loaded"] = True
            window.load_app()
            poll_timer.stop()
            return
        state["elapsed"] += 0.15
        if state["elapsed"] > 40.0:  # ~40 s sin servidor → abortar
            poll_timer.stop()
            splash.close()
            window._stop_server()
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(
                None,
                "Alfa App",
                "No se pudo iniciar el servidor de la aplicación.\n"
                f"Revisa el log en:\n{_appdata_dir() / 'app_log.txt'}",
            )
            app.quit()

    poll_timer = QTimer()
    poll_timer.timeout.connect(_poll)
    poll_timer.start(150)

    # Salvaguarda al salir.
    app.aboutToQuit.connect(window._stop_server)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
