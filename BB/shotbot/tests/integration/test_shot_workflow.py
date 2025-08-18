"""Integration tests for shot discovery and management workflow.

Tests the complete workflow of discovering shots, caching, and refreshing.
Follows the UNIFIED_TESTING_GUIDE_DO_NOT_DELETE.md principles.
"""

import threading
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, Mock, patch

from cache_manager import CacheManager
from shot_model import RefreshResult, Shot, ShotModel
from utils import PathUtils


# Test Doubles following the unified testing guide
class _TestSignal:
    """Lightweight signal test double for non-Qt signals."""

    def __init__(self):
        self.emissions = []
        self.callbacks = []

    def emit(self, *args):
        self.emissions.append(args)
        for callback in self.callbacks:
            callback(*args)

    def connect(self, callback):
        self.callbacks.append(callback)

    @property
    def was_emitted(self):
        return len(self.emissions) > 0

    def reset(self):
        """Reset emission history for reuse."""
        self.emissions.clear()
        self.callbacks.clear()


class _TestProcessPoolManager:
    """Test double for ProcessPoolManager - replaces subprocess calls with predictable behavior."""

    def __init__(self):
        self.commands = []
        self.outputs = [
            """workspace /shows/show1/shots/seq1/seq1_0010
workspace /shows/show1/shots/seq1/seq1_0020
workspace /shows/show2/shots/seq2/seq2_0030""",
        ]
        self.command_completed = _TestSignal()
        self.command_failed = _TestSignal()
        self._should_fail = False
        self._failure_message = "Test failure"

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: int = 120,
    ) -> str:
        """Execute command with predictable test behavior."""
        self.commands.append(command)

        if self._should_fail:
            error_msg = self._failure_message
            self.command_failed.emit(command, error_msg)
            raise RuntimeError(error_msg)

        output = self.outputs[0] if self.outputs else ""
        self.command_completed.emit(command, output)
        return output

    def set_outputs(self, *outputs: str):
        """Set outputs for subsequent command executions."""
        self.outputs = list(outputs)

    def set_failure(self, should_fail: bool = True, message: str = "Test failure"):
        """Configure the manager to fail on next command."""
        self._should_fail = should_fail
        self._failure_message = message

    def invalidate_cache(self, pattern: Optional[str] = None):
        """Mock cache invalidation."""
        pass

    def get_metrics(self) -> Dict[str, Any]:
        """Return test metrics."""
        return {
            "subprocess_calls": len(self.commands),
            "cache_hits": 0,
            "cache_misses": len(self.commands),
            "average_response_ms": 50,
        }

    @classmethod
    def get_instance(cls):
        """Singleton pattern for compatibility."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance


class _TestLauncherManager:
    """Test double for LauncherManager with TestSignals."""

    def __init__(self):
        self.launchers = {}
        self.executions = []

        # Use TestSignal instead of MagicMock
        self.launcher_added = _TestSignal()
        self.launcher_updated = _TestSignal()
        self.launcher_deleted = _TestSignal()
        self.validation_error = _TestSignal()
        self.execution_started = _TestSignal()
        self.execution_finished = _TestSignal()

        # Mock config for testing
        self.config = Mock()
        self.config.config_dir = Path("/tmp")
        self.config.config_file = Path("/tmp/custom_launchers.json")

    def create_launcher(self, name: str, command: str, description: str = "") -> str:
        """Create launcher and return ID."""
        launcher_id = f"test_launcher_{len(self.launchers)}"
        self.launchers[launcher_id] = {
            "name": name,
            "command": command,
            "description": description,
        }
        self.launcher_added.emit(launcher_id, name)
        return launcher_id

    def execute_launcher(
        self,
        launcher_id: str,
        custom_vars: Optional[Dict[str, str]] = None,
    ):
        """Execute launcher with variables."""
        if launcher_id not in self.launchers:
            raise ValueError(f"Launcher {launcher_id} not found")

        launcher = self.launchers[launcher_id]
        command = launcher["command"]

        # Simple variable substitution for testing
        if custom_vars:
            for key, value in custom_vars.items():
                command = command.replace(f"${key}", value)

        execution_record = {
            "launcher_id": launcher_id,
            "command": command,
            "custom_vars": custom_vars or {},
        }
        self.executions.append(execution_record)

        self.execution_started.emit(launcher_id, command)
        # Simulate immediate completion for testing
        self.execution_finished.emit(launcher_id, True, "")

        return True


class TestShotDiscoveryWorkflow:
    """Test complete shot discovery workflow."""

    def test_shot_discovery_to_cache_workflow(
        self,
        temp_cache_dir,
        mock_process_pool_manager,
    ):
        """Test complete workflow from shot discovery to caching."""
        # Create components
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        shot_model = ShotModel(cache_manager=cache_manager, load_cache=False)

        # Perform shot discovery
        result = shot_model.refresh_shots()

        # Verify refresh succeeded
        assert isinstance(result, RefreshResult)
        assert result.success is True
        assert result.has_changes is True

        # Verify shots were discovered
        shots = shot_model.get_shots()
        assert len(shots) == 3
        assert all(isinstance(s, Shot) for s in shots)

        # Verify shots were cached
        cached_shots = cache_manager.get_cached_shots()
        assert cached_shots is not None
        assert len(cached_shots) == 3

    def test_cache_persistence_workflow(
        self,
        temp_cache_dir,
        mock_process_pool_manager,
    ):
        """Test cache persistence across model instances."""
        # First instance - discover and cache
        cache_manager1 = CacheManager(cache_dir=temp_cache_dir)
        model1 = ShotModel(cache_manager=cache_manager1, load_cache=False)

        result1 = model1.refresh_shots()
        assert result1.success
        shots1 = model1.get_shots()

        # Second instance - should load from cache
        cache_manager2 = CacheManager(cache_dir=temp_cache_dir)
        ShotModel(cache_manager=cache_manager2)

        # Load from cache without refresh
        cached_shots = cache_manager2.get_cached_shots()
        assert cached_shots is not None
        assert len(cached_shots) == len(shots1)

        # Shot data should match
        cached_shot_objects = [Shot.from_dict(shot_data) for shot_data in cached_shots]
        for i, shot in enumerate(cached_shot_objects):
            assert shot.show == shots1[i].show
            assert shot.sequence == shots1[i].sequence
            assert shot.shot == shots1[i].shot

    def test_refresh_with_no_changes(self, temp_cache_dir, mock_process_pool_manager):
        """Test refresh when shots haven't changed."""
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        model = ShotModel(cache_manager=cache_manager, load_cache=False)

        # First refresh
        result1 = model.refresh_shots()
        assert result1.has_changes is True

        # Second refresh - no changes (same output)
        result2 = model.refresh_shots()
        assert result2.success is True
        assert result2.has_changes is False

    def test_refresh_with_changes(self, temp_cache_dir):
        """Test refresh when shots have changed - using TestProcessPoolManager."""
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        model = ShotModel(cache_manager=cache_manager, load_cache=False)

        # Replace with test double instead of mocking internal methods
        test_pool = _TestProcessPoolManager()
        model._process_pool = test_pool

        # First refresh with initial data
        test_pool.set_outputs("workspace /shows/test/shots/seq1/seq1_0010")

        result1 = model.refresh_shots()
        assert result1.success is True
        assert len(model.get_shots()) == 1

        # Verify the shot details
        shot = model.get_shots()[0]
        assert shot.show == "test"
        assert shot.sequence == "seq1"
        # Note: shot parsing extracts the full shot name, so we get "seq1_0010" not "0010"
        assert shot.shot == "seq1_0010"

        # Second refresh with more data
        test_pool.set_outputs("""workspace /shows/test/shots/seq1/seq1_0010
workspace /shows/test/shots/seq1/seq1_0020""")

        result2 = model.refresh_shots()
        assert result2.success is True
        assert result2.has_changes is True
        assert len(model.get_shots()) == 2

        # Verify both shots are present
        shots = model.get_shots()
        shot_names = [s.shot for s in shots]
        assert "seq1_0010" in shot_names
        assert "seq1_0020" in shot_names

    def test_concurrent_refresh(self, temp_cache_dir, mock_process_pool_manager):
        """Test concurrent refresh operations."""
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        model = ShotModel(cache_manager=cache_manager, load_cache=False)

        results = []

        def refresh_shots():
            result = model.refresh_shots()
            results.append(result)

        # Run concurrent refreshes
        threads = []
        for _ in range(5):
            t = threading.Thread(target=refresh_shots)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All should succeed
        assert len(results) == 5
        assert all(r.success for r in results)

        # Should have consistent shot count
        shots = model.get_shots()
        assert len(shots) == 3  # From mock_process_pool_manager


