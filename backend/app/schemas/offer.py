"""
Pydantic schemas for the Dead Hours Engine.

This module currently carries only the SUGGESTION side of the feature — the
read-only "your Tuesday 2-5pm is your quietest stretch" analysis. The offer
window CRUD schemas land alongside these when the offer_windows table exists.

Everything here is Response-only: every value is computed server-side from
persisted invoice data and nothing in this file is ever accepted from a client.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class DeadHourWindow(BaseModel):
    """One suggested offer window: a weekday plus a wall-clock hour range.

    `start_hour`/`end_hour` are LOCAL hours in the restaurant's own timezone,
    half-open [start, end) — (14, 17) means 2pm up to but not including 5pm, and
    reads to an owner as "2-5pm". Both are always in 0..23 so the suggestion is
    directly expressible as an offer window's wall-clock start/end times.

    `median_revenue` is what a TYPICAL such window actually took: the median of
    the per-day window totals across `sample_size` same-weekdays. Median, not
    mean, for the reason daily_report_service._compare uses one — a single
    party booking must not redefine "usual".

    `day_median_revenue` is the same statistic over the whole trading day, and
    exists so the UI can render the window figure at scale. "Rs 1,240" means
    nothing on its own; "Rs 1,240 of a typical Rs 9,800 Tuesday" is a decision.
    """

    weekday: int          # Python weekday(): 0=Monday … 6=Sunday
    weekday_label: str    # "Tuesday"
    start_hour: int
    end_hour: int
    median_revenue: Decimal
    day_median_revenue: Decimal
    sample_size: int


class DeadHoursSuggestions(BaseModel):
    """The whole GET /admin/offers/suggestions payload.

    An envelope rather than a bare list, so the admin page can render an honest
    empty state. `windows == []` means "we refuse to guess", and the thresholds
    that produced that refusal (`lookback_weeks`, `min_samples`) are returned
    with it so the UI can say WHY instead of showing a blank panel.
    """

    currency: str
    timezone: str
    lookback_weeks: int
    min_samples: int
    window_hours: int
    windows: list[DeadHourWindow]
