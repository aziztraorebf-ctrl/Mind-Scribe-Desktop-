"""Tests for OnboardingWizard."""
import sys

import pytest


@pytest.fixture(scope="module")
def qt_app():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    return app


class TestOnboardingWizardStructure:
    def test_wizard_has_three_pages(self, qt_app):
        from src.ui.onboarding_wizard import OnboardingWizard
        wizard = OnboardingWizard()
        assert wizard._stack.count() == 3

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
