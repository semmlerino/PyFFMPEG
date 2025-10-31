# ShotBot Remediation - PART 1: Critical Fixes & Performance

**Focus:** Fix crashes, data loss, and UI blocking (URGENT)  
**Effort:** 12-16 hours (3-4 days with reviews)  
**Tasks:** 6 tasks across Phases 1-2

---

## Quick Checklist

### Phase 1: Critical Bug Fixes
- [ ] **1.1** Fix signal disconnection crash (`process_pool_manager.py`)
- [ ] **1.2** Fix cache write data loss (`cache_manager.py`)
- [ ] **1.3** Fix model item access race (`base_item_model.py`)

### Phase 2: Performance Bottlenecks
- [ ] **2.1** Move JSON serialization to background thread (`cache_manager.py`)
- [ ] **2.2** Add LRU eviction to thumbnail cache (`base_item_model.py`)
- [ ] **2.3** Optimize PIL thumbnail generation (`cache_manager.py`)

### Success Metrics
- [ ] UI blocking: 180ms → <10ms (95% improvement)
- [ ] Memory: Unbounded → ~128MB (capped)
- [ ] Thumbnails: 70-140ms → 20-40ms (60% faster)
- [ ] All tests pass: `uv run pytest tests/unit/ -v`

---

# PHASE 1: CRITICAL BUG FIXES

## Task 1.1: Fix Signal Disconnection Crash ⚠️ CRITICAL

**Issue:** `RuntimeError` when disconnecting signals with no connections  
**File:** `process_pool_manager.py:602-615`

### Fix
```python
def cleanup(self) -> None:
    """Clean up resources and disconnect signals safely."""
    # Disconnect each signal individually with try/except
    if hasattr(self, "command_completed"):
        try:
            self.command_completed.disconnect()
            self.logger.debug("Disconnected command_completed signal")
        except (RuntimeError, TypeError) as e:
            self.logger.debug(f"command_completed already disconnected: {e}")

    if hasattr(self, "command_failed"):
        try:
            self.command_failed.disconnect()
            self.logger.debug("Disconnected command_failed signal")
        except (RuntimeError, TypeError) as e:
            self.logger.debug(f"command_failed already disconnected: {e}")

    # Shutdown executor
    if self._executor:
        try:
            self._executor.shutdown(wait=False)
            self.logger.info("ProcessPoolManager executor shutdown")
        except Exception as e:
            self.logger.error(f"Error shutting down executor: {e}")
```

### Tests Required
```python
# tests/unit/test_process_pool_manager.py
def test_cleanup_no_connections(qtbot):
    """Test cleanup when signals have no connections."""
    manager = ProcessPoolManager.get_instance()
    manager.cleanup()  # Should NOT crash
    manager.cleanup()  # Second call also safe
    assert True

def test_cleanup_idempotent(qtbot):
    """Test multiple cleanup calls."""
    manager = ProcessPoolManager.get_instance()
    for _ in range(3):
        handler = lambda x, y: None
        manager.command_completed.connect(handler)
        manager.cleanup()
        manager.cleanup()
    assert True
```

### Verify
```bash
uv run pytest tests/unit/test_process_pool_manager.py -v
uv run basedpyright
```

### Git Commit
```bash
git add process_pool_manager.py tests/unit/test_process_pool_manager.py
git commit -m "fix(critical): Prevent signal disconnection crash on shutdown

- Wrap each signal.disconnect() in individual try/except
- Add debug logging for disconnection events
- Add idempotent cleanup tests
- Fixes RuntimeError on application exit

Related: Phase 1, Task 1.1"
```

---

## Task 1.2: Fix Cache Write Data Loss ⚠️ CRITICAL

**Issue:** Signal emitted before write verification → silent data loss  
**File:** `cache_manager.py:454-480`

