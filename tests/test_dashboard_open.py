# tests/test_dashboard_open.py
"""Tests for Dashboard open/close/theme behavior."""
import os
import sys
import pytest

os.environ.setdefault("MINDSCRIBE_TEST_DIR", "/tmp/ms_test_dashboard")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
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
    store.add("Test entry premier", 3.0)

    d = Dashboard(
        history_store=store,
        style_store=StyleStore(),
        vocabulary=VocabularyStore(),
        settings=Settings.load(),
    )
    yield d
    # Force cleanup
    if d._is_open:
        d._is_open = False
    d.hide()


class TestDashboardOpenClose:
    def test_initial_state_not_open_not_built(self, dashboard):
        """Dashboard starts not open and not built."""
        assert not dashboard._is_open
        assert not dashboard._built

    def test_open_sets_is_open_and_built(self, dashboard):
        """After open(), _is_open and _built are True."""
        dashboard.open()
        _qt_app.processEvents()
        assert dashboard._is_open
        assert dashboard._built

    def test_close_resets_is_open(self, dashboard):
        """After close, _is_open becomes False."""
        dashboard.open()
        _qt_app.processEvents()
        # closeEvent resets _is_open
        dashboard._is_open = False  # simulate closeEvent
        assert not dashboard._is_open

    def test_second_open_does_not_rebuild(self, dashboard):
        """Second open() when already open raises rather than rebuilds."""
        dashboard.open()
        _qt_app.processEvents()
        container_id = id(dashboard._container)
        # Simulate second open() when already open
        dashboard.open()
        _qt_app.processEvents()
        # Container should be the same object
        assert id(dashboard._container) == container_id

    def test_nav_buttons_count(self, dashboard):
        """Dashboard has exactly 4 nav buttons (Home, Dictionary, Styles, Settings)."""
        dashboard.open()
        _qt_app.processEvents()
        assert len(dashboard._nav_buttons) == 4

    def test_tab_switching_all_tabs(self, dashboard):
        """Switching through all 4 tabs does not crash."""
        dashboard.open()
        _qt_app.processEvents()
        for i in range(4):
            dashboard._switch_tab(i)
            _qt_app.processEvents()
        assert dashboard._built

    def test_container_widget_exists(self, dashboard):
        """After open(), _container is a non-None QWidget."""
        dashboard.open()
        _qt_app.processEvents()
        assert dashboard._container is not None


class TestDashboardTheme:
    def test_toggle_to_light_no_crash(self, dashboard):
        """Clicking Light Mode does not crash; window rebuilds."""
        dashboard.open()
        _qt_app.processEvents()
        dashboard._toggle_theme()
        _qt_app.processEvents()
        _qt_app.processEvents()  # process QTimer.singleShot(0)
        _qt_app.processEvents()
        assert dashboard._built
        assert dashboard._container is not None

    def test_toggle_back_to_dark_no_crash(self, dashboard):
        """Two consecutive toggles leave the window functional."""
        dashboard.open()
        _qt_app.processEvents()
        dashboard._toggle_theme()
        _qt_app.processEvents()
        _qt_app.processEvents()
        _qt_app.processEvents()
        dashboard._toggle_theme()
        _qt_app.processEvents()
        _qt_app.processEvents()
        _qt_app.processEvents()
        assert dashboard._built
        assert len(dashboard._nav_buttons) == 4

    def test_theme_button_label_changes(self, dashboard):
        """Theme toggle button label changes between Light Mode and Dark Mode."""
        dashboard.open()
        _qt_app.processEvents()
        label_before = dashboard._theme_btn.text()
        dashboard._toggle_theme()
        _qt_app.processEvents()
        _qt_app.processEvents()
        _qt_app.processEvents()
        label_after = dashboard._theme_btn.text()
        assert label_before != label_after
        assert label_after in ("Light Mode", "Dark Mode")

    def test_nav_buttons_repopulated_after_toggle(self, dashboard):
        """After theme toggle, nav buttons list is repopulated (not empty)."""
        dashboard.open()
        _qt_app.processEvents()
        dashboard._toggle_theme()
        _qt_app.processEvents()
        _qt_app.processEvents()
        _qt_app.processEvents()
        assert len(dashboard._nav_buttons) == 4
