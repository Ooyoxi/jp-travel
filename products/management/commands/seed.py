from django.core.management.base import BaseCommand
from products.models import Category, Product, ProductDatePrice
from datetime import date, timedelta


PRODUCTS = [
    {
        "category": "景点门票",
        "items": [
            {
                "title_zh": "东京迪士尼乐园一日门票",
                "title_ja": "東京ディズニーランド 1デイパスポート",
                "title_en": "Tokyo Disneyland 1-Day Passport",
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
                "title_zh": "大阪环球影城一日券",
                "title_ja": "USJ 1デイ・パス",
                "title_en": "Universal Studios Japan 1-Day Pass",
                "description_zh": "超级任天堂世界、哈利波特魔法世界等热门园区一票畅玩。",
                "description_ja": "スーパー・ニンテンドー・ワールド、ウィザーディング・ワールド・オブ・ハリー・ポッターなど。",
                "description_en": "Super Nintendo World, Wizarding World of Harry Potter and more!",
                "location_zh": "大阪市此花区",
                "location_ja": "大阪市此花区",
                "location_en": "Konohana, Osaka",
                "base_price": 8600,
                "duration_minutes": 600,
                "max_participants": 1,
                "min_participants": 1,
                "featured": True,
            },
            {
                "title_zh": "东京晴空塔展望台门票",
                "title_ja": "東京スカイツリー展望台入場券",
                "title_en": "Tokyo Skytree Observatory Ticket",
                "description_zh": "日本最高塔，350米和450米双展望台，360度俯瞰东京全景。",
                "description_ja": "日本一高いタワー。350mと450mの二つの展望台から東京を一望。",
                "description_en": "Japan's tallest tower. Dual observatories at 350m and 450m with 360° Tokyo views.",
                "location_zh": "东京都墨田区",
                "location_ja": "東京都墨田区",
                "location_en": "Sumida, Tokyo",
                "base_price": 2100,
                "duration_minutes": 120,
                "max_participants": 1,
                "min_participants": 1,
                "featured": True,
            },
        ],
    },
    {
        "category": "体验活动",
        "items": [
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
        "category": "交通票券",
        "items": [
            {
                "title_zh": "日本铁路周游券（7日）",
                "title_ja": "ジャパンレールパス（7日間）",
                "title_en": "JR Pass 7 Days",
                "description_zh": "无限次乘坐JR全国线路（含新干线），7天内畅游日本各地。超值之选。",
                "description_ja": "全国のJR線（新幹線含む）が7日間乗り放題。日本一周旅行に最適。",
                "description_en": "Unlimited JR rides nationwide including Shinkansen for 7 days. Best value for multi-city travel.",
                "location_zh": "全国通用",
                "location_ja": "全国利用可能",
                "location_en": "Nationwide",
                "base_price": 50000,
                "duration_minutes": 10080,
                "max_participants": 1,
                "min_participants": 1,
                "featured": True,
            },
            {
                "title_zh": "东京地铁24小时券",
                "title_ja": "東京メトロ24時間券",
                "title_en": "Tokyo Metro 24-Hour Pass",
                "description_zh": "24小时内无限次乘坐东京地铁全线，覆盖东京主要景点区域。",
                "description_ja": "24時間東京メトロ全線乗り放題。主要観光エリアをカバー。",
                "description_en": "Unlimited Tokyo Metro rides for 24 hours. Covers all major sightseeing areas.",
                "location_zh": "东京都",
                "location_ja": "東京都",
                "location_en": "Tokyo",
                "base_price": 600,
                "duration_minutes": 1440,
                "max_participants": 1,
                "min_participants": 1,
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
        for cat_data in PRODUCTS:
            cat, _ = Category.objects.get_or_create(
                slug=cat_data["category"],
                defaults={
                    "name_zh": cat_data["category"],
                    "name_ja": cat_data["category"],
                    "name_en": cat_data["category"],
                },
            )
            for item in cat_data["items"]:
                product, created = Product.objects.get_or_create(
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
                if created:
                    # 创建未来90天的价格和库存
                    for i in range(90):
                        d = date.today() + timedelta(days=i + 1)
                        # 随机价格波动
                        import random
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
                    self.stdout.write(f"  ✅ {item['title_zh']}")
                else:
                    self.stdout.write(f"  ⏭️ {item['title_zh']} (已存在)")

        total_products = Product.objects.count()
        total_prices = ProductDatePrice.objects.count()
        self.stdout.write(self.style.SUCCESS(f"\n🎉 填充完成！共 {total_products} 个产品，{total_prices} 个日期价格"))
