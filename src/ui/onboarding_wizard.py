"""Onboarding wizard shown on first launch when no API key is configured."""

import logging
import platform
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_IS_MAC = platform.system() == "Darwin"
_UI_FONT = ".AppleSystemUIFont" if _IS_MAC else "Segoe UI"

_BG = "#1E1E2E"
_SURFACE = "#2A2A3E"
_TEXT = "#E0E0F0"
_TEXT_DIM = "#8888AA"
_ACCENT = "#6C63FF"
_AMBER = "#FFB347"
_SUCCESS = "#50FA7B"
_DANGER = "#FF5555"
_BORDER = "#3A3A5C"


# --- macOS permission helpers ---

def _check_accessibility() -> bool:
    """Return True if the process has Accessibility permission."""
    if platform.system() != "Darwin":
        return True
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _check_input_monitoring() -> bool:
    """Return True if Input Monitoring is granted.

    On macOS 10.15+, CGEventTap requires both Accessibility and Input Monitoring.
    We use the same AXIsProcessTrusted check as a proxy — if accessibility is
    granted the CGEventTap will succeed, which implies input monitoring is also
    granted for our use case.
    """
    return _check_accessibility()


def _check_microphone() -> bool:
    """Return True if microphone access is authorized."""
    if platform.system() != "Darwin":
        return True
    try:
        import AVFoundation
        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
            AVFoundation.AVMediaTypeAudio
        )
        # 3 = AVAuthorizationStatusAuthorized
        return status == 3
    except Exception:
        # AVFoundation not available — assume granted (will fail at recording time)
        return True


def _open_privacy_pref(pane: str) -> None:
    """Open a specific Privacy pane in System Settings."""
    url = f"x-apple.systempreferences:com.apple.preference.security?{pane}"
    subprocess.Popen(["open", url])


def _env_target_path() -> Path:
    """Write .env in Application Support (same dir as config.json)."""
    from src.config.settings import Settings
    return Settings.config_path().parent / ".env"


