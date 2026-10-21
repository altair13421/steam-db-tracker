"""Digest service — builds a weekly (or N-day) digest data structure."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, List, Optional

from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from ..models import AppSnapshot, Change, NewsPost, TrackedApp

log = logging.getLogger("tracker.digest")


@dataclass
class AppDigest:
    app: TrackedApp
    n_price_drops: int = 0
    n_price_hikes: int = 0
    n_new_discounts: int = 0
    n_discount_ends: int = 0
    n_app_updates: int = 0
    n_news: int = 0
    lowest_price: Optional[int] = None
    lowest_price_at = None
    highest_discount: int = 0
    last_update_at = None
    last_update_url: str = ""

    @property
    def lowest_price_display(self) -> Optional[str]:
        if self.lowest_price is None:
            return None
        currency = self.app.cached_currency or ""
        return f"{self.lowest_price / 100:.2f} {currency}".strip()

    @property
    def total_changes(self) -> int:
        return (self.n_price_drops + self.n_price_hikes +
                self.n_new_discounts + self.n_discount_ends +
                self.n_app_updates + self.n_news)


@dataclass
class DigestReport:
    days: int
    since: "timezone.datetime"
    apps: List[AppDigest] = field(default_factory=list)
    total_changes: int = 0
    total_news: int = 0


def build_digest(days: int = 7) -> DigestReport:
    """Build a digest report over the last `days` days."""
    now = timezone.now()
    since = now - timedelta(days=days)

    changes_qs = Change.objects.filter(detected_at__gte=since)
    news_qs = NewsPost.objects.filter(date__gte=since)

    # Per-app aggregates.
    apps: List[AppDigest] = []
    for app in TrackedApp.objects.all().order_by("cached_name", "appid"):
        ad = AppDigest(app=app)
        # Change counts per type.
        changes_for_app = changes_qs.filter(app=app)
        ad.n_price_drops = changes_for_app.filter(
            change_type=Change.Type.PRICE_DROP).count()
        ad.n_price_hikes = changes_for_app.filter(
            change_type=Change.Type.PRICE_HIKE).count()
        ad.n_new_discounts = changes_for_app.filter(
            change_type=Change.Type.NEW_DISCOUNT).count()
        ad.n_discount_ends = changes_for_app.filter(
            change_type=Change.Type.DISCOUNT_END).count()
        ad.n_app_updates = changes_for_app.filter(
            change_type=Change.Type.APP_UPDATE).count()
        ad.n_news = changes_for_app.filter(
            change_type=Change.Type.NEW_NEWS).count()

        # Lowest price + highest discount across snapshots in the window.
        snaps = AppSnapshot.objects.filter(
            app=app, fetched_at__gte=since,
        ).order_by("fetched_at")
        for s in snaps:
            if s.price_final and (ad.lowest_price is None
                                   or s.price_final < ad.lowest_price):
                ad.lowest_price = s.price_final
                ad.lowest_price_at = s.fetched_at
            if s.discount_percent > ad.highest_discount:
                ad.highest_discount = s.discount_percent

        # Latest app_update + URL hint.
        last_update_change = changes_for_app.filter(
            change_type=Change.Type.APP_UPDATE
        ).order_by("-detected_at").first()
        if last_update_change:
            ad.last_update_at = last_update_change.detected_at
            if last_update_change.note.startswith("http"):
                ad.last_update_url = last_update_change.note

        apps.append(ad)

    return DigestReport(
        days=days,
        since=since,
        apps=apps,
        total_changes=changes_qs.count(),
        total_news=news_qs.count(),
    )
