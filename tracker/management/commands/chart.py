"""`python manage.py chart [appid]` — render price-history PNGs."""
from django.core.management.base import BaseCommand

from tracker.models import TrackedApp
from tracker.services.charts import render_all, render_discount_chart, render_price_chart


class Command(BaseCommand):
    help = "Render price-history PNG(s). Without an AppID, renders every tracked app."

    def add_arguments(self, parser):
        parser.add_argument(
            "appid", type=int, nargs="?", default=None,
            help="AppID, or omit to render all.",
        )
        parser.add_argument(
            "--discount", action="store_true",
            help="Also render a separate discount chart.",
        )

    def handle(self, *args, **options):
        if options["appid"] is None:
            paths = render_all()
            if not paths:
                self.stdout.write(self.style.WARNING(
                    "No charts rendered — not enough snapshots yet. "
                    "Run `track` at least twice."
                ))
                return
            self.stdout.write(self.style.SUCCESS("Rendered charts:"))
            for p in paths:
                self.stdout.write(f"  {p}")
            return

        try:
            app = TrackedApp.objects.get(appid=options["appid"])
        except TrackedApp.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f"AppID {options['appid']} not in watchlist."
            ))
            return
        path = render_price_chart(app)
        if path is None:
            self.stdout.write(self.style.WARNING(
                f"Could not render chart for AppID {app.appid}. "
                f"Need at least 2 snapshots. Run `track` first."
            ))
            return
        self.stdout.write(self.style.SUCCESS(f"Price chart: {path}"))
        if options["discount"]:
            dpath = render_discount_chart(app)
            if dpath:
                self.stdout.write(self.style.SUCCESS(f"Discount chart: {dpath}"))
