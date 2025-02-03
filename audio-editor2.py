from PyQt6.QtWidgets import (
    QListWidget, 
    QSizePolicy,
    QWidget, 
    QApplication, 
    QMainWindow,
    QGridLayout, 
    QLabel, 
    QPushButton, 
    QComboBox,
    QDoubleSpinBox,
    QFileDialog
)
from PyQt6.QtCore import (
    QObject,
    Qt,
    QRunnable, 
    QThreadPool,
    pyqtSignal,
    pyqtSlot
)

import ffmpeg
import sys
import os
import re

audio_files = {}

class AudioFile():
    def __init__(self, filename, extension, output):
        mean_volume = re.search(r"mean_volume:\s(-?\d+\.\d+) dB", output)
        max_volume = re.search(r"max_volume:\s(-?\d+\.\d+) dB", output)
        bitrate = re.search(r"bitrate: (\d+) kb/s", output)

        mean_volume = float(mean_volume.group(1)) if mean_volume else None
        max_volume = float(max_volume.group(1)) if max_volume else None
        bitrate = int(bitrate.group(1)) if bitrate else None

        self.filename = filename
        self.filename_after = f'{filename}_adjusted'

        self.max_volume = max_volume
        self.changed = False
        self.reserved = False

        self.extension = extension
        self.extension_after = extension

        self.mean_volume = mean_volume
        self.mean_volume_after = round(mean_volume, 2)

        self.bitrate = f'{bitrate}K'
        self.bitrate_after = self.bitrate

    def checkChanged(self):
        if self.mean_volume != self.mean_volume_after or self.extension != self.extension_after or self.bitrate != self.bitrate_after:
            self.changed = True
        else:
            self.changed = False

        return self.changed
    
    def getVolumeDiff(self):
        return self.mean_volume_after - self.mean_volume

    def getBeforeData(self):
        return f'filename: {self.filename}{self.extension}\nvolume:\n  mean: {self.mean_volume}\n  max: {self.max_volume}\nbitrate: {self.bitrate}'
    
    def getAfterData(self):
        return f'filename: {self.filename_after}{self.extension_after}\nvolume:\n mean: {self.mean_volume_after}\n max: {self.max_volume}\nbitrate: {self.bitrate_after}'

class FileLoaderSignals(QObject):
    finished = pyqtSignal(object)

class FileLoader(QRunnable):
    def __init__(self, absolute_path, full_name, name, ext):
        super().__init__()
        self.absolute_path = absolute_path
        self.full_name = full_name
        self.name = name
        self.ext = ext
        self.signals = FileLoaderSignals()

    @pyqtSlot()
    def run(self):  
        stream = (
            ffmpeg
                .input(self.absolute_path)
                .output('-', format='null', af='volumedetect')
        )
        _, stderr = ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
        audio_file = AudioFile(self.name, self.ext, stderr.decode())

        audio_files[self.full_name] = audio_file
        self.signals.finished.emit(self.full_name)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Editor")
        self.setUpUI()
        self.thread_pool = QThreadPool()

        # 디렉토리 선택 팝업 노출
    def selectDirectory(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Select directory.')

        if dir_path:
            self.file_list.clear() 
            self.directory_label.setText(f'workspace: {dir_path}')

            for file in os.listdir(dir_path):
                absolute_path = os.path.join(dir_path, file)
                name, ext = os.path.splitext(file)

                if ext in ('.mp4', '.mp3', '.m4a', '.flac'):
                    file_loader = FileLoader(absolute_path, file, name, ext)
                    file_loader.signals.finished.connect(self.file_list.addItem)
                    
                    self.thread_pool.start(file_loader)

    def setUpUI(self):
        layout = QGridLayout()

        self.directory_button = QPushButton('1. Open directory', self)
        self.directory_button.setEnabled(True)
        self.directory_button.clicked.connect(self.selectDirectory)

        layout.addWidget(self.directory_button, 0, 0)
        
        self.directory_label = QLabel('', self)
        self.directory_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.directory_label, 0, 1, 1, 2)

        self.file_list = QListWidget()
        self.file_list.setMinimumWidth(300)
        self.file_list.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.file_list, 1, 0, 3, 1)
        
        self.metadata_label = QLabel('', self)
        self.metadata_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.metadata_label, 1, 1, 1, 2)

        self.metadata_arrow_label = QLabel('↓', self)
        self.metadata_arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.metadata_arrow_label, 2, 1, 1, 2)

        self.metadata_after_label = QLabel('', self)
        self.metadata_after_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.metadata_after_label, 3, 1, 1, 2)

        self.extension_label = QLabel('extension', self)
        self.extension_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.extension_label, 4, 0)

        self.extension_combo_box = QComboBox(self)
        self.extension_combo_box.addItem('.m4a')
        self.extension_combo_box.addItem('.mp3')
        self.extension_combo_box.addItem('.mp4')
        layout.addWidget(self.extension_combo_box, 4, 1, 1, 2)

        self.bitrate_label = QLabel('bitrate', self)
        self.bitrate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.bitrate_label, 5, 0)

        self.bitrate_combo_box = QComboBox(self)
        self.bitrate_combo_box.addItem('192K')
        self.bitrate_combo_box.addItem('320K')
        layout.addWidget(self.bitrate_combo_box, 5, 1, 1, 2)

        self.volume_label = QLabel('mean volume', self)
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.volume_label, 6, 0)

        volume_double_spin_box = QDoubleSpinBox()
        volume_double_spin_box.setRange(-100, 100)
        volume_double_spin_box.setSingleStep(0.05)
        layout.addWidget(volume_double_spin_box, 6, 1, 1, 2)

        reserve_button = QPushButton('2. Reserve')
        reserve_button.setEnabled(True)
        layout.addWidget(reserve_button, 7, 0, 1, 3)

        apply_button = QPushButton('3. Apply')
        apply_button.setEnabled(True)
        layout.addWidget(apply_button, 8, 0, 1, 3)

        widget = QWidget()
        widget.setLayout(layout)
        widget.setMinimumWidth(900)
        widget.setMinimumHeight(500)

        self.setCentralWidget(widget)

if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()