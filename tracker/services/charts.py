"""Chart rendering service — matplotlib PNGs to MEDIA_ROOT/charts."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import matplotlib
matplotlib.use("Agg")  # headless

import matplotlib.font_manager as fm   # noqa: E402
import matplotlib.pyplot as plt        # noqa: E402
from django.conf import settings       # noqa: E402

from ..models import TrackedApp, AppSnapshot

log = logging.getLogger("tracker.charts")

# CJK + symbol font fallback so non-Latin app names render correctly.
for _f in (
    "/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
):
    try:
        fm.fontManager.addfont(_f)
    except Exception:
        pass

plt.rcParams["font.sans-serif"] = ["Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _fmt_price_axis(cents: float, _pos=None) -> str:
    return f"{cents / 100:.2f}"


def _fmt_date_axis(epoch: float, _pos=None) -> str:
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    return dt.strftime("%m-%d %H:%M")


def render_price_chart(app: TrackedApp) -> Optional[Path]:
    """Render price + initial-price + discount-shaded PNG. Returns path."""
    rows: List[AppSnapshot] = list(
        app.snapshots.order_by("fetched_at")
    )
    if len(rows) < 2:
        log.info("Skipping chart for %s — only %d snapshots", app, len(rows))
        return None

    x = [r.fetched_at.timestamp() for r in rows]
    y_initial = [r.price_initial for r in rows]
    y_final = [r.price_final for r in rows]
    currency = rows[-1].currency or ""

    fig, ax = plt.subplots(figsize=(10, 5), dpi=110, constrained_layout=True)
    ax.step(x, y_initial, where="post",
            color="#888", linewidth=1.4, linestyle="--",
            label="Initial price (MSRP)")
    ax.step(x, y_final, where="post",
            color="#1f77b4", linewidth=2.0,
            label="Final price (paid)")

    # Shade discount windows.
    for i in range(len(rows) - 1):
        if rows[i].discount_percent > 0:
            ax.axvspan(rows[i].fetched_at.timestamp(),
                       rows[i + 1].fetched_at.timestamp(),
                       color="#ff6b6b", alpha=0.10)

    ax.set_title(f"Price history — {app} (AppID {app.appid})",
                 fontsize=13, fontweight="bold", loc="left")
    ax.set_xlabel("Fetched at (UTC)")
    ax.set_ylabel(f"Price ({currency or 'cur'})")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(_fmt_price_axis))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(_fmt_date_axis))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)

    settings.CHART_DIR.mkdir(parents=True, exist_ok=True)
    out_path = settings.CHART_DIR / f"price_{app.appid}.png"
    fig.savefig(out_path)
    plt.close(fig)
    log.info("Wrote price chart to %s", out_path)
    return out_path


def render_discount_chart(app: TrackedApp) -> Optional[Path]:
    rows = list(app.snapshots.order_by("fetched_at"))
    if len(rows) < 2:
        return None
    x = [r.fetched_at.timestamp() for r in rows]
    y = [r.discount_percent for r in rows]

    fig, ax = plt.subplots(figsize=(10, 4), dpi=110, constrained_layout=True)
    ax.fill_between(x, y, step="post", color="#1f77b4", alpha=0.25)
    ax.step(x, y, where="post", color="#1f77b4", linewidth=2.0,
            label="Discount %")
    ax.set_title(f"Discount history — {app} (AppID {app.appid})",
                 fontsize=13, fontweight="bold", loc="left")
    ax.set_xlabel("Fetched at (UTC)")
    ax.set_ylabel("Discount (%)")
    ax.set_ylim(0, max(max(y) + 10, 20))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(_fmt_date_axis))
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), borderaxespad=0.0)

    settings.CHART_DIR.mkdir(parents=True, exist_ok=True)
    out_path = settings.CHART_DIR / f"discount_{app.appid}.png"
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def render_all() -> List[Path]:
    outputs: List[Path] = []
    for app in TrackedApp.objects.all():
        path = render_price_chart(app)
        if path is not None:
            outputs.append(path)
    return outputs
