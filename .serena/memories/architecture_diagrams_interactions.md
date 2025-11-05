# Shotbot Architecture: Diagrams & System Interactions

## 1. LAYERED ARCHITECTURE VISUALIZATION

```
┌───────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE LAYER                         │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  MainWindow (Coordination & Layout)                            │ │
│  │  ├─ Tab Widget (My Shots | 3DE Scenes | Previous Shots)       │ │
│  │  ├─ Split View (Grids | Info/Launcher Panels)                 │ │
│  │  └─ Menu Bar (File, View, Edit, Tools, Help)                  │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─ Tab 1: My Shots    ─┬─ Tab 2: 3DE Scenes    ─┬─ Tab 3: Previous ─┐
│  │ ShotGridView         │ ThreeDEGridView        │ PreviousShotsView │
│  │ (+ Filter Bar)       │ (+ Filter Bar)         │ (+ Filter Bar)    │
│  └──────────────────────┴────────────────────────┴───────────────────┘
│  ┌─ Right Panel (Dynamic) ──────────────────────────────────────────┐ │
│  │ ┌─ ShotInfoPanel ──────┬─ LauncherPanel ──────┬─ LogViewer ──┐  │ │
│  │ │ (Metadata Display)   │ (Launch Buttons)     │ (Command Log)│  │ │
│  │ └──────────────────────┴──────────────────────┴──────────────┘  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      CONTROLLER LAYER                                │
│  ┌──────────────────┬──────────────────┬──────────────────┐          │
│  │LauncherController│SettingsController│ThreeDEController │          │
│  │ - launch_app()   │ - save_settings() │ - recover_scene()│          │
│  │ - update_menu()  │ - load_settings() │ - open_latest()  │          │
│  └──────────────────┴──────────────────┴──────────────────┘          │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ RefreshOrchestrator (Coordinates Model Refresh)                 │ │
│  │ - schedule_refresh()  - handle_model_changes()                  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────────────────────────────────────────────────────────────┐
│                        MODEL LAYER                                   │
│  ┌──────────────────┬──────────────────┬──────────────────┐          │
│  │   ShotModel      │ ThreeDESceneModel│ PreviousShotsModel          │
│  │                  │                  │                  │          │
│  │ +background_load │ +scene_discovery │ +historical_track│          │
│  │ +refresh_strategy│ +incremental_merge │ +auto_migrate   │          │
│  │ +cache_management│ +deduplication   │ +cache_persistent│          │
│  └────────┬─────────┴────────┬─────────┴────────┬─────────┘          │
│           │                  │                  │                    │
│  ┌────────▼──────────────────▼──────────────────▼────────┐          │
│  │         BaseShotModel / BaseItemModel                 │          │
│  │  (Generic base classes for code reuse)                │          │
│  │  - Qt model protocol implementation                   │          │
│  │  - Signal/slot patterns                               │          │
│  │  - Caching integration                                │          │
│  └───────────────────────────────────────────────────────┘          │
└───────────────────────────────────────────────────────────────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────────────────────────────────────────────────────────────┐
│                  SYSTEM INTEGRATION LAYER                            │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ ProcessPoolManager (Singleton)                                  │ │
│  │ ├─ execute_workspace_command(cmd)  → ThreadPoolExecutor        │ │
│  │ ├─ Session Pool Management (Round-robin)                       │ │
│  │ ├─ CommandCache (Result Caching)                               │ │
│  │ └─ Metrics Tracking                                            │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ LauncherProcessManager (Process Lifecycle)                      │ │
│  │ ├─ execute_with_subprocess(cmd)                                │ │
│  │ ├─ execute_with_worker(cmd) → LauncherWorker (QThread)         │ │
│  │ ├─ Active Process Tracking                                     │ │
│  │ └─ Cleanup Scheduling                                          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │ CacheManager (Persistent Data Storage)                          │ │
│  │ ├─ Shots Cache (JSON) ← 30min TTL                               │ │
│  │ ├─ 3DE Scenes Cache (JSON) ← Persistent                        │ │
│  │ ├─ Previous Shots Cache (JSON) ← Persistent                    │ │
│  │ ├─ Thumbnails (JPG/PNG) ← File-based                           │ │
│  │ └─ Generic Data Cache (Key-Value TTL)                          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────────────────────────────────────────────────────────────┐
│               INFRASTRUCTURE LAYER                                   │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ VFX Environment Integration                                    │ │
│  │ ├─ Workspace Commands (ws -sg, ws -cwd, etc.)                 │ │
│  │ ├─ File System Access (3DE, plates, renders)                  │ │
│  │ ├─ Application Launchers (3DE, Nuke, Maya, RV)                │ │
│  │ └─ Environment Detection (Production/Mock)                    │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ Threading & Synchronization                                   │ │
│  │ ├─ Qt Main Thread (UI updates, signal emission)                │ │
│  │ ├─ Worker Threads (Background loading, filesystem scan)        │ │
│  │ ├─ Thread Pool (Workspace command execution)                   │ │
│  │ └─ Locks (RLock, Lock for synchronized access)                │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ Logging & Diagnostics                                          │ │
│  │ ├─ Application Logging (DEBUG_VERBOSE mode)                    │ │
│  │ ├─ Performance Metrics (Load time, cache hit rate)             │ │
│  │ ├─ Error Reporting (Exception details, stack traces)           │ │
│  │ └─ Command History (Executed commands, results)                │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 2. DATA FLOW DIAGRAMS

### 2.1 My Shots Loading Flow

```
┌─ User Interaction
│
├─ Click Tab "My Shots"
│  │
│  ▼
├─ MainWindow._on_tab_changed(index=0)
│  ├─ ShotModel.load_shots()
│  │  │
│  │  ├─ CacheManager.get_cached_shots()
│  │  │  ├─ Cache Hit (valid TTL) → Return cached data [100ms]
│  │  │  └─ Cache Miss → Continue to fetch
│  │  │
│  │  ├─ ProcessPoolManager.execute_workspace_command("ws -sg")
│  │  │  ├─ Check CommandCache → Return if cached [<1ms]
│  │  │  ├─ Round-robin select session from pool
│  │  │  ├─ Execute in ThreadPoolExecutor [100-500ms]
│  │  │  ├─ Cache result
│  │  │  └─ Return to caller
│  │  │
│  │  ├─ AsyncShotLoader (Background Thread)
│  │  │  ├─ optimized_shot_parser.parse_shots(ws_output) [50-200ms]
│  │  │  ├─ Create Shot objects with full metadata
│  │  │  └─ Emit: background_load_finished(List[Shot])
│  │  │
│  │  ├─ ShotModel._on_shots_loaded(shots)
│  │  │  ├─ Validate shot data
│  │  │  ├─ CacheManager.cache_shots(shots)
│  │  │  └─ Emit: background_load_finished(shots)
│  │  │
│  │  └─ MainWindow._on_shots_loaded(shots)
│  │     ├─ ShotItemModel.set_items(shots)
│  │     │  ├─ Clear old items
│  │     │  ├─ Set new items in model
│  │     │  ├─ Reset selection
│  │     │  └─ Batch update signal (debounced 100ms)
│  │     │
│  │     └─ ShotGridView
│  │        ├─ Update row count → rowCount = len(shots)
│  │        ├─ Request delegates for visible rows
│  │        └─ Layout grid with viewport optimization
│  │
│  └─ User sees "My Shots" grid populated [200-500ms]
│
├─ User Scrolls Grid
│  │
│  ├─ ShotGridView viewport change event
│  │  │
│  │  ├─ Calculate visible range
│  │  │  └─ GridLayout.indexAt(viewportRect) → [startRow, endRow]
│  │  │
│  │  ├─ BaseItemModel.set_visible_range(startRow, endRow)
│  │  │  ├─ Compare with last range
│  │  │  ├─ If different → Start debounce timer (100ms)
│  │  │  └─ Schedule: _do_load_visible_thumbnails()
│  │  │
│  │  └─ After debounce timeout
│  │     │
│  │     ├─ For each visible item i in [startRow, endRow]:
│  │     │  │
│  │     │  ├─ Check _pixmap_cache[i]
│  │     │  │  ├─ Hit → Use cached pixmap [<1ms]
│  │     │  │  └─ Miss → Continue
│  │     │  │
│  │     │  ├─ Check CacheManager.get_cached_thumbnail(shot)
│  │     │  │  ├─ Hit → Load from disk [10-50ms]
│  │     │  │  ├─ Add to _pixmap_cache[i]
│  │     │  │  └─ Miss → Continue
│  │     │  │
│  │     │  ├─ Load from source (shot.thumbnail_path)
│  │     │  │  ├─ Read file (JPEG, EXR, PIL format) [50-200ms]
│  │     │  │  ├─ Decode image
│  │     │  │  ├─ Scale to THUMBNAIL_SIZE (256x256)
│  │     │  │  └─ Convert to QPixmap
│  │     │  │
│  │     │  ├─ CacheManager.cache_thumbnail(shot, pixmap)
│  │     │  │  ├─ Save to disk cache (~50KB/image)
│  │     │  │  └─ Update cache metadata
│  │     │  │
│  │     │  ├─ _pixmap_cache[i] = pixmap
│  │     │  │
│  │     │  └─ Emit: thumbnail_loaded(index)
│  │     │     └─ Trigger dataChanged for index
│  │     │
│  │     └─ Batch emit: items_updated (collected in 100ms window)
│  │
│  └─ ShotGridView._on_items_updated()
│     ├─ Invalidate item rects
│     ├─ Request paint for affected delegate indices
│     ├─ ShotGridDelegate.paint(painter, option, index)
│     │  ├─ Retrieve pixmap from BaseItemModel.data(DisplayRole)
│     │  ├─ Render pixmap with overlay (shot name, path)
│     │  └─ Paint focus rectangle if selected
│     │
│     └─ User sees thumbnails loaded as scrolls
│
└─ User Clicks Shot
   │
   ├─ ShotGridView.clicked(index)
   │  │
   │  ├─ ShotItemModel.setData(index, selected, SelectionRole)
   │  │
   │  ├─ BaseItemModel.selection_changed(index)
   │  │  ├─ _selected_index = index
   │  │  ├─ _selected_item = self._items[index]
   │  │  └─ Emit: selection_changed(shot)
   │  │
   │  └─ MainWindow._on_shot_selected(shot)
   │     ├─ LauncherController.set_current_shot(shot)
   │     │  └─ Store reference to shot
   │     │
   │     ├─ ShotInfoPanel.update_from_shot(shot)
   │     │  ├─ Show shot name, path, sequence
   │     │  ├─ Show shot geometry info
   │     │  └─ Show available apps for this shot
   │     │
   │     ├─ LauncherPanel.update_available_apps()
   │     │  ├─ Get apps from config for shot type
   │     │  ├─ Enable/disable buttons based on availability
   │     │  └─ Refresh custom launcher buttons
   │     │
   │     ├─ _update_tab_accent_color() (Visual feedback)
   │     │
   │     └─ LauncherController.update_launcher_menu()
   │        ├─ Get launch options for shot
   │        └─ Update Tools menu with available launchers
   │
   └─ User sees shot details & launcher buttons enabled
