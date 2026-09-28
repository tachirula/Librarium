# src/librarium/service/providers/assets/base.py

"""
Core abstractions for the asset system. An AssetResolver takes a
BookMetadata and produces a Discord-ready Asset, or returns None if it
cannot handle that book.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from librarium.config.book_metadata import BookMetadata


@dataclass(frozen=True)
class Asset:
    """A Discord Rich Presence image reference.

    `url` must be a key registered in the Discord Developer Portal
    (e.g. "book"). External URLs are rejected by Discord for RPC apps
    that aren't verified, so we don't support them here.

    `text` is the hover tooltip.
    """

    url: str
    text: str


class AssetResolver(ABC):
    @abstractmethod
    def resolve(self, book: BookMetadata) -> Asset | None:
        """Return an Asset for this book, or None if not applicable."""