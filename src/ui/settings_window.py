"""Settings window using PyQt6 for MindScribe Desktop configuration.

PyQt6 version for macOS compatibility. Replaces the tkinter settings window.
Thread-safe: open() can be called from any thread via Qt signal.
"""

import logging
import platform
import re
import threading
from typing import Callable

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.settings import Settings
from src.core.audio_recorder import AudioRecorder

logger = logging.getLogger(__name__)

# OS-adaptive UI font
_UI_FONT = "SF Pro Display" if platform.system() == "Darwin" else "Segoe UI"
_MONO_FONT = "SF Mono" if platform.system() == "Darwin" else "Consolas"

# Language options: display label -> ISO-639-1 code
LANGUAGE_OPTIONS = {
    "Francais": "fr",
    "English": "en",
    "Auto-detect": "auto",
}
LANGUAGE_LABELS = list(LANGUAGE_OPTIONS.keys())

# Provider options
PROVIDER_LABELS = {"groq": "Groq (Recommended)", "openai": "OpenAI"}

# Whisper model options
MODEL_LABELS = {
    "whisper-large-v3": "whisper-large-v3 (Best accuracy)",
    "whisper-large-v3-turbo": "whisper-large-v3-turbo (Faster)",
}

# Record mode options
RECORD_MODE_LABELS = {"toggle": "Toggle (press to start/stop)", "hold": "Hold (hold to record)"}

# Hotkey presets
_IS_MAC = platform.system() == "Darwin"
_MOD = "<cmd>" if _IS_MAC else "<ctrl>"
_MOD_LABEL = "Cmd" if _IS_MAC else "Ctrl"

HOTKEY_PRESETS = {
    f"{_MOD}+<shift>+<space>": f"{_MOD_LABEL} + Shift + Space (default)",
    f"{_MOD}+<shift>+r": f"{_MOD_LABEL} + Shift + R",
    f"{_MOD}+<shift>+d": f"{_MOD_LABEL} + Shift + D",
    "<f9>": "F9",
    "<f8>": "F8",
    "<f7>": "F7",
    f"{_MOD}+<alt>+<space>": f"{_MOD_LABEL} + Alt + Space",
}
HOTKEY_PRESET_LABELS = list(HOTKEY_PRESETS.values())

# Dark theme colors
BG = "#1e1e2e"
BG_FIELD = "#2a2a3e"
FG = "#e0e0e0"
FG_DIM = "#999999"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
BTN_CANCEL_BG = "#555555"
SECTION_FG = "#ffffff"

# Global stylesheet for the settings window
_DARK_STYLESHEET = """
QWidget#settings_root {
    background-color: %(bg)s;
}
QScrollArea {
    background-color: %(bg)s;
    border: none;
}
QWidget#scroll_inner {
    background-color: %(bg)s;
}
QLabel {
    color: %(fg)s;
    background: transparent;
}
QLabel#section_label {
    color: %(section_fg)s;
    font-weight: bold;
}
QLabel#dim_label {
    color: %(fg_dim)s;
}
QComboBox {
    background-color: %(bg_field)s;
    color: %(fg)s;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 22px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid %(fg_dim)s;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: %(bg_field)s;
    color: %(fg)s;
    selection-background-color: %(accent)s;
    selection-color: white;
    border: 1px solid #444;
}
QTextEdit {
    background-color: %(bg_field)s;
    color: %(fg)s;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px;
}
QCheckBox {
    color: %(fg)s;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #666;
    background-color: %(bg_field)s;
}
QCheckBox::indicator:checked {
    background-color: %(accent)s;
    border-color: %(accent)s;
}
""" % {
    "bg": BG,
    "bg_field": BG_FIELD,
    "fg": FG,
    "fg_dim": FG_DIM,
    "section_fg": SECTION_FG,
    "accent": ACCENT,
}


