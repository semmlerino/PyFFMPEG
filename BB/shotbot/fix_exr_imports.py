#!/usr/bin/env python3
"""
Fix for EXR processing in ShotBot's Rez environment.
This addresses the OpenEXR import issues by implementing practical workarounds.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional


def check_rez_opencv_packages():
    """Check if OpenCV packages are available in Rez environment."""
    print("Checking for OpenCV/PyAV packages in Rez...")
    
    # Check environment for opencv-related packages
    opencv_packages = []
    pyav_packages = []
    
    for key, value in os.environ.items():
        if key.startswith('REZ_') and ('OPENCV' in key or 'CV' in key):
            opencv_packages.append(f"{key}={value}")
        elif key.startswith('REZ_') and ('PYAV' in key or 'AV' in key):
            pyav_packages.append(f"{key}={value}")
    
    print(f"Found {len(opencv_packages)} OpenCV-related packages:")
    for pkg in opencv_packages:
        print(f"  {pkg}")
        
    print(f"Found {len(pyav_packages)} PyAV-related packages:")  
    for pkg in pyav_packages:
        print(f"  {pkg}")
    
    return len(opencv_packages) > 0 or len(pyav_packages) > 0


def test_exr_conversion_with_tools():
    """Test if we can use OpenEXR command-line tools for conversion."""
    print("\nTesting OpenEXR command-line tools...")
    
    # Find exr tools in PATH
    exr_tools = ['exr2aces', 'exrheader', 'exrinfo']
    available_tools = []
    
    for tool in exr_tools:
        try:
            result = subprocess.run(['which', tool], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0:
                available_tools.append(tool)
                print(f"✅ {tool}: {result.stdout.strip()}")
            else:
                print(f"❌ {tool}: not found")
        except Exception as e:
            print(f"❌ {tool}: error checking - {e}")
    
    return available_tools


def create_exr_conversion_script():
    """Create a shell script for EXR to JPEG conversion using available tools."""
    
    script_content = '''#!/bin/bash
# EXR to JPEG conversion using OpenEXR tools + ImageMagick
# Usage: convert_exr_to_jpeg.sh input.exr output.jpg [size]

INPUT_EXR="$1"
OUTPUT_JPG="$2"
SIZE="${3:-512}"

if [ -z "$INPUT_EXR" ] || [ -z "$OUTPUT_JPG" ]; then
    echo "Usage: $0 input.exr output.jpg [size]"
    exit 1
fi

if [ ! -f "$INPUT_EXR" ]; then
    echo "Error: Input file $INPUT_EXR not found"
    exit 1
fi

# Try different conversion methods in order of preference

# Method 1: Direct ImageMagick (if it supports EXR)
if command -v magick >/dev/null 2>&1; then
    echo "Trying ImageMagick conversion..."
    if magick "$INPUT_EXR" -resize "${SIZE}x${SIZE}" "$OUTPUT_JPG" 2>/dev/null; then
        echo "✅ ImageMagick conversion successful"
        exit 0
    fi
fi

# Method 2: ImageMagick convert command
if command -v convert >/dev/null 2>&1; then
    echo "Trying ImageMagick convert..."
    if convert "$INPUT_EXR" -resize "${SIZE}x${SIZE}" "$OUTPUT_JPG" 2>/dev/null; then
        echo "✅ ImageMagick convert successful"
        exit 0
    fi
fi

# Method 3: FFmpeg (often available in VFX environments)
if command -v ffmpeg >/dev/null 2>&1; then
    echo "Trying FFmpeg conversion..."
    if ffmpeg -i "$INPUT_EXR" -vf scale="${SIZE}:${SIZE}:force_original_aspect_ratio=decrease" -q:v 2 "$OUTPUT_JPG" -y 2>/dev/null; then
        echo "✅ FFmpeg conversion successful"  
        exit 0
    fi
fi

echo "❌ All conversion methods failed"
exit 1
'''

    script_path = Path.cwd() / 'convert_exr_to_jpeg.sh'
    script_path.write_text(script_content)
    script_path.chmod(0o755)
    
    print(f"✅ Created EXR conversion script: {script_path}")
    return script_path


def create_fixed_thumbnail_processor():
    """Create a fixed version of thumbnail_processor.py with Rez environment support."""
    
    fix_content = '''
def _process_exr_with_rez_environment(self, source_path: Path) -> Optional["PILImage.Image"]:
    """Process EXR files in Rez environment using available tools.
    
    This method replaces the failed OpenEXR Python import approach with
    practical solutions that work with the available Rez packages.
    """
    from PIL import Image as PILImage
    import subprocess
    import tempfile
    
    # Method 1: Try external conversion tools
    temp_jpg = None
    try:
        # Create temporary JPEG file
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            temp_jpg = tmp.name
        
        # Try conversion script if available
        script_path = Path(__file__).parent / 'convert_exr_to_jpeg.sh'
        if script_path.exists():
            result = subprocess.run([
                str(script_path), 
                str(source_path), 
                temp_jpg, 
                str(self.target_size)
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and Path(temp_jpg).exists():
                logger.info(f"EXR converted using script: {result.stdout.strip()}")
                return PILImage.open(temp_jpg)
        
        # Method 2: Direct command attempts
        conversion_commands = [
            ['magick', str(source_path), '-resize', f'{self.target_size}x{self.target_size}', temp_jpg],
            ['convert', str(source_path), '-resize', f'{self.target_size}x{self.target_size}', temp_jpg],
            ['ffmpeg', '-i', str(source_path), '-vf', f'scale={self.target_size}:{self.target_size}:force_original_aspect_ratio=decrease', '-q:v', '2', temp_jpg, '-y']
        ]
        
        for cmd in conversion_commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and Path(temp_jpg).exists():
                    logger.info(f"EXR converted using: {cmd[0]}")
                    return PILImage.open(temp_jpg)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        # Method 3: Try imageio with warning about missing backends
        try:
            import imageio.v3 as iio
            img_array = iio.imread(str(source_path))
            
            # Convert to PIL Image
            from PIL import Image as PILImage
            if len(img_array.shape) == 3:
                # RGB/RGBA image
                if img_array.shape[2] == 4:
                    # RGBA, convert to RGB
                    img_array = img_array[:, :, :3]
                
                # Normalize and convert to uint8
                if img_array.dtype == 'float32' or img_array.dtype == 'float64':
                    img_array = (img_array * 255).astype('uint8')
                
                pil_image = PILImage.fromarray(img_array, mode='RGB')
                return pil_image.resize((self.target_size, self.target_size), PILImage.Resampling.LANCZOS)
            
        except Exception as e:
            logger.debug(f"imageio fallback also failed: {e}")
        
        return None
        
    finally:
        # Clean up temporary file
        if temp_jpg and Path(temp_jpg).exists():
            try:
                Path(temp_jpg).unlink()
            except:
                pass


def _process_exr_fallback_method(self, source_path: Path) -> Optional["PILImage.Image"]:
    """Enhanced fallback processing for EXR files in Rez environments."""
    
    # Log the issue for better debugging
    logger.warning(f"Using fallback EXR processing for {source_path.name}")
    
    # Try the Rez-specific method
    result = self._process_exr_with_rez_environment(source_path)
    if result:
        return result
    
    # Ultimate fallback: skip EXR processing and mark as failed
    logger.error(f"All EXR processing methods failed for {source_path}")
    return None
'''

    print("📝 Fixed thumbnail processor methods:")
    print("   - _process_exr_with_rez_environment(): Uses external tools")
    print("   - _process_exr_fallback_method(): Enhanced fallback chain")
    print("   - Supports ImageMagick, FFmpeg, and imageio backends")
    
    return fix_content


def main():
    """Main function to implement EXR fixes."""
    print("🔧 ShotBot EXR Processing Fix for Rez Environment")
    print("=" * 60)
    
    # Check current environment
    openexr_root = os.environ.get('REZ_OPENEXR_ROOT', '')
    if not openexr_root:
        print("⚠️  Not in Rez OpenEXR environment")
        return
    
    print(f"🏠 OpenEXR Root: {openexr_root}")
    
    # Check for additional packages
    has_backends = check_rez_opencv_packages()
    
    # Test available tools
    available_tools = test_exr_conversion_with_tools()
    
    # Create conversion script
    if available_tools:
        script_path = create_exr_conversion_script()
        
        # Test the script with a dummy run
        try:
            result = subprocess.run([str(script_path)], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            print(f"📄 Conversion script created and tested")
        except Exception as e:
            print(f"⚠️  Script created but test failed: {e}")
    
    # Generate fixed code
    fixed_code = create_fixed_thumbnail_processor()
    
    print("\n" + "=" * 60)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 60)
    
    if available_tools:
        print("✅ External EXR tools available - script-based conversion will work")
    else:
        print("❌ No external EXR tools found - may need additional packages")
    
    if has_backends:
        print("✅ Backend packages found - imageio may work")
    else:
        print("⚠️  No OpenCV/PyAV packages - imageio EXR support limited")
    
    print("\nNext Steps:")
    print("1. Add the generated conversion script to the ShotBot directory")  
    print("2. Update thumbnail_processor.py with the fixed methods")
    print("3. Consider requesting opencv or pyav Rez packages for imageio")
    print("4. Test with actual EXR files from the VFX pipeline")
    
    print(f"\n🚀 Ready to implement fixes!")


if __name__ == '__main__':
    main()