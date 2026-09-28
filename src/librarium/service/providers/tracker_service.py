# src/librarium/service/providers/tracker_service.py

"""
Reads the currently-open PDF from a Chromium browser via the Chrome
DevTools Protocol (CDP).

The DOM of the PDF viewer lives in a chrome-extension:// iframe nested
under the file:// tab, so we need to look up that nested target instead
of scraping the shell page directly.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import websocket  # from websocket-client

from librarium.config.book_metadata import BookMetadata


CDP_ENDPOINT = "http://localhost:9222/json"
CDP_TIMEOUT = 5.0
CDP_ERROR_LOG_INTERVAL = 30.0
WS_ERROR_LOG_INTERVAL = 30.0

# Brave/Chrome PDF viewer extension ID
PDF_VIEWER_PREFIX = "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/"


_SCRAPE_JS = r"""
(() => {
  const out = { url: location.href, title: document.title };

  function deepQuery(sel, root = document) {
    const direct = root.querySelector(sel);
    if (direct) return direct;
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) {
        const found = deepQuery(sel, el.shadowRoot);
        if (found) return found;
      }
    }
    return null;
  }

  const totalEl = deepQuery('#pagelength');
  const pageEl = deepQuery('#pageSelector');

  const total = totalEl ? parseInt(totalEl.textContent.replace(/\D/g, ''), 10) : 0;
  const current = pageEl ? parseInt(pageEl.value, 10) : 0;

  out.total = Number.isNaN(total) ? 0 : total;
  out.current = Number.isNaN(current) ? 0 : current;
  out.found_total = !!totalEl;
  out.found_page = !!pageEl;

  if (!totalEl) {
    out.debug = {
      bodyChildren: [...document.body.children].map(c => c.tagName).slice(0, 20),
      hasPdfViewer: !!document.querySelector('pdf-viewer'),
      hasEmbed: !!document.querySelector('embed'),
      hasIframe: !!document.querySelector('iframe'),
      htmlLength: document.documentElement.outerHTML.length,
      bodyStart: document.body.innerHTML.slice(0, 300),
    };
  }

  return JSON.stringify(out);
})()
"""


@dataclass(frozen=True)
class ReadingProgress:
    current_page: int
    total_pages: int
    started_at: datetime

    def percent(self) -> float:
        if self.total_pages <= 0:
            return 0.0
        return (self.current_page / self.total_pages) * 100.0


@dataclass(frozen=True)
class ReadingSession:
    book: BookMetadata
    progress: ReadingProgress


# ---------------------- CDP helpers ----------------------

def _list_targets() -> Optional[list[dict]]:
    try:
        with urllib.request.urlopen(CDP_ENDPOINT, timeout=CDP_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _find_pdf_viewer(shell: dict, targets: list[dict]) -> Optional[dict]:
    """Return the chrome-extension:// viewer target nested under `shell`."""
    shell_id = shell.get("id")
    for t in targets:
        if t.get("parentId") != shell_id:
            continue
        if t.get("url", "").startswith(PDF_VIEWER_PREFIX):
            return t
    return None


def _evaluate(tab: dict, error_sink: list[str]) -> Optional[dict]:
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        error_sink.append("target has no webSocketDebuggerUrl")
        return None

    try:
        ws = websocket.create_connection(
            ws_url,
            timeout=CDP_TIMEOUT,
            origin="http://localhost:9222",
            suppress_origin=False,
        )
    except Exception as e:
        error_sink.append(f"WS connect failed: {e}")
        return None

    try:
        msg_id = 1
        ws.send(json.dumps({
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": _SCRAPE_JS,
                "returnByValue": True,
                "awaitPromise": False,
            },
        }))

        for _ in range(30):
            raw = ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            msg = json.loads(raw)
            if msg.get("id") != msg_id:
                continue
            result = msg.get("result", {}).get("result", {})
            value = result.get("value")
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    error_sink.append("scrape returned invalid JSON")
                    return None
            error_sink.append("evaluate returned no value")
            return None
        error_sink.append("no response with matching id")
        return None
    except Exception as e:
        error_sink.append(f"evaluate failed: {e}")
        return None
    finally:
        try:
            ws.close()
        except Exception:
            pass


# ---------------------- public service ----------------------

class TrackerService:
    def __init__(self) -> None:
        self._started_at: Optional[datetime] = None
        self._last_debug_log: Optional[str] = None
        self._last_cdp_error_log_at: float = 0.0
        self._last_ws_error_log_at: float = 0.0
        self._cdp_was_down: bool = False

    def start(self) -> None:
        pass

    def active_session(self) -> Optional[ReadingSession]:
        targets = _list_targets()

        if targets is None:
            now = time.monotonic()
            if now - self._last_cdp_error_log_at >= CDP_ERROR_LOG_INTERVAL:
                print(
                    f"[tracker] CDP unreachable at {CDP_ENDPOINT} "
                    f"(browser closed or not launched with CDP).",
                    flush=True,
                )
                self._last_cdp_error_log_at = now
                self._cdp_was_down = True
            self._started_at = None
            return None

        if self._cdp_was_down:
            print("[tracker] CDP reachable again.", flush=True)
            self._cdp_was_down = False

        # Find file://*.pdf shells
        shells = [
            t for t in targets
            if t.get("type") == "page"
            and t.get("url", "").lower().startswith("file://")
            and t.get("url", "").lower().endswith(".pdf")
        ]
        if not shells:
            self._started_at = None
            return None

        shell = shells[0]
        viewer = _find_pdf_viewer(shell, targets)

        if viewer is None:
            # Fallback: scrape the shell itself (may work for other viewers)
            viewer = shell

        errors: list[str] = []
        data = _evaluate(viewer, errors)

        if errors:
            now = time.monotonic()
            if now - self._last_ws_error_log_at >= WS_ERROR_LOG_INTERVAL:
                for err in errors:
                    print(f"[tracker] {err}", flush=True)
                self._last_ws_error_log_at = now
            return None

        if not data:
            return None

        total = int(data.get("total") or 0)
        current = int(data.get("current") or 0)

        if total == 0 and data.get("debug"):
            dbg = json.dumps(data["debug"])
            if dbg != self._last_debug_log:
                print(f"[tracker] scrape debug: {dbg}", flush=True)
                self._last_debug_log = dbg

        if self._started_at is None:
            self._started_at = datetime.now(timezone.utc)

        # Book name always comes from the shell's URL (file:// path)
        book = BookMetadata.from_url(shell["url"], total_pages=total)
        progress = ReadingProgress(
            current_page=current,
            total_pages=total,
            started_at=self._started_at,
        )
        return ReadingSession(book=book, progress=progress)