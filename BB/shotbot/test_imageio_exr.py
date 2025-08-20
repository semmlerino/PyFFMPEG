#!/usr/bin/env python3
"""
Test imageio EXR capabilities with actual EXR files from the ShotBot logs.
Based on the diagnostic results, imageio has the right methods - let's test if it works.
"""

import sys
import os
from pathlib import Path
import tempfile

def test_imageio_exr_reading():
    """Test if imageio can actually read EXR files."""
    print("🧪 Testing imageio EXR reading capabilities...")
    
    try:
        import imageio
        import imageio.v3 as iio
        print(f"✅ imageio imported successfully (version {imageio.__version__})")
    except ImportError as e:
        print(f"❌ Failed to import imageio: {e}")
        return False
    
    # Test EXR files from the ShotBot logs
    test_exr_files = [
        "/shows/jack_ryan/shots/MA_074/MA_074_0340/publish/turnover/plate/input_plate/FG01/v001/exr/4312x2304/MA_074_0340_turnover-plate_FG01_lin_sgamut3cine_v001.1020.exr",
        "/shows/jack_ryan/shots/DB_005/DB_005_0060/publish/turnover/plate/input_plate/FG01/v001/exr/4312x2304/DB_005_0060_turnover-plate_FG01_lin_sgamut3cine_v001.1017.exr",
        "/shows/jack_ryan/shots/999_xx/999_xx_999/publish/turnover/plate/input_plate/FG01/v001/exr/editorial/999_xx_999_turnover-plate_FG01_lin_sgamut3cine_v001.1001.exr"
    ]
    
    success_count = 0
    
    for i, exr_path in enumerate(test_exr_files):
        print(f"\n--- Test {i+1}: {Path(exr_path).name} ---")
        
        if not Path(exr_path).exists():
            print(f"⚠️  File does not exist: {exr_path}")
            continue
        
        # Test imageio.v3.imread
        try:
            print("Testing imageio.v3.imread()...")
            img_array = iio.imread(exr_path)
            print(f"✅ Success! Image shape: {img_array.shape}, dtype: {img_array.dtype}")
            
            # Test basic processing
            if len(img_array.shape) >= 2:
                height, width = img_array.shape[:2]
                print(f"   Dimensions: {width}x{height}")
                
                # Test conversion to PIL
                try:
                    from PIL import Image as PILImage
                    import numpy as np
                    
                    # Handle different data types
                    if img_array.dtype in ['float32', 'float64']:
                        # Normalize HDR to LDR
                        normalized = np.clip(img_array, 0, 1)
                        uint8_array = (normalized * 255).astype('uint8')
                    else:
                        uint8_array = img_array
                    
                    # Handle different channel counts
                    if len(uint8_array.shape) == 3:
                        if uint8_array.shape[2] == 4:  # RGBA
                            uint8_array = uint8_array[:, :, :3]  # Convert to RGB
                        pil_image = PILImage.fromarray(uint8_array, mode='RGB')
                    else:
                        pil_image = PILImage.fromarray(uint8_array, mode='L')
                    
                    # Test resize
                    thumbnail = pil_image.resize((256, 256), PILImage.Resampling.LANCZOS)
                    print(f"✅ PIL conversion successful: {thumbnail.size}")
                    
                    success_count += 1
                    
                except Exception as e:
                    print(f"⚠️  PIL conversion failed: {e}")
            
        except Exception as e:
            print(f"❌ imageio.v3.imread failed: {e}")
            
            # Try older imageio API
            try:
                print("Trying imageio.imread() (v2 API)...")
                img_array = imageio.imread(exr_path)
                print(f"✅ v2 API Success! Image shape: {img_array.shape}, dtype: {img_array.dtype}")
                success_count += 1
            except Exception as e2:
                print(f"❌ imageio.imread (v2) also failed: {e2}")
    
    print(f"\n📊 Results: {success_count}/{len(test_exr_files)} EXR files successfully read")
    return success_count > 0


