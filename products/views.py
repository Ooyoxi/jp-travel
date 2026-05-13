from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.http import JsonResponse
from .models import Product, Category, Favorite, Review
from payment.models import Order


def home(request):
    featured = Product.objects.filter(is_active=True, featured=True)[:8]
    categories = Category.objects.filter(is_active=True)
    return render(request, "product/home.html", {
        "featured": featured,
        "categories": categories,
    })


def product_list(request):
    products = Product.objects.filter(is_active=True)
    category_slug = request.GET.get("category")
    if category_slug:
        products = products.filter(category__slug=category_slug)
    q = request.GET.get("q")
    if q:
        products = products.filter(
            models.Q(title_zh__icontains=q)
            | models.Q(title_ja__icontains=q)
            | models.Q(title_en__icontains=q)
        )
    categories = Category.objects.filter(is_active=True)
    return render(request, "product/list.html", {
        "products": products,
        "categories": categories,
        "current_category": category_slug,
    })


def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    is_favorited = False
    can_review = False
    user_review = None

    if request.user.is_authenticated:
        is_favorited = Favorite.objects.filter(user=request.user, product=product).exists()
        can_review = Order.objects.filter(user=request.user, product=product, status="paid").exists()
        user_review = Review.objects.filter(user=request.user, product=product).first()

    # Handle review submission
    if request.method == "POST" and request.user.is_authenticated and can_review and not user_review:
        rating = int(request.POST.get("rating", 5))
        comment = request.POST.get("comment", "")
        Review.objects.create(user=request.user, product=product, rating=rating, comment=comment)
        messages.success(request, _("评价已提交"))
        return redirect("product_detail", pk=pk)

    reviews = product.reviews.select_related("user").all().order_by("-created_at")
    return render(request, "product/detail.html", {
        "product": product,
        "is_favorited": is_favorited,
        "can_review": can_review,
        "user_review": user_review,
        "reviews": reviews,
    })


@login_required
def toggle_favorite(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    fav = Favorite.objects.filter(user=request.user, product=product)
    if fav.exists():
        fav.delete()
        messages.success(request, _("已取消收藏"))
    else:
        Favorite.objects.create(user=request.user, product=product)
        messages.success(request, _("已收藏"))
    return redirect(request.META.get("HTTP_REFERER", "product_detail"))
