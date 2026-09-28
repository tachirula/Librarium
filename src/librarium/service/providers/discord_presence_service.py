# src/librarium/service/providers/discord_presence_service.py

"""
Direct communication service using the pypresence library to update
the Discord Rich Presence status.
"""

from librarium.service.providers.discord_activity_type import (
    PLAYING,
    TypedPresence,
)


# Discord Application ID for Librarium.
# Public by design: it identifies the app in Discord's backend, not the user.
DISCORD_CLIENT_ID = "1553890420973510806"

# Discord has no "Reading" activity type. PLAYING is the reliable default;
# other types (WATCHING, LISTENING) are ignored for unverified RPC apps.
ACTIVITY_TYPE = PLAYING


class DiscordPresenceService:
    def __init__(self):
        self.client_id = DISCORD_CLIENT_ID
        self.rpc = None

    def connect(self):
        try:
            self.rpc = TypedPresence(self.client_id)
            self.rpc.activity_type = ACTIVITY_TYPE
            self.rpc.connect()
            print("Connection established with Discord Rich Presence!", flush=True)
        except Exception as e:
            print(f"Error connecting to Discord: {e}", flush=True)

    def update_presence(
        self,
        details: str,
        state: str,
        large_image: str | None = None,
        large_text: str | None = None,
        start: int | None = None,
    ):
        if not self.rpc:
            return
        kwargs: dict = {"details": details, "state": state}
        if large_image is not None:
            kwargs["large_image"] = large_image
        if large_text is not None:
            kwargs["large_text"] = large_text
        if start is not None:
            kwargs["start"] = start
        try:
            self.rpc.update(**kwargs)
        except Exception as e:
            print(f"Error updating Discord status: {e}", flush=True)

    def close(self):
        if self.rpc:
            try:
                self.rpc.close()
                print("Connection with Discord closed.", flush=True)
            except Exception as e:
                print(f"Error closing the connection: {e}", flush=True)
            finally:
                self.rpc = None