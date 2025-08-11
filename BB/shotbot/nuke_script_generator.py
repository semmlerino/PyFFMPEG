"""Generate Nuke scripts with proper Read nodes for plates and undistortion."""

import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple


class NukeScriptGenerator:
    """Generate temporary Nuke scripts with proper Read nodes."""

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
    def _detect_frame_range(plate_path: str) -> Tuple[int, int]:
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

            frame_numbers = []
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
    def _detect_colorspace(plate_path: str) -> str:
        """Detect colorspace from filename or path.

        Returns appropriate OCIO colorspace name for Nuke.
        """
        if not plate_path:
            return "scene_linear"

        path_lower = plate_path.lower()

        # ACES colorspaces
        if "aces" in path_lower or "acescg" in path_lower:
            return "ACES - ACEScg"
        elif "lin_sgamut3cine" in path_lower or "sgamut" in path_lower:
            return "Input - Sony - S-Gamut3.Cine - Linear"
        elif "rec709" in path_lower:
            return "Output - Rec.709"
        elif "srgb" in path_lower:
            return "Output - sRGB"
        elif "lin_" in path_lower or "linear" in path_lower:
            return "scene_linear"
        else:
            return "scene_linear"  # Safe default

    @staticmethod
    def _detect_resolution(plate_path: str) -> Tuple[int, int]:
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
    def create_plate_script(plate_path: str, shot_name: str) -> Optional[str]:
        """Create a Nuke script with a proper Read node for the plate.

        Args:
            plate_path: Path to the plate sequence (with #### or %04d pattern)
            shot_name: Name of the shot for the script

        Returns:
            Path to the temporary .nk script, or None if creation failed
        """
        try:
            # Convert path for Nuke
            nuke_path = NukeScriptGenerator._escape_path(plate_path)
            # Ensure we use %04d format for Nuke
            nuke_path = nuke_path.replace("####", "%04d")

            # Detect frame range
            first_frame, last_frame = NukeScriptGenerator._detect_frame_range(
                plate_path
            )

            # Detect colorspace
            colorspace = NukeScriptGenerator._detect_colorspace(plate_path)

            # Detect resolution
            width, height = NukeScriptGenerator._detect_resolution(plate_path)

            # Create proper Nuke script content
            script_content = f"""#! /usr/local/Nuke15.1v2/nuke-15.1.2 -nx
version 15.1 v2
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
 name {shot_name}_plate_comp
 first_frame {first_frame}
 last_frame {last_frame}
 fps 24
 format "{width} {height} 0 0 {width} {height} 1 {shot_name}_format"
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
 format "{width} {height} 0 0 {width} {height} 1 square_pixels"
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
 raw false
 colorspace {colorspace}
 name Read_Plate
 label "\\\\[value colorspace]\\\\nframes: {first_frame}-{last_frame}"
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
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".nk",
                prefix=f"{shot_name}_plate_",
                delete=False,
                encoding="utf-8",
            ) as tmp_file:
                tmp_file.write(script_content)
                return tmp_file.name

        except Exception as e:
            print(f"Error creating Nuke script: {e}")
            return None

    @staticmethod
    def create_plate_script_with_undistortion(
        plate_path: str, undistortion_path: Optional[str], shot_name: str
    ) -> Optional[str]:
        """Create a Nuke script with plate and optional undistortion.

        This version properly handles undistortion by embedding instructions
        rather than trying to use incorrect Read node syntax.

        Args:
            plate_path: Path to the plate sequence (can be empty)
            undistortion_path: Path to undistortion .nk file (optional)
            shot_name: Name of the shot

        Returns:
            Path to the temporary .nk script
        """
        try:
            # Handle empty or None paths
            plate_path = plate_path or ""
            undistortion_path = undistortion_path or ""

            # Convert paths for Nuke
            nuke_plate_path = NukeScriptGenerator._escape_path(plate_path)
            nuke_plate_path = nuke_plate_path.replace("####", "%04d")
            nuke_undist_path = NukeScriptGenerator._escape_path(undistortion_path)

            # Detect properties
            first_frame, last_frame = NukeScriptGenerator._detect_frame_range(
                plate_path
            )
            width, height = NukeScriptGenerator._detect_resolution(plate_path)
            colorspace = NukeScriptGenerator._detect_colorspace(plate_path)

            # Create enhanced Nuke script content
            script_content = f"""#! /usr/local/Nuke15.1v2/nuke-15.1.2 -nx
