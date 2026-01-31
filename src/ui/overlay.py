"""Floating overlay window that shows recording/transcribing status with animation."""

import logging
import math
import threading
import tkinter as tk
from typing import Callable

logger = logging.getLogger(__name__)

# Overlay dimensions
WINDOW_WIDTH = 300
WINDOW_HEIGHT_RECORDING = 110
WINDOW_HEIGHT_TRANSCRIBING = 70
WINDOW_WIDTH_READY = 400
WINDOW_HEIGHT_READY = 70
READY_DISPLAY_MS = 10000  # Auto-hide after 10 seconds
FADE_IN_STEPS = 15
FADE_IN_INTERVAL_MS = 33  # ~500ms total fade-in
CANVAS_HEIGHT = 36
BAR_COUNT = 32
BAR_WIDTH = 4
BAR_GAP = 2

# Colors
BG_COLOR = "#1a1a2e"
TEXT_COLOR = "#e0e0e0"
RED_ACCENT = "#ff4444"
AMBER_ACCENT = "#ffaa00"
BTN_BG = "#2a2a4a"
BTN_HOVER = "#3a3a5a"
BTN_RED = "#cc3333"
BTN_RED_HOVER = "#ee4444"
PAUSE_COLOR = "#ffaa00"
PAUSE_HOVER = "#ffcc44"
GREEN_ACCENT = "#22c55e"


