"""Thread-safe worker for background 3DE scene discovery."""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QMutex, QThread, QWaitCondition, Signal, QObject, QMetaObject, Qt, Slot, QTimer

from config import Config
from thread_safe_worker import ThreadSafeWorker
from threede_scene_finder import ThreeDESceneFinder
from utils import ValidationUtils

if TYPE_CHECKING:
    from shot_model import Shot
    from threede_scene_model import ThreeDEScene

# Set up logger for this module
logger = logging.getLogger(__name__)


class QtThreadSafeEmitter(QObject):
    """Thread-safe signal emitter for cross-thread Qt signal emission.
    
    This class solves Qt thread affinity violations by providing a safe way
    to emit Qt signals from ThreadPoolExecutor worker threads. It defines
    its own signals that can be connected with QueuedConnection to the
    worker's signals, ensuring proper thread-safe delivery.
    
    The emitter must be created in the target thread (worker's QThread) to
    have proper thread affinity for signal emission.
    """
    
    # Internal signals for thread-safe communication
    _progress_signal = Signal(int, str)  # files_found, status

    def __init__(self, worker_instance: 'ThreeDESceneWorker') -> None:
        """Initialize the thread-safe emitter.
        
        Args:
            worker_instance: The worker whose signals will be emitted
        """
        super().__init__()
        self.worker = worker_instance
        
        # Connect our internal signal to the worker's actual signals
        # Use QueuedConnection to ensure thread-safe delivery
        self._progress_signal.connect(
            self._emit_progress_safe,
            Qt.ConnectionType.QueuedConnection
        )
        
        logger.debug("QtThreadSafeEmitter created in thread: %s", self.thread())

    def emit_from_thread(self, files_found: int, status: str) -> None:
        """Safely emit progress signals from any thread.
        
        This method can be called from ThreadPoolExecutor threads or any
        other thread. It emits our internal signal which is connected
        with QueuedConnection to ensure thread-safe delivery.
        
        Args:
            files_found: Number of files found so far
            status: Current status message
        """
        # Emit our internal signal - Qt handles the thread-safe delivery
        self._progress_signal.emit(files_found, status)

    @Slot(int, str)
    def _emit_progress_safe(self, files_found: int, status: str) -> None:
        """Internal slot that emits signals in the correct thread.
        
        This slot runs in the worker's QThread and can safely emit Qt signals.
        It's connected to our internal signal with QueuedConnection.
        
        Args:
            files_found: Number of files found so far
            status: Current status message
        """
        # Check if worker is still valid and not stopped
        if self.worker and not self.worker.is_stop_requested():
            # Emit the signals that were being called directly before
            self.worker.progress.emit(
                files_found,  # current files found
                0,           # total unknown during scanning
                0.0,         # percentage unknown during scanning  
                status,      # current status message
                "",          # ETA not available during parallel scan
            )
            
            # Also emit scan progress for compatibility
            self.worker.scan_progress.emit(files_found, 0, status)


