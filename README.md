# MindScribe Desktop (macOS)

Voice dictation app for macOS. Record speech via a global hotkey, transcribe it using Groq or OpenAI Whisper, and paste the text into any active field.

> This is the macOS version (PyQt6). The Windows version (tkinter) lives at [Mind-Scribe-Desktop-](https://github.com/aziztraorebf-ctrl/Mind-Scribe-Desktop-).

## Features

- **Global hotkey** (Cmd+Shift+Space) — toggle or hold-to-record modes
- **Cloud transcription** via Groq API (whisper-large-v3) with OpenAI fallback
- **Floating overlay** with real-time waveform, timer, Pause/Stop/Cancel buttons
- **System tray icon** with state indicators and settings menu
- **Settings dashboard** — language, provider, model, microphone, hotkey, record mode
- **LLM post-processing** — optional cleanup of punctuation and fillers
- **Universal paste** into any active text field (browser, editor, terminal)

## Quick Start

```bash
# Clone
git clone https://github.com/aziztraorebf-ctrl/Mind-Scribe-Mac.git
cd Mind-Scribe-Mac

# Automated setup (installs Homebrew deps, creates venv, installs packages)
chmod +x setup_macos.sh
./setup_macos.sh

# Configure API keys
cp .env.example .env
# Edit .env → add GROQ_API_KEY and/or OPENAI_API_KEY

# Run
source venv-mac/bin/activate
python run.py
```

## Requirements

- macOS 12.0+ (Apple Silicon or Intel)
- Python 3.11+
- Xcode Command Line Tools (`xcode-select --install`)
- Groq API key and/or OpenAI API key

### System dependencies (installed by `setup_macos.sh`)

| Dependency | Purpose | Install |
|-----------|---------|---------|
| portaudio | Microphone capture | `brew install portaudio` |
| ffmpeg | Audio compression | `brew install ffmpeg` |

## macOS Permissions

You **must** grant these in **System Settings > Privacy & Security**:

| Permission | Why | Where to add |
|-----------|-----|-------------|
| **Microphone** | Record your voice | Microphone → Terminal / MindScribe |
| **Accessibility** | Global hotkeys | Accessibility → Terminal / MindScribe |
| **Input Monitoring** | Detect key presses | Input Monitoring → Terminal / MindScribe |

Without Accessibility + Input Monitoring, global hotkeys will not work.

**Shortcut conflict**: If `Cmd+Shift+Space` doesn't work, check **System Settings > Keyboard > Keyboard Shortcuts > Input Sources**. macOS may have it assigned to "Select the previous input source". Disable it there, or choose a different hotkey in MindScribe settings (F9, Cmd+Shift+R, etc.).

## Configuration

Settings are stored in `~/Library/Application Support/MindScribeDesktop/config.json`.

| Setting | Default | Description |
|---------|---------|-------------|
| `language` | `"fr"` | Transcription language (ISO-639-1) |
| `primary_provider` | `"groq"` | `groq` or `openai` |
| `whisper_model` | `"whisper-large-v3"` | Whisper model variant |
| `hotkey` | `Cmd+Shift+Space` | Global shortcut (7 presets) |
| `record_mode` | `"toggle"` | `toggle` or `hold` |
| `post_process` | `false` | LLM cleanup (punctuation, fillers) |

## Building the .app bundle

```bash
# Install PyInstaller
pip install pyinstaller

# Build
chmod +x build.sh
./build.sh
```

Output: `dist/MindScribe.app` — double-click or `open dist/MindScribe.app`.

## Architecture

```
Python 3.11+ (PyQt6)
  + sounddevice     (microphone capture via PortAudio)
  + PyQt6           (overlay + settings UI)
  + Groq/OpenAI API (Whisper transcription)
  + pynput          (global hotkeys via PyObjC/Quartz)
  + pystray         (system tray via PyObjC/Cocoa)
  + pydub           (audio chunking/compression)
```

## Project Structure

```
src/
  app.py                    # Orchestration & state machine
  preflight_macos.py        # Runtime dependency checker
  config/
    settings.py             # JSON config persistence
    dotenv_loader.py        # .env file loading
  core/
    audio_recorder.py       # Mic capture with real-time RMS
    transcriber.py          # Groq/OpenAI with fallback + retry
    chunker.py              # Audio splitting for long recordings
    hotkey_manager.py       # Global keyboard shortcuts (pynput)
    text_inserter.py        # Clipboard paste simulation (Cmd+V)
  ui/
    overlay.py              # Floating overlay (PyQt6, waveform, timer)
    settings_window.py      # Settings dashboard (PyQt6, dark theme)
    tray_icon.py            # System tray with state indicators
    icons.py                # Programmatic tray icons (Pillow)
    notification.py         # Native macOS notifications (osascript)
run.py                      # Launcher (QApplication on main thread)
requirements.txt            # Python dependencies
MindScribe.spec             # PyInstaller spec (.app bundle)
setup_macos.sh              # Automated setup script
build.sh                    # Build script for .app bundle
macos/
  Info.plist                # App bundle metadata + permissions
  entitlements.plist        # Entitlements (audio, apple-events)
```

## Tests

```bash
python -m pytest tests/ -v
```

## License

Private project.
