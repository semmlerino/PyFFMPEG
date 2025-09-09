#!/usr/bin/env python3
"""Enhanced mock ProcessPool that properly simulates workspace commands.

This module provides a more realistic mock that returns all shots at once,
just like the real 'ws -sg' command would.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import Config

logger = logging.getLogger(__name__)


class MockWorkspacePool:
    """Mock ProcessPool that simulates real workspace commands."""

    def __init__(self) -> None:
        """Initialize mock workspace pool."""
        self.shots: list[str] = []
        self._cache: dict[str, str] = {}
        self.commands_executed: list[str] = []

    def set_shots_from_filesystem(self, mock_root: Path | None = None) -> None:
        """Scan the mock filesystem and set up all available shots.

        Args:
            mock_root: Root of mock VFX filesystem (default: /tmp/mock_vfx)
        """
        if mock_root is None:
            mock_root = Path("/tmp/mock_vfx")

        self.shots = []
        shows_dir = mock_root / "shows"

        if not shows_dir.exists():
            logger.warning(f"Shows directory not found: {shows_dir}")
            return

        # Scan each show
        for show_dir in shows_dir.iterdir():
            if not show_dir.is_dir():
                continue

            show_name = show_dir.name
            shots_dir = show_dir / "shots"

            if not shots_dir.exists():
                continue

            # Scan each sequence
            for seq_dir in shots_dir.iterdir():
                if not seq_dir.is_dir():
                    continue

                seq_name = seq_dir.name

                # Scan each shot
                for shot_dir in seq_dir.iterdir():
                    if not shot_dir.is_dir():
                        continue

                    shot_name = shot_dir.name

                    # Skip non-shot directories (config, tools, etc.)
                    # Shot directories follow pattern: SEQUENCE_SHOTNUMBER
                    # e.g., "BRX_118_0010", "012_DC_1000"
                    if "_" not in shot_name or shot_name in ("config", "tools"):
                        continue

                    # Verify it looks like a shot (has sequence prefix)
                    if not shot_name.startswith(f"{seq_name}_"):
                        continue

                    # Build workspace path
                    workspace_path = (
                        f"{Config.SHOWS_ROOT}/{show_name}/shots/{seq_name}/{shot_name}"
                    )
                    self.shots.append(f"workspace {workspace_path}")

        logger.info(f"Loaded {len(self.shots)} shots from mock filesystem")

    def set_shots_from_demo(self, demo_shots: list[dict[str, str]]) -> None:
        """Set shots from demo data.

        Args:
            demo_shots: List of shot dictionaries with show/seq/shot keys
        """
        self.shots = []
        for shot in demo_shots:
            show = shot.get("show", "demo")
            seq = shot.get("seq", "seq01")
            shot_num = shot.get("shot", "0010")
            workspace_path = f"{Config.SHOWS_ROOT}/{show}/shots/{seq}/{seq}_{shot_num}"
            self.shots.append(f"workspace {workspace_path}")

        logger.info(f"Loaded {len(self.shots)} demo shots")

    def execute_workspace_command(
        self,
        command: str,
        cache_ttl: int = 30,
        timeout: int | None = None,
    ) -> str:
        """Execute workspace command.

        For 'ws -sg', returns all shots joined with newlines,
        just like the real command would.

        Args:
            command: Command to execute
            cache_ttl: Cache time-to-live
            timeout: Timeout in seconds

        Returns:
            Command output
        """
        self.commands_executed.append(command)

        # Check cache first
        if command in self._cache:
            return self._cache[command]

        result = ""

        if command == "ws -sg":
            # Return all shots joined with newlines
            result = "\n".join(self.shots)
        elif command.startswith("echo"):
            # For warming commands
            result = command.replace("echo ", "")
        else:
            # Default response
            result = f"Mock output for: {command}"

        # Cache result
        if cache_ttl > 0:
            self._cache[command] = result

        return result

    def batch_execute(
        self,
        commands: list[str],
        cache_ttl: int = 30,
        session_type: str = "workspace",
    ) -> dict[str, str | None]:
        """Execute multiple commands.

        Args:
            commands: Commands to execute
            cache_ttl: Cache TTL
            session_type: Session type

        Returns:
            Command results
        """
        results: dict[str, str | None] = {}
        for cmd in commands:
            try:
                results[cmd] = self.execute_workspace_command(cmd, cache_ttl)
            except Exception as e:
                logger.error(f"Failed to execute {cmd}: {e}")
                results[cmd] = None
        return results

    def invalidate_cache(self, pattern: str | None = None) -> None:
        """Invalidate cache entries.

        Args:
            pattern: Pattern to match (clears all if None)
        """
        if pattern is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k in self._cache if pattern in k]
            for key in keys_to_remove:
                del self._cache[key]

    def shutdown(self) -> None:
        """Shutdown the pool (no-op for mock)."""
        pass

    def get_metrics(self) -> dict[str, int]:
        """Get mock metrics.

        Returns:
            Metrics dictionary
        """
        return {
            "total_shots": len(self.shots),
            "commands_executed": len(self.commands_executed),
            "cache_size": len(self._cache),
        }


def create_mock_pool_from_filesystem() -> MockWorkspacePool:
    """Create a mock pool that simulates user-assigned shots only.

    In a real VFX environment, 'ws -sg' only returns shots assigned to the
    current user, not all shots in the facility. We simulate this by using
    the curated demo shots that represent a realistic user workload.

    Returns:
        MockWorkspacePool configured with user's assigned shots only
    """
    import json

    pool = MockWorkspacePool()

    # Use demo shots first (realistic user assignment of ~12 shots)
    demo_shots_path = Path(__file__).parent / "demo_shots.json"
    if demo_shots_path.exists():
        logger.info("Loading demo shots for user-assigned simulation")
        try:
            with open(demo_shots_path, encoding="utf-8") as f:
                demo_data = json.load(f)

            # Validate JSON structure
            if not isinstance(demo_data, dict):
                raise ValueError(f"Expected dict, got {type(demo_data).__name__}")

            if "shots" not in demo_data:
                raise ValueError("Missing 'shots' key in demo data")

            if not isinstance(demo_data["shots"], list):
                raise ValueError(
                    f"'shots' must be a list, got {type(demo_data['shots']).__name__}"
                )

            # Validate each shot has required fields
            for i, shot in enumerate(demo_data["shots"]):
                if not isinstance(shot, dict):
                    raise ValueError(f"Shot {i} is not a dict")
                required_fields = ["show", "seq", "shot"]
                missing = [f for f in required_fields if f not in shot]
                if missing:
                    raise ValueError(f"Shot {i} missing fields: {missing}")

            # Assign only a subset of shots to gabriel-h to simulate realistic user workload
            # while still allowing "Other 3DE Scenes" to find many unassigned 3DE files
            assigned_shots = demo_data["shots"][:4]  # Take first 4 shots for gabriel-h
            logger.info(
                f"Assigning {len(assigned_shots)} of {len(demo_data['shots'])} demo shots to gabriel-h"
            )

            pool.set_shots_from_demo(assigned_shots)
            if pool.shots:
                logger.info(f"✅ Gabriel-h assigned to {len(pool.shots)} shots:")
                for shot_path in pool.shots:
                    logger.info(f"   📋 {shot_path}")
                logger.info(
                    f"🎯 This leaves {len(demo_data['shots']) - len(assigned_shots)} shots unassigned for 'Other 3DE Scenes'"
                )
                return pool
            else:
                logger.warning("Demo shots loaded but pool is empty")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in demo_shots.json: {e}")
        except OSError as e:
            logger.error(f"Failed to read demo_shots.json: {e}")
        except ValueError as e:
            logger.error(f"Invalid demo shots structure: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading demo shots: {e}")

    # Do NOT fall back to filesystem - this was causing ALL shots to be
    # considered assigned to gabriel-h, which filtered out all "Other 3DE Scenes"
    logger.error("Demo shots are required for realistic mock environment")
    logger.error("Without demo_shots.json, mock will have no assigned shots")
    logger.error(
        "This ensures 'Other 3DE Scenes' can find 3DE files from non-assigned shots"
    )

    return pool


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create pool from filesystem
    pool = create_mock_pool_from_filesystem()

    # Test ws -sg command
    output = pool.execute_workspace_command("ws -sg")
    shots = output.split("\n")

    print(f"Found {len(shots)} shots:")
    for i, shot in enumerate(shots[:10], 1):  # Show first 10
        print(f"  {i}. {shot}")

    if len(shots) > 10:
        print(f"  ... and {len(shots) - 10} more")

    # Show metrics
    metrics = pool.get_metrics()
    print(f"\nMetrics: {metrics}")
