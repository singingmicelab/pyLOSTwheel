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

import matplotlib
matplotlib.use('QtAgg')

from PySide6.QtCore import QSize, QTimer, Signal, QThread
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QToolBar, QPushButton, QHBoxLayout

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

    measurement = Signal(float, float)

    def __init__(self, measurement_interval, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.measurement_interval = measurement_interval

    def run(self):
        while not self.isInterruptionRequested():
            self.measurement.emit(time.time(), time.time())
            time.sleep(self.measurement_interval)

class AcquisitionGraphWidget(QWidget):
    """A Widget that has two plots and updates its data based on QThread
    
    """
    def __init__(self, acquisitionThread, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.acquisitionThread = acquisitionThread

        fig = Figure()
        self.ax1 = fig.add_subplot(121)
        self.ax2 = fig.add_subplot(122)
        self.canvas = FigureCanvas(fig)

        layout = QHBoxLayout()
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        self.acquisitionThread.measurement.connect(self.handleMeasurement)
    
    def handleMeasurement(self, timestamp, value):
        """Receive a timestamped value and update the graph
        
        """

        print('graphing', (timestamp, value))


class AcquisitionWriter:
    """Class that handles writing data from LOSTwheel to file
    
    """

    def __init__(self, acquisitionThread, *args, **kwargs):

        self.isWriting = False
        self.fileHandle = None

        self.acquisitionThread = acquisitionThread

        self.acquisitionThread.measurement.connect(self.writeMeasurement)

    def startWriting(self, timestamp):

        print('start writing', timestamp)
        self.isWriting = True
    
    def stopWriting(self):

        print('stop writing')
        self.isWriting = False

    def writeMeasurement(self, timestamp, value):
        """Receive a timestamped value and write them to file
        
        """
        if self.isWriting:
            print('writing', (timestamp, value))



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

        # initialize gui
        self._createActions()
        self._createMenuBar()
        self._createToolBar()
        self.statusBar()

        # add wheel measurement thread
        self.acquisitionThread = LOSTwheelAcquisitionThread(1.0)

        # add acquisition graph
        self.acquisitionGraphWidget = AcquisitionGraphWidget(self.acquisitionThread)
        self.setCentralWidget(self.acquisitionGraphWidget)

        # add acquisition writer
        self.acquisitionWriter = AcquisitionWriter(self.acquisitionThread)



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
        self.stopButton.setEnabled(False)
        self.monitorButton.clicked.connect(self.monitorButtonClicked)
        self.recordButton.clicked.connect(self.recordButtonClicked)
        self.stopButton.clicked.connect(self.stopButtonClicked)
        toolbar.addWidget(self.monitorButton)
        toolbar.addWidget(self.recordButton)
        toolbar.addWidget(self.stopButton)


    def monitorButtonClicked(self):
        print('start monitoring!')
        self.monitorButton.setEnabled(False)
        self.recordButton.setEnabled(False)
        self.stopButton.setEnabled(True)

        self.guiState = GuiState.MONITOR

        # start acquisition thread
        self.acquisitionThread.start()

    def recordButtonClicked(self):
        print('start recording!')
        self.monitorButton.setEnabled(False)
        self.recordButton.setEnabled(False)
        self.stopButton.setEnabled(True)

        self.guiState = GuiState.RECORD

        # start writer
        self.acquisitionWriter.startWriting(datetime.now().strftime('%Y%m%d%H%M%S'))
        # start acquisition thread
        self.acquisitionThread.start()


    def stopButtonClicked(self):
        print('stop!')
        self.monitorButton.setEnabled(True)
        self.recordButton.setEnabled(True)
        self.stopButton.setEnabled(False)

        # stop acquisition thread
        self.acquisitionThread.requestInterruption()
        self.acquisitionThread.wait()
        # stop writer
        if self.guiState == GuiState.RECORD:
            self.acquisitionWriter.stopWriting()

        self.guiState = GuiState.IDLE


if __name__ == '__main__':

    app = QApplication([])
    app.setApplicationName('pyLOSTwheel')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())