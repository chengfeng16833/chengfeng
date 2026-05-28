"""Track the current journey round.

The training hub shows no explicit turn counter — only a date like "3月下旬"
(the prominent top-left "4" is a *countdown* to the next 评鉴战, and its stylised
glyph isn't OCR-readable anyway). So we count rounds by watching the date advance:
each change of the date = one new round.

We canonicalise the OCR'd date to "<month>月<上|中|下>" so that:
  - a leading search-icon glyph or stray spaces don't cause a false advance, and
  - a read that drops the month digit (e.g. "月下旬") is treated as unknown and
    never advances (avoids 3月上旬 vs 4月上旬 colliding when the digit is missing).
"""
from __future__ import annotations

import re

_DATE_RE = re.compile(r"(\d{1,2})\s*月\s*([上中下])\s*旬")


def _canonical_date(date: str | None) -> str | None:
    if not date:
        return None
    match = _DATE_RE.search(date)
    if match is None:
        return None
    return f"{int(match.group(1))}月{match.group(2)}"


class RoundTracker:
    """current_round is None until the first parseable date, then 1, and +1 on
    every date change. reset() clears it for a new journey."""

    def __init__(self) -> None:
        self._last_date: str | None = None
        self._round = 0

    def reset(self) -> None:
        self._last_date = None
        self._round = 0

    @property
    def current_round(self) -> int | None:
        return self._round or None

    def observe_date(self, date: str | None) -> int | None:
        """Feed the latest OCR'd hub date; returns the (possibly updated) round."""
        canonical = _canonical_date(date)
        if canonical is None:
            return self.current_round
        if canonical != self._last_date:
            self._last_date = canonical
            self._round += 1
        return self.current_round
