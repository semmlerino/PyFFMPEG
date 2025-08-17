"""Unit tests for threede_scene_model module.

This module tests the ThreeDEScene dataclass and ThreeDESceneModel class.
Following the testing guide principles:
- Test behavior, not implementation
- Use real components with test doubles for I/O
- Mock only at system boundaries
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cache_manager import CacheManager
from shot_model import Shot
from threede_scene_model import ThreeDEScene, ThreeDESceneModel
from utils import PathUtils, ValidationUtils


# Test Fixtures
@pytest.fixture
def sample_scene():
    """Create a sample ThreeDEScene for testing."""
    return ThreeDEScene(
        show="test_show",
        sequence="seq01",
        shot="shot01",
        workspace_path="/shows/test_show/seq01/seq01_shot01",
        user="otheruser",
        plate="FG01",
        scene_path=Path(
            "/shows/test_show/seq01/seq01_shot01/user/otheruser/work/3de/scenes/test.3de",
        ),
    )


@pytest.fixture
def sample_scenes():
    """Create multiple ThreeDEScene objects for testing."""
    scenes = [
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/seq01/seq01_shot01",
            user="user1",
            plate="FG01",
            scene_path=Path(
                "/shows/test_show/seq01/seq01_shot01/user/user1/work/3de/scenes/test1.3de",
            ),
        ),
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot02",
            workspace_path="/shows/test_show/seq01/seq01_shot02",
            user="user2",
            plate="BG01",
            scene_path=Path(
                "/shows/test_show/seq01/seq01_shot02/user/user2/work/3de/scenes/test2.3de",
            ),
        ),
        ThreeDEScene(
            show="test_show",
            sequence="seq02",
            shot="shot01",
            workspace_path="/shows/test_show/seq02/seq02_shot01",
            user="user3",
            plate="EL01",
            scene_path=Path(
                "/shows/test_show/seq02/seq02_shot01/user/user3/work/3de/scenes/test3.3de",
            ),
        ),
    ]
    return scenes


@pytest.fixture
def duplicate_scenes():
    """Create scenes with duplicates for the same shot to test deduplication."""
    scenes = [
        # Two scenes for seq01_shot01 - different users and plates
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/seq01/seq01_shot01",
            user="user1",
            plate="FG01",
            scene_path=Path(
                "/shows/test_show/seq01/seq01_shot01/user/user1/work/3de/scenes/old.3de",
            ),
        ),
        ThreeDEScene(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/seq01/seq01_shot01",
            user="user2",
            plate="BG01",
            scene_path=Path(
                "/shows/test_show/seq01/seq01_shot01/user/user2/work/3de/scenes/new.3de",
            ),
        ),
        # Single scene for seq02_shot01
        ThreeDEScene(
            show="test_show",
            sequence="seq02",
            shot="shot01",
            workspace_path="/shows/test_show/seq02/seq02_shot01",
            user="user3",
            plate="EL01",
            scene_path=Path(
                "/shows/test_show/seq02/seq02_shot01/user/user3/work/3de/scenes/test.3de",
            ),
        ),
    ]
    return scenes


@pytest.fixture
def mock_cache_manager(tmp_path):
    """Create a real CacheManager with temp storage for testing."""
    return CacheManager(cache_dir=tmp_path / "cache")


@pytest.fixture
def sample_shots():
    """Create sample Shot objects for testing."""
    return [
        Shot(
            show="test_show",
            sequence="seq01",
            shot="shot01",
            workspace_path="/shows/test_show/seq01/seq01_shot01",
        ),
        Shot(
            show="test_show",
            sequence="seq01",
            shot="shot02",
            workspace_path="/shows/test_show/seq01/seq01_shot02",
        ),
    ]


class TestThreeDEScene:
    """Test ThreeDEScene dataclass."""

    def test_scene_creation(self, sample_scene):
        """Test basic scene creation and properties."""
        assert sample_scene.show == "test_show"
        assert sample_scene.sequence == "seq01"
        assert sample_scene.shot == "shot01"
        assert sample_scene.user == "otheruser"
        assert sample_scene.plate == "FG01"
        assert isinstance(sample_scene.scene_path, Path)

    def test_full_name_property(self, sample_scene):
        """Test full_name property returns correct format."""
        assert sample_scene.full_name == "seq01_shot01"

    def test_display_name_property(self, sample_scene):
        """Test display_name property for deduplicated scenes."""
        assert sample_scene.display_name == "seq01_shot01 - otheruser"

    def test_thumbnail_dir_property(self, sample_scene):
        """Test thumbnail_dir property builds correct path."""
        with patch.object(PathUtils, "build_thumbnail_path") as mock_build:
            mock_build.return_value = Path("/test/thumbnail/path")

            result = sample_scene.thumbnail_dir

            mock_build.assert_called_once()
            assert isinstance(result, Path)

    def test_get_thumbnail_path_editorial_found(self, sample_scene):
        """Test get_thumbnail_path when editorial thumbnail exists."""
        # Mock the path validation and file discovery
        with patch.object(PathUtils, "validate_path_exists") as mock_validate:
            with patch(
                "threede_scene_model.FileUtils.get_first_image_file",
            ) as mock_get_image:
                mock_validate.return_value = True
                mock_get_image.return_value = Path("/test/thumbnail.jpg")

                # First call should search and cache
                result = sample_scene.get_thumbnail_path()
                assert result == Path("/test/thumbnail.jpg")
                mock_validate.assert_called_once()
                mock_get_image.assert_called_once()

                # Second call should use cached result
                mock_validate.reset_mock()
                mock_get_image.reset_mock()
                result2 = sample_scene.get_thumbnail_path()
                assert result2 == Path("/test/thumbnail.jpg")
                mock_validate.assert_not_called()
                mock_get_image.assert_not_called()

    def test_get_thumbnail_path_turnover_fallback(self, sample_scene):
        """Test get_thumbnail_path falls back to turnover plate."""
        with patch.object(PathUtils, "validate_path_exists") as mock_validate:
            with patch(
                "threede_scene_model.FileUtils.get_first_image_file",
            ) as mock_get_image:
                with patch.object(
                    PathUtils, "find_turnover_plate_thumbnail",
                ) as mock_turnover:
                    # Editorial not found
                    mock_validate.return_value = False
                    mock_get_image.return_value = None
                    # Turnover found
                    mock_turnover.return_value = Path("/test/turnover.exr")

                    result = sample_scene.get_thumbnail_path()
                    assert result == Path("/test/turnover.exr")
                    mock_turnover.assert_called_once()

    def test_get_thumbnail_path_publish_fallback(self, sample_scene):
        """Test get_thumbnail_path falls back to any publish thumbnail."""
        with patch.object(PathUtils, "validate_path_exists") as mock_validate:
            with patch(
                "threede_scene_model.FileUtils.get_first_image_file",
            ) as mock_get_image:
                with patch.object(
                    PathUtils, "find_turnover_plate_thumbnail",
                ) as mock_turnover:
                    with patch.object(
                        PathUtils, "find_any_publish_thumbnail",
                    ) as mock_publish:
                        # Nothing found until publish
                        mock_validate.return_value = False
                        mock_get_image.return_value = None
                        mock_turnover.return_value = None
                        mock_publish.return_value = Path("/test/publish.exr")

                        result = sample_scene.get_thumbnail_path()
                        assert result == Path("/test/publish.exr")
                        mock_publish.assert_called_once()

    def test_get_thumbnail_path_none_found(self, sample_scene):
        """Test get_thumbnail_path returns None when no thumbnail found."""
        with patch.object(PathUtils, "validate_path_exists") as mock_validate:
            with patch(
                "threede_scene_model.FileUtils.get_first_image_file",
            ) as mock_get_image:
                with patch.object(
                    PathUtils, "find_turnover_plate_thumbnail",
                ) as mock_turnover:
                    with patch.object(
                        PathUtils, "find_any_publish_thumbnail",
                    ) as mock_publish:
                        # Nothing found
                        mock_validate.return_value = False
                        mock_get_image.return_value = None
                        mock_turnover.return_value = None
                        mock_publish.return_value = None

                        result = sample_scene.get_thumbnail_path()
                        assert result is None

                        # Verify caching of None result
                        mock_validate.reset_mock()
                        result2 = sample_scene.get_thumbnail_path()
                        assert result2 is None
                        mock_validate.assert_not_called()

    def test_to_dict_serialization(self, sample_scene):
        """Test scene serialization to dictionary."""
        data = sample_scene.to_dict()

        assert isinstance(data, dict)
        assert data["show"] == "test_show"
        assert data["sequence"] == "seq01"
        assert data["shot"] == "shot01"
        assert data["workspace_path"] == "/shows/test_show/seq01/seq01_shot01"
        assert data["user"] == "otheruser"
        assert data["plate"] == "FG01"
        assert isinstance(data["scene_path"], str)
        assert "test.3de" in data["scene_path"]

    def test_from_dict_deserialization(self):
        """Test scene creation from dictionary."""
        data = {
            "show": "test_show",
            "sequence": "seq01",
            "shot": "shot01",
            "workspace_path": "/shows/test_show/seq01/seq01_shot01",
            "user": "testuser",
            "plate": "BG01",
            "scene_path": "/test/path/scene.3de",
        }

        scene = ThreeDEScene.from_dict(data)

        assert scene.show == "test_show"
        assert scene.sequence == "seq01"
        assert scene.shot == "shot01"
        assert scene.workspace_path == "/shows/test_show/seq01/seq01_shot01"
        assert scene.user == "testuser"
        assert scene.plate == "BG01"
        assert isinstance(scene.scene_path, Path)
        assert str(scene.scene_path) == "/test/path/scene.3de"

    def test_roundtrip_serialization(self, sample_scene):
        """Test that to_dict -> from_dict preserves data."""
        data = sample_scene.to_dict()
        restored = ThreeDEScene.from_dict(data)

        assert restored.show == sample_scene.show
        assert restored.sequence == sample_scene.sequence
        assert restored.shot == sample_scene.shot
        assert restored.workspace_path == sample_scene.workspace_path
        assert restored.user == sample_scene.user
        assert restored.plate == sample_scene.plate
        assert str(restored.scene_path) == str(sample_scene.scene_path)


class TestThreeDESceneModel:
    """Test ThreeDESceneModel class."""

    def test_initialization_without_cache(self, mock_cache_manager):
        """Test model initialization without loading cache."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        assert model.scenes == []
        assert model.cache_manager == mock_cache_manager
        assert isinstance(model._excluded_users, set)

    def test_initialization_with_cache_loading(self, mock_cache_manager, sample_scenes):
        """Test model initialization with cache loading."""
        # Pre-populate cache
        cache_data = [scene.to_dict() for scene in sample_scenes]
        mock_cache_manager.cache_threede_scenes(cache_data)

        # Create model with cache loading
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=True)

        assert len(model.scenes) == len(sample_scenes)
        for i, scene in enumerate(model.scenes):
            assert scene.show == sample_scenes[i].show
            assert scene.sequence == sample_scenes[i].sequence
            assert scene.shot == sample_scenes[i].shot

    def test_load_from_cache_with_invalid_data(self, mock_cache_manager):
        """Test that invalid cache entries are skipped."""
        # Add invalid cache data
        invalid_data = [
            {"invalid": "data"},  # Missing required fields
            {"show": "test", "sequence": "seq01"},  # Incomplete
        ]
        valid_data = {
            "show": "test_show",
            "sequence": "seq01",
            "shot": "shot01",
            "workspace_path": "/test/path",
            "user": "user1",
            "plate": "FG01",
            "scene_path": "/test/scene.3de",
        }
        mock_cache_manager.cache_threede_scenes(invalid_data + [valid_data])

        # Load with invalid data
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=True)

        # Should only load the valid entry
        assert len(model.scenes) == 1
        assert model.scenes[0].show == "test_show"

    def test_get_scene_by_index(self, mock_cache_manager, sample_scenes):
        """Test getting scene by index."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)
        model.scenes = sample_scenes

        # Valid index
        scene = model.get_scene_by_index(1)
        assert scene == sample_scenes[1]

        # Invalid indices
        assert model.get_scene_by_index(-1) is None
        assert model.get_scene_by_index(len(sample_scenes)) is None

    def test_find_scene_by_display_name(self, mock_cache_manager, sample_scenes):
        """Test finding scene by display name."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)
        model.scenes = sample_scenes

        # Find existing scene
        scene = model.find_scene_by_display_name("seq01_shot02 - user2")
        assert scene is not None
        assert scene.sequence == "seq01"
        assert scene.shot == "shot02"
        assert scene.user == "user2"

        # Non-existent scene
        assert model.find_scene_by_display_name("nonexistent") is None

    def test_to_dict_conversion(self, mock_cache_manager, sample_scenes):
        """Test converting all scenes to dictionary format."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)
        model.scenes = sample_scenes

        data = model.to_dict()

        assert isinstance(data, list)
        assert len(data) == len(sample_scenes)
        for i, scene_dict in enumerate(data):
            assert scene_dict["show"] == sample_scenes[i].show
            assert scene_dict["sequence"] == sample_scenes[i].sequence
            assert scene_dict["shot"] == sample_scenes[i].shot

    def test_deduplicate_scenes_by_shot(self, mock_cache_manager, duplicate_scenes):
        """Test scene deduplication keeps only one scene per shot."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        # Mock file modification times for priority testing
        def mock_stat(self):
            mock_result = Mock()
            if "new.3de" in str(self):
                mock_result.st_mtime = 2000.0
            elif "old.3de" in str(self):
                mock_result.st_mtime = 1000.0
            else:
                mock_result.st_mtime = 1500.0
            return mock_result

        with patch.object(Path, "stat", mock_stat):
            deduplicated = model._deduplicate_scenes_by_shot(duplicate_scenes)

        # Should have 2 scenes (one per unique shot)
        assert len(deduplicated) == 2

        # Check that newer file was selected for seq01_shot01
        seq01_shot01_scenes = [
            s for s in deduplicated if s.sequence == "seq01" and s.shot == "shot01"
        ]
        assert len(seq01_shot01_scenes) == 1
        assert "new.3de" in str(seq01_shot01_scenes[0].scene_path)

    def test_select_best_scene_priority(self, mock_cache_manager):
        """Test scene selection based on priority (mtime, plate type)."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        scenes = [
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test",
                user="user1",
                plate="EL01",
                scene_path=Path("/test/el.3de"),
            ),
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test",
                user="user2",
                plate="FG01",
                scene_path=Path("/test/fg.3de"),
            ),
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test",
                user="user3",
                plate="BG01",
                scene_path=Path("/test/bg.3de"),
            ),
        ]

        with patch.object(Path, "stat") as mock_stat:
            # All have same mtime
            mock_stat.return_value.st_mtime = 1000.0

            best = model._select_best_scene(scenes)

            # FG01 should win due to plate priority
            assert best.plate == "FG01"

    def test_select_best_scene_mtime_wins(self, mock_cache_manager):
        """Test that newer mtime overrides plate priority."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        scenes = [
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test",
                user="user1",
                plate="FG01",
                scene_path=Path("/test/older_fg.3de"),
            ),
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test",
                user="user2",
                plate="EL01",
                scene_path=Path("/test/newer_el.3de"),
            ),
        ]

        def mock_stat(self):
            mock_result = Mock()
            if "newer" in str(self):
                mock_result.st_mtime = 2000.0
            else:
                mock_result.st_mtime = 1000.0
            return mock_result

        with patch.object(Path, "stat", mock_stat):
            best = model._select_best_scene(scenes)

            # Newer EL01 should win over older FG01
            assert best.plate == "EL01"

    def test_refresh_scenes_success(
        self, mock_cache_manager, sample_shots, sample_scenes,
    ):
        """Test successful scene refresh with changes."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        # Mock the scene finder
        with patch("threede_scene_finder.ThreeDESceneFinder") as MockFinder:
            MockFinder.find_all_scenes_in_shows_efficient.return_value = sample_scenes

            success, has_changes = model.refresh_scenes(sample_shots)

            assert success is True
            assert has_changes is True
            assert len(model.scenes) == len(sample_scenes)

            # Verify cache was updated
            MockFinder.find_all_scenes_in_shows_efficient.assert_called_once_with(
                sample_shots, model._excluded_users,
            )

    def test_refresh_scenes_no_changes(
        self, mock_cache_manager, sample_shots, sample_scenes,
    ):
        """Test scene refresh when no changes detected."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)
        model.scenes = sample_scenes  # Pre-populate

        with patch("threede_scene_finder.ThreeDESceneFinder") as MockFinder:
            # Return same scenes
            MockFinder.find_all_scenes_in_shows_efficient.return_value = sample_scenes

            success, has_changes = model.refresh_scenes(sample_shots)

            assert success is True
            assert has_changes is False
            assert len(model.scenes) == len(sample_scenes)

    def test_refresh_scenes_with_deduplication(
        self, mock_cache_manager, sample_shots, duplicate_scenes,
    ):
        """Test that refresh applies deduplication."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        with patch("threede_scene_finder.ThreeDESceneFinder") as MockFinder:
            MockFinder.find_all_scenes_in_shows_efficient.return_value = (
                duplicate_scenes
            )

            # Mock file stats for deduplication
            with patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_mtime = 1000.0

                success, has_changes = model.refresh_scenes(sample_shots)

            assert success is True
            assert has_changes is True
            # Should have deduplicated to 2 unique shots
            assert len(model.scenes) == 2

    def test_refresh_scenes_error_handling(self, mock_cache_manager, sample_shots):
        """Test refresh handles errors gracefully."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        with patch("threede_scene_finder.ThreeDESceneFinder") as MockFinder:
            MockFinder.find_all_scenes_in_shows_efficient.side_effect = Exception(
                "Test error",
            )

            success, has_changes = model.refresh_scenes(sample_shots)

            assert success is False
            assert has_changes is False
            assert model.scenes == []

    def test_refresh_scenes_always_caches(
        self, mock_cache_manager, sample_shots, sample_scenes,
    ):
        """Test that refresh always updates cache to refresh TTL."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        with patch("threede_scene_finder.ThreeDESceneFinder") as MockFinder:
            MockFinder.find_all_scenes_in_shows_efficient.return_value = sample_scenes

            # Spy on cache method
            with patch.object(
                mock_cache_manager,
                "cache_threede_scenes",
                wraps=mock_cache_manager.cache_threede_scenes,
            ) as spy:
                # First refresh
                model.refresh_scenes(sample_shots)
                assert spy.call_count == 1

                # Second refresh with no changes should still cache
                model.refresh_scenes(sample_shots)
                assert spy.call_count == 2

    def test_excluded_users_integration(self, mock_cache_manager):
        """Test that excluded users are properly set and used."""
        with patch.object(ValidationUtils, "get_excluded_users") as mock_get_excluded:
            mock_get_excluded.return_value = {"currentuser", "testuser"}

            model = ThreeDESceneModel(
                cache_manager=mock_cache_manager, load_cache=False,
            )

            assert model._excluded_users == {"currentuser", "testuser"}
            mock_get_excluded.assert_called_once()

    def test_scenes_sorting(self, mock_cache_manager, sample_shots):
        """Test that scenes are sorted after refresh."""
        model = ThreeDESceneModel(cache_manager=mock_cache_manager, load_cache=False)

        unsorted_scenes = [
            ThreeDEScene(
                show="test",
                sequence="seq02",
                shot="shot01",
                workspace_path="/test",
                user="user2",
                plate="FG01",
                scene_path=Path("/test/2.3de"),
            ),
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot01",
                workspace_path="/test",
                user="user1",
                plate="BG01",
                scene_path=Path("/test/1.3de"),
            ),
            ThreeDEScene(
                show="test",
                sequence="seq01",
                shot="shot02",
                workspace_path="/test",
                user="user1",
                plate="EL01",
                scene_path=Path("/test/3.3de"),
            ),
        ]

        with patch("threede_scene_finder.ThreeDESceneFinder") as MockFinder:
            MockFinder.find_all_scenes_in_shows_efficient.return_value = unsorted_scenes

            model.refresh_scenes(sample_shots)

            # Verify sorting by full_name then user
            assert model.scenes[0].full_name == "seq01_shot01"
            assert model.scenes[1].full_name == "seq01_shot02"
            assert model.scenes[2].full_name == "seq02_shot01"
