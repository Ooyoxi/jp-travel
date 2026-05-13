from django.db import models
from django.conf import settings
from products.models import Product


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "待支付"),
        ("paid", "已支付"),
        ("cancelled", "已取消"),
        ("refunded", "已退款"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders", verbose_name="用户"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="orders", verbose_name="产品"
    )
    booking_date = models.DateField("体验日期")
    quantity = models.IntegerField("数量", default=1)
    unit_price = models.DecimalField("单价", max_digits=10, decimal_places=2)
    total_price = models.DecimalField("总价", max_digits=10, decimal_places=2)
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="pending")
    contact_name = models.CharField("联系人", max_length=100, blank=True)
    contact_email = models.EmailField("联系邮箱", blank=True)
    contact_phone = models.CharField("联系电话", max_length=20, blank=True)
    stripe_session_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "订单"
        verbose_name_plural = "订单"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order {self.id} - {self.product.title_zh}"
