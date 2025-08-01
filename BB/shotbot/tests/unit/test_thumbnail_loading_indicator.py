"""Unit tests for thumbnail loading indicator."""

from unittest.mock import Mock

from PySide6.QtCore import Qt
from PySide6.QtGui import QPaintEvent

from thumbnail_loading_indicator import (
    ShimmerLoadingIndicator,
    ThumbnailLoadingIndicator,
)


class TestThumbnailLoadingIndicator:
    """Test ThumbnailLoadingIndicator class."""

    def test_initialization(self, qtbot):
        """Test loading indicator initialization."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        assert indicator.isHidden()
        assert indicator.width() == 40
        assert indicator.height() == 40
        assert not indicator._timer.isActive()

    def test_start_animation(self, qtbot):
        """Test starting the loading animation."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        indicator.start()

        assert indicator.isVisible()
        assert indicator._timer.isActive()
        assert indicator._timer.interval() == 50

    def test_stop_animation(self, qtbot):
        """Test stopping the loading animation."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        # Start then stop
        indicator.start()
        indicator.stop()

        assert indicator.isHidden()
        assert not indicator._timer.isActive()

    def test_rotation(self, qtbot):
        """Test rotation updates."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        initial_angle = indicator._angle
        indicator._rotate()

        assert indicator._angle == (initial_angle + 10) % 360

    def test_multiple_rotations(self, qtbot):
        """Test angle wrapping."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        # Rotate to near 360
        indicator._angle = 355
        indicator._rotate()

        assert indicator._angle == 5  # Should wrap around

    def test_transparency_attributes(self, qtbot):
        """Test transparency attributes are set."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        assert indicator.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert indicator.testAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

    def test_paint_event(self, qtbot):
        """Test paint event renders without errors."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        # Set some angle to test rotation
        indicator._angle = 45

        # Create a mock paint event
        event = Mock(spec=QPaintEvent)
        event.rect.return_value = indicator.rect()

        # Should not raise any exceptions
        indicator.paintEvent(event)

    def test_paint_event_with_different_angles(self, qtbot):
        """Test paint event with different rotation angles."""
        indicator = ThumbnailLoadingIndicator()
        qtbot.addWidget(indicator)

        # Test multiple angles
        for angle in [0, 90, 180, 270, 359]:
            indicator._angle = angle
            event = Mock(spec=QPaintEvent)
            event.rect.return_value = indicator.rect()
            indicator.paintEvent(event)


class TestShimmerLoadingIndicator:
    """Test ShimmerLoadingIndicator class."""

    def test_initialization(self, qtbot):
        """Test shimmer indicator initialization."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)

        assert indicator._shimmer_position == 0
        assert indicator._animation.duration() == 1500
        assert indicator._animation.loopCount() == -1  # Infinite
        assert indicator.isHidden()

    def test_start_animation(self, qtbot):
        """Test starting the shimmer animation."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)
        indicator.resize(200, 100)  # Set a size

        indicator.start()

        assert indicator.isVisible()
        assert indicator._animation.state() == indicator._animation.State.Running
        assert indicator._animation.endValue() == 300  # width + 100

    def test_stop_animation(self, qtbot):
        """Test stopping the shimmer animation."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)

        # Start then stop
        indicator.start()
        indicator.stop()

        assert indicator.isHidden()
        assert indicator._animation.state() == indicator._animation.State.Stopped

    def test_shimmer_position_property(self, qtbot):
        """Test shimmer position property."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)

        # Test setter
        indicator.shimmerPosition = 50
        assert indicator._shimmer_position == 50

        # Test getter
        assert indicator.shimmerPosition == 50

    def test_transparency_attribute(self, qtbot):
        """Test transparency attribute is set."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)

        assert indicator.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def test_paint_event_no_shimmer(self, qtbot):
        """Test paint event when shimmer is outside bounds."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)
        indicator.resize(200, 50)

        # Position shimmer far outside widget
        indicator._shimmer_position = -200

        event = Mock(spec=QPaintEvent)
        event.rect.return_value = indicator.rect()

        # Should not raise any exceptions
        indicator.paintEvent(event)

    def test_paint_event_with_shimmer(self, qtbot):
        """Test paint event when shimmer is visible."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)
        indicator.resize(200, 50)

        # Position shimmer in middle of widget
        indicator._shimmer_position = 100

        event = Mock(spec=QPaintEvent)
        event.rect.return_value = indicator.rect()

        # Should not raise any exceptions
        indicator.paintEvent(event)

    def test_paint_event_shimmer_positions(self, qtbot):
        """Test paint event with different shimmer positions."""
        indicator = ShimmerLoadingIndicator()
        qtbot.addWidget(indicator)
        indicator.resize(200, 50)

        # Test various positions
        positions = [-50, 0, 50, 100, 150, 200, 250]
        for pos in positions:
            indicator._shimmer_position = pos
            event = Mock(spec=QPaintEvent)
            event.rect.return_value = indicator.rect()
            indicator.paintEvent(event)
