"""Generate Nuke scripts with Read nodes for plates."""

import tempfile
from pathlib import Path
from typing import Optional


class NukeScriptGenerator:
    """Generate temporary Nuke scripts with Read nodes."""
    
    @staticmethod
    def create_plate_script(plate_path: str, shot_name: str) -> Optional[str]:
        """Create a temporary Nuke script with a Read node for the plate.
        
        Args:
            plate_path: Path to the plate sequence (with #### pattern)
            shot_name: Name of the shot for the script
            
        Returns:
            Path to the temporary .nk script, or None if creation failed
        """
        try:
            # Parse the plate path to get frame range
            # Convert #### to %04d for Nuke
            nuke_path = plate_path.replace("####", "%04d")
            
            # Try to detect frame range from the plate path
            # Default to a reasonable range if we can't detect
            first_frame = 1001
            last_frame = 1100
            
            # Try to find actual frames
            plate_dir = Path(plate_path).parent
            plate_pattern = Path(plate_path).name.replace("####", "*")
            
            if plate_dir.exists():
                frames = sorted(plate_dir.glob(plate_pattern))
                if frames:
                    # Extract frame numbers
                    frame_numbers = []
                    for frame in frames:
                        # Extract number from filename
                        parts = frame.stem.split(".")
                        if len(parts) > 1:
                            try:
                                frame_num = int(parts[-1])
                                frame_numbers.append(frame_num)
                            except ValueError:
                                pass
                    
                    if frame_numbers:
                        first_frame = min(frame_numbers)
                        last_frame = max(frame_numbers)
            
            # Create the Nuke script content
            script_content = f"""#! /usr/local/Nuke15.1v2/nuke-15.1.2 -nx
version 15.1 v2
define_window_layout_xml {{<?xml version="1.0" encoding="UTF-8"?>
<layout version="1.0">
    <window x="0" y="0" w="1920" h="1080" screen="0">
        <splitter orientation="1">
            <split size="1920"/>
            <dock id="" activePageId="Viewer.1">
                <page id="Viewer.1"/>
            </dock>
        </splitter>
    </window>
</layout>
}}
Root {{
 inputs 0
 name {shot_name}_plate
 first_frame {first_frame}
 last_frame {last_frame}
 format "4312 2304 0 0 4312 2304 1 "
}}
Read {{
 inputs 0
 file_type exr
 file "{nuke_path}"
 first {first_frame}
 last {last_frame}
 origfirst {first_frame}
 origlast {last_frame}
 origset true
 name Read_Plate
 selected true
 xpos 0
 ypos 0
}}
Viewer {{
 frame_range {first_frame}-{last_frame}
 name Viewer1
 xpos 0
 ypos 100
}}
"""
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.nk',
                prefix=f'{shot_name}_plate_',
                delete=False
            ) as tmp_file:
                tmp_file.write(script_content)
                return tmp_file.name
                
        except Exception as e:
            print(f"Error creating Nuke script: {e}")
            return None
    
    @staticmethod
    def create_plate_script_with_undistortion(
        plate_path: str,
        undistortion_path: Optional[str],
        shot_name: str
    ) -> Optional[str]:
        """Create a Nuke script with plate and optional undistortion.
        
        Args:
            plate_path: Path to the plate sequence
            undistortion_path: Path to undistortion .nk file (optional)
            shot_name: Name of the shot
            
        Returns:
            Path to the temporary .nk script
        """
        # Start with basic plate script
        script_path = NukeScriptGenerator.create_plate_script(plate_path, shot_name)
        
        if script_path and undistortion_path and Path(undistortion_path).exists():
            # TODO: Add undistortion node import
            # This would require parsing the undistortion .nk file
            # and inserting it into the node graph
            pass
            
        return script_path