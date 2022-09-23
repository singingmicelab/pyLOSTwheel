"""
    app.py
    GUI application to acquire LOSTwheel data
"""

import sys
import random
import matplotlib
matplotlib.use('Qt5Agg')

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar, QPushButton

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class MplCanvas(FigureCanvas):

    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)

class MainWindow(QMainWindow):
    """The pyLOSTwheel GUI application.

    """
    
    def __init__(self, *args, **kwargs):
        """Initialize the app.
        Args:

        """
        super(MainWindow, self).__init__(*args, **kwargs)

        # set window title
        self.setWindowTitle('pyLOSTwheel')

        # set window size
        self.setFixedSize(QSize(800,600))

        # example action
        exitAction = QAction('Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.triggered.connect(self.close)
        
        # menu bar
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)

        fileMenu = menubar.addMenu('File')
        fileMenu.addAction(exitAction)

        # tool bar
        toolbar = QToolBar("main toolbar")
        toolbar.setMovable(False)
        toolbar.toggleViewAction().setEnabled(False)
        self.addToolBar(toolbar)

        toolbar.addAction(exitAction)

        # status bar
        self.statusBar()

        # make a chart
        self.canvas = MplCanvas(self, width=5, height=4, dpi=100)
        self.setCentralWidget(self.canvas)

        n_data = 50
        self.xdata = list(range(n_data))
        self.ydata = [random.randint(0, 10) for i in range(n_data)]
        self.update_plot()

        # Setup a timer to trigger the redraw by calling update_plot.
        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

    def update_plot(self):
        # Drop off the first y element, append a new one.
        self.ydata = self.ydata[1:] + [random.randint(0, 10)]
        self.canvas.axes.cla()  # Clear the canvas.
        self.canvas.axes.plot(self.xdata, self.ydata, 'r')
        # Trigger the canvas to update and redraw.
        self.canvas.draw()




if __name__ == '__main__':

    app = QApplication([])
    app.setApplicationName("pyLOSTwheel")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())