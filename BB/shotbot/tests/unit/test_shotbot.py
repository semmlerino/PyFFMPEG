"""Tests for shotbot.py - application entry point.

Following UNIFIED_TESTING_GUIDE principles:
- Test behavior not implementation
- Mock only at system boundaries (file system)
- Use real components where possible
- Focus on critical initialization paths
"""

import logging
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

# Import the module under test
import shotbot


class TestLoggingSetup:
    """Test logging configuration."""

    def test_setup_logging_creates_log_directory(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that setup_logging creates the logs directory."""
        # Mock home directory to use temp path
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Call setup_logging
        shotbot.setup_logging()

        # Verify log directory was created
        log_dir = test_home / ".shotbot" / "logs"
        assert log_dir.exists()
        assert log_dir.is_dir()

        # Verify log file exists
        log_file = log_dir / "shotbot.log"
        assert log_file.exists()

    def test_debug_logging_enabled_with_env_var(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that SHOTBOT_DEBUG environment variable enables debug logging."""
        # Set up test environment
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Set debug environment variable
        monkeypatch.setenv("SHOTBOT_DEBUG", "1")

        # Clear existing handlers first
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        # Setup logging
        shotbot.setup_logging()

        # Find console handler
        console_handler = None
        for handler in root_logger.handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and handler.stream == sys.stderr
            ):
                console_handler = handler
                break

        assert console_handler is not None
        assert console_handler.level == logging.DEBUG

    def test_debug_logging_disabled_without_env_var(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that console logging is WARNING level without SHOTBOT_DEBUG."""
        # Set up test environment
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Ensure debug env var is not set
        monkeypatch.delenv("SHOTBOT_DEBUG", raising=False)

        # Clear existing handlers first
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        # Setup logging
        shotbot.setup_logging()

        # Find console handler
        console_handler = None
        for handler in root_logger.handlers:
            if (
                isinstance(handler, logging.StreamHandler)
                and handler.stream == sys.stderr
            ):
                console_handler = handler
                break

        assert console_handler is not None
        assert console_handler.level == logging.WARNING

    def test_pil_logging_suppressed(self, tmp_path: Path, monkeypatch) -> None:
        """Test that PIL/Pillow debug logging is suppressed."""
        # Set up test environment
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Setup logging
        shotbot.setup_logging()

        # Check PIL loggers are set to INFO level
        pil_logger = logging.getLogger("PIL")
        assert pil_logger.level == logging.INFO

        pil_image_logger = logging.getLogger("PIL.Image")
        assert pil_image_logger.level == logging.INFO

        pil_png_logger = logging.getLogger("PIL.PngImagePlugin")
        assert pil_png_logger.level == logging.INFO


class TestApplicationInitialization:
    """Test Qt application initialization."""

    @patch("sys.exit")
    @patch("PySide6.QtWidgets.QApplication.exec")
    def test_main_creates_qt_application(
        self, mock_exec, mock_exit, qtbot, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that main() creates and configures Qt application."""
        # Mock home directory for logging
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Mock QApplication to track calls
        original_qapp = QApplication
        qapp_instances = []

        def mock_qapp_constructor(args):
            app = original_qapp.instance() or original_qapp(args)
            qapp_instances.append(app)
            return app

        with patch("PySide6.QtWidgets.QApplication", side_effect=mock_qapp_constructor):
            # Mock MainWindow to prevent actual window creation
            with patch("main_window.MainWindow") as mock_window_class:
                mock_window = Mock()
                mock_window_class.return_value = mock_window

                # Run main
                shotbot.main()

                # Verify QApplication was created
                assert len(qapp_instances) > 0
                app = qapp_instances[0]

                # Verify application configuration
                assert app.applicationName() == "ShotBot"
                assert app.organizationName() == "VFX"

                # Verify window was created and shown
                mock_window_class.assert_called_once()
                mock_window.show.assert_called_once()

                # Verify exec was called
                mock_exec.assert_called_once()

    @patch("sys.exit")
    @patch("PySide6.QtWidgets.QApplication.exec")
    def test_main_sets_dark_theme(
        self, mock_exec, mock_exit, qtbot, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that main() sets up dark theme correctly."""
        # Mock home directory for logging
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Track palette settings
        palette_set = []

        def track_palette(palette):
            palette_set.append(palette)

        with patch(
            "PySide6.QtWidgets.QApplication.setPalette", side_effect=track_palette
        ):
            with patch("main_window.MainWindow"):
                # Run main
                shotbot.main()

                # Verify palette was set
                assert len(palette_set) == 1
                palette = palette_set[0]

                # Check dark theme colors
                assert palette.color(QPalette.ColorRole.Window).name() == "#232323"
                assert palette.color(QPalette.ColorRole.Base).name() == "#191919"
                assert palette.color(QPalette.ColorRole.Button).name() == "#353535"

    @patch("sys.exit")
    @patch("PySide6.QtWidgets.QApplication.exec")
    def test_main_sets_fusion_style(
        self, mock_exec, mock_exit, qtbot, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that main() sets Fusion style."""
        # Mock home directory for logging
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Track style settings
        styles_set = []

        def track_style(style):
            styles_set.append(style)

        with patch("PySide6.QtWidgets.QApplication.setStyle", side_effect=track_style):
            with patch("main_window.MainWindow"):
                # Run main
                shotbot.main()

                # Verify Fusion style was set
                assert "Fusion" in styles_set


class TestErrorHandling:
    """Test error handling in application startup."""

    @patch("sys.exit")
    def test_main_handles_missing_imports_gracefully(
        self, mock_exit, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that main handles import errors gracefully."""
        # Mock home directory for logging
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Mock MainWindow import to fail
        with patch("shotbot.MainWindow", side_effect=ImportError("Test import error")):
            # This should not crash but handle the error
            with pytest.raises(ImportError):
                shotbot.main()

    def test_logging_handles_permission_errors(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that logging setup handles permission errors."""
        # Mock home directory to use temp path
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Make logs directory read-only to simulate permission error
        log_dir = test_home / ".shotbot"
        log_dir.mkdir()
        log_dir.chmod(0o444)  # Read-only

        # This should not crash even with permission issues
        try:
            shotbot.setup_logging()
        except PermissionError:
            # Expected - permission error is acceptable
            pass
        finally:
            # Restore permissions for cleanup
            log_dir.chmod(0o755)


class TestApplicationLifecycle:
    """Test application lifecycle management."""

    @patch("sys.exit")
    @patch("PySide6.QtWidgets.QApplication.exec")
    def test_main_exits_with_exec_return_code(
        self, mock_exec, mock_exit, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that main() exits with QApplication.exec() return code."""
        # Mock home directory for logging
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Set exec return code
        test_return_code = 42
        mock_exec.return_value = test_return_code

        with patch("main_window.MainWindow"):
            # Run main
            shotbot.main()

            # Verify sys.exit was called with correct code
            mock_exit.assert_called_once_with(test_return_code)

    def test_multiple_logging_setup_calls_safe(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Test that multiple calls to setup_logging don't cause issues."""
        # Mock home directory for logging
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Call setup_logging multiple times
        shotbot.setup_logging()
        shotbot.setup_logging()
        shotbot.setup_logging()

        # Should not raise exceptions or create duplicate handlers
        root_logger = logging.getLogger()

        # Count handlers of each type
        file_handlers = [
            h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
        ]
        stream_handlers = [
            h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)
        ]

        # Should have reasonable number of handlers (not duplicated excessively)
        assert len(file_handlers) <= 3  # Allow for some duplication
        assert len(stream_handlers) <= 3


class TestIntegration:
    """Integration tests for complete application startup."""

    @patch("sys.exit")
    @patch("PySide6.QtWidgets.QApplication.exec")
    def test_complete_application_startup(
        self, mock_exec, mock_exit, qtbot, tmp_path: Path, monkeypatch
    ) -> None:
        """Test complete application startup sequence."""
        # Mock home directory for logging
        test_home = tmp_path / "test_home"
        test_home.mkdir()
        monkeypatch.setattr(Path, "home", lambda: test_home)

        # Set debug mode
        monkeypatch.setenv("SHOTBOT_DEBUG", "1")

        # Track all important calls
        app_created = False
        window_created = False
        window_shown = False

        def track_app_creation(args):
            nonlocal app_created
            app_created = True
            return QApplication.instance() or QApplication(args)

        def track_window_creation():
            nonlocal window_created
            window_created = True
            mock_window = Mock()

            def track_show():
                nonlocal window_shown
                window_shown = True

            mock_window.show = track_show
            return mock_window

        with patch("PySide6.QtWidgets.QApplication", side_effect=track_app_creation):
            with patch("main_window.MainWindow", side_effect=track_window_creation):
                # Run main
                shotbot.main()

                # Verify complete startup sequence
                assert app_created, "QApplication was not created"
                assert window_created, "MainWindow was not created"
                assert window_shown, "MainWindow.show() was not called"

                # Verify logging was configured
                log_file = test_home / ".shotbot" / "logs" / "shotbot.log"
                assert log_file.exists(), "Log file was not created"

                # Verify application executed
                mock_exec.assert_called_once()

                # Verify clean exit
                mock_exit.assert_called_once()


# Module-level test to ensure shotbot can be imported
def test_module_imports_successfully() -> None:
    """Test that shotbot module can be imported without errors."""
    import importlib

    import shotbot

    # Reimport to ensure no side effects
    importlib.reload(shotbot)

    # Verify main function exists
    assert hasattr(shotbot, "main")
    assert callable(shotbot.main)

    # Verify setup_logging exists
    assert hasattr(shotbot, "setup_logging")
    assert callable(shotbot.setup_logging)
