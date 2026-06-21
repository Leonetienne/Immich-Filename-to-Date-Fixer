#!python3
"""Filename-based date extraction.

To support a new filename format, add a class inheriting from DateExtractor
and implement matches() and extract(). Nothing else needs to change: every
DateExtractor subclass is picked up automatically by parse_filename_dt()
via DateExtractor.__subclasses__(), in descending `priority` order.

Give a higher `priority` to formats that are more specific (e.g. ones that
include a time-of-day), so they get tried before generic fallbacks like a
bare YYYYMMDD anywhere in the filename. The first extractor whose matches()
returns True "claims" the filename: if its extract() then fails (e.g. an
invalid month/day), parsing stops there rather than falling through to a
lower-priority extractor.
"""
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path


class DateExtractor(ABC):
    priority = 0

    @abstractmethod
    def matches(self, filename: str) -> bool:
        """Returns whether this extractor should attempt to parse filename."""

    @abstractmethod
    def extract(self, filename: str, tz: timezone):
        """Returns (datetime, has_time), or (None, False) if invalid."""


class FullDateTimeExtractor(DateExtractor):
    """YYYYMMDD_HHMMSS or YYYYMMDD-HHMMSS, e.g. IMG_20230312_130300_383.jpg"""

    priority = 10
    PATTERN = re.compile(r"(\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})")

    def matches(self, filename: str) -> bool:
        return self.PATTERN.search(filename) is not None

    def extract(self, filename: str, tz: timezone):
        year, month, day, hour, minute, second = (
            int(g) for g in self.PATTERN.search(filename).groups()
        )

        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=tz), True
        except ValueError:
            return None, False


class WhatsAppCaptionExtractor(DateExtractor):
    """WhatsApp "Save Image" filename, e.g. WhatsApp Image 2026-06-22 at 14.37.05.jpeg"""

    priority = 10
    PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2}) at (\d{2})\.(\d{2})\.(\d{2})")

    def matches(self, filename: str) -> bool:
        return self.PATTERN.search(filename) is not None

    def extract(self, filename: str, tz: timezone):
        year, month, day, hour, minute, second = (
            int(g) for g in self.PATTERN.search(filename).groups()
        )

        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=tz), True
        except ValueError:
            return None, False


class DateOnlyExtractor(DateExtractor):
    """Bare YYYYMMDD fallback, e.g. IMG-20230312-WA0042.jpg"""

    priority = 0
    PATTERN = re.compile(r"(\d{4})(\d{2})(\d{2})")

    def matches(self, filename: str) -> bool:
        return self.PATTERN.search(filename) is not None

    def extract(self, filename: str, tz: timezone):
        year, month, day = (int(g) for g in self.PATTERN.search(filename).groups())

        try:
            return datetime(year, month, day, 12, 0, 0, tzinfo=tz), False
        except ValueError:
            return None, False


def parse_filename_dt(filename: str, tz: timezone):
    """Returns (datetime, has_time) or (None, False)."""
    name = Path(filename).name

    extractors = sorted(
        (cls() for cls in DateExtractor.__subclasses__()),
        key=lambda extractor: -extractor.priority,
    )

    for extractor in extractors:
        if extractor.matches(name):
            return extractor.extract(name, tz)

    return None, False
