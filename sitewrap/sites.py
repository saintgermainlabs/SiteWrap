"""sites.yaml: load + validate site entries, resolve icons, per-site paths. Pure Python (no Qt)."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import ssl
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
REQUIRED = ("id", "name", "description", "url", "icon")
APP_PREFIX = "sitewrap-"                 # desktop file / Wayland app_id / WM_CLASS: sitewrap-<id>
DEFAULTS = {"cpu_quota": "75%", "memory_max": "1500M"}
DEFAULT_CATEGORY = "Other"
ICON_EXTS = (".png", ".svg", ".ico", ".jpg", ".jpeg", ".webp", ".xpm")


@dataclass
class Category:
    name: str
    icon: str = ""
    description: str = ""

    @property
    def label(self) -> str:
        return f"{self.icon} {self.name}".strip()


@dataclass
class Site:
    id: str
    name: str
    description: str
    url: str
    icon: str
    toolbar: bool = True
    width: int = 1200
    height: int = 800
    user_agent: str = ""
    zoom: float = 1.0
    cpu_quota: str = DEFAULTS["cpu_quota"]
    memory_max: str = DEFAULTS["memory_max"]
    category: str = DEFAULT_CATEGORY
    shortcut: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def app_id(self) -> str:
        return APP_PREFIX + self.id


def sites_file() -> Path:
    env = os.environ.get("SITEWRAP_SITES")
    return Path(env).expanduser() if env else ROOT / "sites.yaml"


def icons_dir() -> Path:
    env = os.environ.get("SITEWRAP_ICONS")
    return Path(env).expanduser() if env else ROOT / "icons"


def data_dir(site_id: str) -> Path:
    base = os.environ.get("SITEWRAP_DATA")
    root = Path(base).expanduser() if base else Path.home() / ".local" / "share" / "webapps"
    return root / site_id


def validate(entry, seen=()) -> str:
    """'' if the entry is valid, else the reason."""
    if not isinstance(entry, dict):
        return "entry is not a mapping"
    missing = [k for k in REQUIRED if not str(entry.get(k) or "").strip()]
    if missing:
        return f"missing {', '.join(missing)}"
    if not ID_RE.match(str(entry["id"])):
        return f"bad id {entry['id']!r} (a-z, 0-9, _ or -, starting with a letter)"
    if entry["id"] in seen:
        return f"duplicate id {entry['id']!r}"
    u = urlparse(str(entry["url"]))
    if u.scheme not in ("http", "https") or not u.netloc:
        return f"url must be http(s): {entry['url']!r}"
    for k in ("width", "height"):
        if k in entry and (not isinstance(entry[k], int) or not 200 <= entry[k] <= 10000):
            return f"{k} must be an integer 200..10000"
    if "zoom" in entry:
        try:
            if not 0.25 <= float(entry["zoom"]) <= 5:
                raise ValueError
        except (TypeError, ValueError):
            return "zoom must be a number 0.25..5"
    for k in ("toolbar", "shortcut"):
        if k in entry and not isinstance(entry[k], bool):
            return f"{k} must be true/false"
    if "category" in entry and entry["category"] is not None and (
            not isinstance(entry["category"], str) or not entry["category"].strip() or len(entry["category"]) > 40):
        return "category must be a non-empty string (max 40 chars)"
    return ""


def load(path: Path = None):
    """Return (sites, errors). Invalid entries are skipped with a reason."""
    path = Path(path or sites_file())
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        return [], [f"{path}: {e}"]
    if isinstance(data, list):
        data = {"sites": data}
    defaults = {**DEFAULTS, **(data.get("defaults") or {})}
    sites, errors, seen = [], [], set()
    for i, e in enumerate(data.get("sites") or []):
        why = validate(e, seen)
        if why:
            errors.append(f"sites[{i}] ({(e or {}).get('id', '?') if isinstance(e, dict) else '?'}): {why}")
            continue
        seen.add(e["id"])
        known = {"id", "name", "description", "url", "icon", "toolbar", "width", "height", "user_agent", "zoom",
                 "cpu_quota", "memory_max", "category", "shortcut"}
        sites.append(Site(
            id=e["id"], name=str(e["name"]), description=str(e["description"]), url=str(e["url"]),
            icon=str(e["icon"]), toolbar=e.get("toolbar", True), width=e.get("width", 1200),
            height=e.get("height", 800), user_agent=str(e.get("user_agent") or ""), zoom=float(e.get("zoom", 1.0)),
            cpu_quota=str(e.get("cpu_quota", defaults["cpu_quota"])),
            memory_max=str(e.get("memory_max", defaults["memory_max"])),
            category=str(e.get("category") or DEFAULT_CATEGORY).strip(), shortcut=e.get("shortcut", False),
            extra={k: v for k, v in e.items() if k not in known}))
    return sites, errors


def parse_categories(raw) -> tuple:
    """Top-level `categories:` → ([Category], errors). Items: "Name" or {name, icon, description}."""
    cats, errors, seen = [], [], set()
    for i, c in enumerate(raw or []):
        if isinstance(c, str):
            c = {"name": c}
        if not isinstance(c, dict) or not str(c.get("name") or "").strip():
            errors.append(f"categories[{i}]: needs a name"); continue
        name = str(c["name"]).strip()
        if name in seen:
            errors.append(f"categories[{i}]: duplicate {name!r}"); continue
        seen.add(name)
        cats.append(Category(name, str(c.get("icon") or ""), str(c.get("description") or "")))
    return cats, errors


def load_categories(path: Path = None, sites_list=None) -> list:
    """Categories in display order: the configured ones first (in YAML order), then any other category
    used by a site (alphabetical), with 'Other' last unless configured. Unused configured ones are kept."""
    path = Path(path or sites_file())
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    cats, _ = parse_categories(data.get("categories") if isinstance(data, dict) else None)
    if sites_list is None:
        sites_list, _ = load(path)
    known = {c.name for c in cats}
    used = sorted({s.category for s in sites_list} - known - {DEFAULT_CATEGORY}, key=str.lower)
    cats += [Category(n) for n in used]
    if DEFAULT_CATEGORY not in known and any(s.category == DEFAULT_CATEGORY for s in sites_list):
        cats.append(Category(DEFAULT_CATEGORY, "📦"))
    return cats


def find(site_id: str, path: Path = None) -> Site:
    sites, _ = load(path)
    for s in sites:
        if s.id == site_id:
            return s
    raise KeyError(site_id)


def is_remote(icon: str) -> bool:
    return urlparse(icon).scheme in ("http", "https")


def cached_icon(site: Site) -> Path | None:
    for p in sorted(icons_dir().glob(f"{site.id}.*")):
        if p.suffix.lower() in ICON_EXTS:
            return p
    return None


def download_icon(site: Site, timeout: float = 10) -> Path:
    """Fetch a remote icon into icons/<id>.<ext>. TLS is always verified (default context)."""
    ctx = ssl.create_default_context()
    req = urllib.request.Request(site.icon, headers={"User-Agent": "SiteWrap/0.1"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        data = r.read(2 * 1024 * 1024 + 1)
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not data or len(data) > 2 * 1024 * 1024:
        raise ValueError("empty or too large (>2 MB)")
    if ctype.startswith("text/html") or data[:15].lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError("got an HTML page, not an image")
    ext = Path(urlparse(site.icon).path).suffix.lower()
    if ext not in ICON_EXTS:
        ext = {"image/svg+xml": ".svg", "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
               "image/jpeg": ".jpg", "image/webp": ".webp"}.get(ctype, ".png")
    d = icons_dir(); d.mkdir(parents=True, exist_ok=True)
    for old in d.glob(f"{site.id}.*"):
        old.unlink()
    out = d / f"{site.id}{ext}"
    out.write_bytes(data)
    return out


def resolve_icon(site: Site, download: bool = False) -> Path:
    """Local icon file for a site: a local path as given, else the downloaded copy (fetched if asked),
    else icons/default.svg."""
    if not is_remote(site.icon):
        p = Path(os.path.expanduser(site.icon))
        p = p if p.is_absolute() else sites_file().parent / p
        return p if p.is_file() else ROOT / "icons" / "default.svg"
    if download:
        try:
            return download_icon(site)
        except Exception:
            pass
    return cached_icon(site) or ROOT / "icons" / "default.svg"


def icon_for_desktop(site: Site, download=True) -> Path:
    """Icons used in .desktop files must be a format GNOME renders: convert .ico to .png when possible."""
    p = resolve_icon(site, download=download)
    if p.suffix.lower() == ".ico":
        png = p.with_suffix(".png")
        try:
            from PySide6.QtGui import QImage
            img = QImage(str(p))
            if not img.isNull() and img.save(str(png)):
                p.unlink(missing_ok=True)
                return png
        except Exception:
            pass
    return p
