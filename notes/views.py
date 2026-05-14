from django.shortcuts import render, get_object_or_404
from .models import Note, NoteCategory
from strategies.models import Strategy, Signal
from market.models import DailySnapshot, Article


def home(request):
    """Home page: quant dashboard"""
    latest_notes = Note.objects.filter(is_published=True)[:4]
    strategies = Strategy.objects.filter(is_active=True)
    latest_signals = Signal.objects.select_related("strategy").all()[:5]
    today_snapshot = DailySnapshot.objects.filter(is_published=True).first()
    recent_articles = Article.objects.all()[:6]
    categories = NoteCategory.objects.all()

    return render(request, "notes/home.html", {
        "latest_notes": latest_notes,
        "strategies": strategies,
        "latest_signals": latest_signals,
        "today_snapshot": today_snapshot,
        "recent_articles": recent_articles,
        "categories": categories,
    })


def note_list(request):
    notes = Note.objects.filter(is_published=True)
    category_slug = request.GET.get("category")
    if category_slug:
        notes = notes.filter(category__slug=category_slug)
    tag = request.GET.get("tag")
    if tag:
        notes = notes.filter(tags__icontains=tag)
    categories = NoteCategory.objects.all()
    return render(request, "notes/list.html", {
        "notes": notes,
        "categories": categories,
        "current_category": category_slug,
        "current_tag": tag,
    })


def note_detail(request, slug):
    note = get_object_or_404(Note, slug=slug, is_published=True)
    return render(request, "notes/detail.html", {
        "note": note,
    })
