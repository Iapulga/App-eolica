"""
desktop_shell.py — Carcasa de escritorio (PySide6 + Qt WebEngine) para SMA 2.0.
================================================================================

Envuelve la app Streamlit en una ventana SIN MARCO (frameless) estilo Discord /
Steam. Chromium (el que trae Qt WebEngine) renderiza http://127.0.0.1:8501 igual
que en el navegador; TODA la carcasa (barra de título propia, botones, arrastre,
resize, zoom, modo oscuro, splash, instancia única, estado de ventana) vive en
ESTE archivo. La capa web de la app —Inicio.py, pages/, navigation.py,
assets/style.css, db.py— NO se toca.

Dos roles en un mismo archivo según la variable de entorno ALFA_RUN_SERVER:

  • ALFA_RUN_SERVER=1  → PROCESO HIJO. Arranca el servidor Streamlit reutilizando
    launcher.run_app(), en su propio hilo principal (los signal handlers de
    Streamlit solo funcionan ahí). No abre el navegador del sistema
    (ALFA_NO_BROWSER=1).

  • (sin la variable) → PROCESO PADRE. Es la carcasa Qt: lanza al hijo, espera
    con un poll NO bloqueante a que el puerto responda y muestra la ventana con
    el QWebEngineView.

Variables de entorno opcionales:
  • ALFA_DEBUG=1 → menú contextual + DevTools remoto (puerto 9222) para depurar.
  • ALFA_GPU=1   → fuerza rasterización por GPU (útil si el render por software
    va lento porque tu tarjeta está en la blocklist de Chromium).
"""

import os
import sys

# ── Constantes de contrato (las usa el resto del build: NO cambiar) ────────────
HOST = "127.0.0.1"
PORT = 8501
URL = f"http://{HOST}:{PORT}"
APP_TITLE = "SMA 2.0 · Wind Project Analyzer"
APP_NAME = "Alfa App"
APPDATA_SUBDIR = "AppEolica"
SINGLETON_KEY = "AlfaApp_SMA2_singleton_v1"
APP_USER_MODEL_ID = "AlfaApp.SMA2"
DEBUG = os.environ.get("ALFA_DEBUG") == "1"


# ──────────────────────────────────────────────────────────────────────────────
# ROL SERVIDOR (proceso hijo). Se resuelve ANTES de importar Qt: el hijo solo
# necesita Streamlit y nunca debe cargar PySide6.
# ──────────────────────────────────────────────────────────────────────────────
if os.environ.get("ALFA_RUN_SERVER") == "1":
    import launcher

    launcher.run_app()
    sys.exit(0)


# ──────────────────────────────────────────────────────────────────────────────
# ROL CARCASA (proceso padre). A partir de aquí sí cargamos Qt.
# ──────────────────────────────────────────────────────────────────────────────
import json
import socket
import subprocess
from pathlib import Path

# DevTools remoto: debe fijarse ANTES de crear el QApplication.
if DEBUG:
    os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "9222")

from PySide6.QtCore import QRect, Qt, QTimer, QUrl
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
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

# ── Paletas de tema (la app arranca en CLARO; el botón ☾/☀ alterna a oscuro) ───
LIGHT = {
    "bg": "#F5F9FF", "titlebar": "#FFFFFF", "text": "#0b2a5b",
    "sub": "#64748b", "border": "#cbd5e1", "hover": "#eff6ff",
    "icon": "#0b2a5b", "page": "#F5F9FF",
}
DARK = {
    "bg": "#0e1117", "titlebar": "#161b22", "text": "#e6edf3",
    "sub": "#8b949e", "border": "#30363d", "hover": "#21262d",
    "icon": "#c9d1d9", "page": "#0e1117",
}
ACCENT = "#2563eb"        # azul primario (= .streamlit/config.toml)
ACCENT_HOVER = "#1d4ed8"
CLOSE_HOVER = "#dc2626"   # rojo del botón cerrar

TITLEBAR_H = 40
GRIP = 6                  # grosor de las asas de resize
MIN_W, MIN_H = 1024, 660
ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5]

