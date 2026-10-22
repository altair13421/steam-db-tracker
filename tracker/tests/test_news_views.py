from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from tracker.models import AppSnapshot, Change, NewsPost, TrackedApp
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

    def test_news_detail_shows_cover_art_separately_from_inline_images(self):
        app = TrackedApp.objects.create(appid=1091500, alias="Cyberpunk 2077")
        post = NewsPost.objects.create(
            gid="cover-art",
            app=app,
            title="REDstreams",
            cover_image=(
                "https://clan.akamai.steamstatic.com/images/"
                "35210272/12c97f011ba5d07c05359e8e39e86751a009650d.png"
            ),
            contents='[img src="{STEAM_CLAN_IMAGE}/35210272/inline.png"][/img]',
        )

        response = self.client.get(
            reverse("tracker:news_detail", kwargs={"gid": post.gid})
        )

        self.assertEqual(response.status_code, 200)
        rendered = response.content.decode()
        cover_image = (
            "https://clan.akamai.steamstatic.com/images/"
            "35210272/12c97f011ba5d07c05359e8e39e86751a009650d.png"
        )
        inline_image = (
            "https://clan.akamai.steamstatic.com/images/"
            "35210272/inline.png"
        )
        self.assertIn(f'src="{cover_image}" alt="REDstreams cover art"', rendered)
        self.assertIn(f'src="{inline_image}"', rendered)
        self.assertLess(rendered.index(cover_image), rendered.index(inline_image))

    def test_tracking_backfills_cover_art_for_existing_news(self):
        app = TrackedApp.objects.create(appid=1091500, alias="Cyberpunk 2077")
        post = NewsPost.objects.create(gid="existing-cover", app=app)
        cover_image = "https://clan.akamai.steamstatic.com/images/35210272/cover.png"

        record_new_news(app, [
            NewsItem(
                appid=1091500,
                gid=post.gid,
                cover_image=cover_image,
            ),
        ])

        post.refresh_from_db()
        self.assertEqual(post.cover_image, cover_image)

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


class AppDetailViewTests(TestCase):
    def test_latest_news_precedes_charts_and_changes_are_readable(self):
        app = TrackedApp.objects.create(appid=292030, alias="The Witcher 3")
        AppSnapshot.objects.create(app=app, currency="USD", price_final=3999)
        post = NewsPost.objects.create(
            gid="news-292030",
            app=app,
            title="Latest patch notes",
            url="https://example.com/news",
            contents="[p]Patch details[/p]",
            date=datetime(2026, 10, 21, tzinfo=timezone.utc),
        )
        Change.objects.create(
            app=app,
            change_type=Change.Type.APP_UPDATE,
            new_value=post.title,
            note=post.url,
        )

        with (
            patch("tracker.views.render_price_chart", return_value=Path("price_292030.png")) as price_chart,
            patch("tracker.views.render_discount_chart", return_value=Path("discount_292030.png")) as discount_chart,
        ):
            response = self.client.get(
                reverse("tracker:app_detail", kwargs={"appid": app.appid})
            )

        self.assertEqual(response.status_code, 200)
        price_chart.assert_called_once_with(app)
        discount_chart.assert_called_once_with(app)
        html = response.content.decode()
        self.assertLess(html.index("Latest news"), html.index("Price history"))
        self.assertContains(response, reverse("tracker:news_detail", kwargs={"gid": post.gid}))
        self.assertContains(response, "Read announcement")
        self.assertContains(
            response,
            'src="https://store.steampowered.com/widget/292030/"',
        )
        self.assertContains(response, "/charts/price_292030.png?v=")
        self.assertContains(response, "/charts/discount_292030.png?v=")

    def test_chart_service_generates_charts_from_one_snapshot(self):
        app = TrackedApp.objects.create(appid=292031, alias="Test app")
        AppSnapshot.objects.create(
            app=app,
            currency="USD",
            price_initial=1999,
            price_final=1499,
            discount_percent=25,
        )

        with TemporaryDirectory() as chart_dir:
            with override_settings(CHART_DIR=Path(chart_dir)):
                from tracker.services.charts import (
                    render_discount_chart,
                    render_price_chart,
                )

                price_chart = render_price_chart(app)
                discount_chart = render_discount_chart(app)
                self.assertIsNotNone(price_chart)
                self.assertIsNotNone(discount_chart)
                self.assertTrue(price_chart.is_file())
                self.assertTrue(discount_chart.is_file())


class PriceDisplayTests(TestCase):
    def test_digest_displays_cents_as_major_currency_units(self):
        app = TrackedApp.objects.create(
            appid=292032,
            alias="Test app",
            cached_currency="USD",
        )
        AppSnapshot.objects.create(
            app=app,
            currency="USD",
            price_final=1799,
        )

        response = self.client.get(reverse("tracker:digest"), {"days": 7})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "17.99 USD")
        self.assertNotContains(response, "1799.00 USD")

    def test_price_chart_formats_cents_as_major_currency_units(self):
        from tracker.services.charts import _fmt_price_axis

        self.assertEqual(_fmt_price_axis(1799), "17.99")
