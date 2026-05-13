from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from products.models import Product, ProductDatePrice
from payment.models import Order
from .models import CartItem


@login_required
def cart_add(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)

    if request.method == "POST":
        date = request.POST.get("date")
        quantity = int(request.POST.get("quantity", 1))
        dp = ProductDatePrice.objects.filter(
            product=product, date=date, is_available=True
        ).first()

        if not dp:
            messages.error(request, _("所选日期不可用"))
        elif quantity > dp.available_qty:
            messages.error(request, _("库存不足"))
        else:
            # 如果同一产品同一日期已在购物车，增加数量
            existing = CartItem.objects.filter(
                user=request.user, product=product, booking_date=date
            ).first()
            if existing:
                existing.quantity += quantity
                existing.save()
            else:
                CartItem.objects.create(
                    user=request.user,
                    product=product,
                    booking_date=date,
                    quantity=quantity,
                    price=dp.price,
                )
            messages.success(request, _("已加入购物车"))

    return redirect(request.META.get("HTTP_REFERER", "product_list"))


@login_required
def cart_view(request):
    items = CartItem.objects.filter(user=request.user).select_related("product")
    total = sum(item.price * item.quantity for item in items)
    return render(request, "cart/view.html", {
        "items": items,
        "total": total,
    })


@login_required
def cart_remove(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, user=request.user)
    item.delete()
    messages.success(request, _("已从购物车移除"))
    return redirect("cart_view")


@login_required
def cart_checkout(request):
    items = CartItem.objects.filter(user=request.user).select_related("product")

    if not items:
        messages.info(request, _("购物车为空"))
        return redirect("cart_view")

    for item in items:
        Order.objects.create(
            user=request.user,
            product=item.product,
            booking_date=item.booking_date,
            quantity=item.quantity,
            unit_price=item.price,
            total_price=item.price * item.quantity,
            status="pending",
        )

    items.delete()
    messages.success(request, _("下单成功！请前往支付。"))
    return redirect("profile")
