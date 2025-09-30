"""Qt signal-slot management utilities to eliminate duplication.

This module provides utilities for managing Qt signal-slot connections,
reducing ~700 lines of duplicate signal handling code.

Usage:
    class MyWidget(QWidget):
        def __init__(self):
            self.signal_manager = SignalManager(self)

            # Connect with automatic tracking
            self.signal_manager.connect_safely(
                button.clicked, self.on_click
            )

            # Chain signals
            self.signal_manager.chain_signals(
                model.dataChanged, view.update
            )

        def cleanup(self):
            # Disconnect all tracked connections
            self.signal_manager.disconnect_all()
"""

from __future__ import annotations

# Standard library imports
import weakref
from typing import TYPE_CHECKING

# Third-party imports
from PySide6.QtCore import QObject, Qt, Signal

# Local application imports
from logging_mixin import LoggingMixin

if TYPE_CHECKING:
    # Standard library imports
    from collections.abc import Callable

    # Third-party imports
    from PySide6.QtCore import SignalInstance


class SignalManager(LoggingMixin):
    """Manages Qt signal-slot connections with automatic cleanup.

    This class provides utilities for:
    - Safe connection with automatic tracking
    - Bulk disconnection for cleanup
    - Signal chaining and forwarding
    - Connection type management
    - Debug logging of connections
    """

    def __init__(self, owner: QObject) -> None:
        """Initialize signal manager.

        Args:
            owner: The QObject that owns these connections
        """
        self.owner_ref = weakref.ref(owner)
        self._connections: list[tuple[object, object, Qt.ConnectionType | None]] = []
        self._signal_chains: list[tuple[object, object]] = []

    @property
    def owner(self) -> QObject | None:
        """Get the owner object if it still exists."""
        return self.owner_ref() if self.owner_ref else None

    def connect_safely(
        self,
        signal: Signal | SignalInstance,
        slot: Callable[..., object],
        connection_type: Qt.ConnectionType | None = None,
        track: bool = True,
    ) -> bool:
        """Connect a signal to a slot with optional tracking.

        Args:
            signal: The signal to connect
            slot: The slot to connect to
            connection_type: Optional connection type (e.g., Qt.QueuedConnection)
            track: Whether to track this connection for cleanup

        Returns:
            True if connection succeeded
        """
        try:
            # Connect based on connection type
            if connection_type is not None:
                signal.connect(slot, connection_type)  # type: ignore[attr-defined]
            else:
                signal.connect(slot)  # type: ignore[attr-defined]

            # Track the connection if requested
            if track:
                self._connections.append((signal, slot, connection_type))
                self.logger.debug(
                    f"Connected {signal} to {slot.__name__ if hasattr(slot, '__name__') else slot}"
                )

            return True

        except Exception as e:
            self.logger.error(f"Failed to connect signal: {e}")
            return False

    def disconnect_safely(
        self, signal: Signal | SignalInstance, slot: Callable[..., object]
    ) -> bool:
        """Safely disconnect a signal from a slot.

        Args:
            signal: The signal to disconnect
            slot: The slot to disconnect from

        Returns:
            True if disconnection succeeded
        """
        try:
            signal.disconnect(slot)  # type: ignore[attr-defined]

            # Remove from tracking
            self._connections = [
                (s, sl, ct)
                for s, sl, ct in self._connections
                if not (s == signal and sl == slot)
            ]

            self.logger.debug(
                f"Disconnected {signal} from {slot.__name__ if hasattr(slot, '__name__') else slot}"
            )
            return True

        except Exception as e:
            # Disconnection can fail if already disconnected, which is ok
            self.logger.debug(
                f"Disconnection failed (may already be disconnected): {e}"
            )
            return False

    def disconnect_all(self) -> int:
        """Disconnect all tracked connections.

        Returns:
            Number of connections disconnected
        """
        disconnected = 0

        # Disconnect in reverse order (LIFO)
        for signal, slot, _ in reversed(self._connections):
            try:
                signal.disconnect(slot)  # type: ignore[attr-defined]
                disconnected += 1
            except Exception as e:
                # Connection might already be gone
                self.logger.debug(f"Could not disconnect {signal}: {e}")

        # Clear the connections list
        self._connections.clear()

        # Disconnect signal chains
        for source, target in self._signal_chains:
            try:
                source.disconnect(target)  # type: ignore[attr-defined,reportUnknownMemberType]
                disconnected += 1
            except Exception:
                pass

        self._signal_chains.clear()

        if disconnected > 0:
            self.logger.debug(f"Disconnected {disconnected} connections")

        return disconnected

    def chain_signals(
        self,
        source_signal: Signal | SignalInstance,
        target_signal: Signal | SignalInstance,
        connection_type: Qt.ConnectionType | None = None,
    ) -> bool:
        """Chain one signal to another.

        When source_signal is emitted, target_signal will also be emitted.

        Args:
            source_signal: The source signal
            target_signal: The target signal to trigger
            connection_type: Optional connection type

        Returns:
            True if chaining succeeded
        """
        try:
            # For signal chaining, we connect to the emit method
            if connection_type is not None:
                source_signal.connect(target_signal.emit, connection_type)  # type: ignore[attr-defined]
            else:
                source_signal.connect(target_signal.emit)  # type: ignore[attr-defined]

            self._signal_chains.append((source_signal, target_signal))
            self.logger.debug(f"Chained {source_signal} -> {target_signal}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to chain signals: {e}")
            return False

    def connect_group(
        self,
        connections: list[tuple[Signal | SignalInstance, Callable[..., object]]],
        connection_type: Qt.ConnectionType | None = None,
    ) -> int:
        """Connect multiple signal-slot pairs at once.

        Args:
            connections: List of (signal, slot) tuples
            connection_type: Connection type for all connections

        Returns:
            Number of successful connections
        """
        connected = 0

        for signal, slot in connections:
            if self.connect_safely(signal, slot, connection_type):
                connected += 1

        self.logger.debug(f"Connected {connected} of {len(connections)} connections")
        return connected

    def block_signals(self, objects: list[QObject], blocked: bool = True) -> None:
        """Block or unblock signals for multiple objects.

        Useful for preventing signal cascades during updates.

        Args:
            objects: List of QObjects to block/unblock
            blocked: Whether to block (True) or unblock (False)
        """
        for obj in objects:
            if obj:
                obj.blockSignals(blocked)

        action = "Blocked" if blocked else "Unblocked"
        self.logger.debug(f"{action} signals for {len(objects)} objects")

    def with_blocked_signals(self, objects: list[QObject]) -> BlockedSignalsContext:
        """Context manager for temporarily blocking signals.

        Usage:
            with signal_manager.with_blocked_signals([widget1, widget2]):
                # Update widgets without triggering signals
                widget1.setValue(10)
                widget2.setText("test")

        Args:
            objects: Objects to block signals on

        Returns:
            Context manager
        """
        return BlockedSignalsContext(objects, self.logger)

    def connect_worker_signals(
        self,
        worker: QObject,
        handlers: dict[str, Callable[..., object]],
        connection_type: Qt.ConnectionType = Qt.ConnectionType.QueuedConnection,
    ) -> int:
        """Connect all signals from a worker thread.

        Common pattern for worker thread signal connections.

        Args:
            worker: The worker object
            handlers: Dict mapping signal names to handler functions
            connection_type: Connection type (default: QueuedConnection for thread safety)

        Returns:
            Number of connections made
        """
        connected = 0

        for signal_name, handler in handlers.items():
            if hasattr(worker, signal_name):
                signal = getattr(worker, signal_name)  # type: ignore[reportAny]
                if self.connect_safely(signal, handler, connection_type):  # type: ignore[reportUnknownArgumentType]
                    connected += 1
            else:
                self.logger.warning(f"Worker has no signal named {signal_name}")

        self.logger.debug(f"Connected {connected} worker signals")
        return connected

    def has_connections(self) -> bool:
        """Check if there are any tracked connections."""
        return len(self._connections) > 0 or len(self._signal_chains) > 0

    def get_connection_count(self) -> int:
        """Get the total number of tracked connections."""
        return len(self._connections) + len(self._signal_chains)

    def create_delayed_connection(
        self,
        signal: Signal | SignalInstance,
        slot: Callable[..., object],
        delay_ms: int = 100,
    ) -> bool:
        """Create a connection with a delay.

        Useful for debouncing rapid signal emissions.

        Args:
            signal: The signal to connect
            slot: The slot to call after delay
            delay_ms: Delay in milliseconds

        Returns:
            True if connection succeeded
        """
        # Third-party imports
        from PySide6.QtCore import QTimer

        def delayed_slot(*args: object, **kwargs: object) -> None:
            """Wrapper that delays the actual slot call."""
            QTimer.singleShot(delay_ms, lambda: slot(*args, **kwargs))  # type: ignore[reportUnknownMemberType]

        return self.connect_safely(signal, delayed_slot)


