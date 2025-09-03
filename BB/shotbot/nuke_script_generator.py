"""Generate Nuke scripts with proper Read nodes for plates and undistortion."""

from __future__ import annotations

import atexit
import os
import re
import tempfile
from pathlib import Path


class NukeScriptGenerator:
    """Generate temporary Nuke scripts with proper Read nodes.

    This class tracks temporary files and ensures they are cleaned up
    on program exit to prevent disk space leaks.
    """

    # Track all temporary files created for cleanup
    _temp_files: set[str] = set()
    _cleanup_registered: bool = False

    @classmethod
    def _register_cleanup(cls) -> None:
        """Register cleanup function to run at program exit."""
        if not cls._cleanup_registered:
            atexit.register(cls._cleanup_temp_files)
            cls._cleanup_registered = True

    @classmethod
    def _cleanup_temp_files(cls) -> None:
        """Clean up all temporary files created during session."""
        for temp_file in cls._temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    print(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                print(f"Warning: Could not delete temp file {temp_file}: {e}")
        cls._temp_files.clear()

    @classmethod
    def _track_temp_file(cls, filepath: str) -> str:
        """Track a temporary file for cleanup and return its path."""
        cls._register_cleanup()  # Ensure cleanup is registered
        cls._temp_files.add(filepath)
        return filepath

    @staticmethod
    def _escape_path(path: str) -> str:
        """Escape file path for Nuke script.

        Nuke uses forward slashes even on Windows.
        """
        if not path:
            return ""
        # Convert to forward slashes for Nuke
        return path.replace("\\", "/")

    @staticmethod
    def _detect_frame_range(plate_path: str) -> tuple[int, int]:
        """Detect actual frame range from plate files.

        Returns:
            Tuple of (first_frame, last_frame)
        """
        if not plate_path:
            return 1001, 1100  # Default VFX range

        try:
            plate_dir = Path(plate_path).parent
            if not plate_dir.exists():
                return 1001, 1100

            # Build pattern for frame detection
            base_name = Path(plate_path).name
            # Replace #### or %04d with regex pattern
            pattern = base_name.replace("####", r"(\d{4})").replace("%04d", r"(\d{4})")
            frame_regex = re.compile(pattern)

            frame_numbers: list[int] = []
            for file in plate_dir.iterdir():
                match = frame_regex.match(file.name)
                if match:
                    frame_numbers.append(int(match.group(1)))

            if frame_numbers:
                return min(frame_numbers), max(frame_numbers)

        except Exception as e:
            print(f"Warning: Could not detect frame range: {e}")

        return 1001, 1100

    @staticmethod
    def _detect_colorspace(plate_path: str) -> tuple[str, bool]:
        """Detect colorspace and raw flag from filename or path.

        Returns:
            Tuple of (colorspace, raw_flag)
            For linear plates: ("linear", True)
            For other plates: (colorspace_name, False)
        """
        if not plate_path:
            return "linear", True  # Default to linear raw

        path_lower = plate_path.lower()

        # Linear plates (use raw=true with colorspace="linear")
        if "lin_" in path_lower or "linear" in path_lower:
            return "linear", True

        # Log plates (use raw=false with appropriate colorspace)
        if "logc" in path_lower or "alexa" in path_lower:
            return "logc3ei800", False
        if "log" in path_lower:
            return "log", False

        # Display-referred colorspaces
        if "rec709" in path_lower:
            return "rec709", False
        if "srgb" in path_lower:
            return "sRGB", False

        # Default to linear raw (safest for VFX plates)
        return "linear", True

    @staticmethod
    def _detect_resolution(plate_path: str) -> tuple[int, int]:
        """Detect resolution from path.

        Returns:
            Tuple of (width, height)
        """
        if not plate_path:
            return 4312, 2304  # Default production resolution

        # Look for patterns like 4312x2304 or 1920x1080
        resolution_pattern = re.compile(r"(\d{3,4})[x_](\d{3,4})")
        match = resolution_pattern.search(plate_path)

        if match:
            try:
                width = int(match.group(1))
                height = int(match.group(2))
                # Sanity check
                if 640 <= width <= 8192 and 480 <= height <= 4320:
                    return width, height
            except (ValueError, AttributeError):
                pass

        return 4312, 2304

    @staticmethod
    def create_plate_script(plate_path: str, shot_name: str) -> str | None:
        """Create a Nuke script with a proper Read node for the plate.

        Args:
            plate_path: Path to the plate sequence (with #### or %04d pattern)
            shot_name: Name of the shot for the script

        Returns:
            Path to the temporary .nk script, or None if creation failed
        """
        try:
            # Sanitize shot_name to prevent path traversal
            safe_shot_name = re.sub(r"[^\w\-_]", "_", shot_name)

            # Convert path for Nuke
            nuke_path = NukeScriptGenerator._escape_path(plate_path)
            # Ensure we use %04d format for Nuke
            nuke_path = nuke_path.replace("####", "%04d")

            # Detect frame range
            first_frame, last_frame = NukeScriptGenerator._detect_frame_range(
                plate_path,
            )

            # Detect colorspace and raw flag
            colorspace, use_raw = NukeScriptGenerator._detect_colorspace(plate_path)
            raw_str = "true" if use_raw else "false"

            # Detect resolution
            width, height = NukeScriptGenerator._detect_resolution(plate_path)

            # Create proper Nuke script content
            script_content = f"""#! /usr/local/Nuke16.0v4/nuke-16.0.4 -nx
version 16.0 v4
define_window_layout_xml {{<?xml version="1.0" encoding="UTF-8"?>
<layout version="1.0">
    <window x="0" y="0" w="1920" h="1080" fullscreen="0" screen="0">
        <splitter orientation="1">
            <split size="1214"/>
            <splitter orientation="2">
                <split size="570"/>
                <dock id="" activePageId="Viewer.1">
                    <page id="Viewer.1"/>
                </dock>
                <split size="460"/>
                <dock id="" activePageId="DAG.1">
                    <page id="DAG.1"/>
                </dock>
            </splitter>
            <split size="682"/>
            <dock id="" activePageId="Properties.1">
                <page id="Properties.1"/>
            </dock>
        </splitter>
    </window>
</layout>
}}
Root {{
 inputs 0
 name {safe_shot_name}_plate_comp
 first_frame {first_frame}
 last_frame {last_frame}
 fps 24
 format "{width} {height} 0 0 {width} {height} 1 {safe_shot_name}_format"
 proxy_type scale
 proxy_format "1920 1080 0 0 1920 1080 1 HD_1080"
 proxySetting "if \\[value root.proxy] {{ 960 540 }} else {{ {width} {height} }}"
 colorManagement OCIO
 OCIO_config aces_1.2
 defaultViewerLUT "OCIO LUTs"
 workingSpaceLUT "ACES - ACEScg"
 monitorLut "Rec.709 (ACES)"
 int8Lut "Rec.709 (ACES)"
 int16Lut "Rec.709 (ACES)"
 logLut "Log film emulation (ACES)"
 floatLut linear
}}
Read {{
 inputs 0
 file_type exr
 file "{nuke_path}"
 format "{width} {height} 0 0 {width} {height} 1 {safe_shot_name}_format"
 proxy "{nuke_path}"
 first {first_frame}
 last {last_frame}
 origfirst {first_frame}
 origlast {last_frame}
 origset true
 on_error black
 reload 0
 auto_alpha true
 premultiplied true
 raw {raw_str}
 colorspace "{colorspace}"
 name Read_Plate
 tile_color 0xcccccc01
 label "\\[value colorspace]\\nframes: {first_frame}-{last_frame}"
 selected true
 xpos 0
 ypos -150
}}
Grade {{
 inputs 1
 name Grade_CC
 label "Color Correction"
 xpos 0
 ypos -50
}}
Viewer {{
 frame_range {first_frame}-{last_frame}
 fps 24
 frame {first_frame}
 gain 1
 gamma 1
 name Viewer1
 selected true
 xpos 0
 ypos 50
}}
"""
            # Create temporary file (will be deleted when Nuke closes it)
            # Note: We need delete=False because Nuke needs to read the file
            # But we should track these files for cleanup elsewhere
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".nk",
                prefix=f"{safe_shot_name}_plate_",
                delete=False,  # Required for Nuke to read, but needs cleanup tracking
                encoding="utf-8",
            ) as tmp_file:
                tmp_file.write(script_content)
                temp_path = tmp_file.name

            # Track the file for cleanup at program exit
            return NukeScriptGenerator._track_temp_file(temp_path)

        except Exception as e:
            print(f"Error creating Nuke script: {e}")
            return None

    @staticmethod
    def _import_undistortion_nodes_copy_paste_format(
        undistortion_path: str,
        ypos_offset: int = -200,
    ) -> str:
        """Import content from a copy/paste format undistortion .nk file.

        This handles files that start with 'set cut_paste_input [stack 0]'
        which is Nuke's standard copy/paste format. It imports all content
        except the copy/paste specific boilerplate.

        Args:
            undistortion_path: Path to the undistortion .nk file
            ypos_offset: Y position offset for imported nodes

        Returns:
            String containing the processed content to insert
        """
        import logging
        import re

        logger = logging.getLogger(__name__)

        try:
            logger.debug(
                f"Attempting copy/paste format import from: {undistortion_path}"
            )

            if not Path(undistortion_path).exists():
                logger.error(f"Undistortion file not found: {undistortion_path}")
                return ""

            with open(undistortion_path, encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                logger.error(f"Undistortion file is empty: {undistortion_path}")
                return ""

            lines = content.split("\n")

            # Check if this is copy/paste format
            is_copy_paste_format = False
            for line in lines[:10]:  # Check first 10 lines
                if "set cut_paste_input" in line:
                    is_copy_paste_format = True
                    logger.info("Detected copy/paste format undistortion file")
                    break

            if not is_copy_paste_format:
                logger.debug(
                    "Not copy/paste format, returning empty (main method will handle fallback)"
                )
                return ""

            # Process copy/paste format - import everything except boilerplate
            imported_lines: list[str] = []
            i = 0
            inside_root = False
            root_brace_count = 0
            inside_python = False
            python_brace_count = 0

            while i < len(lines):
                line = lines[i]
                stripped = line.strip()

                # Skip copy/paste boilerplate
                if "set cut_paste_input" in line:
                    logger.debug(f"Skipping copy/paste boilerplate: {line[:50]}")
                    i += 1
                    continue

                # Skip certain push commands that are copy/paste specific
                if stripped.startswith("push"):
                    if "push $cut_paste_input" in line or "push 0" in stripped:
                        logger.debug(f"Skipping copy/paste push: {line[:50]}")
                        i += 1
                        continue
                    # Keep other push commands as they might be connection management

                # Skip version line (will be in main script already)
                if stripped.startswith("version "):
                    logger.debug(f"Skipping version line: {stripped[:50]}")
                    i += 1
                    continue

                # Skip Root node and its contents (would conflict)
                if not inside_root and (
                    stripped.startswith("Root {") or stripped == "Root {"
                ):
                    logger.debug("Found Root node, skipping its contents")
                    inside_root = True
                    root_brace_count = 1
                    i += 1
                    continue

                # If inside Root node, track braces and skip content
                if inside_root:
                    if "{" in line:
                        root_brace_count += line.count("{")
                    if "}" in line:
                        root_brace_count -= line.count("}")

                    if root_brace_count <= 0:
                        inside_root = False
                        logger.debug("Finished skipping Root node")
                    i += 1
                    continue

                # Apply ypos offset if this line contains ypos
                if "ypos" in line and ypos_offset != 0:
                    ypos_pattern = re.compile(r"ypos\s+(-?\d+)")

                    def adjust_ypos(match: re.Match[str]) -> str:
                        old_ypos = int(match.group(1))
                        new_ypos = old_ypos + ypos_offset
                        return f"ypos {new_ypos}"

                    adjusted_line = ypos_pattern.sub(adjust_ypos, line)
                    if adjusted_line != line:
                        logger.debug(f"Adjusted ypos in line: {stripped[:50]}...")
                        line = adjusted_line

                # Handle Python blocks - strip indentation from Python code
                if not inside_python and stripped.startswith("python {"):
                    inside_python = True
                    python_brace_count = 1
                    # Import the python block opening WITHOUT indentation
                    imported_lines.append("python {")
                    logger.debug("Entering Python block in copy/paste format")
                    i += 1
                    continue

                # If inside Python block, handle Python code properly
                if inside_python:
                    if "{" in line:
                        python_brace_count += line.count("{")
                    if "}" in line:
                        python_brace_count -= line.count("}")
                    
                    if python_brace_count <= 0:
                        inside_python = False
                        logger.debug("Exiting Python block in copy/paste format")
                        # Import the closing brace with no indentation
                        imported_lines.append("}")
                    else:
                        # For Python code, use same logic as standard format
                        if stripped:  # Non-empty line
                            indent_count = len(line) - len(line.lstrip())
                            
                            # Top-level Python statements should have NO indentation
                            if stripped.startswith(('import ', 'from ', 'def ', 'class ')):
                                imported_lines.append(stripped)
                            else:
                                # Preserve relative indentation for nested blocks
                                if indent_count >= 5:
                                    dedented = line[5:] if len(line) > 5 else line.lstrip()
                                elif indent_count == 4:
                                    dedented = line[4:]
                                else:
                                    dedented = line.lstrip()
                                imported_lines.append(dedented)
                            
                            if imported_lines[-1] != line:
                                logger.debug(f"Dedented Python line in copy/paste: {imported_lines[-1][:50]}...")
                        else:
                            # Empty line in Python block
                            imported_lines.append("")
                    i += 1
                    continue

                # Import this line normally (not in Python block)
                imported_lines.append(line)
                i += 1

            # Join the imported content
            imported_content = "\n".join(imported_lines).strip()

            if imported_content:
                result = (
                    "\n# Imported undistortion content from copy/paste format\n"
                    + "# "
                    + undistortion_path
                    + "\n"
                    + imported_content
                    + "\n"
                )
                logger.info(
                    f"Successfully imported copy/paste content ({len(result)} characters)"
                )
                return result

            logger.warning("No content found to import")
            return ""

        except Exception as e:
            logger.error(f"Error importing copy/paste format: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return ""

    @staticmethod
    def _import_undistortion_nodes(
        undistortion_path: str,
        ypos_offset: int = -200,
    ) -> str:
        """Import ALL content from an undistortion .nk file.

        This method imports the entire content of the .nk file, excluding only
        the parts that would conflict with the main script (Root node, version, etc).

        Args:
            undistortion_path: Path to the undistortion .nk file
            ypos_offset: Y position offset for imported nodes

        Returns:
            String containing the processed content to insert
        """
        import logging
        import re

        logger = logging.getLogger(__name__)

        try:
            logger.debug(f"Starting undistortion import from: {undistortion_path}")

            # Check if file exists
            undistortion_file = Path(undistortion_path)
            if not undistortion_file.exists():
                logger.error(f"Undistortion file not found: {undistortion_path}")
                return ""

            logger.debug(f"File exists, size: {undistortion_file.stat().st_size} bytes")

            with open(undistortion_path, encoding="utf-8") as f:
                content = f.read()

            logger.debug(
                f"Successfully read file, content length: {len(content)} characters"
            )

            if not content.strip():
                logger.error(f"Undistortion file is empty: {undistortion_path}")
                return ""

            logger.debug(f"File content preview (first 200 chars): {content[:200]}")

            # Process the file content - we'll import everything except conflicting sections
            lines = content.split("\n")
            imported_lines: list[str] = []
            i = 0
            inside_root = False
            root_brace_count = 0
            inside_python = False
            python_brace_count = 0

            logger.debug(f"Processing {len(lines)} lines")

            while i < len(lines):
                line = lines[i]
                stripped = line.strip()

                # Skip version line (will be in main script already)
                if stripped.startswith("version "):
                    logger.debug(f"Skipping version line: {stripped[:50]}")
                    i += 1
                    continue

                # Skip shebang line
                if stripped.startswith("#!"):
                    logger.debug("Skipping shebang line")
                    i += 1
                    continue

                # Skip window layout definition (conflicts with main script)
                if stripped.startswith("define_window_layout"):
                    logger.debug("Skipping window layout definition")
                    # Skip until we find the closing brace
                    brace_count = 1
                    i += 1
                    while i < len(lines) and brace_count > 0:
                        if "{" in lines[i]:
                            brace_count += lines[i].count("{")
                        if "}" in lines[i]:
                            brace_count -= lines[i].count("}")
                        i += 1
                    continue

                # Handle Root node - skip it and its contents
                if not inside_root and (
                    stripped.startswith("Root {") or stripped == "Root {"
                ):
                    logger.debug("Found Root node, skipping its contents")
                    inside_root = True
                    root_brace_count = 1
                    i += 1
                    continue

                # If inside Root node, track braces and skip content
                if inside_root:
                    if "{" in line:
                        root_brace_count += line.count("{")
                    if "}" in line:
                        root_brace_count -= line.count("}")

                    if root_brace_count <= 0:
                        inside_root = False
                        logger.debug("Finished skipping Root node")
                    i += 1
                    continue

                # Apply ypos offset if this line contains ypos
                if "ypos" in line and ypos_offset != 0:
                    # Find all ypos values in the line and adjust them
                    ypos_pattern = re.compile(r"ypos\s+(-?\d+)")

                    def adjust_ypos(match: re.Match[str]) -> str:
                        old_ypos = int(match.group(1))
                        new_ypos = old_ypos + ypos_offset
                        return f"ypos {new_ypos}"

                    adjusted_line = ypos_pattern.sub(adjust_ypos, line)
                    if adjusted_line != line:
                        logger.debug(f"Adjusted ypos in line: {stripped[:50]}...")
                        line = adjusted_line

                # Skip copy/paste specific lines even in standard format
                # (sometimes files contain these without being full copy/paste format)
                if "set cut_paste_input" in line:
                    logger.debug(f"Skipping copy/paste init line: {stripped[:50]}...")
                    i += 1
                    continue

                if stripped.startswith("push") and (
                    "push $cut_paste_input" in line or "push 0" in stripped
                ):
                    logger.debug(f"Skipping copy/paste push: {stripped[:50]}...")
                    i += 1
                    continue

                # Handle Python blocks - strip indentation from Python code
                if not inside_python and stripped.startswith("python {"):
                    inside_python = True
                    python_brace_count = 1
                    # Import the python block opening WITHOUT indentation
                    imported_lines.append("python {")
                    logger.debug("Entering Python block")
                    i += 1
                    continue

                # If inside Python block, handle Python code properly
                if inside_python:
                    if "{" in line:
                        python_brace_count += line.count("{")
                    if "}" in line:
                        python_brace_count -= line.count("}")
                    
                    if python_brace_count <= 0:
                        inside_python = False
                        logger.debug("Exiting Python block")
                        # Import the closing brace with no indentation 
                        imported_lines.append("}")
                    else:
                        # For Python code, we need to intelligently strip base indentation
                        if stripped:  # Non-empty line
                            # Find how much the line is indented
                            indent_count = len(line) - len(line.lstrip())
                            
                            # For the first non-comment Python line (like 'import'), 
                            # ALL indentation should be removed since Python code starts at column 0
                            if stripped.startswith(('import ', 'from ', 'def ', 'class ')):
                                # This is a top-level Python statement - remove ALL leading whitespace
                                imported_lines.append(stripped)
                            else:
                                # For other lines, try to preserve relative indentation
                                # Detect the base indentation (usually the amount before 'import')
                                # and remove that amount from all lines
                                
                                # Common patterns: lines might have 4, 5, 8, or 9+ spaces
                                # We want to strip the "base" amount but keep Python indentation
                                if indent_count > 0:
                                    # Remove spaces up to the first Python content
                                    # Heuristic: if it has 5+ spaces, first 5 are Nuke indent
                                    if indent_count >= 5:
                                        # Likely pattern: 1 space (Group) + 4 spaces (python block)
                                        dedented = line[5:] if len(line) > 5 else line.lstrip()
                                    elif indent_count == 4:
                                        # Standard 4-space indent - remove it
                                        dedented = line[4:]
                                    else:
                                        # Less indentation - just strip it
                                        dedented = line.lstrip()
                                    imported_lines.append(dedented)
                                else:
                                    imported_lines.append(stripped)
                            
                            logger.debug(f"Processed Python line: {imported_lines[-1][:50]}...")
                        else:
                            # Empty line in Python block
                            imported_lines.append("")
                    i += 1
                    continue

                # Import this line normally (not in Python block)
                imported_lines.append(line)
                i += 1

            # Join the imported lines
            imported_content = "\n".join(imported_lines).strip()

            if imported_content:
                result = (
                    "\n# Imported undistortion content from "
                    + undistortion_path
                    + "\n"
                    + imported_content
                    + "\n"
                )
                logger.info(
                    f"Successfully imported undistortion content ({len(result)} characters)"
                )
                return result

            logger.warning("No content to import after filtering")
            return ""

        except FileNotFoundError:
            logger.error(f"Undistortion file not found: {undistortion_path}")
            return ""
        except UnicodeDecodeError as e:
            logger.error(f"Could not decode undistortion file {undistortion_path}: {e}")
            return ""
        except Exception as e:
            logger.error(
                f"Unexpected error importing undistortion from {undistortion_path}: {e}"
            )
            import traceback

            logger.debug(f"Full traceback: {traceback.format_exc()}")
            return ""

    @staticmethod
    def debug_undistortion_file(undistortion_path: str) -> None:
        """Debug function to analyze undistortion .nk file structure.

        This function analyzes an undistortion file and reports what will be imported,
        which is useful for troubleshooting import issues.

        Args:
            undistortion_path: Path to the undistortion .nk file to analyze
        """
        try:
            if not Path(undistortion_path).exists():
                print(f"ERROR: File does not exist: {undistortion_path}")
                return

            print(f"\n=== DEBUG ANALYSIS: {undistortion_path} ===")

            with open(undistortion_path, encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                print("ERROR: File is empty")
                return

            lines = content.split("\n")
            print(f"File has {len(lines)} lines, {len(content)} characters")

            # Analyze what will be skipped vs imported
            skipped_lines = 0
            imported_lines = 0
            root_lines = 0
            version_lines = 0
            shebang_lines = 0
            window_layout_lines = 0

            # Track if file is copy/paste format
            is_copy_paste = False
            for line in lines[:10]:
                if "set cut_paste_input" in line:
                    is_copy_paste = True
                    break

            if is_copy_paste:
                print(
                    "\nFile Format: Copy/Paste format (contains 'set cut_paste_input')"
                )
            else:
                print("\nFile Format: Standard .nk format")

            # Simulate the import logic
            inside_root = False
            root_brace_count = 0
            inside_window_layout = False
            window_brace_count = 0

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Track what would be skipped
                if stripped.startswith("#!"):
                    shebang_lines += 1
                    skipped_lines += 1
                elif stripped.startswith("version "):
                    version_lines += 1
                    skipped_lines += 1
                elif stripped.startswith("define_window_layout"):
                    inside_window_layout = True
                    window_brace_count = 1
                    window_layout_lines += 1
                    skipped_lines += 1
                elif inside_window_layout:
                    window_layout_lines += 1
                    skipped_lines += 1
                    if "{" in line:
                        window_brace_count += line.count("{")
                    if "}" in line:
                        window_brace_count -= line.count("}")
                    if window_brace_count <= 0:
                        inside_window_layout = False
                elif not inside_root and (
                    stripped.startswith("Root {") or stripped == "Root {"
                ):
                    inside_root = True
                    root_brace_count = 1
                    root_lines += 1
                    skipped_lines += 1
                elif inside_root:
                    root_lines += 1
                    skipped_lines += 1
                    if "{" in line:
                        root_brace_count += line.count("{")
                    if "}" in line:
                        root_brace_count -= line.count("}")
                    if root_brace_count <= 0:
                        inside_root = False
                elif is_copy_paste and "set cut_paste_input" in line:
                    skipped_lines += 1
                elif (
                    is_copy_paste
                    and stripped.startswith("push")
                    and ("push $cut_paste_input" in line or "push 0" in stripped)
                ):
                    skipped_lines += 1
                else:
                    # This line would be imported
                    imported_lines += 1

            print("\nImport Analysis:")
            print(f"  Lines to import: {imported_lines}")
            print(f"  Lines to skip: {skipped_lines}")
            print(f"    - Shebang lines: {shebang_lines}")
            print(f"    - Version lines: {version_lines}")
            print(f"    - Window layout lines: {window_layout_lines}")
            print(f"    - Root node lines: {root_lines}")
            if is_copy_paste:
                print(
                    f"    - Copy/paste boilerplate: {skipped_lines - shebang_lines - version_lines - window_layout_lines - root_lines}"
                )

            # Try the actual import to see what happens
            print("\n=== IMPORT TEST ===")

            # Test both parsers
            if is_copy_paste:
                print("Testing copy/paste format parser...")
                result = (
                    NukeScriptGenerator._import_undistortion_nodes_copy_paste_format(
                        undistortion_path
                    )
                )
            else:
                print("Testing standard format parser...")
                result = NukeScriptGenerator._import_undistortion_nodes(
                    undistortion_path
                )

            if result:
                print(f"SUCCESS: Import returned {len(result)} characters")
                print("\nFirst 400 characters of imported content:")
                print("-" * 40)
                print(result[:400] + "..." if len(result) > 400 else result)
                print("-" * 40)
            else:
                print("FAILED: Import returned empty string")
                print("\nTrying alternate parser as fallback...")
                if is_copy_paste:
                    result = NukeScriptGenerator._import_undistortion_nodes(
                        undistortion_path
                    )
                else:
                    result = NukeScriptGenerator._import_undistortion_nodes_copy_paste_format(
                        undistortion_path
                    )

                if result:
                    print(f"FALLBACK SUCCESS: Got {len(result)} characters")
                else:
                    print("FALLBACK FAILED: Still empty")

        except Exception as e:
            print(f"ERROR analyzing file: {e}")
            import traceback

            print(traceback.format_exc())

    @staticmethod
    def create_loader_script(
        plate_path: str,
        undistortion_path: str,
        shot_name: str,
    ) -> str | None:
        """Create a minimal Nuke loader script that uses Nuke's Python API.

        This method creates a simple script that loads both the plate and undistortion
        using Nuke's built-in scriptSource() command, which properly handles all node
        types and dependencies without parsing.

        Args:
            plate_path: Path to the plate sequence
            undistortion_path: Path to undistortion .nk file
            shot_name: Name of the shot

        Returns:
            Path to the temporary loader script, or None on error
        """
        try:
            # Sanitize shot_name to prevent path traversal
            safe_shot_name = re.sub(r"[^\w\-_]", "_", shot_name)

            # Convert paths for Nuke
            nuke_plate_path = NukeScriptGenerator._escape_path(plate_path)
            nuke_plate_path = nuke_plate_path.replace("####", "%04d")
            nuke_undist_path = NukeScriptGenerator._escape_path(undistortion_path)

            # Detect properties
            first_frame, last_frame = NukeScriptGenerator._detect_frame_range(
                plate_path
            )
            width, height = NukeScriptGenerator._detect_resolution(plate_path)
            colorspace, use_raw = NukeScriptGenerator._detect_colorspace(plate_path)
            raw_str = "true" if use_raw else "false"

            # Create a minimal loader script that uses Python to import everything
            script_content = f"""#! /usr/local/Nuke16.0v4/nuke-16.0.4 -nx
version 16.0 v4

# Loader script for {safe_shot_name}
# This script loads the plate and sources the undistortion file

Root {{
 inputs 0
 name {safe_shot_name}_comp_loader
 frame {first_frame}
 first_frame {first_frame}
 last_frame {last_frame}
 fps 24
 format "{width} {height} 0 0 {width} {height} 1 {safe_shot_name}_format"
 proxy_type scale
 proxy_format "1920 1080 0 0 1920 1080 1 HD_1080"
 colorManagement OCIO
 OCIO_config aces_1.2
 defaultViewerLUT "OCIO LUTs"
 workingSpaceLUT "ACES - ACEScg"
 monitorLut "Rec.709 (ACES)"
 int8Lut "Rec.709 (ACES)"
 int16Lut "Rec.709 (ACES)"
 logLut "Log film emulation (ACES)"
 floatLut linear
}}

# Create plate Read node
Read {{
 inputs 0
 file_type exr
 file "{nuke_plate_path}"
 format "{width} {height} 0 0 {width} {height} 1 {safe_shot_name}_format"
 proxy "{nuke_plate_path}"
 first {first_frame}
 last {last_frame}
 origfirst {first_frame}
 origlast {last_frame}
 origset true
 on_error black
 reload 0
 auto_alpha true
 premultiplied true
 raw {raw_str}
 colorspace "{colorspace}"
 name Read_Plate
 tile_color 0xcccccc01
 label "Raw Plate\\n\\[value colorspace]\\nframes: {first_frame}-{last_frame}"
 selected true
 xpos 0
 ypos -300
}}

# Python script to source the undistortion file
# This executes when the script loads
python {{
import nuke
import os

# Path to undistortion file
undist_file = r"{nuke_undist_path}"

# Check if file exists before sourcing
if os.path.exists(undist_file):
    try:
        # Source the undistortion file - this properly imports all nodes
        nuke.scriptSource(undist_file)
        
        # Connect the first imported node to Read_Plate if possible
        # The imported nodes will be selected after scriptSource
        imported_nodes = nuke.selectedNodes()
        if imported_nodes:
            # Find the first node that can accept inputs
            for node in imported_nodes:
                if node.maxInputs() > 0 and node.input(0) is None:
                    try:
                        node.setInput(0, nuke.toNode("Read_Plate"))
                        break
                    except:
                        pass
                        
        nuke.message("Undistortion imported from:\\n" + undist_file)
    except Exception as e:
        nuke.message("Error importing undistortion:\\n" + str(e))
else:
    nuke.message("Undistortion file not found:\\n" + undist_file)
}}

# Add a note about the undistortion source
StickyNote {{
 inputs 0
 name Note_Undistortion_Source
 label "Undistortion imported from:\\n{nuke_undist_path}"
 note_font_size 14
 note_font_color 0x00aa00ff
 xpos 200
 ypos -300
}}

Viewer {{
 inputs 1
 frame {first_frame}
 frame_range {first_frame}-{last_frame}
 fps 24
 name Viewer1
 selected true
 xpos 0
 ypos 100
}}
"""

            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".nk",
                prefix=f"{safe_shot_name}_loader_",
                delete=False,
                encoding="utf-8",
            ) as tmp_file:
                tmp_file.write(script_content)
                temp_path = tmp_file.name

            # Track temp file for cleanup
            NukeScriptGenerator._track_temp_file(temp_path)

            print(f"Created Nuke loader script: {temp_path}")
            print(f"  Plate: {plate_path}")
            print(f"  Undistortion: {undistortion_path}")

            return temp_path

        except Exception as e:
            print(f"Error creating loader script: {e}")
            return None

    @staticmethod
    def create_plate_script_with_undistortion(
        plate_path: str,
        undistortion_path: str | None,
        shot_name: str,
    ) -> str | None:
        """Create a Nuke script with plate and optional undistortion.

        This version properly imports the undistortion nodes from the .nk file
        and integrates them into the compositing graph.

        Args:
            plate_path: Path to the plate sequence (can be empty)
            undistortion_path: Path to undistortion .nk file (optional)
            shot_name: Name of the shot

        Returns:
            Path to the temporary .nk script
        """
        try:
            # Sanitize shot_name to prevent path traversal
            safe_shot_name = re.sub(r"[^\w\-_]", "_", shot_name)

            # Handle empty or None paths
            plate_path = plate_path or ""
            undistortion_path = undistortion_path or ""

            # Convert paths for Nuke
            nuke_plate_path = NukeScriptGenerator._escape_path(plate_path)
            nuke_plate_path = nuke_plate_path.replace("####", "%04d")

            # Detect properties
            first_frame, last_frame = NukeScriptGenerator._detect_frame_range(
                plate_path,
            )
            width, height = NukeScriptGenerator._detect_resolution(plate_path)
            colorspace, use_raw = NukeScriptGenerator._detect_colorspace(plate_path)
            raw_str = "true" if use_raw else "false"

            # Create enhanced Nuke script content
            script_content = f"""#! /usr/local/Nuke16.0v4/nuke-16.0.4 -nx
version 16.0 v4
define_window_layout_xml {{<?xml version="1.0" encoding="UTF-8"?>
<layout version="1.0">
    <window x="0" y="0" w="1920" h="1080" fullscreen="0" screen="0">
        <splitter orientation="1">
            <split size="1214"/>
            <splitter orientation="2">
                <split size="570"/>
                <dock id="" activePageId="Viewer.1">
                    <page id="Viewer.1"/>
                </dock>
                <split size="460"/>
                <dock id="" activePageId="DAG.1" focus="true">
                    <page id="DAG.1"/>
                </dock>
            </splitter>
            <split size="682"/>
            <dock id="" activePageId="Properties.1">
                <page id="Properties.1"/>
            </dock>
        </splitter>
    </window>
</layout>
}}
Root {{
 inputs 0
 name {safe_shot_name}_comp
 frame {first_frame}
 first_frame {first_frame}
 last_frame {last_frame}
 fps 24
 format "{width} {height} 0 0 {width} {height} 1 {safe_shot_name}_format"
 proxy_type scale
 proxy_format "1920 1080 0 0 1920 1080 1 HD_1080"
 colorManagement OCIO
 OCIO_config aces_1.2
 defaultViewerLUT "OCIO LUTs"
 workingSpaceLUT "ACES - ACEScg"
 monitorLut "Rec.709 (ACES)"
 int8Lut "Rec.709 (ACES)"
 int16Lut "Rec.709 (ACES)"
 logLut "Log film emulation (ACES)"
 floatLut linear
}}
"""

            # Add plate Read node if path provided
            if plate_path and nuke_plate_path:
                script_content += f"""
Read {{
 inputs 0
 file_type exr
 file "{nuke_plate_path}"
 format "{width} {height} 0 0 {width} {height} 1 {safe_shot_name}_format"
 proxy "{nuke_plate_path}"
 first {first_frame}
 last {last_frame}
 origfirst {first_frame}
 origlast {last_frame}
 origset true
 on_error black
 reload 0
 auto_alpha true
 premultiplied true
 raw {raw_str}
 colorspace "{colorspace}"
 name Read_Plate
 tile_color 0xcccccc01
 label "Raw Plate\\n\\[value colorspace]\\nframes: {first_frame}-{last_frame}"
 selected true
 xpos 0
 ypos -300
}}
"""

            # Import undistortion nodes if provided
            if undistortion_path and Path(undistortion_path).exists():
                import logging

                logger = logging.getLogger(__name__)
                logger.info(
                    f"Attempting to import undistortion nodes from: {undistortion_path}"
                )

                # Try copy/paste format first (most common for undistortion files)
                imported_nodes = (
                    NukeScriptGenerator._import_undistortion_nodes_copy_paste_format(
                        undistortion_path,
                        ypos_offset=-200,
                    )
                )

                # If copy/paste format failed, try the standard parser
                if not imported_nodes:
                    logger.info(
                        "Copy/paste format parser returned empty result, trying standard parser as fallback"
                    )
                    imported_nodes = NukeScriptGenerator._import_undistortion_nodes(
                        undistortion_path,
                        ypos_offset=-200,
                    )

                if imported_nodes:
                    logger.info("Successfully imported undistortion nodes into script")
                    # Fix the first node to connect to Read_Plate (if it exists)
                    # and ensure proper chaining
                    if plate_path and nuke_plate_path:
                        # Connect first undistortion node to Read_Plate
                        imported_nodes = imported_nodes.replace(
                            "inputs 0",
                            "inputs 1",
                            1,
                        )
                        logger.debug("Connected first undistortion node to Read_Plate")

                    script_content += imported_nodes
                    script_content += f"""
# Reference to original undistortion file
StickyNote {{
 inputs 0
 name Note_Undistortion_Source
 label "Undistortion imported from:\\n{NukeScriptGenerator._escape_path(undistortion_path)}"
 note_font_size 14
 note_font_color 0x00aa00ff
 xpos 200
 ypos -300
}}
"""
                else:
                    # Fallback to reference if import failed
                    logger.warning(
                        f"Failed to import undistortion nodes from {undistortion_path}, creating reference note instead"
                    )
                    escaped_undist_path = NukeScriptGenerator._escape_path(
                        undistortion_path,
                    )
                    script_content += f"""
# Undistortion available: {escaped_undist_path}
StickyNote {{
 inputs 0
 name Note_Undistortion
 label "UNDISTORTION AVAILABLE\\nFile > Import Script:\\n{escaped_undist_path}"
 note_font_size 16
 note_font_color 0xff8800ff
 xpos 200
 ypos -300
}}
"""
            elif undistortion_path:
                import logging

                logger = logging.getLogger(__name__)
                logger.error(
                    f"Undistortion path provided but file does not exist: {undistortion_path}"
                )

            # Add viewer and other nodes
            script_content += f"""
Viewer {{
 inputs 1
 frame {first_frame}
 frame_range {first_frame}-{last_frame}
 fps 24
 name Viewer1
 selected true
 xpos 0
 ypos 100
}}
"""

            # Create temporary file (will be deleted when Nuke closes it)
            # Note: We need delete=False because Nuke needs to read the file
            # But we should track these files for cleanup elsewhere
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".nk",
                prefix=f"{safe_shot_name}_comp_",
                delete=False,  # Required for Nuke to read, but needs cleanup tracking
                encoding="utf-8",
            ) as tmp_file:
                tmp_file.write(script_content)
                temp_path = tmp_file.name

            # Track the file for cleanup at program exit
            return NukeScriptGenerator._track_temp_file(temp_path)

        except Exception as e:
            print(f"Error creating Nuke script with undistortion: {e}")
            return None

    @staticmethod
    def _generate_read_node(
        file_path: str,
        colorspace: str | None,
        first_frame: int,
        last_frame: int,
    ) -> str:
        """Generate a Read node with proper colorspace quoting.

        Args:
            file_path: Path to the input file/sequence
            colorspace: Colorspace name (will be quoted if contains spaces)
            first_frame: First frame number
            last_frame: Last frame number

        Returns:
            String containing the Read node definition

        Raises:
            ValueError: If frame range is invalid
        """
        # Validate frame range
        if first_frame > last_frame:
            raise ValueError(f"Invalid frame range: {first_frame} to {last_frame}")

        # Escape and quote file path for Nuke
        nuke_path = NukeScriptGenerator._escape_path(file_path)

        # Handle colorspace - always quote for consistency and safety
        if colorspace and colorspace.strip():
            colorspace_line = f'colorspace "{colorspace.strip()}"'
        else:
            colorspace_line = 'colorspace "linear"'  # Default fallback

        return f"""Read {{
 inputs 0
 file_type exr
 file "{nuke_path}"
 {colorspace_line}
 first {first_frame}
 last {last_frame}
 origfirst {first_frame}
 origlast {last_frame}
 origset true
 on_error black
 reload 0
 auto_alpha true
 premultiplied true
 name Read1
 selected true
}}"""

    @staticmethod
    def _generate_write_node(output_path: str) -> str:
        """Generate a Write node for output.

        Args:
            output_path: Path for output file/sequence

        Returns:
            String containing the Write node definition
        """
        # Escape path for Nuke
        nuke_path = NukeScriptGenerator._escape_path(output_path)

        return f"""Write {{
 file_type exr
 file "{nuke_path}"
 colorspace "ACES - ACEScg"
 datatype "16 bit half"
 compression "Zip (1 scanline)"
 interleave "channels"
 autocrop false
 create_directories true
 name Write1
 selected true
}}"""

    @staticmethod
    def _generate_undistortion_node(undisto_path: str) -> str:
        """Generate an undistortion group node.

        Args:
            undisto_path: Path to undistortion .nk file

        Returns:
            String containing the undistortion Group node
        """
        escaped_path = NukeScriptGenerator._escape_path(undisto_path)

        return f"""Group {{
 name Undistortion
 tile_color 0xcc804eff
 note_font_size 11
 note_font_color 0xffffffff
 # Undistortion file: {escaped_path}
 addUserKnob {{26 info_line l "Undistortion Info:"}}
 addUserKnob {{26 source_file l "Source File:" T "{escaped_path}"}}
 addUserKnob {{22 reload_undisto l "Reload Undistortion" -STARTLINE T "# Placeholder for undistortion reload logic"}}
}}"""

    @staticmethod
    def generate_comp_script(
        shot_name: str,
        plate_path: str,
        colorspace: str,
        first_frame: int,
        last_frame: int,
        output_dir: str,
    ) -> str | None:
        """Generate a complete comp script with Read and Write nodes.

        Args:
            shot_name: Name of the shot for filename and script metadata
            plate_path: Path to input plate sequence
            colorspace: Colorspace for the plate
            first_frame: First frame of the sequence
            last_frame: Last frame of the sequence
            output_dir: Directory to save the script

        Returns:
            Path to the generated .nk script file, or None if failed
        """
        try:
            import os
            import re

            # Sanitize shot name to prevent path traversal
            safe_shot_name = re.sub(r"[^\w\-_]", "_", shot_name)
            safe_shot_name = safe_shot_name.replace("..", "_")  # Extra safety

            # Create output script path
            script_filename = f"{safe_shot_name}_comp.nk"
            output_path = os.path.join(output_dir, script_filename)

            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Generate script content
            width, height = NukeScriptGenerator._detect_resolution(plate_path)

            script_content = f"""#! /usr/local/Nuke16.0v4/nuke-16.0.4 -nx
version 16.0 v4
# Shot: {shot_name}
# Generated by ShotBot NukeScriptGenerator

Root {{
 inputs 0
 name {safe_shot_name}_comp
 frame {first_frame}
 first_frame {first_frame}
 last_frame {last_frame}
 fps 24
 format "{width} {height} 0 0 {width} {height} 1 {safe_shot_name}_format"
 proxy_type scale
 proxy_format "1920 1080 0 0 1920 1080 1 HD_1080"
 colorManagement OCIO
 OCIO_config aces_1.2
 defaultViewerLUT "OCIO LUTs"
 workingSpaceLUT "ACES - ACEScg"
 monitorLut "Rec.709 (ACES)"
 int8Lut "Rec.709 (ACES)"
 int16Lut "Rec.709 (ACES)"
 logLut "Log film emulation (ACES)"
 floatLUT linear
}}

{NukeScriptGenerator._generate_read_node(plate_path, colorspace, first_frame, last_frame)}

Grade {{
 inputs 1
 name Grade_CC
 label "Color Correction"
 selected true
 xpos 0
 ypos 50
}}

{NukeScriptGenerator._generate_write_node(f"{output_dir}/comp_output.%04d.exr")}

Viewer {{
 inputs 1
 frame_range {first_frame}-{last_frame}
 fps 24
 frame {first_frame}
 name Viewer1
 selected true
 xpos 0
 ypos 200
}}
"""

            # Write the script file
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(script_content)

            print(f"Generated comp script: {output_path}")
            return output_path

        except Exception as e:
            print(f"Error generating comp script: {e}")
            return None
