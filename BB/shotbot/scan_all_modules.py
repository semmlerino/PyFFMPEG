#!/usr/bin/env python3
"""
Comprehensive Python module scanner for EXR processing capabilities.
Scans all available modules in the Rez environment to find EXR support.
"""

import sys
import os
import pkgutil
import importlib
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional


def print_section(title: str, char: str = "=") -> None:
    """Print formatted section header."""
    print(f"\n{char * 60}")
    print(f" {title}")
    print(f"{char * 60}")


def scan_all_modules() -> List[str]:
    """Scan for all available Python modules in current environment."""
    print("🔍 Scanning all available Python modules...")
    
    modules = []
    
    # Get all modules from sys.path
    for finder, name, ispkg in pkgutil.iter_modules():
        modules.append(name)
    
    # Also check site-packages specifically  
    for path in sys.path:
        if 'site-packages' in path or 'python' in path:
            try:
                for finder, name, ispkg in pkgutil.iter_modules([path]):
                    if name not in modules:
                        modules.append(name)
            except (OSError, ValueError):
                continue
    
    modules.sort()
    print(f"Found {len(modules)} total modules")
    return modules


def find_exr_related_modules(all_modules: List[str]) -> Dict[str, str]:
    """Find modules that might be EXR-related."""
    print("\n🎯 Filtering for EXR-related modules...")
    
    exr_keywords = ['exr', 'openexr', 'imath', 'image', 'cv', 'opencv', 'pil', 'pillow', 
                    'skimage', 'matplotlib', 'tiff', 'hdr', 'imageio', 'wand', 'magick']
    
    exr_related = {}
    
    for module in all_modules:
        module_lower = module.lower()
        for keyword in exr_keywords:
            if keyword in module_lower:
                exr_related[module] = keyword
                break
    
    print(f"Found {len(exr_related)} potentially relevant modules:")
    for module, reason in sorted(exr_related.items()):
        print(f"  {module:25} (contains '{reason}')")
    
    return exr_related


def test_module_import_and_exr_support(module_name: str) -> Dict[str, Any]:
    """Test importing a module and check for EXR support."""
    result = {
        'name': module_name,
        'importable': False,
        'file_path': None,
        'version': None,
        'exr_methods': [],
        'attributes': [],
        'error': None
    }
    
    try:
        # Import the module
        module = importlib.import_module(module_name)
        result['importable'] = True
        result['file_path'] = getattr(module, '__file__', 'Built-in')
        result['version'] = getattr(module, '__version__', 'Unknown')
        
        # Get all attributes
        all_attrs = dir(module)
        result['attributes'] = [attr for attr in all_attrs if not attr.startswith('_')]
        
        # Look for EXR-related methods/attributes
        exr_indicators = ['exr', 'EXR', 'openexr', 'OpenEXR', 'imread', 'imwrite', 'read', 'write', 'load', 'save']
        
        for attr in all_attrs:
            for indicator in exr_indicators:
                if indicator.lower() in attr.lower():
                    result['exr_methods'].append(attr)
                    break
        
        # Special cases for known libraries
        if module_name == 'imageio':
            try:
                # Test EXR format availability
                formats = getattr(module, 'formats', {})
                if hasattr(formats, 'search_read_format'):
                    exr_format = formats.search_read_format('.exr')
                    if exr_format:
                        result['exr_methods'].append(f'formats.search_read_format(.exr) -> {exr_format.name}')
            except:
                pass
        
        elif module_name in ['cv2', 'opencv']:
            try:
                # Test if OpenCV can handle EXR
                imread_flags = getattr(module, 'IMREAD_UNCHANGED', None)
                if imread_flags is not None:
                    result['exr_methods'].append('IMREAD_UNCHANGED (may support EXR)')
            except:
                pass
                
    except ImportError as e:
        result['error'] = f"Import failed: {e}"
    except Exception as e:
        result['error'] = f"Error: {e}"
    
    return result


def test_direct_exr_module_names() -> Dict[str, Any]:
    """Test various EXR module name variations directly."""
    print("\n🧪 Testing direct EXR module name variations...")
    
    exr_module_names = [
        'OpenEXR', 'openexr', 'Imath', 'imath', 
        'exr', 'EXR', 'pyopenexr', 'py_openexr',
        'openexr_python', 'python_openexr', 'PyOpenEXR'
    ]
    
    results = {}
    
    for name in exr_module_names:
        print(f"  Testing {name}...")
        result = test_module_import_and_exr_support(name)
        results[name] = result
        
        if result['importable']:
            print(f"    ✅ {name} - FOUND!")
            print(f"       Version: {result['version']}")
            print(f"       File: {result['file_path']}")
            if result['exr_methods']:
                print(f"       EXR methods: {result['exr_methods'][:5]}")
        else:
            print(f"    ❌ {name} - {result['error']}")
    
    return results


def test_image_libraries_for_exr() -> Dict[str, Any]:
    """Test major image libraries for EXR support."""
    print("\n📸 Testing major image libraries for EXR support...")
    
    image_libs = ['PIL', 'Pillow', 'imageio', 'cv2', 'skimage', 'matplotlib', 'wand']
    results = {}
    
    for lib in image_libs:
        print(f"  Testing {lib} for EXR support...")
        result = test_module_import_and_exr_support(lib)
        results[lib] = result
        
        if result['importable']:
            print(f"    ✅ {lib} available")
            print(f"       Version: {result['version']}")
            
            if result['exr_methods']:
                print(f"       EXR-related methods: {result['exr_methods']}")
            else:
                print(f"       No obvious EXR methods found")
                
            # Special tests
            if lib == 'imageio':
                test_imageio_exr_support(result)
            elif lib in ['cv2']:
                test_opencv_exr_support(result)
            elif lib in ['PIL', 'Pillow']:
                test_pil_exr_support(result)
                
        else:
            print(f"    ❌ {lib} not available")
    
    return results


