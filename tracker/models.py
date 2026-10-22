"""Tracker app models — Django ORM equivalent of the CLI bot's SQLite schema.

Tables:
  TrackedApp     — registry of every app we're tracking (one row per App ID).
  AppSnapshot    — full appdetails snapshot per (app, fetched_at).
  NewsPost       — every fetched Steam news post, deduplicated by Steam `gid`.
  Change         — typed change events (price drop, app update, ...).

Differences vs the CLI bot:
  - All models use Django's auto primary key (BigAutoField).
  - Booleans use BooleanField instead of INTEGER 0/1.
  - Price is stored as integer cents (matches Steam's API).
  - Helper methods on TrackedApp make the UI cleaner.
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class TrackedApp(models.Model):
    """A Steam app the user wants to track."""

    appid = models.PositiveIntegerField(
        unique=True, db_index=True,
        help_text="Steam App ID, e.g. 730 for CS2.",
    )
    alias = models.CharField(
        max_length=200, blank=True,
        help_text="Human-friendly label; auto-resolved from Steam if blank.",
    )
    track_price = models.BooleanField(default=True)
    track_news = models.BooleanField(default=True)
    track_updates = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Snapshot caches (denormalized for dashboard performance).
    cached_name = models.CharField(max_length=300, blank=True)
    cached_currency = models.CharField(max_length=8, blank=True)
    cached_price_final = models.PositiveIntegerField(default=0)
    cached_price_initial = models.PositiveIntegerField(default=0)
    cached_discount_percent = models.PositiveSmallIntegerField(default=0)
    cached_last_update = models.PositiveIntegerField(default=0)
    cached_is_free = models.BooleanField(default=False)
    last_snapshot_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["alias", "appid"]

    def __str__(self) -> str:
        return self.cached_name or self.alias or f"AppID {self.appid}"

    def display_price(self) -> str:
        if self.cached_is_free:
            return "Free"
        if not self.cached_price_final:
            return "—"
        cur = self.cached_currency or ""
        return f"{self.cached_price_final / 100:.2f} {cur}".strip()

    def display_initial_price(self) -> str:
        if self.cached_is_free:
            return "Free"
        if not self.cached_price_initial:
            return "—"
        cur = self.cached_currency or ""
        return f"{self.cached_price_initial / 100:.2f} {cur}".strip()


class AppSnapshot(models.Model):
    """One appdetails snapshot at a point in time."""

    app = models.ForeignKey(
        TrackedApp, on_delete=models.CASCADE, related_name="snapshots",
    )
    fetched_at = models.DateTimeField(default=timezone.now, db_index=True)
    currency = models.CharField(max_length=8, blank=True)
    price_initial = models.PositiveIntegerField(default=0)
    price_final = models.PositiveIntegerField(default=0)
    discount_percent = models.PositiveSmallIntegerField(default=0)
    last_update = models.PositiveIntegerField(default=0)

    @property
    def price_final_display(self):
        if self.price_final is None:
            return None
        currency = self.currency or ""
        return f"{self.price_final / 100:.2f} {currency}".strip()

    @property
    def price_initial_display(self):
        if self.price_initial is None:
            return None
        currency = self.currency or ""
        return f"{self.price_initial / 100:.2f} {currency}".strip()

    class Meta:
        ordering = ["-fetched_at"]
        indexes = [
            models.Index(fields=["app", "-fetched_at"]),
        ]

    def __str__(self) -> str:
        return f"snapshot {self.app_id} @ {self.fetched_at:%Y-%m-%d %H:%M}"


class NewsPost(models.Model):
    """A Steam news post for one tracked app (deduplicated by Steam `gid`)."""

    gid = models.CharField(max_length=64, unique=True)
    app = models.ForeignKey(
        TrackedApp, on_delete=models.CASCADE, related_name="news_posts",
    )
    title = models.CharField(max_length=400, blank=True)
    url = models.URLField(max_length=500, blank=True)
    cover_image = models.URLField(max_length=1000, blank=True)
    author = models.CharField(max_length=200, blank=True)
    feed = models.CharField(max_length=100, blank=True)
    is_update = models.BooleanField(default=False)
    contents = models.TextField(blank=True)
    date = models.DateTimeField(null=True, blank=True, db_index=True)
    first_seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["app", "-date"]),
            models.Index(fields=["is_update", "-date"]),
        ]

    def __str__(self) -> str:
        return self.title or f"news {self.gid}"


class Change(models.Model):
    """A detected change event for one tracked app."""

    class Type(models.TextChoices):
        ADDED          = "added",          "Added"
        PRICE_DROP     = "price_drop",     "Price Drop"
        PRICE_HIKE     = "price_hike",     "Price Hike"
        NEW_DISCOUNT   = "new_discount",   "New Discount"
        DISCOUNT_END   = "discount_end",   "Discount Ended"
        APP_UPDATE     = "app_update",     "App Update"
        NEW_NEWS       = "new_news",       "New News"
        RELEASE_INFO   = "release_info",   "Release Info"

    app = models.ForeignKey(
        TrackedApp, on_delete=models.CASCADE, related_name="changes",
    )
    change_type = models.CharField(
        max_length=20, choices=Type.choices, db_index=True,
    )
    old_value = models.CharField(max_length=400, blank=True)
    new_value = models.CharField(max_length=400, blank=True)
    note = models.CharField(max_length=500, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True, db_index=True)
    detected_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["-detected_at"]),
            models.Index(fields=["app", "-detected_at"]),
            models.Index(fields=["change_type", "-detected_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_change_type_display()} — {self.app} — {self.detected_at:%Y-%m-%d %H:%M}"
