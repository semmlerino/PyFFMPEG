"""Cache configuration and directory management.

This module provides centralized cache directory configuration
that separates mock/test cache from production cache.
"""

from __future__ import annotations

import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CacheConfig:
    """Manage cache directory configuration based on mode."""
    
    # Default cache directories
    PRODUCTION_CACHE_DIR = Path.home() / ".shotbot" / "cache"
    MOCK_CACHE_DIR = Path.home() / ".shotbot" / "cache_mock"
    TEST_CACHE_DIR = Path.home() / ".shotbot" / "cache_test"
    
    @staticmethod
    def get_cache_directory() -> Path:
        """Get the appropriate cache directory based on current mode.
        
        Returns:
            Path to cache directory (production, mock, or test)
        """
        # Check if we're in test mode (pytest or unittest running)
        if CacheConfig.is_test_mode():
            cache_dir = CacheConfig.TEST_CACHE_DIR
            logger.debug(f"Using TEST cache directory: {cache_dir}")
            return cache_dir
        
        # Check if we're in mock mode
        if CacheConfig.is_mock_mode():
            cache_dir = CacheConfig.MOCK_CACHE_DIR
            logger.debug(f"Using MOCK cache directory: {cache_dir}")
            return cache_dir
        
        # Default to production cache
        cache_dir = CacheConfig.PRODUCTION_CACHE_DIR
        logger.debug(f"Using PRODUCTION cache directory: {cache_dir}")
        return cache_dir
    
    @staticmethod
    def is_test_mode() -> bool:
        """Check if running in test mode.
        
        Returns:
            True if pytest or unittest is running
        """
        # Check for pytest
        if "pytest" in sys.modules:
            return True
        
        # Check for unittest
        if "unittest" in sys.modules and hasattr(sys, '_called_from_test'):
            return True
        
        # Check environment variable
        if os.environ.get("SHOTBOT_TEST_MODE", "").lower() in ("1", "true", "yes"):
            return True
        
        # Check if running from tests directory
        import inspect
        frame = inspect.currentframe()
        while frame:
            code = frame.f_code
            if "/tests/" in code.co_filename or "\\tests\\" in code.co_filename:
                return True
            frame = frame.f_back
        
        return False
    
    @staticmethod
    def is_mock_mode() -> bool:
        """Check if running in mock mode.
        
        Returns:
            True if mock mode is enabled
        """
        # Check environment variable
        if os.environ.get("SHOTBOT_MOCK", "").lower() in ("1", "true", "yes"):
            return True
        
        # Check if ProcessPoolFactory is in mock mode
        try:
            from process_pool_factory import ProcessPoolFactory
            if ProcessPoolFactory._factory_mode == "mock":
                return True
        except ImportError:
            pass
        
        return False
    
    @staticmethod
    def is_headless_mode() -> bool:
        """Check if running in headless mode.
        
        Returns:
            True if headless mode is enabled
        """
        if os.environ.get("SHOTBOT_HEADLESS", "").lower() in ("1", "true", "yes"):
            return True
        
        # Check for CI environment
        ci_vars = ["CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS", "GITLAB_CI"]
        for var in ci_vars:
            if os.environ.get(var):
                return True
        
        return False
    
    @staticmethod
    def clear_test_cache() -> None:
        """Clear the test cache directory.
        
        Useful for ensuring clean state in tests.
        """
        import shutil
        
        if CacheConfig.TEST_CACHE_DIR.exists():
            shutil.rmtree(CacheConfig.TEST_CACHE_DIR)
            logger.info(f"Cleared test cache: {CacheConfig.TEST_CACHE_DIR}")
    
    @staticmethod
    def clear_mock_cache() -> None:
        """Clear the mock cache directory.
        
        Useful for ensuring clean state in mock mode.
        """
        import shutil
        
        if CacheConfig.MOCK_CACHE_DIR.exists():
            shutil.rmtree(CacheConfig.MOCK_CACHE_DIR)
            logger.info(f"Cleared mock cache: {CacheConfig.MOCK_CACHE_DIR}")
    
    @staticmethod
    def get_cache_info() -> dict:
        """Get information about current cache configuration.
        
        Returns:
            Dictionary with cache configuration details
        """
        cache_dir = CacheConfig.get_cache_directory()
        
        info = {
            "cache_directory": str(cache_dir),
            "exists": cache_dir.exists(),
            "is_test_mode": CacheConfig.is_test_mode(),
            "is_mock_mode": CacheConfig.is_mock_mode(),
            "is_headless_mode": CacheConfig.is_headless_mode(),
        }
        
        if cache_dir.exists():
            # Calculate size
            total_size = 0
            file_count = 0
            for path in cache_dir.rglob("*"):
                if path.is_file():
                    total_size += path.stat().st_size
                    file_count += 1
            
            info["size_mb"] = round(total_size / (1024 * 1024), 2)
            info["file_count"] = file_count
        
        return info
    
    @staticmethod
    def migrate_cache(from_dir: Path, to_dir: Path) -> bool:
        """Migrate cache from one directory to another.
        
        Args:
            from_dir: Source cache directory
            to_dir: Destination cache directory
            
        Returns:
            True if successful
        """
        import shutil
        
        if not from_dir.exists():
            logger.warning(f"Source cache directory does not exist: {from_dir}")
            return False
        
        try:
            # Ensure parent directory exists
            to_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy entire directory tree
            if to_dir.exists():
                shutil.rmtree(to_dir)
            
            shutil.copytree(from_dir, to_dir)
            logger.info(f"Migrated cache from {from_dir} to {to_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate cache: {e}")
            return False


# Make sys available for is_test_mode
import sys


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test cache directory detection
    print("Cache Configuration Test")
    print("=" * 50)
    
    # Normal mode
    cache_dir = CacheConfig.get_cache_directory()
    print(f"Normal mode cache: {cache_dir}")
    
    # Mock mode
    os.environ["SHOTBOT_MOCK"] = "1"
    cache_dir = CacheConfig.get_cache_directory()
    print(f"Mock mode cache: {cache_dir}")
    
    # Test mode
    os.environ["SHOTBOT_TEST_MODE"] = "1"
    cache_dir = CacheConfig.get_cache_directory()
    print(f"Test mode cache: {cache_dir}")
    
    # Get cache info
    print("\nCache Info:")
    info = CacheConfig.get_cache_info()
    for key, value in info.items():
        print(f"  {key}: {value}")