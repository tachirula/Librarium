<p align="center">
  <img src="docs/banner.png" alt="Librarium banner" width="420">
</p>

# Librarium

[![License: GPL-3.0](https://img.shields.io/github/license/tachirula/Librarium?color=blue)](LICENSE)
[![Status: experimental](https://img.shields.io/badge/status-experimental-orange)](#librarium)
[![Python 3](https://img.shields.io/badge/python-3-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-FCC624?logo=linux&logoColor=black)](#install)
[![Chromium via CDP](https://img.shields.io/badge/Chromium-CDP-4285F4?logo=googlechrome&logoColor=white)](https://chromedevtools.github.io/devtools-protocol/)
[![Discord Rich Presence](https://img.shields.io/badge/Discord-Rich%20Presence-5865F2?logo=discord&logoColor=white)](https://discord.com/developers/docs/rich-presence/overview)
[![Last commit](https://img.shields.io/github/last-commit/tachirula/Librarium)](https://github.com/tachirula/Librarium/commits)
[![Stars](https://img.shields.io/github/stars/tachirula/Librarium?style=flat)](https://github.com/tachirula/Librarium/stargazers)

A Discord Rich Presence integration that shows what local PDF you're reading in a Chromium-based browser, in real time. Built as a technical experiment around the Chrome DevTools Protocol (CDP) and the browser's built-in PDF viewer.

> **Status: experimental.** This is a working technical demo, not a polished product. It targets Chromium browsers (Brave, Chrome, Chromium, Edge) on Linux with XDG-compliant desktops. It was developed and tested with Brave; the other browsers are patched the same way but are untested. It is published as a reference for the CDP technique and the daemon/patch architecture, not as an end-user application.

---

## Why this exists

Discord Rich Presence apps typically ask the user to install a browser extension or a companion app. Librarium takes a different route: it detects the PDF you're reading by talking to the browser over the Chrome DevTools Protocol, **without any extension**. The tricky part is that Chromium's built-in PDF viewer runs inside its own `chrome-extension://` frame, which a regular extension content script can't reach. CDP can attach to that frame directly and evaluate JavaScript inside it, which is enough to read the viewer's page counter.

The other design problem is the CDP flag. Chromium refuses WebSocket connections to its debug port unless the origin is allowlisted, and launching the browser with the flag requires touching its launcher. Librarium solves this by patching the browser's `.desktop` file while the daemon runs, and restoring it on any reasonable shutdown path, including `SIGINT`, `SIGTERM`, and stale-patch cleanup on the next start.

---

## What works

- PDF detection in Chromium browsers via CDP. No browser extension.
- Book metadata parsed from the filename (title, author, publisher when the naming convention is `Title -- Author -- Publisher -- ...`).
- Live page tracking: current page, total pages, percentage, timer.
- Reversible browser integration: the `.desktop` patch is applied by the daemon on start and removed on stop, signal, or `atexit`. If you already have a personal override of the launcher, it is backed up and put back on restore.
- Background daemon with Unix-socket IPC, so the CLI is instant.

## Limitations and open questions

- **Firefox and Safari.** They don't speak CDP.
- **Only local PDFs.** Tabs must be `file://...pdf`, and only the first open one is tracked.
- **Discord activity type.** The card shows "Playing". Whether an unverified app can use other types (Watching, Listening, ...) has not been confirmed yet. `discord_activity_type.py` is an attempt to inject the `type` field by hand; recent `pypresence` versions expose `activity_type` directly on `update()`.
- **Dynamic book covers.** Not implemented. The card uses a static asset registered in the Developer Portal under the key `book`. Discord's documentation describes external image URLs (https only) as supported for `large_image`, so per-book covers should be possible, but this has not been validated with this app yet.
- **Wayland.** The browser patch targets XDG `.desktop` files, so it should work, but it has only been tested under X11.

---

## Install

```bash
git clone https://github.com/tachirula/Librarium.git
cd Librarium
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Use

Fully quit your browser once after the first `libra start` so it picks up the CDP flag. Reopen it from the menu (not the terminal), then open any local PDF.

```bash
libra start           # spawn the daemon in the background
libra status          # check whether it's running
libra stop            # stop the daemon (restores the browser launcher)
```

Optional manual overrides of the Discord card:

```bash
libra state "text"    # replace the 'state' line
libra details "text"  # replace the 'details' line
```

The override stays until the next real change (page turn, another book, or the PDF being closed).

> **Note:** `libra stop` restores the launcher, but a browser that is already running keeps its debug port open until you fully quit it.

### Debug

```bash
libra start -F        # foreground, verbose logs
libra setup-browser   # apply the patch without starting the daemon
libra restore-browser # remove the patch manually
```

## Uninstall

```bash
libra stop            # stop the daemon and restore the browser launcher
pip uninstall librarium
```

Then delete the folder you cloned the repository into. If your browser was started while the patch was active, quit it fully so the debug port closes.

If the daemon is ever killed with `SIGKILL`, the next `libra` command detects the stale `.desktop` patch and removes it automatically.

---

## How it works

1. `libra start` spawns a daemon that:
   - Opens a Unix socket at `$XDG_RUNTIME_DIR/librarium-<uid>.sock` (falling back to a private `~/.cache/librarium/` directory if `XDG_RUNTIME_DIR` is not set), restricted to your user.
   - Patches the browser's `.desktop` entry to launch with `--remote-debugging-port=9222 --remote-allow-origins=http://localhost:9222`. If you already have a personal override of that launcher in `~/.local/share/applications/`, it is moved to `<name>.librarium-bak`, used as the base for the patch (so your own flags survive), and moved back on restore. Files created by Librarium end with a `# Librarium-managed` comment, and only those are ever deleted.
   - Connects to Discord via `pypresence`.
2. Every second, the tracker queries `http://localhost:9222/json`, filters targets of type `page` with a `file://*.pdf` URL, and finds the nested viewer target whose URL starts with `chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/`.
3. It opens a WebSocket to that viewer (only if the URL points at the local debug port) and runs a small script that walks the viewer's shadow roots to read `#pagelength` and `#pageSelector`.
4. `AppController` builds a payload from the filename metadata plus the current/total pages, and updates Discord. Updates are limited to one every 15 seconds and text fields are clipped to Discord's 128-character limit.
5. On shutdown, the daemon restores the `.desktop` file and closes the Discord connection.

---

## Security notes

- **Where the port listens.** The debug port is opened by Chromium, not by Librarium. Chromium listens on loopback (`127.0.0.1`) by default, and Librarium does not change that. You can check it yourself with `ss -ltnp | grep 9222` while the browser is running.
- **What `--remote-allow-origins` does and doesn't do.** It restricts which *web origins* may open a DevTools WebSocket. Websites cannot spoof the `Origin` header that Chromium enforces, so no web page can talk to the debug port. It does **not** filter clients that send no `Origin` header, such as any local process. While the browser runs with the patch, any local process or user on the machine can control it (including reading cookies and sessions). That is usually fine on a single-user desktop; think twice on a shared one.
- **The patch is temporary, the port might not be.** After `libra stop`, an already-running browser keeps the port open until it is fully quit. After a crash or `SIGKILL`, the launcher patch stays until the next `libra` command cleans it up.
- **IPC.** The daemon's Unix socket is created with `0600` permissions and only accepts a small set of fixed commands.

## Privacy

What is sent to Discord: the title and author parsed from the file name, the current/total page numbers, and the session timer. The file path is never sent.

---

## Project structure

```text
Librarium/
├── src/librarium/
│   ├── cli/                    Thin client + Unix-socket helper
│   ├── config/                 BookMetadata parser
│   ├── service/
│   │   ├── daemon.py           Daemon lifecycle, IPC, browser patch
│   │   ├── app_controller.py   Orchestrator
│   │   └── providers/
│   │       ├── browser_patcher.py            .desktop patch + restore
│   │       ├── tracker_service.py            CDP scraper
│   │       ├── discord_presence_service.py
│   │       ├── discord_activity_type.py
│   │       └── assets/                       Static asset resolution
│   └── main.py                 Entry point / subcommand dispatcher
├── docs/
├── LICENSE
├── pyproject.toml
├── README.md
└── requirements.txt
```

---

## Technical notes

- **Shadow DOM.** The PDF viewer's UI is built from web components with shadow roots, so a plain `document.querySelector('#pagelength')` finds nothing. The scraper walks the tree with `el.shadowRoot`, which relies on those roots being open. If Chromium ever closes them, the fallback would be the CDP `DOM` domain (`DOM.getDocument` with `pierce: true`), which can traverse closed roots too.
- **Target tree.** The PDF tab appears as three CDP targets:
  - the shell (`type=page`, `file://`),
  - the viewer (`type=iframe`, `chrome-extension://`),
  - the document (`type=iframe`, `file://`).

  The viewer is the one with the DOM; the shell is the one with the filename.
- **Snap installs.** Brave on Ubuntu installs via Snap; its `.desktop` lives under `/var/lib/snapd/desktop/applications/`. The patcher checks both paths, and only ever writes to `~/.local/share/applications/`, so no root is needed.

---

## License

GPL-3.0. You're free to use, modify, audit, and redistribute this software (or derivatives), including commercially, as long as any distributed version stays under the same license and keeps its source public. See [LICENSE](LICENSE).
