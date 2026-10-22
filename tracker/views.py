"""Views for the tracker web UI.

All views are server-rendered (Django templates + Bootstrap 5 CDN).
No JavaScript framework required.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import yaml
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .forms import AddAppForm, AppsImportForm, ChangeFilterForm
from .models import Change, NewsPost, TrackedApp
from .services.charts import render_discount_chart, render_price_chart
from .services.digest import build_digest
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

class DashboardView(TemplateView):
    """Top-level view: list of tracked apps + recent changes."""

    template_name = "tracker/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        apps = list(TrackedApp.objects.all().order_by("alias", "appid"))
        since_24h = timezone.now() - timedelta(hours=24)
        context.update({
            "apps": apps,
            "recent_changes": Change.objects.filter(
                occurred_at__isnull=False
            ).select_related("app").order_by("-occurred_at")[:10],
            "stats": {
                "total_apps": len(apps),
                "changes_24h": Change.objects.filter(
                    occurred_at__isnull=False,
                    occurred_at__gte=since_24h,
                ).count(),
                "news_24h": NewsPost.objects.filter(
                    date__gte=since_24h
                ).count(),
                "updates_24h": Change.objects.filter(
                    occurred_at__isnull=False,
                    occurred_at__gte=since_24h,
                    change_type=Change.Type.APP_UPDATE,
                ).count(),
            },
        })
        context.setdefault("add_form", AddAppForm())
        return context

    def post(self, request, *args, **kwargs):
        if "add_app" not in request.POST:
            return self.get(request, *args, **kwargs)

        form = AddAppForm(request.POST)
        if form.is_valid():
            appid = form.cleaned_data["appid"]
            if TrackedApp.objects.filter(appid=appid).exists():
                messages.error(request, f"AppID {appid} is already tracked.")
            else:
                app = TrackedApp.objects.create(
                    appid=appid,
                    alias=form.cleaned_data.get("alias") or str(appid),
                    track_price=form.cleaned_data["track_price"],
                    track_news=form.cleaned_data["track_news"],
                    track_updates=form.cleaned_data["track_updates"],
                )
                messages.success(request, f"Added AppID {appid} ({app.alias}).")
                return redirect("tracker:dashboard")

        return self.render_to_response(self.get_context_data(add_form=form))


class TrackNowView(View):
    """POST-only: trigger one tracking cycle for every tracked app."""

    def get(self, request, *args, **kwargs):
        return redirect("tracker:dashboard")

    def post(self, request, *args, **kwargs):
        count = 0
        for app in TrackedApp.objects.all():
            track_one(app)
            count += 1
        messages.success(request, f"Tracked {count} app(s).")
        return redirect("tracker:dashboard")


class TrackAppView(View):
    """POST-only: trigger one tracking cycle for a single app."""

    def get(self, request, appid, *args, **kwargs):
        return redirect("tracker:dashboard")

    def post(self, request, appid, *args, **kwargs):
        app = get_object_or_404(TrackedApp, appid=appid)
        track_one(app)
        messages.success(request, f"Tracked {app}.")
        return redirect("tracker:app_detail", appid=appid)


class RemoveAppView(View):
    """POST-only: remove an app from the watchlist (history kept)."""

    def get(self, request, appid, *args, **kwargs):
        return redirect("tracker:dashboard")

    def post(self, request, appid, *args, **kwargs):
        app = get_object_or_404(TrackedApp, appid=appid)
        name = str(app)
        app.delete()
        messages.success(request, f"Removed {name} from the watchlist.")
        return redirect("tracker:dashboard")


class AppsConfigView(TemplateView):
    """Import an apps.yaml file, merging its apps into the current watchlist."""

    template_name = "tracker/apps_config.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["apps_count"] = TrackedApp.objects.count()
        return context

    def post(self, request, *args, **kwargs):
        form = AppsImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        created = 0
        updated = 0
        with transaction.atomic():
            for app_config in form.cleaned_data["apps"]:
                _, was_created = TrackedApp.objects.update_or_create(
                    appid=app_config["appid"],
                    defaults={
                        "alias": app_config["alias"],
                        "track_news": app_config["news"],
                        "track_updates": app_config["updates"],
                        "track_price": app_config["price"],
                    },
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        messages.success(
            request,
            f"Imported {created + updated} app(s): {created} added, "
            f"{updated} updated. Other tracked apps were left unchanged.",
        )
        return redirect("tracker:apps_config")


class ExportAppsConfigView(View):
    """Download the tracked apps and their settings in seed-compatible YAML."""

    def get(self, request, *args, **kwargs):
        data = {
            "apps": [
                {
                    "appid": app.appid,
                    "alias": app.alias,
                    "news": app.track_news,
                    "updates": app.track_updates,
                    "price": app.track_price,
                }
                for app in TrackedApp.objects.order_by("appid")
            ],
        }
        content = yaml.safe_dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        response = HttpResponse(
            content,
            content_type="application/yaml; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="apps.yaml"'
        return response


# --- App detail ------------------------------------------------------------

class AppDetailView(DetailView):
    model = TrackedApp
    template_name = "tracker/app_detail.html"
    context_object_name = "app"
    slug_field = "appid"
    slug_url_kwarg = "appid"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        app = self.object
        context["snapshots"] = app.snapshots.order_by("-fetched_at")[:50]
        news = list(app.news_posts.order_by("-date")[:8])
        changes = list(
            app.changes.filter(occurred_at__isnull=False)
            .order_by("-occurred_at")[:10]
        )
        news_by_title = {post.title: post for post in news}
        context["news"] = news
        context["change_items"] = [
            {
                "change": change,
                "news_post": news_by_title.get(change.new_value),
                "source_url": (
                    change.note
                    if change.note.startswith(("http://", "https://"))
                    else ""
                ),
            }
            for change in changes
        ]

        snapshot_count = app.snapshots.count()
        latest_snapshot = app.snapshots.first()
        chart_version = (
            int(latest_snapshot.fetched_at.timestamp()) if latest_snapshot else 0
        )
        chart_url = None
        discount_chart_url = None
        if snapshot_count:
            path = render_price_chart(app)
            if path:
                chart_url = (
                    f"{reverse('tracker:chart_image', args=[path.name])}"
                    f"?v={chart_version}"
                )
            discount_path = render_discount_chart(app)
            if discount_path:
                discount_chart_url = (
                    f"{reverse('tracker:chart_image', args=[discount_path.name])}"
                    f"?v={chart_version}"
                )

        context.update({
            "snapshot_count": snapshot_count,
            "chart_url": chart_url,
            "discount_chart_url": discount_chart_url,
        })
        return context


# --- Changelog -------------------------------------------------------------

class ChangelogView(ListView):
    """Filterable changelog."""

    template_name = "tracker/changelog.html"
    context_object_name = "changes"

    def get_queryset(self):
        self.form = ChangeFilterForm(self.request.GET or None)
        queryset = Change.objects.select_related("app").all()
        if self.form.is_valid():
            change_type = self.form.cleaned_data.get("change_type")
            if change_type:
                queryset = queryset.filter(change_type=change_type)
            appid = self.form.cleaned_data.get("appid")
            if appid:
                queryset = queryset.filter(app__appid=appid)
            days = self.form.cleaned_data.get("days") or 7
        else:
            days = 7

        since = timezone.now() - timedelta(days=days)
        return queryset.filter(
            occurred_at__isnull=False,
            occurred_at__gte=since,
        ).order_by(
            "-occurred_at"
        )[:500]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = self.form
        context["total"] = context["changes"].count()
        return context


# --- News feed -------------------------------------------------------------

class NewsListView(ListView):
    """Latest news across all tracked apps."""

    template_name = "tracker/news.html"
    context_object_name = "news"

    def get_queryset(self):
        queryset = NewsPost.objects.select_related("app").all()
        appid = self.request.GET.get("appid")
        if appid:
            queryset = queryset.filter(app__appid=appid)
        self.only_updates = self.request.GET.get("only_updates") == "1"
        if self.only_updates:
            queryset = queryset.filter(is_update=True)
        return queryset.order_by("-date")[:100]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "apps": TrackedApp.objects.all().order_by("cached_name", "appid"),
            "active_appid": self.request.GET.get("appid"),
            "only_updates": self.only_updates,
        })
        return context


class NewsDetailView(DetailView):
    """Show one news post and its stored Steam content."""

    model = NewsPost
    queryset = NewsPost.objects.select_related("app")
    template_name = "tracker/news_detail.html"
    context_object_name = "post"
    slug_field = "gid"
    slug_url_kwarg = "gid"


# --- Digest ----------------------------------------------------------------

class DigestView(TemplateView):
    """Render the digest page in the browser."""

    template_name = "tracker/digest.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        days = int(self.request.GET.get("days", 7))
        if days < 1 or days > 365:
            days = 7
        context.update({
            "report": build_digest(days=days),
            "days": days,
        })
        return context


# --- Chart serving ---------------------------------------------------------

class ChartImageView(View):
    """Serve a chart PNG. In production, prefer nginx; this is a fallback."""

    def get(self, request, filename, *args, **kwargs):
        path = _resolve_chart_filename(filename)
        return FileResponse(open(path, "rb"), content_type="image/png")