class RecordingOverlay:
    """Floating overlay with reactive waveform, timer, and control buttons."""

    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._timer_label: tk.Label | None = None
        self._status_label: tk.Label | None = None
        self._btn_frame: tk.Frame | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._animating = False
        self._mode = "idle"  # "idle", "recording", "paused", "transcribing", "ready"
        self._ready = threading.Event()
        self._anim_phase = 0.0

        # Audio level data source (set by app.py)
        self._get_levels: Callable[[], list[float]] | None = None
        self._get_duration: Callable[[], float] | None = None

        # Action callbacks (set by app.py)
        self.on_stop: Callable[[], None] | None = None
        self.on_cancel: Callable[[], None] | None = None
        self.on_pause: Callable[[], None] | None = None

    @property
    def tk_root(self) -> tk.Tk | None:
        """The underlying tk.Tk root (available after start())."""
        return self._root

    def set_audio_source(
        self,
        get_levels: Callable[[], list[float]],
        get_duration: Callable[[], float],
    ) -> None:
        """Connect to the audio recorder for real-time levels and duration."""
        self._get_levels = get_levels
        self._get_duration = get_duration

    def start(self) -> None:
        """Start the overlay UI thread (hidden by default)."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_tk, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        logger.info("Recording overlay initialized")

    def stop(self) -> None:
        """Destroy the overlay window."""
        self._running = False
        self._animating = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
        self._root = None

    def show_recording(self) -> None:
        """Show the overlay in recording mode with animated waveform."""
        self._mode = "recording"
        self._animating = True
        if self._root:
            self._root.after(0, self._show_window, "recording")

    def show_paused(self) -> None:
        """Show the overlay in paused mode."""
        self._mode = "paused"
        self._animating = True
        if self._root:
            self._root.after(0, self._show_window, "paused")

    def show_transcribing(self) -> None:
        """Show the overlay in transcribing mode with pulsing dots."""
        self._mode = "transcribing"
        self._animating = True
        if self._root:
            self._root.after(0, self._show_window, "transcribing")

    def show_ready(self, hotkey_display: str) -> None:
        """Show a brief 'Ready' overlay at startup, auto-hides after timeout."""
        self._mode = "ready"
        self._ready_hotkey = hotkey_display
        self._animating = True  # Enable pulse animation
        if self._root:
            self._root.after(0, self._show_window, "ready")

    def hide(self) -> None:
        """Hide the overlay."""
        self._mode = "idle"
        self._animating = False
        if self._root:
            self._root.after(0, self._hide_window)

    def _run_tk(self) -> None:
        """Main tkinter loop running in its own thread."""
        self._root = tk.Tk()
        self._root.title("MindScribe")
        self._root.overrideredirect(True)  # No title bar
        self._root.attributes("-topmost", True)  # Always on top
        self._root.attributes("-alpha", 0.92)
        self._root.configure(bg=BG_COLOR)

        # Position: top-center of screen
        screen_w = self._root.winfo_screenwidth()
        x = (screen_w - WINDOW_WIDTH) // 2
        y = 18
        self._root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT_RECORDING}+{x}+{y}")

        # Make window draggable (bind on root for areas without buttons)
        self._drag_data = {"x": 0, "y": 0}
        self._root.bind("<Button-1>", self._on_drag_start)
        self._root.bind("<B1-Motion>", self._on_drag_motion)

        # -- Top row: status label + timer --
        top_frame = tk.Frame(self._root, bg=BG_COLOR)
        top_frame.pack(side="top", fill="x", padx=12, pady=(8, 0))

        self._status_label = tk.Label(
            top_frame,
            text="",
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self._status_label.pack(side="left")

        self._timer_label = tk.Label(
            top_frame,
            text="00:00",
            fg=TEXT_COLOR,
            bg=BG_COLOR,
            font=("Consolas", 10),
            anchor="e",
        )
        self._timer_label.pack(side="right")

        # -- Canvas for waveform / animation --
        self._canvas = tk.Canvas(
            self._root,
            width=WINDOW_WIDTH - 24,
            height=CANVAS_HEIGHT,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self._canvas.pack(side="top", padx=12, pady=(4, 4))

        # -- Button row --
        self._btn_frame = tk.Frame(self._root, bg=BG_COLOR)
        self._btn_frame.pack(side="top", fill="x", padx=12, pady=(0, 8))

        self._btn_pause = self._make_button(
            self._btn_frame, "Pause", PAUSE_COLOR, PAUSE_HOVER, self._handle_pause
        )
        self._btn_pause.pack(side="left", padx=(0, 6))

        self._btn_stop = self._make_button(
            self._btn_frame, "Stop", RED_ACCENT, BTN_RED_HOVER, self._handle_stop
        )
        self._btn_stop.pack(side="left", padx=(0, 6))

        self._btn_cancel = self._make_button(
            self._btn_frame, "Cancel", BTN_BG, BTN_HOVER, self._handle_cancel, fg="#999999"
        )
        self._btn_cancel.pack(side="left")

        # Start hidden
        self._root.withdraw()
        self._ready.set()

        # Animation loop
        self._animate()

        try:
            self._root.mainloop()
        except Exception:
            pass

    def _make_button(
        self,
        parent: tk.Frame,
        text: str,
        bg: str,
        hover_bg: str,
        command: Callable,
        fg: str = "#ffffff",
    ) -> tk.Label:
        """Create a styled button using a Label (for rounded feel in tkinter)."""
        btn = tk.Label(
            parent,
            text=f"  {text}  ",
            fg=fg,
            bg=bg,
            font=("Segoe UI", 8),
            cursor="hand2",
            relief="flat",
            padx=8,
            pady=2,
        )
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def _show_window(self, mode: str) -> None:
        """Show and configure window for given mode."""
        if not self._root:
            return

        # Keep current position if window was dragged
        current_x = self._root.winfo_x()
        current_y = self._root.winfo_y()

        if mode == "recording":
            self._status_label.config(
                text="Recording", fg=RED_ACCENT,
                font=("Segoe UI", 9, "bold"),
            )
            self._timer_label.config(font=("Consolas", 10))
            self._canvas.pack(side="top", padx=12, pady=(4, 4))
            self._btn_frame.pack(side="top", fill="x", padx=12, pady=(0, 8))
            self._btn_pause.config(text="  Pause  ")
            self._root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT_RECORDING}+{current_x}+{current_y}")
        elif mode == "paused":
            self._status_label.config(text="Paused", fg=AMBER_ACCENT)
            self._btn_pause.config(text="  Resume  ")
        elif mode == "transcribing":
            self._status_label.config(text="Transcribing...", fg=AMBER_ACCENT)
            self._timer_label.config(text="")
            self._canvas.pack_forget()
            self._btn_frame.pack_forget()
            self._root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT_TRANSCRIBING}+{current_x}+{current_y}")
        elif mode == "ready":
            hotkey_text = getattr(self, "_ready_hotkey", "")
            self._status_label.config(
                text="MindScribe Ready", fg=GREEN_ACCENT,
                font=("Segoe UI", 11, "bold"),
            )
            self._timer_label.config(
                text=hotkey_text, font=("Consolas", 11),
            )
            self._canvas.pack_forget()
            self._btn_frame.pack_forget()
            # Center on screen
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            rx = (screen_w - WINDOW_WIDTH_READY) // 2
            ry = (screen_h - WINDOW_HEIGHT_READY) // 2
            self._root.geometry(
                f"{WINDOW_WIDTH_READY}x{WINDOW_HEIGHT_READY}+{rx}+{ry}"
            )
            # Fade-in from transparent
            self._root.attributes("-alpha", 0.0)
            self._fade_step = 0
            self._root.after(FADE_IN_INTERVAL_MS, self._fade_in_tick)
            self._root.after(READY_DISPLAY_MS, self._auto_hide_ready)

        self._root.deiconify()

    def _hide_window(self) -> None:
        """Hide the overlay window."""
        if self._root:
            self._root.withdraw()
            if self._canvas:
                self._canvas.delete("all")

    def _animate(self) -> None:
        """Animation tick - draws waveform bars or pulsing dots, updates timer."""
        if not self._root or not self._running:
            return

        if self._animating and self._canvas:
            self._canvas.delete("all")
            canvas_w = WINDOW_WIDTH - 24

            if self._mode in ("recording", "paused"):
                self._draw_waveform(canvas_w)
                self._update_timer()
            elif self._mode == "transcribing":
                self._draw_pulse_dots(canvas_w)
            elif self._mode == "ready":
                self._pulse_ready_text()

            self._anim_phase += 0.15

        # Schedule next frame (~30fps)
        if self._running and self._root:
            try:
                self._root.after(33, self._animate)
            except Exception:
                pass

    def _update_timer(self) -> None:
        """Update the timer label with current recording duration."""
        if not self._timer_label or not self._get_duration:
            return
        secs = self._get_duration()
        minutes = int(secs) // 60
        seconds = int(secs) % 60
        self._timer_label.config(text=f"{minutes:02d}:{seconds:02d}")

    def _draw_waveform(self, canvas_w: int) -> None:
        """Draw waveform bars from real audio levels."""
        total_bars_width = BAR_COUNT * (BAR_WIDTH + BAR_GAP)
        offset_x = (canvas_w - total_bars_width) // 2

        # Get real levels from audio recorder
        levels = []
        if self._get_levels:
            levels = self._get_levels()

        # Pad or resample levels to match BAR_COUNT
        if len(levels) < BAR_COUNT:
            # Pad left with zeros
            levels = [0.0] * (BAR_COUNT - len(levels)) + levels

        # If paused, dim the bars
        dim_factor = 0.3 if self._mode == "paused" else 1.0

        for i in range(BAR_COUNT):
            raw_level = levels[i] if i < len(levels) else 0.0

            # Add subtle animation even to real levels for organic feel
            wave_mod = math.sin(self._anim_phase * 0.5 + i * 0.3) * 0.05
            height_ratio = max(0.06, min(1.0, raw_level + wave_mod)) * dim_factor

            bar_h = int(height_ratio * (CANVAS_HEIGHT - 4))
            x1 = offset_x + i * (BAR_WIDTH + BAR_GAP)
            y_center = CANVAS_HEIGHT // 2
            y1 = y_center - bar_h // 2
            y2 = y_center + bar_h // 2

            # Color gradient: red at peaks, darker at troughs
            intensity = int(80 + height_ratio * 175)
            red_hex = f"#{intensity:02x}2222"

            self._canvas.create_rectangle(
                x1, y1, x1 + BAR_WIDTH, y2,
                fill=red_hex,
                outline="",
            )

    def _draw_pulse_dots(self, canvas_w: int) -> None:
        """Draw pulsing dots for transcribing state."""
        dot_count = 3
        dot_radius_base = 5
        spacing = 30
        total_w = dot_count * spacing
        offset_x = (canvas_w - total_w) // 2
        y_center = CANVAS_HEIGHT // 2

        for i in range(dot_count):
            phase = self._anim_phase - i * 0.5
            scale = (math.sin(phase) + 1) / 2  # 0 to 1
            r = dot_radius_base + int(scale * 4)
            alpha_int = int(120 + scale * 135)

            cx = offset_x + i * spacing + spacing // 2
            self._canvas.create_oval(
                cx - r, y_center - r, cx + r, y_center + r,
                fill=f"#{alpha_int:02x}{int(alpha_int * 0.65):02x}00",
                outline="",
            )

    def _pulse_ready_text(self) -> None:
        """Pulse the 'MindScribe Ready' text color between green shades."""
        if not self._status_label:
            return
        # Oscillate green intensity: base #22c55e, pulse brighter
        pulse = (math.sin(self._anim_phase * 1.5) + 1) / 2  # 0 to 1
        g_base, g_peak = 0x80, 0xFF
        r_base, r_peak = 0x22, 0x66
        b_base, b_peak = 0x3E, 0x7E
        r = int(r_base + pulse * (r_peak - r_base))
        g = int(g_base + pulse * (g_peak - g_base))
        b = int(b_base + pulse * (b_peak - b_base))
        self._status_label.config(fg=f"#{r:02x}{g:02x}{b:02x}")

    def _fade_in_tick(self) -> None:
        """Increment alpha for fade-in effect."""
        if not self._root or self._mode != "ready":
            return
        self._fade_step += 1
        alpha = min(0.92, self._fade_step * (0.92 / FADE_IN_STEPS))
        try:
            self._root.attributes("-alpha", alpha)
        except Exception:
            return
        if self._fade_step < FADE_IN_STEPS:
            self._root.after(FADE_IN_INTERVAL_MS, self._fade_in_tick)

    def _auto_hide_ready(self) -> None:
        """Auto-hide the ready overlay after timeout with fade-out."""
        if self._mode == "ready":
            self._fade_out_step = 0
            self._root.after(FADE_IN_INTERVAL_MS, self._fade_out_tick)

    def _fade_out_tick(self) -> None:
        """Decrement alpha for fade-out effect, then hide."""
        if not self._root or self._mode != "ready":
            return
        self._fade_out_step += 1
        alpha = max(0.0, 0.92 - self._fade_out_step * (0.92 / FADE_IN_STEPS))
        try:
            self._root.attributes("-alpha", alpha)
        except Exception:
            return
        if self._fade_out_step < FADE_IN_STEPS:
            self._root.after(FADE_IN_INTERVAL_MS, self._fade_out_tick)
        else:
            self._mode = "idle"
            self._animating = False
            self._root.attributes("-alpha", 0.92)
            self._hide_window()

    def _handle_stop(self) -> None:
        """Stop button pressed."""
        if self.on_stop:
            threading.Thread(target=self.on_stop, daemon=True).start()

    def _handle_cancel(self) -> None:
        """Cancel button pressed."""
        if self.on_cancel:
            threading.Thread(target=self.on_cancel, daemon=True).start()

    def _handle_pause(self) -> None:
        """Pause/Resume button pressed."""
        if self.on_pause:
            threading.Thread(target=self.on_pause, daemon=True).start()

    def _on_drag_start(self, event: tk.Event) -> None:
        """Record initial position for dragging."""
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _on_drag_motion(self, event: tk.Event) -> None:
        """Move window as user drags."""
        if self._root:
            dx = event.x - self._drag_data["x"]
            dy = event.y - self._drag_data["y"]
            x = self._root.winfo_x() + dx
            y = self._root.winfo_y() + dy
            self._root.geometry(f"+{x}+{y}")
