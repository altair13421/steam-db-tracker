"""`python manage.py digest` — build + persist a Markdown digest."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.services.digest import build_digest


class Command(BaseCommand):
    help = "Build a Markdown weekly (or N-day) digest of all changes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=7,
            help="Window in days (default 7).",
        )
        parser.add_argument(
            "--write", action="store_true",
            help="Also write a Markdown file to <MEDIA_ROOT>/digest_<date>.md",
        )

    def handle(self, *args, **options):
        report = build_digest(days=options["days"])
        markdown = render_markdown(report)
        self.stdout.write(markdown)
        if options["write"]:
            from django.conf import settings
            out_path = settings.MEDIA_ROOT / (
                f"digest_{timezone.now().strftime('%Y-%m-%d')}.md"
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(markdown, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Markdown digest: {out_path}"))


def render_markdown(report) -> str:
    out = []
    start = report.since.strftime("%Y-%m-%d")
    end = timezone.now().strftime("%Y-%m-%d")
    out.append("# Steam Tracker — Weekly Digest")
    out.append("")
    out.append(f"**Window:** {start} .. {end} ({report.days} days)")
    out.append(f"**Total changes:** {report.total_changes}")
    out.append(f"**Total news posts:** {report.total_news}")
    out.append("")
    for ad in report.apps:
        out.append(f"## {ad.app} (AppID {ad.app.appid})")
        out.append("")
        out.append(f"- Price drops: **{ad.n_price_drops}** | "
                   f"Price hikes: **{ad.n_price_hikes}**")
        out.append(f"- New discounts: **{ad.n_new_discounts}** | "
                   f"Discounts ended: **{ad.n_discount_ends}**")
        out.append(f"- App updates: **{ad.n_app_updates}** | "
                   f"News posts: **{ad.n_news}**")
        if ad.lowest_price:
            cur = ad.app.cached_currency or ""
            out.append(f"- Lowest price seen: **{ad.lowest_price/100:.2f} {cur}** "
                       f"(at {ad.lowest_price_at.strftime('%Y-%m-%d %H:%M UTC')})")
        out.append(f"- Highest discount seen: **{ad.highest_discount}%**")
        if ad.last_update_at:
            ts_str = ad.last_update_at.strftime("%Y-%m-%d %H:%M UTC")
            link = f" — [link]({ad.last_update_url})" if ad.last_update_url else ""
            out.append(f"- Last update: {ts_str}{link}")
        out.append("")
    return "\n".join(out)
