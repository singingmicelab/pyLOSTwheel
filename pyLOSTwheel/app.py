"""
    app.py
    GUI application to acquire LOSTwheel data

    references:
    https://github.com/sidneycadot/pyqt-and-graphing/blob/master/PyQtGraphing.py

"""

import time
from datetime import datetime
import sys
import numpy as np
from enum import Enum
import os
import serial

import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtCore import QSize, Signal, QThread
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QToolBar, QPushButton, QVBoxLayout, QLabel, QDialog, QDialogButtonBox, QLineEdit

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class GuiState(Enum):
    """Define the possible state of the gui"""
    IDLE = 1
    MONITOR = 2
    RECORD = 3

class LOSTwheelAcquisitionThread(QThread):
    """Use a QThread to capture sensor data

    """

    measurement = Signal(float, float, int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.arduino = None

        self.isWriting = False
        self.fileHandle = None

    def setArduino(self, arduino):
        self.arduino = arduino

    def enableWriting(self, fileHandle):
        self.isWriting = True
        self.fileHandle = fileHandle

    def disableWriting(self):
        self.isWriting = False
        self.fileHandle = None

    def run(self):
        while not self.isInterruptionRequested() and self.arduino is not None:
            line = self.arduino.readline()
            pc_timestamp = time.time()
            arduino_timestamp, count = line.decode().strip().split(',')
            arduino_timestamp = float(arduino_timestamp)
            count = int(count)
            if self.isWriting:
                print('writing', (pc_timestamp, arduino_timestamp, count))
                self.fileHandle.write(f'{pc_timestamp},{arduino_timestamp},{count}\n')
            self.measurement.emit(pc_timestamp, arduino_timestamp, count)

class SlidingWindow:
    """A SlidingWindow gives access to the 'window_size' most recent values that were appended to it."""

    def __init__(self, window_size, n_dim, buffer_size=None):
        if buffer_size is None:
            self.buffer_size = 5 * window_size
        else:
            self.buffer_size = buffer_size
        self.n_dim = n_dim
        self.data = np.zeros((self.buffer_size, self.n_dim), dtype=np.float64)
        self.n = 0
        self.window_size = window_size

    def reset(self):
        """Reset the SlidingWindow"""
        self.data = np.zeros((self.buffer_size, self.n_dim), dtype=np.float64)
        self.n = 0

    def append(self, value):
        """Append a value to the sliding window."""
        if self.n == len(self.data):
            # Buffer is full.
            # Make room.
            copy_size = self.window_size - 1
            self.data[:copy_size,:] = self.data[-copy_size:,:]
            self.n = copy_size

        self.data[self.n,:] = value
        self.n += 1

    def window(self):
        """Get a window of the most recent 'window_size' samples (or less if not available.)"""
        return self.data[max(0, self.n - self.window_size):self.n,:]

class SlidingSumWindow(SlidingWindow):
    """Inherits SlidingWindow. Instead of displaying every new value, display the sum of sum_window_size new values"""

    def __init__(self, window_size, sum_window_size, n_dim, buffer_size=None):
        
        SlidingWindow.__init__(self, window_size, n_dim, buffer_size)

        self.sum_window_size = sum_window_size
        self.current_sample_count = 0

    def reset(self):
        SlidingWindow.reset(self)
        self.current_sample_count = 0

    def append(self, value):
        if self.n == len(self.data):
            # Buffer is full.
            # Make room.
            copy_size = self.window_size - 1
            self.data[:copy_size] = self.data[-copy_size:,:]
            self.data[-1,:] = 0
            self.n = copy_size
        
        self.data[self.n] += value
        self.current_sample_count += 1

        if self.current_sample_count == self.sum_window_size:
            self.current_sample_count = 0
            self.n += 1


class AcquisitionGraphWidget(QWidget):
    """A Widget that has two plots and updates its data based on QThread
    
    """
    def __init__(self, acquisitionThread, id, port, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.acquisitionThread = acquisitionThread
        self.id = id
        self.port = port

        # add label for id and port
        self.label = QLabel(f'{self.id} - {self.port}')

        # the three dimensions are: pc_timestamp, ar_timestamp, value
        self.windowSize = 60 # seconds
        self.dataWindow = SlidingWindow(self.windowSize, 3)

        self.sumWindowSize = 60 # 1 point every 60 seconds
        self.dataSumWindow = SlidingSumWindow(self.windowSize, self.sumWindowSize, 3)

        fig = Figure()
        fig.set_layout_engine('tight')
        self.ax1 = fig.add_subplot(121)
        self.ax2 = fig.add_subplot(122)
        self.canvas = FigureCanvas(fig)
        self.updateGraph()

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        self.acquisitionThread.measurement.connect(self.handleMeasurement)

    def reset(self):
        """reset the slidingwindow and the graph"""
        self.dataWindow.reset()
        self.dataSumWindow.reset()
        self.updateGraph()

    def handleMeasurement(self, pc_timestamp, arduino_timestamp, value):
        """Receive a timestamped value and update the graph
        
        """

        print('graphing', (pc_timestamp, arduino_timestamp, value))
        self.dataWindow.append((pc_timestamp, arduino_timestamp, value))
        self.dataSumWindow.append((pc_timestamp, arduino_timestamp, value))

        self.updateGraph()

    def updateGraph(self):
        """Update graph"""

        w = self.dataWindow.window()
        w_sum = self.dataSumWindow.window()

        self.ax1.clear()
        if w.size == 0:
            self.ax1.set_xlim([1, 1+self.windowSize])
        else:
            self.ax1.plot(w[:,1], w[:,2])
            self.ax1.set_xlim([w[0,1], w[0,1]+self.windowSize])
        self.ax1.set_xlabel('current minute')
        self.ax1.set_xticks([])
        self.ax1.set_ylabel('counts')
        self.ax1.set_ylim([0,18])
        self.ax1.set_yticks(range(0,20,2))

        self.ax2.clear()
        if w_sum.size == 0:
            xlim_l = time.time()
            xlim_r = xlim_l+self.sumWindowSize*self.windowSize
        else:
            time_bincenter = w_sum[:,0] / self.sumWindowSize - 0.5*self.sumWindowSize
            self.ax2.bar(time_bincenter, w_sum[:,2], width=self.sumWindowSize)
            xlim_l = time_bincenter[0]
            xlim_r = time_bincenter[0]+self.sumWindowSize*self.windowSize
        self.ax2.set_xlim([xlim_l-0.5*self.sumWindowSize, xlim_r+0.5*self.sumWindowSize])
        self.ax2.set_xticks([xlim_l, xlim_r])
        self.ax2.set_xticklabels([datetime.fromtimestamp(xlim_l).strftime('%H:%M'), datetime.fromtimestamp(xlim_r).strftime('%H:%M')])
        self.ax2.set_ylabel('counts in chunk')
        self.ax2.set_ylim([0,800])

        self.canvas.draw()

class SettingsDialog(QDialog):
    """Dialog to control settings
    
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Settings")

        self.idLineEdit = QLineEdit('id')

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.idLineEdit)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

class MainWindow(QMainWindow):
    """The pyLOSTwheel GUI application.

    """
    
    def __init__(self, *args, **kwargs):
        """Initialize the app.

        """
        super(MainWindow, self).__init__(*args, **kwargs)

        # set window title
        self.setWindowTitle('pyLOSTwheel')
        # set window size
        self.setMinimumSize(QSize(800,400))

        # set initial state
        self.guiState = GuiState.IDLE

        # set arduino
        self.id = 'test'
        self.port = 'COM3'
        self.arduino = None
        # set file base path
        self.basePath = 'C:/Users/martin/Desktop/'
        self.fileHandle = None

        # initialize gui
        self._createActions()
        self._createMenuBar()
        self._createToolBar()
        self._createStatusBar()

        # add wheel measurement thread
        self.acquisitionThread = LOSTwheelAcquisitionThread()

        # add acquisition graph
        self.acquisitionGraphWidget = AcquisitionGraphWidget(self.acquisitionThread, self.id, self.port)
        self.setCentralWidget(self.acquisitionGraphWidget)


    def _createActions(self):
        """Create actions
        
        """
        self.loadSettingsAction = QAction('Load Settings', self)
        self.saveSettingsAction = QAction('Save Settings', self)

        self.exitAction = QAction('Exit', self)
        self.exitAction.setShortcut('Ctrl+Q')
        self.exitAction.triggered.connect(self.close)


    def _createMenuBar(self):
        """Create menu bar and menus
        
        """
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)

        fileMenu = menubar.addMenu('File')
        fileMenu.addAction(self.loadSettingsAction)
        fileMenu.addAction(self.saveSettingsAction)
        fileMenu.addAction(self.exitAction)


    def _createToolBar(self):
        """Create tool bar and tools
        
        """
        toolbar = QToolBar('main toolbar')
        toolbar.setMovable(False)
        toolbar.toggleViewAction().setEnabled(False)
        self.addToolBar(toolbar)

        # add buttons
        self.monitorButton = QPushButton('Monitor')
        self.recordButton = QPushButton('Record')
        self.stopButton = QPushButton('Stop')
        self.settingsButton = QPushButton('Settings')
        self.stopButton.setEnabled(False)
        self.monitorButton.clicked.connect(self.monitorButtonClicked)
        self.recordButton.clicked.connect(self.recordButtonClicked)
        self.stopButton.clicked.connect(self.stopButtonClicked)
        self.settingsButton.clicked.connect(self.settingsButtonClicked)
        toolbar.addWidget(self.monitorButton)
        toolbar.addWidget(self.recordButton)
        toolbar.addWidget(self.stopButton)
        toolbar.addWidget(self.settingsButton)

    def _createStatusBar(self):
        """create status bar

        """
        statusBar = self.statusBar()
        # status widget
        self.statusLabel = QLabel('Ready')
        statusBar.addWidget(self.statusLabel)
        # basepath widget
        self.basePathLabel = QLabel(self.basePath)
        statusBar.addPermanentWidget(self.basePathLabel)

    def monitorButtonClicked(self):
        print('start monitoring!')
        self.monitorButton.setEnabled(False)
        self.recordButton.setEnabled(False)
        self.stopButton.setEnabled(True)
        self.settingsButton.setEnabled(False)

        self.guiState = GuiState.MONITOR
        self.statusLabel.setText('Monitoring')

        # reset graph widget
        self.acquisitionGraphWidget.reset()
        self.acquisitionThread.disableWriting()

        # start serial connection
        self.arduino = serial.Serial(port=self.port, baudrate=9600)
        # start acquisition thread
        self.acquisitionThread.setArduino(self.arduino)
        self.acquisitionThread.start()

    def recordButtonClicked(self):
        print('start recording!')
        self.monitorButton.setEnabled(False)
        self.recordButton.setEnabled(False)
        self.stopButton.setEnabled(True)
        self.settingsButton.setEnabled(False)

        self.guiState = GuiState.RECORD
        self.statusLabel.setText('Recording')

        # reset graph widget
        self.acquisitionGraphWidget.reset()
        
        # start serial connection
        self.arduino = serial.Serial(port=self.port, baudrate=9600)
        # start writer
        self.fileHandle = open(os.path.join(self.basePath, f"{self.port}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"), 'w')
        self.fileHandle.write('pc_timestamp,arduino_timestamp,count\n')
        self.acquisitionThread.enableWriting(self.fileHandle)
        # start acquisition thread
        self.acquisitionThread.setArduino(self.arduino)
        self.acquisitionThread.start()

    def stopButtonClicked(self):
        print('stop!')
        self.monitorButton.setEnabled(True)
        self.recordButton.setEnabled(True)
        self.stopButton.setEnabled(False)
        self.settingsButton.setEnabled(True)

        # stop acquisition thread
        self.acquisitionThread.requestInterruption()
        self.acquisitionThread.wait()

        self.arduino.close()
        self.arduino = None
        self.acquisitionThread.setArduino(None)
        if self.guiState == GuiState.RECORD:
            self.fileHandle.close()
            self.fileHandle = None
            self.acquisitionThread.disableWriting()

        self.guiState = GuiState.IDLE
        self.statusLabel.setText('Ready')

    def settingsButtonClicked(self):
        print('open settings')
        settingsDialog = SettingsDialog(self)
        if settingsDialog.exec():
            print("Settings updated!")
        else:
            print("Settings canceled")

def main():
    """main function - entry point"""

    app = QApplication([])
    app.setApplicationName('pyLOSTwheel')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    main()