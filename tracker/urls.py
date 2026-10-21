"""URL config for the tracker app."""
from django.urls import path

from . import views

app_name = "tracker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("track-now", views.track_now, name="track_now"),
    path("track/<int:appid>", views.track_app, name="track_app"),
    path("remove/<int:appid>", views.remove_app, name="remove_app"),
    path("app/<int:appid>", views.app_detail, name="app_detail"),
    path("changelog", views.changelog, name="changelog"),
    path("news", views.news, name="news"),
    path("news/<str:gid>", views.news_detail, name="news_detail"),
    path("digest", views.digest, name="digest"),
    path("charts/<str:filename>", views.chart_image, name="chart_image"),
]
