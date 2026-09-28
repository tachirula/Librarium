# src/librarium/service/providers/assets/manager.py

"""
Asset resolution. In Discord RPC apps that aren't verified, `large_image`
only accepts keys registered in the Developer Portal - external URLs are
rejected. So the only resolver that works today is the static one.
"""

from __future__ import annotations

from librarium.config.book_metadata import BookMetadata
from librarium.service.providers.assets.base import Asset, AssetResolver
from librarium.service.providers.assets.static import StaticAssetResolver


class AssetManager:
    def __init__(self, resolvers: list[AssetResolver] | None = None):
        self.resolvers = resolvers or [StaticAssetResolver()]
        self._cache: dict[str, Asset] = {}

    def resolve(self, book: BookMetadata) -> Asset | None:
        cache_key = book.source_url
        if cache_key in self._cache:
            return self._cache[cache_key]

        for resolver in self.resolvers:
            asset = resolver.resolve(book)
            if asset is not None:
                self._cache[cache_key] = asset
                return asset

        return None