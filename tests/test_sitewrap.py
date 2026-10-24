"""SiteWrap: YAML validation, icons, .desktop generation/cleanup, launcher, and the QtWebEngine window
against a local http.server (offscreen)."""
import http.server
import os
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

from sitewrap import desktop, sites

ROOT = Path(__file__).resolve().parent.parent
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "www"; root.mkdir()
    (root / "index.html").write_text("<html><head><title>Fixture Home</title></head><body>hi</body></html>")
    (root / "page2.html").write_text("<html><head><title>Page Two</title></head><body>2</body></html>")
    (root / "ua.html").write_text("<html><head><title>x</title><script>document.title=navigator.userAgent"
                                  "</script></head></html>")
    (root / "file.bin").write_bytes(b"x" * 100)
    (root / "icon.png").write_bytes(PNG)
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(root), **k)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SITEWRAP_SITES", str(tmp_path / "sites.yaml"))
    monkeypatch.setenv("SITEWRAP_ICONS", str(tmp_path / "icons"))
    monkeypatch.setenv("SITEWRAP_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SITEWRAP_APPS_DIR", str(tmp_path / "apps"))
    monkeypatch.setenv("SITEWRAP_BIN", "/usr/local/bin/webapp-test")
    return tmp_path


def write(env, entries, defaults=None):
    d = {"sites": entries}
    if defaults:
        d["defaults"] = defaults
    (env / "sites.yaml").write_text(yaml.safe_dump(d))


def entry(i, **kw):
    return {"id": i, "name": i.title(), "description": f"{i} desc", "url": f"https://{i}.example",
            "icon": "icons/default.svg", **kw}


def test_example_sites_yaml():
    s, errors = sites.load(ROOT / "sites.example.yaml")
    assert errors == [] and len(s) >= 3
    assert all(x.name and x.description and x.icon and x.url.startswith("https://") for x in s)
    assert any(x.shortcut for x in s)


def test_validation_and_defaults(env):
    write(env, [entry("ok", toolbar=False, width=900, height=600, zoom=1.25, user_agent="UA/1"),
                entry("ok"),                                        # duplicate
                entry("Bad Id"), {"id": "nourl", "name": "n", "description": "d", "icon": "x"},
                entry("ftp", url="ftp://x"), entry("w", width="big"), entry("z", zoom=9),
                entry("t", toolbar="yes"), "junk"],
          defaults={"cpu_quota": "40%", "memory_max": "900M"})
    s, errors = sites.load()
    assert [x.id for x in s] == ["ok"] and len(errors) == 8
    ok = s[0]
    assert (ok.toolbar, ok.width, ok.height, ok.zoom, ok.user_agent) == (False, 900, 600, 1.25, "UA/1")
    assert (ok.cpu_quota, ok.memory_max, ok.app_id) == ("40%", "900M", "sitewrap-ok")
    assert sites.data_dir("ok") == env / "data" / "ok"
    for why in ("duplicate", "bad id", "missing url", "http(s)", "width", "zoom", "toolbar", "mapping"):
        assert any(why in e for e in errors), why


def test_icons_local_remote_and_fallback(env, server):
    (env / "my.png").write_bytes(PNG)
    write(env, [entry("loc", icon="my.png"), entry("rem", icon=server + "/icon.png"),
                entry("html", icon=server + "/index.html"), entry("gone", icon="nope.png")])
    s = {x.id: x for x in sites.load()[0]}
    assert sites.resolve_icon(s["loc"]) == env / "my.png"
    p = sites.resolve_icon(s["rem"], download=True)
    assert p == env / "icons" / "rem.png" and p.read_bytes() == PNG
    assert sites.resolve_icon(s["rem"]) == p                       # cached, no network needed
    assert sites.resolve_icon(s["html"], download=True).name == "default.svg"   # HTML is not an icon
    assert sites.resolve_icon(s["gone"]).name == "default.svg"


def test_desktop_install_cleanup_uninstall(env):
    write(env, [entry("one", description="First site"), entry("two")])
    apps = env / "apps"
    (apps).mkdir()
    (apps / "sitewrap-foreign.desktop").write_text("[Desktop Entry]\nType=Application\nName=x\nExec=x\n")
    r = desktop.install(download_icons=False, log=lambda *_: None)
    assert sorted(r["installed"]) == ["one", "two"]
    text = (apps / "sitewrap-one.desktop").read_text()
    for line in ("Name=One", "Comment=First site", "Exec=/usr/local/bin/webapp-test one",
                 "StartupWMClass=sitewrap-one", "X-SiteWrap-Id=one", "Type=Application"):
        assert line in text.splitlines(), line
    assert any(l.startswith("Icon=/") for l in text.splitlines())
    if shutil.which("desktop-file-validate"):
        v = subprocess.run(["desktop-file-validate", str(apps / "sitewrap-one.desktop")], capture_output=True, text=True)
        assert v.returncode == 0 and not v.stdout.strip(), v.stdout
    write(env, [entry("two")])                                     # "one" deleted from YAML
    r = desktop.install(download_icons=False, log=lambda *_: None)
    assert r["removed"] == ["one"] and not (apps / "sitewrap-one.desktop").exists()
    assert (apps / "sitewrap-foreign.desktop").exists()           # not ours: untouched
    assert desktop.uninstall(log=lambda *_: None) == ["two"]
    assert [p.name for p in apps.glob("*.desktop")] == ["sitewrap-foreign.desktop"]


