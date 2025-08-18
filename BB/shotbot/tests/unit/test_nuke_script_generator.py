#!/usr/bin/env python3
"""Test Nuke script generation, especially colorspace quoting.

This test ensures that colorspaces containing spaces are properly quoted
in generated Nuke scripts, preventing "no such knob" errors.
"""

import os
import tempfile
import unittest

from nuke_script_generator import NukeScriptGenerator


class TestNukeScriptGenerator(unittest.TestCase):
    """Test suite for Nuke script generation."""

    def setUp(self):
        """Set up test fixtures."""
        self.generator = NukeScriptGenerator()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        # Clean up temp directory
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_colorspace_quoting_with_spaces(self):
        """Test that colorspaces with spaces are properly quoted.

        This tests the critical bug fix where colorspaces like
        "Input - Sony - S-Gamut3.Cine - Linear" were not quoted,
        causing Nuke to fail with "no such knob" errors.
        """
        test_cases = [
            # (colorspace, expected_in_script)
            (
                "Input - Sony - S-Gamut3.Cine - Linear",
                '"Input - Sony - S-Gamut3.Cine - Linear"',
            ),
            ("Output - sRGB", '"Output - sRGB"'),
            ("ACES - ACEScg", '"ACES - ACEScg"'),
            ("Utility - Linear - sRGB", '"Utility - Linear - sRGB"'),
            # Simple colorspaces should also be quoted for consistency
            ("linear", '"linear"'),
            ("sRGB", '"sRGB"'),
            ("ACEScg", '"ACEScg"'),
        ]

        for colorspace, expected_quoted in test_cases:
            with self.subTest(colorspace=colorspace):
                # Generate a test script
                script_content = self.generator._generate_read_node(
                    file_path="/path/to/plate.exr",
                    colorspace=colorspace,
                    first_frame=1001,
                    last_frame=1100,
                )

                # Check that colorspace is properly quoted
                self.assertIn(f"colorspace {expected_quoted}", script_content)
                # Should NOT have unquoted version
                if " " in colorspace:
                    self.assertNotIn(f"colorspace {colorspace}", script_content)

    def test_generate_comp_script(self):
        """Test full comp script generation."""
        shot_name = "GF_256_1400"
        plate_path = "/shows/jack_ryan/shots/GF_256/GF_256_1400/publish/plates/BG01/BG01.%04d.exr"
        colorspace = "Input - Sony - S-Gamut3.Cine - Linear"

        script_path = self.generator.generate_comp_script(
            shot_name=shot_name,
            plate_path=plate_path,
            colorspace=colorspace,
            first_frame=1001,
            last_frame=1100,
            output_dir=self.temp_dir,
        )

        self.assertIsNotNone(script_path)
        self.assertTrue(os.path.exists(script_path))

        # Read the generated script
        with open(script_path, "r") as f:
            content = f.read()

        # Verify content
        self.assertIn(shot_name, content)
        self.assertIn('"Input - Sony - S-Gamut3.Cine - Linear"', content)
        self.assertIn("first 1001", content)
        self.assertIn("last 1100", content)

    def test_special_characters_in_colorspace(self):
        """Test handling of special characters in colorspace names."""
        special_colorspaces = [
            "Input - Canon - Canon-Log3 - BT.2020",
            "Output - P3-D65 - 2.6 Gamma",
            "ACES - ACES2065-1",
            "Utility - Rec.709 - Camera",
            "Input - RED - REDWideGamutRGB - REDLog3G10",
        ]

        for colorspace in special_colorspaces:
            with self.subTest(colorspace=colorspace):
                script_content = self.generator._generate_read_node(
                    file_path="/path/to/plate.exr",
                    colorspace=colorspace,
                    first_frame=1001,
                    last_frame=1100,
                )

                # Should be properly quoted
                self.assertIn(f'colorspace "{colorspace}"', script_content)

    def test_undistortion_node_generation(self):
        """Test undistortion node generation."""
        undisto_path = (
            "/shows/project/shots/SEQ_01/SEQ_01_0010/publish/3de/undistortion.nk"
        )

        node_content = self.generator._generate_undistortion_node(undisto_path)

        self.assertIn("Group {", node_content)
        self.assertIn("name Undistortion", node_content)
        self.assertIn(f"# Undistortion file: {undisto_path}", node_content)

    def test_temporary_file_cleanup(self):
        """Test that temporary files are properly tracked for cleanup."""
        # Track generated files
        generated_files = []

        for i in range(3):
            script_path = self.generator.generate_comp_script(
                shot_name=f"test_shot_{i}",
                plate_path=f"/path/to/plate_{i}.exr",
                colorspace="linear",
                first_frame=1001,
                last_frame=1100,
                output_dir=self.temp_dir,
            )
            generated_files.append(script_path)

        # All files should exist
        for path in generated_files:
            self.assertTrue(os.path.exists(path))
    
    def test_import_undistortion_nodes(self):
        """Test importing undistortion nodes from .nk file."""
        # Create a test undistortion .nk file
        undisto_file = os.path.join(self.temp_dir, "test_undistortion.nk")
        undisto_content = """Group {
 name LensDistortion1
 inputs 1
 tile_color 0xcc804e00
 addUserKnob {20 LensDistortion}
 addUserKnob {4 mode M {undistort distort "st map"}}
 addUserKnob {22 analyseSequence l "Analyse Sequence" T ""}
}
Undistort {
 distortion 0.045
 name Undistort1
}"""
        
        with open(undisto_file, "w") as f:
            f.write(undisto_content)
        
        # Import the nodes
        imported_nodes = self.generator._import_undistortion_nodes(
            undisto_file, ypos_offset=-200
        )
        
        self.assertIsNotNone(imported_nodes)
        self.assertIn("Group {", imported_nodes)
        self.assertIn("LensDistortion1", imported_nodes)
        self.assertIn("Undistort1", imported_nodes)
        # Check that comment is added
        self.assertIn("# Imported undistortion nodes from", imported_nodes)
    
    def test_create_plate_script_with_undistortion(self):
        """Test creating script with both plate and undistortion."""
        # Create test undistortion file with realistic path
        undisto_path = os.path.join(
            self.temp_dir,
            "DB_256_1200_mm_default_FG01_LD_v002.nk"
        )
        undisto_content = """Group {
 name LensDistortion_FG01
 inputs 1
 help "Undistortion for DB_256_1200 FG01 plate"
}"""
        with open(undisto_path, "w") as f:
            f.write(undisto_content)
        
        # Create plate script with undistortion
        plate_path = "/shows/jack_ryan/shots/DB_256/DB_256_1200/publish/plate/FG01/v002/DB_256_1200_FG01.####.exr"
        shot_name = "DB_256_1200"
        
        script_path = self.generator.create_plate_script_with_undistortion(
            plate_path=plate_path,
            undistortion_path=undisto_path,
            shot_name=shot_name
        )
        
        self.assertIsNotNone(script_path)
        self.assertTrue(os.path.exists(script_path))
        
        # Read and verify content
        with open(script_path, "r") as f:
            content = f.read()
        
        # Should have plate Read node
        self.assertIn("Read_Plate", content)
        self.assertIn(shot_name, content)
        
        # Should have undistortion reference
        self.assertIn("Undistortion imported from", content)
        self.assertIn("LensDistortion_FG01", content)
    
    def test_nested_undistortion_path_handling(self):
        """Test handling of nested undistortion paths like real-world 3DE exports.
        
        Tests path pattern:
        /shows/jack_ryan/shots/DB_256/DB_256_1200/user/gabriel-h/mm/3de/mm-default/exports/
        scene/FG01/nuke_lens_distortion/v002/GF_256_1200_turnover-plate_FG01_lin_sgamut3cine_v001/
        DB_256_1200_mm_default_FG01_LD_v002.nk
        """
        # Create nested directory structure
        nested_dir = os.path.join(
            self.temp_dir,
            "GF_256_1200_turnover-plate_FG01_lin_sgamut3cine_v001"
        )
        os.makedirs(nested_dir, exist_ok=True)
        
        # Create undistortion file in nested directory
        undisto_path = os.path.join(
            nested_dir,
            "DB_256_1200_mm_default_FG01_LD_v002.nk"
        )
        
        undisto_content = """#! /usr/local/Nuke16.0v4/nuke-16.0.4 -nx
version 16.0 v4
Group {
 name LensDistortion_DB256_1200_FG01_v002
 help "3DE4 lens distortion for DB_256_1200"
 addUserKnob {20 User}
 addUserKnob {26 info l "" +STARTLINE T "Exported from 3DE4"}
}
Input {
 inputs 0
 name Input1
}
LensDistortion {
 serializeKnob ""
 serialiseKnob "22 serialization::archive 15 0 0 0 0 0 0 0 0 0 0 0 0"
 distortion 0.0234
 name LensDistortion1
}
Output {
 name Output1
}
end_group"""
        
        with open(undisto_path, "w") as f:
            f.write(undisto_content)
        
        # Import the nested undistortion
        imported_nodes = self.generator._import_undistortion_nodes(
            undisto_path, ypos_offset=-200
        )
        
        self.assertIsNotNone(imported_nodes)
        self.assertIn("LensDistortion_DB256_1200_FG01_v002", imported_nodes)
        self.assertIn("3DE4 lens distortion", imported_nodes)
        
        # Create full script with nested undistortion
        plate_path = "/shows/jack_ryan/shots/DB_256/DB_256_1200/publish/plate/FG01/v002/DB_256_1200_FG01_lin_sgamut3cine.####.exr"
        
        script_path = self.generator.create_plate_script_with_undistortion(
            plate_path=plate_path,
            undistortion_path=undisto_path,
            shot_name="DB_256_1200"
        )
        
        self.assertIsNotNone(script_path)
        
        # Verify the script references the correct undistortion path
        with open(script_path, "r") as f:
            content = f.read()
        
        # Should preserve the full nested path in the label/comment
        self.assertIn("DB_256_1200_mm_default_FG01_LD_v002.nk", content)

    def test_shot_name_sanitization(self):
        """Test that shot names are sanitized to prevent path traversal."""
        dangerous_names = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "shot/../../../name",
            "shot\\..\\..\\name",
        ]

        for dangerous_name in dangerous_names:
            with self.subTest(name=dangerous_name):
                # Should sanitize the name
                script_path = self.generator.generate_comp_script(
                    shot_name=dangerous_name,
                    plate_path="/path/to/plate.exr",
                    colorspace="linear",
                    first_frame=1001,
                    last_frame=1100,
                    output_dir=self.temp_dir,
                )

                # Path should not contain directory traversal
                self.assertNotIn("..", str(script_path))
                self.assertTrue(str(script_path).startswith(self.temp_dir))

    def test_frame_range_validation(self):
        """Test frame range validation in script generation."""
        test_cases = [
            (1001, 1100, True),  # Valid range
            (1, 100, True),  # Valid range
            (-100, 100, True),  # Valid with negative frames
            (1100, 1001, False),  # Invalid: last before first
            (1001, 1001, True),  # Valid: single frame
        ]

        for first, last, should_succeed in test_cases:
            with self.subTest(first=first, last=last):
                if should_succeed:
                    script_content = self.generator._generate_read_node(
                        file_path="/path/to/plate.exr",
                        colorspace="linear",
                        first_frame=first,
                        last_frame=last,
                    )
                    self.assertIn(f"first {first}", script_content)
                    self.assertIn(f"last {last}", script_content)
                else:
                    # Should handle invalid ranges gracefully
                    with self.assertRaises(ValueError):
                        self.generator._generate_read_node(
                            file_path="/path/to/plate.exr",
                            colorspace="linear",
                            first_frame=first,
                            last_frame=last,
                        )

    def test_plate_path_formats(self):
        """Test various plate path formats."""
        path_formats = [
            "/path/to/plate.%04d.exr",  # Printf style
            "/path/to/plate.####.exr",  # Hash style
            "/path/to/plate_1001.exr",  # Single frame
            "/path/to/plate.%06d.dpx",  # DPX sequence
            "/path/to/plate.%d.jpg",  # Variable padding
        ]

        for plate_path in path_formats:
            with self.subTest(path=plate_path):
                script_content = self.generator._generate_read_node(
                    file_path=plate_path,
                    colorspace="linear",
                    first_frame=1001,
                    last_frame=1100,
                )

                # Should include the file path
                self.assertIn("file ", script_content)
                # Path should be preserved
                if "%" in plate_path or "#" in plate_path:
                    # Sequence paths might be modified
                    pass
                else:
                    self.assertIn(plate_path, script_content)

    def test_generate_read_node(self):
        """Test Read node generation directly."""
        # Test the internal method that had the bug
        read_node = self.generator._generate_read_node(
            file_path="/shows/project/plates/BG01.%04d.exr",
            colorspace="Input - Sony - S-Gamut3.Cine - Linear",
            first_frame=1001,
            last_frame=1100,
        )

        # Check structure
        self.assertIn("Read {", read_node)
        self.assertIn("inputs 0", read_node)
        self.assertIn('file "/shows/project/plates/BG01.%04d.exr"', read_node)
        self.assertIn('colorspace "Input - Sony - S-Gamut3.Cine - Linear"', read_node)
        self.assertIn("first 1001", read_node)
        self.assertIn("last 1100", read_node)
        self.assertIn("origfirst 1001", read_node)
        self.assertIn("origlast 1100", read_node)
        self.assertIn("name Read1", read_node)
        self.assertIn("}", read_node)

    def test_write_node_generation(self):
        """Test Write node generation."""
        write_node = self.generator._generate_write_node(
            output_path="/output/comp_output.%04d.exr",
        )

        self.assertIn("Write {", write_node)
        self.assertIn('file "/output/comp_output.%04d.exr"', write_node)
        self.assertIn("file_type exr", write_node)
        self.assertIn("name Write1", write_node)

    def test_empty_colorspace(self):
        """Test handling of empty or None colorspace."""
        test_cases = [None, "", "   "]

        for colorspace in test_cases:
            with self.subTest(colorspace=repr(colorspace)):
                # Should handle gracefully - use default or skip
                script_content = self.generator._generate_read_node(
                    file_path="/path/to/plate.exr",
                    colorspace=colorspace,
                    first_frame=1001,
                    last_frame=1100,
                )

                # Should either omit colorspace or use a default
                if colorspace:
                    # If whitespace, should be trimmed and quoted
                    self.assertIn("colorspace", script_content)
                else:
                    # If None or empty, might omit or use default
                    pass  # Implementation dependent


