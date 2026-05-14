import os, sys, subprocess, json
from datetime import date
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from django.http import Http404
from django.contrib import messages
from django.utils.translation import gettext as _
from .models import Strategy


def strategy_code(request, slug):
    """Display the strategy source code"""
    strategy = get_object_or_404(Strategy, slug=slug, is_active=True)
    # Try exact name, hyphen→underscore, and partial match
    candidates = [
        settings.BASE_DIR / "scripts" / f"{slug}.py",
        settings.BASE_DIR / "scripts" / f"{slug.replace('-', '_')}.py",
    ]
    candidates += sorted(settings.BASE_DIR.glob(f"scripts/*{slug.replace('-', '_')}*"))
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        raise Http404("代码文件不存在")
    source = path.read_text(encoding="utf-8")
    return render(request, "strategies/code.html", {
        "strategy": strategy,
        "source_lines": source.split("\n"),
        "filename": path.name,
        "lines": source.count("\n"),
    })


def strategy_list(request):
    strategies = Strategy.objects.filter(is_active=True)
    return render(request, "strategies/list.html", {
        "strategies": strategies,
    })


def run_strategy_view(request, slug):
    """Run strategy from web (staff only, synchronous for personal use)"""
    strategy = get_object_or_404(Strategy, slug=slug, is_active=True)
    if not request.user.is_staff:
        messages.error(request, _("需要管理员权限"))
        return redirect("strategies:strategy_detail", slug=slug)

    try:
        import tushare
    except ImportError:
        messages.error(request, _("服务器未安装 tushare，无法运行策略"))
        return redirect("strategies:strategy_detail", slug=slug)

    messages.info(request, _("正在运行策略，请稍候..."))
    manage_py = settings.BASE_DIR / "manage.py"
    result = subprocess.run(
        [sys.executable, str(manage_py), "run_etf_strategy"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0:
        messages.success(request, _("策略运行成功！"))
    else:
        messages.error(request, _("策略运行失败: ") + result.stderr[-300:])

    return redirect("strategies:strategy_detail", slug=slug)


def strategy_detail(request, slug):
    strategy = get_object_or_404(Strategy, slug=slug, is_active=True)
    results = strategy.results.all()[:20]
    latest_signal = strategy.signals.first()
    return render(request, "strategies/detail.html", {
        "strategy": strategy,
        "results": results,
        "latest_signal": latest_signal,
    })
