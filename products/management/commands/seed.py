import os
import random
from io import BytesIO

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from products.models import Category, Product, ProductDatePrice, ProductImage
from datetime import date, timedelta

# Unsplash URLs for product images
UNSPLASH_IMAGES = {
    "东京迪士尼乐园一日游": "https://images.unsplash.com/photo-1536697246787-1f7ae568d89a?w=800",
    "京都和服体验一日游": "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=800",
    "富士山登山徒步一日游": "https://images.unsplash.com/photo-1478436127897-769e1b3f0f36?w=800",
    "东京寿司制作课程": "https://images.unsplash.com/photo-1545569341-9eb8b30979d9?w=800",
    "大阪道顿堀美食徒步之旅": "https://images.unsplash.com/photo-1551218808-94e220e084d2?w=800",
    "京都抹茶体验与茶道课程": "https://images.unsplash.com/photo-1528360983277-13d401cdc186?w=800",
}

CATEGORY_MAP = {
    "旅游活动": {"name_en": "Tours & Activities", "name_ja": "観光ツアー"},
    "美食体验": {"name_en": "Food & Drink", "name_ja": "グルメ"},
}


PRODUCTS = [
    {
        "category": "旅游活动",
        "items": [
            {
                "title_zh": "东京迪士尼乐园一日游",
                "title_ja": "東京ディズニーランド一日ツアー",
                "title_en": "Tokyo Disneyland Day Tour",
                "description_zh": "体验东京迪士尼乐园的魔法世界，包含所有游乐设施和表演。无需排队换票，扫码直接入园。",
                "description_ja": "東京ディズニーランドの魔法の世界を体験。すべてのアトラクションとショーを楽しめます。",
                "description_en": "Experience the magic of Tokyo Disneyland. Includes all rides and shows. Direct QR code entry.",
                "location_zh": "千叶县浦安市",
                "location_ja": "千葉県浦安市",
                "location_en": "Urayasu, Chiba",
                "base_price": 7900,
                "duration_minutes": 600,
                "max_participants": 1,
                "min_participants": 1,
                "featured": True,
            },
            {
                "title_zh": "京都和服体验一日游",
                "title_ja": "京都着物レンタル一日体験",
                "title_en": "Kyoto Kimono Rental & Walking Tour",
                "description_zh": "专业和服着装师为您挑选和穿戴传统和服，漫步在京都的古街小巷，附带摄影师跟拍服务。",
                "description_ja": "プロの着付師が着物を選び着付け。京都の古い街並みを散策し、カメラマンが撮影します。",
                "description_en": "Professional kimono dressing, stroll through Kyoto's historic streets, with photographer service.",
                "location_zh": "京都市东山区",
                "location_ja": "京都市東山区",
                "location_en": "Higashiyama, Kyoto",
                "base_price": 8500,
                "duration_minutes": 360,
                "max_participants": 10,
                "min_participants": 1,
                "featured": True,
            },
            {
                "title_zh": "富士山登山徒步一日游",
                "title_ja": "富士山トレッキング一日ツアー",
                "title_en": "Mt. Fuji Hiking Day Tour",
                "description_zh": "专业向导带领，从五合目出发登山，包含登山装备租赁、午餐和保险。适合初级登山者。",
                "description_ja": "専門ガイドが五合目から案内。登山用具レンタル、昼食、保険付き。初心者向け。",
                "description_en": "Guided hike from 5th Station. Includes gear rental, lunch, and insurance. Beginner-friendly.",
                "location_zh": "山梨县富士吉田市",
                "location_ja": "山梨県富士吉田市",
                "location_en": "Fujiyoshida, Yamanashi",
                "base_price": 15000,
                "duration_minutes": 480,
                "max_participants": 15,
                "min_participants": 4,
                "featured": True,
            },
            {
                "title_zh": "东京寿司制作课程",
                "title_ja": "東京寿司作り体験教室",
                "title_en": "Tokyo Sushi Making Class",
                "description_zh": "跟随资深寿司师傅学习握寿司技巧，使用新鲜筑地市场食材。完成后享用自己制作的寿司午餐。",
                "description_ja": "熟練の寿司職人から握り寿司の技術を学びます。築地市場の新鮮な食材を使用。",
                "description_en": "Learn sushi techniques from a master chef. Use fresh Tsukiji Market ingredients. Enjoy your creations.",
                "location_zh": "东京都中央区筑地",
                "location_ja": "東京都中央区築地",
                "location_en": "Tsukiji, Tokyo",
                "base_price": 12000,
                "duration_minutes": 180,
                "max_participants": 8,
                "min_participants": 2,
                "featured": False,
            },
        ],
    },
    {
        "category": "美食体验",
        "items": [
            {
                "title_zh": "大阪道顿堀美食徒步之旅",
                "title_ja": "大阪道頓堀グルメウォーキングツアー",
                "title_en": "Osaka Dotonbori Food Walking Tour",
                "description_zh": "由在地美食达人带领，品尝章鱼烧、大阪烧、串炸等6种以上大阪名物。",
                "description_ja": "地元グルメガイドが案内。たこ焼き、お好み焼き、串カツなど6種類以上の大阪名物を堪能。",
                "description_en": "Local foodie guide takes you to 6+ Osaka specialties: takoyaki, okonomiyaki, kushikatsu & more.",
                "location_zh": "大阪市中央区道顿堀",
                "location_ja": "大阪市中央区道頓堀",
                "location_en": "Dotonbori, Osaka",
                "base_price": 9800,
                "duration_minutes": 210,
                "max_participants": 12,
                "min_participants": 2,
                "featured": True,
            },
            {
                "title_zh": "京都抹茶体验与茶道课程",
                "title_ja": "京都抹茶体験と茶道教室",
                "title_en": "Kyoto Matcha Experience & Tea Ceremony",
                "description_zh": "在百年茶室中体验正宗日本茶道，学习抹茶的冲泡方法，品尝传统和果子。",
                "description_ja": "百年の茶室で本格的な茶道を体験。抹茶の点て方と伝統的な和菓子を楽しみます。",
                "description_en": "Experience authentic tea ceremony in a century-old tea house. Learn matcha preparation and enjoy wagashi.",
                "location_zh": "京都市宇治市",
                "location_ja": "京都市宇治市",
                "location_en": "Uji, Kyoto",
                "base_price": 5500,
                "duration_minutes": 120,
                "max_participants": 8,
                "min_participants": 1,
                "featured": False,
            },
        ],
    },
]


