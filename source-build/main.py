# ── Quick-patch loader — MUST be first (frozen builds only) ──────────────────
# If deadlock_patch.py sits next to the exe (from a -Quick release), exec it
# instead of the bundled code.  An env-guard prevents re-entry.
import sys as _sys, os as _os
if getattr(_sys, 'frozen', False) and not _os.environ.get('_DT_PATCHED'):
    from pathlib import Path as _PP
    _pf = _PP(_sys.executable).parent / 'deadlock_patch.py'
    if _pf.exists():
        _os.environ['_DT_PATCHED'] = '1'
        try:
            with open(_pf, 'r', encoding='utf-8') as _h:
                _patch_src = _h.read()
            exec(compile(_patch_src, str(_pf), 'exec'), {'__name__': '__main__'})
            _sys.exit(0)
        except Exception:
            # Bad patch — delete it, fall through to bundled code
            try:
                _pf.unlink()
            except Exception:
                pass
# ─────────────────────────────────────────────────────────────────────────────
import sys
import os
import re
import json
import subprocess
import traceback
import urllib.request
import urllib.error
import winreg
import ctypes
import ctypes.wintypes
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QSizePolicy,
    QSlider, QComboBox, QLineEdit, QStackedWidget, QSpacerItem, QProgressBar,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QDialog, QFileDialog,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QSize, QTimer, QThread, QObject, pyqtSignal, QPropertyAnimation, QEasingCurve, QElapsedTimer, QRect, QRectF, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPixmap, QPen, QPainterPath, QBitmap, QRegion

# ──────────────────────────────────────────────────────────────────────────────
# Palette
# ──────────────────────────────────────────────────────────────────────────────
C_BG          = "#0d0d0d"
C_SIDEBAR     = "#111111"
C_CARD        = "#161616"
C_CARD2       = "#1a1a1a"
C_BORDER      = "#222222"
C_GREEN       = "#3ddc84"
C_GREEN_DIM   = "#2aad65"
C_GREEN_GLOW  = "#1e5c38"
C_TEXT        = "#e8e8e8"
C_TEXT_DIM    = "#888888"
C_TEXT_MID    = "#b0b0b0"
C_TOGGLE_OFF  = "#333333"

# ──────────────────────────────────────────────────────────────────────────────
# Theme system
# ──────────────────────────────────────────────────────────────────────────────
_CURRENT_THEME = "dark"

_THEMES = {
    "dark": {
        "bg":         "#0d0d0d",
        "sidebar":    "#111111",
        "card":       "#161616",
        "card2":      "#1a1a1a",
        "border":     "#222222",
        "green":      "#3ddc84",
        "green_dim":  "#2aad65",
        "green_glow": "#1e5c38",
        "text":       "#e8e8e8",
        "text_dim":   "#888888",
        "text_mid":   "#b0b0b0",
        "toggle_off": "#333333",
        "nav_hover":  "#1c1c1c",
        "titlebar_hover": "#2a2a2a",
    },
}


def set_theme(name: str) -> None:
    global _CURRENT_THEME
    global C_BG, C_SIDEBAR, C_CARD, C_CARD2, C_BORDER
    global C_GREEN, C_GREEN_DIM, C_GREEN_GLOW
    global C_TEXT, C_TEXT_DIM, C_TEXT_MID, C_TOGGLE_OFF
    _CURRENT_THEME = name
    t = _THEMES[name]
    C_BG          = t["bg"]
    C_SIDEBAR     = t["sidebar"]
    C_CARD        = t["card"]
    C_CARD2       = t["card2"]
    C_BORDER      = t["border"]
    C_GREEN       = t["green"]
    C_GREEN_DIM   = t["green_dim"]
    C_GREEN_GLOW  = t["green_glow"]
    C_TEXT        = t["text"]
    C_TEXT_DIM    = t["text_dim"]
    C_TEXT_MID    = t["text_mid"]
    C_TOGGLE_OFF  = t["toggle_off"]

# ──────────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────────
# App version & update endpoint
# ──────────────────────────────────────────────────────────────────────────────
APP_VERSION = "1.1.3"
DEFAULT_APP_TRANSPARENCY = 50

GITHUB_REPO = "d1n4styy/deadlock-tweaker"
UPDATE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
UPDATE_ASSET_NAME = "DeadlockTweaker.exe"
PATCH_ASSET_NAME  = "main_patch.py"   # code-only quick-release patch

# ──────────────────────────────────────────────────────────────────────────────
# Refresh-rate aware animation helpers
# ──────────────────────────────────────────────────────────────────────────────
_TOGGLE_ANIM_MS = 220  # toggle knob travel duration in ms

def _screen_hz() -> float:
    """Primary screen refresh rate (Hz); fallback 60."""
    app = QApplication.instance()
    if app:
        screen = app.primaryScreen()
        if screen:
            hz = screen.refreshRate()
            if hz > 0:
                return hz
    return 60.0

def _timer_interval_ms() -> int:
    """One-frame interval in ms for the primary screen's refresh rate."""
    return max(1, round(1000.0 / _screen_hz()))


STEAM_PATH          = Path(r"C:\Program Files (x86)\Steam")
STEAM_USERDATA_PATH = STEAM_PATH / "userdata"
DEADLOCK_APP_ID     = "1422450"
STEAM_AUTOEXEC_ARG  = "+exec autoexec.cfg"
CONFIG_PATH         = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\Deadlock\game\citadel\cfg\autoexec.cfg"
)
PROFILES_PATH = Path(__file__).resolve().parent / "profiles.json"
HEALTHBARS_COMMANDS = [
    "citadel_healthbars_enabled false",
    "citadel_unit_status_use_new true",
]
LEGACY_HEALTHBARS_LINE = "+citadel_healthbars_enabled false +citadel_unit_status_use_new true"


# ──────────────────────────────────────────────────────────────────────────────
# Config discovery helpers
# ──────────────────────────────────────────────────────────────────────────────
_CFG_RELATIVE = Path("steamapps/common/Deadlock/game/citadel/cfg/autoexec.cfg")

def _steam_paths_from_registry() -> list[Path]:
    """Return Steam install paths found in Windows registry."""
    paths = []
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Valve\Steam"),
    ]
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as k:
                val, _ = winreg.QueryValueEx(k, "InstallPath")
                p = Path(val)
                if p.exists() and p not in paths:
                    paths.append(p)
        except OSError:
            pass
    return paths


def _steam_library_folders(steam_root: Path) -> list[Path]:
    """Parse libraryfolders.vdf to get all Steam library paths."""
    libs = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return libs
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = Path(m.group(1))
            if p.exists() and p not in libs:
                libs.append(p)
    except Exception:
        pass
    return libs


def find_autoexec() -> Path | None:
    """Search all Steam libraries for the Deadlock autoexec.cfg."""
    # Hard-coded default first
    if CONFIG_PATH.exists():
        return CONFIG_PATH
    # Registry-based search
    for steam_root in _steam_paths_from_registry():
        for lib in _steam_library_folders(steam_root):
            candidate = lib / _CFG_RELATIVE
            if candidate.exists():
                return candidate
    return None


