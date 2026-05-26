"""Application entrypoint: creates QApplication, Store, MainWindow."""
from __future__ import annotations
import sys

from PySide6 import QtGui, QtWidgets

from . import APP_NAME
from .constants import APP_ICON_PATH
from .main_window import MainWindow
from .store import Store
from .style import APP_STYLESHEET


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(APP_STYLESHEET)
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QtGui.QIcon(str(APP_ICON_PATH)))
    store = Store()
    win = MainWindow(store)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
