from django.contrib import admin
from .models import Category, Product, ProductImage, ProductDatePrice, Favorite, Review


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductDatePriceInline(admin.TabularInline):
    model = ProductDatePrice
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name_zh", "name_ja", "name_en", "order", "is_active"]
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["title_zh", "category", "base_price", "is_active", "featured", "created_at"]
    list_filter = ["category", "is_active", "featured"]
    search_fields = ["title_zh", "title_ja", "title_en"]
    inlines = [ProductImageInline, ProductDatePriceInline]


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "created_at"]
    search_fields = ["user__username", "product__title_zh"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["user", "product", "rating", "created_at"]
    list_filter = ["rating"]
    search_fields = ["user__username", "product__title_zh"]
