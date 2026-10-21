"""`python manage.py track` — run one tracking cycle for every tracked app."""
from django.core.management.base import BaseCommand

from tracker.services.tracker import track_all


class Command(BaseCommand):
    help = "Run one tracking cycle (snapshot + news + diff) for every tracked app."

    def add_arguments(self, parser):
        parser.add_argument(
            "--appid", type=int,
            help="Only track one specific App ID (optional).",
        )

    def handle(self, *args, **options):
        if options["appid"]:
            from tracker.models import TrackedApp
            from tracker.services.tracker import track_one
            try:
                app = TrackedApp.objects.get(appid=options["appid"])
            except TrackedApp.DoesNotExist:
                self.stderr.write(
                    f"AppID {options['appid']} is not in the watchlist. "
                    f"Add it first via the web UI or admin.")
                return
            track_one(app)
            return
        n = track_all()
        self.stdout.write(self.style.SUCCESS(
            f"Tracked {n} app(s)."
        ))
