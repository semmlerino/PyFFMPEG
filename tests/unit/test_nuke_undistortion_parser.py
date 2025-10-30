"""Unit tests for nuke_undistortion_parser module.

Tests parsing logic for Nuke undistortion files including copy/paste format,
standard format, Python code handling, and node name sanitization.
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from nuke_undistortion_parser import NukeUndistortionParser


class TestNukeUndistortionParser:
    """Test undistortion file parsing methods."""

    def test_parse_undistortion_file_empty_path(self) -> None:
        """Test parsing with empty path."""
        result = NukeUndistortionParser.parse_undistortion_file("")

        assert result == ""

    @patch("pathlib.Path.exists")
    def test_parse_undistortion_file_nonexistent(self, mock_exists: MagicMock) -> None:
        """Test parsing with non-existent file."""
        mock_exists.return_value = False

        result = NukeUndistortionParser.parse_undistortion_file("/nonexistent/file.nk")

        assert result == ""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_copy_paste_format_detection(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test detection of copy/paste format."""
        mock_exists.return_value = True
        copy_paste_content = """set cut_paste_input [stack 0]
Constant {
 inputs 0
 name Constant1
 xpos 100
 ypos -200
}"""
        mock_file.return_value.read.return_value = copy_paste_content

        result = NukeUndistortionParser.parse_undistortion_file("/path/to/undist.nk")

        assert "Imported undistortion content from copy/paste format" in result
        assert "Constant {" in result
        assert "name Constant1" in result

    @patch("nuke_undistortion_parser.Path")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_standard_format_fallback(
        self, mock_file: MagicMock, mock_path: MagicMock
    ) -> None:
        """Test fallback to standard format when copy/paste fails."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.stat.return_value.st_size = 100
        standard_content = """#! /usr/local/Nuke
