#!/usr/bin/env python3
"""Test cache directory separation between production, mock, and test modes."""

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def test_cache_config() -> None:
    """Test CacheConfig mode detection and directory selection."""
    logger.info("=" * 50)
    logger.info("Testing CacheConfig")
    logger.info("=" * 50)
    
    from cache_config import CacheConfig
    
    # Save original environment
    original_env = dict(os.environ)
    
    try:
        # Clear all mode indicators
        os.environ.pop("SHOTBOT_MOCK", None)
        os.environ.pop("SHOTBOT_TEST_MODE", None)
        os.environ.pop("SHOTBOT_HEADLESS", None)
        
        # Test production mode
        cache_dir = CacheConfig.get_cache_directory()
        assert cache_dir == CacheConfig.PRODUCTION_CACHE_DIR
        logger.info(f"✅ Production cache: {cache_dir}")
        
        # Test mock mode
        os.environ["SHOTBOT_MOCK"] = "1"
        cache_dir = CacheConfig.get_cache_directory()
        assert cache_dir == CacheConfig.MOCK_CACHE_DIR
        logger.info(f"✅ Mock cache: {cache_dir}")
        
        # Test test mode (overrides mock)
        os.environ["SHOTBOT_TEST_MODE"] = "1"
        cache_dir = CacheConfig.get_cache_directory()
        assert cache_dir == CacheConfig.TEST_CACHE_DIR
        logger.info(f"✅ Test cache: {cache_dir}")
        
    finally:
        # Restore environment
        os.environ.clear()
        os.environ.update(original_env)


def test_cache_manager_separation() -> None:
    """Test that CacheManager uses separate directories."""
    logger.info("=" * 50)
    logger.info("Testing CacheManager directory separation")
    logger.info("=" * 50)
    
    from cache_config import CacheConfig
    from cache_manager import CacheManager
    
    # Save original environment
    original_env = dict(os.environ)
    
    try:
        # Test production mode
        os.environ.pop("SHOTBOT_MOCK", None)
        os.environ.pop("SHOTBOT_TEST_MODE", None)
        
        prod_manager = CacheManager()
        assert prod_manager.cache_dir == CacheConfig.PRODUCTION_CACHE_DIR
        logger.info(f"✅ Production CacheManager: {prod_manager.cache_dir}")
        
        # Test mock mode
        os.environ["SHOTBOT_MOCK"] = "1"
        mock_manager = CacheManager()
        assert mock_manager.cache_dir == CacheConfig.MOCK_CACHE_DIR
        logger.info(f"✅ Mock CacheManager: {mock_manager.cache_dir}")
        
        # Test test mode
        os.environ["SHOTBOT_TEST_MODE"] = "1"
        test_manager = CacheManager()
        assert test_manager.cache_dir == CacheConfig.TEST_CACHE_DIR
        logger.info(f"✅ Test CacheManager: {test_manager.cache_dir}")
        
        # Verify they're all different
        assert prod_manager.cache_dir != mock_manager.cache_dir
        assert prod_manager.cache_dir != test_manager.cache_dir
        assert mock_manager.cache_dir != test_manager.cache_dir
        logger.info("✅ All cache directories are different")
        
    finally:
        # Restore environment
        os.environ.clear()
        os.environ.update(original_env)


def test_cache_isolation() -> None:
    """Test that data written to one cache doesn't appear in another."""
    logger.info("=" * 50)
    logger.info("Testing cache isolation")
    logger.info("=" * 50)
    
    from cache_config import CacheConfig
    from cache_manager import CacheManager
    
    # Save original environment
    original_env = dict(os.environ)
    
    # Create temporary test directories
    test_base = Path(tempfile.mkdtemp(prefix="shotbot_cache_test_"))
    
    try:
        # Override cache directories to use temp locations
        CacheConfig.PRODUCTION_CACHE_DIR = test_base / "prod"
        CacheConfig.MOCK_CACHE_DIR = test_base / "mock"
        CacheConfig.TEST_CACHE_DIR = test_base / "test"
        
        # Write to production cache
        os.environ.clear()
        os.environ.update(original_env)
        os.environ.pop("SHOTBOT_MOCK", None)
        os.environ.pop("SHOTBOT_TEST_MODE", None)
        
        prod_manager = CacheManager()
        prod_data = [{"name": "production_shot", "path": "/prod/path"}]
        prod_manager.cache_shots(prod_data)
        logger.info("✅ Wrote data to production cache")
        
        # Write to mock cache
        os.environ["SHOTBOT_MOCK"] = "1"
        mock_manager = CacheManager()
        mock_data = [{"name": "mock_shot", "path": "/mock/path"}]
        mock_manager.cache_shots(mock_data)
        logger.info("✅ Wrote data to mock cache")
        
        # Verify isolation - production should not have mock data
        os.environ.pop("SHOTBOT_MOCK", None)
        prod_manager2 = CacheManager()
        prod_cached = prod_manager2.get_cached_shots()
        
        if prod_cached:
            assert len(prod_cached) == 1
            assert prod_cached[0]["name"] == "production_shot"
            assert "mock_shot" not in str(prod_cached)
        logger.info("✅ Production cache isolated from mock data")
        
        # Verify isolation - mock should not have production data
        os.environ["SHOTBOT_MOCK"] = "1"
        mock_manager2 = CacheManager()
        mock_cached = mock_manager2.get_cached_shots()
        
        if mock_cached:
            assert len(mock_cached) == 1
            assert mock_cached[0]["name"] == "mock_shot"
            assert "production_shot" not in str(mock_cached)
        logger.info("✅ Mock cache isolated from production data")
        
    finally:
        # Clean up temp directories
        if test_base.exists():
            shutil.rmtree(test_base)
        
        # Restore environment
        os.environ.clear()
        os.environ.update(original_env)
        
        # Restore default directories
        CacheConfig.PRODUCTION_CACHE_DIR = Path.home() / ".shotbot" / "cache"
        CacheConfig.MOCK_CACHE_DIR = Path.home() / ".shotbot" / "cache_mock"
        CacheConfig.TEST_CACHE_DIR = Path.home() / ".shotbot" / "cache_test"


def test_cache_info() -> None:
    """Test cache information reporting."""
    logger.info("=" * 50)
    logger.info("Testing cache info")
    logger.info("=" * 50)
    
    from cache_config import CacheConfig
    
    info = CacheConfig.get_cache_info()
    
    logger.info("Cache Info:")
    for key, value in info.items():
        logger.info(f"  {key}: {value}")
    
    assert "cache_directory" in info
    assert "is_mock_mode" in info
    assert "is_test_mode" in info
    logger.info("✅ Cache info contains expected fields")


def main() -> None:
    """Run all cache separation tests."""
    logger.info("Starting cache separation tests...")
    
    try:
        test_cache_config()
        test_cache_manager_separation()
        test_cache_isolation()
        test_cache_info()
        
        logger.info("")
        logger.info("=" * 50)
        logger.info("✅ ALL CACHE SEPARATION TESTS PASSED!")
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