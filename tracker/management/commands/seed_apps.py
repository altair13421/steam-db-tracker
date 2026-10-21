"""`python manage.py seed_apps` — populate the watchlist from config/apps.yaml
or sensible defaults if no config exists.

Useful for first-time setup and Docker bootstrap.
"""
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand
from django.conf import settings

from tracker.models import TrackedApp
from tracker.services.steam_api import ApiError, resolve_app_name

DEFAULT_APPS = [
    {"appid": 730, "alias": "CS2", "news": True, "updates": True, "price": True},
    {"appid": 1091500, "alias": "Cyberpunk 2077", "news": True, "updates": True, "price": True},
]


class Command(BaseCommand):
    help = "Seed the watchlist from config/apps.yaml (or built-in defaults)."

    def handle(self, *args, **options):
        config_path = Path(settings.BASE_DIR) / "config" / "apps.yaml"
        apps_data = []
        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            apps_data = raw.get("apps") or []
            self.stdout.write(f"Loaded {len(apps_data)} app(s) from {config_path}")
        if not apps_data:
            self.stdout.write(self.style.WARNING(
                "No config/apps.yaml found; using built-in defaults."
            ))
            apps_data = DEFAULT_APPS

        added = 0
        for raw in apps_data:
            appid = int(raw["appid"])
            obj, created = TrackedApp.objects.get_or_create(
                appid=appid,
                defaults={
                    "alias": raw.get("alias") or str(appid),
                    "track_price": bool(raw.get("price", True)),
                    "track_news": bool(raw.get("news", True)),
                    "track_updates": bool(raw.get("updates", True)),
                },
            )
            if created:
                added += 1
                # Try to resolve the name immediately so the dashboard looks populated.
                if not obj.alias or obj.alias == str(appid):
                    try:
                        name = resolve_app_name(appid)
                        if name:
                            obj.alias = name
                            obj.save(update_fields=["alias"])
                    except ApiError:
                        pass
                self.stdout.write(self.style.SUCCESS(
                    f"Added AppID {appid} ({obj.alias})"
                ))
        self.stdout.write(self.style.SUCCESS(
            f"Seed complete: {added} new app(s) added, "
            f"{len(apps_data) - added} already existed."
        ))
