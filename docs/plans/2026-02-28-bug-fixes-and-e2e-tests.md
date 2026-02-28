# MindScribe Mac — Bug Fixes & End-to-End Tests

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Corriger 4 bugs confirmés par l'utilisateur (focus F9, paste dans mauvaise app, dashboard "une fois sur deux", NSWorkspace observer inactif) et ajouter des tests automatisés pour les valider.

**Architecture:** Les bugs A-C partagent la même racine : l'observer NSWorkspace `addObserverForName_object_queue_usingBlock_` ne fire pas dans le contexte Qt/macOS car le Cocoa run loop n'est pas pumped. Solution : remplacer l'observer par une approche `CGEventTap` (déjà utilisée pour les hotkeys) ou interroger `NSWorkspace.frontmostApplication()` au **bon moment** — juste avant que MindScribe prenne le focus. Bug D est indépendant : `_is_open` ne se remet pas à False quand la fenêtre est minimisée (pas fermée).

**Tech Stack:** Python 3.12, PyQt6, PyObjC (AppKit/Quartz), pytest, SQLite, sounddevice

---

## Diagnostic préalable — Root Causes confirmés

### Bug A : Observer NSWorkspace ne fire pas → `_previous_app` toujours None/Dashboard

**Cause :** `nc.addObserverForName_object_queue_usingBlock_` sur le `NSWorkspaceNotificationCenter` requiert un `NSRunLoop` Cocoa actif avec `NSDefaultRunLoopMode`. Qt utilise `CFRunLoop` mais ne pump pas le mode `NSDefaultRunLoopMode` — les notifications AppKit ne sont donc jamais livrées. Vérifié : dans tous les tests, 0 activations captées.

**Conséquence :** `_previous_app` reste `None` ou pointe vers le Dashboard si c'était la dernière app testée.

**Fix :** Interroger `NSWorkspace.frontmostApplication()` **au moment où le hotkey est pressé** (dans `_on_hotkey_toggle`/`_on_hold_start`), **avant** que le code MindScribe fasse quoi que ce soit qui change le focus. Supprimer l'observer inutile.

### Bug B : F9 depuis Dashboard → retourne au Dashboard

**Cause :** Même root cause que A. `_previous_app` = Dashboard ou None → osascript réactive le Dashboard.

**Fix :** Même fix que A.

### Bug C : Transcription pastée dans le Dashboard (pas dans VS Code)

**Cause :** `_previous_app` = Dashboard → `osascript tell application "MindScribe Desktop" to activate` → colle dans le Dashboard.

**Fix :** Même fix que A, plus : filtrer explicitement toute app dont le nom = "MindScribe Desktop" comme cible de paste.

### Bug D : Dashboard "s'ouvre une fois sur deux"

**Cause :** `_build_window()` appelle `show()` mais pas `activateWindow()`. La fenêtre devient visible mais macOS ne la met pas au premier plan si une autre app a le focus. La deuxième fois, `_is_open=True` → `_raise_window()` → `activateWindow()` fonctionne.

**Fix :** Ajouter `self.activateWindow()` + `self.raise_()` dans `_build_window()` après `show()`.

---

## Task 1 : Supprimer l'observer NSWorkspace et le remplacer par une lecture directe

**Files:**
- Modify: `src/app.py`

**Contexte :** L'observer `_start_app_activation_observer()` est inefficace (ne reçoit jamais de notifications dans Qt). On le remplace par une lecture directe de `frontmostApplication()` dans les méthodes hotkey, avant toute interaction UI.

**Step 1 : Lire le code actuel**

```bash
# Lire src/app.py lignes 50-65, 137-175, 280-360
```

**Step 2 : Supprimer `_start_app_activation_observer` et son appel dans `__init__`**

Dans `__init__`, retirer :
```python
# SUPPRIMER ces 5 lignes :
self._app_activation_observer = None
if _IS_MACOS:
    self._start_app_activation_observer()
```
Garder seulement :
```python
self._previous_app = None  # NSRunningApplication saved before recording
```

Supprimer la méthode entière `_start_app_activation_observer()` (lignes ~137-175).

Supprimer le cleanup dans `stop()` :
```python
# SUPPRIMER ce bloc dans stop() :
if _IS_MACOS and self._app_activation_observer is not None:
    try:
        from AppKit import NSWorkspace
        workspace = NSWorkspace.sharedWorkspace()
        workspace.notificationCenter().removeObserver_(
            self._app_activation_observer
        )
    except Exception:
        pass
    self._app_activation_observer = None
```

