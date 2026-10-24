# SiteWrap

**A very basic, simple tool that launches a website like a desktop app.**

You give it a website's URL, and it gives you an app: its own window with the site inside, its own icon, and a launcher you can find by typing its name in your app search. No browser tabs, no Electron, no packaging. There's one config file and one install script, and that's all.

It's deliberately small. It doesn't try to be a browser, a bookmark manager or an app store. It just wraps sites in windows.

## What you get

You list your sites in one file, `sites.yaml`, run one script, and every site becomes an app:

- it opens in **its own window** with the site embedded, its own title and icon, not a browser tab;
- it gets **its own launcher**, so typing its name (or category) in the GNOME app search finds it;
- it gets **its own dock icon**, and stays logged in through **its own browser profile**;
- it runs with **CPU and memory caps**, so one heavy site can't slow the machine down.

A small **dashboard** (the SiteWrap app) shows all your sites as cards: a ★ Shortcuts tab for the ones you use most, and an All tab with one column per category.

---

## Quick start

```bash
git clone https://github.com/saintgermainlabs/SiteWrap.git
cd SiteWrap
scripts/install.sh          # first run: creates sites.yaml from sites.example.yaml
```

Then press Super, type the name of a site (e.g. "Excalidraw"), and press Enter. Or open **SiteWrap** to get the dashboard.

To make it yours, edit `sites.yaml` (see "Configuring sites" below) and run `scripts/install.sh` again. `sites.yaml` is in `.gitignore`, so your own list never gets committed; `sites.example.yaml` is the template that ships with the repo.

Requirements: Linux with a desktop that reads `.desktop` files (tested on GNOME, Wayland and X11), Python 3, and `uv` (recommended; falls back to `python3 -m venv`). `install.sh` installs PySide6 and PyYAML into a local `.venv`; nothing is installed system-wide.

**Whenever you change `sites.yaml`, run `scripts/install.sh` again** so the launchers match. The dashboard picks up changes on its own; the app-search launchers only change when you re-run the script (or use ＋ Add site in the dashboard, which re-runs it for you).

---

## How it works

```
sites.yaml ──► scripts/install.sh ──► ~/.local/share/applications/sitewrap-<id>.desktop   (app search, app grid)
                                 └──► ~/.local/bin/webapp, ~/.local/bin/sitewrap         (commands)

app search / dashboard / Desktop icon
        │
        ▼
webapp <id> ──► systemd-run --user --scope (CPUQuota, MemoryMax) ──► Qt window with the site embedded (QtWebEngine)
                                                                      profile: ~/.local/share/webapps/<id>
```

1. **`sites.yaml`** is the only config file (created from `sites.example.yaml` on the first install). Each entry under `sites:` is one app.
2. **`scripts/install.sh`** builds the `.venv` the first time, links the `webapp` and `sitewrap` commands into `~/.local/bin`, downloads remote icons into `icons/`, and writes one launcher per site to `~/.local/share/applications/sitewrap-<id>.desktop`, plus `sitewrap.desktop` for the dashboard. It deletes launchers of sites you removed, and refreshes or removes any Desktop icons too.
3. **The launcher** runs `webapp <id>`. That puts the site in its own `systemd --user` scope with the CPU/RAM caps, then opens a window that embeds the site with QtWebEngine (Chromium). Cookies and logins live in `~/.local/share/webapps/<id>` (mode 0700), separate for each site.
4. **One window per site.** Every open site listens on `$XDG_RUNTIME_DIR/sitewrap/<id>.sock`. Launching a site that's already open brings its window to the front instead of opening a second one.
5. **Dock identity.** The window identifies itself as `sitewrap-<id>` everywhere: Wayland `app_id`, X11 `WM_CLASS`, the `.desktop` file name and `StartupWMClass`. That's how GNOME shows each site under its own icon in the dock rather than as "Python".

**Security:** TLS verification is never disabled. A bad certificate shows an error page instead of loading the site. Icon downloads verify certificates too. For `*.ts.net` addresses that don't load, the error page reminds you to check Tailscale.

---

## Configuring sites (`sites.yaml`)

