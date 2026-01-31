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
        # At least one dir should exist
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

    def test_returns_empty_keys_when_not_set(self, tmp_path):
        # Use tmp_path (no .env file) so load_dotenv is never triggered
        with patch("src.config.dotenv_loader._get_search_dirs", return_value=[tmp_path]), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROQ_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            result = load_env()
            assert result["groq_api_key"] == ""
            assert result["openai_api_key"] == ""

    def test_reads_groq_key_from_env(self, tmp_path):
        with patch("src.config.dotenv_loader._get_search_dirs", return_value=[tmp_path]), \
             patch.dict(os.environ, {"GROQ_API_KEY": "test-groq-key"}):
            result = load_env()
            assert result["groq_api_key"] == "test-groq-key"

    def test_reads_openai_key_from_env(self, tmp_path):
        with patch("src.config.dotenv_loader._get_search_dirs", return_value=[tmp_path]), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai-key"}):
            result = load_env()
            assert result["openai_api_key"] == "test-openai-key"