def create_autoexec(path: Path) -> None:
    """Create autoexec.cfg with a minimal valid header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("// Deadlock autoexec.cfg — created by Deadlock Tweaker\n", encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# First-run Setup Dialog
# ──────────────────────────────────────────────────────────────────────────────
class SetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.found_path: Path | None = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 420)
        self._drag_pos = None
        self._build()
        self._scan()

    # ── drag support ──────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ── build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setStyleSheet(
            f"QFrame#setup_card {{ background:{C_BG}; border-radius:16px;"
            f" border:1px solid {C_BORDER}; }}"
        )
        card.setObjectName("setup_card")
        outer.addWidget(card)

        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(32, 28, 32, 28)
        vbox.setSpacing(16)

        # Title bar row
        title_row = QHBoxLayout()
        ico = QLabel("⚙")
        ico.setFont(QFont("Segoe UI", 20))
        ico.setStyleSheet(f"color:{C_GREEN}; background:transparent; border:none;")
        title_lbl = QLabel("Deadlock Tweaker — Setup")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color:{C_TEXT}; background:transparent; border:none;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C_TEXT_DIM};border:none;font-size:13px;border-radius:6px;}}"
            f"QPushButton:hover{{background:#2a2a2a;color:{C_TEXT};}}"
        )
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(ico)
        title_row.addSpacing(8)
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        vbox.addLayout(title_row)

        # Divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background:{C_BORDER};border:none;")
        vbox.addWidget(div)

        # Status icon + description
        self._status_icon = QLabel("🔍")
        self._status_icon.setFont(QFont("Segoe UI", 36))
        self._status_icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status_icon.setStyleSheet("background:transparent;border:none;")
        vbox.addWidget(self._status_icon)

        self._status_lbl = QLabel("Поиск игры…")
        self._status_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status_lbl.setStyleSheet(f"color:{C_TEXT}; background:transparent; border:none;")
        vbox.addWidget(self._status_lbl)

        self._detail_lbl = QLabel("Сканирование библиотек Steam…")
        self._detail_lbl.setFont(QFont("Segoe UI", 9))
        self._detail_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setStyleSheet(f"color:{C_TEXT_DIM}; background:transparent; border:none;")
        vbox.addWidget(self._detail_lbl)

        vbox.addStretch()

        # Path display frame
        path_frame = QFrame()
        path_frame.setStyleSheet(
            f"QFrame{{background:{C_CARD};border-radius:8px;border:1px solid {C_BORDER};}}"
        )
        pfl = QHBoxLayout(path_frame)
        pfl.setContentsMargins(12, 8, 12, 8)
        path_ico = QLabel("📁")
        path_ico.setFont(QFont("Segoe UI", 12))
        path_ico.setStyleSheet("background:transparent;border:none;")
        self._path_lbl = QLabel("—")
        self._path_lbl.setFont(QFont("Segoe UI", 8))
        self._path_lbl.setStyleSheet(f"color:{C_TEXT_MID}; background:transparent; border:none;")
        self._path_lbl.setWordWrap(True)
        pfl.addWidget(path_ico)
        pfl.addWidget(self._path_lbl, 1)
        vbox.addWidget(path_frame)

        vbox.addSpacing(8)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        # "Create file" button — hidden until needed
        self._create_btn = QPushButton("✚  Создать autoexec.cfg")
        self._create_btn.setFixedHeight(40)
        self._create_btn.setFont(QFont("Segoe UI", 10))
        self._create_btn.setStyleSheet(
            f"QPushButton{{background:{C_CARD};color:{C_TEXT};border:1px solid {C_BORDER};"
            f"border-radius:8px;padding:0 16px;}}"
            f"QPushButton:hover{{background:#222;border-color:{C_GREEN_DIM};}}"
        )
        self._create_btn.setVisible(False)
        self._create_btn.clicked.connect(self._on_create)

        # "Browse" button
        self._browse_btn = QPushButton("📂  Выбрать вручную")
        self._browse_btn.setFixedHeight(40)
        self._browse_btn.setFont(QFont("Segoe UI", 10))
        self._browse_btn.setStyleSheet(
            f"QPushButton{{background:{C_CARD};color:{C_TEXT_DIM};border:1px solid {C_BORDER};"
            f"border-radius:8px;padding:0 16px;}}"
            f"QPushButton:hover{{background:#222;color:{C_TEXT};}}"
        )
        self._browse_btn.setVisible(False)
        self._browse_btn.clicked.connect(self._on_browse)

        # "Continue" button — main action
        self._continue_btn = QPushButton("▶  Продолжить")
        self._continue_btn.setFixedHeight(40)
        self._continue_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._continue_btn.setStyleSheet(
            f"QPushButton{{background:{C_GREEN};color:#000;border:none;"
            f"border-radius:8px;padding:0 24px;}}"
            f"QPushButton:hover{{background:{C_GREEN_DIM};}}"
        )
        self._continue_btn.setVisible(False)
        self._continue_btn.clicked.connect(self.accept)

        btn_row.addWidget(self._create_btn)
        btn_row.addWidget(self._browse_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._continue_btn)
        vbox.addLayout(btn_row)

    # ── logic ─────────────────────────────────────────────────────────────────
    def _scan(self):
        """Run discovery after the event loop starts."""
        QTimer.singleShot(200, self._do_scan)

    def _do_scan(self):
        path = find_autoexec()
        if path:
            self._set_found(path)
        else:
            self._set_not_found()

    def _set_found(self, path: Path):
        self.found_path = path
        global CONFIG_PATH
        CONFIG_PATH = path
        self._status_icon.setText("✅")
        self._status_lbl.setText("Игра найдена!")
        self._status_lbl.setStyleSheet(f"color:{C_GREEN}; background:transparent; border:none; font-weight:700;")
        self._detail_lbl.setText("Файл конфигурации autoexec.cfg обнаружен.")
        self._path_lbl.setText(str(path))
        self._continue_btn.setVisible(True)
        self._browse_btn.setVisible(True)

    def _set_not_found(self):
        self.found_path = None
        self._status_icon.setText("⚠️")
        self._status_lbl.setText("Файл не найден")
        self._status_lbl.setStyleSheet(f"color:#f0a500; background:transparent; border:none; font-weight:700;")
        self._detail_lbl.setText(
            "Не удалось найти autoexec.cfg в библиотеках Steam.\n"
            "Вы можете создать файл автоматически или указать путь вручную."
        )
        self._path_lbl.setText("Файл не обнаружен")
        self._create_btn.setVisible(True)
        self._browse_btn.setVisible(True)

    def _on_create(self):
        # Try to create in default location
        steam_roots = _steam_paths_from_registry()
        if steam_roots:
            target = steam_roots[0] / _CFG_RELATIVE
        else:
            target = CONFIG_PATH
        try:
            create_autoexec(target)
            self._set_found(target)
            self._create_btn.setVisible(False)
        except Exception as ex:
            self._detail_lbl.setText(f"Ошибка создания файла: {ex}\nПопробуйте выбрать путь вручную.")

    def _on_browse(self):
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Выберите autoexec.cfg", "", "Config Files (*.cfg);;All Files (*)"
        )
        if path_str:
            p = Path(path_str)
            self._set_found(p)
            self._create_btn.setVisible(False)


# ──────────────────────────────────────────────────────────────────────────────
# Profile Name Dialog
# ──────────────────────────────────────────────────────────────────────────────
class ProfileNameDialog(QDialog):
    def __init__(self, parent=None, existing_names=None):
        super().__init__(parent)
        self._existing = existing_names or []
        self.profile_name = ""
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 210)
        self._drag_pos = None
        self._build()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(self.pos() + e.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("pnd_card")
        card.setStyleSheet(
            f"QFrame#pnd_card{{background:{C_BG};border-radius:14px;border:1px solid {C_BORDER};}}"
        )
        outer.addWidget(card)
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(24, 20, 24, 20)
        vbox.setSpacing(12)

        row = QHBoxLayout()
        title = QLabel("Сохранить профиль")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{C_TEXT};background:transparent;border:none;")
        close = QPushButton("✕")
        close.setFixedSize(26, 26)
        close.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C_TEXT_DIM};border:none;border-radius:6px;font-size:12px;}}"
            f"QPushButton:hover{{background:#333;color:{C_TEXT};}}"
        )
        close.clicked.connect(self.reject)
        row.addWidget(title)
        row.addStretch()
        row.addWidget(close)
        vbox.addLayout(row)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Название профиля...")
        self._input.setFixedHeight(38)
        self._input.setFont(QFont("Segoe UI", 10))
        self._input.setStyleSheet(
            f"QLineEdit{{background:{C_CARD};color:{C_TEXT};border:1px solid {C_BORDER};"
            f"border-radius:8px;padding:0 12px;}}"
            f"QLineEdit:focus{{border-color:{C_GREEN_DIM};}}"
        )
        vbox.addWidget(self._input)

        self._error = QLabel("")
        self._error.setFont(QFont("Segoe UI", 8))
        self._error.setStyleSheet("color:#ff4c4c;background:transparent;border:none;")
        self._error.setFixedHeight(16)
        vbox.addWidget(self._error)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        cancel = QPushButton("Отмена")
        cancel.setFixedHeight(36)
        cancel.setFont(QFont("Segoe UI", 9))
        cancel.setStyleSheet(
            f"QPushButton{{background:{C_CARD};color:{C_TEXT_DIM};border:1px solid {C_BORDER};"
            f"border-radius:8px;padding:0 16px;}}"
            f"QPushButton:hover{{color:{C_TEXT};}}"
        )
        cancel.clicked.connect(self.reject)
        save = QPushButton("Сохранить")
        save.setFixedHeight(36)
        save.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        save.setStyleSheet(
            f"QPushButton{{background:{C_GREEN};color:#000;border:none;border-radius:8px;padding:0 20px;}}"
            f"QPushButton:hover{{background:{C_GREEN_DIM};}}"
        )
        save.clicked.connect(self._on_save)
        self._input.returnPressed.connect(self._on_save)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        btn_row.addWidget(save)
        vbox.addLayout(btn_row)

    def _on_save(self):
        name = self._input.text().strip()
        if not name:
            self._error.setText("Введите название профиля")
            return
        if name.lower() == "default profile":
            self._error.setText("Это название зарезервировано")
            return
        if name in self._existing:
            self._error.setText("Профиль с таким именем уже существует")
            return
        self.profile_name = name
        self.accept()


# ──────────────────────────────────────────────────────────────────────────────
# Game process watcher (background thread)
# ──────────────────────────────────────────────────────────────────────────────
class GameWatcher(QObject):
    status_changed = pyqtSignal(bool)  # True = running

    def __init__(self):
        super().__init__()
        self._last_state = None

    def check(self):
        try:
            result = subprocess.run(
                ["tasklist", "/NH"],
                capture_output=True, text=True, timeout=3,
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            out = result.stdout.lower()
            found = "deadlock.exe" in out or "project8.exe" in out
        except Exception:
            found = False
        if found != self._last_state:
            self._last_state = found
            self.status_changed.emit(found)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def shadow(widget: QWidget, radius: int = 24, color: str = "#000000", alpha: int = 120) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(radius)
    c = QColor(color)
    c.setAlpha(alpha)
    eff.setColor(c)
    eff.setOffset(0, 4)
    widget.setGraphicsEffect(eff)


def card_style(radius: int = 14, bg: str = None, border: str = None) -> str:
    if bg is None:
        bg = C_CARD
    if border is None:
        border = C_BORDER
    # Используем rgba для стеклянного эффекта
    r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
    return (
        f"background: rgba({r},{g},{b},200); border-radius:{radius}px;"
        f"border:1px solid rgba(255,255,255,18);"
    )


def _enable_acrylic_blur(hwnd: int, tint_color: int = 0xCC0d0d0d) -> bool:
    """Включает Windows Acrylic blur через SetWindowCompositionAttribute.
    tint_color: 0xAARRGGBB (Windows ожидает AABBGGRR)
    """
    try:
        class ACCENT_POLICY(ctypes.Structure):
            _fields_ = [
                ('AccentState',   ctypes.c_int),
                ('AccentFlags',   ctypes.c_int),
                ('GradientColor', ctypes.c_uint),
                ('AnimationId',   ctypes.c_int),
            ]

        class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
            _fields_ = [
                ('Attribute',   ctypes.c_int),
                ('Data',        ctypes.c_void_p),
                ('SizeOfData',  ctypes.c_size_t),
            ]

        class MARGINS(ctypes.Structure):
            _fields_ = [
                ("cxLeftWidth", ctypes.c_int),
                ("cxRightWidth", ctypes.c_int),
                ("cyTopHeight", ctypes.c_int),
                ("cyBottomHeight", ctypes.c_int),
            ]

        ACCENT_ENABLE_BLURBEHIND = 3
        ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
        WCA_ACCENT_POLICY = 19

        # Перекодируем AARRGGBB -> AABBGGRR
        aa = (tint_color >> 24) & 0xFF
        rr = (tint_color >> 16) & 0xFF
        gg = (tint_color >>  8) & 0xFF
        bb = (tint_color >>  0) & 0xFF
        gradient = (aa << 24) | (bb << 16) | (gg << 8) | rr

        accent = ACCENT_POLICY()
        accent.AccentState   = ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags   = 2
        accent.GradientColor = gradient

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute  = WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data       = ctypes.cast(ctypes.byref(accent), ctypes.c_void_p)

        set_wca = ctypes.windll.user32.SetWindowCompositionAttribute
        set_wca.restype = ctypes.c_bool
        ok = bool(set_wca(hwnd, ctypes.byref(data)))
        if ok:
            return True

        # Fallback: обычный blur behind, если acrylic недоступен / отклонён системой.
        accent.AccentState = ACCENT_ENABLE_BLURBEHIND
        ok = bool(set_wca(hwnd, ctypes.byref(data)))
        if ok:
            return True

        # Последний fallback через DWM: расширяем blur на всю клиентскую область.
        margins = MARGINS(-1, -1, -1, -1)
        dwm_extend = ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea
        dwm_extend.restype = ctypes.c_long
        return dwm_extend(hwnd, ctypes.byref(margins)) == 0
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Toggle Switch
# ──────────────────────────────────────────────────────────────────────────────
class ToggleSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, initial: bool = False):
        super().__init__(parent)
        self._checked = initial
        self._anim_pos = 1.0 if initial else 0.0
        self._anim_from = self._anim_pos
        self._anim_elapsed = QElapsedTimer()
        self.setFixedSize(52, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool) -> None:
        self._checked = v
        self._anim_pos = 1.0 if v else 0.0
        self.update()

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self._anim_from = self._anim_pos
        self._anim_elapsed.restart()
        self._timer.setInterval(_timer_interval_ms())
        if not self._timer.isActive():
            self._timer.start()
        self.toggled.emit(self._checked)

    def _step(self):
        target = 1.0 if self._checked else 0.0
        t = min(self._anim_elapsed.elapsed() / _TOGGLE_ANIM_MS, 1.0)
        # smoothstep ease-in-out
        t_e = t * t * (3.0 - 2.0 * t)
        self._anim_pos = self._anim_from + (target - self._anim_from) * t_e
        if t >= 1.0:
            self._anim_pos = target
            self._timer.stop()
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_color = QColor(C_GREEN) if self._checked else QColor(C_TOGGLE_OFF)
        p.setBrush(QBrush(track_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 4, 52, 20, 10, 10)
        knob_x = 2 + self._anim_pos * 28
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(int(knob_x), 4, 20, 20)
        p.end()




# ──────────────────────────────────────────────────────────────────────────────
# Sidebar Nav Button
# ──────────────────────────────────────────────────────────────────────────────
class NavButton(QPushButton):
    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._active = False
        self._icon_str = icon
        self._label = label
        self.setFont(QFont("Segoe UI", 10))
        self.setFixedHeight(46)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_content()
        self._update_style()

    def _build_content(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)
        icon_lbl = QLabel(self._icon_str)
        icon_lbl.setObjectName("nav_icon")
        icon_lbl.setFont(QFont("Segoe MDL2 Assets", 14))
        icon_lbl.setFixedWidth(22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        text_lbl = QLabel(self._label)
        text_lbl.setObjectName("nav_text")
        text_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl)
        layout.addStretch()
        self._icon_lbl = icon_lbl
        self._text_lbl = text_lbl
        self._update_label_colors()

    def setActive(self, v: bool):
        self._active = v
        self.setChecked(v)
        self._update_style()
        self._update_label_colors()

    def _update_label_colors(self):
        if self._active:
            self._icon_lbl.setStyleSheet(f"color:{C_GREEN};background:transparent;border:none;")
            self._text_lbl.setStyleSheet(f"color:{C_GREEN};background:transparent;border:none;font-weight:500;")
        else:
            self._icon_lbl.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
            self._text_lbl.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;font-weight:500;")

    def _update_style(self):
        if self._active:
            self.setStyleSheet(
                f"QPushButton {{ background: {C_GREEN_GLOW}; border: none; border-radius: 10px; }}"
                f"QPushButton:hover {{ background: {C_GREEN_GLOW}; }}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; border-radius: 10px; }}"
                f"QPushButton:hover {{ background: #1c1c1c; }}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Stat Card (top info strip)
# ──────────────────────────────────────────────────────────────────────────────
class StatCard(QFrame):
    def __init__(self, icon: str, title: str, value: str, value_color: str = None, parent=None):
        super().__init__(parent)
        if value_color is None:
            value_color = C_GREEN
        self.setStyleSheet(card_style(12, C_CARD2, C_BORDER))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setStyleSheet(f"color:{C_GREEN}; background:transparent; border:none;")
        icon_lbl.setFixedWidth(32)
        layout.addWidget(icon_lbl)

        vbox = QVBoxLayout()
        vbox.setSpacing(2)

        t = QLabel(title)
        t.setFont(QFont("Segoe UI", 9))
        t.setStyleSheet(f"color:{C_TEXT_DIM}; background:transparent; border:none;")
        vbox.addWidget(t)

        v = QLabel(value)
        v.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        v.setStyleSheet(f"color:{value_color}; background:transparent; border:none;")
        vbox.addWidget(v)

        layout.addLayout(vbox)
        layout.addStretch()
        shadow(self, 12)
        self._value_lbl = v

    def set_value(self, text: str, color: str):
        self._value_lbl.setText(text)
        self._value_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")


# ──────────────────────────────────────────────────────────────────────────────
# Section header
# ──────────────────────────────────────────────────────────────────────────────
def section_header(title: str, icon: str = "") -> QLabel:
    text = f"{icon}  {title}" if icon else title
    lbl = QLabel(text)
    lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    lbl.setStyleSheet(f"color:{C_TEXT}; background:transparent; border:none; padding:4px 0;")
    return lbl


# ──────────────────────────────────────────────────────────────────────────────
# Toggle Row
# ──────────────────────────────────────────────────────────────────────────────
class ToggleRow(QFrame):
    def __init__(self, label: str, initial: bool = True, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border-radius:10px; border:1px solid {C_BORDER}; }}"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setStyleSheet(f"color:{C_TEXT_MID}; background:transparent; border:none;")
        h.addWidget(lbl)
        h.addStretch()

        self.toggle = ToggleSwitch(initial=initial)
        h.addWidget(self.toggle)


# ──────────────────────────────────────────────────────────────────────────────
# Slider Row
# ──────────────────────────────────────────────────────────────────────────────
class SliderRow(QFrame):
    def __init__(self, label: str, value: str, min_v: int = 0, max_v: int = 200,
                 cur: int = 100, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border-radius:10px; border:1px solid {C_BORDER}; }}"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(12)

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setStyleSheet(f"color:{C_TEXT_MID}; background:transparent; border:none;")
        lbl.setFixedWidth(120)
        h.addWidget(lbl)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(min_v)
        self.slider.setMaximum(max_v)
        self.slider.setValue(cur)
        self.slider.setStyleSheet(
            f"""
            QSlider {{
                border: none; outline: none; background: transparent;
            }}
            QSlider::groove:horizontal {{
                height: 3px; background: {C_BORDER}; border-radius: 2px;
                border: none;
            }}
            QSlider::sub-page:horizontal {{
                background: {C_GREEN}; border-radius: 2px; border: none;
            }}
            QSlider::handle:horizontal {{
                background: #ffffff; border: none;
                width: 12px; height: 12px;
                margin: -5px 0; border-radius: 6px;
            }}
            """
        )
        h.addWidget(self.slider, 1)

        self.val_lbl = QLabel(value)
        self.val_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.val_lbl.setStyleSheet(f"color:{C_TEXT}; background:transparent; border:none;")
        self.val_lbl.setFixedWidth(42)
        self.val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(self.val_lbl)

        self.slider.valueChanged.connect(lambda v: self.val_lbl.setText(str(v)))


# ──────────────────────────────────────────────────────────────────────────────
# Rounded ComboBox — popup с настоящими скруглёнными углами
# ──────────────────────────────────────────────────────────────────────────────
class _ComboPopup(QWidget):
    """Кастомный popup для RoundedComboBox — реальные скруглённые углы через paintEvent."""
    item_chosen = pyqtSignal(int)

    def __init__(self, combo: "RoundedComboBox"):
        # Используем главное окно как родителя — Qt управляет временем жизни
        parent_win = combo.window() if combo.window() is not combo else None
        super().__init__(parent_win, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._combo = combo
        self._picked = False  # защита от двойного срабатывания

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._list = QListWidget()
        self._list.setFrameShape(QFrame.Shape.NoFrame)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setFont(QFont("Segoe UI", 9))
        outer.addWidget(self._list)

        for i in range(combo.count()):
            item = QListWidgetItem(combo.itemText(i))
            item.setSizeHint(QSize(0, 30))
            self._list.addItem(item)
        self._list.setCurrentRow(combo.currentIndex())
        self._list.itemClicked.connect(self._pick)

        self._restyle()

    def _restyle(self):
        self._list.setStyleSheet(
            f"QListWidget {{ background: transparent; color: {C_TEXT};"
            f" border: none; outline: none; padding: 4px; }}"
            f"QListWidget::item {{ border-radius: 6px; padding-left: 8px; }}"
            f"QListWidget::item:hover {{ background: {C_GREEN_GLOW}; color: {C_GREEN}; }}"
            f"QListWidget::item:selected {{ background: {C_GREEN_GLOW}; color: {C_GREEN}; }}"
        )

    def _pick(self, item: QListWidgetItem):
        if self._picked:
            return
        self._picked = True
        row = self._list.row(item)
        # Сначала закрываем, потом эмитируем — предотвращает re-entrancy
        self.close()
        self.item_chosen.emit(row)

    def closeEvent(self, event):
        # Когда Qt авто-закрывает popup (клик снаружи) — очищаем ссылку в combo
        if self._combo is not None and self._combo._popup is self:
            self._combo._popup = None
        super().closeEvent(event)

    def sizeHint(self):
        n = max(1, self._list.count())
        item_h = 32
        w = max(self._combo.width(), 120)
        return QSize(w, min(n * item_h + 10, 300))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(C_CARD)
        bg.setAlpha(235)
        border = QColor(C_BORDER)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.fillPath(path, QBrush(bg))
        p.setPen(QPen(border, 1))
        p.drawPath(path)
        p.end()


class RoundedComboBox(QComboBox):
    """QComboBox с кастомным rounded popup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup: _ComboPopup | None = None
        self._showing_popup = False  # re-entrancy guard

    def showPopup(self):
        if self._showing_popup:
            return
        # Если уже открыт — закрываем
        if self._popup is not None:
            try:
                if self._popup.isVisible():
                    self._popup.close()
            except RuntimeError:
                pass
            self._popup = None
            return

        self._showing_popup = True
        try:
            p = _ComboPopup(self)
            p.item_chosen.connect(self._on_chosen)
            sz = p.sizeHint()
            p.resize(sz)
            # Позиционируем под комбо, с защитой от выхода за экран
            gl = self.mapToGlobal(QPoint(0, self.height()))
            screen = QApplication.primaryScreen()
            if screen:
                sg = screen.availableGeometry()
                if gl.y() + sz.height() > sg.bottom():
                    gl = self.mapToGlobal(QPoint(0, -sz.height()))
                if gl.x() + sz.width() > sg.right():
                    gl.setX(sg.right() - sz.width())
            p.move(gl)
            p.show()
            self._popup = p
        finally:
            self._showing_popup = False

    def hidePopup(self):
        if self._popup is not None:
            try:
                self._popup.close()
            except RuntimeError:
                pass
            self._popup = None
        super().hidePopup()

    def _on_chosen(self, index: int):
        self._popup = None
        if 0 <= index < self.count():
            self.setCurrentIndex(index)