```yaml
defaults:                    # apply to every site unless the site overrides them
  cpu_quota: 75%             # systemd CPUQuota (100% = one full core)
  memory_max: 1500M          # systemd MemoryMax; the site is killed if it goes over

categories:                  # optional: order and look of the columns on the dashboard's All tab
  - name: Homelab
    icon: "🏠"               # emoji (or text) shown before the name
    description: Self-hosted services
  - name: Tools
    icon: "🛠"
    description: Public web tools
  - Other                    # a plain name works too

sites:
  - id: grafana              # required
    name: Grafana            # required
    description: Server dashboards   # required
    url: https://grafana.example.com # required
    icon: https://grafana.example.com/public/img/fav32.png   # required
    category: Homelab        # optional
    shortcut: true           # optional
    toolbar: true            # optional
    width: 1400              # optional
    height: 900              # optional
    zoom: 1.0                # optional
    user_agent: ""           # optional
    cpu_quota: 50%           # optional
    memory_max: 1G           # optional
```

### Site fields

| Field | Required | Default | What it does |
|---|---|---|---|
| `id` | yes | | Short unique name: lowercase letters, digits, `-` or `_`, starting with a letter (max 32). Used for the command (`webapp <id>`), the launcher file, the profile folder and the dock identity. **Changing it starts a fresh profile, so you log in again.** |
| `name` | yes | | Window title and the name shown in app search. |
| `description` | yes | | Shown on the dashboard card and as the launcher's comment. |
| `url` | yes | | The page that opens, `http://` or `https://`. |
| `icon` | yes | | A URL (downloaded into `icons/<id>.<ext>` by `install.sh`), or a file path, relative to `sites.yaml` or absolute. If it can't be loaded, `icons/default.svg` is used. |
| `category` | no | `Other` | Which column the site appears in on the All tab. Also added to the launcher's search keywords, so typing the category in app search finds it. A new name creates a new column. |
| `shortcut` | no | `false` | `true` puts the site on the dashboard's ★ Shortcuts tab. |
| `toolbar` | no | `true` | Show the back/forward/reload/address bar. Ctrl+L or Ctrl+Shift+B shows it anyway. |
| `width`, `height` | no | `1200`, `800` | Window size in pixels at launch (200–10000). |
| `zoom` | no | `1.0` | Page zoom, 0.25–5. |
| `user_agent` | no | Chromium's | Custom user-agent string, for sites that need one. |
| `cpu_quota`, `memory_max` | no | from `defaults` | Per-site override of the caps. |

Invalid entries are skipped, never fatal. The dashboard's status bar and `webapp --list` say which entries were skipped and why.

### Categories

- The `categories:` list sets the **order** of the columns, with an optional `icon` and `description` for each.
- Categories used by sites but not listed come after the listed ones, alphabetically, with `Other` last.
- A listed category with no sites is hidden.

---

## Everyday tasks

| I want to… | Do this |
|---|---|
| **Add a site** | Dashboard → **＋ Add site** (validates, appends to `sites.yaml` keeping your comments, and regenerates the launchers). Or add an entry to `sites.yaml` by hand and run `scripts/install.sh`. |
| **Put a site on the Shortcuts tab** | Add `shortcut: true` to it, or tick *Show on the Shortcuts tab* in ＋ Add site. |
| **Put a site on my Desktop** | Click **＋ Desktop** on its card. It changes to **✓ Desktop**; click again to remove it. |
| **Group sites** | Give them the same `category:`. Add the category to `categories:` to choose its position, icon and description. |
| **Remove a site** | Delete its entry and run `scripts/install.sh`. Its launcher and Desktop icon go away; its login profile stays in `~/.local/share/webapps/<id>` until you delete that folder. |
| **Change a site's icon** | Change `icon:` and run `scripts/install.sh`. To use your own image, drop it in `icons/` and set `icon: icons/<file>.png`. |
| **Log out of a site completely** | Close it and delete `~/.local/share/webapps/<id>`. |

---

## The dashboard

Open **SiteWrap** from app search, or run `webapp` / `sitewrap` with no arguments.

- **★ Shortcuts** (start page): the sites with `shortcut: true`, as a grid of cards.
- **All**: every site in columns side by side, one per category. Columns scroll sideways if they don't fit the window. Click a column header to collapse it; collapsed columns are remembered in `~/.config/sitewrap/dashboard.json`.
- **Cards**: click to open the site, or raise it if it's already open. **● running** marks open sites (rechecked every 2 s). **＋ Desktop** / **✓ Desktop** adds or removes the Desktop icon.
- **Search** (Ctrl+F): filters cards on both tabs by name, id, description, URL or category.
- **✎ Edit sites.yaml** opens the file in your default editor. The dashboard watches the file and reloads when it changes; **⟳ Reload** (Ctrl+R) forces it.
- Sites open as separate processes, so closing the dashboard never closes them. Only one dashboard runs at a time.
- The dashboard doesn't load the web engine, so it stays light (about 90 MB).

