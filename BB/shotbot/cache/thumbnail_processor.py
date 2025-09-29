"""Thumbnail processing with multi-format support (Qt/PIL/OpenEXR)."""

from __future__ import annotations

# Standard library imports
import gc
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

# Third-party imports
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage

# Local application imports
from config import Config
from error_handling_mixin import ErrorHandlingMixin
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    # Third-party imports
    from PIL import Image as PIL


class ThumbnailProcessor(ErrorHandlingMixin, LoggingMixin):
    """Processes images into thumbnails with multi-format support.

    This class handles thumbnail generation from various image formats
    including EXR (HDR), TIFF, JPEG, and PNG. It uses multiple backends
    (Qt, PIL, OpenEXR, imageio) with fallback mechanisms for robust
    image processing.
    """

    def __init__(self, thumbnail_size: int | None = None) -> None:
        """Initialize thumbnail processor.

        Args:
            thumbnail_size: Size in pixels for square thumbnails. If None, uses config.
        """
        self._thumbnail_size = thumbnail_size or Config.CACHE_THUMBNAIL_SIZE

        # Heavy format extensions that need special handling
        self._heavy_formats = getattr(
            Config, "THUMBNAIL_FALLBACK_EXTENSIONS", [".exr", ".tiff", ".tif"]
        )

        # Thread lock for Qt operations
        self._qt_lock = threading.Lock()

        self.logger.debug(
            f"ThumbnailProcessor initialized with size {self._thumbnail_size}px"
        )

    def process_thumbnail(
        self, source_path: Path, cache_path: Path, max_dimension: int = 20000
    ) -> bool:
        """Process source image into a thumbnail at cache_path.

        Args:
            source_path: Path to the source image file
            cache_path: Path where thumbnail should be saved
            max_dimension: Maximum allowed image dimension for safety

        Returns:
            True if thumbnail was created successfully
        """
        if not source_path or not source_path.exists():
            self.logger.warning(f"Source image does not exist: {source_path}")
            return False

        if not cache_path:
            self.logger.error("Cache path not provided")
            return False

        # Create cache directory
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            self.logger.error(
                f"Failed to create cache directory {cache_path.parent}: {e}"
            )
            return False

        try:
            # Analyze source file
            file_info = self._analyze_source_file(source_path)

            # Choose processing strategy based on format and size
            if file_info["use_pil"]:
                return self._process_with_pil(source_path, cache_path, file_info)
            else:
                return self._process_with_qt(
                    source_path, cache_path, file_info, max_dimension
                )

        except MemoryError:
            self.logger.error(f"Out of memory processing: {source_path}")
            return False
        except Exception as e:
            self.logger.exception(f"Unexpected error processing {source_path}: {e}")
            return False
        finally:
            # Force garbage collection for large images
            gc.collect()

    def _analyze_source_file(self, source_path: Path) -> dict[str, object]:
        """Analyze source file to determine processing strategy.

        Args:
            source_path: Path to source image

        Returns:
            Dictionary with file analysis results
        """
        try:
            file_size_mb = source_path.stat().st_size / (1024 * 1024)
        except OSError:
            file_size_mb = 0

        suffix_lower = source_path.suffix.lower()
        is_heavy_format = suffix_lower in self._heavy_formats

        # Use PIL for heavy formats or large files
        use_pil = is_heavy_format and file_size_mb > 1  # Threshold for PIL usage

        return {
            "file_size_mb": file_size_mb,
            "suffix_lower": suffix_lower,
            "is_heavy_format": is_heavy_format,
            "use_pil": use_pil,
        }

    def _process_with_pil(
        self, source_path: Path, cache_path: Path, file_info: dict[str, object]
    ) -> bool:
        """Process image using PIL with multi-backend support.

        Args:
            source_path: Source image path
            cache_path: Output thumbnail path
            file_info: File analysis results

        Returns:
            True if processing succeeded
        """
        try:
            pil_image = self._load_image_with_pil(source_path, file_info)
            if pil_image is None:
                return False

            # Validate image
            if pil_image.size[0] == 0 or pil_image.size[1] == 0:
                self.logger.warning(f"Image has zero dimensions: {source_path}")
                return False

            # Convert to RGB if needed
            if pil_image.mode not in ["RGB", "RGBA"]:
                pil_image = pil_image.convert("RGB")

            # Create thumbnail maintaining aspect ratio
            thumb_size = (self._thumbnail_size, self._thumbnail_size)

            # Handle different PIL/Pillow versions for LANCZOS constant
            try:
                # Modern Pillow (>= 10.0.0)
                # Third-party imports
                from PIL.Image import Resampling

                resample_filter = Resampling.LANCZOS
            except ImportError:
                # Older Pillow (< 10.0.0)
                # Third-party imports
                from PIL import Image as PILImage

                resample_filter = PILImage.LANCZOS

            pil_image.thumbnail(thumb_size, resample_filter)

            # Save with atomic write
            return self._save_pil_thumbnail(pil_image, cache_path, file_info)

        except ImportError:
            self.logger.warning("PIL not available, falling back to Qt")
            return self._process_with_qt(source_path, cache_path, file_info)
        except Exception as e:
            self.logger.warning(f"PIL processing failed for {source_path}: {e}")
            return self._process_with_qt(source_path, cache_path, file_info)

    def _process_with_qt(
        self,
        source_path: Path,
        cache_path: Path,
        file_info: dict[str, object],
        max_dimension: int = 20000,
    ) -> bool:
        """Process image using Qt.

        Args:
            source_path: Source image path
            cache_path: Output thumbnail path
            file_info: File analysis results
            max_dimension: Maximum allowed dimension

        Returns:
            True if processing succeeded
        """
        image = None
        scaled = None

        try:
            # Pre-check dimensions for large formats if PIL is available
            if file_info["is_heavy_format"]:
                if not self._check_dimensions_safe(source_path, max_dimension):
                    return False

            # Use lock for all Qt operations to prevent concurrent access
            with self._qt_lock:
                # Load image with Qt
                image = QImage(str(source_path))
                if image.isNull():
                    self.logger.warning(f"Qt failed to load image: {source_path}")
                    if file_info["suffix_lower"] == ".exr":
                        self.logger.info(
                            "Note: Install OpenEXR with 'pip install OpenEXR' for EXR support"
                        )
                    return False

                # Validate dimensions
                if image.width() > max_dimension or image.height() > max_dimension:
                    self.logger.warning(
                        f"Image too large ({image.width()}x{image.height()} > {max_dimension}): {source_path}"
                    )
                    return False

                # Scale to thumbnail size
                scaled = image.scaled(
                    self._thumbnail_size,
                    self._thumbnail_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                if scaled.isNull():
                    self.logger.warning(f"Failed to scale thumbnail: {source_path}")
                    return False

                # Save with atomic write
                return self._save_qt_thumbnail(scaled, cache_path, file_info)

        finally:
            # Clean up Qt resources
            if image is not None:
                del image
            if scaled is not None:
                del scaled

    def _load_image_with_pil(
        self, source_path: Path, file_info: dict[str, object]
    ) -> PIL.Image | None:
        """Load image using PIL with format-specific handling.

        Args:
            source_path: Path to source image
            file_info: File analysis results

        Returns:
            PIL Image object or None if failed
        """
        suffix_lower = file_info["suffix_lower"]

        try:
            if suffix_lower == ".exr":
                # Try specialized EXR loaders first
                pil_image = self._load_exr_image(source_path)
                if pil_image is not None:
                    return pil_image

            # Standard PIL loading for other formats
            # Third-party imports
            from PIL import Image as PILImage

            pil_image = PILImage.open(str(source_path))

            # Force loading to verify integrity (skip for some formats)
            if suffix_lower not in [".exr"]:  # EXR already loaded above
                pil_image.load()

            return pil_image

        except Exception as e:
            self.logger.debug(f"PIL loading failed for {source_path}: {e}")
            return None

    def _get_rez_environment_info(self) -> dict[str, object]:
        """Get Rez environment information for debugging.

        Returns:
            dict: Rez environment details
        """
        # Standard library imports
        import os
        import sys

        rez_info = {}

        # Check for Rez environment variables
        rez_vars = {
            key: value for key, value in os.environ.items() if key.startswith("REZ_")
        }
        rez_info["rez_variables"] = rez_vars

        # Check for specific packages
        rez_info["openexr_root"] = os.getenv("REZ_OPENEXR_ROOT")
        rez_info["imageio_root"] = os.getenv("REZ_IMAGEIO_ROOT")
        rez_info["used_resolve"] = os.getenv("REZ_USED_RESOLVE", "").split()

        # Python path info
        rez_info["python_path"] = sys.path
        rez_info["in_rez_env"] = bool(rez_vars)

        return rez_info

    def _load_exr_image(self, source_path: Path) -> PIL.Image | None:
        """Load EXR image with specialized backends and Rez environment support.

        Args:
            source_path: Path to EXR file

        Returns:
            PIL Image object or None if failed
        """
        # Get Rez environment info for enhanced debugging
        rez_info = self._get_rez_environment_info()

        if rez_info["in_rez_env"]:
            self.logger.debug(
                f"Processing EXR in Rez environment. Resolved packages: {rez_info['used_resolve']}"
            )

        self.logger.info(f"Attempting to load EXR: {source_path.name}")

        # Try OpenEXR Python bindings first (most reliable when available)
        try:
            self.logger.debug("Trying OpenEXR Python bindings...")
            result = self._load_exr_with_openexr(source_path)
            if result is not None:
                self.logger.info(
                    f"✅ Successfully loaded EXR using OpenEXR bindings: {source_path.name}"
                )
                return result
        except Exception as e:
            self.logger.warning(
                f"OpenEXR Python bindings failed for {source_path.name}: {e}"
            )

        # Try system tools (ImageMagick) as fallback
        try:
            self.logger.debug("Trying ImageMagick system tools...")
            result = self._load_exr_with_system_tools(source_path)
            if result is not None:
                self.logger.info(
                    f"✅ Successfully loaded EXR using ImageMagick: {source_path.name}"
                )
                return result
        except Exception as e:
            self.logger.warning(
                f"ImageMagick conversion failed for {source_path.name}: {e}"
            )

        # Try imageio as fallback (likely to fail due to missing backends)
        try:
            return self._load_exr_with_imageio(source_path)
        except ImportError as e:
            if rez_info["in_rez_env"]:
                if rez_info["imageio_root"]:
                    self.logger.warning(
                        f"imageio import failed in Rez environment (package at {rez_info['imageio_root']}): {e}"
                    )
                else:
                    self.logger.warning(
                        f"imageio import failed in Rez environment (no REZ_IMAGEIO_ROOT): {e}"
                    )
            else:
                self.logger.debug("imageio not available")
        except Exception as e:
            self.logger.debug(f"imageio loading failed: {e}")

        # Final error summary for Rez environments
        if rez_info["in_rez_env"]:
            self.logger.error(
                f"All EXR backends failed in Rez environment. Check package configurations for: {[pkg for pkg in rez_info['used_resolve'] if 'openexr' in pkg.lower() or 'imageio' in pkg.lower()]}"  # type: ignore[misc]
            )

        # Log complete failure
        self.logger.error(
            f"❌ Failed to load EXR file {source_path.name} - all backends failed. "
            f"Ensure ImageMagick is installed or OpenEXR Python bindings are available."
        )

        return None

    def _load_exr_with_system_tools(self, source_path: Path) -> PIL.Image | None:
        """Load EXR using system tools (ImageMagick + OpenEXR native tools).

        This method uses external system tools that we confirmed are working
        in the Rez environment, rather than Python bindings which aren't available.

        Args:
            source_path: Path to EXR file

        Returns:
            PIL Image object or None if failed
        """
        # Standard library imports
        import subprocess
        import tempfile

        # Third-party imports
        from PIL import Image as PILImage

        self.logger.info(
            f"Processing EXR with system tools: {source_path.name} ({source_path.stat().st_size / (1024 * 1024):.1f}MB)"
        )

        # First, check if ImageMagick convert is available
        try:
            subprocess.run(
                ["convert", "-version"],
                capture_output=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.SubprocessError) as e:
            self.logger.warning(f"ImageMagick convert not available: {e}")
            raise ImportError("ImageMagick convert command not found")

        # Validate the EXR file using exrinfo (if available)
        try:
            result = subprocess.run(
                ["exrinfo", str(source_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                self.logger.debug(
                    f"EXR validation failed with exrinfo: {result.stderr}"
                )
                # Continue anyway - maybe convert will work

            # Log EXR info for debugging
            info_lines = result.stdout.strip().split("\n")[:3]  # First 3 lines
            self.logger.debug(f"EXR file validated: {', '.join(info_lines)}")

        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            subprocess.SubprocessError,
        ) as e:
            self.logger.debug(f"exrinfo validation failed: {e}")
            # Continue anyway - maybe convert will work

        # Convert EXR to JPEG using ImageMagick (confirmed working)
        temp_jpg = None
        try:
            # Create temporary JPEG file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_jpg = tmp.name

            # Use ImageMagick convert with appropriate settings for EXR
            convert_cmd = [
                "convert",
                str(source_path),
                "-resize",
                f"{self._thumbnail_size}x{self._thumbnail_size}>",  # > means only downsize
                "-quality",
                "90",
                "-colorspace",
                "sRGB",  # Ensure proper colorspace conversion
                temp_jpg,
            ]

            self.logger.info(
                f"Running ImageMagick convert: {' '.join(convert_cmd[:3])}..."
            )
            result = subprocess.run(
                convert_cmd, capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                self.logger.error(
                    f"ImageMagick conversion failed for {source_path.name}: {result.stderr}"
                )
                return None

            # Check if output file was created
            temp_path = Path(temp_jpg)
            if not temp_path.exists() or temp_path.stat().st_size == 0:
                self.logger.error(
                    f"ImageMagick produced no output file for {source_path.name}"
                )
                return None

            # Load the converted JPEG with PIL
            pil_image = PILImage.open(temp_jpg)
            pil_image.load()  # Force load to ensure it's valid

            self.logger.info(
                f"✅ EXR converted successfully: {source_path.name} -> {pil_image.size}"
            )
            return pil_image

        except subprocess.TimeoutExpired as e:
            self.logger.error(
                f"ImageMagick conversion timed out after 30s for {source_path.name}: {e}"
            )
            return None

        except (FileNotFoundError, subprocess.SubprocessError) as e:
            self.logger.error(
                f"ImageMagick subprocess error for {source_path.name}: {e}"
            )
            return None

        except Exception as e:
            self.logger.error(
                f"PIL loading of converted EXR failed for {source_path.name}: {e}"
            )
            return None

        finally:
            # Clean up temporary file
            if temp_jpg and Path(temp_jpg).exists():
                try:
                    Path(temp_jpg).unlink()
                except Exception:
                    pass  # Best effort cleanup

    def _load_exr_with_openexr(self, source_path: Path) -> PIL.Image | None:
        """Load EXR using OpenEXR library with Rez environment support.

        Handles both official OpenEXR package and alternative openexr packages
        commonly found in VFX Rez environments.

        Args:
            source_path: Path to EXR file

        Returns:
            PIL Image object
        """
        # Rez environment diagnostics
        # Standard library imports
        import os

        # Third-party imports
        import numpy as np
        from PIL import Image as PILImage

        rez_openexr_root = os.getenv("REZ_OPENEXR_ROOT")
        if rez_openexr_root:
            self.logger.debug(f"Rez OpenEXR package detected at: {rez_openexr_root}")

        # Try dual import strategy for Rez compatibility
        openexr_module = None
        imath_module = None
        api_style = None

        # Strategy 1: Try official OpenEXR (uppercase)
        try:
            # Third-party imports
            import Imath
            import OpenEXR

            openexr_module = OpenEXR
            imath_module = Imath
            api_style = "official"
            self.logger.debug("Using official OpenEXR package (uppercase)")
        except ImportError:
            self.logger.debug(
                "Official OpenEXR package not available, trying alternative"
            )

        # Strategy 2: Try alternative openexr (lowercase) - common in Rez
        if openexr_module is None:
            try:
                # Third-party imports
                import openexr

                # Alternative packages often have different Imath location
                try:
                    # Third-party imports
                    import Imath

                    imath_module = Imath
                except ImportError:
                    # Some packages bundle Imath differently
                    # Third-party imports
                    import imath as Imath  # type: ignore[import-untyped]

                    imath_module = Imath
                openexr_module = openexr
                api_style = "alternative"
                self.logger.debug("Using alternative openexr package (lowercase)")
            except ImportError:
                self.logger.debug("Alternative openexr package not available")

        if openexr_module is None or imath_module is None:
            # Enhanced error reporting for Rez environments
            missing_modules = []
            if openexr_module is None:
                missing_modules.append("OpenEXR")
            if imath_module is None:
                missing_modules.append("Imath")

            error_msg = f"Required modules not found: {', '.join(missing_modules)}"
            if rez_openexr_root:
                error_msg += (
                    f" (Rez package at {rez_openexr_root} may be misconfigured)"
                )
            else:
                error_msg += " (not in Rez environment, check package installation)"
            raise ImportError(error_msg)

        # Open EXR file using detected API
        if api_style == "official":
            exr_file = openexr_module.InputFile(str(source_path))
        else:
            # Alternative packages may have different API
            try:
                exr_file = openexr_module.InputFile(str(source_path))
            except AttributeError:
                # Some alternative packages use different method names
                exr_file = openexr_module.File(str(source_path))

        header = exr_file.header()

        # Get dimensions
        dw = header["dataWindow"]
        width = dw.max.x - dw.min.x + 1
        height = dw.max.y - dw.min.y + 1

        # Read RGB channels using detected Imath module
        FLOAT = imath_module.PixelType(imath_module.PixelType.FLOAT)
        channels = []

        for channel in ["R", "G", "B"]:
            if channel in header["channels"]:
                channel_str = exr_file.channel(channel, FLOAT)
                channel_array = np.frombuffer(channel_str, dtype=np.float32)
                channel_array = channel_array.reshape((height, width))
                channels.append(channel_array)
            else:
                # Missing channel, use zeros
                channels.append(np.zeros((height, width), dtype=np.float32))

        # Stack channels and apply tone mapping
        img_array = np.stack(channels, axis=2)
        img_array = np.clip(img_array, 0, 1)  # Simple tone mapping
        img_array = (img_array * 255).astype(np.uint8)

        self.logger.debug(f"Successfully loaded EXR using {api_style} OpenEXR API")
        return PILImage.fromarray(img_array, mode="RGB")

    def _load_exr_with_imageio(self, source_path: Path) -> PIL.Image | None:
        """Load EXR using imageio library with Rez environment support.

        Args:
            source_path: Path to EXR file

        Returns:
            PIL Image object
        """
        # Standard library imports
        import os

        # Third-party imports
        import numpy as np
        from PIL import Image as PILImage

        # Rez environment diagnostics
        rez_imageio_root = os.getenv("REZ_IMAGEIO_ROOT")
        if rez_imageio_root:
            self.logger.debug(f"Rez imageio package detected at: {rez_imageio_root}")

        # Try imageio import with version fallback
        imageio_module = None
        try:
            # Third-party imports
            import imageio.v3 as iio

            imageio_module = iio
            self.logger.debug("Using imageio.v3 API")
        except ImportError:
            try:
                # Third-party imports
                import imageio as iio

                imageio_module = iio
                self.logger.debug("Using imageio v2 API (fallback)")
            except ImportError:
                error_msg = "imageio not available"
                if rez_imageio_root:
                    error_msg += (
                        f" (Rez package at {rez_imageio_root} may be misconfigured)"
                    )
                raise ImportError(error_msg)

        # Check for EXR backend availability
        try:
            # Test backend detection by trying to read the file
            img_array = imageio_module.imread(str(source_path))
            self.logger.debug("imageio successfully loaded EXR with available backend")
        except Exception as e:
            # Enhanced error reporting for missing backends
            error_details = str(e)
            if "Could not find a backend" in error_details:
                backend_msg = "imageio missing EXR backends"
                if rez_imageio_root:
                    backend_msg += " (Rez imageio package needs EXR plugins - check if imageio[opencv] or imageio[pyav] components are included)"
                else:
                    backend_msg += (
                        " (install with: pip install imageio[opencv] or imageio[pyav])"
                    )
                self.logger.warning(backend_msg)
            raise

        # Normalize if needed
        if img_array.dtype in [np.float32, np.float64]:
            img_array = np.clip(img_array, 0, 1)
            img_array = (img_array * 255).astype(np.uint8)
        elif img_array.dtype == np.uint16:
            img_array = (img_array / 256).astype(np.uint8)

        # Convert to PIL based on channels
        if len(img_array.shape) == 2:
            return PILImage.fromarray(img_array, mode="L")
        elif len(img_array.shape) == 3:
            if img_array.shape[2] == 3:
                return PILImage.fromarray(img_array, mode="RGB")
            elif img_array.shape[2] == 4:
                return PILImage.fromarray(img_array, mode="RGBA")

        raise ValueError(f"Unsupported image shape: {img_array.shape}")

    def _check_dimensions_safe(self, source_path: Path, max_dimension: int) -> bool:
        """Check if image dimensions are safe to load.

        Args:
            source_path: Path to image file
            max_dimension: Maximum allowed dimension

        Returns:
            True if dimensions are safe
        """
        try:
            # Third-party imports
            from PIL import Image as PILImage

            with PILImage.open(str(source_path)) as pil_img:
                width, height = pil_img.size
                if width > max_dimension or height > max_dimension:
                    self.logger.warning(
                        f"Image too large ({width}x{height} > {max_dimension}): {source_path}"
                    )
                    return False
                return True

        except Exception:
            # If we can't check, assume it's safe and let Qt handle it
            return True

    def _save_pil_thumbnail(
        self, pil_image: PIL.Image, cache_path: Path, file_info: dict[str, object]
    ) -> bool:
        """Save PIL image as thumbnail with atomic write.

        Args:
            pil_image: PIL Image object
            cache_path: Output path for thumbnail
            file_info: File analysis results

        Returns:
            True if save succeeded
        """
        # Ensure cache directory exists
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            self.logger.error(
                f"Failed to create cache directory {cache_path.parent}: {e}"
            )
            return False

        temp_path = cache_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")

        try:
            # Higher quality for heavy formats
            quality = 95 if file_info["is_heavy_format"] else 90
            pil_image.save(str(temp_path), "JPEG", quality=quality, optimize=True)

            # Verify temp file was created successfully
            if not temp_path.exists() or temp_path.stat().st_size == 0:
                self.logger.error(f"Temp file was not created or is empty: {temp_path}")
                return False

            # Atomic move to final location
            temp_path.replace(cache_path)

            file_size_kb = cache_path.stat().st_size / 1024
            self.logger.debug(
                f"Saved PIL thumbnail: {cache_path.name} "
                + f"({file_info['file_size_mb']:.1f}MB -> {file_size_kb:.1f}KB)"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to save PIL thumbnail: {e}")
            self._cleanup_temp_file(temp_path)
            return False

    def _save_qt_thumbnail(
        self, qt_image: QImage, cache_path: Path, file_info: dict[str, object]
    ) -> bool:
        """Save Qt image as thumbnail with atomic write.

        Args:
            qt_image: QImage object
            cache_path: Output path for thumbnail
            file_info: File analysis results

        Returns:
            True if save succeeded
        """
        temp_path = cache_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")

        try:
            # Higher quality for heavy formats
            quality = 95 if file_info["is_heavy_format"] else 85

            if qt_image.save(str(temp_path), "JPEG", quality):  # type: ignore[call-overload]
                # Atomic move to final location
                temp_path.replace(cache_path)

                file_size_kb = cache_path.stat().st_size / 1024
                self.logger.debug(
                    f"Saved Qt thumbnail: {cache_path.name} "
                    + f"({file_info['file_size_mb']:.1f}MB -> {file_size_kb:.1f}KB)"
                )
                return True
            else:
                self.logger.warning(f"Qt failed to save thumbnail: {temp_path}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to save Qt thumbnail: {e}")
            return False
        finally:
            self._cleanup_temp_file(temp_path)

    def process_thumbnails_parallel(
        self, images: list[Path], max_workers: int = 4
    ) -> list[Path | None]:
        """Process multiple thumbnails in parallel using ThreadPoolExecutor.

        This implements the P3 performance requirement for batch thumbnail processing
        with a 50-70% speed improvement target through parallelization.

        Args:
            images: List of image paths to process
            max_workers: Maximum number of parallel workers (default: 4)

        Returns:
            List of thumbnail paths (or None for failed thumbnails) in the same order as input

        Example:
            >>> processor = ThumbnailProcessor()
            >>> images = [Path("/path/to/img1.exr"), Path("/path/to/img2.jpg")]
            >>> thumbnails = processor.process_thumbnails_parallel(images)
            >>> for img, thumb in zip(images, thumbnails):
            ...     if thumb:
            ...         print(f"Processed {img} -> {thumb}")
        """
        # Standard library imports
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        start_time = time.time()
        results: list[Path | None] = [None] * len(images)  # Pre-allocate results list

        # Create a mapping of future to index for ordered results
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(self._process_single_thumbnail, img_path): i
                for i, img_path in enumerate(images)
            }

            # Process completed futures
            completed = 0
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    result = future.result(timeout=30)  # 30s timeout per image
                    results[index] = result
                    completed += 1

                    # Log progress for large batches
                    if len(images) > 10 and completed % 10 == 0:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed
                        self.logger.info(
                            f"Batch thumbnail progress: {completed}/{len(images)} "
                            f"({rate:.1f} imgs/sec)"
                        )

                except Exception as e:
                    self.logger.error(
                        f"Failed to process thumbnail at index {index}: {e}"
                    )
                    results[index] = None

        # Log final statistics
        elapsed = time.time() - start_time
        successful = sum(1 for r in results if r is not None)
        self.logger.info(
            f"Batch thumbnail processing complete: {successful}/{len(images)} successful "
            f"in {elapsed:.2f}s ({len(images) / elapsed:.1f} imgs/sec)"
        )

        return results

    def _process_single_thumbnail(self, source_path: Path) -> Path | None:
        """Process a single thumbnail for use in parallel batch processing.

        This is a wrapper around the existing process_thumbnail method that
        handles the caching and returns just the path for batch operations.

        Args:
            source_path: Path to source image

        Returns:
            Path to processed thumbnail or None if processing failed
        """
        try:
            # Generate cache path based on source
            cache_key = source_path.stem + "_" + str(hash(str(source_path)))
            cache_path = Path("/tmp") / f"thumb_{cache_key}.jpg"

            # Process the thumbnail using existing method
            result = self.process_thumbnail(source_path, cache_path)

            if result:
                return cache_path
            return None

        except Exception as e:
            self.logger.error(f"Error processing single thumbnail {source_path}: {e}")
            return None

    def _cleanup_temp_file(self, temp_path: Path) -> None:
        """Clean up temporary file if it exists.

        Args:
            temp_path: Path to temporary file
        """
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass  # Ignore cleanup errors

    # ==================== ASYNC EXR PROCESSING ====================
    # Added for Day 1 of refactoring plan to fix EXR blocking issue

    async def process_exr_batch_async(self, exr_files: list[Path]) -> dict[Path, Path]:
        """Process multiple EXR files in parallel without blocking UI.

        This method processes EXR files asynchronously to prevent UI freezing.
        Each EXR conversion runs in a separate asyncio task.

        Args:
            exr_files: List of EXR file paths to process

        Returns:
            Dictionary mapping source EXR paths to generated thumbnail paths
        """
        import asyncio

        self.logger.info(f"Starting async batch processing of {len(exr_files)} EXR files")

        # Create tasks for parallel processing
        tasks = []
        for exr_file in exr_files:
            task = asyncio.create_task(self._convert_single_exr_async(exr_file))
            tasks.append(task)

        # Wait for all conversions to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dictionary, filtering out failures
        processed = {}
        for exr_file, result in zip(exr_files, results):
            if isinstance(result, Exception):
                self.logger.error(f"Failed to process {exr_file.name}: {result}")
            elif result is not None:
                processed[exr_file] = result

        self.logger.info(f"Completed async batch: {len(processed)}/{len(exr_files)} succeeded")
        return processed

    async def _convert_single_exr_async(self, source_path: Path) -> Path | None:
        """Convert single EXR file asynchronously.

        Runs ImageMagick conversion in a thread pool to avoid blocking.

        Args:
            source_path: Path to EXR file

        Returns:
            Path to generated thumbnail or None if failed
        """
        import asyncio
        import subprocess
        from concurrent.futures import ThreadPoolExecutor

        self.logger.debug(f"Starting async conversion of {source_path.name}")

        # Generate cache path for thumbnail
        from cache_config import CacheConfig
        cache_dir = CacheConfig.get_cache_directory() / "thumbnails"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Use hash of path for consistent cache key
        import hashlib
        path_hash = hashlib.md5(str(source_path).encode()).hexdigest()
        thumbnail_path = cache_dir / f"{path_hash}_{self._thumbnail_size}.jpg"

        # Skip if already cached
        if thumbnail_path.exists():
            self.logger.debug(f"Using cached thumbnail for {source_path.name}")
            return thumbnail_path

        # Prepare conversion command
        cmd = [
            "convert",
            str(source_path),
            "-resize",
            f"{self._thumbnail_size}x{self._thumbnail_size}>",
            "-quality",
            "90",
            "-colorspace",
            "sRGB",
            str(thumbnail_path),
        ]

        # Run conversion in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=4)

        try:
            # Execute subprocess in thread pool
            def run_convert():
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

            result = await loop.run_in_executor(executor, run_convert)

            if result.returncode != 0:
                self.logger.error(
                    f"ImageMagick failed for {source_path.name}: {result.stderr}"
                )
                return None

            # Verify output was created
            if not thumbnail_path.exists() or thumbnail_path.stat().st_size == 0:
                self.logger.error(f"No output created for {source_path.name}")
                return None

            self.logger.debug(f"Successfully converted {source_path.name}")
            return thumbnail_path

        except subprocess.TimeoutExpired:
            self.logger.error(f"Conversion timeout for {source_path.name}")
            return None
        except Exception as e:
            self.logger.error(f"Async conversion error for {source_path.name}: {e}")
            return None

    def __repr__(self) -> str:
        """String representation of thumbnail processor."""
        return f"ThumbnailProcessor(size={self._thumbnail_size}px)"


class AsyncEXRProcessor(QThread):
    """Qt thread wrapper for async EXR processing without UI blocking.

    This class provides Qt integration for the async EXR processing,
    allowing the UI to remain responsive during batch EXR conversions.
    """

    # Signals for progress and completion
    progress_updated = Signal(int)  # Current count of processed files
    batch_completed = Signal(dict)  # Dict of source->thumbnail paths
    error_occurred = Signal(str)  # Error message

    def __init__(self, processor: ThumbnailProcessor, exr_files: list[Path], parent=None):
        """Initialize async EXR processor.

        Args:
            processor: ThumbnailProcessor instance to use
            exr_files: List of EXR files to process
            parent: Parent QObject
        """
        super().__init__(parent)
        self._processor = processor
        self._exr_files = exr_files
        self._results = {}

    def run(self):
        """Run async EXR processing in separate thread."""
        import asyncio

        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run the async batch processing
            self._results = loop.run_until_complete(
                self._process_with_progress()
            )

            # Convert Path objects to strings for Qt signal marshalling
            # Qt can't properly serialize Path objects across threads
            str_results = {
                str(k): str(v) for k, v in self._results.items()
            }

            # Emit completion signal with string paths
            self.batch_completed.emit(str_results)

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            # Clean up event loop
            loop.close()

    async def _process_with_progress(self) -> dict[Path, Path]:
        """Process EXRs with progress updates."""
        results = {}
        total = len(self._exr_files)

        # Process in smaller batches for more frequent updates
        batch_size = 4
        for i in range(0, total, batch_size):
            batch = self._exr_files[i:i + batch_size]

            # Process this batch
            batch_results = await self._processor.process_exr_batch_async(batch)
            results.update(batch_results)

            # Emit progress
            processed = min(i + batch_size, total)
            self.progress_updated.emit(processed)

        return results