# Modo oscuro del CONTENIDO web sin tocar el CSS de la app: filtro "invert +
# hue-rotate" a nivel de página (preserva tonos), re-invirtiendo imágenes /
# gráficas / mapas para que NO se vean al revés. Overlay del navegador, 100%
# reversible.
_DARK_CSS = (
    "html{filter:invert(1) hue-rotate(180deg)!important;background:#0e1117!important;}"
    "img,video,canvas,[data-testid='stImage'] img,.js-plotly-plot,.stPlotlyChart,"
    "[data-testid='stPlotlyChart'],iframe,[style*='background-image']"
    "{filter:invert(1) hue-rotate(180deg)!important;}"
)
_DARK_ON = (
    '(function(){var i="__sma_dark__",e=document.getElementById(i);'
    'if(!e){e=document.createElement("style");e.id=i;'
    '(document.head||document.documentElement).appendChild(e);}'
    "e.textContent=" + json.dumps(_DARK_CSS) + ";})();"
)
_DARK_OFF = "(function(){var e=document.getElementById('__sma_dark__');if(e)e.remove();})();"


# ── Helpers de rutas / estado ──────────────────────────────────────────────────
def _appdata_dir() -> Path:
    """%LOCALAPPDATA%/AppEolica (misma carpeta que usan los logs de launcher.py)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    d = (Path(base) / APPDATA_SUBDIR) if base else (Path.home() / APPDATA_SUBDIR)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


STATE_FILE = _appdata_dir() / "window_state.json"


def _shell_dir() -> Path:
    """Carpeta del bundle (frozen) o del script (dev)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _app_icon() -> QIcon:
    """Icono de la app: assets/app.ico si existe; si no, uno generado ('α')."""
    ico = _shell_dir() / "assets" / "app.ico"
    if ico.is_file():
        return QIcon(str(ico))
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(6, 6, 52, 52, 14, 14)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI")
    f.setBold(True)
    f.setPointSize(26)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "α")
    p.end()
    return QIcon(pix)


def _magnifier(size: int = 16, color: str = "#0b2a5b") -> QPixmap:
    """Lupa monocroma (lente + mango) nítida a cualquier tamaño."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    d = int(size * 0.58)
    p.drawEllipse(2, 2, d, d)
    p.drawLine(d, d, size - 2, size - 2)
    p.end()
    return pix


def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """Un intento de conexión (no bloquea el event loop de Qt)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Página web: navegación interna (127.0.0.1) dentro de la app; enlaces externos
# al navegador del sistema.
# ──────────────────────────────────────────────────────────────────────────────
class _WebPage(QWebEnginePage):
    @staticmethod
    def _internal(url: QUrl) -> bool:
        if url.scheme() in ("", "data", "blob", "about", "chrome", "file"):
            return True
        return url.host() in ("127.0.0.1", "localhost", "")

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
        if url.scheme() in ("http", "https") and not self._internal(url):
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    def createWindow(self, _wtype):  # noqa: N802
        # target=_blank / window.open(): capturar la URL y abrirla fuera.
        sink = QWebEnginePage(self.profile(), self)

        def _open(url: QUrl):
            if url.isValid() and url.scheme() in ("http", "https") and not self._internal(url):
                QDesktopServices.openUrl(url)
            sink.deleteLater()

        sink.urlChanged.connect(_open)
        return sink


