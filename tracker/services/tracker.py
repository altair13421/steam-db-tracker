"""Tracker service — turns raw Steam API responses into Django model rows.

Public functions:
  track_one(app)        — fetch + diff + persist for a single TrackedApp.
  track_all()           — loop over every TrackedApp, throttled.
  record_new_news(app, news_items) — dedupe + persist news posts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone as dt_timezone
from typing import List

from django.utils import timezone

from ..models import TrackedApp, AppSnapshot, NewsPost, Change
from .steam_api import (
    ApiError, fetch_app_news, fetch_app_snapshot,
    NewsItem, AppSnapshot as SteamAppSnapshot,
)

log = logging.getLogger("tracker.tracker")


# --- Diff + persist --------------------------------------------------------

def _to_dt(unix_ts: int) -> "datetime | None":
    if not unix_ts:
        return None
    return datetime.fromtimestamp(unix_ts, tz=dt_timezone.utc)


def diff_and_store(app: TrackedApp, snap: SteamAppSnapshot) -> List[Change]:
    """Compare the new snapshot against the previous one; record changes.

    Always inserts the new AppSnapshot row so history stays contiguous.
    Returns the list of newly-created Change rows.
    """
    prev = app.snapshots.order_by("-fetched_at").first()
    now = timezone.now()

    # Insert the new snapshot first.
    new_snapshot = AppSnapshot.objects.create(
        app=app,
        fetched_at=now,
        currency=snap.currency,
        price_initial=snap.price_initial,
        price_final=snap.price_final,
        discount_percent=snap.discount_percent,
        last_update=snap.last_update,
    )

    # Update denormalized cache on the parent TrackedApp.
    app.cached_name = snap.name
    app.cached_currency = snap.currency
    app.cached_price_final = snap.price_final
    app.cached_price_initial = snap.price_initial
    app.cached_discount_percent = snap.discount_percent
    app.cached_last_update = snap.last_update
    app.cached_is_free = snap.is_free
    app.last_snapshot_at = now
    app.save()

    changes: List[Change] = []

    if prev is None:
        # First-ever fetch for this app.
        change = Change.objects.create(
            app=app, change_type=Change.Type.ADDED,
            old_value="",
            new_value=f"price={snap.price_final} {snap.currency} (free={snap.is_free})",
            note=f"Initial snapshot: {snap.name}",
            detected_at=now,
        )
        changes.append(change)
        return changes

    if prev.price_final != snap.price_final:
        ctype = (Change.Type.PRICE_DROP if snap.price_final < prev.price_final
                 else Change.Type.PRICE_HIKE)
        change = Change.objects.create(
            app=app, change_type=ctype,
            old_value=str(prev.price_final),
            new_value=str(snap.price_final),
            note=f"{prev.currency} -> {snap.currency}",
            detected_at=now,
        )
        changes.append(change)

    if prev.discount_percent != snap.discount_percent:
        if snap.discount_percent > prev.discount_percent:
            ctype = Change.Type.NEW_DISCOUNT
            note = (f"discount went {prev.discount_percent}% -> "
                    f"{snap.discount_percent}%")
        else:
            ctype = Change.Type.DISCOUNT_END
            note = (f"discount ended {prev.discount_percent}% -> "
                    f"{snap.discount_percent}%")
        change = Change.objects.create(
            app=app, change_type=ctype,
            old_value=str(prev.discount_percent),
            new_value=str(snap.discount_percent),
            note=note, detected_at=now,
        )
        changes.append(change)

    if snap.last_update and snap.last_update > (prev.last_update or 0):
        change = Change.objects.create(
            app=app, change_type=Change.Type.APP_UPDATE,
            old_value=str(prev.last_update),
            new_value=str(snap.last_update),
            note="last_update moved", detected_at=now,
        )
        changes.append(change)

    return changes


def record_new_news(app: TrackedApp, items: List[NewsItem]) -> List[NewsPost]:
    """Insert new news posts (deduplicated by Steam's GID); emit change events."""
    new_posts: List[NewsPost] = []
    now = timezone.now()
    for item in items:
        if not item.gid:
            continue
        _, created = NewsPost.objects.get_or_create(
            gid=item.gid,
            defaults={
                "app": app,
                "title": item.title,
                "url": item.url,
                "author": item.author,
                "feed": item.feed,
                "is_update": item.is_update,
                "contents": item.contents,
                "date": _to_dt(item.date),
            },
        )
        if not created:
            continue
        new_posts.append(NewsPost.objects.get(gid=item.gid))
        Change.objects.create(
            app=app,
            change_type=(Change.Type.APP_UPDATE if item.is_update
                         else Change.Type.NEW_NEWS),
            old_value="",
            new_value=item.title[:400],
            note=item.url or item.feed,
            detected_at=now,
        )
    return new_posts


# --- Top-level driver ------------------------------------------------------

def track_one(app: TrackedApp) -> None:
    """One tracking cycle for a single app: snapshot + news + diff."""
    try:
        snap = fetch_app_snapshot(app.appid)
    except ApiError as exc:
        log.error("[%s] snapshot failed: %s", app, exc)
        return

    changes = diff_and_store(app, snap)
    if changes:
        log.info("[%s] %d change(s) detected", app.alias or app.appid, len(changes))
        for c in changes:
            log.info("  - %s: %s -> %s (%s)",
                     c.change_type, c.old_value, c.new_value, c.note)
    else:
        log.info("[%s] no change", app.alias or app.appid)

    if app.track_news or app.track_updates:
        try:
            items = fetch_app_news(app.appid, count=20)
        except ApiError as exc:
            log.error("[%s] news fetch failed: %s", app, exc)
            return
        new_posts = record_new_news(app, items)
        if new_posts:
            log.info("[%s] %d new news post(s) (%d update-flagged)",
                     app.alias or app.appid, len(new_posts),
                     sum(1 for p in new_posts if p.is_update))


def track_all() -> int:
    """Track every TrackedApp in turn. Returns number tracked."""
    apps = list(TrackedApp.objects.all())
    log.info("Tracking %d app(s) — cycle starting", len(apps))
    for app in apps:
        track_one(app)
    log.info("Cycle complete.")
    return len(apps)
