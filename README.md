# Librarium

[![Status: experimental](https://img.shields.io/badge/status-experimental-orange)](#librarium)
[![Python 3](https://img.shields.io/badge/python-3-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-FCC624?logo=linux&logoColor=black)](#install)
[![Chromium via CDP](https://img.shields.io/badge/Chromium-CDP-4285F4?logo=googlechrome&logoColor=white)](https://chromedevtools.github.io/devtools-protocol/)
[![Discord Rich Presence](https://img.shields.io/badge/Discord-Rich%20Presence-5865F2?logo=discord&logoColor=white)](https://discord.com/developers/docs/rich-presence/overview)

A Discord Rich Presence integration that shows what PDF you're reading in a Chromium-based browser, in real time. Built as a technical experiment around the Chrome DevTools Protocol (CDP) and the browser's built-in PDF viewer.

> **Status: experimental.** This is a working technical demo, not a polished product. It only supports Chromium browsers (Brave, Chrome, Chromium, Edge, Opera) on Linux with XDG-compliant desktops. It is published as a reference for the CDP technique and the daemon/patch architecture, not as an end-user application.

---

## Why this exists

Discord Rich Presence apps typically ask the user to install a browser extension or a companion app. Librarium takes a different route: it detects the PDF you're reading by talking to the browser over the Chrome DevTools Protocol, **without any extension**. The tricky part is that Chromium's built-in PDF viewer lives inside a closed shadow root under a `chrome-extension://` iframe, so a normal content script cannot read it. CDP can.

The other design problem is the CDP flag. Chromium refuses WebSocket connections to its debug port unless the origin is allowlisted, and launching the browser with the flag requires touching its launcher. Librarium solves this by patching the browser's `.desktop` file while the daemon runs, and restoring it on any reasonable shutdown path, including `SIGINT`, `SIGTERM`, and stale-patch cleanup on the next start.

---

## What works

- PDF detection in Chromium browsers via CDP. No browser extension.
- Book metadata parsed from the filename (title, author, publisher when the naming convention is `Title -- Author -- Publisher -- ...`).
- Live page tracking: current page, total pages, percentage, timer.
- Reversible browser integration: the `.desktop` patch is applied by the daemon on start and removed on stop, signal, or `atexit`.
- Background daemon with Unix-socket IPC, so the CLI is instant.

## What doesn't

- **Firefox and Safari.** They don't speak CDP.
- **Discord activity type.** The card always shows "Playing". Discord ignores the `type` field for unverified RPC apps.
- **Dynamic book covers.** Discord rejects external URLs as `large_image` for unverified apps. The icon is a static asset registered in the Developer Portal under the key `book`.
- **Wayland.** The browser patch targets XDG `.desktop` files, so it works, but it has only been tested under X11.

---

## Install

```bash
git clone https://github.com/Hashiruta/Librarium.git
cd Librarium
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Use

```bash
libra start           # spawn the daemon in the background
libra status          # check whether it's running
libra stop            # stop the daemon (restores the browser)
```

Fully quit your browser once after the first `libra start` so it picks up the CDP flag. After that, just open any local PDF.

### Debug

```bash
libra start -F        # foreground, verbose logs
libra setup-browser   # apply the patch without starting the daemon
libra restore-browser # remove the patch manually
```

## Uninstall

```bash
libra stop            # stop the daemon and restore the browser
pip uninstall librarium
rm -rf ~/Librarium
```

If the daemon is ever killed with `SIGKILL`, the next `libra` command detects the stale `.desktop` patch and removes it automatically.

---

## How it works

1. `libra start` spawns a daemon that:
   - Patches the browser's `.desktop` entry to launch with `--remote-debugging-port=9222 --remote-allow-origins=http://localhost:9222`.
   - Opens a Unix socket at `$XDG_RUNTIME_DIR/librarium-<uid>.sock`.
   - Connects to Discord via `pypresence`.
2. Every second, the tracker queries `http://localhost:9222/json`, filters targets of type `page` with a `file://*.pdf` URL, and finds the nested viewer target whose URL starts with `chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/`.
3. It opens a WebSocket to that viewer and runs a small script that pierces the shadow DOM to read `#pagelength` and `#pageSelector`.
4. `AppController` builds a payload from the filename metadata plus the current/total pages, and updates Discord.
5. On shutdown, the daemon restores the `.desktop` file and closes the Discord connection.

The `--remote-allow-origins` value is scoped to `localhost:9222`, not `*`. Websites cannot spoof the `Origin` header that Chromium sends, so no external page can talk to the debug port while the daemon is running.

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

- **Closed shadow roots.** The Chromium PDF viewer uses `<template shadowrootmode="closed">`, which no content script can pierce. CDP can, because `Runtime.evaluate` runs with the privileges of the DevTools frontend.
- **Target tree.** The PDF tab appears as three CDP targets:
  - the shell (`type=page`, `file://`),
  - the viewer (`type=iframe`, `chrome-extension://`),
  - the document (`type=iframe`, `file://`).

  The viewer is the one with the DOM; the shell is the one with the filename.
- **Snap installs.** Brave on Ubuntu installs via Snap; its `.desktop` lives under `/var/lib/snapd/desktop/applications/`. The patcher checks both paths.

---

## License

GPL-3.0. You're free to use, modify, audit, and redistribute this software (or derivatives), including commercially, as long as any distributed version stays under the same license and keeps its source public. See [LICENSE](LICENSE).
