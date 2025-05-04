#!/usr/bin/env python3
"""
TS Converter GUI (Sequential Processing)
A PySide6 application to batch-convert .ts files to MP4 (H.264) or Apple ProRes MOV using FFmpeg.
Now with optional hardware‐accelerated decode + encode for NVENC, QSV, and VAAPI.
Includes options to delete source after success, and per-file progress in the list.
"""

import os
import sys
import shutil
import re
import subprocess
import time

from PySide6.QtCore import (
    Qt,
    QProcess,
    QFileInfo,
    QSettings,
    QByteArray,
    QThreadPool,
    QRunnable,
    Signal,
    QObject,
    QTimer
)
from PySide6.QtGui import (
    QAction,
    QIcon,
    QCursor,
    QColor
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QLabel,
    QComboBox,
    QSpinBox,
    QProgressBar,
    QPlainTextEdit,
    QMessageBox,
    QAbstractItemView,
    QSplitter,
    QGroupBox,
    QToolBar,
    QStatusBar,
    QMenu,
    QCheckBox,
    QTabWidget,
    QScrollArea,
    QFrame
)


class FileListWidget(QListWidget):
    """Drag & drop .ts files, reorder, context menu, and track per-file items."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.path_items: dict[str, QListWidgetItem] = {}

    def add_path(self, path: str):
        if path in self.path_items:
            return
        fname = QFileInfo(path).fileName()
        item = QListWidgetItem(fname)
        item.setData(Qt.UserRole, path)
        self.addItem(item)
        self.path_items[path] = item

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path.lower().endswith('.ts') and os.path.isfile(path):
                    self.add_path(path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        open_action = menu.addAction("Open Containing Folder")
        remove_action = menu.addAction("Remove Selected")
        chosen = menu.exec(QCursor.pos())
        if chosen == open_action:
            for item in self.selectedItems():
                folder = os.path.dirname(item.data(Qt.UserRole))
                if os.path.isdir(folder):
                    os.startfile(folder)
        elif chosen == remove_action:
            for item in self.selectedItems():
                path = item.data(Qt.UserRole)
                row = self.row(item)
                self.takeItem(row)
                self.path_items.pop(path, None)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            folder = os.path.dirname(item.data(Qt.UserRole))
            if os.path.isdir(folder):
                os.startfile(folder)
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    """Main application window with sequential processing, delete toggle, hardware‐decode toggle, and per-file progress."""
    time_re = re.compile(r'time=(\d{2}):(\d{2}):(\d{2}\.\d{2})')
    fps_re = re.compile(r'fps=\s*(\d+)')
    frame_re = re.compile(r'frame=\s*(\d+)')

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TS Converter GUI - RTX Optimized")
        self.resize(1000, 700)

        self.settings = QSettings("MyCompany", "TsConverterGuiSeq")
        self._check_ffmpeg()

        # QoL state
        self.last_dir = self.settings.value("lastDir", os.getcwd())
        self.process_duration: float | None = None
        self.start_time: float | None = None
        self.current_path: str | None = None
        self.processes = []  # Track running processes
        self.parallel_enabled = False
        self.process_progress = {}  # Track progress per process
        
        # Track UI elements for process monitoring
        self.process_widgets = {}
        self.process_logs = {}
        
        # Performance optimizations
        self.ui_update_timer = QTimer()
        self.ui_update_timer.setInterval(500)  # Update UI every 500ms instead of on every ffmpeg output
        self.ui_update_timer.timeout.connect(self._update_ui)
        self.pending_process_outputs = {}
        
        # Track file exists errors
        self.overwrite_mode = True  # Default to overwrite files
        self.queue: list[str] = []
        self.batch_start_time: float | None = None
        self.total = 0
        self.completed = 0
        
        # Auto-balance tracking
        self.auto_balance_enabled = False
        self.file_codec_assignments = {}  # Maps file paths to codec indices

        self._init_ui()
        self._restore_state()

    def _check_ffmpeg(self):
        if not shutil.which("ffmpeg"):
            QMessageBox.critical(
                None,
                "FFmpeg Not Found",
                "FFmpeg executable not found in PATH. Please install or add to PATH."
            )
            sys.exit(1)

    def _init_ui(self):
        # Detect system capabilities
        self.is_high_end_system = os.cpu_count() >= 16  # Consider 16+ cores as high-end
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        add_files_action = QAction(QIcon.fromTheme("document-open"), "Add Files", self)
        add_files_action.setShortcut("Ctrl+O")
        add_files_action.triggered.connect(self.add_files)
        exit_action = QAction(QIcon.fromTheme("application-exit"), "E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(add_files_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        tools_menu = menubar.addMenu("&Tools")
        clear_log_action = QAction(QIcon.fromTheme("edit-clear"), "Clear Log", self)
        clear_log_action.setShortcut("Ctrl+L")
        clear_log_action.triggered.connect(lambda: self.log.clear())
        tools_menu.addAction(clear_log_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        toolbar.addAction(add_files_action)
        toolbar.addAction(clear_log_action)
        toolbar.addAction(exit_action)
        self.addToolBar(toolbar)

        central = QWidget()
        main_layout = QVBoxLayout(central)

        # File list with per-file progress
        self.file_list = FileListWidget()
        self.file_list.setStyleSheet("QListView::item:hover{background:#363b46;}")

        settings_group = QGroupBox("Conversion Settings")
        settings_layout = QHBoxLayout()

        # Codec selector
        self.format_cb = QComboBox()
        self.format_cb.addItems([
            "H.264 NVENC",          # 0
            "HEVC NVENC",           # 1
            "AV1 NVENC",            # 2
            "x264 CPU",             # 3
            "ProRes CPU",           # 4
            "H.264 QSV",            # 5
            "H.264 VAAPI"           # 6
        ])
        # Set H.264 NVENC as default for RTX GPU
        self.format_cb.setCurrentIndex(0)
        
        # Add performance preset selector
        preset_label = QLabel("Preset:")
        settings_layout.addWidget(preset_label)
        self.preset_cb = QComboBox()
        self.preset_cb.addItems(["Standard", "High Quality", "Fast", "Ultra Fast"])
        self.preset_cb.setCurrentIndex(2)  # Default to Fast for high-end system
        self.preset_cb.setToolTip("Performance preset affects encoding speed vs. quality")
        settings_layout.addWidget(self.preset_cb)
        
        crf_label = QLabel("CRF:")
        self.crf_sb = QSpinBox()
        self.crf_sb.setRange(0, 51)
        self.crf_sb.setValue(int(self.settings.value("crf", 18)))
        self.crf_sb.setAccelerated(True)

        # Threads selector
        thread_label = QLabel("Threads:")
        self.threads_sb = QSpinBox()
        max_threads = os.cpu_count() or 4
        self.threads_sb.setRange(1, max_threads)
        # For high-end CPUs, using all threads may not be optimal for all workloads
        # Use 24 threads as default for CPU encoding on high-end systems
        optimal_threads = min(24, max_threads)
        self.threads_sb.setValue(optimal_threads)
        self.threads_sb.setAccelerated(True)

        # Parallel processing option
        self.parallel_cb = QCheckBox("Parallel Processing")
        self.parallel_cb.setToolTip("Enable parallel conversion of multiple files")
        # Enable parallel processing by default for high-end systems
        self.parallel_cb.setChecked(True)

        # Max parallel processes selector
        parallel_label = QLabel("Max Parallel:")
        self.parallel_sb = QSpinBox()
        # For RTX 4090 mobile, increase the parallel limit to 8
        self.parallel_sb.setRange(1, 8)
        self.parallel_sb.setValue(4)  # Good balance: 2 sessions per NVENC engine
        self.parallel_sb.setAccelerated(True)
        self.parallel_sb.setToolTip("Maximum number of parallel conversions")

        # Delete source toggle
        self.delete_cb = QCheckBox("Delete source file after successful conversion")
        delete_default = self.settings.value("delete", False, type=bool)
        self.delete_cb.setChecked(delete_default)
        self.delete_cb.stateChanged.connect(
            lambda state: self.settings.setValue("delete", bool(state))
        )

        # Hardware decode toggle
        self.hwdecode_cb = QCheckBox("Use hardware decoding")
        hw_def = self.settings.value("hwdecode", True, type=bool)
        self.hwdecode_cb.setChecked(hw_def)
        self.hwdecode_cb.stateChanged.connect(
            lambda s: self.settings.setValue("hwdecode", bool(s))
        )
        
        # Overwrite existing files toggle
        self.overwrite_cb = QCheckBox("Overwrite existing files")
        overwrite_def = self.settings.value("overwrite", True, type=bool)
        self.overwrite_cb.setChecked(overwrite_def)
        self.overwrite_cb.stateChanged.connect(
            lambda s: self.settings.setValue("overwrite", bool(s))
        )
        
        # Add a smart buffer toggle for performance
        self.smart_buffer_cb = QCheckBox("Smart Buffer Mode")
        self.smart_buffer_cb.setChecked(True)
        self.smart_buffer_cb.setToolTip("Optimize memory usage and CPU overhead during conversion")
        
        # Add auto-balance toggle for hybrid encoding
        self.auto_balance_cb = QCheckBox("Auto-Balance (CPU+GPU)")
        self.auto_balance_cb.setChecked(True)
        self.auto_balance_cb.setToolTip("Automatically distribute files between GPU and CPU encoders for maximum throughput")

        # Show/hide CRF based on codec
        self.format_cb.currentIndexChanged.connect(
            lambda idx: crf_label.setVisible(idx == 0) or self.crf_sb.setVisible(idx == 0)
        )
        crf_label.setVisible(self.format_cb.currentIndex() == 0)
        self.crf_sb.setVisible(self.format_cb.currentIndex() == 0)

        # Lay out settings widgets
        for w in (
            QLabel("Codec:"), self.format_cb, preset_label, self.preset_cb, crf_label, self.crf_sb,
            thread_label, self.threads_sb, self.parallel_cb, parallel_label, self.parallel_sb,
            self.delete_cb, self.hwdecode_cb, self.overwrite_cb, self.smart_buffer_cb, self.auto_balance_cb
        ):
            settings_layout.addWidget(w)
        settings_group.setLayout(settings_layout)

        # Control buttons
        controls_layout = QHBoxLayout()
        add_btn = QPushButton("Add Files");      add_btn.clicked.connect(self.add_files)
        remove_btn = QPushButton("Remove Selected"); remove_btn.clicked.connect(self.remove_selected)
        clear_list_btn = QPushButton("Clear List");   clear_list_btn.clicked.connect(self.clear_list)
        start_btn = QPushButton("Start")
        stop_btn = QPushButton("Stop");          stop_btn.setEnabled(False)
        start_btn.clicked.connect(lambda: self.start_conversion(start_btn, stop_btn))
        stop_btn.clicked.connect(lambda: self.stop_conversion(start_btn, stop_btn))
        clear_log_btn = QPushButton("Clear Log");     clear_log_btn.clicked.connect(lambda: self.log.clear())

        for btn in (add_btn, remove_btn, clear_list_btn):
            controls_layout.addWidget(btn)
        controls_layout.addStretch()
        for btn in (start_btn, stop_btn, clear_log_btn):
            controls_layout.addWidget(btn)

        # Splitter for list + progress/log
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.file_list)

        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # Overall progress section
        progress_group = QGroupBox("Overall Progress")
        progress_layout = QVBoxLayout(progress_group)
        self.total_progress = QProgressBar()  
        self.total_progress.setFormat("Total: %p%")
        progress_layout.addWidget(self.total_progress)
        bottom_layout.addWidget(progress_group)
        
        # Individual processes section
        self.processes_tab = QTabWidget()
        self.processes_tab.setTabsClosable(False)
        
        # Main log tab
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.processes_tab.addTab(self.log, "Main Log")
        
        # Create progress monitoring area
        self.progress_area = QScrollArea()
        self.progress_area.setWidgetResizable(True)
        self.process_containers = QWidget()
        self.process_containers.setLayout(QVBoxLayout())
        self.process_containers.layout().setAlignment(Qt.AlignTop)
        self.process_containers.layout().setSpacing(10)
        self.process_containers.layout().setContentsMargins(10, 10, 10, 10)
        self.progress_area.setWidget(self.process_containers)
        self.progress_area.setStyleSheet("QProgressBar { text-align: center; }")
        self.processes_tab.addTab(self.progress_area, "Individual Processes")
        
        bottom_layout.addWidget(self.processes_tab)
        
        # Add to splitter
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        main_layout.addWidget(settings_group)
        main_layout.addLayout(controls_layout)
        main_layout.addWidget(splitter)
        self.setCentralWidget(central)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.current_file_label = QLabel()
        self.eta_label = QLabel()
        status_bar.addWidget(self.current_file_label)
        status_bar.addPermanentWidget(self.eta_label)

    def _restore_state(self):
        geom = self.settings.value("geometry")
        splitter_state = self.settings.value("splitterState")
        if isinstance(geom, QByteArray):
            self.restoreGeometry(geom)
        if isinstance(splitter_state, QByteArray):
            self.splitter.restoreState(splitter_state)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select .ts files", self.last_dir, "TS Files (*.ts)"
        )
        if files:
            self.last_dir = os.path.dirname(files[0])
            self.settings.setValue("lastDir", self.last_dir)
        for f in files:
            self.file_list.add_path(f)

    def remove_selected(self):
        for item in list(self.file_list.selectedItems()):
            path = item.data(Qt.UserRole)
            self.file_list.takeItem(self.file_list.row(item))
            self.file_list.path_items.pop(path, None)

    def clear_list(self):
        self.file_list.clear()
        self.file_list.path_items.clear()

    def _create_process_widget(self, process, path):
        """Create UI elements for monitoring an individual process"""
        container = QFrame()
        container.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        container.setLineWidth(1)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # Add file name and progress as a label
        name = QFileInfo(path).fileName()
        label = QLabel(f"<b>{name}</b>")
        label.setTextFormat(Qt.RichText)
        
        # Add codec type indicator
        codec_idx = self.format_cb.currentIndex() if path not in self.file_codec_assignments else self.file_codec_assignments[path]
        codec_name = self.format_cb.itemText(codec_idx)
        codec_badge = "🎮" if codec_idx in [0, 1, 2] else "🖥️" # GPU/CPU icon
        codec_label = QLabel(f"{codec_badge} <b>{codec_name}</b>")
        codec_label.setTextFormat(Qt.RichText)
        
        # Add progress bar
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(True)
        
        # Add ETA/Status display
        eta_label = QLabel("Starting...")
        eta_label.setStyleSheet("color: #666; font-size: 9pt;")
        
        # Add compact log display
        log = QPlainTextEdit()
        log.setReadOnly(True)
        log.setMaximumBlockCount(500)  # Limit memory usage
        log.setFixedHeight(120)  # Made slightly smaller to fit eta_label
        log.setStyleSheet("font-family: 'Consolas', monospace; font-size: 9pt;")
        
        # Add everything to layout
        layout.addWidget(label)
        layout.addWidget(codec_label)
        layout.addWidget(progress)
        layout.addWidget(eta_label)
        layout.addWidget(log)
        
        # Add to process monitoring tab area
        self.process_containers.layout().addWidget(container)
        
        # Store references to created widgets
        self.process_widgets[process] = {
            "container": container,
            "label": label,
            "codec_label": codec_label,
            "progress": progress,
            "eta_label": eta_label,
            "log": log,
            "path": path
        }
        
        # Also create/store a reference to a dedicated log in the tab widget
        process_log = QPlainTextEdit()
        process_log.setReadOnly(True)
        process_log.setMaximumBlockCount(1000)  # Limit memory usage
        name = QFileInfo(path).fileName()
        tab_idx = self.processes_tab.addTab(process_log, name)
        self.process_logs[process] = {
            "log": process_log,
            "tab_idx": tab_idx
        }

    def _remove_process_widget(self, process):
        """Remove UI elements for a completed process"""
        if process in self.process_widgets:
            # Get widgets
            widgets = self.process_widgets[process]
            
            # Remove from layout and delete
            self.process_containers.layout().removeWidget(widgets["container"])
            widgets["container"].deleteLater()
            
            # Clear references
            del self.process_widgets[process]
            
        if process in self.process_logs:
            # Remove tab
            tab_idx = self.process_logs[process]["tab_idx"]
            self.processes_tab.removeTab(tab_idx)
            del self.process_logs[process]
    
    def _auto_balance_workload(self):
        """Distribute encoding tasks between GPU and CPU for optimal performance"""
        # Reset assignments
        self.file_codec_assignments = {}
        
        # Get available files
        files = [item.data(Qt.UserRole) for item in self.file_list.findItems("*", Qt.MatchWildcard)]
        if not files:
            return
        
        # System info
        cpu_cores = os.cpu_count()
        gpu_slots = min(6, len(files))  # RTX 4090 can handle up to 6 encodes (3 per NVENC block)
        
        # Determine optimal distribution (70% GPU, 30% CPU as a starting point)
        gpu_count = min(int(len(files) * 0.7), gpu_slots)
        cpu_count = len(files) - gpu_count
        
        # Distribution counters
        h264_nvenc_count = min(4, gpu_count)            # H.264 NVENC (most compatible)
        hevc_nvenc_count = max(0, min(2, gpu_count - h264_nvenc_count))  # HEVC NVENC (some for higher quality)
        av1_nvenc_count = 0                             # AV1 NVENC (disabled by default)
        cpu_x264_count = cpu_count                      # CPU x264
        
        # Analyze files to make smart assignments
        assigns = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
        for i, file_path in enumerate(files):
            try:
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # Size in MB
                file_duration = self._probe_duration(file_path) or 0
                
                # Smart codec selection - prioritize files based on characteristics
                if assigns[0] < h264_nvenc_count:  # First fill H.264 NVENC slots
                    codec = 0  # H.264 NVENC
                    assigns[0] += 1
                elif assigns[1] < hevc_nvenc_count:  # Then fill HEVC NVENC slots for longer content
                    codec = 1  # HEVC NVENC
                    assigns[1] += 1
                elif assigns[2] < av1_nvenc_count:  # Fill AV1 slots if enabled
                    codec = 2  # AV1 NVENC
                    assigns[2] += 1
                else:  # Remaining files to CPU
                    codec = 3  # x264 CPU
                    assigns[3] += 1
                
                self.file_codec_assignments[file_path] = codec
            except Exception:
                # Default to H.264 NVENC if analysis fails
                self.file_codec_assignments[file_path] = 0
                assigns[0] += 1
        
        # Log the distribution
        self.log.appendPlainText(f"Auto-balance distribution:")
        self.log.appendPlainText(f"  - H.264 NVENC: {assigns[0]} files")
        self.log.appendPlainText(f"  - HEVC NVENC:  {assigns[1]} files")
        self.log.appendPlainText(f"  - AV1 NVENC:   {assigns[2]} files")
        self.log.appendPlainText(f"  - x264 CPU:    {assigns[3]} files")
        self.log.appendPlainText(f"  - Total:       {sum(assigns.values())} files")
    
    def start_conversion(self, start_btn, stop_btn):
        if not self.file_list.path_items:
            QMessageBox.warning(self, "No Files", "Add at least one .ts file to convert.")
            return

        self.settings.setValue("crf", self.crf_sb.value())
        self.queue = [item.data(Qt.UserRole) for item in self.file_list.findItems("*", Qt.MatchWildcard)]
        self.total = len(self.queue)
        self.completed = 0
        self.batch_start_time = time.time()
        self.parallel_enabled = self.parallel_cb.isChecked()
        self.auto_balance_enabled = self.auto_balance_cb.isChecked() and self.parallel_enabled
        self.process_progress = {}  # Reset process tracking
        self.pending_process_outputs = {}
        self.overwrite_mode = self.overwrite_cb.isChecked()
        
        # If auto-balance is enabled, distribute work between GPU and CPU
        if self.auto_balance_enabled:
            self._auto_balance_workload()
        
        # Clear any existing process widgets
        for process in list(self.process_widgets.keys()):
            self._remove_process_widget(process)
            
        # Clear main log
        self.log.clear()
        
        # reset per-file labels
        for path, item in self.file_list.path_items.items():
            fname = QFileInfo(path).fileName()
            item.setText(fname)

        self.total_progress.setValue(0)
        self.log.clear()
        self.eta_label.clear()

        start_btn.setEnabled(False)
        stop_btn.setEnabled(True)
        
        # Store initial queue length for parallel processing
        self.initial_queue_length = len(self.queue)
        
        # Start parallel or sequential processing
        if self.parallel_enabled:
            # Use dedicated parallel_sb setting instead of thread count
            max_parallel = min(self.parallel_sb.value(), len(self.queue))
            self.log.appendPlainText(f"Starting parallel conversion with {max_parallel} workers")
            
            # For GPU encoders, adjust thread count per process to be more conservative
            codec_idx = self.format_cb.currentIndex()
            if codec_idx >= 2:  # GPU encoders (NVENC, QSV, VAAPI)
                self.log.appendPlainText("Using GPU acceleration - optimizing thread allocation")
            
            for _ in range(max_parallel):
                self._process_next(start_btn, stop_btn)
        else:
            self._process_next(start_btn, stop_btn)

    def _optimize_threads_for_codec(self, codec_idx=None):
        """Optimize thread count based on selected codec and parallel processing mode"""
        codec_idx = self.format_cb.currentIndex() if codec_idx is None else codec_idx
        
        # NVENC encoders - minimal CPU usage
        if codec_idx in (0, 1, 2):  # Any NVENC encoder
            return 2
            
        # Single x264 job - let x264 auto-detect (uses all threads)
        if not self.parallel_enabled:
            return 0  # 0 = "let x264 auto-detect" (uses all 32 HT threads)
            
        # Parallel CPU jobs - divide cleanly
        cpu_jobs = max(1, sum(1 for c in self.file_codec_assignments.values() if c == 3))
        return max(2, os.cpu_count() // cpu_jobs)

    def _process_next(self, start_btn, stop_btn):
        if not self.queue:
            # Only finish if all processes are done in parallel mode
            if not self.parallel_enabled or not self.processes:
                self._finish(start_btn, stop_btn)
            return

        path = self.queue.pop(0)
        self.current_path = path
        filename = QFileInfo(path).fileName()
        
        # Only update the label for the first file in sequential mode
        if not self.parallel_enabled or not self.processes:
            self.current_file_label.setText(f"Processing: {filename}")

        base = QFileInfo(path).completeBaseName()
        folder = os.path.dirname(path)
        
        # Check if this file has a specific codec assignment from auto-balance
        if self.auto_balance_enabled and path in self.file_codec_assignments:
            codec_idx = self.file_codec_assignments[path]
        else:
            codec_idx = self.format_cb.currentIndex()
            
        threads = self.threads_sb.value()
        crf = self.crf_sb.value()

        # Map codec index to encoder args and extension
        enc_args = {
            0: (['-c:v', 'h264_nvenc'],  '.mp4'),  # H.264 NVENC
            1: (['-c:v', 'hevc_nvenc'],  '.mp4'),  # HEVC NVENC
            2: (['-c:v', 'av1_nvenc'],   '.mkv'),  # AV1 NVENC (MKV for better compatibility)
            3: (['-c:v', 'libx264'],     '.mp4'),  # x264 CPU
            4: (['-c:v', 'prores_ks', '-profile:v', '3'], '.mov'),  # ProRes CPU
            5: (['-c:v', 'h264_qsv'],    '.mp4'),  # QSV
            6: (['-c:v', 'h264_vaapi'],  '.mp4'),  # VAAPI
        }[codec_idx]
        video_args, ext = enc_args

        output = os.path.join(folder, f"{base}_RC{ext}")

        # build ffmpeg command
        cmd = ["ffmpeg", "-y"]  # Add -y flag to force overwrite without prompting
        # Optimize thread count based on encoding type and parallel mode
        optimal_threads = self._optimize_threads_for_codec(codec_idx)
        
        # threads only for CPU x264 (now index 1)
        if codec_idx == 1:
            cmd += ["-threads", str(optimal_threads)]
        # optional hardware decode
        if self.hwdecode_cb.isChecked():
            if codec_idx == 0:       # NVENC
                cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
            elif codec_idx == 3:     # QSV
                cmd += ["-init_hw_device", "qsv=hw",
                        "-filter_hw_device", "hw",
                        "-hwaccel", "qsv"]
            elif codec_idx == 4:     # VAAPI
                cmd += ["-hwaccel", "vaapi",
                        "-vaapi_device", "/dev/dri/renderD128"]
        # input + encoder + output
        cmd += ["-i", path] + video_args
        
        # Check for existing audio - try to pass through when possible
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_name", "-select_streams", "a:0",
                "-of", "default=nokey=1:noprint_wrappers=1", path],
                text=True, capture_output=True)
            audio_codec = probe.stdout.strip()
            
            # Copy AC-3/AAC audio to skip needless re-encode
            if audio_codec in ("aac", "ac3", "eac3"):
                cmd += ["-c:a", "copy"]
                self.log.appendPlainText(f"Detected {audio_codec} audio - using passthrough")
            else:
                # Handle ProRes special case, otherwise AAC
                if codec_idx == 4:  # ProRes
                    cmd += ["-c:a", "pcm_s16le"]
                else:
                    cmd += ["-c:a", "aac", "-b:a", "192k"]
        except Exception as e:
            # Fallback to default encoding on error
            if codec_idx == 4:  # ProRes
                cmd += ["-c:a", "pcm_s16le"]
            else:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
        # Add advanced NVENC optimization flags for RTX 4090
        if codec_idx in (0, 1, 2):  # Any NVENC encoder (H.264, HEVC, AV1)
            # Quality/speed optimization for Ada/RTX 4090
            nvenc_common = [
                "-rc",           "vbr",        # constant quality with safety cap
                "-cq",           str(crf),     # CRF-like target
                "-b:v",          "0",          # trust rate control
                "-spatial_aq",   "1",          # spatial adaptive quantization
                "-temporal_aq",  "1",          # temporal adaptive quantization
                "-aq-strength",  "10",         # stronger AQ for better quality
                "-look_ahead",   "32",         # more frames to analyze
                "-surfaces",     "32",         # max surfaces to maximize throughput
                "-gpu",          "0",          # keep both NVENCs on the same dGPU
            ]
            video_args += nvenc_common
            cmd += ["-qmin", "0", "-qmax", "50", "-b:v", "0"]
        
        # Add preset-based parameters
        preset_idx = self.preset_cb.currentIndex()
        
        # threads only for CPU x264 (now index 1)
        if codec_idx == 1:
            # Add CPU preset based on selection
            if preset_idx == 0:  # Standard
                cmd += ["-preset", "medium"]
            elif preset_idx == 1:  # High Quality
                cmd += ["-preset", "slow"]
            elif preset_idx == 2:  # Fast
                cmd += ["-preset", "faster"]
            elif preset_idx == 3:  # Ultra Fast
                cmd += ["-preset", "ultrafast"]
        
        # Apply NVENC preset based on user selection
        if codec_idx in (0, 1, 2):  # Any NVENC encoder
            if preset_idx == 0:  # Standard
                cmd += ["-preset", "p4"]
            elif preset_idx == 1:  # High Quality
                cmd += ["-preset", "p7"]
            elif preset_idx == 2:  # Fast
                cmd += ["-preset", "p2"]
            elif preset_idx == 3:  # Ultra Fast
                cmd += ["-preset", "p1", "-zerolatency", "1"]
        
        cmd += [output]

        # Set process priority - lower for parallel processing to avoid system overload
        process = QProcess(self)
        process.setProgram(cmd[0])
        process.setArguments(cmd[1:])
        process.readyReadStandardError.connect(lambda p=process: self._log_output(p))
        process.finished.connect(lambda *args, p=process, sb=start_btn, tb=stop_btn: 
                                self._on_process_finished(p, sb, tb, path))
        
        # Create UI elements for this process
        self._create_process_widget(process, path)
        
        # Pre-allocate buffer for this process
        self.pending_process_outputs[process] = []
        
        # Add to active processes list
        self.processes.append((process, path))
        process.start()

    @staticmethod
    def _probe_duration(path: str) -> float | None:
        try:
            out = subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                stderr=subprocess.STDOUT,
                text=True
            )
            return float(out.strip())
        except Exception:
            return None

    def _log_output(self, process: QProcess):
        chunk = process.readAllStandardError().data().decode(errors="ignore")
        if not chunk:
            return
            
        # With smart buffer enabled, don't update UI immediately for every output
        if self.smart_buffer_cb.isChecked():
            # Store the output for batch processing
            if process not in self.pending_process_outputs:
                self.pending_process_outputs[process] = []
                
            # Add to pending updates
            self.pending_process_outputs[process].append(chunk)
            
            # Start update timer if not running
            if not self.ui_update_timer.isActive():
                self.ui_update_timer.start()
        else:
            # Immediate update mode
            self._add_to_logs(process, chunk)
            self._process_output(process, chunk)
    
    def _add_to_logs(self, process, chunk):
        """Add chunk to main log and process-specific log"""
        # Log to the main log - limit to last 10000 chars to avoid memory issues
        if len(self.log.toPlainText()) > 10000:
            self.log.clear()
            self.log.appendPlainText("[Log cleared to save memory]\n")
            
        self.log.appendPlainText(chunk)
        vsb = self.log.verticalScrollBar()
        vsb.setValue(vsb.maximum())
        
        # Log to the process-specific log if it exists
        if process in self.process_logs:
            process_log = self.process_logs[process]["log"]
            if len(process_log.toPlainText()) > 5000:
                process_log.clear()
                process_log.appendPlainText("[Log cleared to save memory]\n")
                
            process_log.appendPlainText(chunk)
            vsb = process_log.verticalScrollBar()
            vsb.setValue(vsb.maximum())
            
    def _process_output(self, process, chunk):
        """Process ffmpeg output to update progress indicators"""
        # Find the path associated with this process
        process_path = None
        for p, path in self.processes:
            if p == process:
                process_path = path
                break
        
        if not process_path:
            return
            
        # Get duration for this file if not already available
        if process_path not in self.process_progress:
            duration = self._probe_duration(process_path)
            self.process_progress[process_path] = {
                "duration": duration,
                "start_time": time.time(),
                "current_pct": 0,
                "fps": 0,  # Track encoding speed
                "last_frame": 0,  # For FPS calculation
                "last_fps_time": time.time()  # For FPS calculation
            }
        
        # Extract FPS information if present
        fps_match = re.search(r'fps=\s*(\d+)', chunk)
        if fps_match:
            current_fps = int(fps_match.group(1))
            self.process_progress[process_path]["fps"] = current_fps
        
        # Look for time progress in ffmpeg output
        time_match = self.time_re.search(chunk)
        if not time_match:
            return

        h, m_, s = time_match.groups()
        elapsed_sec = int(h)*3600 + int(m_)*60 + float(s)
        
        # Calculate percentage based on this file's duration
        duration = self.process_progress[process_path]["duration"]
        if not duration:
            return
            
        pct = min(100, int(elapsed_sec / duration * 100))
        self.process_progress[process_path]["current_pct"] = pct
        
        # Update file item in list with colored progress
        if process_path in self.file_list.path_items:
            item = self.file_list.path_items[process_path]
            name = QFileInfo(process_path).fileName()
            
            # Get codec name for item display
            codec_idx = self.file_codec_assignments.get(process_path, self.format_cb.currentIndex())
            codec_name = self.format_cb.itemText(codec_idx).split()[0]  # Get just the format part
            
            item.setText(f"{name} [{codec_name}] — {pct}%")
            
        # Calculate remaining time with more precision
        elapsed = time.time() - self.process_progress[process_path]["start_time"]
        if pct > 0:
            remain = (elapsed / pct) * (100 - pct)  # More precise calculation
        else:
            remain = 0
            
        # Format times for display
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
        remain_str = time.strftime('%H:%M:%S', time.gmtime(remain))
        
        # Get current FPS
        fps = self.process_progress[process_path]["fps"]
        
        # Update process-specific progress bar if it exists
        if process in self.process_widgets:
            # Update progress bar with percentage
            progress_bar = self.process_widgets[process]["progress"]
            progress_bar.setValue(pct)
            progress_bar.setFormat(f"{pct}% ({elapsed_sec:.1f}s / {duration:.1f}s)")
            
            # Update file name label - keep it simple
            self.process_widgets[process]["label"].setText(f"<b>{name}</b>")
            
            # Update detailed ETA in separate label with encoding speed
            codec_idx = self.file_codec_assignments.get(process_path, self.format_cb.currentIndex())
            codec_name = self.format_cb.itemText(codec_idx)
            
            # Create a more informative ETA display
            eta_text = (
                f"<table width='100%' cellspacing='0' cellpadding='0'>" 
                f"<tr><td>Speed:</td><td align='right'><b>{fps} fps</b></td></tr>" 
                f"<tr><td>Elapsed:</td><td align='right'>{elapsed_str}</td></tr>" 
                f"<tr><td>Remaining:</td><td align='right'><b>{remain_str}</b></td></tr>" 
                f"</table>"
            )
            self.process_widgets[process]["eta_label"].setText(eta_text)
    
    def _update_ui(self):
        """Batch update the UI with all pending process outputs"""
        # Process all pending outputs
        for process, chunks in list(self.pending_process_outputs.items()):
            # Skip if process is no longer valid
            if process not in [p for p, _ in self.processes]:
                self.pending_process_outputs.pop(process, None)
                continue
                
            # Combine all chunks for this process
            combined_chunk = ''.join(chunks)
            
            # Add to logs
            self._add_to_logs(process, combined_chunk)
            
            # Process output for progress updates
            self._process_output(process, combined_chunk)
            
            # Clear pending chunks for this process
            self.pending_process_outputs[process] = []
        
        # Update overall progress
        self._update_overall_progress()
        
        # Stop timer if no more pending outputs
        if all(not chunks for chunks in self.pending_process_outputs.values()):
            self.ui_update_timer.stop()
            
    def _update_overall_progress(self):
        """Update overall progress indicators based on all active processes"""
        if not self.processes:
            return
            
        # Calculate overall progress percentage
        overall_pct = 0
        active_files = []
        for process, path in self.processes:
            if path in self.process_progress:
                overall_pct += self.process_progress[path]["current_pct"]
                active_files.append(path)
            
        if self.total > 0:  # Avoid division by zero
            # Calculate weighted progress (completed files count as 100%)
            weighted_pct = (overall_pct + (self.completed * 100)) / self.total
            self.total_progress.setValue(int(weighted_pct))
            
            # Update status bar with progress
            if self.batch_start_time:  # Only if batch conversion is running
                # Calculate overall ETA
                elapsed_total = time.time() - self.batch_start_time
                if weighted_pct > 0:  # Avoid division by zero
                    total_eta = (elapsed_total / weighted_pct) * (100 - weighted_pct)
                    eta_str = time.strftime('%H:%M:%S', time.gmtime(total_eta))
                    
                    # Format elapsed time
                    elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed_total))
                    
                    # Total file counts
                    total_files = len(active_files) + len(self.queue) + self.completed
                    
                    # Get active codecs information
                    active_codecs = {}
                    for path in active_files:
                        codec_idx = self.file_codec_assignments.get(path, 0)
                        codec_type = "GPU" if codec_idx in [0, 1, 2] else "CPU"
                        active_codecs[codec_type] = active_codecs.get(codec_type, 0) + 1
                    
                    # Create codec distribution string
                    codec_info = ""
                    if active_codecs.get("GPU", 0) > 0:
                        codec_info += f"{active_codecs['GPU']} GPU"
                    if active_codecs.get("CPU", 0) > 0:
                        if codec_info:
                            codec_info += " + "
                        codec_info += f"{active_codecs['CPU']} CPU"
                    
                    # Update ETA label with detailed timing
                    self.eta_label.setText(
                        f"Overall ETA: <b>{eta_str}</b> | Elapsed: {elapsed_str} | Progress: {weighted_pct:.1f}%"
                    )
                    
                    # Update current file label with active process details
                    if self.parallel_enabled:
                        active_count = len(self.processes)
                        self.current_file_label.setText(
                            f"Processing {active_count} file(s) ({codec_info}) - "
                            f"Completed: {self.completed}/{total_files}"
                        )
    
    def _on_process_finished(self, process: QProcess, start_btn: QPushButton, stop_btn: QPushButton, path=None):
        exit_code = process.exitCode()
        process_path = path or self.current_path
        
        # Remove from active processes list
        self.processes = [(p, pth) for p, pth in self.processes if p != process]
        
        # Update process widget one last time to show 100% if successful
        if process in self.process_widgets and exit_code == 0:
            self.process_widgets[process]["progress"].setValue(100)
            self.process_widgets[process]["label"].setText(
                f"<b>{QFileInfo(process_path).fileName()}</b> - Complete"
            )
        elif process in self.process_widgets:
            self.process_widgets[process]["label"].setText(
                f"<b>{QFileInfo(process_path).fileName()}</b> - Failed"
            )
            
        # Schedule the process widget for removal after a short delay
        # This allows the user to see the final status
        QTimer.singleShot(5000, lambda: self._remove_process_widget(process))
        
        # Clear progress tracking for this process
        if process_path in self.process_progress:
            del self.process_progress[process_path]
        
        # finalize per-file display
        if process_path in self.file_list.path_items:
            item = self.file_list.path_items[process_path]
            name = QFileInfo(process_path).fileName()
            status = "Done" if exit_code == 0 else "Failed"
            item.setText(f"{name} — {status}")
            
            # Mark completed conversions in green
            if exit_code == 0:
                item.setForeground(QColor(0, 170, 0))  # Green color for completed items

        # delete source if requested and successful
        if exit_code == 0 and self.delete_cb.isChecked():
            try:
                os.remove(process_path)
                self.log.appendPlainText(f"Deleted source: {process_path}")
            except Exception as e:
                self.log.appendPlainText(f"Failed to delete {process_path}: {e}")

        # update totals
        self.completed += 1
        self.total_progress.setValue(int(self.completed / self.total * 100))

        # In parallel mode, start a new process for each completed one
        if self.parallel_enabled and self.queue:
            self._process_next(start_btn, stop_btn)
        # If not parallel, or no more files in the queue
        elif not self.parallel_enabled:
            if self.completed >= self.total:
                self._finish(start_btn, stop_btn)
            else:
                self._process_next(start_btn, stop_btn)
        # Check if all processes are done in parallel mode
        elif not self.processes and self.completed >= self.total:
            self._finish(start_btn, stop_btn)

    def stop_conversion(self, start_btn: QPushButton, stop_btn: QPushButton):
        # kill any running QProcess
        for process, _ in self.processes:
            if process.state() != QProcess.NotRunning:
                process.kill()
                
                # Update status of process widget
                if process in self.process_widgets:
                    self.process_widgets[process]["label"].setText(
                        f"<b>{QFileInfo(self.process_widgets[process]['path']).fileName()}</b> - Stopped"
                    )
        
        # Schedule removal of all process widgets after a delay
        for process in list(self.process_widgets.keys()):
            QTimer.singleShot(3000, lambda p=process: self._remove_process_widget(p))
            
        # Clear processes list
        self.processes = []
        
        self.log.appendPlainText("Conversion stopped by user.")
        start_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        self.eta_label.clear()
        self.current_file_label.clear()

    def _finish(self, start_btn: QPushButton, stop_btn: QPushButton):
        self.log.appendPlainText("All conversions complete.")
        start_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        self.current_file_label.clear()
        self.eta_label.clear()
        self.process_progress = {}  # Clear all process progress
        
        # Return to main log tab when finished
        self.processes_tab.setCurrentIndex(0)

    def _show_about(self):
        QMessageBox.information(
            self,
            "About TS Converter GUI",
            "TS Converter GUI - RTX Advanced\nVersion 2.0\nAdvanced Hybrid Encoding\n" + 
            "Optimized for Intel i9-14900HX + RTX 4090\n" +
            "Features: HEVC/AV1 NVENC, audio passthrough, smart auto-balance"
        )

    def closeEvent(self, event):
        running = bool(self.processes)
        if running:
            if QMessageBox.question(
                self,
                "Conversions running",
                "Jobs are still in progress. Quit anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            ) == QMessageBox.No:
                event.ignore()
                return
            for process, _ in self.processes:
                if process.state() != QProcess.NotRunning:
                    process.kill()

        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitterState", self.splitter.saveState())
        self.settings.setValue("lastDir", self.last_dir)
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