# ──────────────────────────────────────────────────────────────────────────────
# Combo Row
# ──────────────────────────────────────────────────────────────────────────────
class ComboRow(QFrame):
    def __init__(self, label: str, options: list, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background:{C_CARD}; border-radius:10px; border:1px solid {C_BORDER}; }}"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 8, 14, 8)

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setStyleSheet(f"color:{C_TEXT_MID}; background:transparent; border:none;")
        h.addWidget(lbl)
        h.addStretch()

        cb = RoundedComboBox()
        cb.addItems(options)
        cb.setFont(QFont("Segoe UI", 9))
        cb.setFixedWidth(130)
        cb.setStyleSheet(
            f"""
            QComboBox {{
                background: {C_CARD2}; color: {C_TEXT};
                border: 1px solid {C_BORDER}; border-radius: 8px; padding: 4px 10px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {C_CARD2}; color: {C_TEXT}; border: 1px solid {C_BORDER};
                selection-background-color: {C_GREEN_GLOW};
            }}
            """
        )
        h.addWidget(cb)


# ──────────────────────────────────────────────────────────────────────────────
# Scroll Panel wrapper
# ──────────────────────────────────────────────────────────────────────────────
def make_scroll_panel(content_widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidget(content_widget)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setAutoFillBackground(False)
    scroll.viewport().setStyleSheet("background:transparent;")
    scroll.setStyleSheet(
        f"QScrollArea {{ background: transparent; border: none; }}"
        f"QScrollBar:vertical {{ background:{C_SIDEBAR}; width:6px; border-radius:3px; }}"
        f"QScrollBar::handle:vertical {{ background:{C_GREEN_DIM}; border-radius:3px; min-height:20px; }}"
        f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
    )
    return scroll


# ──────────────────────────────────────────────────────────────────────────────
# Content Panels
# ──────────────────────────────────────────────────────────────────────────────

def _action_button(text: str, bg: str, fg: str = None) -> QPushButton:
    if fg is None:
        fg = C_TEXT
    btn = QPushButton(text)
    btn.setFont(QFont("Segoe UI", 10))
    btn.setFixedHeight(44)
    btn.setStyleSheet(
        f"QPushButton{{background:{bg};color:{fg};border:1px solid {C_BORDER};"
        f"border-radius:10px;text-align:left;padding-left:14px;}}"
        f"QPushButton:hover{{border-color:{C_GREEN};}}"
    )
    return btn


def make_dashboard_panel() -> tuple:
    panel = QWidget()
    panel.setStyleSheet("background: transparent;")
    root_v = QVBoxLayout(panel)
    root_v.setContentsMargins(0, 0, 0, 0)
    root_v.setSpacing(16)

    # Title bar
    top_bar = QWidget()
    top_bar.setStyleSheet("background:transparent;")
    top_h = QHBoxLayout(top_bar)
    top_h.setContentsMargins(0, 0, 0, 0)
    top_h.setSpacing(8)

    left_titles = QVBoxLayout()
    left_titles.setSpacing(2)
    t = QLabel("Dashboard")
    t.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
    t.setStyleSheet(f"color:{C_TEXT}; background:transparent; border:none;")
    s = QLabel("Welcome to Deadlock Tweaker")
    s.setFont(QFont("Segoe UI", 11))
    s.setStyleSheet(f"color:{C_TEXT_DIM}; background:transparent; border:none;")
    left_titles.addWidget(t)
    left_titles.addWidget(s)
    top_h.addLayout(left_titles)
    top_h.addStretch()

    profile_cb = RoundedComboBox()
    profile_cb.addItem("Default Profile")
    profile_cb.setFixedWidth(175)
    profile_cb.setFixedHeight(36)
    profile_cb.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
    profile_cb.setStyleSheet(
        f"""
        QComboBox {{
            background: {C_CARD};
            color: {C_TEXT};
            border: 1px solid {C_BORDER};
            border-radius: 9px;
            padding: 0px 12px;
        }}
        QComboBox:hover {{
            border-color: {C_GREEN_DIM};
            background: {C_CARD2};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: right center;
            width: 28px;
            border: none;
            border-left: 1px solid {C_BORDER};
            border-top-right-radius: 9px;
            border-bottom-right-radius: 9px;
        }}
        QComboBox::down-arrow {{
            image: none;
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {C_TEXT_DIM};
        }}
        QComboBox QAbstractItemView {{
            background: {C_CARD};
            color: {C_TEXT};
            border: 1px solid {C_BORDER};
            border-radius: 9px;
            padding: 4px;
            outline: none;
            selection-background-color: {C_GREEN_GLOW};
            selection-color: {C_GREEN};
        }}
        QComboBox QAbstractItemView::item {{
            height: 30px;
            padding-left: 10px;
            border-radius: 6px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background: {C_GREEN_GLOW};
            color: {C_GREEN};
        }}
        """
    )
    top_h.addWidget(profile_cb)

    _btn_add = _btn_del = None
    for sym, tip in (("+", "Сохранить текущие настройки как новый профиль"), ("✕", "Удалить выбранный профиль")):
        b = QPushButton(sym)
        b.setFixedSize(36, 36)
        b.setToolTip(tip)
        b.setFont(QFont("Segoe UI", 13))
        b.setStyleSheet(
            f"QPushButton{{background:{C_CARD};color:{C_TEXT_DIM};border:1px solid {C_BORDER};"
            f"border-radius:9px;}}"
            f"QPushButton:hover{{background:{C_GREEN_GLOW};color:{C_GREEN};border-color:{C_GREEN_DIM};}}"
        )
        top_h.addWidget(b)
        if sym == "+":
            _btn_add = b
        else:
            _btn_del = b

    root_v.addWidget(top_bar)

    cfg_found = find_autoexec() is not None
    cfg_color = C_GREEN if cfg_found else "#ff4c4c"
    cfg_text  = "Detected" if cfg_found else "Not Found"

    # Stat strip
    strip = QHBoxLayout()
    strip.setSpacing(12)
    strip.addWidget(StatCard("≡", "Active Profile", "Default Profile", C_TEXT_MID))
    _cfg_card = StatCard("📄",  "Config Detected", cfg_text, cfg_color)
    strip.addWidget(_cfg_card)
    strip.addWidget(StatCard("⛨", "Protection", "Enabled", C_GREEN))
    _upd_card = StatCard("⏰", "Last Updated", "Never", C_TEXT_MID)
    strip.addWidget(_upd_card)
    root_v.addLayout(strip)

    # Main grid
    grid = QGridLayout()
    grid.setSpacing(12)

    # Visuals card
    vc = QFrame()
    vc.setStyleSheet(card_style(14))
    shadow(vc)
    vcl = QVBoxLayout(vc)
    vcl.setContentsMargins(16, 14, 16, 14)
    vcl.setSpacing(8)
    vcl.addWidget(section_header("Visuals", "◎"))
    _sref = {}
    for key, lbl, val, mn, mx, cur in [
        ("fov",           "FOV",           "110", 60,  150, 110),
        ("brightness",    "Brightness",    "1.20",  0,  200, 120),
        ("contrast",      "Contrast",      "1.10",  0,  200, 110),
        ("saturation",    "Saturation",    "1.15",  0,  200, 115),
        ("color_vibrance","Color Vibrance","1.00",  0,  200, 100),
        ("sharpen",       "Sharpen",       "0.60",  0,  200,  60),
    ]:
        row = SliderRow(lbl, val, mn, mx, cur)
        _sref[key] = row.slider
        vcl.addWidget(row)

    # ESP row
    esp_row = QFrame()
    esp_row.setStyleSheet(f"QFrame{{background:{C_CARD2};border-radius:10px;border:1px solid {C_BORDER};}}")
    esp_h = QHBoxLayout(esp_row)
    esp_h.setContentsMargins(14, 8, 14, 8)
    esp_lbl = QLabel("ESP")
    esp_lbl.setFont(QFont("Segoe UI", 10))
    esp_lbl.setStyleSheet(f"color:{C_TEXT_MID};background:transparent;border:none;")
    esp_h.addWidget(esp_lbl)
    esp_toggle = ToggleSwitch(initial=True)
    esp_h.addWidget(esp_toggle)
    esp_h.addSpacing(10)
    esp_cb = RoundedComboBox()
    esp_cb.addItems(["Enemy Highlight", "Full ESP", "Off"])
    esp_cb.setFixedWidth(140)
    esp_cb.setStyleSheet(
        f"QComboBox{{background:{C_GREEN};color:#000;border:none;border-radius:8px;"
        f"padding:4px 8px;font-weight:600;}}"
        f"QComboBox::drop-down{{border:none;width:18px;}}"
        f"QComboBox QAbstractItemView{{background:{C_CARD2};color:{C_TEXT};"
        f"border:1px solid {C_BORDER};selection-background-color:{C_GREEN_GLOW};}}"
    )
    esp_h.addWidget(esp_cb)
    esp_h.addStretch()
    vcl.addWidget(esp_row)
    vcl.addStretch()
    _sref["esp_enabled"] = esp_toggle
    _sref["esp_mode"] = esp_cb
    grid.addWidget(vc, 0, 0)

    # Gameplay card
    gc = QFrame()
    gc.setStyleSheet(card_style(14))
    shadow(gc)
    gcl = QVBoxLayout(gc)
    gcl.setContentsMargins(16, 14, 16, 14)
    gcl.setSpacing(8)
    gcl.addWidget(section_header("Gameplay", "⚙"))
    for key, lbl, init in [
        ("auto_parry",       "Auto Parry",        True),
        ("auto_sprint",      "Auto Sprint",        True),
        ("slide_enhancer",   "Slide Enhancer",     True),
        ("bullet_prediction","Bullet Prediction",  True),
    ]:
        tr = ToggleRow(lbl, init)
        _sref[key] = tr.toggle
        gcl.addWidget(tr)
    stamina_row = ComboRow("Stamina Helper", ["Normal", "Enhanced", "Off"])
    _sref["stamina_helper"] = stamina_row.findChild(QComboBox)
    gcl.addWidget(stamina_row)
    cd_row = SliderRow("Ability Cooldown", "0.85", 0, 200, 85)
    _sref["ability_cooldown"] = cd_row.slider
    gcl.addWidget(cd_row)
    gcl.addStretch()
    grid.addWidget(gc, 0, 1)

    _apply_btn_ref: list = []  # mutable container to pass button reference out

    # Quick Actions card
    qa = QFrame()
    qa.setStyleSheet(card_style(14))
    shadow(qa)
    qal = QVBoxLayout(qa)
    qal.setContentsMargins(16, 14, 16, 14)
    qal.setSpacing(8)
    qal.addWidget(section_header("Quick Actions"))
    apply_btn = _action_button("✔  Apply Changes", C_GREEN, "#000")
    qal.addWidget(apply_btn)
    _apply_btn_ref.append(apply_btn)
    qal.addWidget(_action_button("✕  Discard Changes", "#2a0a0d", "#e04859"))
    qal.addWidget(_action_button("↺  Reload Game Config", C_CARD2))
    qal.addWidget(_action_button("↺  Reset All Settings", C_CARD2))
    qal.addSpacing(8)
    qal.addWidget(section_header("Information"))
    info_g = QGridLayout()
    info_g.setSpacing(4)
    for i, (k, v, vc2) in enumerate([
        ("Version", APP_VERSION, C_TEXT),
        ("Build", "2026.04.15", C_TEXT),
        ("Author", "Deadlock Tweaker Team", C_TEXT),
        ("Status", "Up to date", C_GREEN),
    ]):
        kl = QLabel(k)
        kl.setFont(QFont("Segoe UI", 9))
        kl.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        vl = QLabel(v)
        vl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        vl.setStyleSheet(f"color:{vc2};background:transparent;border:none;")
        info_g.addWidget(kl, i, 0)
        info_g.addWidget(vl, i, 1)
    qal.addLayout(info_g)
    qal.addStretch()
    upd = QPushButton("↓  Check for Updates")
    upd.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    upd.setFixedHeight(44)
    upd.setStyleSheet(
        f"QPushButton{{background:{C_CARD2};color:{C_TEXT};border:1px solid {C_GREEN_DIM};"
        f"border-radius:10px;text-align:center;}}"
        f"QPushButton:hover{{background:{C_GREEN_GLOW};color:{C_GREEN};}}"
    )
    qal.addWidget(upd)
    upd_progress = QProgressBar()
    upd_progress.setRange(0, 100)
    upd_progress.setValue(0)
    upd_progress.setTextVisible(False)
    upd_progress.setFixedHeight(8)
    upd_progress.setVisible(False)
    upd_progress.setStyleSheet(
        f"QProgressBar{{background:{C_CARD2};border:1px solid {C_BORDER};border-radius:4px;}}"
        f"QProgressBar::chunk{{background:{C_GREEN};border-radius:4px;}}"
    )
    qal.addWidget(upd_progress)
    grid.addWidget(qa, 0, 2)

    # Network card
    nc = QFrame()
    nc.setStyleSheet(card_style(14))
    shadow(nc)
    ncl = QVBoxLayout(nc)
    ncl.setContentsMargins(16, 14, 16, 14)
    ncl.setSpacing(8)
    ncl.addWidget(section_header("Network", "〜"))
    ping_row = QFrame()
    ping_row.setStyleSheet(f"QFrame{{background:{C_CARD2};border-radius:10px;border:1px solid {C_BORDER};}}")
    ph = QHBoxLayout(ping_row)
    ph.setContentsMargins(14, 8, 14, 8)
    pl = QLabel("Ping Spoof")
    pl.setFont(QFont("Segoe UI", 10))
    pl.setStyleSheet(f"color:{C_TEXT_MID};background:transparent;border:none;")
    ph.addWidget(pl)
    ping_toggle = ToggleSwitch(initial=True)
    ph.addWidget(ping_toggle)
    ph.addSpacing(8)
    pe = QLineEdit("42")
    pe.setFixedWidth(56)
    pe.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pe.setStyleSheet(
        f"QLineEdit{{background:{C_CARD};color:{C_TEXT};border:1px solid {C_BORDER};"
        f"border-radius:6px;padding:4px;font-weight:bold;}}"
    )
    ph.addWidget(pe)
    ms = QLabel("ms")
    ms.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
    ph.addWidget(ms)
    ph.addStretch()
    ncl.addWidget(ping_row)
    pl_row = SliderRow("Packet Loss", "0%", 0, 100, 0)
    rl_row = ComboRow("Rate Limit", ["Disabled", "1 Mbps", "5 Mbps", "10 Mbps"])
    ncl.addWidget(pl_row)
    ncl.addWidget(rl_row)
    ncl.addStretch()
    _sref["ping_spoof"] = ping_toggle
    _sref["ping_value"] = pe
    _sref["packet_loss"] = pl_row.slider
    _sref["rate_limit"] = rl_row.findChild(QComboBox)
    grid.addWidget(nc, 1, 0)

    # Misc card
    mc = QFrame()
    mc.setStyleSheet(card_style(14))
    shadow(mc)
    mcl = QVBoxLayout(mc)
    mcl.setContentsMargins(16, 14, 16, 14)
    mcl.setSpacing(8)
    mcl.addWidget(section_header("Misc", "···"))
    for key, lbl, init in [
        ("unlock_console", "Unlock Console", True),
        ("remove_fog",     "Remove Fog",     True),
        ("streamer_mode",  "Streamer Mode",  False),
    ]:
        tr = ToggleRow(lbl, init)
        _sref[key] = tr.toggle
        mcl.addWidget(tr)
    cc_row = ComboRow("Custom Crosshair", ["Crosshair 1", "Crosshair 2", "Off"])
    _sref["custom_crosshair"] = cc_row.findChild(QComboBox)
    mcl.addWidget(cc_row)
    mcl.addStretch()
    grid.addWidget(mc, 1, 1)

    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    grid.setColumnStretch(2, 1)
    root_v.addLayout(grid)

    scroll = make_scroll_panel(panel)
    return scroll, _cfg_card, _upd_card, _apply_btn_ref[0] if _apply_btn_ref else None, upd, upd_progress, profile_cb, _btn_add, _btn_del, _sref


def make_settings_panel(current_transparency: int = DEFAULT_APP_TRANSPARENCY) -> tuple[QScrollArea, QSlider]:
    panel = QWidget()
    panel.setStyleSheet("background:transparent;")
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(16)
    v.addWidget(section_header("Settings", "⚙"))

    transparency_card = QFrame()
    transparency_card.setStyleSheet(card_style(14))
    shadow(transparency_card)
    transparency_layout = QVBoxLayout(transparency_card)
    transparency_layout.setContentsMargins(16, 14, 16, 14)
    transparency_layout.setSpacing(10)

    transparency_layout.addWidget(section_header("Window Transparency", "◌"))

    hint = QLabel("Adjust the transparency of the empty application background from 0% to 100%.")
    hint.setWordWrap(True)
    hint.setFont(QFont("Segoe UI", 10))
    hint.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
    transparency_layout.addWidget(hint)

    transparency_row = SliderRow("Transparency", f"{current_transparency}%", 0, 100, current_transparency)
    transparency_row.val_lbl.setText(f"{current_transparency}%")
    transparency_row.slider.valueChanged.connect(
        lambda value, label=transparency_row.val_lbl: label.setText(f"{value}%")
    )
    transparency_layout.addWidget(transparency_row)

    transparency_layout.addStretch()
    v.addWidget(transparency_card)
    v.addStretch()
    return make_scroll_panel(panel), transparency_row.slider


def _stub_panel(title: str, icon: str = "") -> QScrollArea:
    panel = QWidget()
    panel.setStyleSheet("background:transparent;")
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(12)
    v.addWidget(section_header(title, icon))
    stub = QLabel(f"{title}\n— Скоро —")
    stub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    stub.setFont(QFont("Segoe UI", 12))
    stub.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
    v.addWidget(stub)
    v.addStretch()
    return make_scroll_panel(panel)


def make_visuals_panel() -> QScrollArea:
    panel = QWidget()
    panel.setStyleSheet("background:transparent;")
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(12)
    v.addWidget(section_header("Visuals", "◎"))
    card = QFrame()
    card.setStyleSheet(card_style(14))
    cl = QVBoxLayout(card)
    cl.setContentsMargins(16, 14, 16, 14)
    cl.setSpacing(8)
    for lbl, val, mn, mx, cur in [
        ("FOV", "110", 60, 150, 110),
        ("Brightness", "1.20", 0, 200, 120),
        ("Contrast", "1.10", 0, 200, 110),
        ("Saturation", "1.15", 0, 200, 115),
        ("Color Vibrance", "1.00", 0, 200, 100),
        ("Sharpen", "0.60", 0, 200, 60),
    ]:
        cl.addWidget(SliderRow(lbl, val, mn, mx, cur))
    v.addWidget(card)
    v.addStretch()
    return make_scroll_panel(panel)


def make_gameplay_panel() -> QScrollArea:
    panel = QWidget()
    panel.setStyleSheet("background:transparent;")
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(12)
    v.addWidget(section_header("Gameplay", "⚙"))
    card = QFrame()
    card.setStyleSheet(card_style(14))
    cl = QVBoxLayout(card)
    cl.setContentsMargins(16, 14, 16, 14)
    cl.setSpacing(8)
    for lbl, init in [("Auto Parry", True), ("Auto Sprint", True),
                       ("Slide Enhancer", True), ("Bullet Prediction", True)]:
        cl.addWidget(ToggleRow(lbl, init))
    cl.addWidget(ComboRow("Stamina Helper", ["Normal", "Enhanced", "Off"]))
    cl.addWidget(SliderRow("Ability Cooldown", "0.85", 0, 200, 85))
    v.addWidget(card)
    v.addStretch()
    return make_scroll_panel(panel)


def make_network_panel() -> QScrollArea:
    panel = QWidget()
    panel.setStyleSheet("background:transparent;")
    v = QVBoxLayout(panel)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(12)
    v.addWidget(section_header("Network", "〜"))
    card = QFrame()
    card.setStyleSheet(card_style(14))
    cl = QVBoxLayout(card)
    cl.setContentsMargins(16, 14, 16, 14)
    cl.setSpacing(8)
    cl.addWidget(SliderRow("Packet Loss", "0%", 0, 100, 0))
    cl.addWidget(ComboRow("Rate Limit", ["Disabled", "1 Mbps", "5 Mbps", "10 Mbps"]))
    v.addWidget(card)
    v.addStretch()
    return make_scroll_panel(panel)


# ──────────────────────────────────────────────────────────────────────────────
# Update checker — runs in background thread, never blocks UI
# ──────────────────────────────────────────────────────────────────────────────
def _github_api_headers() -> dict:
    """Headers for public GitHub API and release asset requests."""
    return {
        "User-Agent": f"DeadlockTweaker/{APP_VERSION}",
        "Accept": "application/vnd.github+json",
    }


def _normalize_release_version(tag: str) -> str:
    return str(tag or "").strip().lstrip("vV")


def _pick_release_assets(assets: list[dict]) -> tuple[str, str]:
    """
    Return (patch_url, exe_url) from release asset list.
    patch_url: URL of main_patch.py if present (quick/small update)
    exe_url:   URL of DeadlockTweaker.exe  if present (full update)
    """
    patch_url = ""
    exe_url   = ""
    for asset in assets:
        name = asset.get("name", "")
        url  = asset.get("browser_download_url", "")
        if not url:
            continue
        if name == PATCH_ASSET_NAME:
            patch_url = url
        elif name == UPDATE_ASSET_NAME:
            exe_url = url
    return patch_url, exe_url


class UpdateChecker(QObject):
    """Fetches the latest public GitHub release in a QThread."""
    finished  = pyqtSignal(dict)   # emitted with parsed JSON on success
    error     = pyqtSignal(str)    # emitted with message on failure
    progress  = pyqtSignal(int, int)  # downloaded bytes, total bytes

    def check(self):
        try:
            req = urllib.request.Request(UPDATE_API_URL, headers=_github_api_headers())
            with urllib.request.urlopen(req, timeout=8) as resp:
                release = json.loads(resp.read().decode())

            version = _normalize_release_version(release.get("tag_name", ""))
            if not version:
                raise RuntimeError("Latest release has no tag name")

            patch_url, exe_url = _pick_release_assets(release.get("assets") or [])
            download_url = patch_url or exe_url
            if not download_url:
                raise RuntimeError(
                    "Latest release has no downloadable asset"
                )

            self.finished.emit({
                "version": version,
                "notes": (release.get("body") or "").strip(),
                "download_url": download_url,
                "is_patch": bool(patch_url),
                "html_url": release.get("html_url", UPDATE_RELEASES_URL),
            })
        except Exception as exc:
            self.error.emit(str(exc))

    def download(self, url: str, dest: str):
        """Download new executable to dest path; emits finished({}) or error."""
        try:
            req = urllib.request.Request(url, headers=_github_api_headers())
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                self.progress.emit(downloaded, total)
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(262144)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)
            self.finished.emit({"downloaded": dest, "bytes": downloaded})
        except Exception as exc:
            self.error.emit(str(exc))


