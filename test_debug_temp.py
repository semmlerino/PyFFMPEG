from cache_manager import CacheManager
from config import Config
from main_window import MainWindow


def test_process_pool_calls(qtbot, test_process_pool, tmp_path):
    """Debug test to see when execute_workspace_command is called."""
    cache_manager = CacheManager(cache_dir=tmp_path / "cache")

    # Check initial state
    print(f"\nBefore MainWindow: call_count={test_process_pool.call_count}, queue={len(test_process_pool._outputs_queue)}")

    main_window = MainWindow(cache_manager=cache_manager)
    qtbot.addWidget(main_window)

    # Check after MainWindow creation
    print(f"After MainWindow: call_count={test_process_pool.call_count}, queue={len(test_process_pool._outputs_queue)}")
    print(f"Commands called: {test_process_pool.commands}")

    # Configure outputs
    shows_root = Config.SHOWS_ROOT
    test_process_pool.set_outputs(f"workspace {shows_root}/test/shots/seq01/seq01_0010")

    print(f"After set_outputs: call_count={test_process_pool.call_count}, queue={len(test_process_pool._outputs_queue)}")

    # Call refresh
    main_window._refresh_shots()

    print(f"After refresh: call_count={test_process_pool.call_count}, queue={len(test_process_pool._outputs_queue)}")
    print(f"Commands called: {test_process_pool.commands}")
    print(f"Shots loaded: {len(main_window.shot_model.shots)}")
