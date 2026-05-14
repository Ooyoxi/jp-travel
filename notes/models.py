from django.db import models
from django.utils.text import slugify

class NoteCategory(models.Model):
    name = models.CharField(max_length=50, verbose_name="分类名")
    slug = models.SlugField(unique=True, blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order"]
        verbose_name = "笔记分类"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Note(models.Model):
    title = models.CharField(max_length=200, verbose_name="标题")
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(
        NoteCategory, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="分类"
    )
    tags = models.CharField(max_length=500, blank=True, verbose_name="标签（逗号分隔）")
    summary = models.TextField(blank=True, verbose_name="摘要")
    content_md = models.TextField(verbose_name="内容（Markdown）")
    is_published = models.BooleanField(default=True, verbose_name="已发布")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "学习笔记"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]