### Fix
```python
def migrate_shots_to_previous(
    self, to_migrate: Sequence[Shot | ShotDict]
) -> bool:  # ← Now returns success status
    """Migrate shots to previous cache.
    
    Returns:
        bool: True if migration succeeded, False if write failed
    """
    to_migrate_dicts = [self._shot_to_dict(shot) for shot in to_migrate]

    with QMutexLocker(self._lock):
        existing = self._read_json_cache(self.migrated_shots_cache_file) or []
        existing_dicts = cast("list[ShotDict]", existing)

        # Deduplicate
        existing_keys = {
            (s["show"], s["sequence"], s["shot"]) for s in existing_dicts
        }
        new_shots = [
            s for s in to_migrate_dicts
            if (s["show"], s["sequence"], s["shot"]) not in existing_keys
        ]

        merged = existing_dicts + new_shots

        # Write FIRST
        write_success = self._write_json_cache(
            self.migrated_shots_cache_file, merged
        )

    # Emit signal OUTSIDE lock, ONLY if write succeeded
    if write_success:
        self.logger.info(f"Migrated {len(to_migrate)} shots ({len(new_shots)} new)")
        self.shots_migrated.emit(to_migrate)
        return True
    else:
        self.logger.error(
            f"FAILED to persist {len(to_migrate)} migrated shots. "
            "Migration LOST!"
        )
        return False
```

### Update Caller
```python
# cache_manager.py:545-555
def merge_shots_incremental(self, cached, fresh):
    # ... existing logic ...
    
    if removed_shots:
        self.logger.info(f"Auto-migrating {len(removed_shots)} removed shots")
        success = self.migrate_shots_to_previous(removed_shots)
        if not success:
            self.logger.critical(
                "MIGRATION FAILED - shots may be lost permanently!"
            )

    return ShotMergeResult(...)
```

### Tests Required
```python
# tests/unit/test_cache_manager.py
def test_migrate_shots_disk_full(tmp_path, qtbot, monkeypatch):
    """Test migration failure when disk is full."""
    cache_manager = CacheManager(cache_dir=tmp_path)
    
    # Mock write to fail
    def mock_write_fail(*args, **kwargs):
        return False
    monkeypatch.setattr(cache_manager, "_write_json_cache", mock_write_fail)

    shots = [Shot("show1", "ABC", "0010", Path("/fake"))]
    signal_emitted = []
    cache_manager.shots_migrated.connect(lambda s: signal_emitted.append(s))

    result = cache_manager.migrate_shots_to_previous(shots)

    assert result is False
    assert len(signal_emitted) == 0  # Signal NOT emitted on failure
```

### Verify
```bash
uv run pytest tests/unit/test_cache_manager.py -v
```

### Git Commit
```bash
git add cache_manager.py tests/unit/test_cache_manager.py
git commit -m "fix(critical): Prevent data loss in shot migration

- Emit shots_migrated signal ONLY after successful write
- Return bool from migrate_shots_to_previous()
- Add critical error logging on write failure
- Add tests for disk full scenario

Related: Phase 1, Task 1.2"
```

---

## Task 1.3: Fix Model Item Access Race Condition

**Issue:** `_items` list accessed without bounds checking during concurrent updates  
**File:** `base_item_model.py:365-395`

### Fix
```python
def _do_load_visible_thumbnails(self) -> None:
    """Load thumbnails with race condition protection."""
    if not self._items:
        return

    # Snapshot current state under lock
    with QMutexLocker(self._cache_mutex):
        item_count = len(self._items)
        visible_start = self._visible_start
        visible_end = self._visible_end

    # Calculate range with buffer
    buffer_size = 5
    start = max(0, visible_start - buffer_size)
    end = min(item_count, visible_end + buffer_size)

    # Collect items to load with atomic check-and-mark
    items_to_load: list[tuple[int, T]] = []

    with QMutexLocker(self._cache_mutex):
        # DEFENSIVE: Re-check item count inside lock
        current_count = len(self._items)
        if current_count != item_count:
            # Items changed - reschedule
            self.logger.warning(
                f"Item count changed ({item_count} → {current_count}). Rescheduling."
            )
            QTimer.singleShot(100, self._do_load_visible_thumbnails)
            return

        for row in range(start, end):
            # DEFENSIVE: Bounds check before access
            if row >= len(self._items):
                self.logger.warning(
                    f"Row {row} out of bounds (len={len(self._items)}). "
                    "Concurrent set_items() detected."
                )
                break

            item = self._items[row]

            # Skip if already cached or loading
            if item.full_name in self._thumbnail_cache:
                continue

            state = self._loading_states.get(item.full_name)
            if state in ("loading", "failed"):
                continue

            # Mark as loading atomically
            self._loading_states[item.full_name] = "loading"
            items_to_load.append((row, item))

    # Load thumbnails outside lock
    for row, item in items_to_load:
        self._load_thumbnail_async(row, item)
```