class OnboardingWizard(QDialog):
    """Modal wizard shown when no API key is configured.

    Call run() -- returns True if user completed setup, False if closed.
    """

    _sig_test_result = pyqtSignal(bool, str)
    _sig_perm_results = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._completed = False
        self._sig_test_result.connect(self._on_test_result)
        self._sig_perm_results.connect(self._apply_permission_results)

        self.setWindowTitle("MindScribe - First Setup")
        self.setModal(True)
        self.setFixedSize(520, 420)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {_BG}; color: {_TEXT}; font-family: "{_UI_FONT}"; }}
            QLabel {{ color: {_TEXT}; }}
            QPushButton {{
                background-color: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {_ACCENT}; color: white; border-color: {_ACCENT}; }}
            QPushButton:disabled {{ color: {_TEXT_DIM}; border-color: {_BORDER}; }}
        """)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_page_welcome())       # index 0
        self._stack.addWidget(self._build_page_permissions())   # index 1
        self._stack.addWidget(self._build_page_api_keys())      # index 2
        self._stack.addWidget(self._build_page_done())          # index 3

        self._btn_back = QPushButton("Back")
        self._btn_back.clicked.connect(self._go_back)
        self._btn_back.setVisible(False)

        self._btn_next = QPushButton("Next")
        self._btn_next.clicked.connect(self._go_next)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self._btn_back)
        nav_layout.addStretch()
        nav_layout.addWidget(self._btn_next)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 28, 32, 20)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._stack, stretch=1)
        main_layout.addSpacing(16)
        main_layout.addLayout(nav_layout)

        self._update_nav()

    def _build_page_welcome(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel("Welcome to MindScribe")
        title.setFont(QFont(_UI_FONT, 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_ACCENT};")

        subtitle = QLabel(
            "MindScribe converts your voice to text and pastes it\n"
            "directly into any app - instantly, with one hotkey."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 14px;")

        what = QLabel(
            "To get started, you'll need a free Groq API key.\n"
            "Groq provides fast, free Whisper transcription - no credit card required."
        )
        what.setWordWrap(True)
        what.setStyleSheet(f"font-size: 13px; color: {_TEXT};")

        groq_note = QLabel("Get your free key at: console.groq.com")
        groq_note.setStyleSheet(f"color: {_AMBER}; font-size: 13px;")

        layout.addStretch()
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        layout.addWidget(what)
        layout.addSpacing(8)
        layout.addWidget(groq_note)
        layout.addStretch()
        return page

    def _build_page_permissions(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("System Permissions")
        title.setFont(QFont(_UI_FONT, 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_ACCENT};")

        subtitle = QLabel(
            "MindScribe needs 3 permissions to work. Click each button\n"
            "to open System Settings, grant the permission, then come back."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 13px;")

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        # Build permission rows — store status labels for refresh
        self._perm_labels = {}
        perms = [
            ("microphone", "Microphone", "Record your voice", "Privacy_Microphone"),
            ("accessibility", "Accessibility", "Paste transcribed text", "Privacy_Accessibility"),
            ("input_monitoring", "Input Monitoring", "Detect your global hotkey", "Privacy_ListenEvent"),
        ]
        for key, name, reason, pane in perms:
            row = QHBoxLayout()
            row.setSpacing(12)

            name_label = QLabel(f"<b>{name}</b><br><span style='color:{_TEXT_DIM}; font-size:11px;'>{reason}</span>")
            name_label.setStyleSheet(f"font-size: 13px; color: {_TEXT};")
            name_label.setMinimumWidth(180)

            status_label = QLabel()
            status_label.setFixedWidth(80)
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._perm_labels[key] = status_label

            open_btn = QPushButton("Open Settings")
            open_btn.setFixedWidth(110)
            open_btn.clicked.connect(lambda checked, p=pane: _open_privacy_pref(p))

            row.addWidget(name_label, stretch=1)
            row.addWidget(status_label)
            row.addWidget(open_btn)

            row_frame = QFrame()
            row_frame.setLayout(row)
            row_frame.setStyleSheet(
                f"QFrame {{ background-color: {_SURFACE}; border-radius: 6px; }}"
            )
            row_frame.setContentsMargins(12, 8, 12, 8)
            layout.addWidget(row_frame)

        refresh_btn = QPushButton("Check Again")
        refresh_btn.clicked.connect(self._refresh_permissions)
        layout.addSpacing(4)
        layout.addWidget(refresh_btn)
        layout.addStretch()

        # Populate initial status
        self._refresh_permissions()
        return page

    def _refresh_permissions(self) -> None:
        """Re-check all permissions in a background thread, update UI on completion."""
        import threading

        def _do_check():
            checks = {
                "microphone": _check_microphone(),
                "accessibility": _check_accessibility(),
                "input_monitoring": _check_input_monitoring(),
            }
            self._sig_perm_results.emit(checks)

        threading.Thread(target=_do_check, daemon=True).start()

    def _apply_permission_results(self, checks: dict) -> None:
        """Apply permission check results to UI (must run on Qt thread)."""
        for key, granted in checks.items():
            label = self._perm_labels[key]
            if granted:
                label.setText("Granted")
                label.setStyleSheet(
                    f"font-size: 12px; font-weight: bold; color: {_SUCCESS};"
                )
            else:
                label.setText("Required")
                label.setStyleSheet(
                    f"font-size: 12px; font-weight: bold; color: {_AMBER};"
                )

        all_granted = all(checks.values())
        if self._stack.currentIndex() == 1:
            self._btn_next.setEnabled(all_granted)

    def _build_page_api_keys(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        title = QLabel("API Keys")
        title.setFont(QFont(_UI_FONT, 18, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_ACCENT};")

        groq_label = QLabel("Groq API Key (required)")
        groq_label.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: bold;")

        _field_style = f"""
            QLineEdit {{
                background-color: {_SURFACE};
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """

        self._groq_key_input = QLineEdit()
        self._groq_key_input.setPlaceholderText("gsk_...")
        self._groq_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._groq_key_input.setStyleSheet(_field_style)
        self._groq_key_input.textChanged.connect(self._update_nav_page2)

        self._test_btn = QPushButton("Test Groq Key")
        self._test_btn.clicked.connect(self._test_groq_key)

        self._test_status = QLabel("")
        self._test_status.setWordWrap(True)
        self._test_status.setStyleSheet(f"font-size: 12px; color: {_TEXT_DIM};")

        openai_label = QLabel("OpenAI API Key (optional - fallback provider)")
        openai_label.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 12px;")

        self._openai_key_input = QLineEdit()
        self._openai_key_input.setPlaceholderText("sk-... (optional)")
        self._openai_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_key_input.setStyleSheet(_field_style)

        layout.addWidget(title)
        layout.addSpacing(4)
        layout.addWidget(groq_label)
        layout.addWidget(self._groq_key_input)
        layout.addWidget(self._test_btn)
        layout.addWidget(self._test_status)
        layout.addSpacing(8)
        layout.addWidget(openai_label)
        layout.addWidget(self._openai_key_input)
        layout.addStretch()
        return page

    def _build_page_done(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel("You're all set!")
        title.setFont(QFont(_UI_FONT, 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_SUCCESS};")

        summary = QLabel(
            "MindScribe is ready to use.\n\n"
            "Press your hotkey (Cmd+Shift+Space by default) to start recording.\n"
            "Press it again to stop and transcribe.\n\n"
            "The transcribed text will be pasted into whatever app is in focus."
        )
        summary.setWordWrap(True)
        summary.setStyleSheet(f"font-size: 13px; color: {_TEXT};")

        tip = QLabel(
            "Tip: Open Settings from the menu bar icon to change your hotkey,\n"
            "language, or connect additional providers."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(f"font-size: 12px; color: {_TEXT_DIM};")

        layout.addStretch()
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(summary)
        layout.addSpacing(12)
        layout.addWidget(tip)
        layout.addStretch()
        return page

    # --- Navigation ---

    def _go_next(self):
        current = self._stack.currentIndex()
        if current == 2:
            # API keys page — write .env before advancing to confirmation
            groq_key = self._groq_key_input.text().strip()
            openai_key = self._openai_key_input.text().strip()
            self._write_env(groq_key, openai_key)
        if current < self._stack.count() - 1:
            self._stack.setCurrentIndex(current + 1)
            self._update_nav()
        else:
            self._completed = True
            self.accept()

    def _go_back(self):
        current = self._stack.currentIndex()
        if current > 0:
            self._stack.setCurrentIndex(current - 1)
            self._update_nav()

    def _update_nav(self):
        idx = self._stack.currentIndex()
        last = self._stack.count() - 1
        self._btn_back.setVisible(idx > 0)
        self._btn_next.setText("Finish" if idx == last else "Next")
        if idx == 1:
            # Permissions page — Next enabled only when all granted
            self._refresh_permissions()
        elif idx == 2:
            # API keys page — Next enabled only when at least one key entered
            self._update_nav_page2()
        else:
            self._btn_next.setEnabled(True)

    def _update_nav_page2(self):
        """Enable Next on page 2 (API keys) only when at least one key is entered."""
        if self._stack.currentIndex() != 2:
            return
        has_key = bool(self._groq_key_input.text().strip()) or bool(
            self._openai_key_input.text().strip()
        )
        self._btn_next.setEnabled(has_key)

    # --- API key validation ---

    def _test_groq_key(self):
        """Validate Groq key with a real API call using a silent WAV."""
        import io
        import threading
        import wave

        groq_key = self._groq_key_input.text().strip()
        if not groq_key:
            self._test_status.setText("Enter a Groq key first.")
            self._test_status.setStyleSheet(f"color: {_AMBER}; font-size: 12px;")
            return

        self._test_btn.setEnabled(False)
        self._test_status.setText("Testing...")
        self._test_status.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 12px;")

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 16000 * 2)
        silent_wav = buf.getvalue()

        def _do_test():
            from src.core.transcriber import Transcriber, TranscriptionError
            try:
                t = Transcriber(groq_api_key=groq_key, model="whisper-large-v3-turbo")
                t.transcribe(silent_wav)
                ok, msg = True, "Groq key is valid."
            except TranscriptionError as exc:
                if "empty" in str(exc).lower():
                    ok, msg = True, "Groq key is valid."
                else:
                    ok, msg = False, f"Invalid key: {exc}"
            except Exception as exc:
                ok, msg = False, f"Connection error: {exc}"

            self._sig_test_result.emit(ok, msg)

        threading.Thread(target=_do_test, daemon=True).start()

    def _on_test_result(self, ok: bool, msg: str):
        self._test_btn.setEnabled(True)
        color = _SUCCESS if ok else _DANGER
        self._test_status.setText(msg)
        self._test_status.setStyleSheet(f"color: {color}; font-size: 12px;")

    # --- .env write ---

    def _write_env(self, groq_key: str, openai_key: str, path: Path = None) -> None:
        """Write API keys to .env file."""
        if path is None:
            path = _env_target_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"GROQ_API_KEY={groq_key}\n"]
        if openai_key:
            lines.append(f"OPENAI_API_KEY={openai_key}\n")
        path.write_text("".join(lines), encoding="utf-8")
        logger.info("Wrote .env to %s", path)

    # --- Public API ---

    def run(self) -> bool:
        """Show wizard modally. Returns True if user completed setup."""
        self.exec()
        return self._completed