class SettingsWindow(QWidget):
    """Settings dashboard window using PyQt6.

    Opens as an independent top-level window. Thread-safe via signals.
    """

    _sig_open = pyqtSignal()

    def __init__(
        self,
        settings: Settings,
        on_save: Callable[[Settings], None] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._on_save = on_save
        self._is_open = False
        self._devices: list[dict] = []
        self._hotkey_manager = None
        self._test_listener = None

        # UI widget references (populated in _build_window)
        self._lang_combo: QComboBox | None = None
        self._provider_combo: QComboBox | None = None
        self._model_combo: QComboBox | None = None
        self._model_hint: QLabel | None = None
        self._prompt_text: QTextEdit | None = None
        self._post_process_cb: QCheckBox | None = None
        self._device_combo: QComboBox | None = None
        self._mode_combo: QComboBox | None = None
        self._hotkey_combo: QComboBox | None = None
        self._test_btn: QPushButton | None = None
        self._hotkey_test_label: QLabel | None = None
        self._notif_cb: QCheckBox | None = None
        self._clipboard_cb: QCheckBox | None = None

        self._sig_open.connect(self._build_window)

    @property
    def is_open(self) -> bool:
        return self._is_open

    def set_hotkey_manager(self, manager) -> None:
        """Set reference to the HotkeyManager for pause/resume during test."""
        self._hotkey_manager = manager

    def open(self) -> None:
        """Open the settings window (thread-safe)."""
        if self._is_open:
            self.raise_()
            self.activateWindow()
            return
        self._sig_open.emit()

    # ------------------------------------------------------------------
    # Window construction (runs on Qt main thread)
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        if self._is_open:
            return
        self._is_open = True

        self.setWindowTitle("MindScribe Desktop - Settings")
        self.setObjectName("settings_root")
        self.setFixedSize(500, 600)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(_DARK_STYLESHEET)

        # Center on screen
        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                (geo.width() - 500) // 2 + geo.x(),
                (geo.height() - 600) // 2 + geo.y(),
            )

        # Clear previous layout if re-opening
        if self.layout() is not None:
            QWidget().setLayout(self.layout())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("scroll_inner")
        form = QVBoxLayout(inner)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(4)

        # --- Transcription Section ---
        self._add_section(form, "Transcription")

        # Language
        self._add_field_label(form, "Language")
        current_lang = _code_to_label(self._settings.language, LANGUAGE_OPTIONS)
        self._lang_combo = self._add_combo(form, LANGUAGE_LABELS, current_lang)

        # Provider
        self._add_field_label(form, "Primary Provider")
        provider_labels = list(PROVIDER_LABELS.values())
        current_provider = PROVIDER_LABELS.get(self._settings.primary_provider, provider_labels[0])
        self._provider_combo = self._add_combo(form, provider_labels, current_provider)
        self._provider_combo.currentTextChanged.connect(self._on_provider_changed)

        # Whisper Model
        self._add_field_label(form, "Whisper Model")
        model_labels = list(MODEL_LABELS.values())
        current_model = MODEL_LABELS.get(self._settings.whisper_model, model_labels[0])
        self._model_combo = self._add_combo(form, model_labels, current_model)

        self._model_hint = QLabel("")
        self._model_hint.setObjectName("dim_label")
        self._model_hint.setFont(QFont(_MONO_FONT, 10))
        form.addWidget(self._model_hint)
        self._on_provider_changed()

        # Prompt
        self._add_field_label(form, "Context Prompt (helps Whisper accuracy)")
        self._prompt_text = QTextEdit()
        self._prompt_text.setFont(QFont(_UI_FONT, 10))
        self._prompt_text.setFixedHeight(70)
        self._prompt_text.setPlainText(self._settings.prompt)
        form.addWidget(self._prompt_text)
        self._add_spacer(form)

        # Post-processing
        self._post_process_cb = QCheckBox("Clean up text with LLM (fix punctuation, remove fillers)")
        self._post_process_cb.setFont(QFont(_UI_FONT, 10))
        self._post_process_cb.setChecked(self._settings.post_process)
        form.addWidget(self._post_process_cb)
        self._add_spacer(form)

        # --- Recording Section ---
        self._add_section(form, "Recording")

        # Microphone
        self._add_field_label(form, "Microphone")
        self._device_combo = self._add_combo(form, ["Loading..."], "Loading...")
        threading.Thread(target=self._load_devices, daemon=True).start()

        # Record Mode
        self._add_field_label(form, "Record Mode")
        mode_labels = list(RECORD_MODE_LABELS.values())
        current_mode = RECORD_MODE_LABELS.get(self._settings.record_mode, mode_labels[0])
        self._mode_combo = self._add_combo(form, mode_labels, current_mode)

        # Hotkey
        self._add_field_label(form, "Hotkey")
        hotkey_row = QHBoxLayout()
        current_hotkey_label = _combo_to_preset_label(self._settings.hotkey)
        self._hotkey_combo = QComboBox()
        self._hotkey_combo.addItems(HOTKEY_PRESET_LABELS)
        self._hotkey_combo.setCurrentText(current_hotkey_label)
        self._hotkey_combo.setMinimumWidth(250)
        hotkey_row.addWidget(self._hotkey_combo)

        self._test_btn = QPushButton("  Test  ")
        self._test_btn.setFont(QFont(_UI_FONT, 9))
        self._test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_btn.setStyleSheet(
            "QPushButton { background-color: %s; color: white; border: none;"
            " padding: 5px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: %s; }" % (ACCENT, ACCENT_HOVER)
        )
        self._test_btn.clicked.connect(self._test_hotkey)
        hotkey_row.addWidget(self._test_btn)
        hotkey_row.addStretch()
        form.addLayout(hotkey_row)

        self._hotkey_test_label = QLabel("")
        self._hotkey_test_label.setObjectName("dim_label")
        self._hotkey_test_label.setFont(QFont(_MONO_FONT, 10))
        form.addWidget(self._hotkey_test_label)
        self._add_spacer(form)

        # --- Application Section ---
        self._add_section(form, "Application")

        self._notif_cb = QCheckBox("Show notifications")
        self._notif_cb.setFont(QFont(_UI_FONT, 10))
        self._notif_cb.setChecked(self._settings.show_notifications)
        form.addWidget(self._notif_cb)

        self._clipboard_cb = QCheckBox("Restore clipboard after paste")
        self._clipboard_cb.setFont(QFont(_UI_FONT, 10))
        self._clipboard_cb.setChecked(self._settings.restore_clipboard)
        form.addWidget(self._clipboard_cb)

        form.addStretch()
        scroll.setWidget(inner)
        main_layout.addWidget(scroll)

        # --- Buttons (fixed at bottom) ---
        btn_frame = QWidget()
        btn_frame.setStyleSheet("background-color: %s;" % BG)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(16, 8, 16, 16)

        btn_layout.addStretch()

        cancel_btn = QPushButton("  Cancel  ")
        cancel_btn.setFont(QFont(_UI_FONT, 10))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: %s; color: #ccc; border: none;"
            " padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #666; }" % BTN_CANCEL_BG
        )
        cancel_btn.clicked.connect(self._on_close)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("  Save  ")
        save_btn.setFont(QFont(_UI_FONT, 10, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton { background-color: %s; color: white; border: none;"
            " padding: 6px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: %s; }" % (ACCENT, ACCENT_HOVER)
        )
        save_btn.clicked.connect(self._on_save_click)
        btn_layout.addWidget(save_btn)

        main_layout.addWidget(btn_frame)

        self.show()
        logger.info("Settings window opened")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_section(layout: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("section_label")
        label.setFont(QFont(_UI_FONT, 12, QFont.Weight.Bold))
        layout.addWidget(label)

    @staticmethod
    def _add_field_label(layout: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setFont(QFont(_UI_FONT, 10))
        label.setContentsMargins(12, 0, 0, 0)
        layout.addWidget(label)

    @staticmethod
    def _add_combo(layout: QVBoxLayout, items: list[str], current: str) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(current)
        combo.setMinimumWidth(320)
        layout.addWidget(combo)
        return combo

    @staticmethod
    def _add_spacer(layout: QVBoxLayout) -> None:
        spacer = QWidget()
        spacer.setFixedHeight(8)
        spacer.setStyleSheet("background: transparent;")
        layout.addWidget(spacer)

    # ------------------------------------------------------------------
    # Hotkey test
    # ------------------------------------------------------------------

    def _test_hotkey(self) -> None:
        from pynput import keyboard as kb
        from src.core.hotkey_manager import _parse_hotkey_keys, _pynput_key_to_id

        combo_label = self._hotkey_combo.currentText()
        combo = _preset_label_to_combo(combo_label)
        hotkey_keys = _parse_hotkey_keys(combo)

        self._hotkey_test_label.setText(f"Press {combo_label} now...")
        self._hotkey_test_label.setStyleSheet("color: %s;" % ACCENT)
        self._test_btn.setEnabled(False)
        self._test_btn.setText(" Testing... ")

        # Pause the app's hotkey listener during test
        if self._hotkey_manager is not None:
            self._hotkey_manager.pause()

        test_detected = False
        result_shown = False
        pressed_keys: set[str] = set()

        def on_press(key):
            nonlocal test_detected
            key_id = _pynput_key_to_id(key)
            if not key_id:
                return
            pressed_keys.add(key_id)
            if hotkey_keys.issubset(pressed_keys):
                test_detected = True
                QTimer.singleShot(0, check_result)
                return False  # Stop listener

        def on_release(key):
            key_id = _pynput_key_to_id(key)
            if key_id:
                pressed_keys.discard(key_id)

        self._test_listener = kb.Listener(on_press=on_press, on_release=on_release)
        self._test_listener.daemon = True
        self._test_listener.start()

        def check_result():
            nonlocal result_shown
            if result_shown:
                return
            result_shown = True
            try:
                if self._test_listener is not None:
                    self._test_listener.stop()
            except Exception:
                pass
            # Resume the app's hotkey listener
            if self._hotkey_manager is not None:
                self._hotkey_manager.resume()
            if test_detected:
                self._hotkey_test_label.setText(f"OK - {combo_label} detected!")
                self._hotkey_test_label.setStyleSheet("color: #22c55e;")
            else:
                self._hotkey_test_label.setText("Not detected. Try another hotkey.")
                self._hotkey_test_label.setStyleSheet("color: #ef4444;")
            self._test_btn.setEnabled(True)
            self._test_btn.setText("  Test  ")

        # Timeout after 5 seconds
        QTimer.singleShot(5000, check_result)

    # ------------------------------------------------------------------
    # Provider changed
    # ------------------------------------------------------------------

    def _on_provider_changed(self) -> None:
        if self._provider_combo is None or self._model_combo is None:
            return
        provider_label = self._provider_combo.currentText()
        is_openai = provider_label == PROVIDER_LABELS.get("openai", "")
        if is_openai:
            self._model_combo.setEnabled(False)
            if self._model_hint:
                self._model_hint.setText("OpenAI uses whisper-1 (fixed)")
        else:
            self._model_combo.setEnabled(True)
            if self._model_hint:
                self._model_hint.setText("")

    # ------------------------------------------------------------------
    # Device loading
    # ------------------------------------------------------------------

    def _load_devices(self) -> None:
        try:
            all_devices = AudioRecorder.list_devices()
        except Exception as exc:
            logger.warning("Failed to list audio devices: %s", exc)
            all_devices = []

        # Deduplicate by name
        seen: set[str] = set()
        self._devices = []
        for dev in all_devices:
            if dev["name"] not in seen:
                seen.add(dev["name"])
                self._devices.append(dev)

        # Find system default device
        default_marker = ""
        try:
            import sounddevice as sd
            default_info = sd.query_devices(kind="input")
            if default_info:
                default_marker = default_info["name"]
        except Exception:
            pass

        default_entry = None
        other_entries = []
        for dev in self._devices:
            label = dev["name"]
            entry = f"{label} (#{dev['index']})"
            if label == default_marker:
                default_entry = f"* {label} [active] (#{dev['index']})"
            else:
                other_entries.append(entry)

        device_names = ["System Default"]
        if default_entry:
            device_names.append(default_entry)
        device_names.extend(other_entries)

        current = "System Default"
        if self._settings.input_device is not None:
            for dev in self._devices:
                if dev["index"] == self._settings.input_device:
                    label = dev["name"]
                    if label == default_marker:
                        current = f"* {label} [active] (#{dev['index']})"
                    else:
                        current = f"{label} (#{dev['index']})"
                    break

        # Marshal to Qt thread
        QTimer.singleShot(0, lambda: self._update_device_dropdown(device_names, current))

    def _update_device_dropdown(self, names: list[str], current: str) -> None:
        if self._device_combo is not None:
            self._device_combo.clear()
            self._device_combo.addItems(names)
            self._device_combo.setCurrentText(current)

    # ------------------------------------------------------------------
    # Save / Close
    # ------------------------------------------------------------------

    def _on_save_click(self) -> None:
        # Language
        lang_label = self._lang_combo.currentText()
        self._settings.language = LANGUAGE_OPTIONS.get(lang_label, "fr")

        # Provider
        provider_label = self._provider_combo.currentText()
        for code, label in PROVIDER_LABELS.items():
            if label == provider_label:
                self._settings.primary_provider = code
                break

        # Model
        model_label = self._model_combo.currentText()
        for code, label in MODEL_LABELS.items():
            if label == model_label:
                self._settings.whisper_model = code
                break

        # Prompt
        self._settings.prompt = self._prompt_text.toPlainText().strip()

        # Post-process
        self._settings.post_process = self._post_process_cb.isChecked()

        # Device
        device_label = self._device_combo.currentText()
        if device_label in ("System Default", "Loading..."):
            self._settings.input_device = None
        else:
            idx_match = re.search(r"#(\d+)\)$", device_label)
            self._settings.input_device = int(idx_match.group(1)) if idx_match else None

        # Record Mode
        mode_label = self._mode_combo.currentText()
        for code, label in RECORD_MODE_LABELS.items():
            if label == mode_label:
                self._settings.record_mode = code
                break

        # Hotkey
        hotkey_label = self._hotkey_combo.currentText()
        self._settings.hotkey = _preset_label_to_combo(hotkey_label)

        # App toggles
        self._settings.show_notifications = self._notif_cb.isChecked()
        self._settings.restore_clipboard = self._clipboard_cb.isChecked()

        # Persist
        self._settings.save()
        logger.info("Settings saved to %s", self._settings.config_path())

        if self._on_save:
            self._on_save(self._settings)

        self._on_close()

    def _on_close(self) -> None:
        self._is_open = False
        self.hide()
        logger.info("Settings window closed")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._on_close()
        event.accept()


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------


def _code_to_label(code: str, mapping: dict[str, str]) -> str:
    for label, c in mapping.items():
        if c == code:
            return label
    return list(mapping.keys())[0]


def _combo_to_preset_label(combo: str) -> str:
    for code, label in HOTKEY_PRESETS.items():
        if code == combo:
            return label
    return combo.replace("<", "").replace(">", "").replace("+", " + ").title()


def _preset_label_to_combo(label: str) -> str:
    for code, lbl in HOTKEY_PRESETS.items():
        if lbl == label:
            return code
    return "<cmd>+<shift>+<space>" if _IS_MAC else "<ctrl>+<shift>+<space>"