class TestThumbnailWorkflow:
    """Test thumbnail discovery and caching workflow."""

    def test_thumbnail_discovery_workflow(self, temp_cache_dir, mock_filesystem):
        """Test discovering and caching thumbnails."""
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        shot = Shot(
            "testshow",
            "101_ABC",
            "0010",
            str(mock_filesystem / "testshow/shots/101_ABC/101_ABC_0010"),
        )

        # Build thumbnail path
        thumb_path = PathUtils.build_thumbnail_path(
            str(mock_filesystem),
            shot.show,
            shot.sequence,
            shot.shot,
        )

        # Verify path exists in mock filesystem (the path is already complete)
        assert thumb_path.exists()

        # Find thumbnail files
        from utils import FileUtils

        thumbnails = list(
            FileUtils.find_files_by_extension(thumb_path, [".jpg", ".jpeg"]),
        )
        assert len(thumbnails) == 2  # frame.1001.jpg and frame.1002.jpg

        # Cache thumbnail
        with patch("cache_manager.QImage") as mock_qimage, patch(
            "cache_manager.QApplication",
        ) as mock_qapp, patch("cache_manager.QThread") as mock_qthread, patch(
            "pathlib.Path.stat",
        ) as mock_stat, patch("pathlib.Path.replace") as mock_replace:
            # Mock file stat for size calculation
            mock_stat_result = MagicMock()
            mock_stat_result.st_size = 1024 * 50  # 50KB thumbnail
            mock_stat.return_value = mock_stat_result

            # Mock file replacement to succeed
            mock_replace.return_value = None

            # Mock QImage
            mock_image = MagicMock()
            mock_image.isNull.return_value = False
            mock_image.width.return_value = 1920
            mock_image.height.return_value = 1080
            mock_scaled_image = MagicMock()
            mock_scaled_image.isNull.return_value = False
            mock_scaled_image.save.return_value = True
            mock_image.scaled.return_value = mock_scaled_image
            mock_qimage.return_value = mock_image

            # Mock QApplication to simulate main thread
            mock_app_instance = MagicMock()
            mock_main_thread = MagicMock()
            mock_app_instance.thread.return_value = mock_main_thread
            mock_qapp.instance.return_value = mock_app_instance

            # Mock QThread.currentThread to return main thread
            mock_qthread.currentThread.return_value = mock_main_thread

            if thumbnails:
                cached_path = cache_manager.cache_thumbnail(
                    thumbnails[0],
                    shot.show,
                    shot.sequence,
                    shot.shot,
                )
                assert cached_path is not None
                assert cached_path.name == "0010_thumb.jpg"

    def test_thumbnail_cache_retrieval(self, temp_cache_dir):
        """Test retrieving cached thumbnails."""
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        shot = Shot("test", "seq1", "0010", "/test/path")

        # Create cached thumbnail with correct structure
        thumb_dir = temp_cache_dir / "thumbnails" / "test" / "seq1"
        thumb_dir.mkdir(parents=True)
        cached_file = thumb_dir / "0010_thumb.jpg"
        cached_file.touch()

        # Retrieve cached thumbnail
        retrieved = cache_manager.get_cached_thumbnail(
            shot.show,
            shot.sequence,
            shot.shot,
        )
        assert retrieved == cached_file
        assert retrieved.exists()

    def test_thumbnail_cache_miss(self, cache_manager):
        """Test handling of missing thumbnails."""
        shot = Shot("test", "seq1", "0010", "/test/path")

        # No cached thumbnail
        result = cache_manager.get_cached_thumbnail(shot.show, shot.sequence, shot.shot)
        assert result is None


