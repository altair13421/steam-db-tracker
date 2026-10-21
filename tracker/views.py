"""Views for the tracker web UI.

All views are server-rendered (Django templates + Bootstrap 5 CDN).
No JavaScript framework required.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import AddAppForm, ChangeFilterForm
from .models import AppSnapshot, Change, NewsPost, TrackedApp
from .services.charts import render_discount_chart, render_price_chart
from .services.digest import build_digest
from .services.steam_api import ApiError, resolve_app_name
from .services.tracker import track_one


def _resolve_chart_filename(filename: str) -> Path:
    """Resolve a chart filename to an absolute path under MEDIA_ROOT/charts,
    raising 404 if it escapes that directory."""
    base = settings.CHART_DIR.resolve()
    path = (base / filename).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise Http404("Invalid chart path") from exc
    if not path.exists():
        raise Http404("Chart not yet rendered — run `track` twice.")
    return path


# --- Dashboard --------------------------------------------------------------

def dashboard(request):
    """Top-level view: list of tracked apps + recent changes."""
    apps = list(TrackedApp.objects.all().order_by("alias", "appid"))
    recent_changes = Change.objects.select_related("app").order_by("-detected_at")[:10]

    # Aggregate stats for the top of the dashboard.
    now = timezone.now()
    since_24h = now - timedelta(hours=24)
    stats = {
        "total_apps": len(apps),
        "changes_24h": Change.objects.filter(detected_at__gte=since_24h).count(),
        "news_24h": NewsPost.objects.filter(date__gte=since_24h).count(),
        "updates_24h": Change.objects.filter(
            detected_at__gte=since_24h,
            change_type=Change.Type.APP_UPDATE,
        ).count(),
    }

    add_form = AddAppForm()
    if request.method == "POST" and "add_app" in request.POST:
        add_form = AddAppForm(request.POST)
        if add_form.is_valid():
            appid = add_form.cleaned_data["appid"]
            if TrackedApp.objects.filter(appid=appid).exists():
                messages.error(request, f"AppID {appid} is already tracked.")
            else:
                app = TrackedApp.objects.create(
                    appid=appid,
                    alias=add_form.cleaned_data.get("alias") or str(appid),
                    track_price=add_form.cleaned_data["track_price"],
                    track_news=add_form.cleaned_data["track_news"],
                    track_updates=add_form.cleaned_data["track_updates"],
                )
                messages.success(request, f"Added AppID {appid} ({app.alias}).")
                return redirect("tracker:dashboard")

    return render(request, "tracker/dashboard.html", {
        "apps": apps,
        "recent_changes": recent_changes,
        "stats": stats,
        "add_form": add_form,
    })


def track_now(request):
    """POST-only: trigger one tracking cycle for every tracked app."""
    if request.method != "POST":
        return redirect("tracker:dashboard")
    count = 0
    for app in TrackedApp.objects.all():
        track_one(app)
        count += 1
    messages.success(request, f"Tracked {count} app(s).")
    return redirect("tracker:dashboard")


def track_app(request, appid):
    """POST-only: trigger one tracking cycle for a single app."""
    if request.method != "POST":
        return redirect("tracker:dashboard")
    app = get_object_or_404(TrackedApp, appid=appid)
    track_one(app)
    messages.success(request, f"Tracked {app}.")
    return redirect("tracker:app_detail", appid=appid)


def remove_app(request, appid):
    """POST-only: remove an app from the watchlist (history kept)."""
    if request.method != "POST":
        return redirect("tracker:dashboard")
    app = get_object_or_404(TrackedApp, appid=appid)
    name = str(app)
    app.delete()
    messages.success(request, f"Removed {name} from the watchlist.")
    return redirect("tracker:dashboard")


# --- App detail ------------------------------------------------------------

def app_detail(request, appid):
    app = get_object_or_404(TrackedApp, appid=appid)
    snapshots = app.snapshots.order_by("-fetched_at")[:50]
    news = app.news_posts.order_by("-date")[:20]
    changes = app.changes.order_by("-detected_at")[:20]

    # Render a chart on-demand if at least 2 snapshots exist.
    chart_url = None
    discount_chart_url = None
    if app.snapshots.count() >= 2:
        path = render_price_chart(app)
        if path:
            chart_url = f"{settings.MEDIA_URL}charts/{path.name}"
        dpath = render_discount_chart(app)
        if dpath:
            discount_chart_url = f"{settings.MEDIA_URL}charts/{dpath.name}"

    return render(request, "tracker/app_detail.html", {
        "app": app,
        "snapshots": snapshots,
        "news": news,
        "changes": changes,
        "chart_url": chart_url,
        "discount_chart_url": discount_chart_url,
    })


# --- Changelog -------------------------------------------------------------

def changelog(request):
    """Filterable changelog."""
    form = ChangeFilterForm(request.GET or None)
    qs = Change.objects.select_related("app").all()

    if form.is_valid():
        ct = form.cleaned_data.get("change_type")
        if ct:
            qs = qs.filter(change_type=ct)
        appid = form.cleaned_data.get("appid")
        if appid:
            qs = qs.filter(app__appid=appid)
        days = form.cleaned_data.get("days") or 7
        since = timezone.now() - timedelta(days=days)
        qs = qs.filter(detected_at__gte=since)
    else:
        since = timezone.now() - timedelta(days=7)
        qs = qs.filter(detected_at__gte=since)

    changes = qs.order_by("-detected_at")[:500]
    return render(request, "tracker/changelog.html", {
        "form": form,
        "changes": changes,
        "total": changes.count(),
    })


# --- News feed -------------------------------------------------------------

def news(request):
    """Latest news across all tracked apps."""
    qs = NewsPost.objects.select_related("app").all()
    # Optional filters via query string.
    appid = request.GET.get("appid")
    if appid:
        qs = qs.filter(app__appid=appid)
    only_updates = request.GET.get("only_updates") == "1"
    if only_updates:
        qs = qs.filter(is_update=True)
    news_list = qs.order_by("-date")[:100]
    apps = TrackedApp.objects.all().order_by("cached_name", "appid")
    return render(request, "tracker/news.html", {
        "news": news_list,
        "apps": apps,
        "active_appid": appid,
        "only_updates": only_updates,
    })


def news_detail(request, gid):
    """Show one news post and its stored Steam content."""
    post = get_object_or_404(NewsPost.objects.select_related("app"), gid=gid)
    return render(request, "tracker/news_detail.html", {"post": post})


# --- Digest ----------------------------------------------------------------

def digest(request):
    """Render the digest page in the browser."""
    days = int(request.GET.get("days", 7))
    if days < 1 or days > 365:
        days = 7
    report = build_digest(days=days)
    return render(request, "tracker/digest.html", {
        "report": report,
        "days": days,
    })


# --- Chart serving ---------------------------------------------------------

def chart_image(request, filename: str):
    """Serve a chart PNG. In production, prefer nginx; this is a fallback."""
    path = _resolve_chart_filename(filename)
    return FileResponse(open(path, "rb"), content_type="image/png")
