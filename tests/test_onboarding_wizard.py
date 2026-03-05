"""Tests for OnboardingWizard."""
import sys

import pytest


@pytest.fixture(scope="module")
def qt_app():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    return app


class TestOnboardingWizardStructure:
    def test_wizard_has_four_pages(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        assert wizard._stack.count() == 4

    def test_wizard_starts_on_page_zero(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        assert wizard._stack.currentIndex() == 0

    def test_next_advances_page(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        wizard._go_next()
        assert wizard._stack.currentIndex() == 1

    def test_back_returns_to_previous_page(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        wizard._go_next()
        wizard._go_back()
        assert wizard._stack.currentIndex() == 0

    def test_run_returns_false_on_close(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        wizard.reject()
        assert wizard._completed is False


class TestApiKeyPage:
    def test_groq_key_field_exists(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        assert hasattr(wizard, "_groq_key_input")

    def test_openai_key_field_exists(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        assert hasattr(wizard, "_openai_key_input")

    def test_next_disabled_when_no_key(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        wizard._stack.setCurrentIndex(2)  # API keys page is now index 2
        wizard._groq_key_input.setText("")
        wizard._openai_key_input.setText("")
        wizard._update_nav_page2()
        assert not wizard._btn_next.isEnabled()

    def test_next_enabled_when_groq_key_entered(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        wizard._go_next()
        wizard._groq_key_input.setText("gsk_abc123")
        wizard._update_nav_page2()
        assert wizard._btn_next.isEnabled()

    def test_write_env_creates_file(self, qt_app, tmp_path):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        env_path = tmp_path / ".env"
        wizard._write_env("gsk_test_key", "", env_path)
        content = env_path.read_text()
        assert "GROQ_API_KEY=gsk_test_key" in content

    def test_write_env_includes_openai_when_provided(self, qt_app, tmp_path):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        env_path = tmp_path / ".env"
        wizard._write_env("gsk_test", "sk-openai", env_path)
        content = env_path.read_text()
        assert "OPENAI_API_KEY=sk-openai" in content

    def test_write_env_omits_openai_when_empty(self, qt_app, tmp_path):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        env_path = tmp_path / ".env"
        wizard._write_env("gsk_test", "", env_path)
        content = env_path.read_text()
        assert "OPENAI_API_KEY" not in content


class TestDonePage:
    def test_finish_sets_completed_true(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        from unittest.mock import patch
        wizard = OnboardingWizard()
        wizard._stack.setCurrentIndex(3)  # Done page is now index 3
        wizard._update_nav()
        with patch.object(wizard, "accept"):
            wizard._go_next()
        assert wizard._completed is True

    def test_run_returns_true_after_finish(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        from unittest.mock import patch
        wizard = OnboardingWizard()
        with patch.object(wizard, "exec", return_value=None):
            wizard._completed = True
            result = wizard.run()
        assert result is True