version 12.0
Constant {
 inputs 0
 name Constant1
 xpos 100
 ypos -200
}"""
        mock_file.return_value.read.return_value = standard_content

        result = NukeUndistortionParser.parse_undistortion_file("/path/to/undist.nk")

        assert "Imported undistortion content from /path/to/undist.nk" in result
        assert "Constant {" in result
        assert "name Constant1" in result

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_copy_paste_format_basic(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test basic copy/paste format parsing."""
        mock_exists.return_value = True
        content = """set cut_paste_input [stack 0]
push $cut_paste_input
Lens {
 name Lens1
 xpos 0
 ypos -100
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_copy_paste_format(
            "/path/test.nk", ypos_offset=0
        )

        assert "Lens {" in result
        assert "name Lens1" in result
        assert "xpos 0" in result
        assert "ypos -100" in result
        # Should skip boilerplate
        assert "set cut_paste_input" not in result
        assert "push $cut_paste_input" not in result

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_copy_paste_format_ypos_offset(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test ypos offset adjustment in copy/paste format."""
        mock_exists.return_value = True
        content = """set cut_paste_input [stack 0]
Lens {
 name Lens1
 xpos 0
 ypos -100
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_copy_paste_format(
            "/path/test.nk", ypos_offset=-300
        )

        assert "ypos -400" in result  # -100 + (-300) = -400

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_copy_paste_format_python_block(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test Python block handling in copy/paste format."""
        mock_exists.return_value = True
        content = """set cut_paste_input [stack 0]
Lens {
 python {
import nuke
def test_function():
    return "test"
 }
 name Lens1
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_copy_paste_format("/path/test.nk")

        assert "python {" in result
        assert "import nuke" in result
        assert "def test_function():" in result
        assert 'return "test"' in result
        assert "}" in result

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_copy_paste_format_skip_root(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test Root node skipping in copy/paste format."""
        mock_exists.return_value = True
        content = """set cut_paste_input [stack 0]
Root {
 format "1920 1080"
 first_frame 1001
 last_frame 1100
}
Lens {
 name Lens1
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_copy_paste_format("/path/test.nk")

        # Root node should be skipped
        assert "Root {" not in result
        assert '"1920 1080"' not in result  # More specific than just "format"
        assert "first_frame" not in result
        # But Lens should be included
        assert "Lens {" in result
        assert "name Lens1" in result

    @patch("nuke_undistortion_parser.Path")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_standard_format_basic(
        self, mock_file: MagicMock, mock_path: MagicMock
    ) -> None:
        """Test basic standard format parsing."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.stat.return_value.st_size = 100
        content = """#! /usr/local/Nuke
version 12.0
Lens {
 name Lens1
 xpos 0
 ypos -100
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_standard_format("/path/test.nk")

        assert "Lens {" in result
        assert "name Lens1" in result
        # Should skip boilerplate
        assert "#!" not in result
        assert "version 12.0" not in result

    @patch("nuke_undistortion_parser.Path")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_standard_format_skip_window_layout(
        self, mock_file: MagicMock, mock_path: MagicMock
    ) -> None:
        """Test window layout skipping in standard format."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.stat.return_value.st_size = 100
        content = """version 12.0
define_window_layout_xml {
<layout>
  <window>
  </window>
</layout>
}
Lens {
 name Lens1
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_standard_format("/path/test.nk")

        # Window layout should be skipped
        assert "define_window_layout_xml" not in result
        assert "<layout>" not in result
        # But Lens should be included
        assert "Lens {" in result
        assert "name Lens1" in result

    @patch("nuke_undistortion_parser.Path")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_standard_format_python_dedentation(
        self, mock_file: MagicMock, mock_path: MagicMock
    ) -> None:
        """Test Python code dedentation in standard format."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.stat.return_value.st_size = 100
        content = """version 12.0
Lens {
 python {
     import nuke
     def test_function():
         return "test"
 }
 name Lens1
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_standard_format("/path/test.nk")

        assert "python {" in result
        assert "import nuke" in result  # Should be dedented
        assert "def test_function():" in result  # Should be dedented
        assert 'return "test"' in result  # Should preserve relative indentation

    @pytest.mark.parametrize(
        ("line", "offset", "expected"),
        [
            (" ypos 100", -200, " ypos -100"),
            (" ypos -50", -100, " ypos -150"),
            (" xpos 100", -200, " xpos 100"),
            (" ypos 100", 0, " ypos 100"),
            (" ypos 100 ypos 200", -50, " ypos 50 ypos 150"),
        ],
        ids=[
            "basic_positive",
            "negative_values",
            "no_ypos",
            "zero_offset",
            "multiple_ypos",
        ],
    )
    def test_adjust_ypos_in_line(self, line: str, offset: int, expected: str) -> None:
        """Test ypos adjustment in various scenarios."""
        result = NukeUndistortionParser._adjust_ypos_in_line(line, offset)
        assert result == expected

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            (" name my-node-1", " name my_node_1"),
            (" name node@123", " name node_123"),
            (" name node#456", " name node_456"),
            (" name node$789", " name node_789"),
            (" name node%abc", " name node_abc"),
            (" name node&def", " name node_def"),
            (" name node*ghi", " name node_ghi"),
            (" name node(jkl)", " name node_jkl_"),
            (" name node[mno]", " name node_mno_"),
            (" name node{pqr}", " name node_pqr_"),
            (" xpos 100", " xpos 100"),
            (" name valid_node_123", " name valid_node_123"),
        ],
        ids=[
            "basic_hyphen",
            "at_symbol",
            "hash",
            "dollar",
            "percent",
            "ampersand",
            "asterisk",
            "parentheses",
            "brackets",
            "braces",
            "no_name_attr",
            "already_valid",
        ],
    )
    def test_sanitize_node_names_in_line(self, line: str, expected: str) -> None:
        """Test node name sanitization in various scenarios."""
        result = NukeUndistortionParser._sanitize_node_names_in_line(line)
        assert result == expected

    @pytest.mark.parametrize(
        ("line", "original_line"),
        [
            ("version 12.0", "version 12.0"),
            ("  version 16.0 v4", "version 16.0 v4"),
            ("#! /usr/local/Nuke", "#! /usr/local/Nuke"),
            ("#!/usr/bin/nuke", "#!/usr/bin/nuke"),
            ("set cut_paste_input [stack 0]", "set cut_paste_input [stack 0]"),
            ("push $cut_paste_input", "push $cut_paste_input"),
            ("push 0", "push 0"),
        ],
        ids=[
            "version_basic",
            "version_with_spaces",
            "shebang_space",
            "shebang_no_space",
            "cut_paste_input",
            "push_cut_paste",
            "push_zero",
        ],
    )
    def test_should_skip_boilerplate_line(self, line: str, original_line: str) -> None:
        """Test skipping boilerplate lines."""
        assert NukeUndistortionParser._should_skip_boilerplate_line(line, original_line)

    def test_should_skip_boilerplate_line_keep_normal(self) -> None:
        """Test not skipping normal lines."""
        assert not NukeUndistortionParser._should_skip_boilerplate_line(
            "Lens {", "Lens {"
        )
        assert not NukeUndistortionParser._should_skip_boilerplate_line(
            " name Lens1", "name Lens1"
        )
        assert not NukeUndistortionParser._should_skip_boilerplate_line(
            " xpos 100", "xpos 100"
        )

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_copy_paste_format_empty_file(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test copy/paste format parsing with empty file."""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = ""

        result = NukeUndistortionParser._parse_copy_paste_format("/path/test.nk")

        assert result == ""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_copy_paste_format_not_copy_paste(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test copy/paste format parser with non-copy/paste content."""
        mock_exists.return_value = True
        content = """version 12.0
Lens {
 name Lens1
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_copy_paste_format("/path/test.nk")

        assert result == ""  # Should return empty for non-copy/paste format

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_standard_format_empty_file(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test standard format parsing with empty file."""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = ""

        result = NukeUndistortionParser._parse_standard_format("/path/test.nk")

        assert result == ""

    @patch("pathlib.Path.exists")
    def test_parse_standard_format_nonexistent_file(self, mock_exists: MagicMock) -> None:
        """Test standard format parsing with non-existent file."""
        mock_exists.return_value = False

        result = NukeUndistortionParser._parse_standard_format("/nonexistent/test.nk")

        assert result == ""

    @patch("pathlib.Path.exists")
    @patch(
        "builtins.open", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
    )
    def test_parse_standard_format_unicode_error(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test standard format parsing with unicode decode error."""
        mock_exists.return_value = True

        result = NukeUndistortionParser._parse_standard_format("/path/test.nk")

        assert result == ""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", side_effect=Exception("Unexpected error"))
    def test_parse_standard_format_unexpected_error(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test standard format parsing with unexpected error."""
        mock_exists.return_value = True

        result = NukeUndistortionParser._parse_standard_format("/path/test.nk")

        assert result == ""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", side_effect=Exception("Unexpected error"))
    def test_parse_copy_paste_format_exception(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test copy/paste format parsing with exception."""
        mock_exists.return_value = True

        result = NukeUndistortionParser._parse_copy_paste_format("/path/test.nk")

        assert result == ""

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_complex_python_indentation(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test complex Python code indentation handling."""
        mock_exists.return_value = True
        content = """set cut_paste_input [stack 0]
Lens {
 python {
     import nuke
     import math

     def calculate_distortion():
         # This is a complex function
         for i in range(10):
             if i > 5:
                 result = math.sqrt(i)
                 print(f"Result: {result}")
         return result
 }
 name Lens1
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_copy_paste_format("/path/test.nk")

        assert "import nuke" in result
        assert "import math" in result
        assert "def calculate_distortion():" in result
        assert "for i in range(10):" in result
        assert "if i > 5:" in result
        assert 'print(f"Result: {result}")' in result

    @patch("pathlib.Path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_nested_braces_handling(
        self, mock_file: MagicMock, mock_exists: MagicMock
    ) -> None:
        """Test handling of nested braces in nodes."""
        mock_exists.return_value = True
        content = """set cut_paste_input [stack 0]
Lens {
 distortion_model {
  model "radial"
  parameters {
   k1 0.1
   k2 0.2
  }
 }
 name Lens1
}"""
        mock_file.return_value.read.return_value = content

        result = NukeUndistortionParser._parse_copy_paste_format("/path/test.nk")

        assert "Lens {" in result
        assert "distortion_model {" in result
        assert 'model "radial"' in result
        assert "parameters {" in result
        assert "k1 0.1" in result
        assert "k2 0.2" in result
        assert "name Lens1" in result

    @patch("nuke_undistortion_parser.Path")
    @patch("builtins.open", new_callable=mock_open)
    def test_parse_undistortion_file_logs_appropriately(
        self, mock_file: MagicMock, mock_path: MagicMock
    ) -> None:
        """Test that parse_undistortion_file handles both formats and logs appropriately."""
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.stat.return_value.st_size = 100

        # Standard format content (not copy/paste)
        standard_content = """#! /usr/local/Nuke
version 12.0
Lens {
 name Lens1
 xpos 0
 ypos -100
}"""
        mock_file.return_value.read.return_value = standard_content

        result = NukeUndistortionParser.parse_undistortion_file(
            "/path/test.nk", ypos_offset=-200
        )

        # Should contain imported content
        assert "Imported undistortion content from /path/test.nk" in result
        assert "Lens {" in result
        assert "name Lens1" in result
        assert "ypos -300" in result  # -100 + (-200) offset

    def test_ypos_regex_pattern_variations(self) -> None:
        """Test ypos regex with various spacing patterns."""
        test_cases = [
            ("ypos 100", -50, "ypos 50"),
            ("ypos  100", -50, "ypos 50"),  # Multiple spaces
            ("ypos\t100", -50, "ypos 50"),  # Tab spacing
            (" ypos 100 ", -50, " ypos 50 "),  # Surrounded by spaces
            ("node_ypos 100", -50, "node_ypos 50"),  # Contains ypos pattern
            ("ypositive 100", -50, "ypositive 100"),  # Not actual ypos
        ]

        for original, offset, expected in test_cases:
            result = NukeUndistortionParser._adjust_ypos_in_line(original, offset)
            assert result == expected

    def test_node_name_regex_variations(self) -> None:
        """Test node name regex with various patterns."""
        test_cases = [
            (" name test-node", " name test_node"),
            ("  name  test-node", "  name  test_node"),  # Multiple spaces
            (
                "\tname\ttest-node",
                "\tname\ttest-node",
            ),  # Tab spacing - no change (early return)
            (" name test_node", " name test_node"),  # Already valid
            (" node_name test", " node_name test"),  # Not a name attribute
            (" filename test", " filename test"),  # Not a name attribute
        ]

        for original, expected in test_cases:
            result = NukeUndistortionParser._sanitize_node_names_in_line(original)
            assert result == expected
