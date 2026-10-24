"""SiteWrap dashboard: a light PySide6 window (no QtWebEngine) with one card per site.

Tabs: ★ Shortcuts (sites with `shortcut: true`, the start page) and All (one column per category).
Click a card → `webapp <id>` as a detached process (its own systemd scope via bin/webapp); if the site
is already open, it is raised instead. Cards show a ● running indicator and a Desktop button that puts
the site's launcher on the Desktop (or takes it off). The YAML is watched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml
from PySide6.QtCore import QFileSystemWatcher, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget, QCheckBox, QComboBox, QTabWidget, QToolButton)

from sitewrap import desktop as D, instance, sites as S
from sitewrap.theme import Theme

APP_ID = "sitewrap"
ROOT = S.ROOT
CARD_W = 300


def webapp_cmd() -> list:
    env = os.environ.get("SITEWRAP_LAUNCH")            # tests: replace the launcher
    return env.split() if env else [str(ROOT / "bin" / "webapp")]


def launch_detached(site_id: str) -> subprocess.Popen:
    """New session + own scope (bin/webapp): closing the dashboard never closes site windows."""
    return subprocess.Popen(webapp_cmd() + [site_id], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)


class Card(QFrame):
    clicked = Signal(str)
    desktop_toggled = Signal(str)

    def __init__(self, site: S.Site):
        super().__init__()
        self.site = site
        self.setProperty("class", "ServiceCard"); self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor); self.setFixedSize(CARD_W, 132)
        self.setToolTip(f"Open {site.name}\n{site.url}")
        lay = QHBoxLayout(self); lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(12)
        self.icon = QLabel(); self.icon.setFixedSize(48, 48)
        self.icon.setPixmap(QIcon(str(S.resolve_icon(site))).pixmap(QSize(48, 48)))
        lay.addWidget(self.icon, 0, Qt.AlignTop)
        col = QVBoxLayout(); col.setSpacing(3)
        top = QHBoxLayout()
        self.name = QLabel(f"<b>{site.name}</b>"); self.name.setStyleSheet("font-size:15px; background:transparent;")
        self.dot = QLabel("● running"); self.dot.setStyleSheet("color:#a6e3a1; font-size:11px; background:transparent;")
        self.dot.hide()
        top.addWidget(self.name); top.addStretch(1); top.addWidget(self.dot)
        col.addLayout(top)
        self.desc = QLabel(site.description); self.desc.setWordWrap(True)
        self.desc.setStyleSheet("color:#bac2de; background:transparent;")
        self.host = QLabel(urlparse(site.url).hostname or site.url)
        self.host.setStyleSheet("color:#7f849c; font-size:11px; background:transparent;")
        self.desk = QToolButton(); self.desk.setCursor(Qt.PointingHandCursor)
        self.desk.setStyleSheet("QToolButton { border:none; background:transparent; color:#7f849c; font-size:11px; }"
                                "QToolButton:hover { color:#89b4fa; }")
        self.desk.clicked.connect(lambda: self.desktop_toggled.emit(self.site.id))
        bottom = QHBoxLayout(); bottom.addWidget(self.host); bottom.addStretch(1); bottom.addWidget(self.desk)
        col.addWidget(self.desc); col.addStretch(1); col.addLayout(bottom)
        lay.addLayout(col, 1)
        self.set_on_desktop(False)
        for w in (self.icon, self.name, self.dot, self.desc, self.host):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.running = False

    def set_on_desktop(self, on: bool):
        self.on_desktop = on
        self.desk.setText("✓ Desktop" if on else "＋ Desktop")
        self.desk.setToolTip("Remove from Desktop" if on else "Add a launcher for this site to the Desktop")

    def set_running(self, on: bool):
        self.running = on; self.dot.setVisible(on)

    def matches(self, q: str) -> bool:
        q = q.lower().strip()
        s = self.site
        return not q or any(q in str(x).lower() for x in (s.id, s.name, s.description, s.url, s.category))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.site.id)
        super().mouseReleaseEvent(e)


def state_file() -> Path:
    env = os.environ.get("SITEWRAP_CONFIG")
    d = Path(env).expanduser() if env else Path.home() / ".config" / "sitewrap"
    return d / "dashboard.json"


def load_state() -> dict:
    try:
        d = json.loads(state_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict):
    f = state_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp"); tmp.write_text(json.dumps(state, indent=2), encoding="utf-8"); os.replace(tmp, f)
    except OSError:
        pass


class Section(QWidget):
    """Collapsible category column: header (▾/▸ icon name · count), description, cards stacked vertically."""
    toggled = Signal(str, bool)

    def __init__(self, cat: S.Category, collapsed: bool = False):
        super().__init__()
        self.cat, self.collapsed, self.cards = cat, collapsed, []
        v = QVBoxLayout(self); v.setContentsMargins(0, 4, 0, 6); v.setSpacing(8)
        self.header = QToolButton(); self.header.setObjectName("sectionHeader")
        self.header.setToolButtonStyle(Qt.ToolButtonTextOnly); self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet("QToolButton#sectionHeader { border:none; background:transparent; font-size:15px;"
                                  " font-weight:bold; color:#cdd6f4; padding:2px 0; text-align:left; }"
                                  "QToolButton#sectionHeader:hover { color:#89b4fa; }")
        self.header.clicked.connect(self.toggle)
        self.desc = QLabel(cat.description); self.desc.setStyleSheet("color:#7f849c; font-size:12px;")
        self.header.setFixedHeight(28); self.desc.setFixedHeight(18); self.desc.setToolTip(cat.description); self.setFixedWidth(CARD_W)
        v.addWidget(self.header); v.addWidget(self.desc)
        self.body = QWidget(); self.grid = QGridLayout(self.body); self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12); self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        v.addWidget(self.body)
        self.visible_count = 0
        self._update_header()

    def _update_header(self):
        arrow = "▸" if self.collapsed else "▾"
        self.header.setText(f"{arrow}  {self.cat.label}  ·  {self.visible_count}")
        self.desc.setVisible(True)                     # even when empty: keeps the columns' cards aligned

    def toggle(self):
        self.set_collapsed(not self.collapsed); self.toggled.emit(self.cat.name, self.collapsed)

    def set_collapsed(self, on: bool):
        self.collapsed = on; self.body.setVisible(not on); self._update_header()

    def layout_cards(self, visible, cols=1):
        while self.grid.count():
            self.grid.takeAt(0)
        for c in self.cards:
            c.setVisible(c in visible)
        shown = [c for c in self.cards if c in visible]
        for i, c in enumerate(shown):
            self.grid.addWidget(c, i // cols, i % cols)
        self.visible_count = len(shown)
        self.body.setVisible(not self.collapsed)
        self.setVisible(bool(shown))
        self._update_header()


class AddSiteDialog(QDialog):
    def __init__(self, parent=None, categories=None):
        super().__init__(parent)
        self.setWindowTitle("Add site")
        f = QFormLayout(self)
        self.fields = {}
        for k, ph in (("id", "grafana"), ("name", "Grafana"), ("description", "Dashboards"),
                      ("url", "https://grafana.example.ts.net"), ("icon", "https://…/favicon.png or icons/x.svg")):
            e = QLineEdit(); e.setPlaceholderText(ph); self.fields[k] = e; f.addRow(k.capitalize(), e)
        self.category = QComboBox(); self.category.setEditable(True)
        self.category.setToolTip("Pick a category or type a new one")
        names = [c.name for c in (categories or [])] or [S.DEFAULT_CATEGORY]
        self.category.addItems(names)
        self.category.lineEdit().setPlaceholderText("New category…")
        f.addRow("Category", self.category)
        self.toolbar = QCheckBox("Show toolbar"); self.toolbar.setChecked(True); f.addRow("", self.toolbar)
        self.shortcut = QCheckBox("Show on the Shortcuts tab"); f.addRow("", self.shortcut)
        self.error = QLabel(""); self.error.setStyleSheet("color:#f38ba8"); self.error.setWordWrap(True)
        f.addRow(self.error)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.try_accept); bb.rejected.connect(self.reject); f.addRow(bb)

    def entry(self) -> dict:
        e = {k: w.text().strip() for k, w in self.fields.items()}
        e["toolbar"] = self.toolbar.isChecked()
        if self.shortcut.isChecked():
            e["shortcut"] = True
        cat = self.category.currentText().strip()
        if cat:
            e["category"] = cat
        return e

    def try_accept(self):
        why = add_site(self.entry(), dry_run=True)
        if why:
            self.error.setText(why); return
        self.accept()


def add_site(entry: dict, path: Path = None, dry_run: bool = False) -> str:
    """Append a site to sites.yaml (keeps comments: text append). '' on success, else the reason."""
    path = Path(path or S.sites_file())
    current, _ = S.load(path)
    why = S.validate(entry, {s.id for s in current})
    if why:
        return why
    if dry_run:
        return ""
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    tmp = path.with_suffix(".yaml.tmp")

    def ok(text):
        tmp.write_text(text, encoding="utf-8")
        new, _ = S.load(tmp)
        return entry["id"] in {s.id for s in new} and len(new) == len(current) + 1
    block = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)
    import re
    m = re.findall(r"^([ \t]*)- +id:", old, re.M)      # match the existing list indentation
    ind = m[-1] if m else "  "
    appended = old.rstrip("\n") + "\n\n" + "\n".join(ind + l if l else l for l in block.splitlines()) + "\n"
    if not (old.strip() and ok(appended)):           # text append keeps comments; else rewrite structurally
        data = yaml.safe_load(old) if old.strip() else {}
        data = data if isinstance(data, dict) else {"sites": data or []}
        data["sites"] = list(data.get("sites") or []) + [entry]
        if not ok(yaml.safe_dump(data, sort_keys=False, allow_unicode=True)):
            tmp.unlink(missing_ok=True); return "could not append safely; edit sites.yaml by hand"
    os.replace(tmp, path)
    return ""


def regenerate_launchers() -> subprocess.Popen:
    py = ROOT / ".venv" / "bin" / "python"
    return subprocess.Popen([str(py if py.exists() else sys.executable), "-m", "sitewrap.desktop", "install"],
                            cwd=str(ROOT), env=dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen"),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


class Dashboard(QMainWindow):
    def __init__(self, path: Path = None):
        super().__init__()
        self.path = Path(path or S.sites_file())
        self.setWindowTitle("SiteWrap")
        self.setWindowIcon(QIcon(str(ROOT / "icons" / "sitewrap.svg")))
        self.setStyleSheet(Theme.DARK_QSS + "\nQFrame#card { padding: 0px; }")
        self.resize(1000, 640)
        self.cards: list[Card] = []                    # All tab
        self.shortcut_cards: list[Card] = []           # ★ Shortcuts tab (same sites, separate widgets)
        self.launched = []
        central = QWidget(); self.setCentralWidget(central)
        v = QVBoxLayout(central); v.setContentsMargins(16, 14, 16, 10); v.setSpacing(10)
        head = QHBoxLayout()
        title = QLabel("<b>SiteWrap</b>"); title.setStyleSheet("font-size:20px; color:#89b4fa;")
        head.addWidget(title); head.addSpacing(16)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search sites…  (Ctrl+F)")
        self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self.apply_filter)
        head.addWidget(self.search, 1)
        self.state = load_state()
        self.add_btn = QPushButton("＋ Add site"); self.add_btn.clicked.connect(self.add_site_dialog)
        self.edit_btn = QPushButton("✎ Edit sites.yaml"); self.edit_btn.clicked.connect(self.edit_yaml)
        self.reload_btn = QPushButton("⟳ Reload"); self.reload_btn.clicked.connect(self.reload)
        for b in (self.add_btn, self.edit_btn, self.reload_btn):
            head.addWidget(b)
        v.addLayout(head)
        self.tabs = QTabWidget(); self.tabs.setDocumentMode(True)
        # ★ Shortcuts: the sites marked `shortcut: true`, as a grid that wraps with the window width
        self.short_scroll = QScrollArea(); self.short_scroll.setWidgetResizable(True)
        self.short_scroll.setFrameShape(QFrame.NoFrame)
        self.short_host = QWidget(); self.short_grid = QGridLayout(self.short_host)
        self.short_grid.setContentsMargins(0, 8, 0, 0); self.short_grid.setSpacing(12)
        self.short_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.short_scroll.setWidget(self.short_host)
        # All: one column per category, side by side (scrolls sideways when they don't fit)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.NoFrame)
        self.sections_host = QWidget(); self.sections_lay = QHBoxLayout(self.sections_host)
        self.sections_lay.setContentsMargins(0, 8, 0, 0); self.sections_lay.setSpacing(18)
        self.sections_lay.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.sections_lay.addStretch(1)
        self.sections = {}
        self.scroll.setWidget(self.sections_host)
        self.tabs.addTab(self.short_scroll, "★ Shortcuts"); self.tabs.addTab(self.scroll, "All")
        self.SHORTCUTS, self.ALL = 0, 1
        self.tabs.currentChanged.connect(self.relayout)
        v.addWidget(self.tabs, 1)
        self.empty = QLabel(""); self.empty.setAlignment(Qt.AlignCenter); self.empty.setStyleSheet("color:#7f849c;")
        v.addWidget(self.empty)
        self.statusBar().showMessage(str(self.path))

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._file_changed)
        self.watcher.directoryChanged.connect(self._file_changed)   # editors that save via rename
        self._debounce = QTimer(self); self._debounce.setSingleShot(True); self._debounce.setInterval(300)
        self._debounce.timeout.connect(self.reload)
        self._mtime = None
        self.poll = QTimer(self); self.poll.setInterval(2000); self.poll.timeout.connect(self.refresh_running)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self.reload)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        self.reload()

    # --- data ---------------------------------------------------------------------------------------
    def _watch(self):
        for p in (self.watcher.files() + self.watcher.directories()):
            self.watcher.removePath(p)
        if self.path.exists():
            self.watcher.addPath(str(self.path))
        self.watcher.addPath(str(self.path.parent))

    def _file_changed(self, *_):
        try:
            m = self.path.stat().st_mtime_ns
        except OSError:
            m = None
        if m != self._mtime:
            self._debounce.start()

    def reload(self):
        try:
            self._mtime = self.path.stat().st_mtime_ns
        except OSError:
            self._mtime = None
        sites, errors = S.load(self.path)
        for c in self.cards + self.shortcut_cards:
            c.setParent(None); c.deleteLater()
        for sec in self.sections.values():
            self.sections_lay.removeWidget(sec); sec.setParent(None); sec.deleteLater()
        self.cards, self.shortcut_cards, self.sections = [], [], {}
        self.categories = S.load_categories(self.path, sites)
        collapsed = set(self.state.get("collapsed", []))
        for i, cat in enumerate(self.categories):
            sec = Section(cat, cat.name in collapsed); sec.toggled.connect(self._section_toggled)
            self.sections[cat.name] = sec; self.sections_lay.insertWidget(i, sec)
        for s in sites:
            c = self._card(s); self.cards.append(c)
            self.sections[s.category].cards.append(c)
            if s.shortcut:
                self.shortcut_cards.append(self._card(s))
        self.refresh_desktop()
        self.errors = errors
        self._watch(); self.relayout(); self.refresh_running()
        msg = f"{len(sites)} sites · {self.path}"
        if errors:
            msg += f" · {len(errors)} invalid: " + "; ".join(errors)
        self.statusBar().showMessage(msg)

    def _card(self, site: S.Site) -> Card:
        c = Card(site); c.clicked.connect(self.open_site); c.desktop_toggled.connect(self.toggle_desktop)
        return c

    def _section_toggled(self, name, collapsed):
        c = set(self.state.get("collapsed", []))
        (c.add if collapsed else c.discard)(name)
        self.state["collapsed"] = sorted(c); save_state(self.state)

    def apply_filter(self, *_):
        self.relayout()

    def visible_cards(self):
        """Cards shown on the current tab that match the search."""
        q = self.search.text()
        pool = self.shortcut_cards if self.tabs.currentIndex() == self.SHORTCUTS else self.cards
        return [c for c in pool if c.matches(q)]

    def relayout(self, *_):
        q = self.search.text()
        vis = {c for c in self.cards if c.matches(q)}
        for sec in self.sections.values():
            sec.layout_cards(vis)
        while self.short_grid.count():
            self.short_grid.takeAt(0)
        cols = max(1, (self.short_scroll.viewport().width() - 12) // (CARD_W + 12))
        shown = [c for c in self.shortcut_cards if c.matches(q)]
        for c in self.shortcut_cards:
            c.setVisible(c in shown)
        for i, c in enumerate(shown):
            self.short_grid.addWidget(c, i // cols, i % cols)
        if not self.cards:
            msg = f"No sites in {self.path}"
        elif self.tabs.currentIndex() == self.SHORTCUTS and not self.shortcut_cards:
            msg = "No shortcuts yet: add  shortcut: true  to a site in sites.yaml (or tick it in ＋ Add site)."
        else:
            msg = "" if self.visible_cards() else "No sites match."
        self.empty.setText(msg)

    def resizeEvent(self, e):
        super().resizeEvent(e); self.relayout()

    def refresh_running(self):
        for c in self.cards + self.shortcut_cards:
            c.set_running(instance.is_running(c.site.id))

    # --- actions --------------------------------------------------------------------------------------
    def open_site(self, site_id: str):
        if instance.send(site_id, "raise") == "raised":
            self.statusBar().showMessage(f"{site_id} is already open — raised it", 4000); return "raised"
        self.launched.append(launch_detached(site_id))
        self.statusBar().showMessage(f"Opening {site_id}…", 4000)
        QTimer.singleShot(1500, self.refresh_running)
        return "launched"

    def refresh_desktop(self):
        on = set(D.installed(D.desktop_dir()))
        for c in self.cards + self.shortcut_cards:
            c.set_on_desktop(c.site.id in on)

    def toggle_desktop(self, site_id: str):
        site = next(c.site for c in self.cards if c.site.id == site_id)
        try:
            if D.on_desktop(site_id):
                D.remove_from_desktop(site_id); msg = f"Removed {site.name} from the Desktop"
            else:
                p = D.add_to_desktop(site); msg = f"Added {site.name} to the Desktop ({p})"
        except OSError as e:
            QMessageBox.warning(self, "Desktop", f"Could not update the Desktop launcher: {e}"); return
        self.refresh_desktop(); self.statusBar().showMessage(msg, 5000)

    def edit_yaml(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def add_site_dialog(self):
        d = AddSiteDialog(self, self.categories)
        if d.exec() != QDialog.Accepted:
            return
        why = add_site(d.entry(), self.path)
        if why:
            QMessageBox.warning(self, "Add site", why); return
        self.reload()
        regenerate_launchers()
        self.statusBar().showMessage(f"Added {d.entry()['id']}; regenerating launchers…", 5000)

    def showEvent(self, e):
        super().showEvent(e); self.poll.start(); QTimer.singleShot(0, self.relayout)

    def hideEvent(self, e):
        self.poll.stop(); super().hideEvent(e)


def main() -> int:
    app = QApplication([APP_ID, "-name", APP_ID])
    QGuiApplication.setApplicationName(APP_ID)
    QGuiApplication.setDesktopFileName(APP_ID)
    QGuiApplication.setWindowIcon(QIcon(str(ROOT / "icons" / "sitewrap.svg")))
    if instance.send("_dashboard", "raise") == "raised":
        print("sitewrap: dashboard already open; raised it"); return 0
    w = Dashboard()

    def raise_window():
        if w.isMinimized():
            w.showNormal()
        w.show(); w.raise_(); w.activateWindow()
    w._instance = instance.serve("_dashboard", raise_window, w)
    import signal
    signal.signal(signal.SIGTERM, lambda *_: w.close()); signal.signal(signal.SIGINT, lambda *_: w.close())
    t = QTimer(); t.start(500); t.timeout.connect(lambda: None)
    w.show()
    return app.exec()
