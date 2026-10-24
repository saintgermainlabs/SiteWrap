import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--renderer-process-limit=1 --process-per-site "
                      "--disable-gpu-compositing --enable-low-end-device-mode --disable-gpu")
os.environ["SITEWRAP_APPS_DIR"] = "/nonexistent/sitewrap-tests"      # never the user's launchers
os.environ["SITEWRAP_DESKTOP_DIR"] = "/nonexistent/sitewrap-tests-desktop"  # never the user's Desktop
os.environ["SITEWRAP_DATA"] = "/tmp/sitewrap-tests-data"
os.environ["SITEWRAP_CONFIG"] = "/tmp/sitewrap-tests-config"                 # never the user's dashboard state
try:  # QtWebEngine must be imported before any QApplication exists (pytest-qt creates one)
    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    import PySide6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass
