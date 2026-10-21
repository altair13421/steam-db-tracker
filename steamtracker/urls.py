"""Root URL configuration for the Steam Tracker project."""
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("tracker.urls")),
]

# Serve media in DEBUG so chart PNGs work locally without nginx.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