class TestLauncherWorkflow:
    """Test launcher execution workflow with shots."""

    def test_launcher_with_shot_context(self, tmp_path):
        """Test executing launcher with shot context - using TestLauncherManager."""
        # Use test double instead of real LauncherManager with mocks
        manager = _TestLauncherManager()
        manager.config.config_dir = tmp_path
        manager.config.config_file = tmp_path / "custom_launchers.json"

        shot = Shot(
            "testshow",
            "101_SEQ",
            "0010",
            "/shows/testshow/shots/101_SEQ/101_SEQ_0010",
        )

        # Create launcher with placeholders and get the ID
        launcher_id = manager.create_launcher(
            name="Nuke",
            command="cd $workspace_path && nuke --shot $shot_name",
            description="Nuke launcher for VFX work",
        )
        assert launcher_id is not None

        # Verify launcher was added (test the signal behavior)
        assert manager.launcher_added.was_emitted
        assert manager.launcher_added.emissions[0] == (launcher_id, "Nuke")

        # Execute with shot context using the launcher ID
        result = manager.execute_launcher(
            launcher_id,
            custom_vars={
                "workspace_path": shot.workspace_path,
                "shot_name": f"{shot.sequence}_{shot.shot}",
            },
        )

        # Test behavior, not implementation
        assert result is True
        assert len(manager.executions) == 1

        execution = manager.executions[0]
        assert execution["launcher_id"] == launcher_id
        assert "101_SEQ_0010" in execution["command"]
        assert shot.workspace_path in execution["command"]

        # Verify execution signals were emitted
        assert manager.execution_started.was_emitted
        assert manager.execution_finished.was_emitted

    def test_multiple_launcher_execution(self, tmp_path):
        """Test executing multiple launchers concurrently - using TestLauncherManager."""
        manager = _TestLauncherManager()
        manager.config.config_dir = tmp_path
        manager.config.config_file = tmp_path / "custom_launchers.json"

        # Create multiple launchers and store their IDs
        launcher_configs = [
            {"name": "Maya", "command": "maya $shot", "description": "Maya launcher"},
            {"name": "Nuke", "command": "nuke $shot", "description": "Nuke launcher"},
            {"name": "3DE", "command": "3de $shot", "description": "3DE launcher"},
        ]

        launcher_ids = []
        for config in launcher_configs:
            launcher_id = manager.create_launcher(**config)
            assert launcher_id is not None
            launcher_ids.append(launcher_id)

        # Verify all launchers were created
        assert len(manager.launchers) == 3
        assert len(manager.launcher_added.emissions) == 3  # 3 emissions

        # Execute all launchers using their IDs
        for launcher_id in launcher_ids:
            result = manager.execute_launcher(
                launcher_id,
                custom_vars={"shot": "TEST_0010"},
            )
            assert result is True

        # Test behavior: all should be executed with correct variable substitution
        assert len(manager.executions) == 3

        # Check that commands were properly substituted
        commands = [exec_record["command"] for exec_record in manager.executions]
        assert "maya TEST_0010" in commands
        assert "nuke TEST_0010" in commands
        assert "3de TEST_0010" in commands

        # Verify execution signals were emitted for each
        assert len(manager.execution_started.emissions) == 3
        assert len(manager.execution_finished.emissions) == 3


