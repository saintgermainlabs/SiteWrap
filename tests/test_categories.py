"""Categories: YAML parsing/order/defaults, dashboard tabs (★ Shortcuts start page, All in category columns),
collapse persistence, add-site category + shortcut, .desktop Keywords, Add to Desktop."""
import os
from pathlib import Path

import pytest
import yaml
from PySide6.QtCore import Qt

from sitewrap import desktop, sites

ROOT = Path(__file__).resolve().parent.parent


def entry(i, cat=None, **kw):
    e = {"id": i, "name": i.title(), "description": f"{i} description", "url": f"https://{i}.example",
         "icon": "icons/default.svg", **kw}
    if cat is not None:
        e["category"] = cat
    return e


@pytest.fixture
def env(tmp_path, monkeypatch):
    f = tmp_path / "sites.yaml"
    f.write_text("# keep me\n" + yaml.safe_dump({
        "categories": [{"name": "Homelab", "icon": "🏠", "description": "On the tailnet"}, "Tools",
                       {"name": "Unused"}],
        "sites": [entry("zeta", "Tools", shortcut=True), entry("alpha", "Homelab", shortcut=True), entry("mid", "Media"),
                  entry("nocat"), entry("beta", "Homelab"), entry("aaa", "Archive")]}, sort_keys=False, allow_unicode=True))
    for k, v in (("SITEWRAP_SITES", f), ("SITEWRAP_ICONS", tmp_path / "icons"), ("SITEWRAP_RUNTIME", tmp_path / "run"),
                 ("SITEWRAP_APPS_DIR", tmp_path / "apps"), ("SITEWRAP_CONFIG", tmp_path / "cfg"),
                 ("SITEWRAP_LAUNCH", "/bin/true"), ("SITEWRAP_BIN", "/usr/bin/webapp-test")):
        monkeypatch.setenv(k, str(v))
    return tmp_path


def test_bundled_seed_categories():
    loaded, errors = sites.load(ROOT / "sites.example.yaml")
    assert errors == [] and loaded and all(x.category for x in loaded)
    cats = sites.load_categories(ROOT / "sites.example.yaml")
    assert cats and cats[0].icon and cats[0].description


def test_category_parsing_and_order(env):
    s, errors = sites.load()
    assert errors == []
    by = {x.id: x.category for x in s}
    assert by["nocat"] == "Other" and by["alpha"] == "Homelab"
    names = [c.name for c in sites.load_categories()]
    # configured order first (incl. unused), then other used ones alphabetically, Other last
    assert names == ["Homelab", "Tools", "Unused", "Archive", "Media", "Other"]
    cats, errs = sites.parse_categories(["A", {"name": "A"}, {"icon": "x"}, 5])
    assert [c.name for c in cats] == ["A"] and len(errs) == 3
    assert "category" in sites.validate(entry("bad", ""))
    assert "category" in sites.validate(entry("bad", 3))
    assert sites.validate(entry("ok", "Tools")) == ""


def test_sections_order_headers_and_search(qtbot, env):
    from sitewrap.dashboard import Dashboard
    w = Dashboard(); qtbot.addWidget(w); w.resize(1000, 700); w.show(); w.tabs.setCurrentIndex(w.ALL)
    order = [w.sections_lay.itemAt(i).widget().cat.name for i in range(w.sections_lay.count() - 1)]
    assert order == ["Homelab", "Tools", "Unused", "Archive", "Media", "Other"]
    hl = w.sections["Homelab"]
    assert "🏠 Homelab" in hl.header.text() and hl.header.text().endswith("·  2") and hl.desc.text() == "On the tailnet"
    assert [c.site.id for c in hl.cards] == ["alpha", "beta"]
    assert not w.sections["Unused"].isVisibleTo(w)                  # no sites → no section
    w.search.setText("description")                                 # search spans all categories
    assert len(w.visible_cards()) == 6
    w.search.setText("homelab")                                     # category name is searchable too
    assert {c.site.id for c in w.visible_cards()} == {"alpha", "beta"}
    assert not w.sections["Tools"].isVisibleTo(w) and w.sections["Homelab"].isVisibleTo(w)
    w.search.clear()


def test_shortcuts_tab_is_the_start_page(qtbot, env):
    from sitewrap.dashboard import Dashboard
    w = Dashboard(); qtbot.addWidget(w); w.resize(1000, 700); w.show()
    assert w.tabs.currentIndex() == w.SHORTCUTS and w.tabs.tabText(0) == "★ Shortcuts" and w.tabs.tabText(1) == "All"
    assert [c.site.id for c in w.visible_cards()] == ["zeta", "alpha"]          # YAML order, only shortcut: true
    assert sites.validate(entry("bad", shortcut="yes")) == "shortcut must be true/false"
    w.search.setText("zeta"); assert [c.site.id for c in w.visible_cards()] == ["zeta"]
    w.search.setText("nope"); assert "No sites match" in w.empty.text()
    w.search.clear()
    w.tabs.setCurrentIndex(w.ALL); assert len(w.visible_cards()) == 6
    # columns: the sections sit side by side, one card per row inside each
    hl, tools = w.sections["Homelab"], w.sections["Tools"]
    assert hl.y() == tools.y() and hl.x() < tools.x()
    assert [hl.grid.getItemPosition(hl.grid.indexOf(c))[:2] for c in hl.cards] == [(0, 0), (1, 0)]


