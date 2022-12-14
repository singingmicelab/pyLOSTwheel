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
import serial.tools.list_ports

import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtCore import QSize, Signal, QThread
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QToolBar, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QDialog, QDialogButtonBox, QFileDialog, QLineEdit, QComboBox

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

def get_arduinos_port_sn():
    """Get the port name and serial number of all connected arduinos"""

    arduinos = []

    ports = serial.tools.list_ports.comports()
    for port in ports:
        if 'Arduino' in port.description:
            arduinos.append((port.name, port.serial_number))
    
    return arduinos

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
            self.buffer_size = window_size
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
        self.current_bin = np.zeros((1, self.n_dim), dtype=np.float64)

    def reset(self):
        SlidingWindow.reset(self)
        self.current_sample_count = 0
        self.current_bin = np.zeros((1, self.n_dim), dtype=np.float64)

    def append(self, value):
        # print(self.n, len(self.data), self.current_sample_count, self.current_bin[0,2])
        if self.n == len(self.data):
            # Buffer is full.
            # Make room.
            copy_size = self.window_size - 1
            self.data[:copy_size,:] = self.data[-copy_size:,:]
            self.n = copy_size
        
        self.current_sample_count += 1
        self.current_bin += value

        if self.current_sample_count == self.sum_window_size:
            self.data[self.n] = self.current_bin
            self.n += 1
            self.current_sample_count = 0
            self.current_bin = np.zeros((1, self.n_dim), dtype=np.float64)