def _version_tuple(v: str):
    """Convert '1.2.3' → (1, 2, 3) for comparison."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0,)


# ── Update cache / install helpers ───────────────────────────────────────────
def _app_dir() -> Path:
    """Runtime directory: works for both frozen (PyInstaller) and source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _update_exe_path() -> Path:
    # Staged name — avoids locking the currently running exe
    return _app_dir() / "DeadlockTweaker_new.exe"


def _patch_file_path() -> Path:
    """Path for a downloaded quick-patch (tiny main_patch.py)."""
    return _app_dir() / "deadlock_patch.py"


def _update_meta_path() -> Path:
    return _app_dir() / "_update_meta.json"


def _read_update_cache() -> dict:
    try:
        return json.loads(_update_meta_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_update_cache(version: str) -> None:
    try:
        _update_meta_path().write_text(
            json.dumps({"cached_version": version}), encoding="utf-8"
        )
    except Exception:
        pass


def _clear_update_cache() -> None:
    try:
        _update_meta_path().unlink(missing_ok=True)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Deadlock Tweaker v1.0")
        # Scale initial size and minimum to the primary screen's available area
        _avail = QApplication.primaryScreen().availableGeometry()
        _sw, _sh = _avail.width(), _avail.height()
        _iw = max(900, min(1160, int(_sw * 0.78)))
        _ih = max(580, min(740, int(_sh * 0.82)))
        self.setMinimumSize(max(800, int(_sw * 0.55)), max(520, int(_sh * 0.60)))
        self.resize(_iw, _ih)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self._drag_pos = None
        self._watcher_thread = None
        self._game_timer = QTimer(self)
        self._cfg_timer = QTimer(self)
        self._win_maximized = False
        self._normal_geo: QRect | None = None
        self._anim_max: QTimer | None = None
        self._transparency_percent = DEFAULT_APP_TRANSPARENCY
        self._transparency_timer = QTimer(self)
        self._transparency_timer.setSingleShot(True)
        self._transparency_timer.timeout.connect(lambda: self._apply_blur(tries_left=2))

        outer = QWidget(self)
        outer.setObjectName("outer")
        outer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        outer.setAutoFillBackground(False)
        outer.setStyleSheet("#outer { background: transparent; border: none; }")
        self.setCentralWidget(outer)

        main_h = QHBoxLayout(outer)
        main_h.setContentsMargins(0, 0, 0, 0)
        main_h.setSpacing(0)

        # ── Sidebar ────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            f"#sidebar {{ background: rgba(17,17,17,200); border-top-left-radius:16px;"
            f"border-bottom-left-radius:16px; border-right:1px solid rgba(255,255,255,18); }}"
        )
        sidebar.setContentsMargins(0, 0, 0, 0)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 16)
        sb.setSpacing(0)
        sb.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Logo — full width, no side margins
        logo_icon = QLabel()
        logo_icon.setFixedSize(220, 220)
        logo_icon.setContentsMargins(0, 0, 0, 0)
        logo_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        logo_icon.setStyleSheet(
            "background:transparent; border:none;"
        )
        _logo_path = Path(__file__).resolve().parent / "logoicon.png"
        if _logo_path.exists():
            _full = QPixmap(str(_logo_path))
            _pix = _full.scaled(
                220, 220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            logo_icon.setPixmap(_pix)
        else:
            logo_icon.setText("◎")
            logo_icon.setFont(QFont("Segoe UI", 40))
            logo_icon.setStyleSheet(f"color:{C_GREEN}; background:transparent; border:none;")
        sb.addWidget(logo_icon, 0, Qt.AlignmentFlag.AlignHCenter)

        sb.addSpacing(4)

        nav_items = [
            ("\uE80F", "Dashboard", 0),
            ("\uE8FB", "Visuals",   1),
            ("\uE7FC", "Gameplay",  2),
            ("\uE701", "Network",   3),
            ("\uE765", "Hotkeys",   4),
            ("\uE712", "Misc",      5),
            ("\uE716", "Profiles",  6),
            ("\uE713", "Settings",  7),
        ]
        self._nav_buttons: list[NavButton] = []

        nav_wrapper = QWidget()
        nav_wrapper.setStyleSheet("background:transparent;")
        nav_vbox = QVBoxLayout(nav_wrapper)
        nav_vbox.setContentsMargins(10, 0, 10, 0)
        nav_vbox.setSpacing(2)

        for icon, label, idx in nav_items:
            btn = NavButton(icon, label)
            btn.clicked.connect(lambda _, i=idx: self._switch_page(i))
            self._nav_buttons.append(btn)
            nav_vbox.addWidget(btn)

        sb.addWidget(nav_wrapper)

        sb.addStretch()

        # Status box
        status_box = QFrame()
        status_box.setStyleSheet(
            f"QFrame{{background:{C_CARD};border-radius:10px;border:1px solid {C_BORDER};}}"
        )
        stv = QVBoxLayout(status_box)
        stv.setContentsMargins(12, 10, 12, 10)
        stv.setSpacing(4)
        dot_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;font-size:10px;")
        self._status_gl = QLabel("Game not detected")
        self._status_gl.setFont(QFont("Segoe UI", 9))
        self._status_gl.setStyleSheet(f"color:{C_TEXT_DIM};background:transparent;border:none;")
        dot_row.addWidget(self._status_dot)
        dot_row.addWidget(self._status_gl)
        dot_row.addStretch()
        stv.addLayout(dot_row)
        nr = QHBoxLayout()
        gn = QLabel("Deadlock")
        gn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        gn.setStyleSheet(f"color:{C_TEXT};background:transparent;border:none;")
        self._status_rv = QLabel("Not Running")
        self._status_rv.setFont(QFont("Segoe UI", 9))
        self._status_rv.setStyleSheet(f"color:#ff4c4c;background:transparent;border:none;")
        nr.addWidget(gn)
        nr.addStretch()
        nr.addWidget(self._status_rv)
        stv.addLayout(nr)

        # Game detection — background thread
        self._game_watcher = GameWatcher()
        self._watcher_thread = QThread(self)
        self._game_watcher.moveToThread(self._watcher_thread)
        self._game_watcher.status_changed.connect(self._on_game_status)
        self._watcher_thread.start()
        self._game_timer.setInterval(2000)
        self._game_timer.timeout.connect(self._game_watcher.check)
        self._game_timer.start()
        # initial check
        QTimer.singleShot(100, self._game_watcher.check)

        # Config file detection timer (every 5 sec)
        self._cfg_timer.setInterval(5000)
        self._cfg_timer.timeout.connect(self._check_config)
        self._cfg_timer.start()
        status_wrap = QWidget()
        status_wrap.setStyleSheet("background:transparent;")
        sw_layout = QVBoxLayout(status_wrap)
        sw_layout.setContentsMargins(10, 0, 10, 8)
        sw_layout.setSpacing(8)

        sw_layout.addWidget(status_box)

        sb.addWidget(status_wrap)
        main_h.addWidget(sidebar)

        # ── Right side ─────────────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet("background:transparent;")
        rv2 = QVBoxLayout(right)
        rv2.setContentsMargins(0, 0, 0, 0)
        rv2.setSpacing(0)

        # Custom title bar
        tb = QFrame()
        tb.setFixedHeight(44)
        tb.setStyleSheet("QFrame{background:transparent;border:none;}")
        tbh = QHBoxLayout(tb)
        tbh.setContentsMargins(16, 0, 0, 0)
        tbh.setSpacing(0)
        tbh.addStretch()

        for sym, action in [("─", self.showMinimized), ("□", self._toggle_max), ("✕", self.close)]:
            b = QPushButton(sym)
            # Fill full height of title bar; width matches height → square hit area
            b.setFixedSize(44, 44)
            b.setStyleSheet(
                f"QPushButton{{background:transparent;color:{C_TEXT_DIM};border:none;"
                f"font-size:14px;border-radius:0px;padding:0px;}}"
                f"QPushButton:hover{{background:{_THEMES[_CURRENT_THEME]['titlebar_hover']};color:{C_TEXT};}}"
            )
            b.clicked.connect(action)
            tbh.addWidget(b)
            if action == self._toggle_max:
                self._btn_max = b
        rv2.addWidget(tb)

        # Stacked pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent;")
        self._stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._stack.setContentsMargins(24, 8, 24, 24)

        dashboard_panel, self._cfg_card, self._upd_card, apply_btn, upd_btn, \
            self._upd_progress, self._profile_cb, btn_add, btn_del, self._sref = make_dashboard_panel()
        if apply_btn:
            apply_btn.clicked.connect(self._on_apply_changes)
        upd_btn.clicked.connect(self._on_check_update)
        self._upd_btn = upd_btn
        self._upd_btn_default_text = upd_btn.text()
        self._upd_btn_default_style = upd_btn.styleSheet()
        self._upd_thread: QThread | None = None
        self._upd_worker: UpdateChecker | None = None
        self._pending_download_url: str = ""
        self._pending_update_version: str = ""
        self._pending_is_patch: bool = False

        # Remove stale cache if update exe is missing (e.g. after manual cleanup)
        if not _update_exe_path().exists() and not _patch_file_path().exists():
            _clear_update_cache()

        # Profile system wiring
        self._load_profiles_into_cb()
        if btn_add:
            btn_add.clicked.connect(self._on_profile_save)
        if btn_del:
            btn_del.clicked.connect(self._on_profile_delete)
        self._profile_cb.currentTextChanged.connect(self._on_profile_switch)
        settings_panel, self._transparency_slider = make_settings_panel(self._transparency_percent)
        self._transparency_slider.valueChanged.connect(self._on_transparency_changed)
        pages = [
            dashboard_panel,
            make_visuals_panel(),
            make_gameplay_panel(),
            make_network_panel(),
            _stub_panel("Hotkeys", "⊞"),
            _stub_panel("Misc", "···"),
            _stub_panel("Profiles", "⬡"),
            settings_panel,
        ]
        for page in pages:
            self._stack.addWidget(page)

        rv2.addWidget(self._stack)
        main_h.addWidget(right, 1)

        self._switch_page(0)

    def _switch_page(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setActive(i == idx)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_input_mask()

    def _update_input_mask(self):
        """Tell Windows the exact hit-test region so transparent pixels don't let clicks through."""
        if self._win_maximized:
            self.clearMask()
            return
        bm = QBitmap(self.size())
        bm.fill(Qt.GlobalColor.color0)
        p = QPainter(bm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(Qt.GlobalColor.color1)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bm.rect(), 16, 16)
        p.end()
        self.setMask(QRegion(bm))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.isMaximized() or self._win_maximized:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.end()

    def _transparency_tint(self) -> int:
        alpha = round(255 * (100 - self._transparency_percent) / 100)
        alpha = max(0, min(alpha, 255))
        return (alpha << 24) | 0x0d0d0d

    def _on_transparency_changed(self, value: int):
        value = max(0, min(value, 100))
        if value == self._transparency_percent:
            return
        self._transparency_percent = value
        self._transparency_timer.start(45)

    def showEvent(self, event):
        super().showEvent(event)
        # Вызываем blur через два прохода event loop — HWND к тому моменту гарантированно
        # зарегистрирован в DWM и готов принять SetWindowCompositionAttribute
        QTimer.singleShot(0, lambda: self._apply_blur(tries_left=8))

    def _apply_blur(self, tries_left: int = 1):
        if _enable_acrylic_blur(int(self.winId()), tint_color=self._transparency_tint()):
            return
        if tries_left > 1:
            QTimer.singleShot(120, lambda: self._apply_blur(tries_left - 1))

    def _on_game_status(self, running: bool):
        if running:
            self._status_dot.setStyleSheet(f"color:{C_GREEN};background:transparent;border:none;font-size:10px;")
            self._status_gl.setText("Game detected")
            self._status_rv.setText("Running")
            self._status_rv.setStyleSheet(f"color:{C_GREEN};background:transparent;border:none;")
        else:
            self._status_dot.setStyleSheet("color:#ff4c4c;background:transparent;border:none;font-size:10px;")
            self._status_gl.setText("Game not detected")
            self._status_rv.setText("Not Running")
            self._status_rv.setStyleSheet("color:#ff4c4c;background:transparent;border:none;")

    def _check_config(self):
        if find_autoexec():
            self._cfg_card.set_value("Detected", C_GREEN)
        else:
            self._cfg_card.set_value("Not Found", "#ff4c4c")

    def _on_apply_changes(self):
        now = datetime.now()
        today = datetime.today().date()
        if now.date() == today:
            label = f"Today, {now.strftime('%H:%M')}"
        else:
            label = now.strftime("%d.%m.%Y, %H:%M")
        self._upd_card.set_value(label, C_GREEN)

    def _reset_update_ui(self, delay_ms: int = 0):
        def _apply_reset():
            self._upd_btn.setEnabled(True)
            self._upd_btn.setText(self._upd_btn_default_text)
            self._upd_btn.setStyleSheet(self._upd_btn_default_style)
            self._upd_btn.setToolTip("")
            self._upd_progress.setVisible(False)
            self._upd_progress.setRange(0, 100)
            self._upd_progress.setValue(0)

        if delay_ms > 0:
            QTimer.singleShot(delay_ms, _apply_reset)
        else:
            _apply_reset()

    def _start_update_download(self, version: str, url: str, is_patch: bool = False):
        self._pending_update_version = version
        self._pending_download_url = url
        self._pending_is_patch = is_patch
        self._upd_btn.setText(f"⏳  Downloading v{version}... 0%")
        self._upd_btn.setEnabled(False)
        self._upd_progress.setVisible(True)
        self._upd_progress.setRange(0, 100)
        self._upd_progress.setValue(0)

        dest = str(_patch_file_path() if is_patch else _update_exe_path())
        worker = UpdateChecker()
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(lambda: worker.download(url, dest))
        worker.progress.connect(self._on_download_progress)
        worker.finished.connect(lambda d: self._on_download_result(d))
        worker.error.connect(self._on_update_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        self._upd_worker = worker
        self._upd_thread = thread
        thread.start()

    def _on_download_progress(self, downloaded: int, total: int):
        self._upd_progress.setVisible(True)
        if total > 0:
            percent = max(0, min(100, round(downloaded * 100 / total)))
            self._upd_progress.setRange(0, 100)
            self._upd_progress.setValue(percent)
            self._upd_btn.setText(f"⏳  Downloading... {percent}%")
        else:
            self._upd_progress.setRange(0, 0)
            self._upd_btn.setText("⏳  Downloading...")

    # ── Update system ─────────────────────────────────────────────────────────
    def _run_in_thread(self, fn):
        """Start UpdateChecker worker in a fresh QThread."""
        if self._upd_thread is not None and self._upd_thread.isRunning():
            return  # already busy
        worker = UpdateChecker()
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(fn.__get__(worker, UpdateChecker))
        self._upd_worker = worker
        self._upd_thread = thread
        thread.start()

    def _on_check_update(self):
        if self._upd_thread is not None and self._upd_thread.isRunning():
            return

        self._upd_btn.setText("⏳  Checking...")
        self._upd_btn.setEnabled(False)
        self._upd_btn.setStyleSheet(self._upd_btn_default_style)
        self._upd_progress.setVisible(False)
        self._upd_progress.setRange(0, 100)
        self._upd_progress.setValue(0)
        self._pending_download_url = ""

        worker = UpdateChecker()
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.check)
        worker.finished.connect(self._on_update_result)
        worker.error.connect(self._on_update_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        self._upd_worker = worker
        self._upd_thread = thread
        thread.start()

    def _on_update_result(self, data: dict):
        latest   = data.get("version", "0")
        notes    = data.get("notes", "")
        dl_url   = data.get("download_url", "")
        is_patch = data.get("is_patch", False)

        if _version_tuple(latest) > _version_tuple(APP_VERSION):
            if not dl_url:
                self._on_update_error("Latest release has no downloadable asset")
                return

            # ── Cache check: already downloaded this exact version? ──────────
            cache       = _read_update_cache()
            cached_ver  = cache.get("cached_version", "")
            cached_file = _patch_file_path() if is_patch else _update_exe_path()
            if cached_ver == latest and cached_file.exists():
                self._upd_progress.setVisible(True)
                self._upd_progress.setRange(0, 100)
                self._upd_progress.setValue(100)
                self._upd_btn.setText(f"✓  v{latest} ready — restarting…")
                self._upd_btn.setEnabled(False)
                self._upd_card.set_value("Ready to install", C_GREEN)
                if is_patch:
                    QTimer.singleShot(1500, lambda: self._install_patch_and_restart(str(cached_file)))
                else:
                    QTimer.singleShot(1500, lambda: self._install_and_restart(str(cached_file)))
                return

            self._upd_btn.setStyleSheet(
                f"QPushButton{{background:{C_GREEN_GLOW};color:{C_GREEN};"
                f"border:1px solid {C_GREEN};border-radius:10px;text-align:center;}}"
                f"QPushButton:hover{{background:{C_GREEN};color:#000;}}"
            )
            if notes:
                self._upd_btn.setToolTip(f"What's new:\n{notes}")
            self._start_update_download(latest, dl_url, is_patch=is_patch)
        else:
            self._upd_btn.setText("✓  Up to date")
            self._upd_btn.setEnabled(True)
            self._reset_update_ui(delay_ms=3000)

    def _on_update_error(self, msg: str):
        self._upd_btn.setEnabled(True)
        self._upd_btn.setText("⚠  Check failed — retry")
        self._upd_btn.setToolTip(msg)
        self._upd_progress.setVisible(False)
        self._upd_progress.setRange(0, 100)
        self._upd_progress.setValue(0)
        self._reset_update_ui(delay_ms=4000)

    def _on_download_result(self, data: dict):
        self._upd_btn.setEnabled(True)
        dest = data.get("downloaded", "")
        if dest:
            _write_update_cache(self._pending_update_version)

            self._upd_progress.setVisible(True)
            self._upd_progress.setRange(0, 100)
            self._upd_progress.setValue(100)
            self._upd_btn.setText(f"✓  v{self._pending_update_version} — restarting…")
            self._upd_btn.setEnabled(False)
            self._pending_download_url = ""
            self._upd_card.set_value("Ready to install", C_GREEN)
            if self._pending_is_patch:
                QTimer.singleShot(1500, lambda: self._install_patch_and_restart(dest))
            else:
                QTimer.singleShot(1500, lambda: self._install_and_restart(dest))
        else:
            self._upd_btn.setText("⚠  Download failed")
            self._upd_progress.setVisible(False)
            self._reset_update_ui(delay_ms=4000)

    def _install_and_restart(self, update_exe: str):
        """
        Replace the running exe with the downloaded update via a batch script,
        then quit immediately so the file is no longer locked.
        Also removes any existing quick-patch file (the new exe has latest code).
        """
        import sys, tempfile
        if getattr(sys, "frozen", False):
            current_exe = sys.executable
            patch_file  = str(_patch_file_path())
            bat_path = os.path.join(tempfile.gettempdir(), "deadlock_selfupdate.bat")
            try:
                with open(bat_path, "w", encoding="ascii", errors="replace") as f:
                    f.write("@echo off\r\n")
                    f.write("timeout /T 3 /NOBREAK >nul\r\n")
                    f.write(f'if exist "{patch_file}" del /f "{patch_file}"\r\n')
                    f.write(f'move /y "{update_exe}" "{current_exe}"\r\n')
                    f.write(f'start "" "{current_exe}"\r\n')
                    f.write('del "%~f0"\r\n')
                subprocess.Popen(
                    ["cmd.exe", "/c", bat_path],
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except Exception:
                try:
                    os.startfile(update_exe)
                except Exception:
                    pass
        _clear_update_cache()
        QApplication.quit()

    def _install_patch_and_restart(self, patch_file: str):
        """
        Quick-patch already downloaded as deadlock_patch.py.
        Just restart the exe — the patch loader will pick it up automatically.
        """
        import sys
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen(
                    [sys.executable],
                    shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        except Exception:
            try:
                os.startfile(sys.executable)
            except Exception:
                pass
        _clear_update_cache()
        QApplication.quit()


    # ── Profile system ────────────────────────────────────────────────────────
    def _profiles_data(self) -> dict:
        if PROFILES_PATH.exists():
            try:
                return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _write_profiles(self, data: dict):
        PROFILES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_profiles_into_cb(self):
        data = self._profiles_data()
        self._profile_cb.blockSignals(True)
        current = self._profile_cb.currentText()
        self._profile_cb.clear()
        self._profile_cb.addItem("Default Profile")
        for name in data.keys():
            self._profile_cb.addItem(name)
        idx = self._profile_cb.findText(current)
        self._profile_cb.setCurrentIndex(max(0, idx))
        self._profile_cb.blockSignals(False)

    def _collect_settings(self) -> dict:
        """Read current values from all tracked setting widgets."""
        from PyQt6.QtWidgets import QSlider, QComboBox, QLineEdit
        result = {}
        for key, widget in self._sref.items():
            if widget is None:
                continue
            try:
                if isinstance(widget, QSlider):
                    result[key] = widget.value()
                elif isinstance(widget, QComboBox):
                    result[key] = widget.currentIndex()
                elif isinstance(widget, QLineEdit):
                    result[key] = widget.text()
                elif isinstance(widget, ToggleSwitch):
                    result[key] = widget.isChecked()
            except RuntimeError:
                pass
        return result

    def _apply_settings(self, settings: dict):
        """Apply saved values back to the tracked setting widgets."""
        from PyQt6.QtWidgets import QSlider, QComboBox, QLineEdit
        for key, val in settings.items():
            widget = self._sref.get(key)
            if widget is None:
                continue
            try:
                widget.blockSignals(True)
                if isinstance(widget, QSlider):
                    widget.setValue(int(val))
                elif isinstance(widget, QComboBox):
                    widget.setCurrentIndex(int(val))
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(val))
                elif isinstance(widget, ToggleSwitch):
                    widget.setChecked(bool(val))
            except RuntimeError:
                # виджет уже удалён Qt — пропускаем
                pass
            finally:
                try:
                    widget.blockSignals(False)
                except RuntimeError:
                    pass

    def _on_profile_save(self):
        data = self._profiles_data()
        existing = list(data.keys())
        dlg = ProfileNameDialog(self, existing_names=existing)
        dlg.move(
            self.geometry().center().x() - dlg.width() // 2,
            self.geometry().center().y() - dlg.height() // 2,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = dlg.profile_name
        data[name] = self._collect_settings()
        self._write_profiles(data)
        self._load_profiles_into_cb()
        self._profile_cb.setCurrentText(name)

    def _on_profile_delete(self):
        name = self._profile_cb.currentText()
        if name == "Default Profile":
            return
        data = self._profiles_data()
        data.pop(name, None)
        self._write_profiles(data)
        self._load_profiles_into_cb()

    def _on_profile_switch(self, name: str):
        if not name or name == "Default Profile":
            return
        try:
            data = self._profiles_data()
            if name in data:
                self._apply_settings(data[name])
        except Exception:
            pass

    def closeEvent(self, event):
        self._game_timer.stop()
        self._cfg_timer.stop()
        if self._watcher_thread is not None and self._watcher_thread.isRunning():
            self._game_watcher.status_changed.disconnect()
            self._watcher_thread.quit()
            self._watcher_thread.wait(2000)
        event.accept()

    def _toggle_max(self):
        screen = self.screen() or QApplication.primaryScreen()
        work_area = screen.availableGeometry()  # excludes taskbar

        # Duration scales with Hz: 200ms at 60Hz, same wall-clock at 144/240Hz
        anim_ms = 200

        if not self._win_maximized:
            from_geo = self.geometry()
            to_geo = work_area
            self._normal_geo = QRect(from_geo)   # save before animating
            self._win_maximized = True
            if hasattr(self, "_btn_max"):
                self._btn_max.setText("❐")
            self.clearMask()
        else:
            from_geo = self.geometry()
            to_geo = self._normal_geo if (self._normal_geo and self._normal_geo.isValid()) else \
                QRect(work_area.x() + (work_area.width() - 1160) // 2,
                      work_area.y() + (work_area.height() - 740) // 2,
                      1160, 740)
            self._win_maximized = False
            if hasattr(self, "_btn_max"):
                self._btn_max.setText("□")
            # mask will be applied by resizeEvent when geometry updates

        # Stop previous animation if still running
        if self._anim_max is not None:
            self._anim_max.stop()
            self._anim_max = None

        elapsed = QElapsedTimer()
        elapsed.start()
        fx = from_geo.x(); fy = from_geo.y()
        fw = from_geo.width(); fh = from_geo.height()
        tx = to_geo.x(); ty = to_geo.y()
        tw = to_geo.width(); th = to_geo.height()

        timer = QTimer(self)
        timer.setInterval(max(1, round(1000.0 / (screen.refreshRate() or 60.0))))

        def _tick():
            t = min(elapsed.elapsed() / anim_ms, 1.0)
            # smoothstep ease-out: 1-(1-t)^3
            ease = 1.0 - (1.0 - t) ** 3
            self.setGeometry(
                QRect(
                    round(fx + (tx - fx) * ease),
                    round(fy + (ty - fy) * ease),
                    round(fw + (tw - fw) * ease),
                    round(fh + (th - fh) * ease),
                )
            )
            if t >= 1.0:
                timer.stop()
                self._anim_max = None

        timer.timeout.connect(_tick)
        timer.start()
        self._anim_max = timer   # store so we can stop it if needed


    def nativeEvent(self, eventType, message):
        """Handle WM_NCHITTEST for native drag (HTCAPTION) and edge resize."""
        if eventType == b"windows_generic_MSG":
            import ctypes, ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                if self._win_maximized:
                    return super().nativeEvent(eventType, message)
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                geo = self.frameGeometry()
                lx = x - geo.x()
                ly = y - geo.y()
                w = self.width()
                h = self.height()
                r = 8  # resize border width
                # Corners (check before edges)
                if lx <= r and ly <= r:         return True, 13  # HTTOPLEFT
                if lx >= w - r and ly <= r:     return True, 14  # HTTOPRIGHT
                if lx <= r and ly >= h - r:     return True, 16  # HTBOTTOMLEFT
                if lx >= w - r and ly >= h - r: return True, 17  # HTBOTTOMRIGHT
                # Edges
                if lx <= r:     return True, 10  # HTLEFT
                if lx >= w - r: return True, 11  # HTRIGHT
                if ly <= r:     return True, 12  # HTTOP
                if ly >= h - r: return True, 15  # HTBOTTOM
                # Title bar drag area (top 44 px, excluding 3×44=132 px buttons on right)
                if ly <= 44 and lx < w - 132:
                    return True, 2  # HTCAPTION
        return super().nativeEvent(eventType, message)


# ──────────────────────────────────────────────────────────────────────────────
def main():
    # Crisp rendering on HiDPI / fractional-scale displays
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("* { font-family: 'Segoe UI'; }")

    # Show setup dialog if autoexec.cfg is not found
    if not find_autoexec():
        dlg = SetupDialog()
        dlg.move(
            app.primaryScreen().geometry().center().x() - dlg.width() // 2,
            app.primaryScreen().geometry().center().y() - dlg.height() // 2,
        )
        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()









