# src/librarium/service/providers/assets/static.py

"""
Static resolver. Returns a fixed asset key that must exist in the
Discord Developer Portal under Rich Presence -> Art Assets.
"""

from __future__ import annotations

from librarium.config.book_metadata import BookMetadata
from librarium.service.providers.assets.base import Asset, AssetResolver


class StaticAssetResolver(AssetResolver):
    def __init__(self, key: str = "book", text: str | None = None):
        self.key = key
        self._text = text

    def resolve(self, book: BookMetadata) -> Asset:
        return Asset(url=self.key, text=self._text or "Librarium")