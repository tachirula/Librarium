# src/librarium/config/book_metadata.py

"""
Static metadata of the document currently being read. Populated once
when a reading session starts and never mutated afterwards.

Sources of information, in priority order:
  1. The browser tab title (most reliable - PDFs embed their own title).
  2. The filename in the file:// URL (fallback when the tab title is
     generic like "document.pdf" or the viewer sets it to something
     unhelpful).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


# Anna's Archive and similar catalogs use " -- " to separate fields in
# the filename, e.g.:
#   "Sumérgete en los patrones de diseño -- Alexander Shvets -- Refactoring_Guru -- <hash> -- Anna's Archive.pdf"
_SEPARATOR = re.compile(r"\s+--\s+")


@dataclass(frozen=True)
class BookMetadata:
    title: str
    total_pages: int
    source_url: str
    author: str | None = None
    publisher: str | None = None

    @classmethod
    def from_url(cls, url: str, total_pages: int) -> "BookMetadata":
        """Build metadata from a file:// URL and a page count.

        The page count comes from the DOM (the <span id="pagelength">
        element in the web viewer), so the caller is responsible for
        scraping it before calling this constructor.
        """
        parsed = urlparse(url)
        raw_path = unquote(parsed.path)
        stem = Path(raw_path).stem          # drop directories and ".pdf"

        title, author, publisher = _split_filename(stem)
        return cls(
            title=title,
            author=author,
            publisher=publisher,
            total_pages=total_pages,
            source_url=url,
        )

    def display_name(self) -> str:
        """Human-friendly label for Discord's 'details' field."""
        if self.author:
            return f"{self.title} — {self.author}"
        return self.title


def _humanize(text: str) -> str:
    """Turn filename-safe text into something readable in Discord.

    'Allen_B._Downey' -> 'Allen B. Downey'
    'The_Little_Book' -> 'The Little Book'
    """
    text = text.replace("_", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def _split_filename(stem: str) -> tuple[str, str | None, str | None]:
    """Best-effort parse of a filename into (title, author, publisher).

    Handles these forms gracefully:
      "Title -- Author -- Publisher -- extra -- extra"
      "Title -- Author"
      "Title"
      "my_notes"
    """
    parts = [p.strip() for p in _SEPARATOR.split(stem) if p.strip()]
    if not parts:
        return _humanize(stem), None, None

    title = _humanize(parts[0])
    author = _humanize(parts[1]) if len(parts) > 1 else None
    publisher = _humanize(parts[2]) if len(parts) > 2 else None
    return title, author, publisher