class BlockedSignalsContext:
    """Context manager for temporarily blocking Qt signals."""

    def __init__(self, objects: list[QObject], logger: object = None) -> None:
        """Initialize context.

        Args:
            objects: Objects to block signals on
            logger: Optional logger (any logger-like object)
        """
        self.objects = objects
        self.logger = logger
        self._previous_states: list[bool] = []

    def __enter__(self) -> BlockedSignalsContext:
        """Block signals and store previous states."""
        self._previous_states = []
        for obj in self.objects:
            if obj:
                self._previous_states.append(obj.signalsBlocked())
                obj.blockSignals(True)

        if self.logger and hasattr(self.logger, "debug"):
            self.logger.debug(f"Blocked signals for {len(self.objects)} objects")  # type: ignore[reportUnknownMemberType,reportAttributeAccessIssue]

        return self

    def __exit__(self, *args: object) -> None:
        """Restore previous signal states."""
        for obj, was_blocked in zip(self.objects, self._previous_states):
            if obj:
                obj.blockSignals(was_blocked)

        if self.logger and hasattr(self.logger, "debug"):
            self.logger.debug(f"Restored signal states for {len(self.objects)} objects")  # type: ignore[reportUnknownMemberType,reportAttributeAccessIssue]


class SignalThrottler(QObject):
    """Throttle rapid signal emissions to reduce UI updates.

    Useful for signals that fire rapidly (e.g., slider movements)
    but where you only need periodic updates.
    """

    # Emitted with the last received arguments
    throttled = Signal(object)

    def __init__(
        self,
        source_signal: Signal | SignalInstance,
        interval_ms: int = 100,
        parent: QObject | None = None,
    ) -> None:
        """Initialize throttler.

        Args:
            source_signal: The signal to throttle
            interval_ms: Minimum interval between emissions
            parent: Optional parent QObject
        """
        super().__init__(parent)
        # Third-party imports
        from PySide6.QtCore import QTimer

        self.source_signal = source_signal
        self.interval_ms = interval_ms
        self._pending_args: tuple[object, ...] | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_throttled)

        # Connect source signal
        source_signal.connect(self._on_source_signal)  # type: ignore[attr-defined]

    def _on_source_signal(self, *args: object) -> None:
        """Handle source signal emission."""
        self._pending_args = args

        if not self._timer.isActive():
            self._timer.start(self.interval_ms)

    def _emit_throttled(self) -> None:
        """Emit the throttled signal with stored arguments."""
        if self._pending_args is not None:
            self.throttled.emit(self._pending_args)
            self._pending_args = None

    def stop(self) -> None:
        """Stop throttling and disconnect."""
        self._timer.stop()
        try:
            self.source_signal.disconnect(self._on_source_signal)  # type: ignore[attr-defined]
        except Exception:
            pass


