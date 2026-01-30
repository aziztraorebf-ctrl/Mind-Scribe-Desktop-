"""Settings window using tkinter for MindScribe Desktop configuration.

Uses the overlay's tk.Tk root to avoid Tcl/Tk thread conflicts.
All UI operations are scheduled on the overlay's mainloop via root.after().
"""

import logging
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

    @property
    def is_open(self) -> bool:
        return self._is_open

    def set_tk_root(self, root: tk.Tk) -> None:
        """Set the shared tk root (from the overlay thread)."""
        self._tk_root = root

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

        # Whisper Model
        self._add_field_label(scroll_frame, "Whisper Model")
        model_labels = list(MODEL_LABELS.values())
        current_model = MODEL_LABELS.get(self._settings.whisper_model, model_labels[0])
        self._model_var = tk.StringVar(value=current_model)
        self._model_combo = ttk.Combobox(
            scroll_frame, textvariable=self._model_var, values=model_labels,
            state="readonly", style="Dark.TCombobox", width=38
        )
        self._model_combo.pack(anchor="w", padx=24, pady=(0, 10))

        # Prompt
        self._add_field_label(scroll_frame, "Context Prompt (helps Whisper accuracy)")
        self._prompt_text = tk.Text(
            scroll_frame, width=40, height=3, bg=BG_FIELD, fg=FG,
            insertbackground=FG, font=("Segoe UI", 10), relief="flat",
            wrap="word", padx=6, pady=4
        )
        self._prompt_text.insert("1.0", self._settings.prompt)
        self._prompt_text.pack(anchor="w", padx=24, pady=(0, 10))

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

        # Hotkey (read-only)
        self._add_field_label(scroll_frame, "Hotkey")
        hotkey_display = self._settings.hotkey.replace("<", "").replace(">", "").replace("+", " + ").title()
        ttk.Label(scroll_frame, text=hotkey_display, style="Dim.TLabel").pack(
            anchor="w", padx=24, pady=(0, 10)
        )

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

    def _load_devices(self) -> None:
        """Load audio devices in a background thread."""
        try:
            self._devices = AudioRecorder.list_devices()
        except Exception as exc:
            logger.warning("Failed to list audio devices: %s", exc)
            self._devices = []

        device_names = ["System Default"]
        for dev in self._devices:
            device_names.append(f"{dev['name']} (#{dev['index']})")

        current = "System Default"
        if self._settings.input_device is not None:
            for dev in self._devices:
                if dev["index"] == self._settings.input_device:
                    current = f"{dev['name']} (#{dev['index']})"
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

        # Device
        device_label = self._device_var.get()
        if device_label == "System Default" or device_label == "Loading...":
            self._settings.input_device = None
        else:
            for dev in self._devices:
                if f"{dev['name']} (#{dev['index']})" == device_label:
                    self._settings.input_device = dev["index"]
                    break

        # Record Mode
        mode_label = self._mode_var.get()
        for code, label in RECORD_MODE_LABELS.items():
            if label == mode_label:
                self._settings.record_mode = code
                break

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
        if self._window is not None:
            try:
                # Unbind mousewheel to avoid affecting other windows
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
