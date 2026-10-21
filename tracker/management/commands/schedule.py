"""`python manage.py schedule` — long-running scheduler.

Loops `track_all` every SCHEDULE_INTERVAL (from settings, default 12h).
Honors SIGINT/SIGTERM for clean Docker shutdown. Use `--once` for a
single cycle (cron-friendly).
"""
import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from tracker.services.tracker import track_all


def _parse_interval_to_seconds(s: str) -> int:
    """Parse '12 hours' / '30 minutes' / '3600' -> seconds."""
    s = (s or "").strip().lower()
    parts = s.split()
    if len(parts) == 2 and parts[0].isdigit():
        s = parts[0] + parts[1]
    multipliers = {
        "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
        "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
        "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
        "d": 86_400, "day": 86_400, "days": 86_400,
    }
    for unit, mult in multipliers.items():
        if s.endswith(unit):
            num_part = s[:-len(unit)].strip()
            if num_part.isdigit():
                return int(num_part) * mult
    try:
        return int(s)
    except ValueError:
        raise ValueError(f"Invalid interval: {s!r}")


class Command(BaseCommand):
    help = "Long-running scheduler that polls Steam on SCHEDULE_INTERVAL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval", default=None,
            help="Override interval, e.g. '6 hours' or '30 minutes'.",
        )
        parser.add_argument(
            "--once", action="store_true",
            help="Run one cycle then exit (cron mode).",
        )

    def handle(self, *args, **options):
        interval_str = options["interval"] or settings.SCHEDULE_INTERVAL
        interval_secs = _parse_interval_to_seconds(interval_str)
        if interval_secs < 300:
            self.stdout.write(self.style.WARNING(
                f"Interval {interval_secs}s is below 300s; bumping to 300s."
            ))
            interval_secs = 300
        self.stdout.write(self.style.SUCCESS(
            f"Scheduler: interval = {interval_str} ({interval_secs}s). "
            f"Press Ctrl-C to stop."
        ))

        stop = {"now": False}

        def _on_signal(signum, _frame):
            self.stdout.write(self.style.WARNING(
                f"Received signal {signum} — shutting down after current cycle."
            ))
            stop["now"] = True

        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)

        while not stop["now"]:
            try:
                n = track_all()
                self.stdout.write(self.style.SUCCESS(
                    f"Cycle complete: tracked {n} app(s)."
                ))
            except Exception:
                self.stdout.write(self.style.ERROR(
                    "Uncaught error in schedule cycle; continuing."
                ))
                import traceback
                self.stderr.write(traceback.format_exc())

            if options["once"]:
                self.stdout.write("--once set; exiting after one cycle.")
                return

            self.stdout.write(f"Sleeping {interval_secs}s until next cycle...")
            for _ in range(interval_secs):
                if stop["now"]:
                    break
                time.sleep(1)
        self.stdout.write("Scheduler stopped cleanly.")