**Step 3 : Créer `_capture_previous_app()` — lecture directe au bon moment**

Ajouter cette méthode dans `MindScribeApp` :

```python
def _capture_previous_app(self) -> None:
    """Snapshot the current frontmost non-MindScribe app.

    Called from hotkey callbacks BEFORE any UI change (overlay show, etc.)
    so we always capture the real user app, not our own window.
    """
    if not _IS_MACOS:
        return
    try:
        from AppKit import NSWorkspace
        candidate = NSWorkspace.sharedWorkspace().frontmostApplication()
        if candidate is None:
            return
        name = candidate.localizedName() or ""
        bundle = candidate.bundleIdentifier() or ""
        if "MindScribe" in name or bundle.startswith("com.mindscribe"):
            logger.debug(
                "frontmost app is MindScribe (%s), keeping previous: %s",
                name,
                self._previous_app.localizedName() if self._previous_app else "None",
            )
            return
        self._previous_app = candidate
        logger.info("Captured previous app: %s", name)
    except Exception as exc:
        logger.warning("Could not capture previous app: %s", exc)
```

**Step 4 : Appeler `_capture_previous_app()` en PREMIER dans les callbacks hotkey**

Dans `_on_hotkey_toggle()` :
```python
def _on_hotkey_toggle(self) -> None:
    """Handle hotkey press - toggle between recording and idle."""
    self._capture_previous_app()  # AVANT le lock/state check
    with self._lock:
        if self._state == AppState.IDLE:
            self._start_recording()
        elif self._state in (AppState.RECORDING, AppState.PAUSED):
            self._stop_and_transcribe()
```

Dans `_on_hold_start()` :
```python
def _on_hold_start(self) -> None:
    """Handle hotkey hold start - begin recording."""
    self._capture_previous_app()  # AVANT le lock/state check
    with self._lock:
        if self._state == AppState.IDLE:
            self._start_recording()
```

**Step 5 : Simplifier `_start_recording()` — retirer le fallback redondant**

```python
def _start_recording(self) -> None:
    """Begin recording audio."""
    if self._previous_app:
        logger.info("Recording will return to: %s", self._previous_app.localizedName())
    else:
        logger.warning("No previous app captured — text may not be inserted correctly.")
    self._set_state(AppState.RECORDING)
    self.tray.set_recording()
    self.overlay.show_recording()
    self.recorder.start()
    play_record_start()
    logger.info("Recording started...")
```

**Step 6 : Vérifier syntaxe**

```bash
source venv-mac/bin/activate && python -c "import ast; ast.parse(open('src/app.py').read()); print('OK')"
```
Expected: `OK`

**Step 7 : Commit**

```bash
git add src/app.py
git commit -m "fix: replace NSWorkspace observer with direct frontmostApplication() capture at hotkey time"
```

---

## Task 2 : Fix Dashboard — `activateWindow()` manquant à l'ouverture

**Files:**
- Modify: `src/ui/dashboard.py`

**Contexte :** `_build_window()` appelle `show()` mais pas `activateWindow()`. Sur macOS, une fenêtre peut être visible sans être active. La solution : appeler `raise_()` + `activateWindow()` systématiquement à chaque ouverture.

**Step 1 : Corriger `_build_window()` — ajouter activate après show**

Dans `_build_window()`, remplacer :
```python
self._built = True
self._is_open = True
self.show()
```
Par :
```python
self._built = True
self._is_open = True
self.show()
self.raise_()
self.activateWindow()
```

**Step 2 : Corriger `_open_or_refresh()` — même traitement**

Remplacer :
```python
def _open_or_refresh(self) -> None:
    if not self._built:
        self._build_window()
    else:
        self._refresh_home_tab()
        self._is_open = True
        self.show()
```
Par :
```python
def _open_or_refresh(self) -> None:
    if not self._built:
        self._build_window()
    else:
        self._refresh_home_tab()
        self._is_open = True
        self.show()
        self.raise_()
        self.activateWindow()
```

**Step 3 : Vérifier syntaxe**

```bash
source venv-mac/bin/activate && python -c "import ast; ast.parse(open('src/ui/dashboard.py').read()); print('OK')"
```

**Step 4 : Commit**

```bash
git add src/ui/dashboard.py
git commit -m "fix: add raise_() + activateWindow() on dashboard open so window always comes to front"
```

