# Run: python tools/package_release.py (safe staging + new release directory).
from pathlib import Path
import os
import sys
from PyInstaller.config import CONF

root = Path(SPECPATH)
if Path(CONF['distpath']).resolve() != (root / 'build' / 'release').resolve():
    raise SystemExit('Refusing to overwrite release folders. Use build.bat or tools/package_release.py; staging must be build/release.')
# Keep unrelated image/PDF toolchains on the developer's PATH from shadowing
# Windows ICU/UCRT during dependency discovery. Qt uses the Windows ICU API.
windows_root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
os.environ['PATH'] = os.pathsep.join([
    str(Path(sys.executable).parent), str(Path(sys.base_prefix)),
    str(Path(sys.base_prefix) / 'DLLs'), str(windows_root / 'System32'), str(windows_root),
])
a = Analysis(
    [str(root / 'app.py')], pathex=[str(root)], binaries=[], datas=[(str(root / 'assets'), 'assets')],
    hiddenimports=[],
    excludes=['numpy', 'pandas', 'scipy', 'matplotlib', 'PIL', 'tkinter',
              'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtMultimedia', 'PySide6.QtPdf'],
    noarchive=False,
)
# Windows 10/11 provide these OS components. In particular an unrelated
# icuuc.dll with version-suffixed exports is incompatible with Qt's system ICU.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {'icuuc.dll', 'ucrtbase.dll'}
              and not Path(entry[0]).name.lower().startswith(('api-ms-win-', 'ext-ms-win-', 'icudt'))]
# This Widgets application does not use Qt's on-screen virtual keyboard or QML.
# QtGui's generic plugin collection can otherwise pull in that optional plugin
# and a complete Quick/QML stack. Keep ordinary Windows input and IME support;
# exclude only the unused virtual-keyboard plugin and its unused Qt modules.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {'qt6virtualkeyboard.dll', 'qtvirtualkeyboardplugin.dll', 'qpdf.dll', 'opengl32sw.dll'}
              and not Path(entry[0]).name.lower().startswith(('qt6qml', 'qt6quick', 'qt6pdf'))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='wtjudge', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets' / 'wotu.ico'),
          version=str(root / 'version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='wtjudge')