class Command(BaseCommand):
    help = "填充演示数据"

    def handle(self, *args, **options):
        self.stdout.write("开始填充数据...\n")

        for cat_data in PRODUCTS:
            cat_slug = cat_data["category"]
            names = CATEGORY_MAP.get(cat_slug, {"name_en": cat_slug, "name_ja": cat_slug})
            cat, created = Category.objects.get_or_create(
                slug=cat_slug,
                defaults={
                    "name_zh": cat_slug,
                    "name_ja": names["name_ja"],
                    "name_en": names["name_en"],
                },
            )
            if not created:
                # Update names if already exists
                Category.objects.filter(slug=cat_slug).update(
                    name_ja=names["name_ja"],
                    name_en=names["name_en"],
                )
            self.stdout.write(f"📁 分类: {cat_slug}")

            for item in cat_data["items"]:
                product, created = Product.objects.update_or_create(
                    title_zh=item["title_zh"],
                    defaults={
                        "category": cat,
                        "title_ja": item["title_ja"],
                        "title_en": item["title_en"],
                        "description_zh": item["description_zh"],
                        "description_ja": item["description_ja"],
                        "description_en": item["description_en"],
                        "location_zh": item["location_zh"],
                        "location_ja": item["location_ja"],
                        "location_en": item["location_en"],
                        "base_price": item["base_price"],
                        "duration_minutes": item["duration_minutes"],
                        "max_participants": item["max_participants"],
                        "min_participants": item["min_participants"],
                        "featured": item["featured"],
                        "is_active": True,
                    },
                )

                # 创建未来90天的价格和库存（如果不存在）
                for i in range(90):
                    d = date.today() + timedelta(days=i + 1)
                    price = item["base_price"]
                    if random.random() < 0.3:
                        price = int(item["base_price"] * random.uniform(0.8, 1.2))
                    ProductDatePrice.objects.get_or_create(
                        product=product,
                        date=d,
                        defaults={
                            "price": price,
                            "available_qty": random.randint(5, 50),
                            "is_available": True,
                        },
                    )

                # 更新产品图片（删除旧图重新下载）
                img_url = UNSPLASH_IMAGES.get(item["title_zh"])
                if img_url:
                    try:
                        resp = requests.get(img_url, timeout=10)
                        if resp.status_code == 200:
                            # 删除已有图片
                            product.images.all().delete()
                            content_type = resp.headers.get("content-type", "image/jpeg")
                            ext = "jpg" if "jpeg" in content_type else "png"
                            filename = f"{product.id}_{item['title_zh'][:20]}.{ext}"
                            ProductImage.objects.create(
                                product=product,
                                image=ContentFile(resp.content, name=filename),
                                is_cover=True,
                            )
                            self.stdout.write(f"  ✅ {item['title_zh']} (图片已更新)")
                        else:
                            self.stdout.write(f"  ⚠️ {item['title_zh']} (图片下载失败: HTTP {resp.status_code})")
                    except Exception as e:
                        self.stdout.write(f"  ⚠️ {item['title_zh']} (图片下载失败: {e})")
                else:
                    self.stdout.write(f"  ✅ {item['title_zh']}")

        total_products = Product.objects.count()
        total_prices = ProductDatePrice.objects.count()
        total_images = ProductImage.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\n🎉 填充完成！共 {total_products} 个产品，{total_prices} 个日期价格，{total_images} 张图片"))
