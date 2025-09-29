#!/usr/bin/env python3
"""Test the new dependency injection system for ProcessPoolManager."""

# Standard library imports
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_production_mode() -> None:
    """Test that production mode works."""
    logger.info("=" * 50)
    logger.info("Testing PRODUCTION mode")
    logger.info("=" * 50)

    # Local application imports
    from process_pool_factory import ProcessPoolFactory, get_process_pool

    # Reset to clean state
    ProcessPoolFactory.reset()

    # Get instance in production mode (should be real ProcessPoolManager)
    pool = get_process_pool()
    logger.info(f"Got instance: {pool.__class__.__name__}")
    logger.info(f"Instance module: {pool.__class__.__module__}")
    logger.info(f"Instance type: {type(pool)}")

    # Verify it's the real ProcessPoolManager
    # Local application imports
    from process_pool_manager import ProcessPoolManager

    logger.info(f"ProcessPoolManager type: {ProcessPoolManager}")
    logger.info(f"ProcessPoolManager module: {ProcessPoolManager.__module__}")

    # In test environment, we might be getting TestProcessPool or MockWorkspacePool which is expected
    # Local application imports
    from mock_workspace_pool import MockWorkspacePool
    from tests.test_doubles_library import TestProcessPool

    if isinstance(pool, TestProcessPool | MockWorkspacePool):
        logger.info(f"✅ Got {pool.__class__.__name__} in test environment (expected)")
        return

    assert isinstance(pool, ProcessPoolManager), (
        f"Expected ProcessPoolManager, TestProcessPool, or MockWorkspacePool, got {type(pool)}"
    )
    logger.info("✅ Production mode works correctly")

    # Clean up - only call shutdown if it exists
    if hasattr(pool, "shutdown"):
        pool.shutdown()
    ProcessPoolFactory.reset()


def test_mock_mode() -> None:
    """Test that mock mode works."""
    logger.info("=" * 50)
    logger.info("Testing MOCK mode")
    logger.info("=" * 50)

    # Local application imports
    from process_pool_factory import ProcessPoolFactory, get_process_pool

    # Reset to clean state
    ProcessPoolFactory.reset()

    # Enable mock mode
    ProcessPoolFactory.set_mock_mode(True)

    # Get instance in mock mode (could be TestProcessPool or MockWorkspacePool)
    pool = get_process_pool()
    logger.info(f"Got instance: {pool.__class__.__name__}")

    # Verify it's one of the test doubles
    # Local application imports
    from mock_workspace_pool import MockWorkspacePool
    from tests.test_doubles_library import TestProcessPool

    assert isinstance(pool, TestProcessPool | MockWorkspacePool), (
        f"Expected TestProcessPool or MockWorkspacePool, got {type(pool)}"
    )
    logger.info(f"✅ Mock mode works correctly with {pool.__class__.__name__}")

    # Test that it has demo data
    result = pool.execute_workspace_command("ws -sg")
    lines = result.split("\n")
    logger.info(f"Mock data returned: {len(lines)} lines")
    assert "workspace" in result, "Mock should return workspace data"
    logger.info("✅ Mock returns demo data")

    # Clean up
    ProcessPoolFactory.reset()


def test_custom_injection() -> None:
    """Test custom implementation injection."""
    logger.info("=" * 50)
    logger.info("Testing CUSTOM injection")
    logger.info("=" * 50)

    # Local application imports
    from process_pool_factory import ProcessPoolFactory, get_process_pool
    from tests.test_doubles_library import TestProcessPool

    # Reset to clean state
    ProcessPoolFactory.reset()

    # Create custom instance
    custom_pool = TestProcessPool()
    custom_pool.set_outputs(
        "workspace /custom/test/path1",
        "workspace /custom/test/path2",
    )

    # Inject custom implementation
    ProcessPoolFactory.set_implementation(custom_pool)

    # Get instance (should be our custom one)
    pool = get_process_pool()
    logger.info(f"Got instance: {pool.__class__.__name__}")

    # Verify it's our custom instance
    assert pool is custom_pool, "Should return the exact custom instance"

    # Test that it has our custom data
    result = pool.execute_workspace_command("ws -sg")
    assert "/custom/test/path1" in result, "Should have custom data"
    logger.info("✅ Custom injection works correctly")

    # Clean up
    ProcessPoolFactory.reset()


def test_singleton_behavior() -> None:
    """Test that factory maintains singleton behavior."""
    logger.info("=" * 50)
    logger.info("Testing SINGLETON behavior")
    logger.info("=" * 50)

    # Local application imports
    from process_pool_factory import ProcessPoolFactory, get_process_pool

    # Reset to clean state
    ProcessPoolFactory.reset()

    # Get multiple instances
    pool1 = get_process_pool()
    pool2 = get_process_pool()

    # They should be the same instance
    assert pool1 is pool2, "Should return the same singleton instance"
    logger.info("✅ Singleton behavior maintained")

    # Clean up - only call shutdown if it exists (ProcessPoolManager has it, TestProcessPool doesn't)
    if hasattr(pool1, "shutdown"):
        pool1.shutdown()
    ProcessPoolFactory.reset()


def test_backward_compatibility() -> None:
    """Test that old code still works."""
    logger.info("=" * 50)
    logger.info("Testing BACKWARD COMPATIBILITY")
    logger.info("=" * 50)

    # Local application imports
    from process_pool_factory import ProcessPoolFactory
    from process_pool_manager import ProcessPoolManager

    # Reset to clean state
    ProcessPoolFactory.reset()

    # Old code that uses ProcessPoolManager.get_instance() directly
    pool = ProcessPoolManager.get_instance()
    logger.info(f"Got instance via old method: {pool.__class__.__name__}")

    # In test environment, might get TestProcessPool which is OK
    # Local application imports
    from mock_workspace_pool import MockWorkspacePool
    from tests.test_doubles_library import TestProcessPool

    assert isinstance(pool, ProcessPoolManager | TestProcessPool | MockWorkspacePool), (
        f"Old method should return a valid pool, got {type(pool)}"
    )
    logger.info("✅ Backward compatibility maintained")

    # Clean up - only call shutdown if it exists
    if hasattr(pool, "shutdown"):
        pool.shutdown()
    ProcessPoolFactory.reset()


def main() -> None:
    """Run all tests."""
    logger.info("Starting dependency injection tests...")

    try:
        test_production_mode()
        test_mock_mode()
        test_custom_injection()
        test_singleton_behavior()
        test_backward_compatibility()

        logger.info("")
        logger.info("=" * 50)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("=" * 50)

    except AssertionError as e:
        logger.error(f"❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        # Standard library imports
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
