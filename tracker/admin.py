"""Django admin registration for the tracker models."""
from django.contrib import admin

from .models import TrackedApp, AppSnapshot, NewsPost, Change


@admin.register(TrackedApp)
class TrackedAppAdmin(admin.ModelAdmin):
    list_display = (
        "appid", "alias", "cached_name", "display_price",
        "cached_discount_percent", "track_price", "track_news",
        "track_updates", "last_snapshot_at",
    )
    list_filter = ("track_price", "track_news", "track_updates")
    search_fields = ("appid", "alias", "cached_name")
    readonly_fields = (
        "cached_name", "cached_currency", "cached_price_final",
        "cached_price_initial", "cached_discount_percent",
        "cached_last_update", "cached_is_free", "last_snapshot_at",
        "created_at", "updated_at",
    )
    list_editable = ("alias",)
    actions = ["trigger_track_now"]

    @admin.action(description="Track now (one cycle for selected apps)")
    def trigger_track_now(self, request, queryset):
        from .services.tracker import track_one
        count = 0
        for app in queryset:
            track_one(app)
            count += 1
        self.message_user(request, f"Tracked {count} app(s).")


@admin.register(AppSnapshot)
class AppSnapshotAdmin(admin.ModelAdmin):
    list_display = ("app", "fetched_at", "currency", "price_initial",
                    "price_final", "discount_percent", "last_update")
    list_filter = ("currency",)
    search_fields = ("app__appid", "app__cached_name")
    date_hierarchy = "fetched_at"


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("gid", "app", "title", "is_update", "date", "first_seen")
    list_filter = ("is_update", "feed")
    search_fields = ("title", "gid", "app__cached_name")
    date_hierarchy = "date"
    readonly_fields = ("gid", "app", "title", "url", "author", "feed",
                       "cover_image", "is_update", "contents", "date",
                       "first_seen")


@admin.register(Change)
class ChangeAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "app", "change_type",
                    "old_value", "new_value", "note")
    list_filter = ("change_type",)
    search_fields = ("app__cached_name", "app__appid", "note")
    date_hierarchy = "occurred_at"
    readonly_fields = ("occurred_at", "detected_at")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(occurred_at__isnull=False)