def test_shortcuts_empty_hint(qtbot, tmp_path, monkeypatch):
    from sitewrap.dashboard import Dashboard
    f = tmp_path / "s.yaml"; f.write_text(yaml.safe_dump({"sites": [entry("one")]}))
    monkeypatch.setenv("SITEWRAP_SITES", str(f)); monkeypatch.setenv("SITEWRAP_CONFIG", str(tmp_path / "cfg"))
    w = Dashboard(); qtbot.addWidget(w); w.show()
    assert w.visible_cards() == [] and "shortcut: true" in w.empty.text()


def test_add_to_desktop_button(qtbot, env, monkeypatch):
    from sitewrap.dashboard import Dashboard
    ddir = env / "Desktop"; monkeypatch.setenv("SITEWRAP_DESKTOP_DIR", str(ddir))
    w = Dashboard(); qtbot.addWidget(w); w.show()
    card = w.shortcut_cards[0]
    assert card.site.id == "zeta" and card.desk.text() == "＋ Desktop"
    qtbot.mouseClick(card.desk, Qt.LeftButton)                     # the button does not open the site
    f = ddir / "sitewrap-zeta.desktop"
    assert f.exists() and "Exec=/usr/bin/webapp-test zeta" in f.read_text() and os.access(f, os.X_OK)
    assert desktop.on_desktop("zeta") and not desktop.on_desktop("alpha")
    assert card.desk.text() == "✓ Desktop"
    assert next(c for c in w.cards if c.site.id == "zeta").desk.text() == "✓ Desktop"   # both tabs agree
    desktop.install(download_icons=False)                           # install keeps it, drops removed sites
    assert f.exists()
    (env / "sites.yaml").write_text(yaml.safe_dump({"sites": [entry("alpha")]}))
    desktop.install(download_icons=False); assert not f.exists()
    w.reload(); w.toggle_desktop("alpha"); assert (ddir / "sitewrap-alpha.desktop").exists()
    w.toggle_desktop("alpha"); assert not (ddir / "sitewrap-alpha.desktop").exists()
    assert w.cards[0].desk.text() == "＋ Desktop"
    w.toggle_desktop("alpha"); desktop.uninstall(log=lambda *_: None)   # uninstall clears the Desktop too
    assert not (ddir / "sitewrap-alpha.desktop").exists()


def test_collapse_is_remembered(qtbot, env):
    from sitewrap.dashboard import Dashboard, load_state
    w = Dashboard(); qtbot.addWidget(w); w.show(); w.tabs.setCurrentIndex(w.ALL)
    sec = w.sections["Homelab"]
    qtbot.mouseClick(sec.header, Qt.LeftButton)
    assert sec.collapsed and not sec.body.isVisibleTo(w) and sec.header.text().startswith("▸")
    assert load_state()["collapsed"] == ["Homelab"]
    w.reload()                                                      # survives reloads
    assert w.sections["Homelab"].collapsed
    w2 = Dashboard(); qtbot.addWidget(w2); w2.show(); w2.tabs.setCurrentIndex(w2.ALL)   # and restarts
    assert w2.sections["Homelab"].collapsed and not w2.sections["Tools"].collapsed
    qtbot.mouseClick(w2.sections["Homelab"].header, Qt.LeftButton)
    assert load_state()["collapsed"] == []


def test_add_site_category_combo(qtbot, env):
    from sitewrap.dashboard import AddSiteDialog, add_site, Dashboard
    w = Dashboard(); qtbot.addWidget(w)
    d = AddSiteDialog(w, w.categories); qtbot.addWidget(d)
    assert [d.category.itemText(i) for i in range(d.category.count())][:3] == ["Homelab", "Tools", "Unused"]
    assert d.category.isEditable()
    for k, v in entry("newone").items():
        d.fields[k].setText(v)
    d.category.setEditText("Brand New")                             # a new category
    e = d.entry(); assert e["category"] == "Brand New" and "shortcut" not in e
    d.shortcut.setChecked(True); e = d.entry(); assert e["shortcut"] is True
    assert add_site(e) == ""
    s = {x.id: x for x in sites.load()[0]}
    assert s["newone"].category == "Brand New"
    assert (env / "sites.yaml").read_text().startswith("# keep me")
    w.reload(); assert "Brand New" in w.sections and w.sections["Brand New"].cards[0].site.id == "newone"


def test_desktop_keywords_and_comment(env):
    desktop.install(download_icons=False, log=lambda *_: None)
    t = (env / "apps" / "sitewrap-alpha.desktop").read_text().splitlines()
    assert "Keywords=Homelab;alpha;Alpha;" in t and "Comment=alpha description" in t
    assert "Keywords=Other;nocat;Nocat;" in (env / "apps" / "sitewrap-nocat.desktop").read_text().splitlines()
    import shutil, subprocess
    if shutil.which("desktop-file-validate"):
        v = subprocess.run(["desktop-file-validate", str(env / "apps" / "sitewrap-alpha.desktop")], capture_output=True, text=True)
        assert v.returncode == 0 and not v.stdout.strip(), v.stdout