### Tests Required
```python
# tests/unit/test_base_item_model.py
def test_concurrent_set_items_during_load(qtbot):
    """Test concurrent set_items doesn't crash thumbnail loading."""
    model = ShotItemModel()
    shots = [create_mock_shot(i) for i in range(100)]
    model.set_items(shots)
    model.set_visible_range(0, 50)

    # Immediately change items (race condition)
    new_shots = [create_mock_shot(i + 100) for i in range(50)]
    model.set_items(new_shots)  # Should NOT crash

    qtbot.wait(500)
    assert model.rowCount() == 50
```

### Verify
```bash
uv run pytest tests/unit/test_base_item_model.py -v
```

### Git Commit
```bash
git add base_item_model.py tests/unit/test_base_item_model.py
git commit -m "fix(high): Add bounds checking for concurrent item access

- Snapshot item count before iteration
- Re-check count inside lock before access
- Add defensive bounds checking in loop
- Reschedule load if items change mid-iteration

Related: Phase 1, Task 1.3"
```

---

# PHASE 2: PERFORMANCE BOTTLENECKS

## Task 2.1: Move JSON Serialization to Background Thread

**Issue:** `json.dump()` + `fsync()` blocks main thread for ~180ms  
**File:** `cache_manager.py:860-905`  
**Impact:** UI freezes during cache writes

### Add Async Write Infrastructure
```python
# cache_manager.py (ADD)
from concurrent.futures import ThreadPoolExecutor, Future

class CacheManager:
    def __init__(self, ...):
        # ... existing init ...
        
        # Background thread pool for I/O
        self._io_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="cache_io"
        )
        self._pending_writes: dict[Path, Future[bool]] = {}

    def _write_json_cache_sync(self, cache_file: Path, data: object) -> bool:
        """Synchronous write (renamed for clarity)."""
        cache_data = {"data": data, "cached_at": datetime.now().isoformat()}
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path_str = tempfile.mkstemp(
            suffix=".tmp",
            prefix=f".{cache_file.name}.",
            dir=cache_file.parent,
        )
        temp_path = Path(temp_path_str)

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(temp_path, cache_file)
            return True
        except Exception as e:
            self.logger.error(f"Failed to write cache {cache_file}: {e}")
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
            return False

    def write_json_cache_async(
        self,
        cache_file: Path,
        data: object,
        callback: Callable[[bool], None] | None = None,
    ) -> Future[bool]:
        """Write JSON cache asynchronously."""
        # Cancel any pending write for same file
        if cache_file in self._pending_writes:
            self._pending_writes[cache_file].cancel()

        # Submit to background thread
        future = self._io_executor.submit(
            self._write_json_cache_sync, cache_file, data
        )

        # Add callback if provided
        if callback:
            def done_callback(f: Future[bool]) -> None:
                try:
                    success = f.result()
                    callback(success)
                except Exception as e:
                    self.logger.error(f"Cache write callback error: {e}")
                    callback(False)
            future.add_done_callback(done_callback)

        self._pending_writes[cache_file] = future
        return future

    def wait_for_pending_writes(self, timeout: float = 5.0) -> bool:
        """Wait for all pending async writes (call on shutdown)."""
        if not self._pending_writes:
            return True

        self.logger.info(f"Waiting for {len(self._pending_writes)} pending writes...")

        all_success = True
        for cache_file, future in list(self._pending_writes.items()):
            try:
                success = future.result(timeout=timeout)
                if not success:
                    all_success = False
            except TimeoutError:
                self.logger.error(f"Write timeout: {cache_file}")
                all_success = False

        self._pending_writes.clear()
        return all_success

    def cleanup(self) -> None:
        """Cleanup resources (call on shutdown)."""
        self.wait_for_pending_writes(timeout=5.0)
        self._io_executor.shutdown(wait=True)
```