def test_imageio_exr_support(result: Dict[str, Any]) -> None:
    """Test imageio EXR support specifically."""
    try:
        import imageio
        print(f"      🔍 Testing imageio EXR capabilities...")
        
        # Test format detection
        try:
            # Try to get EXR format info
            if hasattr(imageio, 'formats'):
                formats = imageio.formats
                print(f"         Available format search methods: {[m for m in dir(formats) if 'format' in m.lower()]}")
                
        except Exception as e:
            print(f"         Format detection failed: {e}")
        
        # Test version and backends
        try:
            import imageio.v3 as iio
            print(f"         imageio.v3 available")
            
            # Try to test with a dummy path
            # (We can't actually test without a real EXR file)
            
        except Exception as e:
            print(f"         imageio.v3 test failed: {e}")
            
    except Exception as e:
        print(f"      imageio EXR test failed: {e}")


def test_opencv_exr_support(result: Dict[str, Any]) -> None:
    """Test OpenCV EXR support specifically."""
    try:
        import cv2
        print(f"      🔍 Testing OpenCV EXR capabilities...")
        
        # Check for EXR-related constants
        exr_constants = []
        for attr in dir(cv2):
            if 'EXR' in attr or ('HDR' in attr and 'IMREAD' in attr):
                exr_constants.append(attr)
        
        if exr_constants:
            print(f"         EXR-related constants: {exr_constants}")
        else:
            print(f"         No obvious EXR constants found")
            
        # Check imread flags
        imread_flags = [attr for attr in dir(cv2) if 'IMREAD' in attr]
        print(f"         IMREAD flags available: {len(imread_flags)}")
        
    except Exception as e:
        print(f"      OpenCV EXR test failed: {e}")


def test_pil_exr_support(result: Dict[str, Any]) -> None:
    """Test PIL/Pillow EXR support specifically."""
    try:
        from PIL import Image
        print(f"      🔍 Testing PIL/Pillow EXR capabilities...")
        
        # Check supported formats
        formats = Image.registered_extensions()
        exr_formats = {ext: fmt for ext, fmt in formats.items() if 'exr' in ext.lower()}
        
        if exr_formats:
            print(f"         EXR formats registered: {exr_formats}")
        else:
            print(f"         No EXR formats registered in PIL")
            
    except Exception as e:
        print(f"      PIL EXR test failed: {e}")


def check_system_commands_for_exr() -> List[str]:
    """Check system for EXR-capable command line tools."""
    print("\n⚙️  Checking system commands for EXR support...")
    
    commands = [
        'exr2aces', 'exrheader', 'exrinfo', 'exrmaketiled', 'exrmakepreview',
        'magick', 'convert', 'ffmpeg', 'ffprobe', 
        'oiiotool', 'iconvert', 'idiff', 'iinfo'  # OpenImageIO tools
    ]
    
    available = []
    
    for cmd in commands:
        try:
            result = subprocess.run(['which', cmd], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0:
                available.append(cmd)
                print(f"    ✅ {cmd}: {result.stdout.strip()}")
            else:
                print(f"    ❌ {cmd}: not found")
        except Exception as e:
            print(f"    ❌ {cmd}: error - {e}")
    
    return available


def main():
    """Main scanning function."""
    print("🔬 COMPREHENSIVE MODULE SCANNER FOR EXR SUPPORT")
    print_section("Environment Info")
    
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Architecture: {os.uname().machine if hasattr(os, 'uname') else 'Unknown'}")
    print(f"Working directory: {os.getcwd()}")
    
    # Scan all modules
    print_section("All Available Modules")
    all_modules = scan_all_modules()
    
    # Filter for EXR-related
    print_section("EXR-Related Modules")
    exr_modules = find_exr_related_modules(all_modules)
    
    # Test direct EXR module names
    print_section("Direct EXR Module Testing")
    direct_results = test_direct_exr_module_names()
    
    # Test major image libraries
    print_section("Image Library EXR Support")
    image_lib_results = test_image_libraries_for_exr()
    
    # Check system commands
    print_section("System EXR Tools")
    system_tools = check_system_commands_for_exr()
    
    # Summary
    print_section("SUMMARY AND RECOMMENDATIONS", "=")
    
    working_modules = []
    for name, result in direct_results.items():
        if result['importable']:
            working_modules.append(name)
    
    for name, result in image_lib_results.items():
        if result['importable'] and result['exr_methods']:
            working_modules.append(name)
    
    print(f"✅ Working Python modules: {working_modules if working_modules else 'None'}")
    print(f"✅ Working system tools: {system_tools if system_tools else 'None'}")
    
    if working_modules:
        print("\n🎯 RECOMMENDED PYTHON SOLUTION:")
        for module in working_modules[:3]:  # Top 3 recommendations
            if module in direct_results:
                result = direct_results[module]
            else:
                result = image_lib_results[module]
            print(f"   • Use {module} (version {result['version']})")
            if result['exr_methods']:
                print(f"     Methods: {result['exr_methods'][:3]}")
    
    if system_tools:
        print("\n🔧 RECOMMENDED SYSTEM TOOL SOLUTION:")
        for tool in system_tools[:3]:
            print(f"   • Use {tool} for command-line EXR processing")
    
    if not working_modules and not system_tools:
        print("\n❌ NO EXR SOLUTIONS FOUND")
        print("   Consider requesting additional Rez packages:")
        print("   • opencv (for imageio EXR backend)")
        print("   • pyav (for imageio EXR backend)")  
        print("   • openexr-python (Python bindings)")
        print("   • openimageio (comprehensive image tools)")


if __name__ == '__main__':
    main()