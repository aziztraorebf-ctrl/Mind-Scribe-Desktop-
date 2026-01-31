# Phase 5A: PyInstaller Windows Packaging - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Package MindScribe Desktop as a standalone Windows .exe that runs without Python installed, loads .env from its own directory, and can be distributed as a single folder.

**Architecture:** PyInstaller `--onedir` bundle (not `--onefile`) because sounddevice needs PortAudio DLLs alongside the exe, and tkinter needs Tcl/Tk data. A `.spec` file gives us full control over hidden imports, binary bundling, and the .env search path. The dotenv_loader must be adapted to search next to the executable when frozen.

**Tech Stack:** PyInstaller 6.x, Python 3.14, sounddevice (PortAudio DLLs), pynput, pystray, Pillow, plyer, tkinter, numpy

---

## Critical Context

### Python 3.14 + PyInstaller
Python 3.14 is very new. PyInstaller 6.x supports it but may need `--noupx` flag and latest version. If PyInstaller fails on 3.14, fallback is `pip install pyinstaller --pre`.

### Why --onedir not --onefile
- `--onefile` extracts to a temp dir on every launch (slow startup, ~5-8s)
- `--onefile` breaks PortAudio DLL loading (sounddevice can't find DLLs)
- `--onedir` starts instantly and keeps DLLs in predictable location
- Final distribution: zip the folder, user extracts and runs .exe

### Dependencies requiring special handling
| Dependency | Issue | Solution |
|-----------|-------|---------|
| sounddevice | Needs `_sounddevice_data/portaudio-binaries/*.dll` | `collect_data_files('_sounddevice_data')` |
| plyer | Lazy imports platform backends | `hiddenimport: plyer.platforms.win.notification` |
| pydub | Needs ffmpeg for MP3 export | Bundle ffmpeg.exe OR warn user |
| tkinter | Needs Tcl/Tk data files | PyInstaller handles automatically |
| numpy | Large binary, many sub-packages | `exclude: numpy.testing, numpy.f2py` to reduce size |

### .env Loading When Frozen
Current `dotenv_loader.py` searches `Path.cwd()` and `Path(__file__).parent.parent.parent`. When frozen by PyInstaller:
- `Path(__file__)` points inside the extracted bundle (useless)
- `Path.cwd()` depends on how user launches the .exe
- **Fix:** Add `sys._MEIPASS` parent check + exe directory check

---

## Task 1: Install PyInstaller and verify it works

**Files:**
- Modify: `requirements.txt` (add pyinstaller)

**Step 1: Install PyInstaller**

Run:
```powershell
Set-Location 'C:\Users\azizt\mindscribe-desktop'
.\venv\Scripts\pip.exe install pyinstaller
```

Expected: Successfully installed pyinstaller-6.x

**Step 2: Verify PyInstaller sees the project**

Run:
```powershell
.\venv\Scripts\pyinstaller.exe --help | Select-String "version"
```

Expected: Shows PyInstaller version

**Step 3: Quick smoke test - can PyInstaller analyze run.py?**

Run:
```powershell
.\venv\Scripts\pyi-makespec.exe run.py --name MindScribe --noconsole
```

Expected: Creates `MindScribe.spec` in project root (we'll replace this with our custom spec)

**Step 4: Clean up generated spec (we'll write our own)**

Delete the auto-generated MindScribe.spec - we need a custom one.

**Step 5: Commit**

```bash
git add requirements.txt
git commit -m "chore: add pyinstaller to requirements for Phase 5 packaging"
```

---

## Task 2: Fix dotenv_loader for frozen executables

**Files:**
- Modify: `src/config/dotenv_loader.py`
- Create: `tests/test_dotenv_loader.py`

**Step 1: Write the failing test**

Create `tests/test_dotenv_loader.py`:

```python
"""Tests for .env loading, including PyInstaller frozen mode."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config.dotenv_loader import load_env, _get_search_dirs


class TestGetSearchDirs:
    """Test that _get_search_dirs returns correct paths for both normal and frozen modes."""

    def test_normal_mode_includes_cwd(self):
        dirs = _get_search_dirs()
        assert Path.cwd() in dirs

    def test_normal_mode_includes_project_root(self):
        dirs = _get_search_dirs()
        # Project root is 3 levels up from dotenv_loader.py
        expected = Path(__file__).resolve().parent.parent / "src" / "config"
        # At least one dir should be an ancestor of src/config
        assert any(d.exists() for d in dirs)

    def test_frozen_mode_includes_exe_directory(self, tmp_path):
        fake_exe = tmp_path / "MindScribe.exe"
        fake_exe.touch()
        with patch.object(sys, 'frozen', True, create=True), \
             patch.object(sys, 'executable', str(fake_exe)):
            dirs = _get_search_dirs()
            assert tmp_path in dirs

    def test_frozen_mode_prioritizes_exe_directory(self, tmp_path):
        fake_exe = tmp_path / "MindScribe.exe"
        fake_exe.touch()
        with patch.object(sys, 'frozen', True, create=True), \
             patch.object(sys, 'executable', str(fake_exe)):
            dirs = _get_search_dirs()
            # exe dir should be first in the list
            assert dirs[0] == tmp_path


class TestLoadEnv:
    """Test that load_env reads API keys from environment."""

    def test_returns_empty_keys_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove any existing keys
            os.environ.pop("GROQ_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            result = load_env()
            assert result["groq_api_key"] == ""
            assert result["openai_api_key"] == ""

    def test_reads_groq_key_from_env(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            result = load_env()
            assert result["groq_api_key"] == "test-groq-key"

    def test_reads_openai_key_from_env(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}):
            result = load_env()
            assert result["openai_api_key"] == "test-openai-key"
```

**Step 2: Run test to verify it fails**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_dotenv_loader.py -v
```

Expected: FAIL - `_get_search_dirs` does not exist yet, `frozen` tests fail

**Step 3: Implement the fix**

Modify `src/config/dotenv_loader.py`:

```python
"""Load environment variables from .env file."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _get_search_dirs() -> list[Path]:
    """Return directories to search for .env file, ordered by priority.

    When running as a PyInstaller frozen executable, prioritizes
    the directory containing the .exe so users can place .env next to it.
    """
    dirs = []

    # Frozen mode (PyInstaller): directory containing the .exe
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir)

    # Current working directory
    dirs.append(Path.cwd())

    # Project root (3 levels up from this file) - only useful in dev mode
    project_root = Path(__file__).resolve().parent.parent.parent
    if project_root not in dirs:
        dirs.append(project_root)

    return dirs


def load_env() -> dict[str, str]:
    """Load .env from best available location and return API keys."""
    for d in _get_search_dirs():
        env_path = d / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            break

    return {
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
    }
```

**Step 4: Run tests to verify they pass**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_dotenv_loader.py -v
```

Expected: All 7 tests PASS

**Step 5: Run full test suite to check no regressions**

Run:
```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: All tests pass (26 existing + 7 new = 33)

**Step 6: Commit**

```bash
git add src/config/dotenv_loader.py tests/test_dotenv_loader.py
git commit -m "fix: dotenv_loader searches next to .exe when frozen by PyInstaller

Adds _get_search_dirs() that prioritizes the executable's directory
in frozen mode, so users can place .env next to MindScribe.exe."
```

---

## Task 3: Write the PyInstaller .spec file

**Files:**
- Create: `MindScribe.spec`

**Step 1: Write the spec file**

Create `MindScribe.spec` in project root:

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for MindScribe Desktop.

Build command:
    pyinstaller MindScribe.spec

Output:
    dist/MindScribe/MindScribe.exe
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect PortAudio DLLs bundled with sounddevice
sounddevice_data = collect_data_files('_sounddevice_data')

# Collect plyer platform backends (lazy-loaded)
plyer_imports = collect_submodules('plyer.platforms.win')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=sounddevice_data,
    hiddenimports=[
        # App modules (PyInstaller may miss dynamic imports)
        'src',
        'src.app',
        'src.config',
        'src.config.settings',
        'src.config.dotenv_loader',
        'src.core',
        'src.core.audio_recorder',
        'src.core.chunker',
        'src.core.hotkey_manager',
        'src.core.text_inserter',
        'src.core.transcriber',
        'src.ui',
        'src.ui.icons',
        'src.ui.notification',
        'src.ui.overlay',
        'src.ui.settings_window',
        'src.ui.tray_icon',
        # Third-party hidden imports
        'plyer.platforms.win',
        'plyer.platforms.win.notification',
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pystray._win32',
        # audioop replacement for Python 3.13+
        'audioop_lts',
        'audioop',
    ] + plyer_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev-only packages
        'pytest',
        'pytest_cov',
        'customtkinter',
        # Unused numpy sub-packages (saves ~30MB)
        'numpy.testing',
        'numpy.f2py',
        'numpy.distutils',
        'numpy.doc',
        # Unused stdlib
        'unittest',
        'pdb',
        'doctest',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MindScribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disable UPX - avoids false antivirus positives
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/mindscribe.ico',  # TODO: Add app icon in future
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MindScribe',
)
```

**Step 2: Verify the spec file is valid Python**

Run:
```powershell
.\venv\Scripts\python.exe -c "compile(open('MindScribe.spec').read(), 'MindScribe.spec', 'exec'); print('Spec syntax OK')"
```

Expected: `Spec syntax OK`

**Step 3: Commit**

```bash
git add MindScribe.spec
git commit -m "feat: add PyInstaller spec file for Windows onedir build

Configures hidden imports for plyer/pynput/pystray Win32 backends,
bundles PortAudio DLLs from _sounddevice_data, excludes dev/test
packages to reduce bundle size. Uses --noconsole for GUI-only mode."
```

---

## Task 4: First build attempt and fix issues

**Files:**
- May modify: `MindScribe.spec` (to fix build errors)

**Step 1: Run the build**

Run:
```powershell
Set-Location 'C:\Users\azizt\mindscribe-desktop'
.\venv\Scripts\pyinstaller.exe MindScribe.spec --clean 2>&1 | Tee-Object -FilePath build.log
```

Expected: Build completes (may have warnings). Creates `dist/MindScribe/MindScribe.exe`

**Step 2: Check the output**

Run:
```powershell
Get-ChildItem dist/MindScribe -Name | Select-Object -First 20
Get-ChildItem dist/MindScribe -Recurse | Measure-Object -Property Length -Sum | ForEach-Object { "Total size: {0:N0} MB" -f ($_.Sum / 1MB) }
```

Expected: MindScribe.exe exists, total folder ~30-80MB

**Step 3: Smoke test - launch the exe**

Run:
```powershell
Start-Process .\dist\MindScribe\MindScribe.exe
```

Expected: App starts, tray icon appears. If it crashes, check:
```powershell
# Re-run with console enabled for debugging
# Temporarily change console=True in spec, rebuild, and run from terminal
.\dist\MindScribe\MindScribe.exe
```

**Step 4: Fix any import errors**

Common issues and fixes:
- `ModuleNotFoundError: plyer.platforms.win.notification` -> Add to hiddenimports
- `sounddevice.PortAudioError: libportaudio not found` -> Verify `_sounddevice_data` is in datas
- `audioop` missing -> Verify `audioop_lts` in hiddenimports
- tkinter missing -> Install `tk` package or ensure Python includes it

**Step 5: Commit fixes (if any)**

```bash
git add MindScribe.spec
git commit -m "fix: adjust PyInstaller spec for discovered import issues"
```

---

## Task 5: Validate the packaged .exe end-to-end

**Step 1: Copy .env to dist folder**

Run:
```powershell
Copy-Item '.env' 'dist\MindScribe\.env'
```

**Step 2: Full functional test**

Manual checklist:
- [ ] App starts from dist/MindScribe/MindScribe.exe
- [ ] Tray icon appears (gray microphone)
- [ ] Right-click tray -> Settings opens
- [ ] Settings dropdown shows 9 hotkey presets
- [ ] Test button detects hotkey press
- [ ] Save settings closes window
- [ ] Hotkey (Ctrl+Alt) starts recording
- [ ] Overlay appears with waveform
- [ ] Stop recording -> transcription runs
- [ ] Text pasted into active field
- [ ] Notification appears
- [ ] Tray -> Quit exits cleanly

**Step 3: Check .env loading**

Verify that the .exe reads .env from its own directory:
```powershell
# Remove .env from project root temporarily
Rename-Item '.env' '.env.bak'

# Launch from dist - should still work because .env is in dist/MindScribe/
Start-Process .\dist\MindScribe\MindScribe.exe

# Restore after testing
Rename-Item '.env.bak' '.env'
```

**Step 4: Test without .env (should show error notification)**

```powershell
# Remove .env from dist folder
Remove-Item 'dist\MindScribe\.env'
Start-Process .\dist\MindScribe\MindScribe.exe
```

Expected: App starts but shows "No API keys configured" error.

---

## Task 6: Add build script and .gitignore entries

**Files:**
- Create: `build.ps1` (Windows build script)
- Modify: `.gitignore` (add build artifacts)

**Step 1: Write build.ps1**

Create `build.ps1`:

```powershell
# MindScribe Desktop - Windows Build Script
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== MindScribe Desktop Build ===" -ForegroundColor Cyan

# Check Python and PyInstaller
Write-Host "Checking prerequisites..."
& python -c "import PyInstaller; print(f'PyInstaller {PyInstaller.__version__}')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller not installed. Run: pip install pyinstaller" -ForegroundColor Red
    exit 1
}

# Clean previous build
if (Test-Path "dist\MindScribe") {
    Write-Host "Cleaning previous build..."
    Remove-Item -Recurse -Force "dist\MindScribe"
}
if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

# Build
Write-Host "Building MindScribe.exe..."
& pyinstaller MindScribe.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Build failed!" -ForegroundColor Red
    exit 1
}

# Show result
$exePath = "dist\MindScribe\MindScribe.exe"
if (Test-Path $exePath) {
    $size = (Get-ChildItem "dist\MindScribe" -Recurse | Measure-Object -Property Length -Sum).Sum
    Write-Host ""
    Write-Host "BUILD SUCCESSFUL" -ForegroundColor Green
    Write-Host "Output: dist\MindScribe\MindScribe.exe"
    Write-Host ("Total size: {0:N1} MB" -f ($size / 1MB))
    Write-Host ""
    Write-Host "To run: copy .env to dist\MindScribe\ then launch MindScribe.exe"
} else {
    Write-Host "ERROR: MindScribe.exe not found in dist/" -ForegroundColor Red
    exit 1
}
```

**Step 2: Update .gitignore**

Add to `.gitignore`:

```
# PyInstaller build artifacts
build/
dist/
*.spec.bak
build.log
```

Note: Do NOT gitignore `MindScribe.spec` - it's part of the project.

**Step 3: Run the build script**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Expected: Build succeeds, shows total size.

**Step 4: Commit**

```bash
git add build.ps1 .gitignore
git commit -m "feat: add Windows build script and gitignore for PyInstaller artifacts

build.ps1 runs PyInstaller with MindScribe.spec, cleans previous
builds, and shows output size. .gitignore excludes build/ and dist/."
```

---

## Task 7: Update README with build instructions

**Files:**
- Modify: `README.md`

**Step 1: Add Build section to README**

Add after the "### Run" section:

```markdown
### Build standalone .exe (Windows)

```bash
# Install PyInstaller (one time)
pip install pyinstaller

# Build
powershell -ExecutionPolicy Bypass -File build.ps1

# Or manually:
pyinstaller MindScribe.spec --clean
```

Output: `dist/MindScribe/MindScribe.exe` (~30-50MB folder)

To distribute:
1. Copy the entire `dist/MindScribe/` folder
2. Place your `.env` file (with API keys) inside the folder
3. Run `MindScribe.exe`
```

**Step 2: Update Phase 5 status in README**

Replace the Phase 5 section:

```markdown
### Phase 5: Packaging (in progress)
- [x] PyInstaller .spec file with hidden imports and PortAudio DLLs
- [x] .env loading from executable directory (frozen mode)
- [x] Windows build script (build.ps1)
- [x] Standalone .exe tested end-to-end
- [ ] macOS .app bundle
- [ ] Auto-start at boot
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add Windows build instructions and update Phase 5 status"
```

---

## Parallelization Strategy for Sub-Agents

Tasks that can be run in parallel:

| Parallel Group | Tasks | Rationale |
|---------------|-------|-----------|
| **Group A** | Task 1 (install PyInstaller) | Must be first - all others depend on it |
| **Group B** | Task 2 (dotenv_loader fix) + Task 3 (spec file) | Independent: one modifies Python code, other creates new file |
| **Group C** | Task 4 (first build) | Depends on Group A + B |
| **Group D** | Task 5 (validation) + Task 6 (build script + gitignore) | Task 5 needs user interaction; Task 6 is independent |
| **Group E** | Task 7 (README) | After everything else confirmed working |

### Execution Flow

```
Task 1 (install)
    |
    v
Task 2 (dotenv fix) ---+--- Task 3 (spec file)    [PARALLEL]
    |                   |
    +------- + ---------+
             |
             v
         Task 4 (first build + fix issues)
             |
             v
Task 5 (validate) ---+--- Task 6 (build script)   [PARALLEL]
    |                 |
    +------- + -------+
             |
             v
         Task 7 (README update)
```

---

## Known Risks and Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| PyInstaller doesn't support Python 3.14 | Medium | Try `pip install pyinstaller --pre`, or downgrade to 3.13 in venv |
| PortAudio DLLs not found at runtime | High | `collect_data_files('_sounddevice_data')` + verify in dist/ |
| pydub needs ffmpeg for MP3 export | High | Bundle ffmpeg.exe OR catch exception and fall back to raw WAV chunks |
| Antivirus false positive on .exe | Medium | `upx=False` already set; may need code signing later |
| Bundle too large (>100MB) | Low | Exclude numpy test modules, strip unused stdlib |
| plyer notification fails in frozen mode | Medium | Test notification in Task 5; fallback already exists in notification.py |

## ffmpeg Note

`pydub` uses ffmpeg for MP3 compression in `chunker.py`. Without ffmpeg:
- Short recordings (<25MB WAV) will fail to compress to MP3
- Fall back to raw WAV upload (works but uses more bandwidth)
- Long recordings (>25MB) will still chunk correctly as WAV

Options:
1. **Bundle ffmpeg.exe** (~80MB, doubles bundle size) - Not recommended for now
2. **Skip MP3 compression** when ffmpeg missing (graceful degradation) - Already handled by try/except in `prepare_audio()`
3. **Install ffmpeg separately** and document it - Best for now

Current code already has try/except in `prepare_audio()` line 88, so this is already handled gracefully.
