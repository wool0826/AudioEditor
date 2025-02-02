import sys
import os
import subprocess
import re

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import uic

ui_class = uic.loadUiType("audio-editor.ui")[0]
files_by_name={}
extensions={
    ".flac": [ ".flac", ".m4a" ],
    ".mp4": [ ".mp4", ".mp3", ".m4a" ],
    ".mp3": [ ".mp3", ".m4a" ],
    ".m4a": [ ".m4a", ".mp3" ]
}

class BackgroundWorker(QRunnable):
    def __init__(self, audio_file, directory):
        super().__init__()
        self.audio_file = audio_file
        self.directory = directory
    
    def run(self):
        before_file_name = f'{self.audio_file.filename}{self.audio_file.extension}'
        after_file_name = f'{self.audio_file.filename_after}{self.audio_file.extension_after}'

        file_path = os.path.join(self.directory, before_file_name)
        output_path = os.path.join(self.directory, after_file_name)

        if self.audio_file.extension == '.flac':
            command = f'ffmpeg -y -i "{file_path}" -af volume="{self.audio_file.getVolumeDiff()}dB" -c:v copy -c:a alac "{output_path}"'            
        else:
            command = f'ffmpeg -y -i "{file_path}" -b:a {self.audio_file.bitrate_after} -af volume="{self.audio_file.getVolumeDiff()}dB" "{output_path}" 2>&1'
        
        subprocess.run(command, shell=True, capture_output=True, text=True)

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

class AudioEditor(QMainWindow, ui_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.threadpool = QThreadPool()
        self.constructEventListener()
    
    def constructEventListener(self):
        self.directory_button.clicked.connect(self.selectDirectory)
        self.file_list.currentItemChanged.connect(self.updateMetadataWindow)

        self.extension_combo_box.currentIndexChanged.connect(self.updateExtension)
        self.quality_combo_box.currentIndexChanged.connect(self.updateBitrate)
        self.volume_double_spin_box.valueChanged.connect(self.updateVolume)
        self.reserve_button.clicked.connect(self.reserve)
        self.apply_button.clicked.connect(self.execute)
        
        self.apply_button.setEnabled(False)

    # 디렉토리 선택 팝업 노출
    def selectDirectory(self):
        dir_path = QFileDialog.getExistingDirectory(self, '디렉토리 선택')
        if dir_path:
            self.directory_label.setText(dir_path)
            self.loadMusicFiles(dir_path)

    def loadMusicFiles(self, dir_path):
        self.file_list.clear()
        files_by_name.clear()

        for file in os.listdir(dir_path):
            name, ext = os.path.splitext(file)

            if ext in ('.mp4', '.mp3', '.m4a', '.flac'):
                file_name = f'{name}{ext}'
                metadata = self.obtainMetadata(file)
                
                self.file_list.addItem(file_name)
                files_by_name[file_name] = AudioFile(name, ext, metadata)

    def obtainMetadata(self, filename):
        file_path = os.path.join(self.directory_label.text(), filename)
        command = f'ffmpeg -i "{file_path}" -af volumedetect -f null - 2>&1'
        result = subprocess.run(command, shell=True, capture_output=True, text=True)

        return result.stdout
    
    def clearMetadataWindow(self):
        self.metadata.setText('')
        self.metadata_after.setText('')
        self.volume_double_spin_box.setEnabled(False)
        self.quality_combo_box.setEnabled(False)
        self.extension_combo_box.setEnabled(False)
        self.reserve_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.apply_button.setText(f'3. 전체 적용')

    def findIndexInComboBox(self, combo_box, text_to_find):
        index = combo_box.findText(text_to_find)
        
        if index == -1:
            combo_box.addItem(text_to_find)
            return combo_box.count() - 1
        
        return index
    
    def countReservedFiles(self):
        return sum(1 for v in files_by_name.values() if v.reserved is True)

    # 파일 목록에서 파일 선택 시
    def updateMetadataWindow(self):
        if not self.file_list.currentItem():
            self.clearMetadataWindow()
            return

        current_item = self.file_list.currentItem().text()
        current_file = files_by_name[current_item]

        current_file.checkChanged()

        self.metadata.setText(current_file.getBeforeData())
        self.metadata_after.setText(current_file.getAfterData())
        
        # volume
        self.volume_double_spin_box.setValue(current_file.mean_volume_after)
        self.volume_double_spin_box.setEnabled(True)

        # bitrate
        self.quality_combo_box.setCurrentIndex(self.findIndexInComboBox(self.quality_combo_box, current_file.bitrate_after))

        if current_file.extension == '.flac':
            self.quality_combo_box.setEnabled(False)    
        else:
            self.quality_combo_box.setEnabled(True)
        
        # extension
        self.extension_combo_box.setCurrentIndex(self.findIndexInComboBox(self.extension_combo_box, current_file.extension_after))
        self.extension_combo_box.setEnabled(True)

        # reserve button
        if current_file.reserved or current_file.changed:
            self.reserve_button.setEnabled(True)
        else:
            self.reserve_button.setEnabled(False)

        reserve_count = self.countReservedFiles()
        
        # apply button
        if reserve_count > 0 and self.file_list.count() > 0:
            self.apply_button.setEnabled(True)
            self.apply_button.setText(f'3. 전체 적용 ({reserve_count}개)')
        else:
            self.apply_button.setEnabled(False)
            self.apply_button.setText(f'3. 전체 적용')
    
    # action on event
    def updateExtension(self):
        current_item = self.file_list.currentItem().text()
        current_file = files_by_name[current_item]

        current_file.extension_after = self.extension_combo_box.currentText()
        
        self.updateMetadataWindow()

    def updateBitrate(self):
        current_item = self.file_list.currentItem().text()
        current_file = files_by_name[current_item]

        current_file.bitrate_after = self.quality_combo_box.currentText()
    
        self.updateMetadataWindow()

    def updateVolume(self):
        current_item = self.file_list.currentItem().text()
        current_file = files_by_name[current_item]

        current_file.mean_volume_after = round(self.volume_double_spin_box.value(), 2)

        self.updateMetadataWindow()

    def reserve(self):
        current_item = self.file_list.currentItem().text()
        current_file = files_by_name[current_item]

        current_file.reserved = current_file.checkChanged()
        
        self.updateMetadataWindow()

    # 전체적용 버튼 클릭 시 수행할 동작
    def execute(self):
        for v in files_by_name.values():
            if v.changed and v.reserved:
                worker = BackgroundWorker(v, self.directory_label.text())
                self.threadpool.start(worker)
        
        self.loadMusicFiles(self.directory_label.text())
        self.updateMetadataWindow()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AudioEditor()
    ex.show()
    sys.exit(app.exec_())