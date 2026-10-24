"""Dashboard: cards, filter, YAML watch/reload, add-site, launch/raise, running indicator, single instance,
detached launches, no QtWebEngine in the dashboard process."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from sitewrap import desktop, instance, sites

ROOT = Path(__file__).resolve().parent.parent
HEADER = "# my comment stays\ndefaults:\n  cpu_quota: 50%\n\nsites:\n"


def entry(i, **kw):
    return {"id": i, "name": i.title(), "description": f"{i} description", "url": f"https://{i}.example.ts.net",
            "icon": "icons/default.svg", **kw}


@pytest.fixture
def env(tmp_path, monkeypatch):
    f = tmp_path / "sites.yaml"
    f.write_text(HEADER + "\n".join("  " + l for l in yaml.safe_dump([entry("alpha"), entry("beta")],
                                                                     sort_keys=False).splitlines()) + "\n")
    monkeypatch.setenv("SITEWRAP_SITES", str(f))
    monkeypatch.setenv("SITEWRAP_ICONS", str(tmp_path / "icons"))
    monkeypatch.setenv("SITEWRAP_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SITEWRAP_RUNTIME", str(tmp_path / "run"))
    monkeypatch.setenv("SITEWRAP_APPS_DIR", str(tmp_path / "apps"))
    log = tmp_path / "launch.log"
    fake = tmp_path / "fake_webapp"
    fake.write_text(f"#!/bin/sh\necho \"$1 $(ps -o sid= -p $$)\" >> {log}\n")
    fake.chmod(0o755)
    monkeypatch.setenv("SITEWRAP_LAUNCH", str(fake))
    return tmp_path


def test_dashboard_process_never_loads_webengine(env):
    code = ("import sys; from PySide6.QtWidgets import QApplication; app = QApplication([]);"
            "from sitewrap.dashboard import Dashboard; w = Dashboard(); w.show(); app.processEvents();"
            "print(len(w.cards), any(m.startswith('PySide6.QtWebEngine') for m in sys.modules))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen"))
    assert r.stdout.split() == ["2", "False"], r.stderr[-1500:]


def test_cards_filter_and_watch(qtbot, env):
    from sitewrap.dashboard import Dashboard
    w = Dashboard(); qtbot.addWidget(w); w.show(); w.tabs.setCurrentIndex(w.ALL)
    assert [c.site.id for c in w.cards] == ["alpha", "beta"]
    c = w.cards[0]
    assert "Alpha" in c.name.text() and c.desc.text() == "alpha description" and c.host.text() == "alpha.example.ts.net"
    assert not c.icon.pixmap().isNull()
    w.search.setText("BETA")
    assert [x.site.id for x in w.visible_cards()] == ["beta"] and not w.cards[0].isVisibleTo(w)
    w.search.setText("nothing-matches"); assert "No sites match" in w.empty.text()
    w.search.clear()
    # editing the file (atomic rename, like most editors) reloads the dashboard
    f = env / "sites.yaml"; tmp = env / "s.tmp"
    tmp.write_text(f.read_text() + "  - " + yaml.safe_dump(entry("gamma"), sort_keys=False).replace("\n", "\n    ").rstrip() + "\n")
    os.replace(tmp, f)
    qtbot.waitUntil(lambda: [x.site.id for x in w.cards] == ["alpha", "beta", "gamma"], timeout=5000)
    w.reload_btn.click(); assert len(w.cards) == 3


def test_click_launches_detached_then_raises_when_running(qtbot, env):
    from sitewrap.dashboard import Dashboard
    w = Dashboard(); qtbot.addWidget(w); w.show(); w.tabs.setCurrentIndex(w.ALL)
    qtbot.mouseClick(w.cards[0], __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.LeftButton)
    qtbot.waitUntil(lambda: (env / "launch.log").exists(), timeout=5000)
    sid_line = (env / "launch.log").read_text().split()
    assert sid_line[0] == "alpha"
    assert int(sid_line[1]) != os.getsid(0)                # own session: survives the dashboard
    assert not w.cards[0].running
    # pretend alpha is open: a live instance in another process (as in real use)
    flag = env / "raised"
    code = ("import sys; from PySide6.QtCore import QCoreApplication; app = QCoreApplication([]);"
            "from sitewrap import instance;"
            f"srv = instance.serve('alpha', lambda: open({str(flag)!r}, 'a').write('1')); app.exec()")
    p = subprocess.Popen([sys.executable, "-c", code], env=dict(os.environ, PYTHONPATH=str(ROOT)))
    try:
        qtbot.waitUntil(lambda: instance.is_running("alpha"), timeout=10000)
        w.refresh_running()
        assert w.cards[0].running and w.cards[0].dot.isVisibleTo(w) and not w.cards[1].running
        assert w.open_site("alpha") == "raised" and flag.read_text() == "1"
        assert (env / "launch.log").read_text().count("alpha") == 1          # no duplicate launch
    finally:
        p.terminate(); p.wait(10)
    w.refresh_running(); assert not w.cards[0].running

def test_add_site_validates_appends_keeps_comments(qtbot, env):
    from sitewrap.dashboard import add_site, AddSiteDialog
    f = env / "sites.yaml"
    assert "duplicate" in add_site(entry("alpha"))
    assert "url" in add_site(entry("bad", url="ftp://x"))
    assert "missing" in add_site({"id": "x"})
    assert add_site(entry("delta", toolbar=False)) == ""
    text = f.read_text()
    assert text.startswith("# my comment stays") and "cpu_quota: 50%" in text
    s = {x.id: x for x in sites.load(f)[0]}
    assert list(s) == ["alpha", "beta", "delta"] and s["delta"].toolbar is False and s["delta"].cpu_quota == "50%"
    d = AddSiteDialog(); qtbot.addWidget(d)
    for k, v in entry("Bad Id").items():
        d.fields[k].setText(v)
    d.try_accept(); assert "bad id" in d.error.text() and d.result() == 0


def test_single_instance_end_to_end(env, tmp_path):
    """A second `webapp <id>` raises the first window instead of opening a duplicate."""
    import http.server, threading
    (tmp_path / "www").mkdir(); (tmp_path / "www" / "index.html").write_text("<title>x</title>")
    h = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path / "www"), **k)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    (env / "sites.yaml").write_text(yaml.safe_dump({"sites": [entry("loc", url=f"http://127.0.0.1:{httpd.server_address[1]}/")]}))
    e = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    first = subprocess.Popen([sys.executable, "-m", "sitewrap", "loc"], env=e, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if instance.is_running("loc"):
                break
            time.sleep(0.2)
        assert instance.is_running("loc")
        r = subprocess.run([sys.executable, "-m", "sitewrap", "loc"], env=e, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0 and "already open" in r.stdout
        assert first.poll() is None
    finally:
        first.terminate(); first.wait(15); httpd.shutdown()
    assert not instance.is_running("loc")


def test_dashboard_desktop_entry(env):
    r = desktop.install(download_icons=False, log=lambda *_: None)
    p = env / "apps" / "sitewrap.desktop"
    t = p.read_text().splitlines()
    assert "Name=SiteWrap" in t and "StartupWMClass=sitewrap" in t and any(l.startswith("Icon=/") for l in t)
    import shutil
    if shutil.which("desktop-file-validate"):
        v = subprocess.run(["desktop-file-validate", str(p)], capture_output=True, text=True)
        assert v.returncode == 0 and not v.stdout.strip(), v.stdout
    desktop.uninstall(log=lambda *_: None)
    assert not p.exists()
