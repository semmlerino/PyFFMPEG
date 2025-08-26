# Test Performance Optimization Report

Total issues found: 131

## Issues by Type
- time.sleep() calls: 31
- Excessive timeouts (>2000ms): 14
- Unnecessary waits: 86
- Missing @pytest.mark.slow: 0

## Recommended Fixes by File

## test_doubles_library.py
  - Line 103: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 182: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 197: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 571: Replace time.sleep() with qtbot.wait() or signal wait

## test_cache_integration.py
  - Line 303: Replace time.sleep() with qtbot.wait() or signal wait

## test_performance_benchmarks.py
  - Line 377: Replace time.sleep() with qtbot.wait() or signal wait

## test_threede_optimization_coverage.py
  - Line 75: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 136: Replace time.sleep() with qtbot.wait() or signal wait

## test_threede_optimization_coverage_fixed.py
  - Line 97: Replace time.sleep() with qtbot.wait() or signal wait

## test_threading_fixes.py
  - Line 4: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 10: Use waitSignal() or remove if not needed
  - Line 134: Use waitSignal() or remove if not needed
  - Line 425: Use waitSignal() or remove if not needed

## test_doubles.py
  - Line 175: Replace time.sleep() with qtbot.wait() or signal wait

## test_example_best_practices.py
  - Line 211: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 216: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 229: Replace time.sleep() with qtbot.wait() or signal wait

## test_launcher_dialog.py
  - Line 9: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 210: Use waitSignal() or remove if not needed
  - Line 227: Use waitSignal() or remove if not needed
  - Line 243: Use waitSignal() or remove if not needed
  - Line 265: Use waitSignal() or remove if not needed
  - Line 330: Use waitSignal() or remove if not needed
  - Line 342: Use waitSignal() or remove if not needed
  - Line 358: Use waitSignal() or remove if not needed
  - Line 373: Use waitSignal() or remove if not needed
  - Line 384: Use waitSignal() or remove if not needed
  - Line 397: Use waitSignal() or remove if not needed
  - Line 413: Use waitSignal() or remove if not needed
  - Line 429: Use waitSignal() or remove if not needed
  - Line 450: Use waitSignal() or remove if not needed
  - Line 464: Use waitSignal() or remove if not needed
  - Line 648: Use waitSignal() or remove if not needed
  - Line 664: Use waitSignal() or remove if not needed
  - Line 686: Use waitSignal() or remove if not needed
  - Line 714: Use waitSignal() or remove if not needed
  - Line 731: Use waitSignal() or remove if not needed
  - Line 775: Use waitSignal() or remove if not needed
  - Line 779: Use waitSignal() or remove if not needed
  - Line 788: Use waitSignal() or remove if not needed
  - Line 795: Use waitSignal() or remove if not needed
  - Line 803: Use waitSignal() or remove if not needed
  - Line 811: Use waitSignal() or remove if not needed
  - Line 861: Use waitSignal() or remove if not needed

## test_launcher_manager_coverage.py
  - Line 162: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 197: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 200: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 212: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 215: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 1093: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 1096: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 1133: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 1135: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 1234: Replace time.sleep() with qtbot.wait() or signal wait

## test_launcher_manager_coverage_refactored.py
  - Line 137: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 216: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 381: Use waitSignal() or remove if not needed

## test_launcher_manager_refactored.py
  - Line 248: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 471: Use waitSignal() or remove if not needed

## test_log_viewer.py
  - Line 7: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 175: Use waitSignal() or remove if not needed

## test_previous_shots_worker_fixed.py
  - Line 138: Reduce timeout to 1000ms or less
  - Line 160: Replace time.sleep() with qtbot.wait() or signal wait
  - Line 195: Reduce timeout to 1000ms or less
  - Line 391: Reduce timeout to 1000ms or less
  - Line 450: Reduce timeout to 1000ms or less
  - Line 478: Reduce timeout to 1000ms or less

## test_thumbnail_processor_thread_safety.py
  - Line 521: Replace time.sleep() with qtbot.wait() or signal wait

