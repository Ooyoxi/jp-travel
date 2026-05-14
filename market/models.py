from django.db import models


class RssSource(models.Model):
    name = models.CharField(max_length=100, verbose_name="名称")
    feed_url = models.URLField(verbose_name="RSS 地址", unique=True)
    site_url = models.URLField(blank=True, verbose_name="网站地址")
    category = models.CharField(max_length=50, blank=True, verbose_name="分类")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    last_fetched = models.DateTimeField(null=True, blank=True, verbose_name="上次抓取")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "RSS 订阅源"

    def __str__(self):
        return self.name


class DailySnapshot(models.Model):
    date = models.DateField(unique=True, verbose_name="日期")
    title = models.CharField(max_length=200, blank=True, verbose_name="标题")
    content_md = models.TextField(blank=True, verbose_name="内容（Markdown）")
    market_note = models.TextField(blank=True, verbose_name="盘面简评")
    is_published = models.BooleanField(default=False, verbose_name="已发布")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        verbose_name = "每日市场快照"

    def __str__(self):
        return f"{self.date} - {self.title or '无标题'}"


class Article(models.Model):
    SOURCE_CHOICES = [
        ("rss", "RSS"),
        ("manual", "手动"),
        ("api", "API"),
        ("email", "邮件"),
    ]
    title = models.CharField(max_length=300, verbose_name="标题")
    url = models.URLField(verbose_name="原文链接", blank=True)
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default="manual", verbose_name="来源渠道"
    )
    source_name = models.CharField(max_length=100, blank=True, verbose_name="来源名称")
    author = models.CharField(max_length=100, blank=True, verbose_name="作者")
    summary = models.TextField(blank=True, verbose_name="摘要")
    content_text = models.TextField(blank=True, verbose_name="原文全文")
    content_translated = models.TextField(blank=True, verbose_name="中文翻译")
    tags = models.CharField(max_length=500, blank=True, verbose_name="标签")
    people = models.CharField(max_length=200, blank=True, verbose_name="相关人物")
    is_favorite = models.BooleanField(default=False, verbose_name="收藏")
    snapshot = models.ForeignKey(
        DailySnapshot, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="articles", verbose_name="关联快照"
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name="发布日期")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "文章"

    def __str__(self):
        return self.title

    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def people_list(self):
        return [p.strip() for p in self.people.split(",") if p.strip()]
