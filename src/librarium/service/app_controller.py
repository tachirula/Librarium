# src/librarium/service/app_controller.py

"""
Central orchestrator. Owns the Discord connection, the reading tracker
and the asset resolver chain.
"""

from __future__ import annotations

from datetime import datetime, timezone

from librarium.service.providers.assets import AssetManager
from librarium.service.providers.discord_presence_service import (
    DiscordPresenceService,
)
from librarium.service.providers.tracker_service import TrackerService


WAITING_STATE = "Waiting for a PDF..."


class AppController:
    def __init__(self):
        self.discord_service = DiscordPresenceService()
        self.tracker = TrackerService()
        self.assets = AssetManager()

        self._last_signature = None
        self._current_url: str | None = None
        self._session_started: datetime | None = None

    def start(self):
        print("Starting services...", flush=True)
        self.discord_service.connect()
        self.tracker.start()
        self.discord_service.update_presence(
            details="Librarium v0.1.0",
            state=WAITING_STATE,
        )

    def update_loop(self):
        session = self.tracker.active_session()

        # --- no PDF open ---
        if session is None:
            if self._last_signature is not None:
                self._last_signature = None
                self._current_url = None
                self._session_started = None
                self.discord_service.update_presence(
                    details="Librarium v0.1.0",
                    state=WAITING_STATE,
                )
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

        self.discord_service.update_presence(
            details=session.book.display_name(),
            state=state,
            large_image=asset.url if asset else None,
            large_text=asset.text if asset else None,
            start=int(self._session_started.timestamp()) if self._session_started else None,
        )

    def stop(self):
        self.discord_service.close()