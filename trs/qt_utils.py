import os
from pathlib import Path

from PySide6 import QtCore


def configure_qt_plugins() -> None:
    # Ensure Qt can find multimedia plugins when running from a bundled Python.
    pyside_dir = Path(QtCore.__file__).resolve().parent
    plugin_dir = pyside_dir / "plugins"
    if plugin_dir.is_dir():
        QtCore.QCoreApplication.addLibraryPath(str(plugin_dir))
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_dir))
        # Keep DLL resolution happy for the FFmpeg backend shipped with PySide6.
        os.environ.setdefault("PATH", str(pyside_dir) + os.pathsep + os.environ.get("PATH", ""))
        # Windows needs explicit DLL search paths for plugin dependencies.
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(pyside_dir))
            os.add_dll_directory(str(plugin_dir))
