from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        "id", "product_title", "user_name", "booking_date",
        "quantity", "total_price_display", "status_display", "created_at"
    ]
    list_filter = ["status", "created_at"]
    search_fields = ["product__title_zh", "user__username"]

    def product_title(self, obj):
        return obj.product.title_zh
    product_title.short_description = "产品"

    def user_name(self, obj):
        return obj.user.username
    user_name.short_description = "用户"

    def total_price_display(self, obj):
        return f"¥{obj.total_price}"
    total_price_display.short_description = "总价"

    def status_display(self, obj):
        return obj.get_status_display()
    status_display.short_description = "状态"