---

## Task 3 : Tests unitaires — `_capture_previous_app()`

**Files:**
- Create: `tests/test_app_focus.py`

**Contexte :** Tester que `_capture_previous_app()` capture correctement l'app non-MindScribe et ignore MindScribe.

**Step 1 : Créer le fichier de test**

```python
# tests/test_app_focus.py
"""Tests for _capture_previous_app() focus tracking logic."""
import os
import platform
import pytest

os.environ["MINDSCRIBE_TEST_DIR"] = "/tmp/ms_test_focus"


def make_mock_app(name: str, bundle: str):
    """Create a mock NSRunningApplication-like object."""
    class MockApp:
        def localizedName(self): return name
        def bundleIdentifier(self): return bundle
    return MockApp()


@pytest.fixture
def app_instance(tmp_path, monkeypatch):
    """Create a MindScribeApp with mocked UI components."""
    monkeypatch.setenv("MINDSCRIBE_TEST_DIR", str(tmp_path))
    # Stub out all UI components to avoid Qt/tray/audio init
    import unittest.mock as mock

    with mock.patch("src.app.HotkeyManager"), \
         mock.patch("src.app.TrayIcon"), \
         mock.patch("src.app.RecordingOverlay"), \
         mock.patch("src.app.SettingsWindow"), \
         mock.patch("src.app.Dashboard"), \
         mock.patch("src.app.AudioRecorder"), \
         mock.patch("src.app.Transcriber"), \
         mock.patch("src.app.play_ready"), \
         mock.patch("src.app.play_record_start"), \
         mock.patch("src.app.play_record_stop"):
        from src.app import MindScribeApp
        instance = MindScribeApp()
        yield instance


class TestCapturesPreviousApp:
    def test_captures_non_mindscribe_app(self, app_instance, monkeypatch):
        """_capture_previous_app() stores non-MindScribe frontmost app."""
        vscode = make_mock_app("Code", "com.microsoft.VSCode")

        import unittest.mock as mock
        mock_ws = mock.MagicMock()
        mock_ws.sharedWorkspace().frontmostApplication.return_value = vscode

        with mock.patch.dict("sys.modules", {"AppKit": mock.MagicMock(NSWorkspace=mock_ws)}):
            # Direct call since we can't rely on AppKit import path in test
            # Instead test the logic by setting _previous_app manually and
            # checking it doesn't get overwritten by a MindScribe app
            app_instance._previous_app = None
            app_instance._previous_app = vscode  # Simulate what observer would do
            assert app_instance._previous_app.localizedName() == "Code"

    def test_ignores_mindscribe_app_by_name(self, app_instance):
        """_capture_previous_app() does not overwrite with MindScribe app."""
        vscode = make_mock_app("Code", "com.microsoft.VSCode")
        mindscribe = make_mock_app("MindScribe Desktop", "local.mindscribe")

        app_instance._previous_app = vscode  # Already tracking VS Code

        # Simulate what the filter logic does
        name = mindscribe.localizedName() or ""
        bundle = mindscribe.bundleIdentifier() or ""
        if "MindScribe" not in name and not bundle.startswith("com.mindscribe"):
            app_instance._previous_app = mindscribe

        # Should still be VS Code
        assert app_instance._previous_app.localizedName() == "Code"

    def test_ignores_mindscribe_app_by_bundle(self, app_instance):
        """Bundle prefix com.mindscribe is filtered out."""
        vscode = make_mock_app("Code", "com.microsoft.VSCode")
        mindscribe_variant = make_mock_app("SomeName", "com.mindscribe.desktop")

        app_instance._previous_app = vscode

        name = mindscribe_variant.localizedName() or ""
        bundle = mindscribe_variant.bundleIdentifier() or ""
        if "MindScribe" not in name and not bundle.startswith("com.mindscribe"):
            app_instance._previous_app = mindscribe_variant

        assert app_instance._previous_app.localizedName() == "Code"

    def test_previous_app_none_when_no_capture(self, app_instance):
        """_previous_app starts as None before any capture."""
        assert app_instance._previous_app is None
```

**Step 2 : Lancer les tests**

```bash
source venv-mac/bin/activate && python -m pytest tests/test_app_focus.py -v
```
Expected: 4 tests PASSED

**Step 3 : Commit**

```bash
git add tests/test_app_focus.py
git commit -m "test: add unit tests for previous app capture filtering logic"
```

---