```

### 2.2 Application Launch Flow

```
User Clicks "Launch 3DE" Button
│
├─ LauncherPanel.on_launch_3de_clicked()
│  │
│  └─ MainWindow.launch_app("3DE")
│     │
│     ├─ LauncherController.launch_app("3DE")
│     │  │
│     │  ├─ Get current shot: shot = self._current_shot
│     │  │
│     │  ├─ Build launch command
│     │  │  ├─ Get launcher config for "3DE" from settings
│     │  │  ├─ Construct workspace cd command
│     │  │  │  └─ cd_cmd = f"ws -cd {shot.workspace_path}"
│     │  │  │
│     │  │  ├─ Construct app launch command
│     │  │  │  └─ app_cmd = f"3de {scene_path} &"
│     │  │  │
│     │  │  └─ Combine: final_cmd = f"{cd_cmd} && {app_cmd}"
│     │  │
│     │  ├─ Emit: launcher_started(launcher_id)
│     │  │
│     │  └─ LauncherProcessManager.execute_with_worker(final_cmd)
│     │     │
│     │     ├─ Generate unique process_key
│     │     │
│     │     ├─ Create LauncherWorker (QThread)
│     │     │  ├─ moveToThread(worker_thread)
│     │     │  └─ Connect signals to slots
│     │     │
│     │     ├─ Store in _active_workers[worker_id] = worker
│     │     │
│     │     ├─ Emit: worker_created(worker_id)
│     │     │
│     │     └─ worker.do_work()
│     │        │
│     │        ├─ LauncherWorker._sanitize_command()
│     │        │  ├─ Validate command syntax
│     │        │  ├─ Escape special characters
│     │        │  └─ Check for dangerous patterns
│     │        │
│     │        ├─ Popen(command, cwd=None, shell=True, stdout=PIPE, stderr=PIPE)
│     │        │  └─ External application starts
│     │        │
│     │        ├─ Emit: command_started(launcher_id)
│     │        │
│     │        ├─ Wait for process completion
│     │        │  └─ poll() in loop until returncode != None
│     │        │
│     │        ├─ Capture stdout/stderr
│     │        │
│     │        ├─ Create CommandResult
│     │        │  ├─ returncode
│     │        │  ├─ stdout
│     │        │  ├─ stderr
│     │        │  └─ execution_time
│     │        │
│     │        ├─ Emit: command_finished(result)
│     │        │
│     │        └─ LauncherWorker._cleanup_process()
│     │           ├─ Close process pipes
│     │           ├─ Release resources
│     │           └─ Mark process completed
│     │
│     ├─ LauncherProcessManager._on_worker_finished(worker_id, result)
│     │  ├─ Emit: process_finished(process_key, result)
│     │  │
│     │  ├─ Schedule cleanup
│     │  │  └─ _cleanup_finished_workers() in CLEANUP_INTERVAL_MS
│     │  │
│     │  └─ Store result for history
│     │
│     └─ LauncherController._on_launcher_finished(result)
│        │
│        ├─ Extract command output
│        │
│        ├─ LogViewer.append_log(result)
│        │  ├─ Format command output
│        │  ├─ Color code based on exit code
│        │  ├─ Append to log text
│        │  └─ Scroll to bottom
│        │
│        └─ If failed:
│           ├─ Show error dialog to user
│           ├─ Log failure in cache
│           └─ Offer to retry or debug
│
└─ User sees result in LogViewer
   Application launched or error reported
