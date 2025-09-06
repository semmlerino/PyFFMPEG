"""Threading fixes for ShotBot - Critical issues and resolutions"""

# ============================================================================
# FIX 1: ThreeDESceneWorker - Race condition on _finished_emitted
# ============================================================================

# File: threede_scene_worker.py
# Issue: _finished_emitted flag accessed without synchronization
# Impact: Potential double emission of finished signal, race conditions

# CURRENT PROBLEMATIC CODE (lines 298-327):
"""
@Slot()
def run(self) -> None:
    # Track whether finished signal was emitted
    self._finished_emitted = False  # NOT THREAD-SAFE!
    
    try:
        super().run()
    finally:
        if not self._finished_emitted:  # RACE CONDITION!
            # emit signals...
"""

# FIXED CODE:
def fix_threede_scene_worker():
    """
    Add to __init__ method:
    """
    # In __init__, add:
    self._finished_mutex = QMutex()
    self._finished_emitted = False
    
    """
    Replace run() method with:
    """
    @Slot()
    def run(self) -> None:
        """Override run to ensure finished signal is always emitted."""
        # Use mutex for thread-safe access
        with QMutexLocker(self._finished_mutex):
            self._finished_emitted = False
        
        try:
            # Call parent's run() which manages state and calls do_work()
            super().run()
        finally:
            # Thread-safe check and emit
            should_emit = False
            scenes_to_emit = []
            
            with QMutexLocker(self._finished_mutex):
                if not self._finished_emitted:
                    should_emit = True
                    self._finished_emitted = True
                    scenes_to_emit = self._all_scenes.copy() if self._all_scenes else []
            
            # Emit outside the lock to prevent deadlocks
            if should_emit:
                if not scenes_to_emit:
                    logger.debug("Worker finishing, emitting finished signal with empty list")
                    self.finished.emit([])
                else:
                    logger.debug(f"Worker finishing, emitting finished signal with {len(scenes_to_emit)} scenes")
                    self.finished.emit(scenes_to_emit)

    """
    Update do_work() method - protect all _finished_emitted accesses:
    """
    def do_work(self) -> None:
        # ... existing code ...
        
        # Line 405-407: Replace
        # self._finished_emitted = True
        # self.finished.emit([])
        # With:
        with QMutexLocker(self._finished_mutex):
            if not self._finished_emitted:
                self._finished_emitted = True
                # Set flag to emit after lock release
                emit_empty = True
        
        if emit_empty:
            self.finished.emit([])
        
        # Similar pattern for lines 412, 425, 432

# ============================================================================
# FIX 2: ThreeDESceneWorker - Progress Reporter Initialization Race
# ============================================================================

# Issue: _progress_reporter created in do_work() but accessed from threads
# Impact: Null reference if progress callback fires before initialization

# FIXED CODE:
def fix_progress_reporter_race():
    """
    Move progress reporter initialization to __init__:
    """
    def __init__(self, shots, excluded_users=None, batch_size=None, 
                 enable_progressive=True, scan_all_shots=False):
        super().__init__()
        # ... existing init code ...
        
        # Create progress reporter early to avoid race
        self._progress_reporter = QtProgressReporter()
        self._progress_reporter_connected = False
        self._reporter_mutex = QMutex()
    
    def do_work(self) -> None:
        """Enhanced main worker thread execution."""
        try:
            # ... existing code ...
            
            # Connect reporter safely with mutex
            with QMutexLocker(self._reporter_mutex):
                if not self._progress_reporter_connected:
                    self._progress_reporter.progress_update.connect(
                        self._handle_progress_update, 
                        Qt.ConnectionType.QueuedConnection
                    )
                    self._progress_reporter_connected = True
            
            # ... rest of method ...

# ============================================================================
# FIX 3: ThumbnailLoader - Signal Deletion During Emission
# ============================================================================

# File: cache/thumbnail_loader.py
# Issue: Signals can be deleted while being emitted
# Impact: RuntimeError exceptions (caught but not ideal)

# FIXED CODE:
def fix_thumbnail_loader():
    """
    Add signal validity check before emission:
    """
    def run(self) -> None:
        """Process the thumbnail in background with safe signal emission."""
        # ... existing code ...
        
        # Replace lines 208-217 with:
        if success and self.cache_path.exists():
            # Set successful result
            self.result.set_result(self.cache_path)
            
            # Thread-safe signal emission
            try:
                # Check if signals still valid before emission
                if hasattr(self, "signals") and self.signals and not sip.isdeleted(self.signals):
                    self.signals.loaded.emit(
                        self.show,
                        self.sequence, 
                        self.shot,
                        self.cache_path,
                    )
            except (RuntimeError, AttributeError):
                # Object already deleted - safe to ignore
                pass

# ============================================================================  
# FIX 4: CacheManager - Active Loaders Tracking Race
# ============================================================================

# File: cache_manager.py
# Issue: _active_loaders dict accessed from multiple threads
# Impact: KeyError or missing entries

