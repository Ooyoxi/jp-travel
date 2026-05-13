import stripe
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.utils.translation import gettext as _
from .models import Order


@login_required
def create_checkout_session(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user, status="pending")

    if settings.STRIPE_SECRET_KEY:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                "price_data": {
                    "currency": "jpy",
                    "product_data": {"name": order.product.title_zh},
                    "unit_amount": int(order.unit_price * 100),
                },
                "quantity": order.quantity,
            }],
            mode="payment",
            success_url=request.build_absolute_uri("/zh-hans/payment/success/") + f"?order_id={order.id}",
            cancel_url=request.build_absolute_uri("/zh-hans/payment/cancel/") + f"?order_id={order.id}",
            customer_email=order.contact_email or request.user.email,
        )
        order.stripe_session_id = checkout_session.id
        order.save()
        return redirect(checkout_session.url, code=303)
    else:
        # 没有 Stripe 密钥时，直接跳到支付模拟
        return redirect("payment_simulate", order_id=order.id)


@login_required
def payment_simulate(request, order_id):
    """模拟支付：没有 Stripe 密钥时用这个来测试"""
    order = get_object_or_404(Order, pk=order_id, user=request.user, status="pending")
    if request.method == "POST":
        order.status = "paid"
        order.save()
        messages.success(request, _("支付成功！（模拟）"))
        return redirect("profile")
    return render(request, "payment/simulate.html", {"order": order})


@login_required
def payment_success(request):
    order_id = request.GET.get("order_id")
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    return render(request, "payment/success.html", {"order": order})


@login_required
def payment_cancel(request):
    order_id = request.GET.get("order_id")
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    return render(request, "payment/cancel.html", {"order": order})


@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    if settings.STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            return HttpResponse(status=400)
    else:
        event = stripe.Event.construct_from(payload, stripe.api_key)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        Order.objects.filter(stripe_session_id=session["id"]).update(status="paid")

    return HttpResponse(status=200)
