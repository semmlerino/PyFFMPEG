"""Configuration constants for ShotBot application."""

from pathlib import Path


class Config:
    """Application configuration."""

    # App info
    APP_NAME = "ShotBot"
    APP_VERSION = "1.0.0"

    # Window settings
    DEFAULT_WINDOW_WIDTH = 1200
    DEFAULT_WINDOW_HEIGHT = 800
    MIN_WINDOW_WIDTH = 800
    MIN_WINDOW_HEIGHT = 600

    # Thumbnail settings
    DEFAULT_THUMBNAIL_SIZE = 200
    MIN_THUMBNAIL_SIZE = 100
    MAX_THUMBNAIL_SIZE = 400
    THUMBNAIL_SPACING = 20  # Increased to accommodate selection highlight
    PLACEHOLDER_COLOR = "#444444"

    # Shot paths
    SHOWS_ROOT = "/shows"
    THUMBNAIL_PATH_PATTERN = "{shows_root}/{show}/shots/{sequence}/{shot}/publish/editorial/cutref/v001/jpg/1920x1080/"

    # Commands
    APPS = {
        "3de": "3de",
        "nuke": "nuke",
        "maya": "maya",
        "rv": "rv",
        "publish": "publish_standalone",
    }
    DEFAULT_APP = "nuke"

    # Settings file
    SETTINGS_FILE = Path.home() / ".shotbot" / "settings.json"

    # UI settings
    LOG_MAX_LINES = 1000
    GRID_COLUMNS = 4  # Default columns, will be dynamic based on width

    # Threading
    MAX_THUMBNAIL_THREADS = 4

    # Memory optimization
    USE_MEMORY_OPTIMIZED_GRID = True  # Enable viewport-based loading
    MAX_LOADED_THUMBNAILS = 50  # Maximum thumbnails to keep in memory
    VIEWPORT_BUFFER_ROWS = 2  # Extra rows to load beyond viewport
    THUMBNAIL_UNLOAD_DELAY_MS = 5000  # Delay before unloading invisible thumbnails

    # Process and command settings
    SUBPROCESS_TIMEOUT_SECONDS = 10  # Timeout for subprocess calls
    WS_COMMAND_TIMEOUT_SECONDS = 10  # Timeout for ws -sg command specifically

    # Image and memory limits
    MAX_THUMBNAIL_DIMENSION_PX = 4096  # Maximum dimension for thumbnail images
    MAX_INFO_PANEL_DIMENSION_PX = 2048  # Maximum dimension for info panel thumbnails  
    MAX_CACHE_DIMENSION_PX = 10000  # Maximum dimension for cached images
    MAX_THUMBNAIL_MEMORY_MB = 50  # Maximum memory usage for thumbnail images
    MAX_FILE_SIZE_MB = 100  # Maximum file size for image loading

    # Cache settings
    CACHE_EXPIRY_MINUTES = 30  # How long to keep cached data
    CACHE_THUMBNAIL_SIZE = 512  # Size for cached thumbnails

    # VFX pipeline settings
    DEFAULT_USERNAME = "gabriel-h"  # Default username for pipeline paths
    UNDISTORTION_SUBPATH = "mm"  # Subdirectory for undistortion files

    # File extensions
    IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tiff", ".tif", ".exr"]
    NUKE_EXTENSIONS = [".nk", ".nknc"]
    THREEDE_EXTENSIONS = [".3de"]

    # Path construction segments
    THUMBNAIL_SEGMENTS = ["publish", "editorial", "cutref", "v001", "jpg", "1920x1080"]
    RAW_PLATE_SEGMENTS = ["publish", "turnover", "plate", "input_plate", "bg01"]
    UNDISTORTION_BASE_SEGMENTS = ["user", "mm", "3de", "mm-default", "exports", "scene", "bg01", "nuke_lens_distortion"]
    THREEDE_SCENE_SEGMENTS = ["mm", "3de", "mm-default", "scenes", "scene"]
