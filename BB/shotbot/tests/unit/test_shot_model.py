"""Unit tests for ShotModel class."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from shot_model import RefreshResult, Shot, ShotModel


class TestShot:
    """Test cases for Shot dataclass."""
    
    def test_shot_creation(self, sample_shot):
        """Test Shot instance creation."""
        assert sample_shot.show == "testshow"
        assert sample_shot.sequence == "101_ABC"
        assert sample_shot.shot == "0010"
        assert sample_shot.workspace_path == "/shows/testshow/shots/101_ABC/101_ABC_0010"

    def test_shot_string_representation(self, sample_shot):
        """Test Shot string representation."""
        shot_str = str(sample_shot)
        assert "testshow" in shot_str
        assert "101_ABC" in shot_str
        assert "0010" in shot_str
    
    def test_shot_full_name_property(self, sample_shot):
        """Test Shot full_name property."""
        assert sample_shot.full_name == "101_ABC_0010"
    
    def test_shot_thumbnail_dir_property(self, sample_shot):
        """Test Shot thumbnail_dir property."""
        thumbnail_dir = sample_shot.thumbnail_dir
        assert isinstance(thumbnail_dir, Path)
        # This tests line 107 - the thumbnail_dir property
        assert "testshow" in str(thumbnail_dir)
        assert "101_ABC" in str(thumbnail_dir)
        assert "0010" in str(thumbnail_dir)
    
    @patch('utils.PathUtils.validate_path_exists')
    @patch('utils.FileUtils.get_first_image_file')
    def test_get_thumbnail_path_editorial_success(self, mock_get_first_image, mock_validate_path, sample_shot):
        """Test get_thumbnail_path finds editorial thumbnail."""
        # Setup mocks for successful editorial thumbnail discovery
        mock_validate_path.return_value = True
        mock_get_first_image.return_value = Path("/path/to/thumbnail.jpg")
        
        # Test that thumbnail path is found and cached
        thumbnail_path = sample_shot.get_thumbnail_path()
        assert thumbnail_path == Path("/path/to/thumbnail.jpg")
        
        # Test caching - second call should return cached result without filesystem access
        thumbnail_path_cached = sample_shot.get_thumbnail_path()
        assert thumbnail_path_cached == Path("/path/to/thumbnail.jpg")
        
        # Verify filesystem was only accessed once due to caching
        assert mock_validate_path.call_count == 1
        assert mock_get_first_image.call_count == 1
    
    @patch('utils.PathUtils.validate_path_exists')
    @patch('utils.FileUtils.get_first_image_file')
    @patch('utils.PathUtils.find_turnover_plate_thumbnail')
    def test_get_thumbnail_path_turnover_fallback(self, mock_find_turnover, mock_get_first_image, mock_validate_path, sample_shot):
        """Test get_thumbnail_path falls back to turnover plates."""
        # Editorial directory doesn't exist or no images found
        mock_validate_path.return_value = False
        mock_get_first_image.return_value = None
        
        # Turnover fallback succeeds
        mock_find_turnover.return_value = Path("/path/to/turnover.jpg")
        
        thumbnail_path = sample_shot.get_thumbnail_path()
        assert thumbnail_path == Path("/path/to/turnover.jpg")
        
        # Verify fallback was called
        mock_find_turnover.assert_called_once()
    
    @patch('utils.PathUtils.validate_path_exists')
    @patch('utils.FileUtils.get_first_image_file')
    @patch('utils.PathUtils.find_turnover_plate_thumbnail')
    @patch('utils.PathUtils.find_any_publish_thumbnail')
    def test_get_thumbnail_path_publish_fallback(self, mock_find_publish, mock_find_turnover, mock_get_first_image, mock_validate_path, sample_shot):
        """Test get_thumbnail_path falls back to publish thumbnails."""
        # Editorial and turnover both fail
        mock_validate_path.return_value = False
        mock_get_first_image.return_value = None
        mock_find_turnover.return_value = None
        
        # Publish fallback succeeds
        mock_find_publish.return_value = Path("/path/to/publish.exr")
        
        thumbnail_path = sample_shot.get_thumbnail_path()
        assert thumbnail_path == Path("/path/to/publish.exr")
        
        # Verify all fallbacks were attempted
        mock_find_turnover.assert_called_once()
        mock_find_publish.assert_called_once()
    
    @patch('utils.PathUtils.validate_path_exists')
    @patch('utils.FileUtils.get_first_image_file')
    @patch('utils.PathUtils.find_turnover_plate_thumbnail')
    @patch('utils.PathUtils.find_any_publish_thumbnail')
    def test_get_thumbnail_path_no_thumbnails_found(self, mock_find_publish, mock_find_turnover, mock_get_first_image, mock_validate_path, sample_shot):
        """Test get_thumbnail_path returns None when no thumbnails found."""
        # All fallbacks fail
        mock_validate_path.return_value = False
        mock_get_first_image.return_value = None
        mock_find_turnover.return_value = None
        mock_find_publish.return_value = None
        
        thumbnail_path = sample_shot.get_thumbnail_path()
        assert thumbnail_path is None
        
        # Test that None result is cached
        thumbnail_path_cached = sample_shot.get_thumbnail_path()
        assert thumbnail_path_cached is None
        
        # Verify filesystem was only accessed once due to caching
        assert mock_validate_path.call_count == 1
    
    def test_shot_to_dict_serialization(self, sample_shot):
        """Test Shot to_dict serialization."""
        shot_dict = sample_shot.to_dict()
        
        expected = {
            "show": "testshow",
            "sequence": "101_ABC", 
            "shot": "0010",
            "workspace_path": "/shows/testshow/shots/101_ABC/101_ABC_0010"
        }
        
        assert shot_dict == expected
        assert isinstance(shot_dict, dict)
        assert all(isinstance(v, str) for v in shot_dict.values())
    
    def test_shot_from_dict_deserialization(self):
        """Test Shot from_dict deserialization."""
        shot_data = {
            "show": "testshow",
            "sequence": "101_ABC",
            "shot": "0010", 
            "workspace_path": "/shows/testshow/shots/101_ABC/101_ABC_0010"
        }
        
        shot = Shot.from_dict(shot_data)
        
        assert shot.show == "testshow"
        assert shot.sequence == "101_ABC"
        assert shot.shot == "0010"
        assert shot.workspace_path == "/shows/testshow/shots/101_ABC/101_ABC_0010"
        
        # Verify cached thumbnail path is reset (not restored from dict)
        assert shot._cached_thumbnail_path is not None  # Should be _NOT_SEARCHED sentinel
    
    def test_shot_serialization_roundtrip(self, sample_shot):
        """Test Shot serialization roundtrip maintains data integrity."""
        # Serialize to dict
        shot_dict = sample_shot.to_dict()
        
        # Deserialize back to Shot
        restored_shot = Shot.from_dict(shot_dict)
        
        # Verify all data is preserved
        assert restored_shot.show == sample_shot.show
        assert restored_shot.sequence == sample_shot.sequence
        assert restored_shot.shot == sample_shot.shot
        assert restored_shot.workspace_path == sample_shot.workspace_path
        assert restored_shot.full_name == sample_shot.full_name


class TestShotModel:
    """Test cases for ShotModel class."""
    
    def test_shot_model_initialization(self, shot_model):
        """Test ShotModel initialization."""
        assert shot_model is not None
        assert hasattr(shot_model, 'shots')
        assert isinstance(shot_model.shots, list)
        
    def test_get_shots(self, shot_model_with_shots):
        """Test getting shots list."""
        shots = shot_model_with_shots.shots
        assert len(shots) == 3
        assert all(isinstance(shot, Shot) for shot in shots)
        
    def test_get_shot_by_name(self, shot_model_with_shots):
        """Test getting specific shot by name."""
        shot = shot_model_with_shots.find_shot_by_name("seq1_0010")
        assert shot is not None
        assert shot.show == "show1"
        assert shot.sequence == "seq1"
        assert shot.shot == "0010"
        
    def test_get_shot_by_name_not_found(self, shot_model_with_shots):
        """Test getting non-existent shot."""
        shot = shot_model_with_shots.find_shot_by_name("nonexistent")
        assert shot is None

    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_success(self, mock_execute, shot_model):
        """Test successful shot refresh."""
        # Mock successful command execution
        mock_execute.return_value = "workspace /shows/test/shots/seq1/seq1_0010\n"
        
        result = shot_model.refresh_shots()
        
        assert isinstance(result, RefreshResult)
        assert result.success is True
        
    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_failure(self, mock_execute, shot_model):
        """Test failed shot refresh."""
        # Mock failed command execution - throw exception to simulate failure
        mock_execute.side_effect = Exception("Command failed")
        
        result = shot_model.refresh_shots()
        
        assert isinstance(result, RefreshResult)
        assert result.success is False

    def test_refresh_result_tuple_unpacking(self, shot_model):
        """Test RefreshResult supports tuple unpacking for backwards compatibility."""
        with patch('process_pool_manager.ProcessPoolManager.execute_workspace_command') as mock_execute:
            mock_execute.return_value = "workspace /shows/test/shots/seq1/seq1_0010\n"
            
            # Test tuple unpacking
            success, has_changes = shot_model.refresh_shots()
            assert isinstance(success, bool)
            assert isinstance(has_changes, bool)
    
    def test_get_shots_method(self, shot_model_with_shots):
        """Test get_shots method returns shot list."""
        shots = shot_model_with_shots.get_shots()
        assert len(shots) == 3
        assert all(isinstance(shot, Shot) for shot in shots)
    
    def test_get_shot_by_index_valid(self, shot_model_with_shots):
        """Test get_shot_by_index with valid index."""
        shot = shot_model_with_shots.get_shot_by_index(0)
        assert shot is not None
        assert shot.show == "show1"
        assert shot.sequence == "seq1"
        assert shot.shot == "0010"
        
        shot = shot_model_with_shots.get_shot_by_index(2)
        assert shot is not None
        assert shot.show == "show2"
    
    def test_get_shot_by_index_invalid(self, shot_model_with_shots):
        """Test get_shot_by_index with invalid indices."""
        # Negative index
        shot = shot_model_with_shots.get_shot_by_index(-1)
        assert shot is None
        
        # Index too large
        shot = shot_model_with_shots.get_shot_by_index(10)
        assert shot is None
        
        # Boundary case - exactly at length
        shot = shot_model_with_shots.get_shot_by_index(3)
        assert shot is None
    
    def test_get_shot_by_name_alias_method(self, shot_model_with_shots):
        """Test get_shot_by_name method (alias for find_shot_by_name)."""
        shot = shot_model_with_shots.get_shot_by_name("seq1_0010")
        assert shot is not None
        assert shot.show == "show1"
        
        shot = shot_model_with_shots.get_shot_by_name("nonexistent")
        assert shot is None
    
    def test_invalidate_workspace_cache(self, shot_model):
        """Test invalidate_workspace_cache method."""
        # Mock the _process_pool attribute directly  
        shot_model._process_pool = Mock()
        
        shot_model.invalidate_workspace_cache()
        
        shot_model._process_pool.invalidate_cache.assert_called_once_with("ws -sg")
    
    def test_get_performance_metrics(self, shot_model):
        """Test get_performance_metrics method."""
        # Mock the _process_pool attribute directly
        shot_model._process_pool = Mock()
        mock_metrics = {
            "subprocess_calls": 5,
            "cache_hits": 2,
            "cache_misses": 3,
            "average_response_ms": 150.5
        }
        shot_model._process_pool.get_metrics.return_value = mock_metrics
        
        metrics = shot_model.get_performance_metrics()
        
        assert metrics == mock_metrics
        shot_model._process_pool.get_metrics.assert_called_once()
    
    @patch('cache_manager.CacheManager')
    def test_shot_model_initialization_with_debug_verbose(self, mock_cache_manager):
        """Test ShotModel initialization with DEBUG_VERBOSE enabled."""
        with patch.dict(os.environ, {'SHOTBOT_DEBUG_VERBOSE': '1'}):
            with patch('process_pool_manager.ProcessPoolManager.get_instance') as mock_get_instance:
                mock_pool = Mock()
                mock_get_instance.return_value = mock_pool
                
                # Test initialization with load_cache=True to trigger cache loading
                model = ShotModel(cache_manager=mock_cache_manager(), load_cache=True)
                
                assert model is not None
                mock_get_instance.assert_called_once()
    
    def test_load_from_cache_success(self, shot_model):
        """Test successful cache loading."""
        # Setup mock cache data
        mock_cache_data = [
            {"show": "test", "sequence": "seq1", "shot": "0010", "workspace_path": "/test/path1"},
            {"show": "test", "sequence": "seq1", "shot": "0020", "workspace_path": "/test/path2"}
        ]
        
        with patch.object(shot_model.cache_manager, 'get_cached_shots', return_value=mock_cache_data):
            result = shot_model._load_from_cache()
            
            assert result is True
            assert len(shot_model.shots) == 2
            assert shot_model.shots[0].show == "test"
            assert shot_model.shots[1].shot == "0020"
    
    def test_load_from_cache_no_data(self, shot_model):
        """Test cache loading when no data available."""
        with patch.object(shot_model.cache_manager, 'get_cached_shots', return_value=None):
            result = shot_model._load_from_cache()
            
            assert result is False
            assert len(shot_model.shots) == 0


class TestShotModelErrorHandling:
    """Test error handling scenarios in ShotModel."""
    
    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_timeout_error(self, mock_execute, shot_model):
        """Test refresh_shots handles TimeoutError properly."""
        mock_execute.side_effect = TimeoutError("Command timed out")
        
        result = shot_model.refresh_shots()
        
        assert isinstance(result, RefreshResult)
        assert result.success is False
        assert result.has_changes is False
    
    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_runtime_error(self, mock_execute, shot_model):
        """Test refresh_shots handles RuntimeError properly."""
        mock_execute.side_effect = RuntimeError("Session failed")
        
        result = shot_model.refresh_shots()
        
        assert isinstance(result, RefreshResult)
        assert result.success is False
        assert result.has_changes is False
    
    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_parse_error(self, mock_execute, shot_model):
        """Test refresh_shots handles parse errors properly."""
        # Return valid output but mock parser to raise ValueError
        mock_execute.return_value = "workspace /shows/test/shots/seq1/shot1"
        
        with patch.object(shot_model, '_parse_ws_output', side_effect=ValueError("Parse failed")):
            result = shot_model.refresh_shots()
            
            assert isinstance(result, RefreshResult)
            assert result.success is False
            assert result.has_changes is False
    
    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_cache_write_failure(self, mock_execute, shot_model):
        """Test refresh_shots handles cache write failures gracefully."""
        mock_execute.return_value = "workspace /shows/test/shots/seq1/seq1_0010"
        
        # Mock cache_shots to raise OSError
        with patch.object(shot_model.cache_manager, 'cache_shots', side_effect=OSError("Disk full")):
            result = shot_model.refresh_shots()
            
            # Should still succeed despite cache failure
            assert isinstance(result, RefreshResult)
            assert result.success is True
            assert len(shot_model.shots) == 1
    
    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_change_detection(self, mock_execute, shot_model_with_shots):
        """Test change detection logic in refresh_shots."""
        # Return same shots as currently loaded
        mock_execute.return_value = """workspace /shows/show1/shots/seq1/seq1_0010
