from django.contrib import admin
from .models import Note, NoteCategory

@admin.register(NoteCategory)
class NoteCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "order"]

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "is_published", "created_at"]
    list_filter = ["category", "is_published"]
    prepopulated_fields = {"slug": ["title"]}
    search_fields = ["title", "content_md"]