def test_system_tool_conversion():
    """Test system tool EXR conversion."""
    print("\n🔧 Testing system tool EXR conversion...")
    
    # Find an EXR file to test with
    test_exr_files = [
        "/shows/jack_ryan/shots/MA_074/MA_074_0340/publish/turnover/plate/input_plate/FG01/v001/exr/4312x2304/MA_074_0340_turnover-plate_FG01_lin_sgamut3cine_v001.1020.exr",
        "/shows/jack_ryan/shots/AS_193/AS_193_1900/publish/editorial/cutref/v001/jpg/1920x1080/AS_193_1900_editorial-cutref_v001.1074.jpg"  # Fallback to JPG for testing
    ]
    
    test_file = None
    for file_path in test_exr_files:
        if Path(file_path).exists():
            test_file = file_path
            break
    
    if not test_file:
        print("⚠️  No test files found")
        return False
    
    print(f"Using test file: {Path(test_file).name}")
    
    # Test conversion tools
    import subprocess
    
    tools_to_test = [
        ['exrinfo', test_file],
        ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', test_file],
        ['convert', test_file, '-resize', '256x256', '/tmp/test_convert.jpg']
    ]
    
    success_count = 0
    
    for tool_cmd in tools_to_test:
        tool_name = tool_cmd[0]
        print(f"\nTesting {tool_name}...")
        
        try:
            result = subprocess.run(tool_cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=30)
            
            if result.returncode == 0:
                print(f"✅ {tool_name} successful!")
                if result.stdout:
                    # Show first few lines of output
                    lines = result.stdout.strip().split('\n')[:3]
                    for line in lines:
                        print(f"   {line}")
                success_count += 1
            else:
                print(f"❌ {tool_name} failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print(f"⏱️  {tool_name} timed out")
        except FileNotFoundError:
            print(f"❌ {tool_name} not found")
        except Exception as e:
            print(f"❌ {tool_name} error: {e}")
    
    # Test our conversion script
    script_path = Path(__file__).parent / 'convert_exr_to_jpeg.sh'
    if script_path.exists() and test_file.endswith('.exr'):
        print(f"\nTesting conversion script...")
        try:
            result = subprocess.run([str(script_path), test_file, '/tmp/script_test.jpg', '256'],
                                  capture_output=True, 
                                  text=True, 
                                  timeout=60)
            
            if result.returncode == 0:
                print(f"✅ Conversion script successful!")
                if Path('/tmp/script_test.jpg').exists():
                    size = Path('/tmp/script_test.jpg').stat().st_size
                    print(f"   Output file: /tmp/script_test.jpg ({size} bytes)")
                success_count += 1
            else:
                print(f"❌ Conversion script failed: {result.stderr}")
                print(f"   stdout: {result.stdout}")
        except Exception as e:
            print(f"❌ Conversion script error: {e}")
    
    print(f"\n📊 System tools: {success_count} successful tests")
    return success_count > 0


def main():
    """Main test function."""
    print("🧪 IMAGEIO EXR CAPABILITY TEST")
    print("=" * 50)
    
    imageio_works = test_imageio_exr_reading()
    system_tools_work = test_system_tool_conversion()
    
    print("\n" + "=" * 50)
    print("FINAL RECOMMENDATIONS")
    print("=" * 50)
    
    if imageio_works:
        print("🎯 RECOMMENDED SOLUTION: Use imageio for EXR processing")
        print("   • imageio can successfully read EXR files")
        print("   • Conversion to PIL/thumbnails works")
        print("   • Update thumbnail_processor.py to use imageio")
        
    elif system_tools_work:
        print("🔧 RECOMMENDED SOLUTION: Use system tools for EXR processing")
        print("   • Use conversion script with available tools")
        print("   • Reliable but requires subprocess calls")
        print("   • Update thumbnail_processor.py to use external conversion")
        
    else:
        print("❌ PROBLEM: No working EXR solutions found")
        print("   • May need to request additional Rez packages")
        print("   • Consider opencv or openimageio packages")


if __name__ == '__main__':
    main()