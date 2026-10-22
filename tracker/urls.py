"""URL config for the tracker app."""
from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("track-now", views.TrackNowView.as_view(), name="track_now"),
    path("track/<int:appid>", views.TrackAppView.as_view(), name="track_app"),
    path("remove/<int:appid>", views.RemoveAppView.as_view(), name="remove_app"),
    path("apps-config", views.AppsConfigView.as_view(), name="apps_config"),
    path(
        "apps-config/export",
        views.ExportAppsConfigView.as_view(),
        name="export_apps_config",
    ),
    path("app/<int:appid>", views.AppDetailView.as_view(), name="app_detail"),
    path("changelog", views.ChangelogView.as_view(), name="changelog"),
    path("news", views.NewsListView.as_view(), name="news"),
    path("news/<str:gid>", views.NewsDetailView.as_view(), name="news_detail"),
    path("digest", views.DigestView.as_view(), name="digest"),
    path(
        "charts/<str:filename>",
        views.ChartImageView.as_view(),
        name="chart_image",
    ),
]
