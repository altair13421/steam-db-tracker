"""Tracker app — Django-side container for the Steam tracker."""
from django.apps import AppConfig


class TrackerConfig(AppConfig):
    name = "tracker"
    verbose_name = "Steam Tracker"
    default_auto_field = "django.db.models.BigAutoField"