```

### 2.3 Refresh Orchestration Flow

```
Periodic Refresh Timer OR User Clicks Refresh Button
│
├─ RefreshOrchestrator.trigger_refresh()
│  │
│  ├─ Emit: refresh_started
│  │
│  ├─ ShotModel.refresh_strategy()
│  │  │
│  │  ├─ Load fresh shots from workspace
│  │  │  └─ ProcessPoolManager.execute_workspace_command("ws -sg")
│  │  │
│  │  ├─ Compare with cached
│  │  │  ├─ new_shots = {shot.name: shot for shot in fresh}
│  │  │  ├─ old_shots = {shot.name: shot for shot in cached}
│  │  │  ├─ added = set(new_shots.keys()) - set(old_shots.keys())
│  │  │  ├─ removed = set(old_shots.keys()) - set(new_shots.keys())
│  │  │  └─ changed = [s for s in new_shots if old_shots[s] != s]
│  │  │
│  │  ├─ CacheManager.cache_shots(fresh_shots)
│  │  │
│  │  └─ Emit: background_load_finished(fresh, changes)
│  │     └─ MainWindow._on_shots_changed(shots, has_changes)
│  │
│  ├─ ThreeDESceneModel.refresh()
│  │  │
│  │  ├─ ThreeDESceneWorker (Background Thread)
│  │  │  │
│  │  │  ├─ threede_scene_finder.find_all_scenes()
│  │  │  │  ├─ os.walk(search_paths)
│  │  │  │  ├─ Find *.3de files
│  │  │  │  ├─ Parse scene metadata
│  │  │  │  └─ Return: List[ThreeDEScene]
│  │  │  │
│  │  │  ├─ CacheManager.get_persistent_threede_scenes()
│  │  │  │  └─ Load cache without TTL check
│  │  │  │
│  │  │  ├─ CacheManager.merge_scenes_incremental(cached, fresh)
│  │  │  │  ├─ Start with cached scenes (preserve history)
│  │  │  │  ├─ For each fresh scene
│  │  │  │  │  ├─ If not in cache → add
│  │  │  │  │  └─ If in cache → keep newer by mtime
│  │  │  │  └─ Return merged list
│  │  │  │
│  │  │  ├─ Deduplication by shot key
│  │  │  │  ├─ Group by (show, sequence, shot)
│  │  │  │  ├─ For each group, keep scene with highest priority
│  │  │  │  │  ├─ Prefer "plate" scenes if available
│  │  │  │  │  └─ Otherwise newest by mtime
│  │  │  │  └─ Return deduplicated list
│  │  │  │
│  │  │  ├─ CacheManager.cache_threede_scenes(merged)
│  │  │  │
│  │  │  └─ Emit: scenes_changed(merged_scenes)
│  │  │     └─ MainWindow: Update 3DE grid
│  │  │
│  │  └─ Return to main thread via signal
│  │
│  ├─ PreviousShotsModel.refresh()
│  │  │
│  │  ├─ Query approved/completed shots
│  │  │
│  │  ├─ Filter out current shots (in ShotModel)
│  │  │
│  │  ├─ CacheManager.cache_previous_shots(filtered)
│  │  │
│  │  └─ Emit: previous_shots_updated(shots)
│  │     └─ MainWindow: Update Previous grid
│  │
│  ├─ MainWindow._on_tab_changed() [if on active tab]
│  │  └─ Update visible grid with new data
│  │
│  ├─ MainWindow._update_status()
│  │  └─ Show refresh result: "Loaded 47 shots (3 new, 1 removed)"
│  │
│  └─ Emit: refresh_finished(success, has_changes)
│
└─ Refresh complete, UI updated with latest data
```

---

## 3. COMPONENT INTERACTION DIAGRAMS

### 3.1 Signal Flow Architecture

```
SIGNAL PRODUCERS (Models)        SIGNAL ROUTING (MainWindow)      CONSUMERS (UI)
═════════════════════════        ═════════════════════════        ══════════════