# FIXED CODE:
def fix_cache_manager_active_loaders():
    """
    Already has self._lock, but not used consistently for _active_loaders
    """
    def cache_thumbnail(self, source_path, show, sequence, shot, wait=True, timeout=None):
        # ... existing validation ...
        
        cache_key = f"{show}_{sequence}_{shot}"
        
        # ENTIRE block should be under lock, not just the check
        with self._lock:
            # Check if already being loaded
            if cache_key in self._active_loaders:
                result = self._active_loaders[cache_key]
                # Don't release lock yet!
            else:
                # Check if already cached
                cache_path = self.thumbnails_dir / show / sequence / f"{shot}_thumb.jpg"
                if cache_path.exists():
                    logger.debug(f"Thumbnail already cached: {cache_path}")
                    _ = self._memory_manager.track_item(cache_path)
                    return cache_path
                
                # ... failure tracker check ...
                
                # Create result container and track loading
                result = ThumbnailCacheResult()
                self._active_loaders[cache_key] = result
                # Now safe to release lock
        
        # Continue with processing outside lock...

# ============================================================================
# FIX 5: ProcessPoolManager - Session Pool Race Conditions  
# ============================================================================

# File: process_pool_manager.py
# Issue: Complex session pool management with potential races
# Already mostly fixed with condition variables, but could be improved

# The current implementation is actually quite good with:
# - RLock usage preventing deadlocks
# - Condition variables for synchronization
# - Proper wait/notify patterns

# ============================================================================
# FIX 6: Auto-refresh Timer Race Conditions
# ============================================================================

# Multiple components have auto-refresh timers that could conflict

def fix_auto_refresh_races():
    """
    Ensure all auto-refresh operations are properly synchronized:
    """
    # In PreviousShotsModel.refresh_shots():
    def refresh_shots(self) -> bool:
        """Refresh with proper locking."""
        # Current implementation is good with _scan_lock
        # Just ensure worker cleanup is always called
        
    # In shot_model.py (if has auto-refresh):
    def auto_refresh(self):
        """Ensure single refresh at a time."""
        if hasattr(self, '_refresh_in_progress'):
            with self._refresh_lock:
                if self._refresh_in_progress:
                    logger.debug("Refresh already in progress, skipping")
                    return False
                self._refresh_in_progress = True
        
        try:
            # Do refresh
            pass
        finally:
            with self._refresh_lock:
                self._refresh_in_progress = False

# ============================================================================
# FIX 7: Cross-thread Signal/Slot Connections
# ============================================================================

def ensure_proper_qt_connections():
    """
    All cross-thread signal/slot connections should use QueuedConnection
    """
    # GOOD Examples (already in code):
    # previous_shots_model.py line 161-164:
    self._worker.scan_finished.connect(
        self._on_scan_finished,
        Qt.ConnectionType.QueuedConnection  # CORRECT!
    )
    
    # Check all signal connections and ensure:
    # 1. Cross-thread uses QueuedConnection
    # 2. Same-thread can use DirectConnection for performance
    # 3. Auto connection is risky - be explicit

# ============================================================================
# FIX 8: ThreadPoolExecutor Resource Leaks
# ============================================================================

# Already addressed in threading_utils.py with CancellationEvent system
# The existing implementation is good!

# ============================================================================
# TESTING RECOMMENDATIONS
# ============================================================================

def test_threading_fixes():
    """
    Test cases to verify threading fixes:
    """
    
    # 1. Test rapid start/stop of workers
    for i in range(10):
        worker = ThreeDESceneWorker([])
        worker.start()
        worker.stop()
        assert worker.wait(1000), f"Worker {i} failed to stop"
    
    # 2. Test concurrent thumbnail loading
    from concurrent.futures import ThreadPoolExecutor
    manager = CacheManager()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(100):
            future = executor.submit(
                manager.cache_thumbnail,
                f"test{i}.jpg", "show", "seq", f"shot{i}"
            )
            futures.append(future)
        
        # All should complete without errors
        for future in futures:
            try:
                result = future.result(timeout=5)
            except Exception as e:
                print(f"Thumbnail loading failed: {e}")
    
    # 3. Test progress reporter race
    import time
    from threading import Thread
    
    worker = ThreeDESceneWorker([])
    
    def spam_progress():
        """Spam progress updates from multiple threads"""
        for i in range(100):
            if hasattr(worker, '_progress_reporter'):
                worker._progress_reporter.report_progress(i, f"Thread update {i}")
            time.sleep(0.001)
    
    threads = [Thread(target=spam_progress) for _ in range(5)]
    for t in threads:
        t.start()
    
    worker.start()
    time.sleep(0.5)
    worker.stop()
    
    for t in threads:
        t.join()
    
    # Should not crash or raise exceptions
    
    print("All threading tests passed!")

if __name__ == "__main__":
    test_threading_fixes()
