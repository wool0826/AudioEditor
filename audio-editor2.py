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
    def __init__(self, directory, filename, extension, output):
        mean_volume = re.search(r"mean_volume:\s(-?\d+\.\d+) dB", output)
        max_volume = re.search(r"max_volume:\s(-?\d+\.\d+) dB", output)
        bitrate = re.search(r"bitrate: (\d+) kb/s", output)

        mean_volume = float(mean_volume.group(1)) if mean_volume else 0.0
        max_volume = float(max_volume.group(1)) if max_volume else 0.0
        bitrate = int(bitrate.group(1)) if bitrate else None

        self.directory = directory
        self.filename = filename
        self.filename_after = f'{filename}_adjusted'

        self.max_volume = max_volume
        self.reserved = False

        self.extension = extension
        self.extension_after = extension

        self.mean_volume = round(mean_volume, 2)
        self.mean_volume_after = round(mean_volume, 2)

        self.bitrate = f'{bitrate}K' if self.extension != '.mp4' else '320K'
        self.bitrate_after = self.bitrate

    def isChanged(self):
        return self.mean_volume != self.mean_volume_after or self.extension != self.extension_after or self.bitrate != self.bitrate_after
    
    def canReserve(self):
        return self.reserved or self.isChanged()

    def getVolumeDiff(self):
        return round(self.mean_volume_after - self.mean_volume, 2)

    def getBeforeData(self):
        return f'filename: {self.filename}{self.extension}\nvolume:\n  mean: {self.mean_volume}\n  max: {self.max_volume}\nbitrate: {self.bitrate}'
    
    def getAfterData(self):
        return f'filename: {self.filename_after}{self.extension_after}\nvolume:\n mean: {self.mean_volume_after}\n max: {self.max_volume}\nbitrate: {self.bitrate_after}'

class FileEditorSignals(QObject):
    finished = pyqtSignal(object)

class FileEditor(QRunnable):
    def __init__(self, audio_file):
        super().__init__()
        self.audio_file = audio_file
        self.signals = FileEditorSignals()

    @pyqtSlot()
    def run(self):
        before_absolute_path = os.path.join(self.audio_file.directory, f'{self.audio_file.filename}{self.audio_file.extension}')
        after_absolute_path = os.path.join(self.audio_file.directory, f'{self.audio_file.filename_after}{self.audio_file.extension_after}')

        if self.audio_file.extension == '.flac':
            result = (
                ffmpeg
                    .input(before_absolute_path)
                    .output(after_absolute_path, af=f'volume={self.audio_file.getVolumeDiff()}dB', **{'c:v': 'copy', 'c:a': 'alac'})
                    .overwrite_output()
                    .run()
            )
        else:
            result = (
                ffmpeg
                    .input(before_absolute_path)
                    .output(after_absolute_path, af=f'volume={self.audio_file.getVolumeDiff()}dB', **{'b:a': f'{self.audio_file.bitrate_after}'})
                    .overwrite_output()
                    .run()
            )

        print(f'{before_absolute_path} complete')

class FileLoaderSignals(QObject):
    finished = pyqtSignal(object)

