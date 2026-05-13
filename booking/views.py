from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from products.models import Product, ProductDatePrice
from payment.models import Order


@login_required
def create_booking(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    error = None

    if request.method == "POST":
        booking_date = request.POST.get("date")
        quantity = int(request.POST.get("quantity", 1))
        contact_name = request.POST.get("contact_name", "")
        contact_email = request.POST.get("contact_email", "")
        contact_phone = request.POST.get("contact_phone", "")

        dp = ProductDatePrice.objects.filter(
            product=product, date=booking_date, is_available=True
        ).first()
        if not dp:
            error = _("所选日期不可用")
        elif quantity > dp.available_qty:
            error = _("库存不足")
        else:
            total = dp.price * quantity
            Order.objects.create(
                user=request.user,
                product=product,
                booking_date=booking_date,
                quantity=quantity,
                unit_price=dp.price,
                total_price=total,
                status="pending",
                contact_name=contact_name,
                contact_email=contact_email,
                contact_phone=contact_phone,
            )
            messages.success(request, _("订单已创建，请在个人中心查看。"))
            return redirect("profile")

    date_prices = product.date_prices.filter(is_available=True).order_by("date")[:90]
    return render(request, "booking/create.html", {
        "product": product,
        "date_prices": date_prices,
        "error": error,
    })