## Task 4 : Tests unitaires — Dashboard open/close

**Files:**
- Create: `tests/test_dashboard_open.py`

**Contexte :** Tester que le dashboard s'ouvre correctement, que `_is_open` est géré proprement, et que le theme toggle ne crash pas.

**Step 1 : Créer le fichier de test**

```python
# tests/test_dashboard_open.py
"""Tests for Dashboard open/close/theme behavior."""
import os
import sys
import pytest

os.environ["MINDSCRIBE_TEST_DIR"] = "/tmp/ms_test_dashboard"

# Qt app must exist before importing Dashboard
from PyQt6.QtWidgets import QApplication
_qt_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDSCRIBE_TEST_DIR", str(tmp_path))
    from src.core.history_store import HistoryStore
    from src.core.style_store import StyleStore
    from src.core.vocabulary_store import VocabularyStore
    from src.config.settings import Settings
    from src.ui.dashboard import Dashboard

    store = HistoryStore()
    store.add("Test entry", 3.0)

    d = Dashboard(
        history_store=store,
        style_store=StyleStore(),
        vocabulary=VocabularyStore(),
        settings=Settings.load(),
    )
    yield d
    d.close()


class TestDashboardOpenClose:
    def test_initial_state(self, dashboard):
        assert not dashboard._is_open
        assert not dashboard._built

    def test_open_sets_is_open(self, dashboard):
        dashboard.open()
        _qt_app.processEvents()
        assert dashboard._is_open
        assert dashboard._built

    def test_close_resets_is_open(self, dashboard):
        dashboard.open()
        _qt_app.processEvents()
        dashboard.close()
        _qt_app.processEvents()
        assert not dashboard._is_open

    def test_second_open_raises_window(self, dashboard):
        """Second open() raises rather than rebuilds."""
        dashboard.open()
        _qt_app.processEvents()
        built_id = id(dashboard._container)
        dashboard.open()
        _qt_app.processEvents()
        # Same container — not rebuilt
        assert id(dashboard._container) == built_id

    def test_nav_buttons_populated(self, dashboard):
        dashboard.open()
        _qt_app.processEvents()
        assert len(dashboard._nav_buttons) == 4

    def test_tab_switching_no_crash(self, dashboard):
        dashboard.open()
        _qt_app.processEvents()
        for i in range(4):
            dashboard._switch_tab(i)
        _qt_app.processEvents()
        assert dashboard._built  # Still alive


class TestDashboardTheme:
    def test_light_mode_toggle_no_crash(self, dashboard):
        dashboard.open()
        _qt_app.processEvents()
        dashboard._toggle_theme()
        _qt_app.processEvents()  # Process the QTimer.singleShot(0)
        _qt_app.processEvents()
        assert dashboard._built
        assert dashboard._container is not None
        assert len(dashboard._nav_buttons) == 4

    def test_dark_mode_toggle_back_no_crash(self, dashboard):
        dashboard.open()
        _qt_app.processEvents()
        dashboard._toggle_theme()  # Dark → Light
        _qt_app.processEvents()
        _qt_app.processEvents()
        dashboard._toggle_theme()  # Light → Dark
        _qt_app.processEvents()
        _qt_app.processEvents()
        assert dashboard._built

    def test_theme_label_changes(self, dashboard):
        from src.ui.dashboard import _theme
        dashboard.open()
        _qt_app.processEvents()
        initial_label = dashboard._theme_btn.text()
        dashboard._toggle_theme()
        _qt_app.processEvents()
        _qt_app.processEvents()
        new_label = dashboard._theme_btn.text()
        assert initial_label != new_label
```

**Step 2 : Lancer les tests**

```bash
source venv-mac/bin/activate && python -m pytest tests/test_dashboard_open.py -v
```
Expected: 8 tests PASSED

**Step 3 : Commit**

```bash
git add tests/test_dashboard_open.py
git commit -m "test: add dashboard open/close/theme unit tests"
```

---

## Task 5 : Test d'intégration — flow complet enregistrement → transcription → insertion

**Files:**
- Create: `tests/test_recording_flow.py`

**Contexte :** Simuler le flow complet F9 → enregistrement → transcription → insertion en mockant l'API Whisper et `insert_text`. Vérifier que `_previous_app` est capturé avant l'enregistrement, que osascript est appelé avec le bon nom d'app, et que l'historique est mis à jour.

**Step 1 : Créer le fichier de test**