ShotModel                                                   
  ├─ background_load_finished ────┐                                  
  ├─ shots_changed ────────────────┤                              ShotGridView
  └─ load_error ───────────────────┼──▶ MainWindow ───────────────┤ (Receives items)
                                   │   (Coordinates)               │
ThreeDESceneModel                  │    - _on_shots_loaded()      ShotItemModel
  ├─ scenes_changed ──────────────┤    - _on_shots_changed()     │ (Qt Model)
  ├─ refresh_started ─────────────┼─▶  - _on_tab_changed()       │
  └─ refresh_finished ────────────┤    - _apply_show_filter()    ShotInfoPanel
                                   │                              │
PreviousShotsModel                 │                          LauncherPanel
  ├─ previous_shots_updated ───────┤                              │
  ├─ refresh_finished ────────────┤                          LogViewer
  └─ load_error ───────────────────┤                              │
                                   │                          StatusBar
CacheManager                       │                              │
  ├─ cache_updated ───────────────┤                              
  └─ shots_migrated ──────────────┤                              
                                   │                          
LauncherProcessManager             │                          
  ├─ process_started ─────────────┤                          
  ├─ process_finished ────────────┼──▶ LauncherController    
  ├─ process_error ───────────────┤    (Models controller)    
  ├─ worker_created ──────────────┤    - _on_launcher_finished()  LogViewer
  └─ worker_removed ──────────────┤                              │
                                                                  │
                                                            StatusBar