class FileLoader(QRunnable):
    def __init__(self, dir_path, full_name, name, ext):
        super().__init__()
        self.dir_path = dir_path
        self.full_name = full_name
        self.name = name
        self.ext = ext
        self.signals = FileLoaderSignals()

    @pyqtSlot()
    def run(self):
        absolute_path = os.path.join(self.dir_path, self.full_name)
        stream = (
            ffmpeg
                .input(absolute_path)
                .output('-', format='null', af='volumedetect')
        )
        _, stderr = ffmpeg.run(stream, capture_stdout=True, capture_stderr=True)
        audio_file = AudioFile(self.dir_path, self.name, self.ext, stderr.decode())

        audio_files[self.full_name] = audio_file
        self.signals.finished.emit(self.full_name)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Editor")
        self.setUpUI()
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(os.cpu_count())

    # 디렉토리 선택 팝업 노출
    def selectDirectory(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Select directory.')

        if dir_path:
            self.file_list.clear() 
            self.directory_label.setText(f'workspace: {dir_path}')

            for file in os.listdir(dir_path):
                name, ext = os.path.splitext(file)

                if ext in ('.mp4', '.mp3', '.m4a', '.flac'):
                    file_loader = FileLoader(dir_path, file, name, ext)
                    file_loader.signals.finished.connect(self.file_list.addItem)
                    
                    self.thread_pool.start(file_loader)

    def findIndexInComboBox(self, combo_box, text_to_find):
        index = combo_box.findText(text_to_find)
        
        if index == -1:
            combo_box.addItem(text_to_find)
            return combo_box.count() - 1
        
        return index
    
    def drawApplyButton(self):
        reserve_count = sum(1 for v in audio_files.values() if v.reserved is True)

        if reserve_count > 0 and self.file_list.count() > 0:
            self.apply_button.setEnabled(True)
            self.apply_button.setText(f'3. Apply (total: {reserve_count})')
        else:
            self.apply_button.setEnabled(False)
            self.apply_button.setText('3. Apply')

    def onSelectedFileChanged(self, item):
        print('onSelectedFileChanged')

        current_file = audio_files[item.text()]

        self.metadata_label.setText(current_file.getBeforeData())
        self.metadata_after_label.setText(current_file.getAfterData())

        self.volume_double_spin_box.setValue(current_file.mean_volume_after)
        self.volume_double_spin_box.setEnabled(True)

        self.bitrate_combo_box.setCurrentIndex(self.findIndexInComboBox(self.bitrate_combo_box, current_file.bitrate_after))
        self.bitrate_combo_box.setEnabled(False if current_file.extension == '.flac' else True)

        self.extension_combo_box.setCurrentIndex(self.findIndexInComboBox(self.extension_combo_box, current_file.extension_after))
        self.extension_combo_box.setEnabled(True)

        self.reserve_button.setEnabled(current_file.canReserve())

        self.drawApplyButton()

    def observeComplete(self):
        self.count = self.count + 1
    
        if self.max_count < self.count:
            self.max_count = 0
            self.count = 0

            self.reserve_button.setEnabled(True)
            self.apply_button.setEnabled(True)
            self.drawApplyButton()

    def onApplyButtonClicked(self):
        self.reserve_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        
        for k, v in audio_files.items():
            if v.reserved:
                fileEditor = FileEditor(v)
                fileEditor.signals.finished.connect()
                self.thread_pool.start(fileEditor)



        return
    
    def onReserveButtonClicked(self):
        print('onReserveButtonClicked')
        
        current_file = audio_files[self.file_list.currentItem().text()]
        current_file.reserved = current_file.isChanged()
        self.reserve_button.setEnabled(current_file.canReserve())

        self.drawApplyButton()

    def onExtensionChanged(self, text):
        current_file = audio_files[self.file_list.currentItem().text()]

        if current_file.extension_after == text:
            return
        
        current_file.extension_after = text
            
        self.reserve_button.setEnabled(current_file.canReserve())
        self.metadata_after_label.setText(current_file.getAfterData())        

    def onBitrateChanged(self, text):
        current_file = audio_files[self.file_list.currentItem().text()]

        if current_file.bitrate_after == text:
            return

        current_file.bitrate_after = text

        self.reserve_button.setEnabled(current_file.canReserve())
        self.metadata_after_label.setText(current_file.getAfterData())        

    def onVolumeChanged(self, value):
        current_file = audio_files[self.file_list.currentItem().text()]

        if current_file.mean_volume_after == value:
            return
        
        current_file.mean_volume_after = value

        self.reserve_button.setEnabled(current_file.canReserve())
        self.metadata_after_label.setText(current_file.getAfterData())
        
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
        self.file_list.currentItemChanged.connect(self.onSelectedFileChanged)
        layout.addWidget(self.file_list, 1, 0, 3, 1)
        
        self.metadata_label = QLabel('', self)
        self.metadata_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.metadata_label, 1, 1, 1, 2)

        self.metadata_arrow_label = QLabel('↓', self)
        self.metadata_arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.metadata_arrow_label, 2, 1, 1, 2)

        self.metadata_after_label = QLabel('', self)
        self.metadata_after_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.metadata_after_label, 3, 1, 1, 2)

        self.extension_label = QLabel('extension', self)
        self.extension_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.extension_label, 4, 0)

        self.extension_combo_box = QComboBox(self)
        self.extension_combo_box.addItem('.m4a')
        self.extension_combo_box.addItem('.mp3')
        self.extension_combo_box.addItem('.mp4')
        self.extension_combo_box.currentTextChanged.connect(self.onExtensionChanged)
        layout.addWidget(self.extension_combo_box, 4, 1, 1, 2)

        self.bitrate_label = QLabel('bitrate', self)
        self.bitrate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.bitrate_label, 5, 0)

        self.bitrate_combo_box = QComboBox(self)
        self.bitrate_combo_box.addItem('192K')
        self.bitrate_combo_box.addItem('320K')
        self.bitrate_combo_box.currentTextChanged.connect(self.onBitrateChanged)
        layout.addWidget(self.bitrate_combo_box, 5, 1, 1, 2)

        self.volume_label = QLabel('mean volume', self)
        self.volume_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.volume_label, 6, 0)

        self.volume_double_spin_box = QDoubleSpinBox()
        self.volume_double_spin_box.setRange(-100, 100)
        self.volume_double_spin_box.setSingleStep(0.05)
        self.volume_double_spin_box.valueChanged.connect(self.onVolumeChanged)
        layout.addWidget(self.volume_double_spin_box, 6, 1, 1, 2)

        self.reserve_button = QPushButton('2. Reserve')
        self.reserve_button.setEnabled(False)
        self.reserve_button.clicked.connect(self.onReserveButtonClicked)
        layout.addWidget(self.reserve_button, 7, 0, 1, 3)

        self.apply_button = QPushButton('3. Apply')
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.onApplyButtonClicked)
        layout.addWidget(self.apply_button, 8, 0, 1, 3)

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