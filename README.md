# MindScribe Desktop

Native voice dictation application for Windows and macOS. Record speech via a global hotkey, transcribe it using Groq or OpenAI Whisper, and paste the text into any active field (browser, code editor, terminal, etc.).

Inspired by [Wispr Flow](https://wisprflow.ai) and [groq_whisperer](https://github.com/KennyVaneetvelde/groq_whisperer).

## Features

### Core
- **Configurable global hotkey** with 9 OS-adaptive presets (single keys like F9, combos like Ctrl+Shift+Space, Numpad+)
- **Toggle and Hold modes** - press to start/stop, or hold to record
- **Cloud transcription** via Groq API (whisper-large-v3) with OpenAI fallback
- **LLM post-processing** - optional cleanup of punctuation, fillers, and formatting via Groq/OpenAI chat
- **Universal text insertion** - pastes transcribed text into any active text field
- **Audio chunking** for recordings longer than 25MB (Groq API limit)
- **Clipboard preservation** - restores original clipboard content after pasting

### UI
- **Floating overlay** with real-time reactive waveform, recording timer, and control buttons (Pause/Stop/Cancel)
- **System tray icon** with state indicators (idle/recording/transcribing), dynamic hotkey display
- **Settings dashboard** (dark theme) - language, provider, model, microphone, hotkey preset, record mode
- **Hotkey test button** - verify detection before saving
- **Native notifications** on transcription completion, errors, or empty recordings

### Robustness
- **Provider fallback** - Groq primary, OpenAI secondary
- **Retry with exponential backoff** (3 attempts per provider)
- **Audio device fallback** - automatic switch to system default if saved device is unavailable
- **Hotkey fallback** - reverts to default if configured hotkey fails to start
- **Thread-safe** state management throughout

## Architecture

```
Python 3.11+ (tested on 3.14)
  + sounddevice     (audio recording)
  + Groq API        (whisper-large-v3 transcription)
  + OpenAI API      (Whisper fallback)
  + pynput          (global hotkeys, cross-platform)
  + pyperclip       (clipboard management)
  + pystray         (system tray icon)
  + tkinter         (floating overlay)
  + pydub           (audio chunking/compression)
```

## Project Structure

```
mindscribe-desktop/
  src/
    app.py                    # Main orchestration & state machine
    config/
      settings.py             # Dataclass config with JSON persistence
      dotenv_loader.py        # .env file loading
    core/
      audio_recorder.py       # Mic capture with real-time RMS levels
      transcriber.py          # Groq/OpenAI client with fallback + retry
      chunker.py              # Audio splitting for long recordings
      hotkey_manager.py       # Global keyboard shortcuts (pynput)
      text_inserter.py        # Clipboard paste simulation
    ui/
      overlay.py              # Floating window (waveform, timer, buttons)
      settings_window.py      # Settings dashboard (dark theme, hotkey presets)
      tray_icon.py            # System tray with state indicators
      icons.py                # Programmatic tray icons (Pillow)
      notification.py         # Native system notifications
  tests/
    test_audio_recorder.py    # 7 tests
    test_transcriber.py       # 7 tests
    test_chunker.py           # 12 tests (includes settings)
    conftest.py               # Shared fixtures
  run.py                      # Launcher script
  .env.example                # API key template
  requirements.txt
```

## Setup

### Prerequisites
- Python 3.11+ (tested on 3.14)
- A microphone
- Groq API key and/or OpenAI API key

### Installation

```bash
# Clone the repo
git clone https://github.com/aziztraorebf-ctrl/Mind-Scribe-Desktop-.git
cd Mind-Scribe-Desktop-

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env and add your Groq and/or OpenAI API keys
```

### Run

```bash
python run.py
```

Press your configured hotkey (default: **Ctrl+Shift+Space**) to start recording, press again to stop and transcribe. The text will be pasted into whatever field has focus. Right-click the tray icon to open Settings and change the hotkey, language, provider, and more.

## Configuration

Settings are stored in:
- **Windows**: `%LOCALAPPDATA%\MindScribeDesktop\config.json`
- **macOS**: `~/Library/Application Support/MindScribeDesktop/config.json`

| Setting | Default | Description |
|---------|---------|-------------|
| `language` | `"fr"` | Transcription language (ISO-639-1) |
| `primary_provider` | `"groq"` | Primary API (`groq` or `openai`) |
| `whisper_model` | `"whisper-large-v3"` | Whisper model variant |
| `hotkey` | `Ctrl+Shift+Space` | Global shortcut (9 presets available) |
| `record_mode` | `"toggle"` | `toggle` (press to start/stop) or `hold` (hold to record) |
| `post_process` | `false` | Clean up transcription with LLM (punctuation, fillers) |
| `show_notifications` | `true` | System notifications |
| `restore_clipboard` | `true` | Restore clipboard after paste |
| `prompt` | Contextual hint | Helps Whisper with domain vocabulary |

## Tests

```bash
python -m pytest tests/ -v
```

33 tests covering audio recording, transcription, chunking, settings, and dotenv loading.

## Building from Source (Windows)

### Prerequisites

- Python 3.12+ (tested with 3.14)
- pip (included with Python)

### Steps

1. Clone the repo:
   ```bash
   git clone https://github.com/aziztraorebf-ctrl/Mind-Scribe-Desktop-.git
   cd Mind-Scribe-Desktop-
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   ```bash
   .\venv\Scripts\activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Build the executable:
   ```bash
   .\build.ps1
   ```
   Or manually:
   ```bash
   python -m PyInstaller MindScribe.spec --clean -y
   ```

6. Copy your `.env` file to `dist\MindScribe\` with your API keys (`GROQ_API_KEY` and/or `OPENAI_API_KEY`).

7. Run the application:
   ```bash
   dist\MindScribe\MindScribe.exe
   ```

### Windows Defender Note

Unsigned PyInstaller executables may be flagged by Windows Defender. To prevent this, add `dist\MindScribe\` to your exclusions:

Windows Security > Virus & threat protection > Manage settings > Exclusions > Add folder

### Distribution

The `dist\MindScribe\` folder is self-contained and can be copied or zipped for distribution. Users need to place their own `.env` file next to `MindScribe.exe`.

## Current Status

### Phase 1-3: Core MVP (complete)
- [x] Audio recording with sounddevice (with device fallback)
- [x] Groq/OpenAI transcription with fallback and retry
- [x] Global hotkey (toggle and hold modes)
- [x] Universal text insertion via clipboard
- [x] System tray with state icons and dynamic hotkey display
- [x] Floating overlay with reactive waveform
- [x] Recording timer (freezes on pause)
- [x] Overlay control buttons (Pause/Resume, Stop, Cancel)
- [x] Draggable overlay (preserves position across state changes)
- [x] 26 unit tests passing

### Phase 4: Settings UI (complete)
- [x] Dark-themed settings dashboard (tkinter)
- [x] Language, provider, model selection
- [x] Microphone picker with deduplication and system default
- [x] LLM post-processing toggle (punctuation cleanup, filler removal)
- [x] Hotkey preset dropdown (9 OS-adaptive presets) with Test button
- [x] Toggle/Hold record mode selection
- [x] Notification and clipboard restore toggles

### Phase 5: Planned
- [ ] PyInstaller packaging (.exe / .app)
- [ ] macOS testing and compatibility
- [ ] Auto-start at boot
- [ ] Multi-language auto-detection
- [ ] Network error handling improvements (adaptive retry for rate limits)

## Tech Decisions

- **Python over Tauri/Electron**: Best ratio of dev speed / performance / cross-platform for this type of system tool. ~30-50MB RAM, ~15-30MB packaged size.
- **sounddevice over PyAudio**: Better macOS compatibility, cleaner API.
- **pynput over keyboard**: Cross-platform global hotkeys without macOS permission issues.
- **whisper-large-v3 (not turbo)**: Better accuracy for non-standard accents (8.4% vs 10.9% WER).
- **language="fr" parameter**: Reduces word error rate by ~30% for French transcription.

## License

Private project.