# ──────────────────────────────────────────────────────────────────────────────
# Botón de la barra de título (transparente + hover; cierre en rojo).
# ──────────────────────────────────────────────────────────────────────────────
class _CaptionButton(QPushButton):
    def __init__(self, glyph: str, *, width: int = 46, danger: bool = False, parent=None):
        super().__init__(glyph, parent)
        self._danger = danger
        self.setFixedSize(width, TITLEBAR_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_theme(LIGHT)

    def apply_theme(self, pal: dict) -> None:
        hover_bg = CLOSE_HOVER if self._danger else pal["hover"]
        hover_fg = "#ffffff" if self._danger else pal["text"]
        self.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;color:{pal['text']};"
            f"font-size:14px;font-family:'Segoe UI',sans-serif;}}"
            f"QPushButton:hover{{background:{hover_bg};color:{hover_fg};}}"
            f"QPushButton:pressed{{background:{hover_bg};}}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Barra de título propia: logo + título + zoom + tema + acerca + min/max/cerrar.
# Arrastre nativo (startSystemMove → Aero Snap incluido); doble-clic = maximizar.
# ──────────────────────────────────────────────────────────────────────────────
class _TitleBar(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self._win = win
        self.setFixedHeight(TITLEBAR_H)
        self.setObjectName("titlebar")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(6)

        self._logo = QLabel(self)
        self._logo.setPixmap(_app_icon().pixmap(18, 18))
        self._logo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._logo)

        self._title = QLabel(APP_TITLE, self)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self._title)
        lay.addStretch(1)

        # Zoom: lupa + alejar + porcentaje + acercar.
        self._zoom_icon = QLabel(self)
        self._zoom_icon.setPixmap(_magnifier(16))
        self._zoom_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._zoom_icon.setContentsMargins(6, 0, 2, 0)
        lay.addWidget(self._zoom_icon)

        self._b_zoom_out = _CaptionButton("−", width=30, parent=self)
        self._b_zoom_out.setToolTip("Alejar (Ctrl −)")
        self._b_zoom_out.clicked.connect(win.zoom_out)
        self._b_zoom_pct = _CaptionButton("100 %", width=58, parent=self)
        self._b_zoom_pct.setToolTip("Restablecer zoom (Ctrl 0)")
        self._b_zoom_pct.clicked.connect(win.zoom_reset)
        self._b_zoom_in = _CaptionButton("+", width=30, parent=self)
        self._b_zoom_in.setToolTip("Acercar (Ctrl +)")
        self._b_zoom_in.clicked.connect(win.zoom_in)
        for b in (self._b_zoom_out, self._b_zoom_pct, self._b_zoom_in):
            lay.addWidget(b)

        sep = QLabel(self)
        sep.setFixedWidth(8)
        sep.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(sep)

        # Tema, acerca de, y controles de ventana.
        self._b_theme = _CaptionButton("☾", parent=self)
        self._b_theme.setToolTip("Modo oscuro")
        self._b_theme.clicked.connect(win.toggle_theme)
        self._b_about = _CaptionButton("ℹ", parent=self)
        self._b_about.setToolTip("Acerca de")
        self._b_about.clicked.connect(win.show_about)
        self._b_min = _CaptionButton("—", parent=self)
        self._b_min.setToolTip("Minimizar")
        self._b_min.clicked.connect(win.showMinimized)
        self._b_max = _CaptionButton("□", parent=self)
        self._b_max.setToolTip("Maximizar")
        self._b_max.clicked.connect(win.toggle_max_restore)
        self._b_close = _CaptionButton("✕", danger=True, parent=self)
        self._b_close.setToolTip("Cerrar")
        self._b_close.clicked.connect(win.close)
        for b in (self._b_theme, self._b_about, self._b_min, self._b_max, self._b_close):
            lay.addWidget(b)

        self._buttons = (
            self._b_zoom_out, self._b_zoom_pct, self._b_zoom_in,
            self._b_theme, self._b_about, self._b_min, self._b_max, self._b_close,
        )
        self.apply_theme(LIGHT, dark=False)

    def set_zoom_label(self, pct: int) -> None:
        self._b_zoom_pct.setText(f"{pct} %")

    def set_max_glyph(self, is_max: bool) -> None:
        self._b_max.setText("❐" if is_max else "□")
        self._b_max.setToolTip("Restaurar" if is_max else "Maximizar")

    def apply_theme(self, pal: dict, dark: bool) -> None:
        self.setStyleSheet(
            f"#titlebar{{background:{pal['titlebar']};border-bottom:1px solid {pal['border']};}}"
        )
        self._title.setStyleSheet(
            f"color:{pal['text']};font-size:13px;font-weight:600;"
            f"font-family:'Segoe UI',sans-serif;"
        )
        self._zoom_icon.setPixmap(_magnifier(16, pal["icon"]))
        for b in self._buttons:
            b.apply_theme(pal)
        self._b_theme.setText("☀" if dark else "☾")
        self._b_theme.setToolTip("Modo claro" if dark else "Modo oscuro")

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemMove()  # arrastre nativo (Aero Snap incluido)
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
# Asas de resize: widgets finos por encima del web view. startSystemResize deja
# que Windows haga el hit-testing, así funciona aunque el cursor esté sobre el
# área del navegador.
# ──────────────────────────────────────────────────────────────────────────────
class _Grip(QWidget):
    def __init__(self, win: "MainWindow", edges: "Qt.Edge", cursor: "Qt.CursorShape"):
        super().__init__(win)
        self._win = win
        self._edges = edges
        self.setCursor(cursor)
        self.setStyleSheet("background:transparent;")

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and not self._win.isMaximized():
            handle = self._win.windowHandle()
            if handle is not None:
                handle.startSystemResize(self._edges)
                e.accept()
                return
        super().mousePressEvent(e)


