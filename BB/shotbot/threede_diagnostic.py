#!/usr/bin/env python3
"""Diagnostic tool for troubleshooting 3DE scene finding issues.

This tool helps identify why 3DE scenes aren't being found by:
1. Scanning actual directory structures under user directories
2. Comparing expected paths vs actual paths
3. Finding all .3de files regardless of location
4. Checking environment variables and alternative path patterns
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils import PathUtils


class ThreeDEDiagnostic:
    """Diagnostic tool for 3DE scene finding issues."""

    def __init__(self, verbose: bool = False):
        """Initialize diagnostic tool.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.setup_logging()
        self.found_3de_files: List[Path] = []
        self.scanned_directories: List[Path] = []
        self.permission_errors: List[Path] = []
        self.expected_paths: List[Path] = []
        self.actual_paths: List[Path] = []

    def setup_logging(self):
        """Setup logging configuration."""
        level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
        self.logger = logging.getLogger(__name__)

    def diagnose_shot(
        self,
        shot_workspace_path: str,
        show: Optional[str] = None,
        sequence: Optional[str] = None,
        shot: Optional[str] = None,
    ) -> Dict:
        """Run complete diagnostic for a shot workspace.

        Args:
            shot_workspace_path: Path to shot workspace
            show: Show name (for context, extracted from path if not provided)
            sequence: Sequence name (for context, extracted from path if not provided)
            shot: Shot name (for context, extracted from path if not provided)

        Returns:
            Dictionary containing diagnostic results
        """
        self.logger.info(
            f"Starting 3DE diagnostic for workspace: {shot_workspace_path}"
        )

        # Reset state
        self.found_3de_files.clear()
        self.scanned_directories.clear()
        self.permission_errors.clear()
        self.expected_paths.clear()
        self.actual_paths.clear()

        # Extract shot info from path if not provided
        if not all([show, sequence, shot]):
            show, sequence, shot = self._extract_shot_info_from_path(
                shot_workspace_path
            )

        results = {
            "workspace_path": shot_workspace_path,
            "show": show,
            "sequence": sequence,
            "shot": shot,
            "workspace_exists": False,
            "user_dir_exists": False,
            "environment_vars": self._check_environment_variables(),
            "user_directories": [],
            "expected_paths": [],
            "actual_structure": {},
            "found_3de_files": [],
            "permission_errors": [],
            "recommendations": [],
        }

        # Check if workspace exists
        workspace_path = Path(shot_workspace_path)
        results["workspace_exists"] = workspace_path.exists()
        if not results["workspace_exists"]:
            self.logger.error(f"Workspace path does not exist: {shot_workspace_path}")
            results["recommendations"].append(
                f"Workspace path does not exist: {shot_workspace_path}"
            )
            return results

        # Check user directory
        user_dir = workspace_path / "user"
        results["user_dir_exists"] = user_dir.exists()
        if not results["user_dir_exists"]:
            self.logger.error(f"User directory does not exist: {user_dir}")
            results["recommendations"].append(f"User directory missing: {user_dir}")
            return results

        # Scan user directories
        results["user_directories"] = self._scan_user_directories(user_dir)

        # Check expected paths for each user
        for user_info in results["user_directories"]:
            username = user_info["username"]
            expected_path = self._get_expected_3de_path(shot_workspace_path, username)
            self.expected_paths.append(expected_path)
            results["expected_paths"].append(
                {
                    "username": username,
                    "path": str(expected_path),
                    "exists": expected_path.exists(),
                }
            )

        # Build actual directory structure
        results["actual_structure"] = self._build_directory_structure(user_dir)

        # Search for all .3de files
        results["found_3de_files"] = self._find_all_3de_files(user_dir)

        # Add permission errors
        results["permission_errors"] = [str(p) for p in self.permission_errors]

        # Generate recommendations
        results["recommendations"].extend(self._generate_recommendations(results))

        return results

    def _extract_shot_info_from_path(self, workspace_path: str) -> Tuple[str, str, str]:
        """Extract show/sequence/shot from workspace path.

        Args:
            workspace_path: Shot workspace path

        Returns:
            Tuple of (show, sequence, shot)
        """
        path = Path(workspace_path)
        parts = path.parts

        # Look for common VFX path patterns
        # e.g., /shows/showname/shots/sequence/shot
        show = sequence = shot = "unknown"

        try:
            if "shots" in parts:
                shots_index = parts.index("shots")
                if shots_index >= 1:
                    show = parts[shots_index - 1]
                if shots_index + 1 < len(parts):
                    sequence = parts[shots_index + 1]
                if shots_index + 2 < len(parts):
                    shot = parts[shots_index + 2]
        except (ValueError, IndexError):
            self.logger.warning(
                f"Could not extract shot info from path: {workspace_path}"
            )

        return show, sequence, shot

    def _check_environment_variables(self) -> Dict[str, str]:
        """Check for relevant environment variables.

        Returns:
            Dictionary of environment variables and their values
        """
        env_vars = {}

        # Common VFX environment variables that might affect 3DE paths
        relevant_vars = [
            "SHOW",
            "SEQUENCE",
            "SHOT",
            "PROJECT_ROOT",
            "SHOWS_ROOT",
            "THREEDE_PATH",
            "3DE_PATH",
            "TDE_PATH",
            "USER",
            "USERNAME",
            "LOGNAME",
            "MM_ROOT",
            "MM_PATH",  # Matchmove specific
        ]

        for var in relevant_vars:
            value = os.environ.get(var)
            if value:
                env_vars[var] = value
                self.logger.debug(f"Found environment variable {var}={value}")

        return env_vars

    def _scan_user_directories(self, user_dir: Path) -> List[Dict]:
        """Scan user directories and collect information.

        Args:
            user_dir: Path to user directory

        Returns:
            List of user directory information
        """
        user_directories = []

        try:
            for item in user_dir.iterdir():
                if item.is_dir():
                    user_info = {
                        "username": item.name,
                        "path": str(item),
                        "accessible": True,
                        "subdirectories": [],
                    }

                    # Try to list subdirectories
                    try:
                        subdirs = [
                            subitem.name
                            for subitem in item.iterdir()
                            if subitem.is_dir()
                        ]
                        user_info["subdirectories"] = sorted(subdirs)
                        self.logger.debug(
                            f"User {item.name} has subdirectories: {subdirs}"
                        )
                    except PermissionError:
                        user_info["accessible"] = False
                        self.permission_errors.append(item)
                        self.logger.warning(f"Permission denied accessing: {item}")

                    user_directories.append(user_info)
                    self.scanned_directories.append(item)

        except PermissionError:
            self.permission_errors.append(user_dir)
            self.logger.error(f"Permission denied accessing user directory: {user_dir}")

        return user_directories

    def _get_expected_3de_path(self, workspace_path: str, username: str) -> Path:
        """Get expected 3DE scene path for a user.

        Args:
            workspace_path: Shot workspace path
            username: Username

        Returns:
            Expected 3DE scene path
        """
        return PathUtils.build_threede_scene_path(workspace_path, username)

    def _build_directory_structure(self, user_dir: Path, max_depth: int = 4) -> Dict:
        """Build a tree representation of the actual directory structure.

        Args:
            user_dir: User directory to scan
            max_depth: Maximum depth to scan

        Returns:
            Nested dictionary representing directory structure
        """

        def scan_directory(path: Path, depth: int = 0) -> Dict:
            if depth > max_depth:
                return {"truncated": True}

            structure = {"type": "directory", "children": {}}

            try:
                for item in path.iterdir():
                    if item.is_dir():
                        structure["children"][item.name] = scan_directory(
                            item, depth + 1
                        )
                    elif item.suffix.lower() == ".3de":
                        structure["children"][item.name] = {
                            "type": "3de_file",
                            "path": str(item),
                        }
                    elif depth < 2:  # Only show files at shallow depths
                        structure["children"][item.name] = {"type": "file"}

            except PermissionError:
                structure["permission_denied"] = True
                self.permission_errors.append(path)

            return structure

        return scan_directory(user_dir)

    def _find_all_3de_files(self, user_dir: Path) -> List[Dict]:
        """Find all .3de files in user directories.

        Args:
            user_dir: User directory to search

        Returns:
            List of .3de file information
        """
        found_files = []

        def search_recursive(path: Path, relative_to: Path):
            try:
                for item in path.rglob("*.3de"):
                    if item.is_file():
                        relative_path = item.relative_to(relative_to)
                        file_info = {
                            "path": str(item),
                            "relative_path": str(relative_path),
                            "size_bytes": item.stat().st_size,
                            "parent_dirs": list(relative_path.parent.parts)
                            if relative_path.parent != Path(".")
                            else [],
                            "filename": item.name,
                        }
                        found_files.append(file_info)
                        self.found_3de_files.append(item)
                        self.logger.info(f"Found .3de file: {relative_path}")

            except PermissionError:
                self.permission_errors.append(path)
                self.logger.warning(f"Permission denied searching: {path}")
            except Exception as e:
                self.logger.error(f"Error searching for .3de files in {path}: {e}")

        search_recursive(user_dir, user_dir)
        return found_files

    def _generate_recommendations(self, results: Dict) -> List[str]:
        """Generate recommendations based on diagnostic results.

        Args:
            results: Diagnostic results

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if not results["found_3de_files"]:
            recommendations.append("No .3de files found in any user directories")
            recommendations.append(
                "Check if 3DE scenes are being saved to the expected locations"
            )
        else:
            recommendations.append(
                f"Found {len(results['found_3de_files'])} .3de files total"
            )

            # Check if files are in expected locations
            expected_locations = [
                ep["path"] for ep in results["expected_paths"] if ep["exists"]
            ]
            if not expected_locations:
                recommendations.append(
                    "None of the .3de files are in expected locations"
                )
                recommendations.append(
                    "Consider updating THREEDE_SCENE_SEGMENTS in config.py"
                )

                # Suggest alternative path patterns based on found files
                if results["found_3de_files"]:
                    common_patterns = self._analyze_file_patterns(
                        results["found_3de_files"]
                    )
                    if common_patterns:
                        recommendations.append(
                            f"Common path patterns found: {common_patterns}"
                        )

        if results["permission_errors"]:
            recommendations.append(
                f"Permission errors accessing {len(results['permission_errors'])} directories"
            )
            recommendations.append("Check file system permissions for user directories")

        if not results["user_directories"]:
            recommendations.append(
                "No user directories found - check if shots have been worked on"
            )

        return recommendations

    def _analyze_file_patterns(self, found_files: List[Dict]) -> List[str]:
        """Analyze common patterns in found .3de file paths.

        Args:
            found_files: List of found .3de file information

        Returns:
            List of common path patterns
        """
        patterns = []

        # Look for common directory sequences
        dir_sequences = []
        for file_info in found_files:
            if "parent_dirs" in file_info and file_info["parent_dirs"]:
                dir_sequences.append(tuple(file_info["parent_dirs"]))

        # Find most common sequences
        from collections import Counter

        if dir_sequences:
            common_sequences = Counter(dir_sequences).most_common(3)
            for sequence, count in common_sequences:
                patterns.append(f"{' -> '.join(sequence)} (found {count} times)")

        return patterns

    def print_report(self, results: Dict):
        """Print a formatted diagnostic report.

        Args:
            results: Diagnostic results dictionary
        """
        print("\n" + "=" * 80)
        print("3DE SCENE DIAGNOSTIC REPORT")
        print("=" * 80)

        print("\nWORKSPACE INFORMATION:")
        print(f"  Path: {results['workspace_path']}")
        print(f"  Show: {results['show']}")
        print(f"  Sequence: {results['sequence']}")
        print(f"  Shot: {results['shot']}")
        print(f"  Workspace exists: {results['workspace_exists']}")
        print(f"  User directory exists: {results['user_dir_exists']}")

        if results["environment_vars"]:
            print("\nENVIRONMENT VARIABLES:")
            for var, value in results["environment_vars"].items():
                print(f"  {var}={value}")

        print(f"\nUSER DIRECTORIES FOUND: {len(results['user_directories'])}")
        for user_info in results["user_directories"]:
            status = "accessible" if user_info["accessible"] else "permission denied"
            print(f"  {user_info['username']} ({status})")
            if user_info["accessible"] and user_info["subdirectories"]:
                subdirs = ", ".join(user_info["subdirectories"][:5])
                if len(user_info["subdirectories"]) > 5:
                    subdirs += f" ... ({len(user_info['subdirectories'])} total)"
                print(f"    Subdirectories: {subdirs}")

        print("\nEXPECTED 3DE PATHS:")
        for expected in results["expected_paths"]:
            status = "EXISTS" if expected["exists"] else "MISSING"
            print(f"  {expected['username']}: {expected['path']} [{status}]")

        print(f"\nFOUND .3DE FILES: {len(results['found_3de_files'])}")
        for file_info in results["found_3de_files"]:
            size_kb = file_info["size_bytes"] / 1024
            print(f"  {file_info['relative_path']} ({size_kb:.1f} KB)")

        if results["permission_errors"]:
            print(f"\nPERMISSION ERRORS: {len(results['permission_errors'])}")
            for error_path in results["permission_errors"]:
                print(f"  {error_path}")

        if results["recommendations"]:
            print("\nRECOMMENDATIONS:")
            for i, rec in enumerate(results["recommendations"], 1):
                print(f"  {i}. {rec}")

        print("\n" + "=" * 80)


def main():
    """Main entry point for the diagnostic tool."""
    parser = argparse.ArgumentParser(
        description="Diagnostic tool for 3DE scene finding issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python threede_diagnostic.py /shows/myshow/shots/seq001/shot010
  python threede_diagnostic.py /shows/myshow/shots/seq001/shot010 --verbose
  python threede_diagnostic.py /shows/myshow/shots/seq001/shot010 --show myshow --sequence seq001 --shot shot010
        """,
    )

    parser.add_argument("workspace_path", help="Path to shot workspace directory")

    parser.add_argument(
        "--show", help="Show name (extracted from path if not provided)"
    )

    parser.add_argument(
        "--sequence", help="Sequence name (extracted from path if not provided)"
    )

    parser.add_argument(
        "--shot", help="Shot name (extracted from path if not provided)"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    # Validate workspace path
    if not os.path.exists(args.workspace_path):
        print(f"Error: Workspace path does not exist: {args.workspace_path}")
        sys.exit(1)

    # Run diagnostic
    diagnostic = ThreeDEDiagnostic(verbose=args.verbose)
    results = diagnostic.diagnose_shot(
        args.workspace_path, args.show, args.sequence, args.shot
    )

    # Print report
    diagnostic.print_report(results)

    # Exit with appropriate code
    if results["found_3de_files"]:
        sys.exit(0)  # Success - found files
    else:
        sys.exit(1)  # No files found


if __name__ == "__main__":
    main()
