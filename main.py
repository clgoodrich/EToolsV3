import sys
import os

# Add the src directory to Python path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up the environment
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'

from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtCore import Qt
from EToolsLimited import Ui_Dialog


def main():
    # Create the application
    app = QApplication(sys.argv)

    # Enable high DPI scaling
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Create and show the main dialog
    dialog = QDialog()
    ui = Ui_Dialog()
    ui.setupUi(dialog)
    dialog.show()

    # Start the event loop
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()