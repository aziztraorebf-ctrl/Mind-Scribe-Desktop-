"""Settings window using tkinter for MindScribe Desktop configuration.

Uses the overlay's tk.Tk root to avoid Tcl/Tk thread conflicts.
All UI operations are scheduled on the overlay's mainloop via root.after().
"""

import logging
import platform
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from src.config.settings import Settings
from src.core.audio_recorder import AudioRecorder

logger = logging.getLogger(__name__)

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

# Hotkey presets: pynput combo string -> display label (OS-adaptive)
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
    "<numpad_plus>": "Numpad +",
    f"{_MOD}+<alt>": f"{_MOD_LABEL} + Alt",
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


class SettingsWindow:
    """Settings dashboard window using plain tkinter.

    Opens as a Toplevel from the overlay's tk.Tk root so both share
    the same Tcl interpreter thread, avoiding crashes.
    """

    def __init__(self, settings: Settings, on_save: Callable[[Settings], None] | None = None) -> None:
        self._settings = settings
        self._on_save = on_save
        self._tk_root: tk.Tk | None = None
        self._window: tk.Toplevel | None = None
        self._is_open = False
        self._devices: list[dict] = []
        self._hotkey_manager = None
        self._active_test_listener = None

    @property
    def is_open(self) -> bool:
        return self._is_open

    def set_tk_root(self, root: tk.Tk) -> None:
        """Set the shared tk root (from the overlay thread)."""
        self._tk_root = root

    def set_hotkey_manager(self, manager) -> None:
        """Set reference to the HotkeyManager for pause/resume during test."""
        self._hotkey_manager = manager

    def open(self) -> None:
        """Schedule opening the settings window on the tk mainloop thread."""
        if self._is_open:
            if self._window is not None and self._tk_root is not None:
                try:
                    self._tk_root.after(0, self._focus_window)
                except Exception:
                    self._is_open = False
            if self._is_open:
                return

        if self._tk_root is None:
            logger.error("Cannot open settings: no tk root set")
            return

        self._tk_root.after(0, self._build_window)

    def _focus_window(self) -> None:
        if self._window is not None:
            self._window.focus_force()
            self._window.lift()

    def _build_window(self) -> None:
        """Build the settings UI as a Toplevel window."""
        self._window = tk.Toplevel(self._tk_root)
        self._window.title("MindScribe Desktop - Settings")
        self._window.geometry("500x600")
        self._window.resizable(False, False)
        self._window.attributes("-topmost", True)
        self._window.configure(bg=BG)
        self._window.protocol("WM_DELETE_WINDOW", self._on_close)
        self._is_open = True

        # Center on screen
        self._window.update_idletasks()
        sw = self._window.winfo_screenwidth()
        sh = self._window.winfo_screenheight()
        x = (sw - 500) // 2
        y = (sh - 600) // 2
        self._window.geometry(f"500x600+{x}+{y}")

        # Configure ttk styles for dark theme
        style = ttk.Style(self._window)
        style.theme_use("clam")
        style.configure("Dark.TFrame", background=BG)
        style.configure("Dark.TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=BG, foreground=SECTION_FG, font=("Segoe UI", 12, "bold"))
        style.configure("Dim.TLabel", background=BG, foreground=FG_DIM, font=("Consolas", 10))
        style.configure("Dark.TCombobox", fieldbackground=BG_FIELD, background=BG_FIELD,
                         foreground=FG, selectbackground=ACCENT, selectforeground="#ffffff")
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", BG_FIELD)],
                  foreground=[("readonly", FG)])
        style.configure("Dark.TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.map("Dark.TCheckbutton", background=[("active", BG)])

        # Scrollable canvas
        canvas = tk.Canvas(self._window, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self._window, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, style="Dark.TFrame")

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=480)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(10, 0))
        scrollbar.pack(side="right", fill="y", pady=(10, 0))

        # Enable mouse wheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # --- Transcription Section ---
        self._add_section(scroll_frame, "Transcription")

        # Language
        self._add_field_label(scroll_frame, "Language")
        current_lang = _code_to_label(self._settings.language, LANGUAGE_OPTIONS)
        self._lang_var = tk.StringVar(value=current_lang)
        self._lang_combo = ttk.Combobox(
            scroll_frame, textvariable=self._lang_var, values=LANGUAGE_LABELS,
            state="readonly", style="Dark.TCombobox", width=38
        )
        self._lang_combo.pack(anchor="w", padx=24, pady=(0, 10))

        # Provider
        self._add_field_label(scroll_frame, "Primary Provider")
        provider_labels = list(PROVIDER_LABELS.values())
        current_provider = PROVIDER_LABELS.get(self._settings.primary_provider, provider_labels[0])
        self._provider_var = tk.StringVar(value=current_provider)
        self._provider_combo = ttk.Combobox(
            scroll_frame, textvariable=self._provider_var, values=provider_labels,
            state="readonly", style="Dark.TCombobox", width=38
        )
        self._provider_combo.pack(anchor="w", padx=24, pady=(0, 10))
        self._provider_combo.bind("<<ComboboxSelected>>", lambda e: self._on_provider_changed())

        # Whisper Model
        self._add_field_label(scroll_frame, "Whisper Model")
        model_labels = list(MODEL_LABELS.values())
        current_model = MODEL_LABELS.get(self._settings.whisper_model, model_labels[0])
        self._model_var = tk.StringVar(value=current_model)
        self._model_combo = ttk.Combobox(
            scroll_frame, textvariable=self._model_var, values=model_labels,
            state="readonly", style="Dark.TCombobox", width=38
        )
        self._model_combo.pack(anchor="w", padx=24, pady=(0, 2))
        self._model_hint = ttk.Label(
            scroll_frame, text="", style="Dim.TLabel"
        )
        self._model_hint.pack(anchor="w", padx=24, pady=(0, 10))
        # Set initial state based on current provider
        self._on_provider_changed()

        # Prompt
        self._add_field_label(scroll_frame, "Context Prompt (helps Whisper accuracy)")
        self._prompt_text = tk.Text(
            scroll_frame, width=40, height=3, bg=BG_FIELD, fg=FG,
            insertbackground=FG, font=("Segoe UI", 10), relief="flat",
            wrap="word", padx=6, pady=4
        )
        self._prompt_text.insert("1.0", self._settings.prompt)
        self._prompt_text.pack(anchor="w", padx=24, pady=(0, 10))

        # Post-processing
        self._post_process_var = tk.BooleanVar(value=self._settings.post_process)
        ttk.Checkbutton(
            scroll_frame, text="Clean up text with LLM (fix punctuation, remove fillers)",
            variable=self._post_process_var, style="Dark.TCheckbutton"
        ).pack(anchor="w", padx=24, pady=(0, 10))

        # --- Recording Section ---
        self._add_section(scroll_frame, "Recording")

        # Microphone
        self._add_field_label(scroll_frame, "Microphone")
        self._device_var = tk.StringVar(value="Loading...")
        self._device_combo = ttk.Combobox(
            scroll_frame, textvariable=self._device_var, values=["Loading..."],
            state="readonly", style="Dark.TCombobox", width=38
        )
        self._device_combo.pack(anchor="w", padx=24, pady=(0, 10))
        threading.Thread(target=self._load_devices, daemon=True).start()

        # Record Mode
        self._add_field_label(scroll_frame, "Record Mode")
        mode_labels = list(RECORD_MODE_LABELS.values())
        current_mode = RECORD_MODE_LABELS.get(self._settings.record_mode, mode_labels[0])
        self._mode_var = tk.StringVar(value=current_mode)
        self._mode_combo = ttk.Combobox(
            scroll_frame, textvariable=self._mode_var, values=mode_labels,
            state="readonly", style="Dark.TCombobox", width=38
        )
        self._mode_combo.pack(anchor="w", padx=24, pady=(0, 10))

        # Hotkey
        self._add_field_label(scroll_frame, "Hotkey")
        hotkey_frame = tk.Frame(scroll_frame, bg=BG)
        hotkey_frame.pack(anchor="w", padx=24, pady=(0, 2))

        current_hotkey_label = _combo_to_preset_label(self._settings.hotkey)
        self._hotkey_var = tk.StringVar(value=current_hotkey_label)
        self._hotkey_combo_widget = ttk.Combobox(
            hotkey_frame, textvariable=self._hotkey_var,
            values=HOTKEY_PRESET_LABELS,
            state="readonly", style="Dark.TCombobox", width=28
        )
        self._hotkey_combo_widget.pack(side="left")

        self._test_btn = tk.Label(
            hotkey_frame, text="  Test  ", bg=ACCENT, fg="#ffffff",
            font=("Segoe UI", 9), cursor="hand2", padx=8, pady=4
        )
        self._test_btn.pack(side="left", padx=(8, 0))
        self._test_btn.bind("<Button-1>", lambda e: self._test_hotkey())
        self._test_btn.bind("<Enter>", lambda e: self._test_btn.config(bg=ACCENT_HOVER))
        self._test_btn.bind("<Leave>", lambda e: self._test_btn.config(bg=ACCENT))

        self._hotkey_test_label = ttk.Label(
            scroll_frame, text="", style="Dim.TLabel"
        )
        self._hotkey_test_label.pack(anchor="w", padx=24, pady=(0, 10))

        # --- Application Section ---
        self._add_section(scroll_frame, "Application")

        # Notifications
        self._notif_var = tk.BooleanVar(value=self._settings.show_notifications)
        ttk.Checkbutton(
            scroll_frame, text="Show notifications", variable=self._notif_var,
            style="Dark.TCheckbutton"
        ).pack(anchor="w", padx=24, pady=(0, 6))

        # Restore clipboard
        self._clipboard_var = tk.BooleanVar(value=self._settings.restore_clipboard)
        ttk.Checkbutton(
            scroll_frame, text="Restore clipboard after paste", variable=self._clipboard_var,
            style="Dark.TCheckbutton"
        ).pack(anchor="w", padx=24, pady=(0, 16))

        # --- Buttons (outside scrollable area) ---
        btn_frame = tk.Frame(self._window, bg=BG)
        btn_frame.pack(side="bottom", fill="x", padx=16, pady=(8, 16))

        save_btn = tk.Label(
            btn_frame, text="  Save  ", bg=ACCENT, fg="#ffffff",
            font=("Segoe UI", 10, "bold"), cursor="hand2", padx=16, pady=6
        )
        save_btn.pack(side="right", padx=(8, 0))
        save_btn.bind("<Button-1>", lambda e: self._on_save_click())
        save_btn.bind("<Enter>", lambda e: save_btn.config(bg=ACCENT_HOVER))
        save_btn.bind("<Leave>", lambda e: save_btn.config(bg=ACCENT))

        cancel_btn = tk.Label(
            btn_frame, text="  Cancel  ", bg=BTN_CANCEL_BG, fg="#cccccc",
            font=("Segoe UI", 10), cursor="hand2", padx=16, pady=6
        )
        cancel_btn.pack(side="right")
        cancel_btn.bind("<Button-1>", lambda e: self._on_close())
        cancel_btn.bind("<Enter>", lambda e: cancel_btn.config(bg="#666666"))
        cancel_btn.bind("<Leave>", lambda e: cancel_btn.config(bg=BTN_CANCEL_BG))

        logger.info("Settings window opened")

    def _test_hotkey(self) -> None:
        """Test whether the selected hotkey preset is detectable."""
        from pynput import keyboard as kb
        from src.core.hotkey_manager import _parse_hotkey_keys, _pynput_key_to_id

        combo_label = self._hotkey_var.get()
        combo = _preset_label_to_combo(combo_label)
        hotkey_keys = _parse_hotkey_keys(combo)

        self._hotkey_test_label.config(
            text=f"Press {combo_label} now...", foreground=ACCENT
        )
        self._test_btn.config(text=" Testing... ", bg=BTN_CANCEL_BG)
        self._test_btn.unbind("<Button-1>")

        # Pause the app's hotkey listener during test
        if self._hotkey_manager is not None:
            self._hotkey_manager.pause()

        self._test_detected = False
        self._test_result_shown = False
        pressed_keys: set[str] = set()

        def on_press(key):
            key_id = _pynput_key_to_id(key)
            if not key_id:
                return
            pressed_keys.add(key_id)
            if hotkey_keys.issubset(pressed_keys):
                self._test_detected = True
                if self._tk_root:
                    self._tk_root.after(0, check_result)
                return False  # Stop listener

        def on_release(key):
            key_id = _pynput_key_to_id(key)
            if key_id:
                pressed_keys.discard(key_id)

        test_listener = kb.Listener(on_press=on_press, on_release=on_release)
        test_listener.daemon = True
        test_listener.start()
        self._active_test_listener = test_listener

        def check_result():
            if self._test_result_shown or self._window is None:
                return
            self._test_result_shown = True
            self._active_test_listener = None
            try:
                test_listener.stop()
            except Exception:
                pass
            # Resume the app's hotkey listener
            if self._hotkey_manager is not None:
                self._hotkey_manager.resume()
            if self._test_detected:
                self._hotkey_test_label.config(
                    text=f"OK - {combo_label} detected!", foreground="#22c55e"
                )
            else:
                self._hotkey_test_label.config(
                    text="Not detected. Try another hotkey.", foreground="#ef4444"
                )
            self._test_btn.config(text="  Test  ", bg=ACCENT)
            self._test_btn.bind("<Button-1>", lambda e: self._test_hotkey())

        # Timeout after 5 seconds
        if self._tk_root:
            self._tk_root.after(5000, check_result)

    def _on_provider_changed(self) -> None:
        """Enable/disable model dropdown based on selected provider."""
        provider_label = self._provider_var.get()
        is_openai = provider_label == PROVIDER_LABELS["openai"]
        if is_openai:
            self._model_combo.configure(state="disabled")
            self._model_hint.configure(text="OpenAI uses whisper-1 (fixed)")
        else:
            self._model_combo.configure(state="readonly")
            self._model_hint.configure(text="")

    def _load_devices(self) -> None:
        """Load audio devices in a background thread, deduplicating by name."""
        try:
            all_devices = AudioRecorder.list_devices()
        except Exception as exc:
            logger.warning("Failed to list audio devices: %s", exc)
            all_devices = []

        # Deduplicate: keep first occurrence of each device name
        # (Windows exposes the same device via MME, DirectSound, WASAPI)
        seen_names: set[str] = set()
        self._devices = []
        for dev in all_devices:
            name = dev["name"]
            if name not in seen_names:
                seen_names.add(name)
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

        # Build device list with active device promoted to top
        default_entry = None
        other_entries = []
        for dev in self._devices:
            label = dev["name"]
            is_default = (label == default_marker)
            entry = f"{label} (#{dev['index']})"
            if is_default:
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

        if self._tk_root is not None:
            try:
                self._tk_root.after(0, self._update_device_dropdown, device_names, current)
            except Exception:
                pass

    def _update_device_dropdown(self, device_names: list[str], current: str) -> None:
        if self._device_combo is not None:
            self._device_combo.configure(values=device_names)
            self._device_var.set(current)

    def _on_save_click(self) -> None:
        """Read UI values, update settings, persist, and close."""
        # Language
        lang_label = self._lang_var.get()
        self._settings.language = LANGUAGE_OPTIONS.get(lang_label, "fr")

        # Provider
        provider_label = self._provider_var.get()
        for code, label in PROVIDER_LABELS.items():
            if label == provider_label:
                self._settings.primary_provider = code
                break

        # Model
        model_label = self._model_var.get()
        for code, label in MODEL_LABELS.items():
            if label == model_label:
                self._settings.whisper_model = code
                break

        # Prompt
        self._settings.prompt = self._prompt_text.get("1.0", "end").strip()

        # Post-process
        self._settings.post_process = self._post_process_var.get()

        # Device (match by index number in the label)
        device_label = self._device_var.get()
        if device_label == "System Default" or device_label == "Loading...":
            self._settings.input_device = None
        else:
            import re
            idx_match = re.search(r"#(\d+)\)$", device_label)
            if idx_match:
                self._settings.input_device = int(idx_match.group(1))
            else:
                self._settings.input_device = None

        # Record Mode
        mode_label = self._mode_var.get()
        for code, label in RECORD_MODE_LABELS.items():
            if label == mode_label:
                self._settings.record_mode = code
                break

        # Hotkey
        hotkey_label = self._hotkey_var.get()
        self._settings.hotkey = _preset_label_to_combo(hotkey_label)

        # App toggles
        self._settings.show_notifications = self._notif_var.get()
        self._settings.restore_clipboard = self._clipboard_var.get()

        # Persist to disk
        self._settings.save()
        logger.info("Settings saved to %s", self._settings.config_path())

        # Notify app
        if self._on_save:
            self._on_save(self._settings)

        self._on_close()

    def _on_close(self) -> None:
        """Close the settings window."""
        self._is_open = False
        # Stop any active test listener and resume app hotkey listener
        if self._active_test_listener is not None:
            try:
                self._active_test_listener.stop()
            except Exception:
                pass
            self._active_test_listener = None
            if self._hotkey_manager is not None:
                self._hotkey_manager.resume()
        if self._window is not None:
            try:
                self._window.unbind_all("<MouseWheel>")
                self._window.destroy()
            except Exception:
                pass
            self._window = None
        logger.info("Settings window closed")

    @staticmethod
    def _add_section(parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, style="Section.TLabel").pack(
            anchor="w", padx=12, pady=(16, 6)
        )

    @staticmethod
    def _add_field_label(parent: ttk.Frame, text: str) -> None:
        ttk.Label(parent, text=text, style="Dark.TLabel").pack(
            anchor="w", padx=24, pady=(0, 4)
        )


def _code_to_label(code: str, mapping: dict[str, str]) -> str:
    """Convert a code value to its display label."""
    for label, c in mapping.items():
        if c == code:
            return label
    return list(mapping.keys())[0]


def _combo_to_preset_label(combo: str) -> str:
    """Find the display label for a hotkey combo, or format it if not a preset."""
    for code, label in HOTKEY_PRESETS.items():
        if code == combo:
            return label
    # Fallback for legacy/unknown combos
    return combo.replace("<", "").replace(">", "").replace("+", " + ").title()


def _preset_label_to_combo(label: str) -> str:
    """Reverse lookup: display label -> pynput combo string."""
    for code, lbl in HOTKEY_PRESETS.items():
        if lbl == label:
            return code
    # Fallback to default
    if _IS_MAC:
        return "<cmd>+<shift>+<space>"
    return "<ctrl>+<shift>+<space>"
