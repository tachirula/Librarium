# src/librarium/service/providers/discord_activity_type.py

"""
Optional: force the Discord activity type (Playing / Watching /
Listening / ...) by subclassing pypresence.Presence and injecting the
'type' field into the SET_ACTIVITY payload before it is sent.

Caveat: Discord may silently ignore this for unverified RPC apps and
fall back to "Playing". Test in your own client before relying on it.
"""

from __future__ import annotations

from pypresence import Presence


# Discord activity types
PLAYING = 0
STREAMING = 1
LISTENING = 2
WATCHING = 3
COMPETING = 5


class TypedPresence(Presence):
    """Presence subclass that injects `type` into every SET_ACTIVITY."""

    activity_type: int = PLAYING

    def send_data(self, op, payload):
        if op == 1 and isinstance(payload, dict):
            activity = payload.get("args", {}).get("activity")
            if isinstance(activity, dict):
                activity["type"] = self.activity_type
        return super().send_data(op, payload)