```

### 3.2 Dependency Injection Patterns

```
PRODUCTION SETUP                          TEST SETUP
════════════════════                      ══════════════════

ProcessPoolManager (Singleton)      MockProcessPoolManager
  ├─ Real subprocess pool                ├─ Returns pre-set results
  └─ Real file system access             └─ Configurable responses

    ▼                                       ▼
CacheManager                        MockCacheManager
  ├─ Real file I/O                       ├─ In-memory storage
  └─ Real JSON serialization             └─ No disk access

    ▼                                       ▼
ShotModel                           ShotModel
  ├─ Uses pool & cache                   ├─ Uses mocks
  └─ Produces signals                    └─ Same interface

    ▼                                       ▼
MainWindow                          MainWindow (TestWindow)
  ├─ Coordinates everything              ├─ Same UI
  └─ Connects signals                    └─ Tests verify signals
```

### 3.3 Threading Model

```
MAIN THREAD (Qt Event Loop)                WORKER THREADS
═════════════════════════════              ══════════════════════

MainWindow
  ├─ Handle user input
  ├─ Emit user signals
  └─ Update UI
      │
      ├─▶ ShotItemModel
      │   └─ Qt model updates
      │       │
      │       └─▶ ShotGridView
      │           └─ Render & paint
      │
      ├─▶ ShotGridView scroll event
      │   └─ Request visible range
      │       │
      │       └─▶ BaseItemModel
      │           ├─ Check memory cache
      │           │
      │           └─▶ ASYNC: Load thumbnail
      │                  ├─ Check disk cache
      │                  └─ Load from source
      │                      │
      │                      ├─▶ Emit: thumbnail_loaded
      │                      │   (Back to main thread)
      │
      ├─▶ LauncherPanel click
      │   └─ LauncherController.launch_app()
      │       │
      │       └─▶ LauncherProcessManager
      │           │
      │           └─▶ WORKER: LauncherWorker (QThread)
      │                  ├─ Execute command
      │                  ├─ Monitor process
      │                  │
      │                  └─▶ Emit: command_finished
      │                      (Back to main thread)
      │
      └─▶ Refresh button
          └─ RefreshOrchestrator
              │
              ├─▶ WORKER: AsyncShotLoader
              │      ├─ ProcessPoolManager
              │      │  └─▶ ThreadPoolExecutor
              │      │      └─ Workspace command
              │      │
              │      └─▶ Emit: background_load_finished
              │          (Back to main thread)
              │
              └─▶ WORKER: ThreeDESceneWorker
                     ├─ Filesystem scan
                     ├─ Parse scenes
                     │
                     └─▶ Emit: scenes_changed
                         (Back to main thread)