def test_cli_list_and_unknown(env):
    write(env, [entry("one")])
    e = dict(os.environ, PYTHONPATH=str(ROOT))
    r = subprocess.run([sys.executable, "-m", "sitewrap", "--list"], capture_output=True, text=True, env=e, timeout=30)
    assert r.returncode == 0 and "one" in r.stdout
    r = subprocess.run([sys.executable, "-m", "sitewrap", "nope"], capture_output=True, text=True, env=e, timeout=30)
    assert r.returncode == 2 and "unknown site" in r.stderr


def test_launcher_scope_props(env):
    """bin/webapp runs the window in a systemd --user scope with the site's caps."""
    text = (ROOT / "bin" / "webapp").read_text()
    assert "systemd-run --user --scope" in text and "CPUQuota=$CPU" in text and "MemoryMax=$MEM" in text
    assert "QT_QPA_PLATFORM" not in text.split("set -euo")[1]      # native Wayland allowed


def test_window_local_server(qtbot, env, server):
    write(env, [entry("fix", url=server + "/index.html", name="Fixture", width=700, height=500, zoom=1.1)])
    from sitewrap.app import build_window
    site = sites.find("fix")
    w = build_window(site, downloads=env / "dl"); qtbot.addWidget(w); w.show()
    web = w.web
    with qtbot.waitSignal(web.view.loadFinished, timeout=30000) as sig:
        pass
    assert sig.args == [True] and web.view.title() == "Fixture Home"
    qtbot.waitUntil(lambda: w.windowTitle() == "Fixture Home — Fixture", timeout=5000)
    assert (w.width(), w.height()) == (700, 500) and not w.windowIcon().isNull()
    assert web.toolbar.isVisibleTo(w) and web.zoom_label.text() == "110%"
    root = env / "data" / "fix"
    assert Path(web.profile.persistentStoragePath()) == root and not web.profile.isOffTheRecord()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    with qtbot.waitSignal(web.view.loadFinished, timeout=30000):
        web.url_edit.setText(server + "/page2.html"); web._navigate_typed()
    with qtbot.waitSignal(web.view.loadFinished, timeout=30000):
        web.view.back()
    assert web.view.title() == "Fixture Home"
    from PySide6.QtCore import QUrl
    with qtbot.waitSignal(web.profile.downloadRequested, timeout=30000):
        web.view.page().download(QUrl(server + "/file.bin"))
    qtbot.waitUntil(lambda: (env / "dl" / "file.bin").exists(), timeout=30000)
    w.close()


def test_toolbar_off_and_user_agent(qtbot, env, server):
    write(env, [entry("ua", url=server + "/ua.html", toolbar=False, user_agent="SiteWrapTest/1.0")])
    from sitewrap.app import build_window
    w = build_window(sites.find("ua")); qtbot.addWidget(w); w.show()
    qtbot.waitUntil(lambda: w.web.view.title() == "SiteWrapTest/1.0", timeout=30000)
    assert not w.web.toolbar.isVisibleTo(w) and not w.statusBar().isVisibleTo(w)
    w.close()


def test_error_page_tailscale_hint_and_retry(qtbot, env):
    from sitewrap.web import WebWidget, error_html
    w = WebWidget("down", "http://127.0.0.1:9/", "Down"); qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.stack.currentIndex() == 1, timeout=30000)
    assert "Couldn't load" in w.last_error
    w.retry(); assert w.stack.currentIndex() == 0
    qtbot.waitUntil(lambda: w.stack.currentIndex() == 1, timeout=30000)
    assert "tailscale status" in error_html("https://coolify.your-tailnet.ts.net")
    assert "tailscale" not in error_html("https://example.com")
    w.shutdown()


def test_tls_never_disabled():
    src = (ROOT / "sitewrap" / "web.py").read_text() + (ROOT / "sitewrap" / "sites.py").read_text()
    for bad in ("acceptCertificate", "ignore-certificate-errors", "CERT_NONE", "check_hostname = False",
                "_create_unverified_context", "verify=False"):
        assert bad not in src, bad
    assert "rejectCertificate" in src and "create_default_context" in src


@pytest.mark.skipif(not shutil.which("openssl"), reason="needs openssl")
def test_self_signed_tls_is_rejected(qtbot, env, tmp_path):
    import ssl
    key, crt = tmp_path / "k.pem", tmp_path / "c.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(crt),
                    "-days", "1", "-subj", "/CN=127.0.0.1"], check=True, capture_output=True)
    (tmp_path / "www").mkdir(exist_ok=True); (tmp_path / "www" / "index.html").write_text("<title>secret</title>")
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(tmp_path / "www"), **k)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(crt, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    from sitewrap.web import WebWidget
    w = WebWidget("tls", f"https://127.0.0.1:{httpd.server_address[1]}/", "TLS"); qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.stack.currentIndex() == 1, timeout=30000)
    assert getattr(w, "cert_errors", 0) >= 1 and "Invalid TLS certificate" in w.last_error
    assert w.view.title() != "secret"
    w.shutdown(); httpd.shutdown()
