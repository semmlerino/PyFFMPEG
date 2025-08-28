"""Cache validation and repair operations."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from .memory_manager import MemoryManager
from .storage_backend import StorageBackend

if TYPE_CHECKING:
    from type_definitions import (
        CacheEfficiencyDict,
        ValidationResultDict,
    )

logger = logging.getLogger(__name__)


class CacheValidator:
    """Validates cache consistency and performs repair operations.

    This class checks for common cache issues such as orphaned files,
    size mismatches, missing files, and memory tracking inconsistencies.
    It can automatically repair many issues and provides detailed
    statistics about cache health.
    """

    def __init__(
        self,
        thumbnails_directory: Path,
        memory_manager: MemoryManager,
        storage_backend: StorageBackend | None = None,
    ):
        """Initialize cache validator.

        Args:
            thumbnails_directory: Directory containing cached thumbnails
            memory_manager: Memory manager instance to validate
            storage_backend: Storage backend for file operations
        """
        self._thumbnails_dir = thumbnails_directory
        self._memory_manager = memory_manager
        self._storage = storage_backend or StorageBackend()

        logger.debug(f"CacheValidator initialized for {thumbnails_directory}")

    def validate_cache(self, fix_issues: bool = True) -> "ValidationResultDict":
        """Validate cache consistency and optionally fix issues.

        Args:
            fix_issues: If True, automatically fix issues found

        Returns:
            Dictionary with validation results and statistics
        """
        logger.info("Starting cache validation...")

        results: ValidationResultDict = {
            "valid": True,
            "issues_found": 0,
            "issues_fixed": 0,
            "orphaned_files": 0,
            "missing_files": 0,
            "size_mismatches": 0,
            "memory_usage_corrected": False,
            "details": [],
        }

        try:
            # Validate memory tracking
            memory_results = self._validate_memory_tracking(fix_issues)
            results.update(memory_results)

            # Find orphaned thumbnail files
            orphan_results = self._find_orphaned_files(fix_issues)
            results.update(orphan_results)

            # Validate directory structure
            structure_results = self._validate_directory_structure(fix_issues)
            results.update(structure_results)

            # Calculate final status
            total_issues = (
                results["missing_files"]
                + results["size_mismatches"]
                + results["orphaned_files"]
            )

            results["issues_found"] = total_issues
            results["valid"] = total_issues == 0

            if results["valid"]:
                logger.info("Cache validation passed - no issues found")
            else:
                logger.info(
                    f"Cache validation found {total_issues} issues, "
                    + f"fixed {results['issues_fixed']}"
                )

            return results

        except Exception as e:
            logger.error(f"Error during cache validation: {e}")
            return {
                "valid": False,
                "error": str(e),
                "issues_found": 0,
                "issues_fixed": 0,
            }

    def repair_cache(self) -> "ValidationResultDict":
        """Perform comprehensive cache repair operations.

        Returns:
            Dictionary with repair results
        """
        logger.info("Starting comprehensive cache repair...")
        return self.validate_cache(fix_issues=True)

    def get_cache_statistics(self) -> "ValidationResultDict":
        """Get detailed cache statistics without making changes.

        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "thumbnails_directory": str(self._thumbnails_dir),
            "directory_exists": self._thumbnails_dir.exists(),
            "memory_stats": self._memory_manager.get_usage_stats(),
        }

        if self._thumbnails_dir.exists():
            # Count actual files on disk
            thumbnail_files = list(self._thumbnails_dir.rglob("*.jpg"))
            stats["actual_thumbnail_count"] = len(thumbnail_files)
            stats["actual_total_size_mb"] = sum(
                f.stat().st_size for f in thumbnail_files if f.exists()
            ) / (1024 * 1024)

            # Directory structure info
            subdirs = [d for d in self._thumbnails_dir.iterdir() if d.is_dir()]
            stats["show_directories"] = len(subdirs)

        else:
            stats["actual_thumbnail_count"] = 0
            stats["actual_total_size_mb"] = 0
            stats["show_directories"] = 0

        return stats

    def _validate_memory_tracking(
        self, fix_issues: bool
    ) -> "ValidationResultDict":
        """Validate memory manager tracking accuracy.

        Args:
            fix_issues: Whether to fix issues found

        Returns:
            Dictionary with validation results
        """
        results = {
            "missing_files": 0,
            "size_mismatches": 0,
            "memory_usage_corrected": False,
            "details": [],
        }

        # Use the memory manager's validate_tracking method
        validation_result = self._memory_manager.validate_tracking()

        results["missing_files"] = validation_result.get("invalid_files", 0)
        results["size_mismatches"] = validation_result.get("size_mismatches", 0)
        results["issues_fixed"] = validation_result.get("issues_fixed", 0)

        if validation_result.get("issues_fixed", 0) > 0:
            results["memory_usage_corrected"] = True
            results["details"].append(
                f"Fixed {validation_result['issues_fixed']} memory tracking issues"
            )

        return results

    def _find_orphaned_files(self, fix_issues: bool) -> "ValidationResultDict":
        """Find thumbnail files not being tracked by memory manager.

        Args:
            fix_issues: Whether to add orphaned files to tracking

        Returns:
            Dictionary with orphan file results
        """
        results = {
            "orphaned_files": 0,
            "details": [],
        }

        if not self._thumbnails_dir.exists():
            return results

        orphaned_files = []

        # Find all thumbnail files
        for thumb_file in self._thumbnails_dir.rglob("*.jpg"):
            if not thumb_file.exists():
                continue

            # Check if tracked by memory manager
            if not self._memory_manager.is_item_tracked(thumb_file):
                orphaned_files.append(thumb_file)

        results["orphaned_files"] = len(orphaned_files)

        if orphaned_files and fix_issues:
            fixed_count = 0
            for orphan_file in orphaned_files:
                try:
                    if self._memory_manager.track_item(orphan_file):
                        fixed_count += 1
                except Exception as e:
                    logger.debug(f"Failed to track orphaned file {orphan_file}: {e}")

            results["issues_fixed"] = fixed_count
            if fixed_count > 0:
                results["details"].append(
                    f"Added {fixed_count} orphaned files to tracking"
                )

        elif orphaned_files:
            results["details"].append(f"Found {len(orphaned_files)} orphaned files")

        return results

    def _validate_directory_structure(
        self, fix_issues: bool
    ) -> "ValidationResultDict":
        """Validate the cache directory structure.

        Args:
            fix_issues: Whether to fix structural issues

        Returns:
            Dictionary with structure validation results
        """
        results = {
            "structure_issues": 0,
            "details": [],
        }

        # Ensure main thumbnails directory exists
        if not self._thumbnails_dir.exists():
            if fix_issues:
                try:
                    if self._storage.ensure_directory(self._thumbnails_dir):
                        results["details"].append(
                            "Created missing thumbnails directory"
                        )
                        results["issues_fixed"] = results.get("issues_fixed", 0) + 1
                    else:
                        results["structure_issues"] += 1
                        results["details"].append(
                            "Failed to create thumbnails directory"
                        )
                except Exception as e:
                    results["structure_issues"] += 1
                    results["details"].append(f"Directory creation error: {e}")
            else:
                results["structure_issues"] += 1
                results["details"].append("Thumbnails directory does not exist")

        return results

    def clean_empty_directories(self) -> int:
        """Remove empty subdirectories in the cache.

        Returns:
            Number of directories removed
        """
        if not self._thumbnails_dir.exists():
            return 0

        removed_count = 0

        # Find empty directories (bottom-up to handle nested empty dirs)
        for dirpath in sorted(self._thumbnails_dir.rglob("*"), reverse=True):
            if not dirpath.is_dir():
                continue

            try:
                # Try to remove if empty
                if not any(dirpath.iterdir()):
                    dirpath.rmdir()
                    removed_count += 1
                    logger.debug(f"Removed empty directory: {dirpath}")
            except (OSError, IOError) as e:
                logger.debug(f"Failed to remove directory {dirpath}: {e}")

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} empty directories")

        return removed_count

    def analyze_cache_efficiency(self) -> dict[str, Any]:
        """Analyze cache usage patterns and efficiency.

        Returns:
            Dictionary with efficiency analysis
        """
        stats = self.get_cache_statistics()
        memory_stats = stats["memory_stats"]

        analysis = {
            "memory_utilization_percent": memory_stats["usage_percent"],
            "average_file_size_kb": memory_stats.get("average_item_kb", 0),
            "cache_hit_potential": "unknown",  # Would need access patterns to calculate
            "recommendations": [],
        }

        # Generate recommendations based on usage
        if memory_stats["usage_percent"] > 90:
            analysis["recommendations"].append(
                "Memory usage is very high - consider increasing cache limit or running cleanup"
            )
        elif memory_stats["usage_percent"] < 20:
            analysis["recommendations"].append(
                "Memory usage is low - cache limit could potentially be reduced"
            )

        if memory_stats.get("average_item_kb", 0) > 100:
            analysis["recommendations"].append(
                "Average thumbnail size is large - consider reducing thumbnail dimensions"
            )

        return analysis

    def __repr__(self) -> str:
        """String representation of cache validator."""
        return f"CacheValidator(dir={self._thumbnails_dir.name})"
