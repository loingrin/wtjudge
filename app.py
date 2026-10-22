"""GUI entry point. No server or database required."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QStandardPaths, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from wtjudge import __version__
from wtjudge.gui.main_window import MainWindow
from wtjudge.gui.resources import asset_path


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("wtjudge")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("wtjudge")
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(str(asset_path("wotu.ico"))))
    translator = QTranslator(app)
    if translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    log_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[RotatingFileHandler(log_dir / "wtjudge.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