```

---

## 4. STATE MACHINES

### 4.1 ShotModel Lifecycle

```
        ┌─────────────────────┐
        │   UNINITIALIZED     │
        │ (Created but empty) │
        └──────────┬──────────┘
                   │
              initialize_async()
                   │
                   ▼
        ┌─────────────────────┐
        │  LOADING_INITIAL    │ ──emit──▶ background_load_started
        │ (Async load from WS)│
        └──────────┬──────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
    [Success]            [Failure]
        │                     │
        ▼                     ▼
┌─────────────────────┐  ┌──────────────────┐
│   SHOTS_LOADED      │  │   LOAD_ERROR     │
│ (Data available)    │  │ (Error state)    │
└──────────┬──────────┘  └──────────┬───────┘
           │                        │
    ┌──────▼────────┐        retry_load()
    │               │          │
emit: refresh_strategy()  [Success]
shots_changed()           │
    │                     ▼
    └───────────────────→ SHOTS_LOADED
           
In SHOTS_LOADED:
    ├─ Can call refresh_shots_sync()
    │  └─ Fetches fresh data, emits shots_changed()
    │
    ├─ Can call get_shot_by_name(name)
    │  └─ Returns Shot or None
    │
    ├─ Can call select_shot_by_name(name)
    │  └─ Updates selection
    │
    └─ Background refresh can trigger
       ├─ Emit: background_load_started
       ├─ Fetch fresh data
       └─ Emit: background_load_finished(shots)