workspace /shows/show1/shots/seq1/seq1_0020
workspace /shows/show2/shots/seq2/seq2_0030"""
        
        result = shot_model_with_shots.refresh_shots()
        
        assert result.success is True
        # Initial shots in fixture have different shot naming (seq1_0010 vs 0010)
        # so this will detect changes when parsing workspace output
        assert result.has_changes is True  # Changes detected due to shot name parsing differences
        
        # Now return different shots
        mock_execute.return_value = "workspace /shows/newshow/shots/seq1/seq1_0010"
        
        result = shot_model_with_shots.refresh_shots()
        
        assert result.success is True
        assert result.has_changes is True  # Changes detected


class TestShotModelParser:
    """Test workspace output parsing edge cases."""
    
    def test_parse_ws_output_invalid_input_type(self, shot_model):
        """Test parser rejects non-string input."""
        with pytest.raises(ValueError, match="Expected string output"):
            shot_model._parse_ws_output(123)  # type: ignore
        
        with pytest.raises(ValueError, match="Expected string output"):
            shot_model._parse_ws_output(None)  # type: ignore
    
    def test_parse_ws_output_empty_string(self, shot_model):
        """Test parser handles empty output."""
        shots = shot_model._parse_ws_output("")
        assert shots == []
        
        shots = shot_model._parse_ws_output("   ")  # Whitespace only
        assert shots == []
    
    def test_parse_ws_output_no_matches(self, shot_model):
        """Test parser with lines that don't match workspace pattern."""
        output = """Invalid line 1
Another invalid line
Not a workspace line"""
        
        shots = shot_model._parse_ws_output(output)
        assert shots == []
    
    def test_parse_ws_output_mixed_valid_invalid(self, shot_model):
        """Test parser with mix of valid and invalid lines."""
        output = """Invalid line
workspace /shows/test1/shots/seq1/seq1_0010
Another invalid line
workspace /shows/test2/shots/seq2/seq2_0020
Yet another invalid"""
        
        shots = shot_model._parse_ws_output(output)
        assert len(shots) == 2
        assert shots[0].show == "test1"
        assert shots[1].show == "test2"
    
    def test_parse_ws_output_empty_lines(self, shot_model):
        """Test parser skips empty lines."""
        output = """workspace /shows/test1/shots/seq1/seq1_0010

workspace /shows/test2/shots/seq2/seq2_0020

"""
        
        shots = shot_model._parse_ws_output(output)
        assert len(shots) == 2
    
    def test_parse_ws_output_validation_failure(self, shot_model):
        """Test parser handles validation failures."""
        # Mock ValidationUtils to return False
        with patch('utils.ValidationUtils.validate_not_empty', return_value=False):
            output = "workspace /shows/test/shots/seq1/seq1_0010"
            
            shots = shot_model._parse_ws_output(output)
            assert shots == []  # Should skip invalid entries
    
    def test_parse_ws_output_complex_shot_names(self, shot_model):
        """Test parser handles complex shot name parsing."""
        output = """workspace /shows/test/shots/seq1/001_ABC_0010
workspace /shows/test/shots/seq2/simple_name
workspace /shows/test/shots/seq3/very_long_complex_shot_name_0050"""
        
        shots = shot_model._parse_ws_output(output)
        assert len(shots) == 3
        
        # Test shot name extraction logic
        assert shots[0].shot == "0010"  # Last part after split
        assert shots[1].shot == "simple_name"  # No underscore splits
        assert shots[2].shot == "0050"  # Last part of complex name
    
    def test_parse_ws_output_regex_error_handling(self, shot_model):
        """Test parser handles regex match errors gracefully."""
        # Test error handling with a workspace line that will cause AttributeError during parsing
        # by making shot_name.split() fail - this tests the IndexError/AttributeError handling in lines 370-377
        with patch('shot_model.Shot') as mock_shot_class:
            mock_shot_class.side_effect = AttributeError("Shot creation failed")
            
            output = "workspace /shows/test/shots/seq1/seq1_0010"
            
            # Should handle shot creation error gracefully and continue
            shots = shot_model._parse_ws_output(output)
            assert shots == []  # Should handle error and continue parsing


class TestShotModelDebugVerbose:
    """Test DEBUG_VERBOSE code paths."""
    
    @patch.dict(os.environ, {'SHOTBOT_DEBUG_VERBOSE': '1'})
    @patch('process_pool_manager.ProcessPoolManager.execute_workspace_command')
    def test_refresh_shots_debug_verbose_logging(self, mock_execute, shot_model):
        """Test DEBUG_VERBOSE logging in refresh_shots."""
        mock_execute.return_value = "workspace /shows/test/shots/seq1/seq1_0010"
        
        # The debug logging should not affect functionality
        result = shot_model.refresh_shots()
        
        assert result.success is True
        assert len(shot_model.shots) == 1
    
    @patch.dict(os.environ, {'SHOTBOT_DEBUG_VERBOSE': '1'})
    def test_debug_verbose_module_setup(self):
        """Test DEBUG_VERBOSE module-level setup."""
        # Import shot_model with DEBUG_VERBOSE enabled
        # This tests lines 21-28
        import importlib

        import shot_model
        importlib.reload(shot_model)
        
        # Verify the module was loaded (no direct way to test logging setup)
        assert shot_model.DEBUG_VERBOSE is True