## test_user_workflows.py
  - Line 236: Use waitSignal() or remove if not needed
  - Line 313: Use waitSignal() or remove if not needed
  - Line 385: Reduce timeout to 1000ms or less
  - Line 480: Use waitSignal() or remove if not needed
  - Line 542: Use waitSignal() or remove if not needed
  - Line 643: Reduce timeout to 1000ms or less
  - Line 710: Use waitSignal() or remove if not needed
  - Line 735: Use waitSignal() or remove if not needed
  - Line 811: Use waitSignal() or remove if not needed
  - Line 830: Use waitSignal() or remove if not needed
  - Line 847: Use waitSignal() or remove if not needed
  - Line 931: Reduce timeout to 1000ms or less
  - Line 1034: Use waitSignal() or remove if not needed
  - Line 1066: Use waitSignal() or remove if not needed

## test_cache_manager.py
  - Line 585: Reduce timeout to 1000ms or less

## test_previous_shots_worker.py
  - Line 151: Reduce timeout to 1000ms or less
  - Line 185: Reduce timeout to 1000ms or less
  - Line 228: Use waitSignal() or remove if not needed
  - Line 253: Reduce timeout to 1000ms or less
  - Line 287: Reduce timeout to 1000ms or less
  - Line 405: Reduce timeout to 1000ms or less

## test_main_window_coordination.py
  - Line 109: Use waitSignal() or remove if not needed
  - Line 121: Use waitSignal() or remove if not needed
  - Line 125: Use waitSignal() or remove if not needed
  - Line 132: Use waitSignal() or remove if not needed
  - Line 182: Use waitSignal() or remove if not needed
  - Line 199: Use waitSignal() or remove if not needed
  - Line 242: Use waitSignal() or remove if not needed
  - Line 271: Use waitSignal() or remove if not needed
  - Line 279: Use waitSignal() or remove if not needed
  - Line 313: Use waitSignal() or remove if not needed
  - Line 338: Use waitSignal() or remove if not needed

## test_main_window_widgets.py
  - Line 111: Use waitSignal() or remove if not needed
  - Line 177: Use waitSignal() or remove if not needed
  - Line 192: Use waitSignal() or remove if not needed
  - Line 236: Use waitSignal() or remove if not needed
  - Line 253: Use waitSignal() or remove if not needed
  - Line 316: Use waitSignal() or remove if not needed
  - Line 320: Use waitSignal() or remove if not needed
  - Line 336: Use waitSignal() or remove if not needed
  - Line 340: Use waitSignal() or remove if not needed
  - Line 352: Use waitSignal() or remove if not needed
  - Line 356: Use waitSignal() or remove if not needed
  - Line 387: Use waitSignal() or remove if not needed
  - Line 403: Use waitSignal() or remove if not needed
  - Line 417: Use waitSignal() or remove if not needed
  - Line 427: Use waitSignal() or remove if not needed
  - Line 482: Use waitSignal() or remove if not needed
  - Line 494: Use waitSignal() or remove if not needed
  - Line 520: Use waitSignal() or remove if not needed
  - Line 533: Use waitSignal() or remove if not needed

## test_previous_shots_grid.py
  - Line 294: Use waitSignal() or remove if not needed
  - Line 297: Use waitSignal() or remove if not needed

## test_thumbnail_widget_qt.py
  - Line 104: Use waitSignal() or remove if not needed
  - Line 118: Use waitSignal() or remove if not needed
  - Line 133: Use waitSignal() or remove if not needed
  - Line 262: Use waitSignal() or remove if not needed
  - Line 277: Use waitSignal() or remove if not needed
  - Line 291: Use waitSignal() or remove if not needed
  - Line 318: Use waitSignal() or remove if not needed
  - Line 322: Use waitSignal() or remove if not needed
  - Line 435: Use waitSignal() or remove if not needed
  - Line 451: Use waitSignal() or remove if not needed

## Quick Wins
1. Replace all time.sleep() with proper synchronization
2. Reduce all timeouts to 1000ms or less
3. Mark slow tests with @pytest.mark.slow
4. Use -m 'not slow' to skip slow tests during development