class TestSearchWorkflow:
    """Test shot search and filtering workflow."""

    def test_search_shots_by_show(self, shot_model_with_shots):
        """Test searching shots by show name."""
        model = shot_model_with_shots
        all_shots = model.get_shots()

        # Filter by show
        show1_shots = [s for s in all_shots if s.show == "show1"]
        assert len(show1_shots) == 2

        show2_shots = [s for s in all_shots if s.show == "show2"]
        assert len(show2_shots) == 1

    def test_search_shots_by_sequence(self, shot_model_with_shots):
        """Test searching shots by sequence."""
        model = shot_model_with_shots
        all_shots = model.get_shots()

        # Filter by sequence
        seq1_shots = [s for s in all_shots if s.sequence == "seq1"]
        assert len(seq1_shots) == 2

        seq2_shots = [s for s in all_shots if s.sequence == "seq2"]
        assert len(seq2_shots) == 1

    def test_find_shot_by_name(self, shot_model_with_shots):
        """Test finding specific shot by name."""
        model = shot_model_with_shots

        # Find by full name
        shot = model.get_shot_by_name("seq1_0010")
        assert shot is not None
        assert shot.shot == "0010"
        assert shot.sequence == "seq1"

        # Non-existent shot
        shot = model.get_shot_by_name("nonexistent")
        assert shot is None


