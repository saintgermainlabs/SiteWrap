"""Generate / remove per-site .desktop launchers (sitewrap-<id>.desktop)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from sitewrap import sites as S

MARK = "X-SiteWrap-Id"


def apps_dir() -> Path:
    env = os.environ.get("SITEWRAP_APPS_DIR")
    return Path(env).expanduser() if env else Path.home() / ".local" / "share" / "applications"


def desktop_dir() -> Path:
    """The user's Desktop folder (XDG), where "Add to Desktop" puts a copy of a site's launcher."""
    env = os.environ.get("SITEWRAP_DESKTOP_DIR")
    if env:
        return Path(env).expanduser()
    if shutil.which("xdg-user-dir"):
        out = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True).stdout.strip()
        if out and Path(out) != Path.home():
            return Path(out)
    return Path.home() / "Desktop"


def webapp_bin() -> str:
    env = os.environ.get("SITEWRAP_BIN")
    return env or str(Path.home() / ".local" / "bin" / "webapp")


def _esc(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace("\n", " ").replace("\r", " ").replace("\t", " ")


def _kw(v: str) -> str:
    return _esc(v).replace(";", ",")


def desktop_entry(site: S.Site, icon: Path, exe: str = None) -> str:
    exe = exe or webapp_bin()
    q = exe if " " not in exe else f'"{exe}"'
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        f"Name={_esc(site.name)}",
        f"Comment={_esc(site.description)}",
        f"Keywords={_kw(site.category)};{site.id};{_kw(site.name)};",
        f"Exec={q} {site.id}",
        f"TryExec={exe}",
        f"Icon={icon}",
        "Terminal=false",
        "Categories=Network;",
        f"StartupWMClass={site.app_id}",
        "StartupNotify=true",
        f"{MARK}={site.id}",
        "",
    ])


DASHBOARD_FILE = "sitewrap.desktop"


def dashboard_entry(exe: str = None) -> str:
    exe = exe or webapp_bin()
    return "\n".join([
        "[Desktop Entry]", "Type=Application", "Version=1.5", "Name=SiteWrap",
        "Comment=Dashboard of your web apps (sites.yaml)", f"Exec={exe}", f"TryExec={exe}",
        f"Icon={S.ROOT / 'icons' / 'sitewrap.svg'}", "Terminal=false", "Categories=Network;",
        "StartupWMClass=sitewrap", "StartupNotify=true", "X-SiteWrap-Dashboard=true", ""])


def installed(adir: Path = None) -> dict:
    """{id: path} of launchers we generated (identified by our X-SiteWrap-Id key)."""
    out = {}
    for p in sorted((adir or apps_dir()).glob(f"{S.APP_PREFIX}*.desktop")):
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith(MARK + "="):
                    out[line.split("=", 1)[1].strip()] = p
        except OSError:
            pass
    return out


def on_desktop(site_id: str, ddir: Path = None) -> bool:
    return site_id in installed(ddir or desktop_dir())


def add_to_desktop(site: S.Site, ddir: Path = None, download_icon=False) -> Path:
    """Put the site's launcher on the Desktop (trusted, so GNOME lets it launch)."""
    ddir = ddir or desktop_dir(); ddir.mkdir(parents=True, exist_ok=True)
    p = ddir / f"{site.app_id}.desktop"
    p.write_text(desktop_entry(site, S.icon_for_desktop(site, download=download_icon)), encoding="utf-8")
    os.chmod(p, 0o755)
    run_quiet(["gio", "set", str(p), "metadata::trusted", "true"])
    return p


def remove_from_desktop(site_id: str, ddir: Path = None) -> bool:
    p = installed(ddir or desktop_dir()).get(site_id)
    if p:
        p.unlink(missing_ok=True)
    return bool(p)


def run_quiet(argv):
    if shutil.which(argv[0]):
        subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def install(download_icons=True, adir: Path = None, log=print) -> dict:
    adir = adir or apps_dir(); adir.mkdir(parents=True, exist_ok=True)
    sites, errors = S.load()
    for e in errors:
        log(f"  ! skipped {e}")
    wanted = {}
    for s in sites:
        icon = S.icon_for_desktop(s, download=download_icons)
        p = adir / f"{s.app_id}.desktop"
        p.write_text(desktop_entry(s, icon), encoding="utf-8"); os.chmod(p, 0o755)
        run_quiet(["gio", "set", str(p), "metadata::trusted", "true"])
        wanted[s.id] = p
        note = "" if icon.name != "default.svg" else "  (icon: default; remote icon not reachable)"
        log(f"  + {p.name}  →  {s.name}  [{icon.name}]{note}")
    dp = adir / DASHBOARD_FILE
    dp.write_text(dashboard_entry(), encoding="utf-8"); os.chmod(dp, 0o755)
    run_quiet(["gio", "set", str(dp), "metadata::trusted", "true"])
    log(f"  + {DASHBOARD_FILE}  →  SiteWrap dashboard")
    removed = []
    for sid, p in installed(adir).items():
        if sid not in wanted:
            p.unlink(missing_ok=True); removed.append(sid)
            log(f"  - {p.name}  (no longer in sites.yaml)")
    ddir = desktop_dir()                           # keep Desktop copies in sync (refresh / drop removed sites)
    by_id = {s.id: s for s in sites}
    for sid in installed(ddir):
        if sid in by_id:
            add_to_desktop(by_id[sid], ddir)
        else:
            remove_from_desktop(sid, ddir); log(f"  - Desktop/{S.APP_PREFIX}{sid}.desktop  (no longer in sites.yaml)")
    run_quiet(["update-desktop-database", str(adir)])
    return {"installed": wanted, "removed": removed, "errors": errors}


def uninstall(adir: Path = None, log=print) -> list:
    adir = adir or apps_dir()
    gone = []
    for sid, p in installed(adir).items():
        p.unlink(missing_ok=True); gone.append(sid); log(f"  - {p.name}")
    for sid in installed(desktop_dir()):
        remove_from_desktop(sid); log(f"  - Desktop/{S.APP_PREFIX}{sid}.desktop")
    dp = adir / DASHBOARD_FILE
    if dp.exists() and "X-SiteWrap-Dashboard=true" in dp.read_text(encoding="utf-8"):
        dp.unlink(); log(f"  - {DASHBOARD_FILE}")
    run_quiet(["update-desktop-database", str(adir)])
    return gone


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    if cmd == "install":
        r = install(download_icons="--no-download" not in sys.argv)
        sys.exit(1 if r["errors"] and not r["installed"] else 0)
    elif cmd == "uninstall":
        uninstall()
    else:
        sys.exit("usage: python -m sitewrap.desktop install|uninstall")
