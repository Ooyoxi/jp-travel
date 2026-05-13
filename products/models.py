from django.db import models
from django.conf import settings


class Category(models.Model):
    name_zh = models.CharField("中文名称", max_length=100)
    name_ja = models.CharField("日本語名", max_length=100)
    name_en = models.CharField("English name", max_length=100)
    slug = models.SlugField(unique=True)
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "分类"
        verbose_name_plural = "分类"
        ordering = ["order"]

    def __str__(self):
        return self.name_zh


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="products", verbose_name="分类"
    )
    title_zh = models.CharField("中文标题", max_length=200)
    title_ja = models.CharField("日本語タイトル", max_length=200)
    title_en = models.CharField("English title", max_length=200)
    description_zh = models.TextField("中文描述", blank=True)
    description_ja = models.TextField("日本語説明", blank=True)
    description_en = models.TextField("English description", blank=True)
    location_zh = models.CharField("中文地点", max_length=200, blank=True)
    location_ja = models.CharField("日本語場所", max_length=200, blank=True)
    location_en = models.CharField("English location", max_length=200, blank=True)
    base_price = models.DecimalField("基准价格", max_digits=10, decimal_places=2)
    duration_minutes = models.IntegerField("时长(分钟)", default=60)
    max_participants = models.IntegerField("最大参与人数", default=10)
    min_participants = models.IntegerField("最少成团人数", default=1)
    is_active = models.BooleanField("上架", default=True)
    featured = models.BooleanField("推荐", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    latitude = models.FloatField("纬度", blank=True, null=True)
    longitude = models.FloatField("经度", blank=True, null=True)

    class Meta:
        verbose_name = "产品"
        verbose_name_plural = "产品"

    def __str__(self):
        return self.title_zh


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images", verbose_name="产品"
    )
    image = models.ImageField("图片", upload_to="products/")
    caption_zh = models.CharField("中文说明", max_length=200, blank=True)
    caption_ja = models.CharField("日本語説明", max_length=200, blank=True)
    caption_en = models.CharField("English caption", max_length=200, blank=True)
    is_cover = models.BooleanField("封面图", default=False)
    order = models.IntegerField(default=0)

    class Meta:
        verbose_name = "产品图片"
        verbose_name_plural = "产品图片"
        ordering = ["order"]

    def __str__(self):
        return f"{self.product.title_zh} - {self.order}"


class ProductDatePrice(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="date_prices", verbose_name="产品"
    )
    date = models.DateField("日期")
    price = models.DecimalField("当日价格", max_digits=10, decimal_places=2)
    available_qty = models.IntegerField("可用库存", default=0)
    is_available = models.BooleanField("可预订", default=True)

    class Meta:
        verbose_name = "日期价格"
        verbose_name_plural = "日期价格"
        unique_together = ["product", "date"]

    def __str__(self):
        return f"{self.product.title_zh} - {self.date}"


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites", verbose_name="用户"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="favorites", verbose_name="产品"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "收藏"
        verbose_name_plural = "收藏"
        unique_together = ["user", "product"]

    def __str__(self):
        return f"{self.user.username} ❤️ {self.product.title_zh}"


class Review(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews", verbose_name="用户"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews", verbose_name="产品"
    )
    rating = models.IntegerField("评分", choices=[(i, i) for i in range(1, 6)], default=5)
    comment = models.TextField("评价", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "评价"
        verbose_name_plural = "评价"
        unique_together = ["user", "product"]

    def __str__(self):
        return f"{self.user.username} ⭐{self.rating} - {self.product.title_zh}"