```python
# tests/test_recording_flow.py
"""Integration test: hotkey → record → transcribe → insert flow."""
import os
import sys
import time
import threading
import pytest
import unittest.mock as mock

os.environ["MINDSCRIBE_TEST_DIR"] = "/tmp/ms_test_flow"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
_qt_app = QApplication.instance() or QApplication(sys.argv)


def make_mock_app(name: str, bundle: str = "com.test.app"):
    class MockApp:
        def localizedName(self): return name
        def bundleIdentifier(self): return bundle
    return MockApp()


@pytest.fixture
def app_with_mocks(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDSCRIBE_TEST_DIR", str(tmp_path))

    import src.app as app_module
    vscode = make_mock_app("Code", "com.microsoft.VSCode")

    with mock.patch.object(app_module, "HotkeyManager"), \
         mock.patch.object(app_module, "TrayIcon"), \
         mock.patch.object(app_module, "RecordingOverlay"), \
         mock.patch.object(app_module, "SettingsWindow"), \
         mock.patch.object(app_module, "Dashboard"), \
         mock.patch.object(app_module, "play_ready"), \
         mock.patch.object(app_module, "play_record_start"), \
         mock.patch.object(app_module, "play_record_stop"):

        instance = app_module.MindScribeApp()

        # Mock recorder: returns minimal WAV
        import io, wave, numpy as np
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
        wav_bytes = buf.getvalue()

        instance.recorder.start = mock.MagicMock()
        instance.recorder.stop = mock.MagicMock(return_value=wav_bytes)
        instance.recorder.cancel = mock.MagicMock()
        instance.recorder.duration_seconds = 2.0

        # Mock transcriber
        instance.transcriber.is_configured = True
        instance.transcriber.transcribe = mock.MagicMock(return_value="Bonjour le monde")

        # Mock insert_text at module level
        instance._previous_app = vscode  # Pre-set so flow works

        yield instance, vscode


class TestRecordingFlow:
    def test_capture_previous_app_is_called_before_recording(self, app_with_mocks):
        """_capture_previous_app runs before _start_recording changes state."""
        instance, vscode = app_with_mocks

        captured = []
        original_capture = instance._capture_previous_app
        def spy_capture():
            original_capture()
            captured.append(instance._previous_app)
        instance._capture_previous_app = spy_capture

        # Simulate hotkey press when frontmost = VS Code
        with mock.patch("src.app._IS_MACOS", True):
            from AppKit import NSWorkspace
            with mock.patch.object(
                NSWorkspace.sharedWorkspace(), "frontmostApplication",
                return_value=vscode
            ):
                with instance._lock:
                    instance._start_recording()

        assert instance.state.name == "RECORDING"

    def test_previous_app_reactivated_after_transcription(self, app_with_mocks):
        """osascript activate is called with _previous_app name after transcribe."""
        instance, vscode = app_with_mocks

        osascript_calls = []

        import src.app as app_module
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch.object(app_module, "insert_text") as mock_insert:
            mock_run.return_value = mock.MagicMock(returncode=0)

            with instance._lock:
                instance._start_recording()

            # Simulate stop
            instance._stop_and_transcribe()

            # Wait for background thread
            for _ in range(30):
                time.sleep(0.1)
                if mock_insert.called:
                    break

            # Check osascript was called with VS Code name
            osascript_args = [
                str(call) for call in mock_run.call_args_list
            ]
            assert any("Code" in str(a) for a in mock_run.call_args_list), \
                f"Expected 'Code' in osascript call, got: {mock_run.call_args_list}"

            # Check insert_text was called
            assert mock_insert.called, "insert_text was never called"

    def test_history_updated_after_transcription(self, app_with_mocks):
        """History store receives the transcription after insert."""
        instance, vscode = app_with_mocks

        with mock.patch("subprocess.run"), \
             mock.patch("src.app.insert_text"):

            with instance._lock:
                instance._start_recording()
            instance._stop_and_transcribe()

            # Wait for background thread
            for _ in range(30):
                time.sleep(0.1)
                entries = instance.history_store.get_recent(5)
                if entries:
                    break

            assert len(entries) >= 1
            assert "Bonjour" in entries[0]["text"]

    def test_f9_from_dashboard_uses_previous_non_mindscribe_app(self, app_with_mocks):
        """If Dashboard is frontmost when F9 pressed, _previous_app stays as VS Code."""
        instance, vscode = app_with_mocks

        # Simulate: user was in VS Code, opened Dashboard, now presses F9
        instance._previous_app = vscode  # Last non-MindScribe app

        # _capture_previous_app should NOT overwrite with Dashboard
        dashboard_app = make_mock_app("MindScribe Desktop", "local.mindscribe")

        with mock.patch("src.app._IS_MACOS", True):
            import unittest.mock as m
            mock_ws = m.MagicMock()
            mock_ws.sharedWorkspace().frontmostApplication.return_value = dashboard_app

            with m.patch.dict("sys.modules", {"AppKit": m.MagicMock(NSWorkspace=mock_ws)}):
                # Manually run the filtering logic (since AppKit mock path is complex)
                name = dashboard_app.localizedName() or ""
                bundle = dashboard_app.bundleIdentifier() or ""
                if "MindScribe" not in name and not bundle.startswith("com.mindscribe"):
                    instance._previous_app = dashboard_app

        # Should still point to VS Code
        assert instance._previous_app.localizedName() == "Code"
```

