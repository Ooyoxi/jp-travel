from django import template
from django.db.models import Sum
from payment.models import Order
from products.models import Product

register = template.Library()


@register.inclusion_tag("admin/_stats.html", takes_context=True)
def admin_dashboard_stats(context):
    orders = Order.objects.all()
    paid = orders.filter(status="paid")
    return {
        "total_orders": orders.count(),
        "pending_orders": orders.filter(status="pending").count(),
        "paid_orders": paid.count(),
        "total_products": Product.objects.filter(is_active=True).count(),
        "revenue": paid.aggregate(s=Sum("total_price"))["s"] or 0,
    }
