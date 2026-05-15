import sys, subprocess, logging
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.contrib import messages
from django.utils.translation import gettext as _
from .models import DailySnapshot, Article
from .market_data import fetch_market_news

logger = logging.getLogger(__name__)


def market_home(request):
    snapshots = DailySnapshot.objects.filter(is_published=True)[:30]
    featured_articles = Article.objects.filter(is_favorite=True)[:10]
    latest_articles = Article.objects.all()[:20]
    people = (
        Article.objects.exclude(people="")
        .values_list("people", flat=True)
        .distinct()[:20]
    )
    all_people = set()
    for p in people:
        for name in p.split(","):
            name = name.strip()
            if name:
                all_people.add(name)

    # Fetch Yahoo Finance news (force refresh with ?refresh=1)
    from datetime import datetime
    news_articles = []
    force = request.GET.get("refresh") == "1"
    try:
        news_articles = fetch_market_news(force_refresh=force)
        # 将 ISO 时间字符串转回 datetime 对象供模板使用
        for a in news_articles:
            if isinstance(a.get("published_at"), str):
                a["published_at"] = datetime.fromisoformat(a["published_at"])
    except Exception as e:
        logger.warning("yfinance news fetch failed: %s", e)

    # 检查缓存时间
    from .market_data import CACHE_FILE
    cache_mtime = None
    try:
        import os
        if os.path.exists(CACHE_FILE):
            cache_mtime = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
    except Exception:
        pass

    return render(request, "market/home.html", {
        "snapshots": snapshots,
        "featured_articles": featured_articles,
        "latest_articles": latest_articles,
        "all_people": sorted(all_people),
        "news_articles": news_articles,
        "news_updated_at": cache_mtime,
    })


def article_list(request):
    tag = request.GET.get("tag")
    person = request.GET.get("person")
    articles = Article.objects.all()
    if tag:
        articles = articles.filter(tags__icontains=tag)
    if person:
        articles = articles.filter(people__icontains=person)
    return render(request, "market/article_list.html", {
        "articles": articles,
    })


def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk)
    return render(request, "market/article_detail.html", {
        "article": article,
    })


def by_person(request, person):
    articles = Article.objects.filter(people__icontains=person)
    return render(request, "market/article_list.html", {
        "articles": articles,
        "person": person,
    })


def by_tag(request, tag):
    articles = Article.objects.filter(tags__icontains=tag)
    return render(request, "market/article_list.html", {
        "articles": articles,
        "tag": tag,
    })


def fetch_rss_view(request):
    """网页触发 RSS 采集（仅管理员）"""
    if not request.user.is_staff:
        messages.error(request, _("需要管理员权限"))
        return redirect("market:market_home")

    messages.info(request, _("📡 开始采集 RSS，请稍候..."))
    manage_py = settings.BASE_DIR / "manage.py"
    result = subprocess.run(
        [sys.executable, str(manage_py), "fetch_rss"],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode == 0:
        messages.success(request, _("RSS 采集完成！"))
    else:
        messages.error(request, _("采集出错: ") + result.stderr[-200:])

    return redirect("market:market_home")