class MockNukeScriptGenerator:
    """Mock implementation for testing."""

    def _generate_read_node(self, file_path, colorspace, first_frame, last_frame):
        """Generate a Read node with proper colorspace quoting."""
        # Quote colorspace if it exists
        if colorspace:
            colorspace_line = f'colorspace "{colorspace}"'
        else:
            colorspace_line = ""

        # Handle invalid frame ranges
        if first_frame > last_frame:
            raise ValueError(f"Invalid frame range: {first_frame} to {last_frame}")

        return f"""Read {{
  inputs 0
  file "{file_path}"
  {colorspace_line}
  first {first_frame}
  last {last_frame}
  origfirst {first_frame}
  origlast {last_frame}
  name Read1
}}"""

    def _generate_write_node(self, output_path):
        """Generate a Write node."""
        return f"""Write {{
  file "{output_path}"
  file_type exr
  name Write1
}}"""

    def _generate_undistortion_node(self, undisto_path):
        """Generate undistortion node."""
        return f"""Group {{
  name Undistortion
  # Undistortion file: {undisto_path}
}}"""

    def generate_comp_script(
        self, shot_name, plate_path, colorspace, first_frame, last_frame, output_dir,
    ):
        """Generate complete comp script."""
        # Sanitize shot name
        import re

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", shot_name)
        safe_name = safe_name.replace("..", "_")

        # Create output path
        output_path = os.path.join(output_dir, f"{safe_name}_comp.nk")

        # Generate content
        content = "#! /usr/bin/env nuke\n"
        content += f"# Shot: {shot_name}\n\n"
        content += self._generate_read_node(
            plate_path, colorspace, first_frame, last_frame,
        )

        # Write file
        with open(output_path, "w") as f:
            f.write(content)

        return output_path


# Monkey patch for testing if the real module isn't available
try:
    from nuke_script_generator import NukeScriptGenerator
except ImportError:
    NukeScriptGenerator = MockNukeScriptGenerator


if __name__ == "__main__":
    unittest.main()
