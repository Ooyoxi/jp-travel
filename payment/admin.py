from django.contrib import admin
from django.utils.html import format_html
from .models import Order


@admin.action(description="标记为已支付")
def mark_paid(modeladmin, request, queryset):
    queryset.update(status="paid")


@admin.action(description="标记为已取消")
def mark_cancelled(modeladmin, request, queryset):
    queryset.update(status="cancelled")


@admin.action(description="标记为已退款")
def mark_refunded(modeladmin, request, queryset):
    queryset.update(status="refunded")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "id", "product_title", "user_name", "booking_date",
        "quantity", "total_price_display", "status_badge", "created_at"
    ]
    list_filter = ["status", "created_at", "booking_date"]
    search_fields = ["product__title_zh", "contact_name", "contact_email", "user__username"]
    date_hierarchy = "created_at"
    actions = [mark_paid, mark_cancelled, mark_refunded]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = [
        ("订单信息", {"fields": ["user", "product", "status"]}),
        ("预订详情", {"fields": ["booking_date", "quantity", "unit_price", "total_price"]}),
        ("联系人", {"fields": ["contact_name", "contact_email", "contact_phone"]}),
        ("支付", {"fields": ["stripe_session_id"]}),
        ("时间", {"fields": ["created_at", "updated_at"]}),
    ]

    def product_title(self, obj):
        return obj.product.title_zh
    product_title.short_description = "产品"

    def user_name(self, obj):
        return obj.user.username
    user_name.short_description = "用户"

    def total_price_display(self, obj):
        return f"¥{obj.total_price}"
    total_price_display.short_description = "总价"

    def status_badge(self, obj):
        colors = {
            "pending": "orange",
            "paid": "green",
            "cancelled": "red",
            "refunded": "gray",
        }
        c = colors.get(obj.status, "gray")
        return format_html(f'<span style="color:white;background:{c};padding:3px 10px;border-radius:999px;font-size:12px;">{{}}</span>', obj.get_status_display())
    status_badge.short_description = "状态"
