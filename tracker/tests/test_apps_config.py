import yaml
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from tracker.models import TrackedApp


class AppsConfigViewTests(TestCase):
    def test_apps_config_page_is_available_from_navigation(self):
        response = self.client.get(reverse("tracker:apps_config"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import adds new apps and updates matching app settings.")
        self.assertContains(response, reverse("tracker:export_apps_config"))
        self.assertContains(response, "Apps YAML")

    def test_export_contains_only_tracked_apps_and_tracking_settings(self):
        TrackedApp.objects.create(
            appid=730,
            alias="Counter-Strike 2",
            track_price=False,
            track_news=True,
            track_updates=False,
            cached_name="Cached name is not exported",
        )
        TrackedApp.objects.create(appid=1091500, alias="Cyberpunk 2077")

        response = self.client.get(reverse("tracker:export_apps_config"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/yaml; charset=utf-8")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="apps.yaml"',
        )
        self.assertEqual(
            yaml.safe_load(response.content),
            {
                "apps": [
                    {
                        "appid": 730,
                        "alias": "Counter-Strike 2",
                        "news": True,
                        "updates": False,
                        "price": False,
                    },
                    {
                        "appid": 1091500,
                        "alias": "Cyberpunk 2077",
                        "news": True,
                        "updates": True,
                        "price": True,
                    },
                ],
            },
        )

    def test_import_creates_and_updates_apps_without_removing_others(self):
        existing = TrackedApp.objects.create(
            appid=730,
            alias="Old alias",
            track_price=True,
            track_news=False,
            track_updates=True,
        )
        untouched = TrackedApp.objects.create(appid=440, alias="Team Fortress 2")
        upload = SimpleUploadedFile(
            "apps.yaml",
            (
                "apps:\n"
                "  - appid: 730\n"
                "    alias: Counter-Strike 2\n"
                "    news: true\n"
                "    updates: false\n"
                "    price: false\n"
                "  - appid: 1091500\n"
                "    alias: Cyberpunk 2077\n"
                "    news: false\n"
                "    updates: true\n"
                "    price: true\n"
            ).encode(),
            content_type="application/yaml",
        )

        response = self.client.post(
            reverse("tracker:apps_config"),
            {"file": upload},
        )

        self.assertRedirects(response, reverse("tracker:apps_config"))
        existing.refresh_from_db()
        untouched.refresh_from_db()
        self.assertEqual(existing.alias, "Counter-Strike 2")
        self.assertTrue(existing.track_news)
        self.assertFalse(existing.track_updates)
        self.assertFalse(existing.track_price)
        self.assertEqual(untouched.alias, "Team Fortress 2")
        self.assertTrue(TrackedApp.objects.filter(appid=1091500).exists())
        self.assertEqual(TrackedApp.objects.count(), 3)

    def test_invalid_yaml_does_not_change_the_watchlist(self):
        existing = TrackedApp.objects.create(appid=730, alias="Keep this")
        upload = SimpleUploadedFile(
            "invalid.yaml",
            b'apps:\n  - appid: 730\n    alias: Changed\n    news: "yes"\n',
            content_type="application/yaml",
        )

        response = self.client.post(
            reverse("tracker:apps_config"),
            {"file": upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "setting &#x27;news&#x27; must be true or false")
        existing.refresh_from_db()
        self.assertEqual(existing.alias, "Keep this")

    def test_import_rejects_duplicate_app_ids(self):
        upload = SimpleUploadedFile(
            "duplicate.yaml",
            b"apps:\n  - appid: 730\n  - appid: 730\n",
            content_type="application/yaml",
        )

        response = self.client.post(
            reverse("tracker:apps_config"),
            {"file": upload},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AppID 730 appears more than once.")
        self.assertEqual(TrackedApp.objects.count(), 0)
