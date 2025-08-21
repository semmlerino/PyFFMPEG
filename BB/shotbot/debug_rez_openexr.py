#!/usr/bin/env python3
"""
Diagnostic script to explore Rez OpenEXR package structure and find working import methods.
Run this in the same Rez environment as ShotBot to diagnose OpenEXR import issues.

Usage:
    rez env PySide6_Essentials pillow Jinja2 -- python3 debug_rez_openexr.py
"""

import importlib.util
import os
import sys
from pathlib import Path


def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def explore_directory(path, max_depth=3, current_depth=0):
    """Recursively explore directory structure."""
    if current_depth >= max_depth:
        return

    try:
        path_obj = Path(path)
        if not path_obj.exists():
            return

        indent = "  " * current_depth
        print(f"{indent}{path_obj.name}/")

        # List contents
        try:
            for item in sorted(path_obj.iterdir()):
                if item.is_dir():
                    explore_directory(item, max_depth, current_depth + 1)
                else:
                    print(f"{indent}  {item.name}")
        except PermissionError:
            print(f"{indent}  [Permission Denied]")
    except Exception as e:
        print(f"Error exploring {path}: {e}")


def test_import_method(module_name, description, extra_paths=None):
    """Test a specific import method."""
    print(f"\n--- Testing {description} ---")

    # Temporarily add paths to sys.path
    original_path = sys.path.copy()
    if extra_paths:
        for path in extra_paths:
            if path not in sys.path:
                sys.path.insert(0, str(path))

    try:
        module = importlib.import_module(module_name)
        print(f"✅ SUCCESS: {module_name} imported successfully")
        print(f"   Module file: {getattr(module, '__file__', 'Built-in')}")
        print(
            f"   Module attributes: {[attr for attr in dir(module) if not attr.startswith('_')][:10]}..."
        )

        # Test specific attributes we need
        if hasattr(module, "InputFile"):
            print("   ✅ Has InputFile")
        if hasattr(module, "PixelType"):
            print("   ✅ Has PixelType")

        return module
    except ImportError as e:
        print(f"❌ FAILED: {module_name} - {e}")
    except Exception as e:
        print(f"❌ ERROR: {module_name} - {e}")
    finally:
        # Restore original sys.path
        sys.path[:] = original_path

    return None


def find_python_packages_in_path(base_path):
    """Find Python packages in a given path."""
    packages = []
    try:
        base_path_obj = Path(base_path)
        if not base_path_obj.exists():
            return packages

        # Look for common Python package directories
        for subdir in ["lib", "lib64", "python", "site-packages"]:
            search_path = base_path_obj / subdir
            if search_path.exists():
                packages.extend(_find_packages_recursive(search_path))

        # Also check for direct Python version directories
        for item in base_path_obj.iterdir():
            if item.is_dir() and item.name.startswith("python"):
                packages.extend(_find_packages_recursive(item))

    except Exception as e:
        print(f"Error searching {base_path}: {e}")

    return packages


def _find_packages_recursive(path, max_depth=4, current_depth=0):
    """Recursively find Python packages."""
    packages = []
    if current_depth >= max_depth:
        return packages

    try:
        for item in path.iterdir():
            if item.is_dir():
                # Check if it's a Python package (has __init__.py or is named like a module)
                if (item / "__init__.py").exists() or any(
                    f.suffix == ".so" for f in item.glob("*")
                ):
                    packages.append(str(item))
                packages.extend(
                    _find_packages_recursive(item, max_depth, current_depth + 1)
                )
    except PermissionError:
        pass
    except Exception as e:
        print(f"Error in recursive search {path}: {e}")

    return packages