```

### 4.2 LauncherWorker Lifecycle

```
        ┌──────────────────┐
        │   CREATED        │
        │ (In thread pool) │
        └────────┬─────────┘
                 │
            do_work() signal
                 │
                 ▼
        ┌──────────────────┐
        │  EXECUTING       │ ──emit──▶ command_started
        │ (Running process)│
        └────────┬─────────┘
                 │
         ┌───────┴────────┐
         │                │
    [Success]        [Exception/Timeout]
         │                │
         ▼                ▼
┌──────────────────┐ ┌──────────────────┐
│  COMPLETED       │ │  ERROR           │
│ (Process ended)  │ │ (Failed to exec) │
└────────┬─────────┘ └────────┬─────────┘
         │                    │
    ┌────▼────────────────────▼────┐
    │                              │
emit: command_finished(result)     │
emit: command_error(error)         │
    │                              │
    └──────────────┬───────────────┘
                   │
           _cleanup_process()
                   │
                   ▼
        ┌──────────────────┐
        │  CLEANED_UP      │
        │ (Resources freed)│
        └────────┬─────────┘
                 │
          request_stop()
                 │
                 ▼
        ┌──────────────────┐
        │  STOPPED         │
        │ (Thread finished)│
        └──────────────────┘
```

---

## 5. CACHE ARCHITECTURE

```
CACHE HIERARCHY
═══════════════

Request for Thumbnail
  │
  ├─ Level 1: Memory Cache (_pixmap_cache)
  │   │
  │   ├─ Hit (≤1ms) → Return immediately
  │   └─ Miss → Continue
  │
  ├─ Level 2: Disk Cache (CacheManager.thumbnails/)
  │   │
  │   ├─ Hit (10-50ms) → Load into memory → Return
  │   └─ Miss → Continue
  │
  └─ Level 3: Source File (shot.thumbnail_path)
      │
      ├─ Load (50-200ms)
      ├─ Decode (JPEG/EXR/PIL)
      ├─ Scale to size
      ├─ Save to disk cache
      ├─ Cache in memory
      └─ Return


CACHE INVALIDATION STRATEGY
═══════════════════════════

Memory Cache:
  ├─ Time-based: Kept while visible
  ├─ Event-based: Cleared on tab change
  └─ Limit: Only visible + buffer

Disk Cache:
  ├─ Time-based: Never expires automatically
  ├─ Event-based: Cleared on user request
  └─ Cleanup: Managed by OS (LRU eviction)

JSON Caches (Shots/Scenes):
  ├─ Time-based: 30min for shots, none for scenes
  ├─ Event-based: Cleared on refresh
  └─ Merge: Incremental on each update


CACHE CONSISTENCY
═════════════════

Single Truth Source: ProcessPoolManager (for commands)
  ├─ Caches workspace command results
  ├─ TTL managed per cache type
  └─ Invalidation via invalidate_cache()

Derived Cache: CacheManager
  ├─ Built from command results
  ├─ May differ if data changed
  └─ Refreshed on user action

Application Memory:
  ├─ Loaded from CacheManager
  ├─ Displayed to user
  └─ May be stale until refresh

Strategy: Eventual Consistency
  ├─ Data eventually consistent with source
  ├─ Refreshes happen periodically
  └─ User can manually refresh
```

---

## 6. ERROR HANDLING FLOW

```
Command Execution
  │
  ├─ LauncherWorker.do_work()
  │  │
  │  ├─ Popen(command)
  │  │  │
  │  │  ├─ OSError (command not found)
  │  │  │  └─ Catch → Emit command_error
  │  │  │
  │  │  ├─ Process runs
  │  │  │  │
  │  │  │  ├─ Exit code == 0 → Success
  │  │  │  │
  │  │  │  └─ Exit code != 0 → Soft failure
  │  │  │     └─ Include stderr in result
  │  │  │
  │  │  └─ Timeout exception
  │  │     └─ Catch → Emit command_error
  │  │
  │  └─ Emit: command_finished(result)
  │     ├─ returncode
  │     ├─ stdout
  │     └─ stderr
  │
  ├─ LauncherProcessManager._on_worker_finished()
  │  │
  │  ├─ Check if success (returncode == 0)
  │  │  ├─ Yes → Log successful execution
  │  │  └─ No → Log error but don't crash
  │  │
  │  └─ Schedule cleanup
  │
  └─ LauncherController._on_launcher_finished()
     │
     ├─ Parse result
     ├─ LogViewer.append_log(result)
     │  ├─ Format output
     │  └─ Color code (green=success, red=error)
     │
     └─ If error:
        ├─ Show status: "Launch failed: {stderr}"
        └─ Offer user: [Retry] [Debug] [OK]


