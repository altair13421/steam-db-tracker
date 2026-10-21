"""ASGI entry point (kept for future async / websockets)."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "steamtracker.settings")

application = get_asgi_application()