class AcquisitionGraphWidget(QWidget):
    """A Widget that has two plots and updates its data based on QThread
    
    """
    def __init__(self, acquisitionThread, id, arduinoInfo, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.acquisitionThread = acquisitionThread
        self.id = id
        self.arduinoInfo = arduinoInfo

        self.fs = 5

        # add label for id and port
        self.label = QLabel(f'{self.id} - {self.arduinoInfo[0]} ({self.arduinoInfo[1]})')

        # the three dimensions are: pc_timestamp, ar_timestamp, value
        self.dataWindowSize = 60*self.fs # 60 seconds
        self.dataWindow = SlidingWindow(self.dataWindowSize, 3)

        self.sumWindowSize = 60*self.fs # 1 point every 60 seconds
        self.sumDataWindowSize = 120 # 2 hours
        self.dataSumWindow = SlidingSumWindow(self.sumDataWindowSize, self.sumWindowSize, 3)

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
            xlim_l = 0
            xlim_r = self.dataWindowSize/self.fs
        else:
            self.ax1.plot(w[:,1], w[:,2])
            xlim_l = w[0,1]
            xlim_r = w[0,1]+self.dataWindowSize/self.fs
        self.ax1.set_xlim([xlim_l, xlim_r])
        self.ax1.set_xticks([int((xlim_l+xlim_r)/2)])
        # self.ax1.set_xlabel('current second')
        self.ax1.set_ylabel('counts')
        self.ax1.set_ylim([0,8])
        self.ax1.set_yticks(range(0,10,2))
        self.ax1.set_title('current minute')

        self.ax2.clear()
        if w_sum.size == 0:
            xlim_l = time.time()
            xlim_r = xlim_l+self.sumDataWindowSize*self.sumWindowSize/self.fs
        else:
            time_bincenter = w_sum[:,0] / self.sumWindowSize
            self.ax2.bar(time_bincenter, w_sum[:,2], width=self.sumWindowSize/self.fs)
            xlim_l = time_bincenter[0] - 0.5*self.sumWindowSize/self.fs
            xlim_r = time_bincenter[0] + self.sumDataWindowSize*self.sumWindowSize/self.fs - 0.5*self.sumWindowSize/self.fs
        self.ax2.set_xlim([xlim_l, xlim_r])
        self.ax2.set_xticks([xlim_l, xlim_r])
        self.ax2.set_xticklabels([datetime.fromtimestamp(xlim_l).strftime('%H:%M'), datetime.fromtimestamp(xlim_r).strftime('%H:%M')])
        self.ax2.set_ylabel('counts in chunk')
        self.ax2.set_ylim([0,800])
        self.ax2.set_title('recent history')

        self.canvas.draw()

class Experiment:
    """A class that organizes an acquisition wheel experiment
    
    """

    def __init__(self, id, arduinoInfo, basePath):

        self.id = id
        self.arduinoInfo = arduinoInfo
        self.port = self.arduinoInfo[0]
        self.sn = self.arduinoInfo[1]
        self.basePath = basePath

        self.arduino = None
        self.fileHandle = None

        # add wheel measurement thread
        self.acquisitionThread = LOSTwheelAcquisitionThread()

        # add acquisition graph
        self.acquisitionGraphWidget = AcquisitionGraphWidget(self.acquisitionThread, self.id, self.arduinoInfo)

    def startMonitor(self):

        # reset graph widget
        self.acquisitionGraphWidget.reset()
        self.acquisitionThread.disableWriting()

        # start serial connection
        self.arduino = serial.Serial(port=self.port, baudrate=9600)
        # start acquisition thread
        self.acquisitionThread.setArduino(self.arduino)
        self.acquisitionThread.start()

    def startRecord(self):

        # reset graph widget
        self.acquisitionGraphWidget.reset()
        
        # start serial connection
        self.arduino = serial.Serial(port=self.port, baudrate=9600)
        # start writer
        self.fileHandle = open(os.path.join(self.basePath, f"{self.id}_{self.sn}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"), 'w')
        self.fileHandle.write('pc_timestamp,arduino_timestamp,count\n')
        self.acquisitionThread.enableWriting(self.fileHandle)
        # start acquisition thread
        self.acquisitionThread.setArduino(self.arduino)
        self.acquisitionThread.start()


    def stop(self, guiState):

        # stop acquisition thread
        self.acquisitionThread.requestInterruption()
        self.acquisitionThread.wait()

        self.arduino.close()
        self.arduino = None
        self.acquisitionThread.setArduino(None)
        if guiState == GuiState.RECORD:
            self.fileHandle.close()
            self.fileHandle = None
            self.acquisitionThread.disableWriting()

    def __str__(self):
        return f'Experiment: {self.id}; Port: {self.port}; SN: {self.sn}'



class SettingsDialog(QDialog):
    """Dialog to control settings
    
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Settings")
        self.setMinimumSize(QSize(400,100))

        # properties
        self.defaultBasePath = os.path.join(os.path.expanduser('~'), 'Desktop')
        self.basePath = self.defaultBasePath
        self.arduinos = get_arduinos_port_sn()

        self.expInfo = []

        self.experimentWidgets = []
        self.experimentIdWidgets = []
        self.experimentArduinoWidgets = []

        # basepath subwidget
        self.basePathWidget = QWidget()
        self.basePathSelectLabel = QLabel(self.defaultBasePath)
        self.basePathSelectButton = QPushButton('Select')
        self.basePathSelectButton.clicked.connect(self.selectFile)
        self.basePathSelectButton.setFixedSize(50,23)
        basePathWidgetLayout = QHBoxLayout()
        basePathWidgetLayout.addWidget(self.basePathSelectLabel)
        basePathWidgetLayout.addWidget(self.basePathSelectButton)
        self.basePathWidget.setLayout(basePathWidgetLayout)

        # experiment subwidget
        for i in range(4):
            experimentWidget = QWidget()
            experimentWidgetLayout = QGridLayout()
            experimentIdWidget = QLineEdit('')
            experimentIdWidget.setFixedSize(100,23)
            experimentArduinoWidget = QComboBox()
            experimentArduinoWidget.addItem(None)
            experimentArduinoWidget.addItems([f'{arduino[0]} ({arduino[1]})' for arduino in self.arduinos])
            experimentWidgetLayout.addWidget(QLabel('id'), 0, 0)
            experimentWidgetLayout.addWidget(QLabel('Port (SN)'), 0, 1)
            experimentWidgetLayout.addWidget(experimentIdWidget, 1, 0)
            experimentWidgetLayout.addWidget(experimentArduinoWidget, 1, 1)
            experimentWidget.setLayout(experimentWidgetLayout)
            
            self.experimentWidgets.append(experimentWidget)
            self.experimentIdWidgets.append(experimentIdWidget)
            self.experimentArduinoWidgets.append(experimentArduinoWidget)

        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.basePathWidget)
        for experimentWidget in self.experimentWidgets:
            self.layout.addWidget(experimentWidget)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def selectFile(self):
        fname = QFileDialog.getExistingDirectory(self, 'Select BasePath', self.defaultBasePath)
        self.basePath = fname
        self.basePathSelectLabel.setText(fname)

    def accept(self):
        """override accept to validate input"""
        self.expInfo = []
        expIds = []
        expArduinos = []

        for i in range(4):
            expId = self.experimentIdWidgets[i].text()
            expArduinoIdx = self.experimentArduinoWidgets[i].currentIndex()-1
            if expId != '' and expArduinoIdx != -1:
                self.expInfo.append((expId, self.arduinos[expArduinoIdx]))
                expIds.append(expId)
                expArduinos.append(expArduinoIdx)
                
        if self.basePath != '' and len(self.expInfo) > 0 and len(self.expInfo) == len(set(expIds)) and len(self.expInfo) == len(set(expArduinos)):
            super().accept()

        

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
        self.setMinimumSize(QSize(800,500))

        # set initial state
        self.guiState = GuiState.IDLE

        # default basepath
        self.defaultBasePath = os.path.join(os.path.expanduser('~'), 'Desktop')

        # initialize gui
        self._createActions()
        self._createMenuBar()
        self._createToolBar()
        self._createStatusBar()

        self.basePath = None
        self.expInfo = []
        self.experiments = []


    def _createActions(self):
        """Create actions
        
        """
        # self.loadSettingsAction = QAction('Load Settings', self)
        # self.saveSettingsAction = QAction('Save Settings', self)

        self.exitAction = QAction('Exit', self)
        self.exitAction.setShortcut('Ctrl+Q')
        self.exitAction.triggered.connect(self.close)


    def _createMenuBar(self):
        """Create menu bar and menus
        
        """
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)

        fileMenu = menubar.addMenu('File')
        # fileMenu.addAction(self.loadSettingsAction)
        # fileMenu.addAction(self.saveSettingsAction)
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
        self.monitorButton.setEnabled(False)
        self.recordButton.setEnabled(False)
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
        self.basePathLabel = QLabel(self.defaultBasePath)
        statusBar.addPermanentWidget(self.basePathLabel)

    def monitorButtonClicked(self):
        print('start monitoring!')
        self.monitorButton.setEnabled(False)
        self.recordButton.setEnabled(False)
        self.stopButton.setEnabled(True)
        self.settingsButton.setEnabled(False)

        self.guiState = GuiState.MONITOR
        self.statusLabel.setText('Monitoring')

        for experiment in self.experiments:
            experiment.startMonitor()

    def recordButtonClicked(self):
        print('start recording!')
        self.monitorButton.setEnabled(False)
        self.recordButton.setEnabled(False)
        self.stopButton.setEnabled(True)
        self.settingsButton.setEnabled(False)

        self.guiState = GuiState.RECORD
        self.statusLabel.setText('Recording')

        for experiment in self.experiments:
            experiment.startRecord()

    def stopButtonClicked(self):
        print('stop!')
        self.monitorButton.setEnabled(True)
        self.recordButton.setEnabled(True)
        self.stopButton.setEnabled(False)
        self.settingsButton.setEnabled(True)

        for experiment in self.experiments:
            experiment.stop(self.guiState)

        self.guiState = GuiState.IDLE
        self.statusLabel.setText('Ready')

    def settingsButtonClicked(self):
        print('open settings')
        settingsDialog = SettingsDialog(self)
        if settingsDialog.exec():
            print("Settings updated!")
            self.basePath = settingsDialog.basePath

            self.expInfo = settingsDialog.expInfo
            self.experiments = []

            self.basePathLabel.setText(self.basePath)
            self.monitorButton.setEnabled(True)
            self.recordButton.setEnabled(True)

            # create experiment
            for i in range(len(self.expInfo)):
                id = self.expInfo[i][0]
                arduinoInfo = self.expInfo[i][1]
                experiment = Experiment(id, arduinoInfo, self.basePath)
                self.experiments.append(experiment)

            for experiment in self.experiments:
                print(experiment)

            # add graph widget
            centralWidget = QWidget()
            centralLayout = QVBoxLayout()
            for experiment in self.experiments:
                centralLayout.addWidget(experiment.acquisitionGraphWidget)
            centralWidget.setLayout(centralLayout)
            self.setCentralWidget(centralWidget)

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