Cache Loading Error
  │
  ├─ CacheManager._read_json_cache()
  │  │
  │  ├─ File not found → Return empty data structure
  │  │
  │  ├─ JSON parse error
  │  │  ├─ Log: "Cache corrupted: {file}"
  │  │  └─ Return empty data structure
  │  │
  │  └─ Return parsed data
  │
  └─ Application continues with empty/default data


Model Load Error
  │
  ├─ ShotModel.initialize_async()
  │  │
  │  ├─ ProcessPoolManager.execute_workspace_command()
  │  │  │
  │  │  ├─ Workspace not found → Emit load_failed
  │  │  │
  │  │  └─ Command execution error → Emit load_failed
  │  │
  │  └─ Main thread receives signal
  │
  ├─ MainWindow._on_shot_error()
  │  │
  │  ├─ Check error type
  │  │  ├─ WORKSPACE_NOT_FOUND
  │  │  │  └─ Show: "Workspace not available. Running in mock mode."
  │  │  │
  │  │  └─ COMMAND_FAILED
  │  │     └─ Show: "Failed to load shots: {error}"
  │  │
  │  └─ Can offer [Retry] [Switch to Mock] [Report]
  │
  └─ UI shows error gracefully, application doesn't crash
```

---

## 7. KEY PERFORMANCE METRICS

```
LOADING PERFORMANCE
═══════════════════

Startup (First Load):
  ├─ ProcessPoolManager init: 100-200ms
  │  └─ Create thread pool
  │
  ├─ ShotModel initialize: 100-500ms
  │  ├─ Execute ws -sg: 200-400ms
  │  └─ Parse shots: 50-100ms
  │
  ├─ UI setup: 50-100ms
  │  └─ Create widgets/delegates
  │
  └─ Total: 250-800ms


Cache Hit (Subsequent Load):
  ├─ CacheManager.get_cached_shots(): <1ms
  │  └─ Validation: <1ms
  │
  ├─ ShotItemModel.set_items(): 10-50ms
  │  └─ Qt model update
  │
  └─ Total: <100ms


Thumbnail Loading:
  ├─ Memory cache hit: <1ms
  ├─ Disk cache hit: 10-50ms
  │  └─ File I/O + decode
  │
  ├─ Source load: 50-200ms
  │  ├─ Read file: 20-100ms
  │  ├─ Decode: 10-50ms
  │  ├─ Scale: 5-10ms
  │  └─ Save to cache: 10-30ms
  │
  └─ Viewport load (20 items): 200-500ms (mostly parallel)


MEMORY USAGE
════════════

Typical Session:
  ├─ Base (Models + UI): 50-100MB
  ├─ Loaded shots (500): 10-20MB
  │  └─ Metadata per shot: ~20KB
  │
  ├─ Cached thumbnails (30 visible): 30-50MB
  │  └─ ~1MB per 256x256 pixmap
  │
  ├─ Disk cache: 500MB-2GB
  │  └─ Depends on # of shots
  │
  └─ Total RAM: 100-150MB


CACHE HIT RATES
═══════════════

Typical Usage Pattern:
  ├─ Command cache: 70-90% hit rate
  │  (Same commands executed frequently)
  │
  ├─ Thumbnail memory cache: 50-80% hit rate
  │  (User scrolls back to visible items)
  │
  ├─ Thumbnail disk cache: 95%+ hit rate
  │  (Once loaded, stays on disk)
  │
  └─ Model data cache: 60-80% hit rate
     (Data changes periodically)
```

This comprehensive architecture documentation provides a complete map of Shotbot's design, with clear diagrams showing how components interact and flow of data through the system.
