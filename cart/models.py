from django.db import models
from django.conf import settings
from products.models import Product


class CartItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items", verbose_name="用户"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="cart_items", verbose_name="产品"
    )
    booking_date = models.DateField("体验日期")
    quantity = models.IntegerField("数量", default=1)
    price = models.DecimalField("价格", max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "购物车项"
        verbose_name_plural = "购物车项"

    def __str__(self):
        return f"{self.product.title_zh} x{self.quantity}"
