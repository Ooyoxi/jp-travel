from django.db import models
from django.utils.text import slugify

class Strategy(models.Model):
    name = models.CharField(max_length=100, verbose_name="策略名称")
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True, verbose_name="简介")
    content_md = models.TextField(blank=True, verbose_name="详细说明（Markdown）")
    code_link = models.URLField(blank=True, verbose_name="代码链接")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "策略"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BacktestResult(models.Model):
    strategy = models.ForeignKey(
        Strategy, on_delete=models.CASCADE, related_name="results", verbose_name="策略"
    )
    date = models.DateField(verbose_name="回测日期")
    annual_return = models.FloatField(null=True, blank=True, verbose_name="年化收益率")
    sharpe_ratio = models.FloatField(null=True, blank=True, verbose_name="夏普比率")
    max_drawdown = models.FloatField(null=True, blank=True, verbose_name="最大回撤")
    win_rate = models.FloatField(null=True, blank=True, verbose_name="胜率")
    metrics_json = models.JSONField(default=dict, blank=True, verbose_name="其他指标")
    chart_html = models.TextField(blank=True, verbose_name="图表 HTML")
    notes = models.TextField(blank=True, verbose_name="备注")

    class Meta:
        ordering = ["-date"]
        verbose_name = "回测结果"


class Signal(models.Model):
    strategy = models.ForeignKey(
        Strategy, on_delete=models.CASCADE, related_name="signals", verbose_name="策略"
    )
    date = models.DateField(verbose_name="信号日期")
    summary = models.TextField(blank=True, verbose_name="信号摘要")
    details_json = models.JSONField(default=dict, blank=True, verbose_name="详细数据")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "策略信号"