class TestErrorHandlingWorkflow:
    """Test error handling in workflows."""

    def test_workspace_command_failure(self, cache_manager):
        """Test handling workspace command failure - using TestProcessPoolManager."""
        model = ShotModel(cache_manager=cache_manager, load_cache=False)

        # Replace with test double configured to fail
        test_pool = _TestProcessPoolManager()
        test_pool.set_failure(True, "ws: command not found")
        model._process_pool = test_pool

        result = model.refresh_shots()

        # Test behavior: ShotModel should handle the failure gracefully
        assert result.success is False
        assert result.has_changes is False
        assert len(model.get_shots()) == 0

        # Verify the failure signal was emitted
        assert test_pool.command_failed.was_emitted
        assert "ws: command not found" in test_pool.command_failed.emissions[0][1]

    def test_cache_corruption_recovery(self, temp_cache_dir):
        """Test recovery from corrupted cache - using TestProcessPoolManager."""
        # Create corrupted cache with correct filename
        cache_file = temp_cache_dir / "shots.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("{ invalid json }")

        # Should handle gracefully
        cache_manager = CacheManager(cache_dir=temp_cache_dir)
        model = ShotModel(cache_manager=cache_manager)

        # Should start fresh after corrupted cache
        assert model.get_shots() == []

        # Should be able to refresh normally after cache corruption
        test_pool = _TestProcessPoolManager()
        test_pool.set_outputs("workspace /shows/test/shots/seq1/seq1_0010")
        model._process_pool = test_pool

        result = model.refresh_shots()

        # Test behavior: should recover and work normally
        assert result.success is True
        assert (
            result.has_changes is True
        )  # Should have changes since we started with empty
        assert len(model.get_shots()) == 1

        # Verify the shot was parsed correctly
        shot = model.get_shots()[0]
        assert shot.show == "test"
        assert shot.sequence == "seq1"
        # Note: shot parsing extracts the full shot name
        assert shot.shot == "seq1_0010"

        # Verify new cache was created successfully
        cached_shots = cache_manager.get_cached_shots()
        assert cached_shots is not None
        assert len(cached_shots) == 1

    def test_concurrent_error_handling(self, cache_manager):
        """Test error handling with concurrent operations - using shared TestProcessPoolManager."""
        model = ShotModel(cache_manager=cache_manager, load_cache=False)

        results = []
        errors = []

        # Create a shared test pool that will be used by all threads
        test_pool = _TestProcessPoolManager()
        test_pool.set_outputs(
            "workspace /shows/test/shots/seq1/seq1_0010",
            "workspace /shows/test/shots/seq1/seq1_0010",
            "workspace /shows/test/shots/seq1/seq1_0010",
        )

        # For the second call, we'll simulate a failure by changing the pool state
        call_count = 0
        original_execute = test_pool.execute_workspace_command

        def failing_execute(command, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call fails
                test_pool.set_failure(True, "Simulated error")
                raise RuntimeError("Simulated error")
            else:
                test_pool.set_failure(False)  # Reset failure state
                return original_execute(command, **kwargs)

        test_pool.execute_workspace_command = failing_execute
        model._process_pool = test_pool

        def refresh_with_error_handling():
            try:
                result = model.refresh_shots()
                results.append(result)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for _ in range(3):
            t = threading.Thread(target=refresh_with_error_handling)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Test behavior: should handle mixed results gracefully
        assert len(results) == 3
        assert len(errors) == 0  # Errors handled internally by ShotModel

        # Check that some succeeded and some failed
        success_count = sum(1 for r in results if r.success)
        failure_count = sum(1 for r in results if not r.success)

        assert success_count >= 2  # At least 2 should succeed
        assert failure_count >= 1  # At least 1 should fail
