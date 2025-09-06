#!/usr/bin/env python3
"""Test the new dependency injection system for ProcessPoolManager."""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def test_production_mode():
    """Test that production mode works."""
    logger.info("=" * 50)
    logger.info("Testing PRODUCTION mode")
    logger.info("=" * 50)
    
    from process_pool_factory import ProcessPoolFactory, get_process_pool
    
    # Reset to clean state
    ProcessPoolFactory.reset()
    
    # Get instance in production mode (should be real ProcessPoolManager)
    pool = get_process_pool()
    logger.info(f"Got instance: {pool.__class__.__name__}")
    
    # Verify it's the real ProcessPoolManager
    from process_pool_manager import ProcessPoolManager
    assert isinstance(pool, ProcessPoolManager), f"Expected ProcessPoolManager, got {type(pool)}"
    logger.info("✅ Production mode works correctly")
    
    # Clean up
    pool.shutdown()
    ProcessPoolFactory.reset()

def test_mock_mode():
    """Test that mock mode works."""
    logger.info("=" * 50)
    logger.info("Testing MOCK mode")
    logger.info("=" * 50)
    
    from process_pool_factory import ProcessPoolFactory, get_process_pool
    
    # Reset to clean state
    ProcessPoolFactory.reset()
    
    # Enable mock mode
    ProcessPoolFactory.set_mock_mode(True)
    
    # Get instance in mock mode (should be TestProcessPool)
    pool = get_process_pool()
    logger.info(f"Got instance: {pool.__class__.__name__}")
    
    # Verify it's the mock TestProcessPool
    from tests.test_doubles_library import TestProcessPool
    assert isinstance(pool, TestProcessPool), f"Expected TestProcessPool, got {type(pool)}"
    logger.info("✅ Mock mode works correctly")
    
    # Test that it has demo data
    result = pool.execute_workspace_command("ws -sg")
    logger.info(f"Mock data returned: {len(result.split('\\n'))} lines")
    assert "workspace" in result, "Mock should return workspace data"
    logger.info("✅ Mock returns demo data")
    
    # Clean up
    ProcessPoolFactory.reset()

def test_custom_injection():
    """Test custom implementation injection."""
    logger.info("=" * 50)
    logger.info("Testing CUSTOM injection")
    logger.info("=" * 50)
    
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

def test_singleton_behavior():
    """Test that factory maintains singleton behavior."""
    logger.info("=" * 50)
    logger.info("Testing SINGLETON behavior")
    logger.info("=" * 50)
    
    from process_pool_factory import ProcessPoolFactory, get_process_pool
    
    # Reset to clean state
    ProcessPoolFactory.reset()
    
    # Get multiple instances
    pool1 = get_process_pool()
    pool2 = get_process_pool()
    
    # They should be the same instance
    assert pool1 is pool2, "Should return the same singleton instance"
    logger.info("✅ Singleton behavior maintained")
    
    # Clean up
    pool1.shutdown()
    ProcessPoolFactory.reset()

def test_backward_compatibility():
    """Test that old code still works."""
    logger.info("=" * 50)
    logger.info("Testing BACKWARD COMPATIBILITY")
    logger.info("=" * 50)
    
    from process_pool_factory import ProcessPoolFactory
    from process_pool_manager import ProcessPoolManager
    
    # Reset to clean state
    ProcessPoolFactory.reset()
    
    # Old code that uses ProcessPoolManager.get_instance() directly
    pool = ProcessPoolManager.get_instance()
    logger.info(f"Got instance via old method: {pool.__class__.__name__}")
    
    # Should still work
    assert isinstance(pool, ProcessPoolManager), "Old method should still work"
    logger.info("✅ Backward compatibility maintained")
    
    # Clean up
    pool.shutdown()
    ProcessPoolFactory.reset()

def main():
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
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()