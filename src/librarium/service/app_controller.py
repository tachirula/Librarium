# src/librarium/service/app_controller.py

"""
Central orchestrator. Owns the Discord connection, the reading tracker
and the asset resolver chain.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from librarium.service.providers.assets import AssetManager
from librarium.service.providers.discord_presence_service import (
    DiscordPresenceService,
)
from librarium.service.providers.tracker_service import TrackerService


DEFAULT_DETAILS = "Librarium v0.1.0"
WAITING_STATE = "Waiting for a PDF..."

# Discord accepts 2..128 characters for details/state.
MAX_FIELD_LEN = 128
MIN_FIELD_LEN = 2

# Discord rate-limits presence updates; don't push more often than this
# while the user is flipping pages.
MIN_UPDATE_INTERVAL = 15.0


def _clip(text: str, fallback: str) -> str:
    """Normalize whitespace and keep the text inside Discord's limits."""
    text = " ".join((text or "").split())
    if len(text) < MIN_FIELD_LEN:
        return fallback
    if len(text) > MAX_FIELD_LEN:
        return text[: MAX_FIELD_LEN - 1].rstrip() + "…"
    return text


class AppController:
    def __init__(self):
        self.discord_service = DiscordPresenceService()
        self.tracker = TrackerService()
        self.assets = AssetManager()

        self._last_signature = None
        self._current_url: str | None = None
        self._session_started: datetime | None = None
        self._last_sent: float = float("-inf")

    # ---------------------- internals ----------------------

    def _can_send(self) -> bool:
        return time.monotonic() - self._last_sent >= MIN_UPDATE_INTERVAL

    def _send(
        self,
        details: str,
        state: str,
        large_image: str | None = None,
        large_text: str | None = None,
        start: int | None = None,
    ) -> None:
        self.discord_service.update_presence(
            details=_clip(details, DEFAULT_DETAILS),
            state=_clip(state, "Reading"),
            large_image=large_image,
            large_text=large_text,
            start=start,
        )
        self._last_sent = time.monotonic()

    # ---------------------- lifecycle ----------------------

    def start(self):
        print("Starting services...", flush=True)
        self.discord_service.connect()
        self.tracker.start()
        # Direct call: the initial presence does not delay the first PDF.
        self.discord_service.update_presence(
            details=DEFAULT_DETAILS,
            state=WAITING_STATE,
        )

    def set_manual_presence(self, details: str, state: str) -> None:
        """Used by the `libra state` / `libra details` IPC commands.

        Stays on screen until the next real change (page turn, new book
        or PDF closed) triggers a normal update.
        """
        self._send(details=details, state=state)

    def update_loop(self):
        session = self.tracker.active_session()

        # --- no PDF open ---
        if session is None:
            if self._last_signature is not None and self._can_send():
                self._last_signature = None
                self._current_url = None
                self._session_started = None
                self._send(details=DEFAULT_DETAILS, state=WAITING_STATE)
            return

        # --- timer resets when the user switches books ---
        if session.book.source_url != self._current_url:
            self._current_url = session.book.source_url
            self._session_started = datetime.now(timezone.utc)

        # --- avoid spamming Discord when nothing changed ---
        sig = (
            session.book.title,
            session.book.author,
            session.progress.current_page,
            session.progress.total_pages,
        )
        if sig == self._last_signature:
            return

        # --- respect Discord's rate limit; retried on the next loop ---
        if not self._can_send():
            return
        self._last_signature = sig

        # --- resolve asset (book cover or fallback) ---
        asset = self.assets.resolve(session.book)

        # --- build state line ---
        if session.progress.total_pages > 0:
            state = (
                f"Page {session.progress.current_page} / "
                f"{session.progress.total_pages} "
                f"({session.progress.percent():.0f}%)"
            )
        else:
            state = "Reading"

        self._send(
            details=session.book.display_name(),
            state=state,
            large_image=asset.url if asset else None,
            large_text=asset.text if asset else None,
            start=int(self._session_started.timestamp()) if self._session_started else None,
        )

    def stop(self):
        self.discord_service.close()
