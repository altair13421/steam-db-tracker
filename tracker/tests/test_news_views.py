from datetime import datetime, timezone

from django.test import TestCase
from django.urls import reverse

from tracker.models import NewsPost, TrackedApp
from tracker.services.steam_api import NewsItem
from tracker.services.tracker import record_new_news


class NewsDetailViewTests(TestCase):
    def test_tracking_saves_steam_publication_timestamp(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        published_at = datetime(2024, 3, 15, 12, 34, tzinfo=timezone.utc)

        posts = record_new_news(app, [
            NewsItem(appid=730, gid="123455", date=int(published_at.timestamp())),
        ])

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].date, published_at)

    def test_news_detail_shows_contents_and_original_publication_time(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        published_at = datetime(2024, 3, 15, 12, 34, tzinfo=timezone.utc)
        post = NewsPost.objects.create(
            gid="123456",
            app=app,
            title="Patch notes",
            contents="First paragraph.\n\nSecond paragraph.",
            date=published_at,
        )

        response = self.client.get(
            reverse("tracker:news_detail", kwargs={"gid": post.gid})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First paragraph.")
        self.assertContains(response, "Second paragraph.")
        self.assertContains(response, "2024-03-15 12:34 UTC")
        self.assertContains(response, 'datetime="2024-03-15T12:34:00+00:00"')

    def test_news_detail_escapes_post_content(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        post = NewsPost.objects.create(
            gid="123457",
            app=app,
            contents="<script>alert('unsafe')</script>",
        )

        response = self.client.get(
            reverse("tracker:news_detail", kwargs={"gid": post.gid})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>")
