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

    def test_news_detail_converts_steam_markup_and_resolves_clan_images(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        post = NewsPost.objects.create(
            gid="123458",
            app=app,
            contents=(
                "[p]Hello, choom![/p]"
                '[p][img src="{STEAM_CLAN_IMAGE}/35210272/image.png"][/img][/p]'
                '[p][dynamiclink href="https://example.com/watch"]Watch here[/dynamiclink][/p]'
                '[p][dynamiclink href="https://example.com/empty"][/dynamiclink][/p]'
                "[p][img]https://example.com/plain.png[/img][/p]"
                "[list][*]One[*]Two[/list]"
            ),
        )

        response = self.client.get(
            reverse("tracker:news_detail", kwargs={"gid": post.gid})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<p>Hello, choom!</p>", html=True)
        self.assertContains(
            response,
            'src="https://clan.akamai.steamstatic.com/images/35210272/image.png"',
        )
        self.assertContains(
            response,
            '<a href="https://example.com/watch" target="_blank" rel="noopener noreferrer">Watch here</a>',
            html=True,
        )
        self.assertContains(response, "https://example.com/empty")
        self.assertContains(response, '<img src="https://example.com/plain.png"', html=False)
        self.assertContains(response, "<ul><li>One</li><li>Two</li></ul>", html=True)
        self.assertNotContains(response, "[p]")

    def test_news_detail_rejects_unsafe_markup_urls(self):
        app = TrackedApp.objects.create(appid=730, alias="CS2")
        post = NewsPost.objects.create(
            gid="123459",
            app=app,
            contents=(
                '[dynamiclink href="javascript:alert(1)"]bad link[/dynamiclink]'
                '[img src="javascript:alert(1)"][/img]'
            ),
        )

        response = self.client.get(
            reverse("tracker:news_detail", kwargs={"gid": post.gid})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "javascript:")
        self.assertNotContains(response, "<img")

    def test_news_detail_converts_reported_steam_markup(self):
        app = TrackedApp.objects.create(appid=1091500, alias="Cyberpunk 2077")
        post = NewsPost.objects.create(
            gid="123460",
            app=app,
            contents=(
                "[p]Chrome up, chooms! A new update is coming.[/p]"
                "[p][/p]"
                '[p][img src="{STEAM_CLAN_IMAGE}/35210272/image.png"][/img][/p]'
                "[p]Tune in here:[/p]"
                '[p][dynamiclink href="https://twitch.tv/cdprojektred"][/dynamiclink][/p]'
            ),
        )

        response = self.client.get(
            reverse("tracker:news_detail", kwargs={"gid": post.gid})
        )
        rendered = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<p>Chrome up, chooms! A new update is coming.</p>", rendered)
        self.assertIn(
            'src="https://clan.akamai.steamstatic.com/images/35210272/image.png"',
            rendered,
        )
        self.assertIn(">https://twitch.tv/cdprojektred</a>", rendered)
        self.assertNotIn("[p]", rendered)
        self.assertNotIn("[img", rendered)
        self.assertNotIn("[dynamiclink", rendered)
