"""Top-level launcher (used by PyInstaller and as a convenience entry script).

In development the regular `python -m pr2_editor` works because the package is
visible on sys.path. PyInstaller, however, runs the analysed script outside any
package context, so a relative import inside ``pr2_editor/__main__.py`` would
fail at startup. This file dodges the issue with an absolute import.
"""
from __future__ import annotations
import sys

from pr2_editor.app import main


if __name__ == "__main__":
    sys.exit(main())
