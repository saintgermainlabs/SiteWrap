"""Website view: QWebEngineView with a persistent per-site profile, optional toolbar, error page, downloads.

Copied from ToolBox modules/web/widget.py (not imported) and adapted for standalone windows."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from sitewrap import sites as websites

ZOOM_STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]


def make_profile(site_id: str, parent=None, user_agent: str = "") -> QWebEngineProfile:
    """Named (on-disk) profile: cookies/logins persist across restarts. Dir is private (0700)."""
    root = websites.data_dir(site_id)
    for d in (root, root / "cache"):
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    os.chmod(root.parent, 0o700)
    prof = QWebEngineProfile(f"sitewrap-{site_id}", parent)
    prof.setPersistentStoragePath(str(root))
    prof.setCachePath(str(root / "cache"))
    prof.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    prof.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
    prof.setHttpCacheMaximumSize(50 * 1024 * 1024)
    if user_agent:
        prof.setHttpUserAgent(user_agent)
    return prof


def error_html(url: str, detail: str = "") -> str:
    host = urlparse(url).hostname or url
    hint = ""
    if host.endswith(".ts.net"):
        hint = ("<p>This is a tailnet address. Is Tailscale up? Check with <code>tailscale status</code>, "
                "then retry.</p>")
    return f"<h3>Couldn't load {host}</h3><p>{detail}</p>{hint}"


class WebWidget(QWidget):
    def __init__(self, site_id: str, url: str, name: str = "", status_bar=None, downloads: Path = None,
                 toolbar: bool = True, user_agent: str = "", zoom: float = 1.0):
        super().__init__()
        self.site_id, self.home_url, self.name = site_id, url, name or site_id
        self.status_bar = status_bar
        self.downloads = Path(downloads or Path.home() / "Downloads")
        self.last_error = ""
        self.downloaded = []
        self.profile = make_profile(site_id, self, user_agent)
        self.profile.downloadRequested.connect(self._on_download)
        self.view = QWebEngineView(self)
        self.page = QWebEnginePage(self.profile, self.view)   # default: invalid TLS certs are rejected
        self.view.setPage(self.page)
        # TLS verification is never disabled: every certificate error is rejected and shown.
        self.page.certificateError.connect(self._on_cert_error)

        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        bar = QHBoxLayout(); bar.setContentsMargins(4, 4, 4, 0)

        def btn(text, tip, slot):
            b = QToolButton(); b.setText(text); b.setToolTip(tip); b.clicked.connect(slot); bar.addWidget(b)
            return b
        self.back_btn = btn("◀", "Back", self.view.back)
        self.fwd_btn = btn("▶", "Forward", self.view.forward)
        self.reload_btn = btn("⟳", "Reload", self.view.reload)
        self.home_btn = btn("🏠", "Home", self.go_home)
        self.url_edit = QLineEdit(url); self.url_edit.returnPressed.connect(self._navigate_typed)
        bar.addWidget(self.url_edit, 1)
        btn("−", "Zoom out", lambda: self.zoom(-1))
        self.zoom_label = QLabel("100%"); bar.addWidget(self.zoom_label)
        btn("+", "Zoom in", lambda: self.zoom(1))
        btn("📋", "Copy URL", self.copy_url)
        btn("↗", "Open in external browser", self.open_external)
        self.toolbar = QWidget(); self.toolbar.setLayout(bar); lay.addWidget(self.toolbar)
        self.toolbar.setVisible(bool(toolbar))

        self.stack = QStackedWidget()
        self.stack.addWidget(self.view)
        err = QWidget(); el = QVBoxLayout(err); el.addStretch(1)
        self.error_label = QLabel(); self.error_label.setWordWrap(True); self.error_label.setTextFormat(Qt.RichText)
        self.error_label.setAlignment(Qt.AlignCenter)
        self.retry_btn = QPushButton("🔄 Retry"); self.retry_btn.clicked.connect(self.retry)
        el.addWidget(self.error_label); el.addWidget(self.retry_btn, 0, Qt.AlignCenter); el.addStretch(1)
        self.stack.addWidget(err)
        self.loading = QLabel(""); self.loading.setStyleSheet("color:#a6adc8; padding: 0 6px;")
        lay.addWidget(self.loading)
        lay.addWidget(self.stack, 1)

        self.view.urlChanged.connect(lambda u: self.url_edit.setText(u.toString()))
        self.view.loadStarted.connect(lambda: self.loading.setText("Loading…"))
        self.view.loadProgress.connect(lambda p: self.loading.setText(f"Loading… {p}%") if p < 100 else None)
        self.view.loadFinished.connect(self._on_loaded)
        self.page.renderProcessTerminated.connect(
            lambda *_: self._show_error(self.view.url().toString() or self.home_url, "The page process stopped."))
        self.base_zoom = float(zoom or 1.0)
        self.view.setZoomFactor(self.base_zoom); self.zoom_label.setText(f"{round(self.base_zoom * 100)}%")
        self.go_home()

    # navigation
    def go_home(self):
        self.load(self.home_url)

    def load(self, url: str):
        self.stack.setCurrentIndex(0)
        self.view.load(QUrl.fromUserInput(url))

    def retry(self):
        self.load(self.url_edit.text() or self.home_url)

    def _navigate_typed(self):
        self.load(self.url_edit.text().strip())

    def _on_loaded(self, ok: bool):
        self.loading.setText("")
        if ok:
            self.last_error = ""
            self.stack.setCurrentIndex(0)
            self._status(f"{self.name}: {self.view.title()}")
        else:
            self._show_error(self.view.url().toString() or self.home_url, "The site did not respond or refused the connection.")

    def _show_error(self, url, detail):
        self.last_error = error_html(url, detail)
        self.error_label.setText(self.last_error)
        self.stack.setCurrentIndex(1)
        self._status(f"⚠️ {self.name}: failed to load")

    def _on_cert_error(self, err):
        err.rejectCertificate()
        self.cert_errors = getattr(self, "cert_errors", 0) + 1
        self._show_error(err.url().toString(), f"Invalid TLS certificate: {err.description()} (never bypassed).")

    # toolbar actions
    def zoom(self, step: int):
        cur = self.view.zoomFactor()
        i = min(range(len(ZOOM_STEPS)), key=lambda k: abs(ZOOM_STEPS[k] - cur))
        f = ZOOM_STEPS[max(0, min(len(ZOOM_STEPS) - 1, i + step))]
        self.view.setZoomFactor(f); self.zoom_label.setText(f"{round(f * 100)}%")

    def current_url(self) -> str:
        return self.view.url().toString() or self.home_url

    def copy_url(self):
        QGuiApplication.clipboard().setText(self.current_url())
        self._status("URL copied")

    def open_external(self):
        QDesktopServices.openUrl(QUrl(self.current_url()))

    def _on_download(self, d: QWebEngineDownloadRequest):
        self.downloads.mkdir(parents=True, exist_ok=True)
        d.setDownloadDirectory(str(self.downloads))
        d.accept()
        self.downloaded.append(d.downloadFileName())
        self._status(f"⬇ Downloading {d.downloadFileName()} → {self.downloads}")

    def _status(self, msg):
        if self.status_bar is not None:
            self.status_bar.showMessage(msg, 6000)

    def shutdown(self):
        # Page must go before its profile, or Qt warns and may leak the renderer.
        try:
            self.view.stop()
            self.view.setPage(None)
            import shiboken6
            shiboken6.delete(self.page)
        except RuntimeError:
            pass

