"""Application entrypoint: creates QApplication, Store, MainWindow."""
from __future__ import annotations
import sys

from PySide6 import QtWidgets

from . import APP_NAME
from .main_window import MainWindow
from .store import Store
from .style import APP_STYLESHEET


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(APP_STYLESHEET)
    store = Store()
    win = MainWindow(store)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
