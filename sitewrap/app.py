"""`webapp <id>`: one site in its own window, with its own name, icon, dock identity and profile."""
from __future__ import annotations

import os
import signal
import sys

# Keep QtWebEngine light: one renderer, share per site, no GPU compositing, small disk cache.
# (Same flags as ToolBox.) Must be set before QtWebEngine is imported.
CHROMIUM_FLAGS = ("--renderer-process-limit=1 --process-per-site --disable-gpu-compositing "
                  "--enable-low-end-device-mode --disk-cache-size=52428800")


def usage(sites, errors) -> str:
    lines = ["usage: webapp            (dashboard)", "       webapp <id>       (open one site)",
             "       webapp --list", "", "sites:"]
    lines += [f"  {s.id:<14} {s.name} — {s.url}" for s in sites]
    lines += [f"  (skipped) {e}" for e in errors]
    return "\n".join(lines)


def build_window(site, downloads=None):
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon, QKeySequence, QShortcut
    from PySide6.QtWidgets import QMainWindow
    from sitewrap import sites as S
    from sitewrap.web import WebWidget

    w = QMainWindow()
    w.setWindowTitle(site.name)
    w.setWindowIcon(QIcon(str(S.resolve_icon(site))))
    w.resize(QSize(site.width, site.height))
    web = WebWidget(site.id, site.url, site.name, status_bar=w.statusBar(), downloads=downloads,
                    toolbar=site.toolbar, user_agent=site.user_agent, zoom=site.zoom)
    w.setCentralWidget(web)
    w.statusBar().setVisible(site.toolbar)
    web.view.titleChanged.connect(lambda t: w.setWindowTitle(f"{t} — {site.name}" if t and t != site.name else site.name))
    for keys, slot in (("Ctrl+R", web.view.reload), ("F5", web.view.reload), ("Alt+Left", web.view.back),
                       ("Alt+Right", web.view.forward), ("Alt+Home", web.go_home), ("Ctrl++", lambda: web.zoom(1)),
                       ("Ctrl+=", lambda: web.zoom(1)), ("Ctrl+-", lambda: web.zoom(-1)),
                       ("Ctrl+L", lambda: (web.toolbar.setVisible(True), web.url_edit.setFocus(), web.url_edit.selectAll())),
                       ("Ctrl+Shift+B", lambda: web.toolbar.setVisible(not web.toolbar.isVisible())),
                       ("Ctrl+Q", w.close)):
        sc = QShortcut(QKeySequence(keys), w); sc.activated.connect(slot)
    w.web = web
    orig_close = w.closeEvent

    def close_event(e):
        web.shutdown(); orig_close(e)
    w.closeEvent = close_event
    return w


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    from sitewrap import sites as S
    sites, errors = S.load()
    if not argv or argv[0] == "--dashboard":
        from sitewrap.dashboard import main as dashboard_main
        return dashboard_main()
    if argv[0] in ("-h", "--help", "--list"):
        print(usage(sites, errors)); return 0
    sid = argv[0]
    site = next((s for s in sites if s.id == sid), None)
    if site is None:
        print(f"webapp: unknown site {sid!r}\n\n" + usage(sites, errors), file=sys.stderr); return 2
    from sitewrap import instance
    if instance.send(sid, "raise") == "raised":           # already open: focus it, no duplicate
        print(f"webapp: {sid} is already open; raised it"); return 0

    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", CHROMIUM_FLAGS)
    from PySide6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    import PySide6.QtWebEngineWidgets  # noqa: F401  (before QApplication)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QGuiApplication, QIcon

    # Dock identity: Wayland app_id = desktop file name; X11 WM_CLASS = (-name, applicationName).
    app = QApplication([site.app_id, "-name", site.app_id])
    QGuiApplication.setApplicationName(site.app_id)
    QGuiApplication.setDesktopFileName(site.app_id)
    QGuiApplication.setWindowIcon(QIcon(str(S.resolve_icon(site))))
    w = build_window(site)

    def raise_window():
        if w.isMinimized():
            w.showNormal()
        w.show(); w.raise_(); w.activateWindow()
    w._instance = instance.serve(sid, raise_window, w)
    if w._instance is None and instance.send(sid, "raise") == "raised":   # lost a start race
        return 0
    signal.signal(signal.SIGTERM, lambda *_: w.close())
    signal.signal(signal.SIGINT, lambda *_: w.close())
    from PySide6.QtCore import QTimer
    t = QTimer(); t.start(500); t.timeout.connect(lambda: None)   # let Python see signals
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
