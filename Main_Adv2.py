from PySide6 import QtWidgets, QtUiTools, QtCore, QtGui
import sys
import os
import subprocess
import shutil
import threading
import re
import io
import glob
import cv2
import time
import uuid
import signal

# import logging

'''
Main script to convert image sequence or video files to WebM format using FFmpeg.
'''
SCRIPT_FILE_PATH = os.path.dirname(os.path.abspath(__file__))
UI_FILE_PATH = "ui/PngSeq2Webm_UI.ui"

def resource_path(relative_path):
    """🎁 Works in dev and in PyInstaller bundles"""
    try:
        base = sys._MEIPASS  # PyInstaller temp folder
    except AttributeError:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, relative_path)

def truncate_path_by_folder(path, keep_start=2, keep_end=2):
    # Normalize path separators
    parts = os.path.normpath(path).split(os.sep)

    if len(parts) <= (keep_start + keep_end):
        return path

    return os.sep.join(parts[:keep_start]) + os.sep + '...' + os.sep + os.sep.join(parts[-keep_end:])

def get_mov_duration_and_frame_count(ffmpeg, path):
    try:
        proc = subprocess.run(
            [ffmpeg, '-i', path],
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        output = proc.stderr

        # Extract duration
        dur_match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', output)
        if dur_match:
            h, m, s = dur_match.groups()
            total_duration = int(h) * 3600 + int(m) * 60 + float(s)
        else:
            total_duration = None

        # Extract fps
        fps_match = re.search(r'(\d+(?:\.\d+)?) fps', output)
        if fps_match:
            fps = float(fps_match.group(1))
        else:
            fps = None

        total_frames = int(total_duration * fps) if total_duration and fps else None
        return total_duration, total_frames

    except Exception as e:
        print(f"Error getting MOV info: {e}")
        return None, None

class ConverterSignals(QtCore.QObject):
    progress = QtCore.Signal(float)  # emits percentage (0–100)
    finished = QtCore.Signal(bool)   # success/failure
    cancelled = QtCore.Signal()


class MainWindow(QtWidgets.QMainWindow):
    show_warning = QtCore.Signal(str, str)
    show_critical = QtCore.Signal(str, str)
    show_info = QtCore.Signal(str, str)

    def __init__(self):

        super(MainWindow, self).__init__()
        # Build the correct path to your .ui file
        ui_path = resource_path(UI_FILE_PATH)
        self.setWindowTitle("Webm Converter")
        # self.setWindowIcon(QtGui.QIcon(resource_path(".\icon\icon.png")))  # Set the window icon

        # Apply global QSS

        loader = QtUiTools.QUiLoader()
        ui_file = QtCore.QFile(ui_path)
        ui_file.open(QtCore.QFile.ReadOnly)
        self.theMainWidget = loader.load(ui_file,self)
        ui_file.close() 
        self.setCentralWidget(self.theMainWidget)
        
        
        self.theMainWidget.setStyleSheet("""

        QWidget {
            background-color:#0D0D0D ;
            color: #E0E0E0;
        }
        QGroupBox {
            background-color:#232324;
            color: #E0E0E0;
            border: 0px solid;
            padding:10px;
            padding-top:15px;
            border-radius: 6px;
        }
        QLineEdit {
            background-color: #515152;
            color: #F2F2F2;
            border-color: #ff0000;
            border-radius:6px;
            padding-top: 3px;
            padding-bottom: 3px;
            padding-left: 10px;
            padding-right:10px;
        }
        QSpinBox {
            background-color: #515152;
            border-radius:4px;
            color: #E0E0E0;
            padding-left: 3px;
            padding-right:3px;
        }
        QDoubleSpinBox {
            background-color: #515152;
            border-radius:4px;
            color: #E0E0E0;
            padding-left: 3px;
            padding-right:3px;
        }


        QSpinBox:disabled {
            background-color: #3A3A3B;
            color: #959597;
        }
        QLabel {
            background-color: #232324;
            color: #E0E0E0;
        }
        QPushButton {
            background-color: #7E7E81;
            color: #f5f5f5;
            border: 1px solid #0D0D0D;
            border-radius:6px;
            padding-top: 3px;
            padding-bottom: 3px;
            padding-left: 15px;
            padding-right:15px;
        }
            QPushButton#QPushButton_Convert {
            background-color: #94BEFF;
            color:0D0D0D;
}
        QPushButton::hover {
            background-color: #959597;
        }
        QPushButton#QPushButton_Convert::hover {
            background-color: #B8D4FF;
        }
        QPushButton::pressed {
            background-color: #68686A;
        }
        QPushButton#QPushButton_Convert::pressed {
            background-color: #86ABE5;
        }
        QCheckBox {
            background-color: #F2F2F2;
            color: #E0E0E0;
            border-color: #232323;
            border-radius:4px;
        }
    """)

        # self.theMainWidget.QLineEdit_FFMpegLoc.setText("L:/LEMONSKY/LSA_PIPELINE/02_RnD/_TEMP/Sumesh/Winston/FFMpeg/ffmpeg.exe")

        self.theMainWidget.QPushButton_Convert.clicked.connect(self.start_conversion)
        # self.theMainWidget.QPushButton_FFMpegLocBrowse.clicked.connect(self.browse_FFMpeg)
        self.theMainWidget.QPushButton_InputFileBrowse.clicked.connect(self.browse_input_file)
        self.theMainWidget.QPushButton_OutputFileBrowse.clicked.connect(self.browse_output_file)
        self.theMainWidget.QCheckbox_Settings_Bitrate.stateChanged.connect(self.switch_bitrate)

        self.show_warning.connect(self._show_warning_box)
        self.show_critical.connect(self._show_critical_box)
        self.show_info.connect(self._show_info_box)

        self.settings = QtCore.QSettings("YourCompany", "PngSequence2Webm")
        self._create_menu()
        self.active_conversions = {}
        
    # @QtCore.Slot(float)
    # def on_progress(self, value):
    #     self.progressDialog.progress.setValue(int(value))

    @QtCore.Slot(bool)
    def on_finished(self, progressDialog, success):
        progressDialog.setValue(100)
        progressDialog.close()
        # if success:
            # pass
            # self.show_info.emit("Conversion Complete", "Finished!")
        # else:
            # self.show_critical.emit("Conversion Failed", "Check logs or stats.")

    def on_cancel(self, task_id, signals):
        print("Cancelling conversion...")
        data = self.active_conversions.get(task_id)
        print(task_id)
        print(data["process"])
        if data and data["process"]:
            print("still running")
            process = data["process"]
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])
            print('heresub')

            
    '''
    Help Doc
    '''
    def _create_menu(self):
        menu_bar = self.menuBar()
        help_menu = menu_bar.addMenu("&Help")  # Alt+H shortcut
        
        view_help = QtGui.QAction("View Help", self)
        view_help.setStatusTip("Open help document")
        view_help.triggered.connect(self.open_help_document)
        help_menu.addAction(view_help)

        return 0
        
    
    def open_help_document(self):
        help_path = os.path.join(SCRIPT_FILE_PATH, 'doc', 'help_doc.pdf')  # modify as needed
        url = QtCore.QUrl.fromLocalFile(help_path)
        QtGui.QDesktopServices.openUrl(url)

        return 0
        
    '''
    Message Box
    '''
    def _show_warning_box(self, title, message):
        QtWidgets.QMessageBox.warning(self, title, message)

        return 0

    def _show_critical_box(self, title, message):
        QtWidgets.QMessageBox.critical(self, title, message)

        return 0

    def _show_info_box(self, title, message):
        msg = QtWidgets.QMessageBox(self)                  # instance-based
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setModal(False)                                # make it non-modal
        msg.setAttribute(QtCore.Qt.WA_DeleteOnClose)      # auto-cleanup after close
        msg.show()   

        return 0
    '''
    State Change
    '''
    def switch_bitrate(self):
        switch = self.theMainWidget.QCheckbox_Settings_Bitrate.isChecked()
        self.theMainWidget.QSpinBox_Settings_Bitrate.setEnabled(switch)
        return 0

    '''
    Browse Functions
    '''
    def browse_FFMpeg(self):
        last_dir = self.settings.value("ffmpeg_dir", "")
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select FFmpeg Executable",
            last_dir,
            "Executable Files (*.exe);;All Files (*)"
        )
        if file_path:
            self.theMainWidget.QLineEdit_FFMpegLoc.setText(file_path)
            self.settings.setValue("ffmpeg_dir", os.path.dirname(file_path))

        return 0
    
    def browse_input_file(self):
        last_dir = self.settings.value("input_dir", "")
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Input File (Video or Image Sequence)",
            last_dir,
            "Media Files (*.mp4 *.mov *.png);;All Files (*)"
        )
        if file_path:
            # Try to convert to sequence pattern if it's an image
            _ , self.ext = os.path.splitext(file_path)
            match = re.search(r'^(.*?)([._])(\d+)(\.\w+)$', file_path)

            if match and self.ext == ".png":
                prefix, seperator, digits, ext = match.groups()
                pattern = f"{prefix}{seperator}%0{len(digits)}d{ext}"
                self.theMainWidget.QLineEdit_InputFile.setText(pattern)
            else:
                self.theMainWidget.QLineEdit_InputFile.setText(file_path)
            self.settings.setValue("input_dir", os.path.dirname(file_path))

        return 0

    def browse_output_file(self):
        last_dir = self.settings.value("output_dir", "")
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Select Output WebM File",
            last_dir,
            "WebM Video (*.webm);;All Files (*)"
        )
        if file_path:
            self.theMainWidget.QLineEdit_OutputFile.setText(file_path)
            self.settings.setValue("output_dir", os.path.dirname(file_path))

        return 0
    '''
    Main Func
    '''
    def start_conversion(self):
        self.ffmpeg_path = "D:\\Script_D\\_FINAL\\PngSequence2Webm\\ffmpeg.exe"
        self.input_file = self.theMainWidget.QLineEdit_InputFile.text()
        self.output_file = self.theMainWidget.QLineEdit_OutputFile.text()

        progressDialog = QtWidgets.QProgressDialog("", "Cancel", 0, 100)
        progressDialog.setAutoClose(False)
        progressDialog.setAutoReset(False)
        progressDialog.setWindowTitle("Converting")
        progressDialog.setWindowModality(QtCore.Qt.NonModal) 


        label = QtWidgets.QLabel(
            f"Converting:\n"
            f"  {'Source:':<7} {truncate_path_by_folder(self.input_file)}\n"
            f"  {'Output:':<7} {truncate_path_by_folder(self.output_file)}"
        )
        progressDialog.setLabel(label)

        task_id = str(uuid.uuid4())  # ✅ generate a unique ID
        thread = threading.Thread(target=lambda: self.convert(task_id, signals, progressDialog))

        signals = ConverterSignals()
        signals.progress.connect(progressDialog.setValue)
        signals.finished.connect(lambda success: self.on_finished(progressDialog, success))
        progressDialog.canceled.connect(lambda: self.on_cancel(task_id, signals))
        
        

        self.active_conversions[task_id] = {
            "thread": thread,
            "process": None  # you'll set this in `self.convert`
        }
        
        thread.start()
        return 0

    def convert(self, task_id, signals, progressDialog):
        # Check FFmpeg path
        if not self.ffmpeg_path or not os.path.isfile(self.ffmpeg_path):
            self.show_warning.emit("FFmpeg Not Found", "FFmpeg executable not found. Please select the correct FFmpeg path.")
            progressDialog.close()
            return

        # Check input file
        elif not self.input_file:
            self.show_warning.emit("Input File Missing", "Please provide a valid input file or image sequence.")
            progressDialog.close()
            return
        thread = threading.current_thread()
        if self.theMainWidget.QSpinBox_Settings_Bitrate.isEnabled():
            bitrate = self.theMainWidget.QSpinBox_Settings_Bitrate.text()
        else:
            bitrate = 0

        frameRate = self.theMainWidget.QSpinBox_Settings_FrameRate.value()  # Default frame rate
        crf = self.theMainWidget.QSpinBox_Settings_CRF.value()  # Constant Rate Factor for quality
        output_f = self.output_file



        is_image_sequence = '%' in self.input_file
        total_frames = None
        total_duration = None

        if is_image_sequence:
            glob_pattern = re.sub(r'%0\d+d', '*', self.input_file)
            matches = sorted(glob.glob(glob_pattern))
            if not matches:
                self.show_warning.emit("No Images Found", f"No files match {glob_pattern}")
                progressDialog.close()
                return
            total_frames = len(matches)
        else:
            total_duration, total_frames = get_mov_duration_and_frame_count(self.ffmpeg_path,self.input_file)
            if total_frames is None:
                self.show_warning.emit("Error", "Could not determine MOV duration or frame count.")
                progressDialog.close()
                return
      
        # Check output file
        if not self.output_file:
            self.show_warning.emit("Output File Missing", "Please provide an output file path.")
            progressDialog.close()
            return

        if not self.output_file.lower().endswith('.webm'):
            self.show_warning.emit("Invalid Output Extension", "Output file must have a .webm extension.")
            progressDialog.close()
            return
        
        if self.ext == '.png':
            framerate_filter = f'-framerate {frameRate}'
        else:
            framerate_filter = ''

        command = (
            f'cmd /c'
            f'{self.ffmpeg_path} '
            f'-i {self.input_file} '
            f'-vf "fps={frameRate},scale=512:512:force_original_aspect_ratio=decrease,format=yuva420p" '
            f'{framerate_filter} -c:v libvpx-vp9 '
            f'-pix_fmt yuva420p '
            f'-b:v {bitrate} '
            f'-crf {crf} '
            f'-deadline best '
            f'-cpu-used 0 '
            f'-y '
            f'-an '
            f'{self.output_file} '
            f'|| cmd /k"'
        )
        
        try:

            proc = subprocess.Popen(
                command,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                # creationflags=subprocess.CREATE_NEW_CONSOLE  # This pops up a new terminal window
            )
            print(task_id)
            print(proc)
            self.active_conversions[task_id]["process"] = proc
            # proc.communicate()

            def monitor_progress():
                for raw in iter(proc.stderr.readline, b''):
                    if not raw:
                        break
                    line = raw.strip()
                    print(">>", line)

                    if is_image_sequence or self.input_file.endswith(".mov"):
                        m = re.search(r"frame=\s*(\d+)", line)
                        if m and total_frames:
                            pct = min(int(m.group(1)) / total_frames * 100, 100)
                            signals.progress.emit(pct)

                    
                    else:
                        # Try to extract time from output
                        m = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
                        if m and total_duration:
                            h, m_, s = m.group(1).split(':')
                            t = int(h) * 3600 + int(m_) * 60 + float(s)
                            pct = min(t / total_duration * 100, 100)
                            signals.progress.emit(pct)

                signals.progress.emit(100.0)
            # Start progress-monitor thread
            t = threading.Thread(target=monitor_progress)
            t.start()
            t.join()
            # Wait for FFmpeg to complete
            stdout, stderr = proc.communicate()
            print('HERE1')
            signals.progress.emit(100)
            print('HERE2')
            signals.finished.emit(proc.returncode == 0)
            print('HERE3')
            del self.active_conversions[task_id]
            print('HERE4')
            if proc.returncode ==3221225786: #closed manually
                pass

            elif proc.returncode != 0:
                    last_lines = "\n".join(stderr.strip().splitlines()[-5:])
                    self.show_critical.emit(
                        "FFmpeg Error",
                        f"FFmpeg failed with error code {proc.returncode}.\n\n"
                        f"Details:\n{last_lines}"
                    )

            else:
                
                self.show_info.emit(
                    "Conversion Complete",
                    f"Converted successfully to:\n{output_f}"
                )

                print(f"Conversion successful: {output_f}")

        except Exception as e:
            self.show_critical.emit("Conversion Error", f"An error occurred during conversion:\n{e}")

        return 0
            
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    # app.setStyle('Fusion')
    # apply_stylesheet(app, theme='dark_teal.xml')
    window = MainWindow()  # or MyWidget()
    window.show()
    sys.exit(app.exec())
