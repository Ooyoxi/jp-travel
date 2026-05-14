from django.contrib import admin
from .models import Strategy, BacktestResult, Signal

@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    prepopulated_fields = {"slug": ["name"]}

@admin.register(BacktestResult)
class BacktestResultAdmin(admin.ModelAdmin):
    list_display = ["strategy", "date", "annual_return", "sharpe_ratio", "max_drawdown"]
    list_filter = ["strategy"]

@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = ["strategy", "date", "summary"]
    list_filter = ["strategy"]
