"""Integration example for Thread Health Monitoring in ShotBot.

This module demonstrates how to integrate the Thread Health Monitoring system
into the existing ShotBot application architecture. It shows best practices
for registration, monitoring, and health reporting.

This is an example file and should be adapted based on your specific integration needs.
"""

import logging
from typing import Optional

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

# Import the health monitoring system
from thread_health_monitor import (
    ThreadHealthMonitor,
    start_monitoring,
    register_thread_for_monitoring,
    register_worker_for_monitoring,
    get_health_status,
)

# Import existing ShotBot components
try:
    from main_window import MainWindow
    from launcher_manager import LauncherManager, LauncherWorker
    from cache_manager import CacheManager
    from process_pool_manager import ProcessPoolManager
    from threede_scene_worker import ThreeDESceneWorker
    HAS_SHOTBOT_COMPONENTS = True
except ImportError:
    HAS_SHOTBOT_COMPONENTS = False
    logging.warning("ShotBot components not available - running in demo mode")

logger = logging.getLogger(__name__)


class ShotBotWithHealthMonitoring:
    """Example integration of ShotBot with Thread Health Monitoring.
    
    This class demonstrates how to wrap the existing ShotBot application
    to include comprehensive thread health monitoring.
    """
    
    def __init__(self):
        """Initialize ShotBot with health monitoring."""
        self.health_monitor: Optional[ThreadHealthMonitor] = None
        self.main_window: Optional['MainWindow'] = None
        self.launcher_manager: Optional['LauncherManager'] = None
        self.cache_manager: Optional['CacheManager'] = None
        self.process_pool_manager: Optional['ProcessPoolManager'] = None
        
        # Health status timer
        self.health_status_timer: Optional[QTimer] = None
    
    def initialize(self) -> None:
        """Initialize the application with health monitoring."""
        logger.info("Initializing ShotBot with Thread Health Monitoring")
        
        # 1. Start health monitoring early
        self.health_monitor = start_monitoring(interval=5.0)
        
        # Enable advanced monitoring features
        self.health_monitor.enable_deadlock_detection(heartbeat_interval=3.0)
        self.health_monitor.enable_resource_leak_detection(check_interval=30.0)
        
        # Connect to health signals for logging/alerting
        self.health_monitor.health_updated.connect(self._on_health_updated)
        self.health_monitor.alert_triggered.connect(self._on_health_alert)
        
        # 2. Initialize core ShotBot components
        if HAS_SHOTBOT_COMPONENTS:
            self._initialize_shotbot_components()
        else:
            self._initialize_demo_components()
        
        # 3. Register all components for monitoring
        self._register_components_for_monitoring()
        
        # 4. Set up periodic health reporting
        self._setup_health_reporting()
        
        logger.info("ShotBot initialization complete with health monitoring active")
    
    def _initialize_shotbot_components(self) -> None:
        """Initialize actual ShotBot components."""
        try:
            # Initialize cache manager
            self.cache_manager = CacheManager()
            
            # Initialize process pool manager
            self.process_pool_manager = ProcessPoolManager()
            
            # Initialize launcher manager
            self.launcher_manager = LauncherManager()
            
            # Initialize main window
            self.main_window = MainWindow(cache_manager=self.cache_manager)
            
            logger.info("ShotBot core components initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize ShotBot components: {e}")
            raise
    
    def _initialize_demo_components(self) -> None:
        """Initialize demo components when ShotBot is not available."""
        logger.info("Initializing demo components for health monitoring demonstration")
        
        # Create some demo threads for monitoring
        demo_thread1 = QThread()
        demo_thread1.setObjectName("DemoThread1")
        demo_thread1.start()
        
        demo_thread2 = QThread()
        demo_thread2.setObjectName("DemoThread2")
        demo_thread2.start()
        
        # Store references to prevent garbage collection
        self._demo_threads = [demo_thread1, demo_thread2]
    
    def _register_components_for_monitoring(self) -> None:
        """Register all components with the health monitoring system."""
        if not self.health_monitor:
            return
        
        logger.info("Registering components for health monitoring")
        
        if HAS_SHOTBOT_COMPONENTS:
            # Register main window thread (main Qt thread)
            if self.main_window:
                main_thread = QApplication.instance().thread()
                self.health_monitor.register_qt_thread(main_thread)
            
            # Register process pool manager
            if self.process_pool_manager:
                self.health_monitor.register_process_pool(self.process_pool_manager)
            
            # Register launcher workers when they are created
            if self.launcher_manager:
                # Connect to launcher manager to monitor new workers
                self.launcher_manager.command_started.connect(self._on_launcher_worker_started)
        
        else:
            # Register demo threads
            for thread in getattr(self, '_demo_threads', []):
                self.health_monitor.register_qt_thread(thread)
    
    def _on_launcher_worker_started(self, launcher_id: str, command: str) -> None:
        """Handle when a new launcher worker starts."""
        if not self.launcher_manager or not self.health_monitor:
            return
        
        # Find the worker and register it for monitoring
        # Note: This would need to be adapted based on actual LauncherManager API
        try:
            # This is pseudocode - adapt based on actual LauncherManager implementation
            worker = self.launcher_manager.get_worker(launcher_id)
            if worker and isinstance(worker, LauncherWorker):
                self.health_monitor.register_worker(worker)
                logger.debug(f"Registered launcher worker for monitoring: {launcher_id}")
        except Exception as e:
            logger.debug(f"Could not register launcher worker for monitoring: {e}")
    
    def _setup_health_reporting(self) -> None:
        """Set up periodic health status reporting."""
        self.health_status_timer = QTimer()
        self.health_status_timer.timeout.connect(self._report_health_status)
        self.health_status_timer.start(60000)  # Report every minute
        
        logger.info("Health status reporting enabled (60s interval)")
    
    def _on_health_updated(self, health_data: dict) -> None:
        """Handle health status updates."""
        health_score = health_data.get("health_score", 100)
        status = health_data.get("status", "unknown")
        
        logger.debug(f"Health update: score={health_score}, status={status}")
        
        # Log warnings for degraded health
        if health_score < 70:
            logger.warning(f"System health degraded: score={health_score}, status={status}")
            
            # Get detailed component status
            components = health_data.get("components", {})
            for component_name, component_data in components.items():
                if component_data.get("status") != "healthy":
                    issues = component_data.get("issues", [])
                    if issues:
                        logger.warning(f"{component_name} issues: {issues}")
    
    def _on_health_alert(self, alert_data: dict) -> None:
        """Handle health alerts."""
        severity = alert_data.get("severity", "UNKNOWN")
        component = alert_data.get("component", "Unknown")
        message = alert_data.get("message", "No message")
        
        log_level = logging.ERROR if severity in ["CRITICAL", "FAILING"] else logging.WARNING
        logger.log(log_level, f"Health Alert [{severity}] {component}: {message}")
        
        # Could integrate with external alerting systems here
        # e.g., send notification to monitoring dashboard, email, Slack, etc.
    
    def _report_health_status(self) -> None:
        """Report current health status."""
        if not self.health_monitor:
            return
        
        try:
            health_score = self.health_monitor.get_health_score()
            logger.info(f"System Health Score: {health_score}/100")
            
            # Log detailed report if health is degraded
            if health_score < 80:
                report = self.health_monitor.get_health_report()
                logger.info(f"Health Report: {report}")
                
        except Exception as e:
            logger.error(f"Failed to report health status: {e}")
    
    def shutdown(self) -> None:
        """Shutdown the application and clean up monitoring."""
        logger.info("Shutting down ShotBot with health monitoring")
        
        # Stop health reporting
        if self.health_status_timer:
            self.health_status_timer.stop()
        
        # Get final health report
        if self.health_monitor:
            try:
                final_report = self.health_monitor.get_health_report()
                logger.info(f"Final health report: {final_report}")
                
                # Stop monitoring
                self.health_monitor.stop_monitoring()
            except Exception as e:
                logger.error(f"Error during health monitoring shutdown: {e}")
        
        # Clean up demo threads if running in demo mode
        if hasattr(self, '_demo_threads'):
            for thread in self._demo_threads:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(5000)  # Wait up to 5 seconds
        
        logger.info("ShotBot shutdown complete")
    
    def get_current_health_status(self) -> dict:
        """Get current health status for external monitoring.
        
        Returns:
            Dictionary containing current health information
        """
        if not self.health_monitor:
            return {"status": "monitoring_not_active", "score": 0}
        
        return get_health_status()
    
    def get_detailed_health_report(self) -> dict:
        """Get detailed health report for diagnostics.
        
        Returns:
            Detailed health report with metrics and diagnostics
        """
        if not self.health_monitor:
            return {"status": "monitoring_not_active"}
        
        return self.health_monitor.get_detailed_report()


def create_monitored_shotbot_application() -> ShotBotWithHealthMonitoring:
    """Create a ShotBot application instance with health monitoring.
    
    Returns:
        Configured ShotBotWithHealthMonitoring instance
    """
    app = ShotBotWithHealthMonitoring()
    app.initialize()
    return app


# Example usage for integration into main application
def main():
    """Example main function showing integration."""
    import sys
    
    # Create Qt application
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("ShotBot with Health Monitoring")
    
    # Create monitored ShotBot application
    shotbot_app = create_monitored_shotbot_application()
    
    try:
        # Show main window if available
        if shotbot_app.main_window:
            shotbot_app.main_window.show()
        
        # Set up graceful shutdown
        def shutdown_handler():
            shotbot_app.shutdown()
            qt_app.quit()
        
        # For demo, quit after 30 seconds
        QTimer.singleShot(30000, shutdown_handler)
        
        # Run the application
        return qt_app.exec()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        shotbot_app.shutdown()
        return 0
    except Exception as e:
        logger.error(f"Application error: {e}")
        shotbot_app.shutdown()
        return 1


if __name__ == "__main__":
    # Configure logging for the example
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    sys.exit(main())