### Update cache_shots() to Use Async
```python
# cache_manager.py:374-395 (UPDATE)
def cache_shots(self, shots: Sequence[Shot | ShotDict]) -> None:
    """Cache shots with async write (non-blocking)."""
    shots_dicts = [self._shot_to_dict(shot) for shot in shots]

    with QMutexLocker(self._lock):
        self._shots_cache = shots_dicts
        self._cache_timestamp = datetime.now()

    # Write asynchronously
    def on_write_complete(success: bool) -> None:
        if success:
            self.logger.info(f"Cached {len(shots_dicts)} shots asynchronously")
            self.cache_updated.emit("shots")
        else:
            self.logger.error("Failed to persist shots cache")

    self.write_json_cache_async(
        self.shots_cache_file,
        shots_dicts,
        callback=on_write_complete
    )
```

### Performance Test
```python
# tests/performance/test_cache_write.py (NEW)
def test_cache_write_doesnt_block_ui(qtbot, tmp_path):
    """Verify async cache write doesn't block UI thread."""
    cache_manager = CacheManager(cache_dir=tmp_path)
    shots = [create_mock_shot(i) for i in range(432)]

    start = time.perf_counter()
    cache_manager.cache_shots(shots)
    elapsed = time.perf_counter() - start

    # Should return almost immediately (<10ms)
    assert elapsed < 0.010, f"Blocked for {elapsed*1000:.1f}ms"

    # Wait for background write
    cache_manager.wait_for_pending_writes()

    # Verify write succeeded
    cached = cache_manager.get_persistent_shots()
    assert len(cached) == 432
```

### Verify
```bash
uv run pytest tests/performance/test_cache_write.py -v
```

### Git Commit
```bash
git add cache_manager.py tests/performance/test_cache_write.py
git commit -m "perf(critical): Move JSON serialization to background threads

- Add ThreadPoolExecutor for non-blocking cache writes
- Implement write_json_cache_async() with callback support
- Add wait_for_pending_writes() for graceful shutdown
- Reduce UI blocking from 180ms to <10ms (95% improvement)

Related: Phase 2, Task 2.1"
```

---

## Task 2.2: Add LRU Eviction to Thumbnail Cache

**Issue:** Unbounded `_thumbnail_cache` dict grows indefinitely  
**File:** `base_item_model.py:139`  
**Impact:** Memory leak (~110MB+ baseline)

### Add LRU Cache Class
```python
# base_item_model.py (ADD)
from collections import OrderedDict

class LRUCache(Generic[K, V]):
    """Thread-safe LRU cache with size limit."""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._lock = QMutex()

    def get(self, key: K) -> V | None:
        """Get value and move to end (most recently used)."""
        with QMutexLocker(self._lock):
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: K, value: V) -> None:
        """Put value, evict LRU if over max_size."""
        with QMutexLocker(self._lock):
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value

            # Evict oldest if over limit
            if len(self._cache) > self.max_size:
                oldest_key = next(iter(self._cache))
                self._cache.pop(oldest_key)

    def __contains__(self, key: K) -> bool:
        with QMutexLocker(self._lock):
            return key in self._cache

    def clear(self) -> None:
        with QMutexLocker(self._lock):
            self._cache.clear()

    def __len__(self) -> int:
        with QMutexLocker(self._lock):
            return len(self._cache)
```

### Update BaseItemModel
```python
# base_item_model.py (UPDATE)
class BaseItemModel(QAbstractListModel, Generic[T]):
    def __init__(self, ...):
        # ... existing init ...
        
        # Replace dict with LRU cache
        self._thumbnail_cache = LRUCache[str, QImage](max_size=500)
```

### Update Cache Operations
```python
# Replace all dict operations with LRU cache methods:
# self._thumbnail_cache[key] = value  →  self._thumbnail_cache.put(key, value)
# key in self._thumbnail_cache  →  stays the same (uses __contains__)
```

### Tests
```python
# tests/unit/test_lru_cache.py (NEW)
def test_eviction():
    """Test LRU eviction."""
    cache = LRUCache[str, str](max_size=3)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")
    
    cache.put("d", "4")  # Evicts "a"
    assert "a" not in cache
    assert "d" in cache

def test_lru_ordering():
    """Test recently accessed items are kept."""
    cache = LRUCache[str, str](max_size=3)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")
    
    cache.get("a")  # Make "a" recent
    cache.put("d", "4")  # Should evict "b"
    
    assert "a" in cache  # Kept
    assert "b" not in cache  # Evicted
```

