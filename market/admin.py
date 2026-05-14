from django.contrib import admin
from .models import RssSource, DailySnapshot, Article

@admin.register(DailySnapshot)
class DailySnapshotAdmin(admin.ModelAdmin):
    list_display = ["date", "title", "is_published"]
    list_filter = ["is_published"]

@admin.register(RssSource)
class RssSourceAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active", "last_fetched"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "feed_url"]

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "source_name", "author", "is_favorite", "published_at"]
    list_filter = ["source", "source_name", "is_favorite"]
    search_fields = ["title", "summary", "content_text"]