class ProgressCalculator:
    """Helper class for calculating progress and ETA during file scanning."""

    def __init__(self, smoothing_window: int | None = None) -> None:
        """Initialize progress calculator.

        Args:
            smoothing_window: Number of samples for ETA smoothing
        """
        self.smoothing_window = smoothing_window or Config.PROGRESS_ETA_SMOOTHING_WINDOW
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.processing_times: deque[float] = deque(maxlen=self.smoothing_window)
        self.files_processed = 0
        self.total_files_estimate = 0

    def update(
        self,
        files_processed: int,
        total_estimate: int | None = None,
    ) -> tuple[float, str]:
        """Update progress and calculate ETA.

        Args:
            files_processed: Number of files processed so far
            total_estimate: Updated total file estimate (if available)

        Returns:
            Tuple of (progress_percentage, eta_string)
        """
        current_time = time.time()

        if total_estimate is not None:
            self.total_files_estimate = total_estimate

        # Calculate progress percentage
        if self.total_files_estimate > 0:
            progress_pct = min(
                100.0,
                (files_processed / self.total_files_estimate) * 100,
            )
        else:
            progress_pct = 0.0

        # Update processing rate for ETA calculation
        if files_processed > self.files_processed:
            time_delta = current_time - self.last_update_time
            if time_delta > 0:
                files_delta = files_processed - self.files_processed
                rate = files_delta / time_delta  # files per second
                self.processing_times.append(rate)

        self.files_processed = files_processed
        self.last_update_time = current_time

        # Calculate ETA
        eta_str = self._calculate_eta()

        return progress_pct, eta_str

    def _calculate_eta(self) -> str:
        """Calculate estimated time to completion.

        Returns:
            Human-readable ETA string
        """
        if not Config.PROGRESS_ENABLE_ETA:
            return ""

        if (
            self.total_files_estimate <= 0
            or self.files_processed >= self.total_files_estimate
            or len(self.processing_times) == 0
        ):
            return ""

        # Calculate average processing rate
        avg_rate = sum(self.processing_times) / len(self.processing_times)

        if avg_rate <= 0:
            return ""

        remaining_files = self.total_files_estimate - self.files_processed
        eta_seconds = remaining_files / avg_rate

        # Format ETA
        if eta_seconds < 60:
            return f"~{int(eta_seconds)}s remaining"
        if eta_seconds < 3600:
            minutes = int(eta_seconds / 60)
            return f"~{minutes}m remaining"
        hours = int(eta_seconds / 3600)
        minutes = int((eta_seconds % 3600) / 60)
        return f"~{hours}h {minutes}m remaining"