version 15.1 v2
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
 name {shot_name}_comp
 frame {first_frame}
 first_frame {first_frame}
 last_frame {last_frame}
 fps 24
 format "{width} {height} 0 0 {width} {height} 1 {shot_name}_format"
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
 format "{width} {height} 0 0 {width} {height} 1 square_pixels"
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
 raw false
 colorspace {colorspace}
 name Read_Plate
 label "Raw Plate\\\\n\\\\[value colorspace]\\\\nframes: {first_frame}-{last_frame}"
 selected true
 xpos 0
 ypos -300
}}
"""

            # Add undistortion handling if provided
            if undistortion_path and Path(undistortion_path).exists():
                # Instead of trying to import with Read node, we'll add a StickyNote
                # with instructions and potentially embed the undistortion nodes
                script_content += f"""
StickyNote {{
 inputs 0
 name StickyNote_Undistortion
 label "UNDISTORTION AVAILABLE"
 note_font "Helvetica Bold"
 note_font_size 24
 note_font_color 0xff0000ff
 xpos 200
 ypos -300
}}
BackdropNode {{
 inputs 0
 name Backdrop_Undistortion
 tile_color 0x71c67100
 label "<center><b>UNDISTORTION</b></center>\\\\nTo apply undistortion:\\\\n1. File > Import Script\\\\n2. Navigate to:\\\\n{nuke_undist_path}\\\\n3. Connect to plate"
 note_font_size 14
 xpos -70
 ypos -200
 bdwidth 340
 bdheight 250
}}
"""

                # Try to read and embed undistortion content if it's a simple script
                try:
                    with open(undistortion_path, "r", encoding="utf-8") as f:
                        undist_content = f.read()

                    # Extract just the LensDistortion nodes if present
                    if "LensDistortion" in undist_content:
                        # Add a comment about the undistortion
                        script_content += f"""
# Undistortion nodes from: {nuke_undist_path}
Group {{
 inputs 1
 name Undistortion_Group
 label "3DE Undistortion"
 xpos 0
 ypos -200
}}
 Input {{
  inputs 0
  name Input1
  xpos 0
  ypos -50
 }}
"""
                        # Extract LensDistortion node (simplified - you'd need proper parsing)
                        if "LensDistortion {" in undist_content:
                            # Find the LensDistortion node content
                            ld_start = undist_content.find("LensDistortion {")
                            if ld_start != -1:
                                # Find the matching closing brace
                                brace_count = 0
                                i = ld_start + len("LensDistortion {")
                                while i < len(undist_content):
                                    if undist_content[i] == "{":
                                        brace_count += 1
                                    elif undist_content[i] == "}":
                                        if brace_count == 0:
                                            # Found the closing brace
                                            ld_node = undist_content[ld_start : i + 1]
                                            # Indent for group
                                            ld_node = "\n".join(
                                                " " + line
                                                for line in ld_node.split("\n")
                                            )
                                            script_content += f"\n{ld_node}\n"
                                            break
                                        brace_count -= 1
                                    i += 1

                        script_content += """
 Output {
  inputs 1
  name Output1
  xpos 0
  ypos 100
 }
end_group
"""
                except Exception as e:
                    print(f"Warning: Could not embed undistortion content: {e}")

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

            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".nk",
                prefix=f"{shot_name}_comp_",
                delete=False,
                encoding="utf-8",
            ) as tmp_file:
                tmp_file.write(script_content)
                return tmp_file.name

        except Exception as e:
            print(f"Error creating Nuke script with undistortion: {e}")
            return None
