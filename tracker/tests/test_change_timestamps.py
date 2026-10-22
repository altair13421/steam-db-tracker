from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tracker.models import AppSnapshot, Change, TrackedApp
from tracker.services.steam_api import AppSnapshot as SteamAppSnapshot, NewsItem
from tracker.services.digest import build_digest
from tracker.services.tracker import diff_and_store, record_new_news


class ChangeTimestampTests(TestCase):
    def test_news_change_uses_steam_publication_time(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        published_at = datetime(2024, 3, 15, 12, 34, tzinfo=dt_timezone.utc)

        record_new_news(app, [
            NewsItem(
                appid=730,
                gid="news-with-timestamp",
                title="Patch notes",
                date=int(published_at.timestamp()),
            ),
        ])

        change = Change.objects.get(app=app)
        self.assertEqual(change.occurred_at, published_at)
        self.assertNotEqual(change.detected_at, published_at)

    def test_app_update_change_uses_steam_last_update_time(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        AppSnapshot.objects.create(app=app, last_update=100)
        updated_at = datetime(2024, 3, 15, 12, 34, tzinfo=dt_timezone.utc)

        diff_and_store(
            app,
            SteamAppSnapshot(
                appid=730,
                name="CS2",
                last_update=int(updated_at.timestamp()),
            ),
        )

        change = Change.objects.get(change_type=Change.Type.APP_UPDATE)
        self.assertEqual(change.occurred_at, updated_at)

    def test_changelog_only_shows_changes_with_recent_actual_times(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        detected_at = timezone.now().replace(second=0, microsecond=0)
        occurred_at = detected_at - timedelta(hours=1)
        Change.objects.create(
            app=app,
            change_type=Change.Type.NEW_NEWS,
            new_value="Patch notes",
            occurred_at=occurred_at,
            detected_at=detected_at,
        )
        Change.objects.create(
            app=app,
            change_type=Change.Type.PRICE_DROP,
            new_value="1000",
            detected_at=detected_at,
        )
        Change.objects.create(
            app=app,
            change_type=Change.Type.NEW_NEWS,
            new_value="Old actual time",
            occurred_at=detected_at - timedelta(days=8),
            detected_at=detected_at,
        )

        response = self.client.get(reverse("tracker:changelog"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Change time (UTC)")
        self.assertContains(response, "Patch notes")
        self.assertContains(
            response,
            f'datetime="{occurred_at.isoformat(timespec="seconds")}"',
        )
        self.assertContains(response, occurred_at.strftime("%Y-%m-%d %H:%M"))
        self.assertNotContains(response, "Detected")
        self.assertNotContains(response, "1000")
        self.assertNotContains(response, "Old actual time")

    def test_dashboard_and_digest_exclude_changes_without_actual_times(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        occurred_at = timezone.now() - timedelta(hours=1)
        Change.objects.create(
            app=app,
            change_type=Change.Type.APP_UPDATE,
            new_value="Actual update",
            occurred_at=occurred_at,
        )
        Change.objects.create(
            app=app,
            change_type=Change.Type.APP_UPDATE,
            new_value="Detected only",
        )

        dashboard = self.client.get(reverse("tracker:dashboard"))
        report = build_digest(days=7)

        self.assertContains(dashboard, "Actual update")
        self.assertNotContains(dashboard, "Detected only")
        self.assertEqual(report.total_changes, 1)
        self.assertEqual(report.apps[0].n_app_updates, 1)
        self.assertEqual(report.apps[0].last_update_at, occurred_at)