---

## Commands

```text
scripts/install.sh               venv + commands + launchers (re-run after editing sites.yaml)
scripts/install.sh --venv-only   just build the .venv
webapp                           the dashboard (same as: sitewrap)
webapp <id>                      open a site, or raise it if it's already open (with CPU/RAM caps)
webapp --no-scope <id>           open a site without the caps
webapp --list                    list the sites, and any skipped invalid entries
scripts/uninstall.sh             remove launchers, Desktop icons and the commands (keeps logins)
scripts/uninstall.sh --purge     same, and delete every site profile (logins, cookies)
```

## Keys inside a site window

| Keys | Action |
|---|---|
| Ctrl+R / F5 | Reload |
| Alt+← / Alt+→ | Back / forward |
| Alt+Home | Go to the site's `url` |
| Ctrl++ (or Ctrl+=) / Ctrl+- | Zoom in / out |
| Ctrl+L | Show the toolbar and focus the address bar |
| Ctrl+Shift+B | Show / hide the toolbar |
| Ctrl+Q | Close the window |

Downloads go to `~/Downloads`.

---

## Files and folders

| Path | What |
|---|---|
| `sites.yaml` | Your configuration (not committed; see `.gitignore`). |
| `sites.example.yaml` | The template `install.sh` copies to `sites.yaml` on the first run. |
| `icons/` | Icons: your own files plus downloaded ones (`icons/<id>.<ext>`). Only `default.svg` (the fallback) and `sitewrap.svg` are committed. |
| `~/.local/share/applications/sitewrap-<id>.desktop` | App-search launcher for each site (generated; don't edit by hand). |
| `~/.local/share/applications/sitewrap.desktop` | Launcher for the dashboard. |
| `~/Desktop/sitewrap-<id>.desktop` | Desktop icons you added with ＋ Desktop. |
| `~/.local/bin/webapp`, `~/.local/bin/sitewrap` | Links to `bin/webapp`. |
| `~/.local/share/webapps/<id>/` | Each site's browser profile (logins, cookies, cache). |
| `~/.config/sitewrap/dashboard.json` | Dashboard state (collapsed columns). |

Generated launchers carry an `X-SiteWrap-Id` line. SiteWrap only ever updates or deletes files with that marker, never other launchers.

Environment overrides, mainly for testing: `SITEWRAP_SITES` (path to `sites.yaml`), `SITEWRAP_ICONS`, `SITEWRAP_DATA` (profiles), `SITEWRAP_APPS_DIR`, `SITEWRAP_DESKTOP_DIR`, `SITEWRAP_CONFIG`, `SITEWRAP_RUNTIME`, `SITEWRAP_BIN`.

---

## Troubleshooting

- **A site doesn't show up in app search.** Run `scripts/install.sh` and look for `! skipped` lines: the entry is invalid and the reason is printed. `webapp --list` shows the same.
- **A site shows the wrong icon.** Remote icons are saved as `icons/<id>.<ext>`. If `icon:` points at another site's image, that image is what you get. Point it at the right URL or a local file and re-run `install.sh`.
- **The Desktop icon won't launch.** SiteWrap marks it trusted with `gio`. If your file manager still asks, right-click it → *Allow Launching*.
- **A `*.ts.net` site shows an error page.** Check that Tailscale is up (`tailscale status`).
- **A site gets killed or is sluggish.** It hit its `memory_max` or `cpu_quota`. Raise them for that site, or test with `webapp --no-scope <id>`.

---

## Tests

```bash
.venv/bin/pytest -q
```

The tests run offscreen against a local `http.server` and never touch your real launchers, Desktop, profiles or dashboard state. They cover:
- YAML validation;
- icons: local, remote, HTML rejection, fallback;
- generating, validating and cleaning up `.desktop` launchers, and uninstalling;
- the CLI;
- the site window: profile, navigation, zoom, user agent, downloads, the error page and Tailscale hint, and rejecting a self-signed certificate;
- the dashboard: single instance, launching detached, raising instead of duplicating, the running indicator, search, reloading on file change, ＋ Add site, the ★ Shortcuts start page, category columns, collapse memory, Add to Desktop, and `.desktop` Keywords.
