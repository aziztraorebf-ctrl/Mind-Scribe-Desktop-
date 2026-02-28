# MindScribe — AutoCloud Context

## What is this project
macOS voice dictation app. Global hotkey → record audio → Whisper transcription → paste into active field.
Built with Python 3.11+ and PyQt6. No web server. No Electron. Fully native macOS.

## Tech stack
- Python 3.11+, PyQt6 (UI)
- Groq API (primary transcription), OpenAI API (fallback)
- Whisper large-v3 / large-v3-turbo
- sounddevice + PortAudio (microphone)
- pynput + Quartz (global hotkeys)
- SQLite via stdlib sqlite3 (new — for history persistence)
- Config persisted as JSON in ~/Library/Application Support/MindScribeDesktop/

## Key files — DO NOT modify
- src/ui/overlay.py — floating recording overlay (waveform, timer, buttons)
- src/core/transcriber.py — Groq/OpenAI transcription + LLM post-processing
- src/core/hotkey_manager.py — global hotkey listener (Quartz-based)
- src/core/audio_recorder.py — microphone capture
- src/core/chunker.py — audio splitting for long recordings
- src/config/dotenv_loader.py — .env loader

## Key files — safe to modify
- src/app.py — main orchestrator (MindScribeApp class)
- src/ui/tray_icon.py — system tray icon and menu
- src/ui/settings_window.py — settings window (remove vocabulary section, it moves to dashboard)
- src/ui/history_window.py — replace entirely with new dashboard
- src/config/settings.py — add active_style field

## Existing patterns to follow
- Thread safety: all UI updates via pyqtSignal (see overlay.py for reference pattern)
- Dark theme colors: bg=#1e1e2e, field=#2a2a3e, fg=#e0e0e0, fg_dim=#999999, accent=#3b82f6
- OS font: ".AppleSystemUIFont" on macOS, "Segoe UI" on Windows
- Mono font: "Menlo" on macOS, "Consolas" on Windows
- Settings persistence: dataclass + asdict() + json, never API keys in file
- No emojis in .py files
- Full type hints on all functions
- logging.getLogger(__name__) in every module

## VocabularyStore (src/core/vocabulary_store.py)
Already exists. Persists a list of words to ~/Library/.../vocabulary.json.
build_prompt_suffix() returns a string appended to the Whisper prompt.
Already wired into app.py via _effective_prompt().
The Dashboard Dictionary tab is just a better UI for this — do not duplicate the logic.

## Active style wiring
When the user changes the active style in the dashboard:
1. Update settings.active_style (persist via settings.save())
2. Call transcriber.prompt = new_prompt (live update, no restart needed)
The transcriber.prompt property is writable — see transcriber.py line 33.

## Run command
source venv-mac/bin/activate && python run.py

## Tests
python -m pytest tests/ -v