### Verify
```bash
uv run pytest tests/unit/test_lru_cache.py -v
```

### Git Commit
```bash
git add base_item_model.py tests/unit/test_lru_cache.py
git commit -m "perf(medium): Add LRU eviction to thumbnail cache

- Implement thread-safe LRUCache[K, V] generic class
- Cap thumbnail cache at 500 items (~128MB)
- Automatic eviction of least recently used thumbnails

Memory improvement:
- Before: Unbounded (110MB+ baseline, grows indefinitely)
- After: Capped at ~128MB

Related: Phase 2, Task 2.2"
```

---

## Task 2.3: Optimize PIL Thumbnail Generation

**Issue:** PIL thumbnail generation takes 70-140ms per image  
**File:** `cache_manager.py:301-319`

### Optimize Thumbnail Processing
```python
# cache_manager.py:301-330 (REPLACE)
def _process_standard_thumbnail(self, source: Path, output: Path) -> Path:
    """Generate thumbnail with optimized PIL settings.
    
    Optimizations:
    - Use img.draft() for faster JPEG decoding
    - Use BILINEAR instead of LANCZOS (4x faster, minimal quality loss at 256px)
    - Optimize JPEG encoding settings
    """
    img = Image.open(source)

    # For JPEG files, use draft mode (fast path)
    if img.format == "JPEG":
        img.draft("RGB", (256, 256))

    # BILINEAR is 4x faster than LANCZOS with minimal difference at 256px
    img.thumbnail((256, 256), Image.Resampling.BILINEAR)

    # Convert and save with optimized settings
    if img.mode != "RGB":
        img = img.convert("RGB")

    img.save(
        output,
        "JPEG",
        quality=85,
        optimize=False,  # Disable for faster encoding
        progressive=False,  # Not needed for small files
    )

    return output
```

### Performance Test
```python
# tests/performance/test_thumbnail_generation.py (NEW)
def test_thumbnail_generation_performance(tmp_path):
    """Benchmark thumbnail generation speed."""
    cache_manager = CacheManager(cache_dir=tmp_path)
    test_image = create_test_jpeg(tmp_path / "test.jpg", (1920, 1080))

    times = []
    for i in range(10):
        start = time.perf_counter()
        cache_manager._process_standard_thumbnail(
            test_image,
            tmp_path / f"thumb_{i}.jpg"
        )
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    avg_time = sum(times) / len(times)
    print(f"Average: {avg_time*1000:.1f}ms")

    # Should be under 50ms with optimizations
    assert avg_time < 0.050
```

### Verify
```bash
uv run pytest tests/performance/test_thumbnail_generation.py -v
```

### Git Commit
```bash
git add cache_manager.py tests/performance/test_thumbnail_generation.py
git commit -m "perf(medium): Optimize PIL thumbnail generation

- Use img.draft() for faster JPEG decoding
- Switch from LANCZOS to BILINEAR (4x faster)
- Disable optimize/progressive for small files

Performance improvement:
- Before: 70-140ms per thumbnail
- After: 20-40ms per thumbnail (60% faster)

Related: Phase 2, Task 2.3"
```

---

# PART 1 COMPLETION

## Final Verification

```bash
# Full test suite
uv run pytest tests/unit/ -v
uv run pytest tests/performance/ -v

# Type checking and linting
uv run basedpyright
uv run ruff check .

# Manual smoke test
uv run python shotbot.py --mock
# - Navigate all tabs
# - Rapid tab switching
# - Clean shutdown
```

## Success Metrics Checklist

- [ ] No crashes on shutdown
- [ ] No data loss on migration  
- [ ] UI blocking: 180ms → <10ms ✅
- [ ] Memory: Unbounded → ~128MB ✅
- [ ] Thumbnails: 70-140ms → 20-40ms ✅
- [ ] All tests passing ✅

## After Part 1

1. **Document actual performance metrics**
2. **Verify all success criteria met**
3. **Proceed to IMPLEMENTATION_PLAN_PART2.md**

---

**Part 1 Complete!** Ready for Part 2 (architecture & polish)

**Document Version:** 1.1  
**Last Updated:** 2025-10-30