class SignalDebugger(LoggingMixin):
    """Debug utility for tracing signal emissions.

    Useful for debugging complex signal flows.
    """

    def __init__(self, enabled: bool = True) -> None:
        """Initialize debugger.

        Args:
            enabled: Whether debugging is enabled
        """
        self.enabled = enabled
        self._signal_counts: dict[str, int] = {}

    def trace_signal(
        self,
        signal: Signal | SignalInstance,
        signal_name: str = "unknown",
    ) -> None:
        """Trace a signal's emissions.

        Args:
            signal: The signal to trace
            signal_name: Name for logging
        """
        if not self.enabled:
            return

        def trace_handler(*args: object) -> None:
            """Log signal emission."""
            self._signal_counts[signal_name] = (
                self._signal_counts.get(signal_name, 0) + 1
            )
            count = self._signal_counts[signal_name]

            args_str = ", ".join(str(arg) for arg in args) if args else "no args"
            self.logger.debug(f"Signal {signal_name}[{count}]: {args_str}")

        signal.connect(trace_handler)  # type: ignore[attr-defined]

    def get_stats(self) -> dict[str, int]:
        """Get signal emission statistics."""
        return self._signal_counts.copy()

    def reset_stats(self) -> None:
        """Reset signal statistics."""
        self._signal_counts.clear()