# ──────────────────────────────────────────────────────────────────────────────
# Diálogo "Acerca de" (frameless, respeta el tema actual).
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

        title = QLabel(APP_TITLE, self)
        title.setStyleSheet(f"color:{pal['text']};font-size:18px;font-weight:800;")
        lay.addWidget(title)

        info = QLabel(
            "Aplicación para cálculos de parques eólicos.\n\n"
            f"Motor: Qt WebEngine (Chromium {qWebEngineChromiumVersion()})\n"
            "Interfaz: Streamlit",
            self,
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{pal['sub']};font-size:13px;")
        lay.addWidget(info)
        lay.addStretch(1)

        ok = QPushButton("Cerrar", self)
        ok.setFixedHeight(34)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:#fff;border:none;border-radius:8px;"
            f"font-weight:600;padding:0 18px;}}QPushButton:hover{{background:{ACCENT_HOVER};}}"
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

        st = _load_state()
        self._zoom = self._clamp_zoom(st.get("zoom", 1.0))
        self._dark = bool(st.get("dark", False))
        self._start_max = bool(st.get("maximized", False))

        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(MIN_W, MIN_H)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        central = QWidget(self)
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = _TitleBar(self)
        root.addWidget(self.titlebar)

        # Perfil persistente: cachea en disco el bundle JS de Streamlit (varios MB)
        # entre arranques → los siguientes inicios cargan más rápido.
        self._profile = QWebEngineProfile("AlfaApp", self)
        try:
            self._profile.setCachePath(str(_appdata_dir() / "webcache"))
            self._profile.setPersistentStoragePath(str(_appdata_dir() / "webstore"))
            self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
            self._profile.setHttpCacheMaximumSize(256 * 1024 * 1024)
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
            )
            self._profile.setSpellCheckEnabled(False)
        except Exception:
            pass

        # Web view + página con Chromium incrustado.
        self.view = QWebEngineView(self)
        self.page = _WebPage(self._profile, self.view)
        self.view.setPage(self.page)
        self.page.setBackgroundColor(QColor(LIGHT["page"]))  # evita flash blanco
        self.view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if not DEBUG:
            self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
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
        # Reaplicar el zoom guardado tras cada carga (Streamlit recarga al navegar).
        self.view.loadFinished.connect(self._reapply_zoom)

        # Atajos de zoom (Ctrl +/−/0), activos tenga el foco quien lo tenga.
        for seq, fn in (
            (QKeySequence.StandardKey.ZoomIn, self.zoom_in),
            (QKeySequence.StandardKey.ZoomOut, self.zoom_out),
            (QKeySequence("Ctrl+="), self.zoom_in),
            (QKeySequence("Ctrl+0"), self.zoom_reset),
        ):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(fn)

        # Asas de resize (8) por encima del web view.
        E, C = Qt.Edge, Qt.CursorShape
        self._grips = [
            _Grip(self, E.LeftEdge, C.SizeHorCursor),
            _Grip(self, E.RightEdge, C.SizeHorCursor),
            _Grip(self, E.TopEdge, C.SizeVerCursor),
            _Grip(self, E.BottomEdge, C.SizeVerCursor),
            _Grip(self, E.LeftEdge | E.TopEdge, C.SizeFDiagCursor),
            _Grip(self, E.RightEdge | E.BottomEdge, C.SizeFDiagCursor),
            _Grip(self, E.RightEdge | E.TopEdge, C.SizeBDiagCursor),
            _Grip(self, E.LeftEdge | E.BottomEdge, C.SizeBDiagCursor),
        ]

        self._restore_geometry(st)
        self.titlebar.set_zoom_label(round(self._zoom * 100))
        self.apply_theme()

    # ── Carga / mostrar ──
    def load_app(self) -> None:
        self.view.setUrl(QUrl(URL))

    def show_app(self) -> None:
        if self._start_max:
            self.showMaximized()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _reapply_zoom(self, ok: bool) -> None:
        if ok:
            self.view.setZoomFactor(self._zoom)

    # ── Zoom ──
    @staticmethod
    def _clamp_zoom(value) -> float:
        try:
            return max(ZOOM_STEPS[0], min(ZOOM_STEPS[-1], float(value)))
        except Exception:
            return 1.0

    def _set_zoom(self, factor: float) -> None:
        self._zoom = self._clamp_zoom(factor)
        self.view.setZoomFactor(self._zoom)
        self.titlebar.set_zoom_label(round(self._zoom * 100))

    def zoom_in(self) -> None:
        self._set_zoom(next((z for z in ZOOM_STEPS if z > self._zoom + 1e-3), ZOOM_STEPS[-1]))

    def zoom_out(self) -> None:
        self._set_zoom(next((z for z in reversed(ZOOM_STEPS) if z < self._zoom - 1e-3), ZOOM_STEPS[0]))

    def zoom_reset(self) -> None:
        self._set_zoom(1.0)

    # ── Tema claro / oscuro ──
    def apply_theme(self) -> None:
        pal = DARK if self._dark else LIGHT
        self.centralWidget().setStyleSheet(
            f"#central{{background:{pal['bg']};border:1px solid {pal['border']};}}"
        )
        self.titlebar.apply_theme(pal, self._dark)
        try:
            self.page.setBackgroundColor(QColor(pal["page"]))
        except Exception:
            pass
        self._apply_dark_filter()

    def toggle_theme(self) -> None:
        self._dark = not self._dark
        self.apply_theme()

    def _apply_dark_filter(self) -> None:
        """Oscurece/aclara el CONTENIDO web sin tocar su CSS. Un QWebEngineScript
        persistente reaplica el filtro en cada navegación; además se aplica al
        instante sobre la página actual."""
        try:
            scripts = self._profile.scripts()
            for s in scripts.find("sma-dark"):
                scripts.remove(s)
            if self._dark:
                sc = QWebEngineScript()
                sc.setName("sma-dark")
                sc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
                sc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
                sc.setRunsOnSubFrames(False)
                sc.setSourceCode(_DARK_ON)
                scripts.insert(sc)
        except Exception:
            pass
        try:
            self.page.runJavaScript(_DARK_ON if self._dark else _DARK_OFF)
        except Exception:
            pass

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
        self.titlebar.set_max_glyph(is_max)
        for g in self._grips:
            g.setVisible(not is_max)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if not hasattr(self, "_grips"):
            return
        w, h, m = self.width(), self.height(), GRIP
        show = not self.isMaximized()
        rects = [
            QRect(0, m, m, h - 2 * m),          # left
            QRect(w - m, m, m, h - 2 * m),      # right
            QRect(m, 0, w - 2 * m, m),          # top
            QRect(m, h - m, w - 2 * m, m),      # bottom
            QRect(0, 0, m, m),                  # top-left
            QRect(w - m, h - m, m, m),          # bottom-right
            QRect(w - m, 0, m, m),              # top-right
            QRect(0, h - m, m, m),              # bottom-left
        ]
        for g, r in zip(self._grips, rects):
            g.setGeometry(r)
            g.setVisible(show)
            g.raise_()

    # ── Descargas → "Guardar como" ──
    def _on_download(self, dl: QWebEngineDownloadRequest) -> None:
        name = dl.suggestedFileName() or "descarga"
        start = str(Path.home() / "Downloads" / name)
        path, _ = QFileDialog.getSaveFileName(self, "Guardar como", start)
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

    # ── Geometría: restaurar / centrar ──
    def _restore_geometry(self, st: dict) -> None:
        rect = None
        try:
            rect = QRect(int(st["x"]), int(st["y"]), int(st["w"]), int(st["h"]))
        except Exception:
            rect = None
        if rect and rect.width() >= MIN_W and rect.height() >= MIN_H and self._on_screen(rect):
            self.setGeometry(rect)
        else:
            self.resize(1280, 820)
            self._center()

    @staticmethod
    def _on_screen(rect: QRect) -> bool:
        return any(s.availableGeometry().intersects(rect) for s in QGuiApplication.screens())

    def _center(self) -> None:
        scr = QGuiApplication.primaryScreen()
        if not scr:
            return
        a = scr.availableGeometry()
        self.move(
            a.x() + (a.width() - self.width()) // 2,
            a.y() + (a.height() - self.height()) // 2,
        )

    # ── Estado de ventana: guardar ──
    def _save_state(self) -> None:
        try:
            g = self.normalGeometry()  # geometría NO maximizada
            STATE_FILE.write_text(
                json.dumps({
                    "x": g.x(), "y": g.y(), "w": g.width(), "h": g.height(),
                    "maximized": self.isMaximized(),
                    "zoom": self._zoom,
                    "dark": self._dark,
                }),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Cierre limpio: matar el servidor hijo ──
    def stop_server(self) -> None:
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
        self._save_state()
        self.stop_server()
        super().closeEvent(e)


# ──────────────────────────────────────────────────────────────────────────────
# Proceso hijo del servidor Streamlit.
# ──────────────────────────────────────────────────────────────────────────────
def _start_server() -> subprocess.Popen:
    env = {**os.environ, "ALFA_RUN_SERVER": "1", "ALFA_NO_BROWSER": "1"}
    if getattr(sys, "frozen", False):
        args = [sys.executable]  # el .exe se re-ejecuta en modo servidor
    else:
        args = [sys.executable, os.path.abspath(__file__)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    return subprocess.Popen(args, env=env, creationflags=flags)


# ──────────────────────────────────────────────────────────────────────────────
# Splash de arranque (respeta el tema guardado).
# ──────────────────────────────────────────────────────────────────────────────
def _make_splash(dark: bool) -> QSplashScreen:
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
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(186, 56, 68, 68, 18, 18)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI")
    f.setBold(True)
    f.setPointSize(30)
    p.setFont(f)
    p.drawText(QRect(186, 56, 68, 68), Qt.AlignmentFlag.AlignCenter, "α")
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
    # Flags de Chromium (antes de crear el QApplication). Conservadoras por
    # defecto; ALFA_GPU=1 fuerza rasterización por GPU.
    flags = "--disable-features=Translate"
    if os.environ.get("ALFA_GPU") == "1":
        flags += " --ignore-gpu-blocklist --enable-gpu-rasterization --enable-zero-copy"
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", flags)

    try:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(_app_icon())

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass

    # Instancia única: si ya hay una abierta, enfocarla y salir.
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

    splash = _make_splash(bool(_load_state().get("dark", False)))
    splash.show()
    app.processEvents()

    server_proc = _start_server()
    window = MainWindow(server_proc)

    # 2ª instancia → traer la ventana al frente.
    def _focus_existing():
        conn = local_server.nextPendingConnection()
        if conn:
            conn.readyRead.connect(conn.deleteLater)
        if window.isMinimized():
            window.showNormal()
        window.raise_()
        window.activateWindow()

    local_server.newConnection.connect(_focus_existing)

    state = {"loaded": False, "shown": False, "elapsed": 0.0}

    def _on_load(ok: bool):
        if state["shown"]:
            return
        if not ok:
            QTimer.singleShot(600, window.load_app)  # reintento corto
            return
        state["shown"] = True
        splash.finish(window)
        window.show_app()

    window.view.loadFinished.connect(_on_load)

    def _poll():
        if state["loaded"]:
            return
        if _port_open(HOST, PORT):
            state["loaded"] = True
            poll.stop()
            window.load_app()
            return
        state["elapsed"] += 0.15
        if state["elapsed"] > 40.0:  # ~40 s sin servidor → abortar
            poll.stop()
            splash.close()
            window.stop_server()
            QMessageBox.critical(
                None, APP_NAME,
                "No se pudo iniciar el servidor de la aplicación.\n"
                f"Revisa el log en:\n{_appdata_dir() / 'app_log.txt'}",
            )
            app.quit()

    poll = QTimer()
    poll.timeout.connect(_poll)
    poll.start(150)

    # Salvaguarda al salir.
    app.aboutToQuit.connect(window.stop_server)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