def main():
    """Main diagnostic function."""
    print_section("REZ OPENEXR DIAGNOSTIC SCRIPT")

    # Get environment info
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Current working directory: {os.getcwd()}")

    # Check environment variables
    print_section("REZ ENVIRONMENT VARIABLES")
    rez_vars = {
        k: v for k, v in os.environ.items() if "REZ" in k or "openexr" in k.lower()
    }
    for key, value in sorted(rez_vars.items()):
        print(f"{key}={value}")

    # Check PATH
    print_section("PATH ANALYSIS")
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    openexr_paths = [p for p in path_entries if "openexr" in p.lower()]
    print(f"Total PATH entries: {len(path_entries)}")
    print(f"OpenEXR-related PATH entries: {len(openexr_paths)}")
    for path in openexr_paths:
        print(f"  {path}")

    # Find OpenEXR package root
    openexr_root = None
    for path in openexr_paths:
        if "openexr" in path.lower() and "/bin" in path:
            openexr_root = str(Path(path).parent)
            break

    if not openexr_root:
        # Try to detect from environment
        for key, value in os.environ.items():
            if "openexr" in key.lower() and "root" in key.lower():
                openexr_root = value
                break

    if openexr_root:
        print(f"\nDetected OpenEXR package root: {openexr_root}")
    else:
        print("\n⚠️  Could not detect OpenEXR package root")
        return

    # Explore package structure
    print_section("OPENEXR PACKAGE STRUCTURE")
    explore_directory(openexr_root, max_depth=4)

    # Find Python packages in OpenEXR root
    print_section("PYTHON PACKAGES IN OPENEXR ROOT")
    python_packages = find_python_packages_in_path(openexr_root)
    print(f"Found {len(python_packages)} potential Python package directories:")
    for pkg in python_packages[:10]:  # Limit output
        print(f"  {pkg}")
    if len(python_packages) > 10:
        print(f"  ... and {len(python_packages) - 10} more")

    # Current sys.path
    print_section("CURRENT PYTHON PATH")
    print(f"sys.path entries: {len(sys.path)}")
    for i, path in enumerate(sys.path):
        print(f"  {i:2d}: {path}")

    # Test various import strategies
    print_section("IMPORT TESTING")

    # Strategy 1: Direct import
    openexr_module = test_import_method("OpenEXR", "Direct OpenEXR import")
    imath_module = test_import_method("Imath", "Direct Imath import")

    # Strategy 2: Alternative names
    if not openexr_module:
        openexr_module = test_import_method("openexr", "Alternative openexr import")

    # Strategy 3: Add potential paths to sys.path
    if not openexr_module and python_packages:
        print("\n--- Testing with additional paths ---")
        for pkg_path in python_packages[:5]:  # Test first 5 paths
            pkg_parent = str(Path(pkg_path).parent)
            openexr_module = test_import_method(
                "OpenEXR", f"OpenEXR with path {pkg_parent}", [pkg_parent]
            )
            if openexr_module:
                break
            openexr_module = test_import_method(
                "openexr", f"openexr with path {pkg_parent}", [pkg_parent]
            )
            if openexr_module:
                break

    # Test Imath similarly
    if not imath_module and python_packages:
        for pkg_path in python_packages[:5]:
            pkg_parent = str(Path(pkg_path).parent)
            imath_module = test_import_method(
                "Imath", f"Imath with path {pkg_parent}", [pkg_parent]
            )
            if imath_module:
                break

    # Test imageio backends
    print_section("IMAGEIO BACKEND TESTING")
    try:
        import imageio.v3 as iio

        print("✅ imageio.v3 imported successfully")

        # Test available formats
        try:
            formats = iio.imformats()
            exr_formats = [f for f in formats if "exr" in f.name.lower()]
            print(f"Available formats: {len(formats)}")
            print(f"EXR-related formats: {[f.name for f in exr_formats]}")
        except AttributeError:
            print("imageio.v3.imformats() not available, trying alternative methods")
            try:
                # Try reading a test EXR file
                test_result = "No test file available"
                print(f"imageio EXR test: {test_result}")
            except Exception as e:
                print(f"imageio EXR test failed: {e}")

        # Test plugins
        plugins = getattr(iio, "plugins", {})
        print(
            f"Available plugins: {list(plugins.keys()) if hasattr(plugins, 'keys') else 'Unknown'}"
        )

        # Test backends
        try:
            import imageio

            print(f"imageio version: {imageio.__version__}")

            # Check for opencv backend
            try:
                importlib.import_module("cv2")
                print("✅ OpenCV available for imageio")
            except ImportError:
                print("❌ OpenCV not available for imageio")

        except Exception as e:
            print(f"Backend check failed: {e}")

    except ImportError as e:
        print(f"❌ imageio import failed: {e}")

    # Summary
    print_section("SUMMARY")
    if openexr_module and imath_module:
        print("✅ SUCCESS: Both OpenEXR and Imath modules can be imported")
        print("   Solution: Update thumbnail_processor.py with working import method")
    elif openexr_module:
        print("⚠️  PARTIAL: OpenEXR works but Imath missing")
        print("   May need different import method for Imath")
    else:
        print("❌ FAILED: Could not import OpenEXR modules")
        print("   Rez package may need additional configuration")

    # Provide fix recommendations
    print_section("RECOMMENDED FIXES")
    if openexr_module:
        print("1. Update thumbnail_processor.py to use working import method")
        print("2. Add any required paths to sys.path before importing")
    else:
        print("1. Check if OpenEXR Rez package includes Python bindings")
        print("2. May need to request opencv or pyav packages for imageio backends")
        print("3. Consider building custom OpenEXR package with Python support")


if __name__ == "__main__":
    main()
