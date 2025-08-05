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
    UNDISTORTION_BASE_SEGMENTS = [
        "user",
        "mm",
        "3de",
        "mm-default",
        "exports",
        "scene",
        "bg01",
        "nuke_lens_distortion",
    ]
    THREEDE_SCENE_SEGMENTS = ["mm", "3de", "mm-default", "scenes", "scene"]

    # Alternative 3DE scene path patterns to try if main pattern fails
    THREEDE_ALTERNATIVE_PATTERNS = [
        ["mm", "3de", "scenes"],
        ["mm", "3de", "scene"],
        ["3de", "scenes"],
        ["3de", "scene"],
        ["matchmove", "3de", "scenes"],
        ["matchmove", "3de", "scene"],
        ["mm", "scenes"],
        ["mm", "scene"],
        ["scenes"],
        ["scene"],
    ]

    # Environment variables that may contain 3DE path information
    THREEDE_ENV_VARS = [
        "THREEDE_SCENE_PATH",
        "3DE_SCENE_PATH",
        "TDE_SCENE_PATH",
        "MM_SCENE_PATH",
        "MATCHMOVE_SCENE_PATH",
    ]

    # Common VFX plate name patterns for intelligent grouping
    PLATE_NAME_PATTERNS = [
        r"^[bf]g\d{2}$",  # bg01, fg01, bg02, fg02, etc.
        r"^plate_?\d+$",  # plate01, plate_01, plate02
        r"^comp_?\d+$",  # comp01, comp_01, comp02
        r"^shot_?\d+$",  # shot01, shot_01, shot010
        r"^sc\d+$",  # sc01, sc02, sc10
        r"^[\w]+_v\d{3}$",  # anything_v001, test_v002
        r"^elem_?\d+$",  # elem01, elem_01
        r"^cam_?\d+$",  # cam01, cam_01, cam1
        r"^tk\d+$",  # tk01, tk02 (take numbers)
        r"^roto_?\d+$",  # roto01, roto_01
    ]

    # Show-wide search configuration
    SHOW_SEARCH_ENABLED = (
        True  # Enable searching all shots in shows (not just user's shots)
    )
    SHOW_ROOT_PATHS = ["/shows"]  # Root directories where shows are stored
    MAX_SHOTS_PER_SHOW = 1000  # Limit to prevent excessive searching in huge shows
    SKIP_SEQUENCE_PATTERNS = ["tmp", "temp", "test", "old", "archive", "_dev"]
    SKIP_SHOT_PATTERNS = ["tmp", "temp", "test", "old", "archive", "_dev"]
