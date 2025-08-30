"""Finder for previous/approved shots that user has worked on."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Generator

from config import ThreadingConfig
from shot_model import Shot

logger = logging.getLogger(__name__)


class PreviousShotsFinder:
    """Finds shots that user has worked on but are no longer active.

    This class scans the filesystem for shots containing user work directories
    and filters out currently active shots to show only approved/completed ones.
    """

    def __init__(self, username: str | None = None) -> None:
        """Initialize the previous shots finder.

        Args:
            username: Username to search for. If None, uses current user.
        """
        # Get raw username
        raw_username = username or os.environ.get("USER") or os.getlogin()

        # SECURITY FIX: Sanitize username to prevent path traversal attacks
        # Remove any path traversal characters (., /, \)
        self.username = re.sub(r"[./\\]", "", raw_username)

        # Validate that username is not empty after sanitization
        if not self.username:
            raise ValueError(f"Invalid username after sanitization: '{raw_username}'")

        # Additional validation: username should only contain alphanumeric, dash, and underscore
        if not re.match(r"^[a-zA-Z0-9_-]+$", self.username):
            raise ValueError(f"Username contains invalid characters: '{self.username}'")

        self.user_path_pattern = f"/user/{self.username}"
        self._shot_pattern = re.compile(r"/shows/([^/]+)/shots/([^/]+)/([^/]+)/")
        logger.info(f"PreviousShotsFinder initialized for user: {self.username}")

    def find_user_shots(self, shows_root: Path = Path("/shows")) -> list[Shot]:
        """Find all shots that contain user work directories.

        Args:
            shows_root: Root directory to search for shots.

        Returns:
            List of Shot objects where user has work directories.
        """
        shots = []

        if not shows_root.exists():
            logger.warning(f"Shows root does not exist: {shows_root}")
            return shots

        try:
            # Use find command for efficient filesystem traversal
            # Look for directories matching */user/{username}
            cmd = [
                "find",
                str(shows_root),
                "-type",
                "d",
                "-path",
                f"*{self.user_path_pattern}",
                "-maxdepth",
                "8",  # Limit depth for performance
            ]

            logger.debug(f"Running find command: {' '.join(cmd)}")

            # SECURITY FIX: Use stderr=subprocess.DEVNULL instead of shell redirection
            # Note: Can't use capture_output=True with stderr=subprocess.DEVNULL
            # Increased timeout to 120 seconds for large filesystem searches
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,  # Capture stdout explicitly
                stderr=subprocess.DEVNULL,  # Suppress stderr
                text=True,
                timeout=120,  # Increased from 30 to 120 seconds
                shell=False,
            )

            if result.returncode != 0:
                logger.warning(
                    f"Find command returned non-zero exit code: {result.returncode}"
                )

            # Parse each found path to extract shot information
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                shot = self._parse_shot_from_path(line)
                if shot and shot not in shots:
                    shots.append(shot)

            logger.info(f"Found {len(shots)} shots with user work")

        except subprocess.TimeoutExpired:
            logger.error("Find command timed out after 120 seconds")
        except Exception as e:
            logger.error(f"Error finding user shots: {e}")

        return shots

    def _parse_shot_from_path(self, path: str) -> Shot | None:
        """Parse shot information from a filesystem path.

        Args:
            path: Path containing shot information.

        Returns:
            Shot object if path is valid, None otherwise.
        """
        match = self._shot_pattern.search(path)
        if match:
            show, sequence, shot_name = match.groups()

            # Build the workspace path
            workspace_path = f"/shows/{show}/shots/{sequence}/{shot_name}"

            try:
                return Shot(
                    show=show,
                    sequence=sequence,
                    shot=shot_name,
                    workspace_path=workspace_path,
                )
            except Exception as e:
                logger.debug(f"Could not create Shot from path {path}: {e}")

        return None

    def filter_approved_shots(
        self, all_user_shots: list[Shot], active_shots: list[Shot]
    ) -> list[Shot]:
        """Filter out active shots to get only approved/completed ones.

        Args:
            all_user_shots: All shots where user has work.
            active_shots: Currently active shots from workspace.

        Returns:
            List of approved shots (user shots minus active shots).
        """
        # Create a set of active shot identifiers for efficient lookup
        active_ids = {(shot.show, shot.sequence, shot.shot) for shot in active_shots}

        # Filter out active shots
        approved_shots = [
            shot
            for shot in all_user_shots
            if (shot.show, shot.sequence, shot.shot) not in active_ids
        ]

        logger.info(
            f"Filtered {len(all_user_shots)} user shots to "
            f"{len(approved_shots)} approved shots"
        )

        return approved_shots

    def find_approved_shots(
        self, active_shots: list[Shot], shows_root: Path = Path("/shows")
    ) -> list[Shot]:
        """Find all approved shots for the user.

        This is a convenience method that combines finding user shots
        and filtering out active ones.

        Args:
            active_shots: Currently active shots from workspace.
            shows_root: Root directory to search for shots.

        Returns:
            List of approved/completed shots.
        """
        all_user_shots = self.find_user_shots(shows_root)
        return self.filter_approved_shots(all_user_shots, active_shots)

    def get_shot_details(self, shot: Shot) -> dict[str, Any]:
        """Get additional details about an approved shot.

        Args:
            shot: Shot to get details for.

        Returns:
            Dictionary with shot details including paths and metadata.
        """
        details = {
            "show": shot.show,
            "sequence": shot.sequence,
            "shot": shot.shot,
            "workspace_path": shot.workspace_path,
            "user_path": f"{shot.workspace_path}{self.user_path_pattern}",
            "status": "approved",  # These are all approved shots
        }

        # Check if user directory still exists
        user_dir = Path(details["user_path"])
        details["user_dir_exists"] = str(user_dir.exists())

        # Check for common VFX work files
        if user_dir.exists():
            details["has_3de"] = str(any(user_dir.rglob("*.3de")))
            details["has_nuke"] = str(any(user_dir.rglob("*.nk")))
            details["has_maya"] = str(any(user_dir.rglob("*.m[ab]")))

        return details


class ParallelShotsFinder(PreviousShotsFinder):
    """Parallel implementation of PreviousShotsFinder for improved performance.
    
    This class uses ThreadPoolExecutor to search multiple shows in parallel,
    reducing scan time from 120+ seconds to ~30-40 seconds.
    """
    
    def __init__(self, username: str | None = None, max_workers: int | None = None) -> None:
        """Initialize the parallel shots finder.
        
        Args:
            username: Username to search for. If None, uses current user.
            max_workers: Maximum number of parallel workers (default: from config)
        """
        super().__init__(username)
        self.max_workers = max_workers or ThreadingConfig.PREVIOUS_SHOTS_PARALLEL_WORKERS
        self._stop_requested = False
        self._progress_callback = None
        self._show_cache: dict[str, float] = {}  # Cache show list with timestamps
        self._cache_ttl = ThreadingConfig.PREVIOUS_SHOTS_CACHE_TTL
        
    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Set callback for progress reporting.
        
        Args:
            callback: Function to call with (current, total, message) args
        """
        self._progress_callback = callback
        
    def request_stop(self) -> None:
        """Request the parallel scan to stop."""
        self._stop_requested = True
        logger.info("Stop requested for parallel shot finder")
        
    def _report_progress(self, current: int, total: int, message: str) -> None:
        """Report progress if callback is set."""
        if self._progress_callback:
            self._progress_callback(current, total, message)
            
    def _discover_shows(self, shows_root: Path) -> list[Path]:
        """Quickly discover all shows in the root directory.
        
        Args:
            shows_root: Root directory containing shows
            
        Returns:
            List of show directory paths
        """
        shows = []
        
        try:
            # Use os.scandir for fast directory listing
            with os.scandir(shows_root) as entries:
                for entry in entries:
                    if self._stop_requested:
                        break
                        
                    if entry.is_dir() and not entry.name.startswith('.'):
                        # Check if it looks like a show directory
                        show_path = Path(entry.path)
                        shots_dir = show_path / "shots"
                        if shots_dir.exists():
                            shows.append(show_path)
                            
            logger.info(f"Discovered {len(shows)} shows in {shows_root}")
            
        except (OSError, PermissionError) as e:
            logger.error(f"Error discovering shows: {e}")
            
        return shows
        
    def _scan_show_for_user(self, show_path: Path) -> list[Shot]:
        """Scan a single show for user directories.
        
        Args:
            show_path: Path to the show directory
            
        Returns:
            List of Shot objects found in this show
        """
        shots = []
        
        if self._stop_requested:
            return shots
            
        try:
            # Use find command limited to this show
            cmd = [
                "find",
                str(show_path / "shots"),
                "-type", "d",
                "-path", f"*{self.user_path_pattern}",
                "-maxdepth", "6",  # Reduced depth since we're starting from shots/
            ]
            
            # Run with shorter timeout per show
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=ThreadingConfig.PREVIOUS_SHOTS_SCAN_TIMEOUT,  # Configurable timeout per show
                shell=False,
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line or self._stop_requested:
                        continue
                        
                    shot = self._parse_shot_from_path(line)
                    if shot and shot not in shots:
                        shots.append(shot)
                        
            logger.debug(f"Found {len(shots)} shots in {show_path.name}")
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout scanning show: {show_path.name}")
        except Exception as e:
            logger.error(f"Error scanning show {show_path.name}: {e}")
            
        return shots
        
    def find_user_shots_parallel(self, shows_root: Path = Path("/shows")) -> Generator[Shot, None, None]:
        """Find user shots using parallel search with incremental yielding.
        
        Args:
            shows_root: Root directory to search for shots
            
        Yields:
            Shot objects as they are discovered
        """
        if not shows_root.exists():
            logger.warning(f"Shows root does not exist: {shows_root}")
            return
            
        # Stage 1: Quick show discovery
        self._report_progress(0, 100, "Discovering shows...")
        shows = self._discover_shows(shows_root)
        
        if not shows:
            logger.warning("No shows found to scan")
            return
            
        total_shows = len(shows)
        completed_shows = 0
        
        # Stage 2: Parallel search with incremental results
        self._report_progress(10, 100, f"Scanning {total_shows} shows in parallel...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all show scans
            future_to_show = {
                executor.submit(self._scan_show_for_user, show): show 
                for show in shows
            }
            
            # Process results as they complete
            for future in concurrent.futures.as_completed(future_to_show):
                if self._stop_requested:
                    # Cancel remaining futures
                    for f in future_to_show:
                        f.cancel()
                    break
                    
                show = future_to_show[future]
                completed_shows += 1
                
                # Update progress
                progress = 10 + int((completed_shows / total_shows) * 80)
                self._report_progress(
                    progress, 100, 
                    f"Processed {show.name} ({completed_shows}/{total_shows})"
                )
                
                try:
                    shots = future.result(timeout=5)
                    # Yield shots immediately as they're found
                    yield from shots
                        
                except concurrent.futures.TimeoutError:
                    logger.warning(f"Timeout processing {show.name}")
                except Exception as e:
                    logger.error(f"Error processing {show.name}: {e}")
                    
        self._report_progress(100, 100, "Scan complete")
        
    def find_user_shots(self, shows_root: Path = Path("/shows")) -> list[Shot]:
        """Find all shots with user work directories using parallel search.
        
        This method overrides the parent's synchronous implementation with
        a parallel version. Falls back to legacy method if environment variable is set.
        
        Args:
            shows_root: Root directory to search for shots
            
        Returns:
            List of Shot objects where user has work directories
        """
        # Check for legacy mode fallback
        if os.environ.get("USE_LEGACY_SHOT_FINDER"):
            logger.info("Using legacy sequential shot finder")
            return super().find_user_shots(shows_root)
            
        # Use new parallel implementation
        logger.info("Using parallel shot finder with incremental loading")
        start_time = time.time()
        
        # Collect all shots from generator
        shots = list(self.find_user_shots_parallel(shows_root))
        
        elapsed = time.time() - start_time
        logger.info(f"Parallel scan found {len(shots)} shots in {elapsed:.1f} seconds")
        
        return shots

    def find_approved_shots_targeted(
        self, active_shots: list[Shot], shows_root: Path = Path("/shows")
    ) -> list[Shot]:
        """Find approved shots using targeted search for maximum performance.

        This method uses the new TargetedShotsFinder which only searches in shows
        where the user has active shots, providing 95%+ performance improvement
        over scanning all shows.

        Args:
            active_shots: Currently active shots from workspace command
            shows_root: Root directory to search for shots

        Returns:
            List of approved/completed shots
        """
        from targeted_shot_finder import TargetedShotsFinder
        
        # Create targeted finder with same settings
        targeted_finder = TargetedShotsFinder(
            username=self.username, 
            max_workers=self.max_workers
        )
        
        # Set progress callback to forward to our callback
        if self._progress_callback:
            targeted_finder.set_progress_callback(self._progress_callback)
            
        # Forward stop request
        if self._stop_requested:
            targeted_finder.request_stop()
        
        logger.info("Using targeted search approach for maximum performance")
        
        try:
            approved_shots = targeted_finder.find_approved_shots_targeted(
                active_shots, shows_root
            )
            return approved_shots
            
        except Exception as e:
            logger.error(f"Error in targeted search, falling back to parallel search: {e}")
            # Fallback to existing parallel implementation
            return self.find_approved_shots(active_shots, shows_root)
