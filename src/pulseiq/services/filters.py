"""Global filters shared by every service function, API endpoint and dashboard page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

PLATFORMS = ("ios", "android", "web")
CHANNELS = ("organic", "paid_social", "search", "referral", "influencer")
COUNTRY_TIERS = ("high", "mid", "low")


@dataclass(frozen=True)
class Filters:
    """Date range (inclusive) plus optional segment filters (None = all)."""

    start: date | None = None
    end: date | None = None
    platform: str | None = None
    channel: str | None = None
    country_tier: str | None = None

    def __post_init__(self) -> None:
        if self.platform is not None and self.platform not in PLATFORMS:
            raise ValueError(f"platform must be one of {PLATFORMS}")
        if self.channel is not None and self.channel not in CHANNELS:
            raise ValueError(f"channel must be one of {CHANNELS}")
        if self.country_tier is not None and self.country_tier not in COUNTRY_TIERS:
            raise ValueError(f"country_tier must be one of {COUNTRY_TIERS}")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be on or before end")

    def user_clause(self, alias: str = "u") -> tuple[str, list]:
        """SQL predicate on dim_users-like columns + parameters."""
        parts, params = ["1 = 1"], []
        for col, val in (
            ("platform", self.platform),
            ("acquisition_channel", self.channel),
            ("country_tier", self.country_tier),
        ):
            if val is not None:
                parts.append(f"{alias}.{col} = ?")
                params.append(val)
        return " and ".join(parts), params

    def date_clause(self, column: str) -> tuple[str, list]:
        """SQL predicate restricting ``column`` (a date) to the range."""
        parts, params = [], []
        if self.start:
            parts.append(f"{column} >= ?")
            params.append(self.start)
        if self.end:
            parts.append(f"{column} <= ?")
            params.append(self.end)
        return (" and ".join(parts) or "1 = 1"), params

    def previous(self) -> Filters | None:
        """The immediately preceding period of equal length (for deltas)."""
        if not (self.start and self.end):
            return None
        length = (self.end - self.start).days + 1
        return Filters(
            self.start - timedelta(days=length),
            self.start - timedelta(days=1),
            self.platform,
            self.channel,
            self.country_tier,
        )

    def with_dates(self, start: date, end: date) -> Filters:
        """Copy with a different date range."""
        return Filters(start, end, self.platform, self.channel, self.country_tier)
