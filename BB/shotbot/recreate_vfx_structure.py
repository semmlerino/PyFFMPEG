#!/usr/bin/env python3
"""Recreate VFX filesystem structure from captured data.

This script takes the JSON output from capture_vfx_structure.py
and recreates the directory structure locally with placeholder files.

Usage:
    python recreate_vfx_structure.py vfx_structure.json
    
Or specify a custom root:
    python recreate_vfx_structure.py vfx_structure.json --root /tmp/mock_vfx
"""

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


class VFXStructureRecreator:
    """Recreate VFX filesystem structure with placeholder files."""
    
    def __init__(self, root_path: str = None):
        """Initialize recreator.
        
        Args:
            root_path: Root directory for recreation (default: /tmp/mock_vfx)
        """
        self.root = Path(root_path or "/tmp/mock_vfx")
        self.stats = {
            'dirs_created': 0,
            'files_created': 0,
            'thumbnails_created': 0,
            '3de_files_created': 0
        }
        
    def create_placeholder_image(self, path: Path, text: str = None, 
                                width: int = 256, height: int = 144):
        """Create a placeholder thumbnail image.
        
        Args:
            path: Path to save the image
            text: Text to display on image
            width: Image width
            height: Image height
        """
        # Create gradient background
        img = Image.new('RGB', (width, height))
        draw = ImageDraw.Draw(img)
        
        # Random gradient colors for variety
        colors = [
            ((20, 20, 40), (60, 60, 100)),   # Dark blue gradient
            ((40, 20, 20), (100, 60, 60)),   # Dark red gradient
            ((20, 40, 20), (60, 100, 60)),   # Dark green gradient
            ((40, 40, 20), (100, 100, 60)),  # Dark yellow gradient
        ]
        
        color_set = random.choice(colors)
        
        # Draw gradient
        for y in range(height):
            ratio = y / height
            r = int(color_set[0][0] + (color_set[1][0] - color_set[0][0]) * ratio)
            g = int(color_set[0][1] + (color_set[1][1] - color_set[0][1]) * ratio)
            b = int(color_set[0][2] + (color_set[1][2] - color_set[0][2]) * ratio)
            draw.rectangle([(0, y), (width, y+1)], fill=(r, g, b))
        
        # Add text
        if text:
            # Try to use a basic font, fall back to default if not available
            try:
                # This should work on most systems
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            except:
                font = ImageFont.load_default()
            
            # Draw text with shadow for better visibility
            text_lines = text.split('\n')
            y_offset = height // 2 - (len(text_lines) * 20) // 2
            
            for i, line in enumerate(text_lines):
                # Get text bbox for centering
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                y = y_offset + i * 20
                
                # Shadow
                draw.text((x+1, y+1), line, font=font, fill=(0, 0, 0, 128))
                # Text
                draw.text((x, y), line, font=font, fill=(255, 255, 255))
        
        # Add border
        draw.rectangle([(0, 0), (width-1, height-1)], outline=(100, 100, 100), width=1)
        
        # Save
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, 'JPEG', quality=85)
        self.stats['thumbnails_created'] += 1
    
    def create_3de_file(self, path: Path, shot_name: str, user: str, plate: str):
        """Create a placeholder 3DE scene file.
        
        Args:
            path: Path to save the file
            shot_name: Shot name
            user: User who created the scene
            plate: Plate name
        """
        # 3DE files are binary but we'll create a text placeholder
        # that indicates what it represents
        content = f"""# 3DE Scene File (Mock)
# This is a placeholder for development/testing
#
# Shot: {shot_name}
# User: {user}
# Plate: {plate}
# Path: {path}
#
# In production, this would be a binary 3DE project file
# containing camera tracking data, lens information, etc.
"""
        
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        self.stats['3de_files_created'] += 1
    
    def create_exr_sequence(self, path: Path, shot_name: str, start: int = 1001, end: int = 1010):
        """Create placeholder EXR files for a plate sequence.
        
        Args:
            path: Directory path for the sequence
            shot_name: Shot name
            start: Start frame
            end: End frame
        """
        path.mkdir(parents=True, exist_ok=True)
        
        # Create a few sample frames (not the whole sequence to save space)
        sample_frames = [start, (start + end) // 2, end]
        
        for frame in sample_frames:
            # EXR files would be large images, we'll create tiny placeholders
            frame_file = path / f"{shot_name}.{frame:04d}.exr"
            # Just create an empty file or tiny text file
            frame_file.write_text(f"EXR placeholder: {shot_name} frame {frame}\n", encoding='utf-8')
        
        # Create a slate image as JPG
        slate_path = path / f"{shot_name}_slate.jpg"
        self.create_placeholder_image(
            slate_path,
            f"{shot_name}\nFrames {start}-{end}",
            512, 288
        )
    
    def recreate_node(self, node: dict, parent_path: Path):
        """Recursively recreate a node from the captured structure.
        
        Args:
            node: Node dictionary from captured structure
            parent_path: Parent directory path
        """
        if node['type'] == 'truncated':
            return
            
        name = node['name']
        
        if node['type'] == 'dir':
            # Create directory
            dir_path = parent_path / name if name != '.' else parent_path
            dir_path.mkdir(parents=True, exist_ok=True)
            self.stats['dirs_created'] += 1
            
            # Process children
            for child in node.get('children', []):
                self.recreate_node(child, dir_path)
                
        elif node['type'] == 'file':
            file_path = parent_path / name
            
            # Determine file type and create appropriate placeholder
            lower_name = name.lower()
            
            if any(pattern in lower_name for pattern in ['thumbnail', 'poster_frame', 'frame']):
                # Create thumbnail image
                if lower_name.endswith(('.jpg', '.jpeg', '.png')):
                    # Extract shot info from path
                    path_parts = str(file_path).split('/')
                    shot_info = "Thumbnail"
                    
                    # Try to find shot name in path
                    for part in path_parts:
                        if '_' in part and any(c.isdigit() for c in part):
                            shot_info = part
                            break
                    
                    self.create_placeholder_image(file_path, shot_info)
                    
            elif lower_name.endswith('.3de'):
                # Create 3DE file
                # Extract info from path
                path_str = str(file_path)
                user = "unknown"
                plate = "unknown"
                shot = "unknown"
                
                if '/user/' in path_str:
                    user = path_str.split('/user/')[1].split('/')[0]
                if '/scene/' in path_str:
                    plate = path_str.split('/scene/')[1].split('/')[0]
                    
                # Extract shot from filename
                if '_' in name:
                    shot = '_'.join(name.split('_')[:3])
                    
                self.create_3de_file(file_path, shot, user, plate)
                
            elif lower_name.endswith('.exr'):
                # Skip individual EXR files, handle at sequence level
                pass
                
            else:
                # Create generic placeholder file
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(f"Placeholder for {name}\n", encoding='utf-8')
                
            self.stats['files_created'] += 1
    
    def create_additional_3de_files(self, structure_data: dict):
        """Create additional 3DE files from other users for 'Other 3DE Scenes' tab.
        
        Args:
            structure_data: Dictionary loaded from capture JSON
        """
        print("Creating additional 3DE files from other users...")
        
        # Other users to create 3DE files for (top users from the original structure)
        other_users = ["henry-b", "david-s", "jeanette-m", "dave-c", "richard-f"]
        
        # Get workspace shots from the structure data
        workspace_shots = structure_data.get('workspace_shots', [])
        if not workspace_shots:
            print("No workspace shots found, skipping additional 3DE files")
            return
            
        # Create 3DE files for about 25% of the shots for each other user
        import random
        random.seed(42)  # Consistent results
        
        for user in other_users:
            # Select a subset of shots for this user
            selected_shots = random.sample(workspace_shots, min(len(workspace_shots) // 4, 20))
            
            for shot_path in selected_shots:
                try:
                    # Parse path string: /shows/broken_eggs/shots/BRX_170/BRX_170_0100
                    path_parts = Path(shot_path).parts
                    if len(path_parts) >= 5 and 'shows' in path_parts and 'shots' in path_parts:
                        shows_idx = path_parts.index('shows')
                        shots_idx = path_parts.index('shots')
                        
                        show = path_parts[shows_idx + 1]  # broken_eggs
                        sequence = path_parts[shots_idx + 1]  # BRX_170  
                        shot = path_parts[shots_idx + 2]  # BRX_170_0100
                    else:
                        print(f"Could not parse shot path: {shot_path}")
                        continue
                    
                    # Create 3DE file path following the standard pattern
                    shot_dir = self.root / 'shows' / show / 'shots' / sequence / shot
                    user_3de_dir = shot_dir / 'user' / user / 'mm' / '3de' / 'mm-default' / 'scenes' / 'scene' / 'bg01'
                    
                    # Create directory structure
                    user_3de_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Create 3DE file
                    threede_filename = f"{shot}_mm_default_bg01_scene_v001.3de"
                    threede_file = user_3de_dir / threede_filename
                    
                    self.create_3de_file(threede_file, shot, user, "bg01")
                    
                except Exception as e:
                    print(f"Error creating 3DE file for {user} in {shot_path}: {e}")
                    continue
        
        print(f"Created additional 3DE files from {len(other_users)} other users")
    
    def create_gabrielh_3de_files(self, structure_data: dict):
        """Create 3DE files for gabriel-h to populate 'My Shots' tab."""
        gabrielh_3de_count = 0
        
        # Find all gabriel-h 3DE scene directories
        for show, show_data_list in structure_data.get('shows', {}).items():
            for show_data in show_data_list:
                structure = show_data.get('structure', {})
                gabrielh_3de_paths = []
                
                def find_gabrielh_3de_scenes(node, path_parts=[]):
                    """Recursively find gabriel-h 3DE scenes directories."""
                    if node.get('type') == 'dir':
                        current_path = path_parts + [node['name']]
                        
                        # Check if this is a gabriel-h scenes directory
                        path_str = '/'.join(current_path)
                        if ('user/gabriel-h' in path_str and 
                            'scenes' in path_str and 
                            '3de' in path_str and
                            'mm-default' in path_str):
                            gabrielh_3de_paths.append(current_path)
                        
                        # Recurse through children
                        for child in node.get('children', []):
                            find_gabrielh_3de_scenes(child, current_path)
                
                find_gabrielh_3de_scenes(structure)
                
                # Create 3DE files in each found scenes directory
                for path_parts in gabrielh_3de_paths:
                    try:
                        # Extract shot info from path 
                        # Example path: shows/broken_eggs/shots/BRX_170/BRX_170_0100/user/gabriel-h/mm/3de/mm-default/scenes
                        if 'shots' in path_parts:
                            shots_idx = path_parts.index('shots')
                            if shots_idx + 2 < len(path_parts):
                                sequence = path_parts[shots_idx + 1]
                                shot = path_parts[shots_idx + 2]
                                
                                # Create scene/bg01 subdirectory and 3DE file
                                # Path parts start with show name, need to prepend 'shows'
                                full_path_parts = ['shows'] + path_parts
                                scenes_dir = self.root / Path(*full_path_parts)
                                scene_bg01_dir = scenes_dir / 'scene' / 'bg01'
                                scene_bg01_dir.mkdir(parents=True, exist_ok=True)
                                
                                # Create 3DE file
                                threede_filename = f"{shot}_mm_default_bg01_scene_v001.3de"
                                threede_file = scene_bg01_dir / threede_filename
                                
                                self.create_3de_file(threede_file, shot, "gabriel-h", "bg01")
                                gabrielh_3de_count += 1
                                
                    except Exception as e:
                        print(f"Error creating gabriel-h 3DE file in {'/'.join(path_parts)}: {e}")
                        continue
        
        print(f"Created {gabrielh_3de_count} 3DE files for gabriel-h")
    
    def recreate_structure(self, structure_data: dict):
        """Recreate the entire VFX structure.
        
        Args:
            structure_data: Dictionary loaded from capture JSON
        """
        print(f"Recreating VFX structure in {self.root}")
        self.root.mkdir(parents=True, exist_ok=True)
        
        # Recreate each show
        for show, show_data_list in structure_data.get('shows', {}).items():
            print(f"Recreating show: {show}")
            
            for show_data in show_data_list:
                # Determine local root (map /shows to our root)
                original_root = show_data['root']
                
                # Create show structure
                if 'structure' in show_data:
                    show_structure = show_data['structure']
                    
                    # Create under our mock root
                    show_path = self.root / 'shows' / show
                    self.recreate_node(show_structure, self.root / 'shows')
        
        # Create additional 3DE files from other users for "Other 3DE Scenes" tab
        self.create_additional_3de_files(structure_data)
        
        # Create 3DE files for current user gabriel-h for "My Shots" tab
        self.create_gabrielh_3de_files(structure_data)
        
        # Create symlink for convenience (if on Linux/Mac)
        try:
            shows_link = Path('/tmp/shows')
            if not shows_link.exists():
                shows_link.symlink_to(self.root / 'shows')
                print(f"Created symlink: /tmp/shows -> {self.root / 'shows'}")
        except Exception as e:
            print(f"Could not create symlink: {e}")
        
        # Print statistics
        print("\nRecreation complete!")
        print(f"  Directories created: {self.stats['dirs_created']}")
        print(f"  Files created: {self.stats['files_created']}")
        print(f"  Thumbnails created: {self.stats['thumbnails_created']}")
        print(f"  3DE files created: {self.stats['3de_files_created']}")

def merge_structures(json_files):
    """Merge multiple VFX structure JSON files.
    
    Args:
        json_files: List of JSON file paths
        
    Returns:
        Merged structure dictionary
    """
    merged = {
        'capture_time': None,
        'capture_host': 'merged',
        'workspace_shots': [],
        'shows': {},
        'show_roots': [],
        'patterns': {}
    }
    
    workspace_shots_set = set()
    show_roots_set = set()
    
    for json_file in json_files:
        print(f"Loading {json_file}...")
        with open(json_file, encoding='utf-8') as f:
            data = json.load(f)
        
        # Use the latest capture time
        if data.get('capture_time'):
            if merged['capture_time'] is None or data['capture_time'] > merged['capture_time']:
                merged['capture_time'] = data['capture_time']
        
        # Merge workspace shots (unique)
        for shot in data.get('workspace_shots', []):
            workspace_shots_set.add(shot)
        
        # Merge show roots (unique)
        for root in data.get('show_roots', []):
            show_roots_set.add(root)
        
        # Merge shows
        for show, show_data_list in data.get('shows', {}).items():
            if show not in merged['shows']:
                merged['shows'][show] = []
            
            # Add show data, avoiding duplicates
            for show_data in show_data_list:
                # Check if this root/structure combo already exists
                exists = False
                for existing in merged['shows'][show]:
                    if existing.get('root') == show_data.get('root'):
                        # Merge or replace - use the one with more data
                        existing_size = count_nodes(existing.get('structure', {}))
                        new_size = count_nodes(show_data.get('structure', {}))
                        if new_size > existing_size:
                            existing['structure'] = show_data['structure']
                        exists = True
                        break
                
                if not exists:
                    merged['shows'][show].append(show_data)
        
        # Merge patterns
        for key, value in data.get('patterns', {}).items():
            if key not in merged['patterns']:
                merged['patterns'][key] = []
            if isinstance(value, list):
                for item in value:
                    if item not in merged['patterns'][key]:
                        merged['patterns'][key].append(item)
    
    # Convert sets back to lists
    merged['workspace_shots'] = sorted(list(workspace_shots_set))
    merged['show_roots'] = sorted(list(show_roots_set))
    
    return merged

def count_nodes(structure):
    """Count total nodes in a structure tree."""
    if not structure or not isinstance(structure, dict):
        return 0
    
    count = 1  # Count this node
    for child in structure.get('children', []):
        count += count_nodes(child)
    return count

def main():
    parser = argparse.ArgumentParser(
        description='Recreate VFX filesystem structure from captured data'
    )
    parser.add_argument(
        'input',
        nargs='+',  # Accept multiple input files
        help='Input JSON file(s) from capture_vfx_structure.py (can specify multiple)'
    )
    parser.add_argument(
        '--root',
        default='/tmp/mock_vfx',
        help='Root directory for recreation (default: /tmp/mock_vfx)'
    )
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Clean existing structure before recreating'
    )
    
    args = parser.parse_args()
    
    # Handle single or multiple input files
    if len(args.input) == 1:
        # Single file - load directly
        with open(args.input[0], encoding='utf-8') as f:
            structure_data = json.load(f)
        print(f"Loaded structure from {args.input[0]}")
    else:
        # Multiple files - merge them
        print(f"Merging {len(args.input)} structure files...")
        structure_data = merge_structures(args.input)
        print(f"Merged {len(args.input)} files successfully")
    
    print(f"Capture time: {structure_data.get('capture_time', 'unknown')}")
    print(f"Capture host: {structure_data.get('capture_host', 'unknown')}")
    print(f"Shows found: {', '.join(structure_data.get('shows', {}).keys())}")
    
    # If multiple files were merged, optionally save the merged result
    if len(args.input) > 1:
        merged_output = Path(args.root) / 'merged_structure.json'
        print(f"\nSaving merged structure to: {merged_output}")
        merged_output.parent.mkdir(parents=True, exist_ok=True)
        with open(merged_output, 'w', encoding='utf-8') as f:
            json.dump(structure_data, f, indent=2)
        print("Merged structure saved for future use")
    
    # Clean if requested
    if args.clean:
        root = Path(args.root)
        if root.exists():
            import shutil
            print(f"Cleaning existing structure at {root}")
            shutil.rmtree(root)
    
    # Recreate structure
    recreator = VFXStructureRecreator(args.root)
    recreator.recreate_structure(structure_data)
    
    # Create a marker file to indicate this is mock
    marker = Path(args.root) / 'MOCK_VFX_ENVIRONMENT.txt'
    marker.write_text("""This is a mock VFX environment created for development/testing.
    
Generated from: {}
Capture time: {}
Capture host: {}

DO NOT use for production!
""".format(
        args.input,
        structure_data.get('capture_time', 'unknown'),
        structure_data.get('capture_host', 'unknown')
    ), encoding='utf-8')
    
    print(f"\n✅ Mock VFX environment ready at: {args.root}")
    print(f"You can now set SHOWS_ROOT={args.root}/shows when running ShotBot")

if __name__ == '__main__':
    main()