class ThreeDESceneWorker(ThreadSafeWorker):
    """Thread-safe worker for progressive 3DE scene discovery.

    This worker inherits from ThreadSafeWorker to provide:
    - Thread-safe state management
    - Safe signal connection tracking
    - Proper lifecycle management
    - Race condition prevention

    Additional features:
    - Progressive/batched file scanning for responsive UI
    - Cancellation and pause/resume functionality
    - Detailed progress reporting with ETA calculation
    - Memory-aware processing with configurable limits
    """

    # Enhanced signals specific to 3DE discovery
    started = Signal()  # Emitted when discovery starts
    batch_ready = Signal(list)  # Emitted with each batch of scenes
    progress = Signal(
        int,
        int,
        float,
        str,
        str,
    )  # (current, total, percentage, description, eta)
    scan_progress = Signal(int, int, str)  # Emitted during individual shot scanning
    finished = Signal(list)  # Emitted with complete list of scenes
    error = Signal(str)  # Emitted when an error occurs
    paused = Signal()  # Emitted when worker is paused
    resumed = Signal()  # Emitted when worker resumes

    def __init__(
        self,
        shots: list[Shot],
        excluded_users: set[str] | None = None,
        batch_size: int | None = None,
        enable_progressive: bool = True,
        scan_all_shots: bool = False,
    ) -> None:
        """Initialize the enhanced worker with shots to search.

        Args:
            shots: List of shots to use for determining shows to search
            excluded_users: Set of usernames to exclude from search
            batch_size: Number of scenes per batch for progressive scanning
            enable_progressive: Enable progressive scanning (vs. traditional all-at-once)
            scan_all_shots: If True, scan ALL shots in shows (not just provided shots)
        """
        super().__init__()
        self.shots = shots
        self.user_shots = shots  # Keep track of user's shots for filtering
        self.scan_all_shots = scan_all_shots
        self.excluded_users = excluded_users or ValidationUtils.get_excluded_users()
        self.batch_size = batch_size or Config.PROGRESSIVE_SCAN_BATCH_SIZE
        self.enable_progressive = enable_progressive and Config.PROGRESSIVE_SCAN_ENABLED

        # Control flags
        self._is_paused = False  # Only pause flag needed, stop is managed by base class

        # Thread synchronization
        self._pause_mutex = QMutex()
        self._pause_condition = QWaitCondition()

        # Progress tracking
        self._progress_calculator = ProgressCalculator()
        self._last_progress_time = 0
        self._all_scenes: list[ThreeDEScene] = []
        self._files_processed = 0

        # Store desired priority for setting after thread starts
        priority_map = {
            -1: QThread.Priority.LowPriority,
            0: QThread.Priority.NormalPriority,
            1: QThread.Priority.HighPriority,
        }
        self._desired_priority = priority_map.get(
            Config.WORKER_THREAD_PRIORITY,
            QThread.Priority.NormalPriority,
        )

    def stop(self) -> None:
        """Request the worker to stop processing.

        Uses the thread-safe base class stop mechanism.
        """
        logger.debug("Stop requested for 3DE scene worker")
        # Wake up paused thread so it can exit
        self.resume()
        # Use base class thread-safe stop
        self.request_stop()

    def pause(self) -> None:
        """Request the worker to pause processing."""
        logger.debug("Pause requested for 3DE scene worker")
        should_emit = False
        self._pause_mutex.lock()
        try:
            if not self._is_paused:  # Only emit if state actually changes
                self._is_paused = True
                should_emit = True
        finally:
            self._pause_mutex.unlock()

        # Emit signal outside the lock to prevent deadlocks
        if should_emit:
            self.paused.emit()

    def resume(self) -> None:
        """Resume processing if paused."""
        logger.debug("Resume requested for 3DE scene worker")
        should_emit = False
        self._pause_mutex.lock()
        try:
            if self._is_paused:
                self._is_paused = False
                self._pause_condition.wakeAll()
                should_emit = True
        finally:
            self._pause_mutex.unlock()

        # Emit signal outside the lock to prevent deadlocks
        if should_emit:
            self.resumed.emit()

    def is_paused(self) -> bool:
        """Check if worker is currently paused."""
        self._pause_mutex.lock()
        try:
            return self._is_paused
        finally:
            self._pause_mutex.unlock()

    def _check_pause_and_cancel(self) -> bool:
        """Check for pause/cancel requests and handle them.

        Returns:
            True if should continue, False if should exit
        """
        # Check for cancellation using base class method
        if self.is_stop_requested():
            logger.debug("Worker received stop signal")
            return False

        # Check for pause
        self._pause_mutex.lock()
        try:
            while self._is_paused and not self.is_stop_requested():
                logger.debug("Worker paused, waiting for resume...")
                self._pause_condition.wait(
                    self._pause_mutex,
                    Config.WORKER_PAUSE_CHECK_INTERVAL_MS,
                )
        finally:
            self._pause_mutex.unlock()

        # Check cancellation again after pause
        return not self.is_stop_requested()

    def do_work(self) -> None:
        """Enhanced main worker thread execution with progressive scanning.

        This replaces the run() method to follow ThreadSafeWorker pattern.
        The base class run() method handles state management and calls this.
        """
        try:
            # Set thread priority now that thread is running
            if hasattr(self, "_desired_priority"):
                self.setPriority(self._desired_priority)

            # Create thread-safe emitter now that we're in the worker thread
            # This ensures proper Qt thread affinity for signal emission
            self.thread_safe_emitter = QtThreadSafeEmitter(self)
            logger.debug("Thread-safe emitter created in worker thread")

            logger.info("Starting enhanced 3DE scene discovery")
            self.started.emit()

            if not self.shots:
                logger.warning("No shots provided for 3DE scene discovery")
                self.finished.emit([])
                return

            # Check for initial cancellation using base class method
            if self.is_stop_requested():
                logger.info("3DE scene discovery cancelled before starting")
                self.finished.emit([])
                return

            # Choose discovery method based on configuration
            if self.enable_progressive:
                scenes = self._discover_scenes_progressive()
            else:
                scenes = self._discover_scenes_traditional()

            # Final cancellation check
            if self.is_stop_requested():
                logger.info("3DE scene discovery cancelled during processing")
                self.finished.emit(self._all_scenes)  # Return partial results
                return

            logger.info(
                f"Enhanced 3DE scene discovery completed: {len(scenes)} scenes found",
            )
            self.finished.emit(scenes)

        except Exception as e:
            logger.error(f"Error in enhanced 3DE scene discovery worker: {e}")
            self.error.emit(str(e))
            # Re-raise to trigger worker_error signal from base class
            raise

    def _discover_scenes_progressive(self) -> list[ThreeDEScene]:
        """Progressive scene discovery with batch processing and detailed progress.

        Returns:
            List of all discovered ThreeDEScene objects
        """
        logger.info("Starting progressive 3DE scene discovery")

        if self.scan_all_shots:
            # When scanning all shots, use the efficient file-first discovery
            # This finds ALL 3DE files in the shows, then filters
            return self._discover_all_scenes_in_shows()

        # Original behavior: scan only the provided shots
        # Convert shots to the format expected by the finder
        shot_tuples = []
        for shot in self.shots:
            shot_tuples.append(
                (shot.workspace_path, shot.show, shot.sequence, shot.shot),
            )

        # Get size estimation for progress calculation
        try:
            estimated_users, estimated_files = ThreeDESceneFinder.estimate_scan_size(
                shot_tuples,
                self.excluded_users,
            )
            logger.debug(
                f"Scan estimate: {estimated_users} users, ~{estimated_files} files",
            )

            # Initialize progress tracking
            self._progress_calculator = ProgressCalculator()
            self._files_processed = 0

            # Emit initial progress
            progress_pct, eta_str = self._progress_calculator.update(0, estimated_files)
            self.progress.emit(
                0,
                estimated_files,
                progress_pct,
                f"Starting scan of {len(shot_tuples)} shots",
                eta_str,
            )

        except Exception as e:
            logger.warning(f"Could not estimate scan size: {e}")
            estimated_files = len(shot_tuples) * 10  # Fallback estimate

        # Use the progressive finder generator
        try:
            for (
                scene_batch,
                current_shot,
                total_shots,
                status_msg,
            ) in ThreeDESceneFinder.find_all_scenes_progressive(
                shot_tuples,
                self.excluded_users,
                self.batch_size,
            ):
                # Check for pause/cancel between batches
                if not self._check_pause_and_cancel():
                    break

                # Add batch to accumulated results
                if scene_batch:
                    self._all_scenes.extend(scene_batch)
                    self.batch_ready.emit(scene_batch)

                    logger.debug(f"Processed batch of {len(scene_batch)} scenes")

                # Update progress tracking
                self._files_processed += len(scene_batch)

                # Throttle progress updates
                current_time = time.time()
                if (current_time - self._last_progress_time) >= (
                    Config.PROGRESS_UPDATE_INTERVAL_MS / 1000.0
                ):
                    progress_pct, eta_str = self._progress_calculator.update(
                        self._files_processed,
                        estimated_files,
                    )

                    detailed_status = (
                        f"{status_msg} ({len(self._all_scenes)} scenes found)"
                    )

                    self.progress.emit(
                        current_shot,
                        total_shots,
                        progress_pct,
                        detailed_status,
                        eta_str,
                    )

                    self._last_progress_time = current_time

                # Emit scan progress for fine-grained updates
                self.scan_progress.emit(current_shot, total_shots, status_msg)

        except Exception as e:
            logger.error(f"Error in progressive discovery: {e}")
            raise

        return self._all_scenes

    def _discover_all_scenes_in_shows(self) -> list[ThreeDEScene]:
        """Discover ALL 3DE scenes in the shows using parallel scanning.

        This uses the new parallel file-first discovery to find ALL 3DE files
        with frequent progress updates, then filters out user's shots.

        Returns:
            List of all discovered ThreeDEScene objects
        """
        logger.info("Discovering ALL 3DE scenes in shows using parallel file-first strategy")

        # Create progress callback that emits signals to UI using thread-safe emitter
        def progress_callback(files_found: int, status: str) -> None:
            """Forward progress updates to UI with cancellation check.
            
            This callback runs in ThreadPoolExecutor worker threads, so it uses
            the thread-safe emitter to avoid Qt thread affinity violations.
            """
            if self.is_stop_requested():
                return
                
            # Use thread-safe emitter instead of direct signal emission
            # This prevents Qt thread affinity violations when called from ThreadPoolExecutor
            self.thread_safe_emitter.emit_from_thread(files_found, status)

        # Create cancel flag callback
        def cancel_flag() -> bool:
            """Check if scan should be cancelled."""
            return self.is_stop_requested()

        # Use the new parallel file-first discovery
        logger.info("Using parallel discovery with progress reporting")
        all_scenes = ThreeDESceneFinder.find_all_scenes_in_shows_truly_efficient_parallel(
            self.user_shots,  # Used to determine which shows to search
            self.excluded_users,
            progress_callback=progress_callback,
            cancel_flag=cancel_flag,
        )

        # Check for cancellation after scan
        if self.is_stop_requested():
            logger.info("3DE scene discovery cancelled during parallel scan")
            return []

        # Create a set of user's shot identifiers for filtering
        user_shot_ids = set()
        for shot in self.user_shots:
            shot_id = f"{shot.show}/{shot.sequence}/{shot.shot}"
            user_shot_ids.add(shot_id)

        # Filter out user's shots from the results (for "Other 3DE scenes")
        other_scenes = []
        for scene in all_scenes:
            if self.is_stop_requested():
                break
                
            scene_id = f"{scene.show}/{scene.sequence}/{scene.shot}"
            if scene_id not in user_shot_ids:
                other_scenes.append(scene)

        logger.info(
            f"Found {len(all_scenes)} total scenes using parallel scan, {len(other_scenes)} are from other shots",
        )

        # Emit final progress update
        if not self.is_stop_requested():
            self.progress.emit(
                len(other_scenes),
                len(all_scenes),
                100.0,
                f"Completed: Found {len(other_scenes)} scenes from other shots",
                "",
            )

        return other_scenes

    def _discover_scenes_traditional(self) -> list[ThreeDEScene]:
        """Traditional scene discovery method for backward compatibility.

        Returns:
            List of discovered ThreeDEScene objects
        """
        logger.info("Using traditional 3DE scene discovery method")

        all_scenes: list[ThreeDEScene] = []

        # Extract unique shows and show roots
        shows_to_search: set[str] = set()
        show_roots: set[str] = set()

        for shot in self.shots:
            shows_to_search.add(shot.show)
            # Extract show root from workspace path
            workspace_parts = Path(shot.workspace_path).parts
            if "shows" in workspace_parts:
                shows_idx = workspace_parts.index("shows")
                show_root = "/".join(workspace_parts[: shows_idx + 1])
                show_roots.add(show_root)

        if not show_roots:
            # Use configured show roots or fallback
            configured_roots = (
                Config.SHOW_ROOT_PATHS
                if hasattr(Config, "SHOW_ROOT_PATHS")
                else ["/shows"]
            )
            show_roots = set(configured_roots)

        total_shows = len(shows_to_search)
        current_show = 0

        # Process each show
        for show_root in show_roots:
            for show in shows_to_search:
                if not self._check_pause_and_cancel():
                    break

                current_show += 1
                self.progress.emit(
                    current_show,
                    total_shows,
                    0.0,
                    f"Discovering shots in {show}",
                    "",
                )

                # Discover all shots in this show
                all_shots = ThreeDESceneFinder.discover_all_shots_in_show(
                    show_root,
                    show,
                )

                if not all_shots:
                    logger.warning(f"No shots discovered in {show}")
                    continue

                self.progress.emit(
                    current_show,
                    total_shows,
                    0.0,
                    f"Searching {len(all_shots)} shots in {show}",
                    "",
                )

                # Search each discovered shot with periodic progress updates
                shot_count = 0
                for workspace_path, show_name, sequence, shot in all_shots:
                    if not self._check_pause_and_cancel():
                        break

                    shot_count += 1

                    # Update progress every 10 shots to avoid too many signals
                    if shot_count % 10 == 0:
                        progress_pct = (shot_count / len(all_shots)) * 100
                        self.progress.emit(
                            current_show,
                            total_shows,
                            progress_pct,
                            f"Searching {show} ({shot_count}/{len(all_shots)} shots)",
                            "",
                        )

                    scenes = ThreeDESceneFinder.find_scenes_for_shot(
                        workspace_path,
                        show_name,
                        sequence,
                        shot,
                        self.excluded_users,
                    )
                    all_scenes.extend(scenes)

                if not self._check_pause_and_cancel():
                    break

            if not self._check_pause_and_cancel():
                break

        # Final progress update
        if self._check_pause_and_cancel():
            self.progress.emit(
                total_shows,
                total_shows,
                100.0,
                f"Discovery complete: {len(all_scenes)} scenes found",
                "",
            )

        return all_scenes