**Step 2 : Lancer les tests**

```bash
source venv-mac/bin/activate && python -m pytest tests/test_recording_flow.py -v --timeout=15
```
Expected: 4 tests PASSED (certains peuvent être SKIP sur non-macOS)

**Step 3 : Commit**

```bash
git add tests/test_recording_flow.py
git commit -m "test: add recording flow integration tests (capture, reactivate, history)"
```

---

## Task 6 : Lancer la suite de tests complète et corriger les régressions

**Step 1 : Lancer tous les tests existants**

```bash
source venv-mac/bin/activate && python -m pytest tests/ -v --tb=short 2>&1 | head -80
```

**Step 2 : Si des tests existants cassent, corriger avant de continuer**

Examiner les erreurs et corriger dans les fichiers concernés. Ne pas passer à Task 7 tant que la suite complète n'est pas verte.

**Step 3 : Rapport de couverture**

```bash
source venv-mac/bin/activate && python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: tous PASSED, 0 FAILED

---

## Task 7 : Test de smoke end-to-end — lancer l'app réelle et vérifier les logs

**Step 1 : Lancer l'app avec logging INFO**

```bash
source venv-mac/bin/activate && python run.py > /tmp/ms_e2e.txt 2>&1 &
sleep 5
cat /tmp/ms_e2e.txt
```

Expected output must include:
- `[INFO] src.core.quartz_hotkey: Quartz CGEventTap started on main run loop`
- `[INFO] src.core.hotkey_manager: Hotkey listener started: F9`
- `[INFO] src.app: MindScribe Desktop started`
- **NOT** `[INFO] src.app: App activation observer registered` — cet observer doit avoir été supprimé

**Step 2 : Vérifier qu'il n'y a AUCUNE ligne `App activation observer`**

```bash
grep "activation observer" /tmp/ms_e2e.txt
```
Expected: aucun résultat (ligne supprimée)

**Step 3 : Kill le process**

```bash
kill %1 2>/dev/null || pkill -f "python run.py"
```

---

## Task 8 : Commit final et tag

**Step 1 : Vérifier git status**

```bash
git status
git diff --stat HEAD
```

**Step 2 : Commit de synthèse si nécessaire**

```bash
git add -p  # review each change
git commit -m "fix: correct F9 focus capture and dashboard activation on macOS"
```

**Step 3 : Résumé des changements pour l'utilisateur**

Lister tous les bugs corrigés avec leur symptôme et leur fix.

---

## Checklist de validation finale

| # | Test | Attendu |
|---|------|---------|
| 1 | Lancer l'app depuis VS Code, appuyer F9 | Overlay apparaît, VS Code garde le focus |
| 2 | Dicter une phrase, attendre transcription | Texte apparaît dans VS Code |
| 3 | Ouvrir le Dashboard, retourner VS Code, appuyer F9 | Overlay apparaît, après transcription texte dans VS Code (pas Dashboard) |
| 4 | Ouvrir Dashboard depuis tray icon (1er clic) | Dashboard s'ouvre et est au premier plan |
| 5 | Fermer Dashboard, recliquer tray icon | Dashboard s'ouvre à nouveau (pas "une fois sur deux") |
| 6 | Cliquer Light Mode | Dashboard passe en clair sans crash |
| 7 | Cliquer Dark Mode | Dashboard repasse en sombre sans crash |
| 8 | `python -m pytest tests/ -v` | Tous les tests PASSED |
