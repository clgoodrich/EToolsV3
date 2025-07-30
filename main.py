import sys
import os
from PyQt5.QtWidgets import QApplication, QDialog

from src.mainProject import ETools
import traceback

# Add the src directory to Python path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
# Set up the environment
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'


def except_hook(cls: type, exception: Exception, tb) -> None:
    """Enhanced exception handler for debugging Qt applications.

    This custom exception handler provides detailed error information
    without calling the default handler, preventing error cascades.

    Args:
        cls: Exception class
        exception: Exception instance
        tb: Traceback object
    """

    traceback.print_tb(tb)

def main():
    sys.excepthook = except_hook

    # Create Qt application
    app = QApplication(sys.argv)

    # Create main window
    w = ETools()

    # Show window
    w.show()

    # Run application event loop
    sys.exit(app.exec_())



if __name__ == '__main__':
    main()