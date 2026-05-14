"""
初始化精准 RSS 订阅源 — 聚焦黄仁勋/马斯克/特朗普/美国宏观政策
"""
from django.core.management.base import BaseCommand
from market.models import RssSource


class Command(BaseCommand):
    help = "添加定向 RSS 订阅源（黄仁勋·马斯克·特朗普·美国宏观）"

    def handle(self, *args, **options):
        sources = [
            # ── 黄仁勋 / NVIDIA ──
            ("NVIDIA Blog", "https://blogs.nvidia.com/feed/", "https://blogs.nvidia.com", "芯片/AI"),

            # ── 马斯克 / 科技前沿 ──
            ("TechCrunch", "https://techcrunch.com/feed/", "https://techcrunch.com", "科技前沿"),
            ("The Verge", "https://www.theverge.com/rss/index.xml", "https://www.theverge.com", "科技前沿"),
            ("Wired", "https://www.wired.com/feed/rss", "https://www.wired.com", "科技前沿"),

            # ── 特朗普 / 美国政策 ──
            ("The Hill", "https://thehill.com/feed/", "https://thehill.com", "美国政策"),
            ("Politico", "https://rss.politico.com/politiconews.xml", "https://www.politico.com", "美国政策"),

            # ── 美国宏观政策（利率 / QE / 通胀）──
            ("CNBC Fed", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "https://www.cnbc.com", "宏观"),
            ("MarketWatch Economy", "https://feeds.marketwatch.com/marketwatch/economy", "https://www.marketwatch.com", "宏观"),
            ("Reuters Business", "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best", "https://www.reuters.com", "宏观"),

            # ── 综合科技 ──
            ("ArsTechnica", "https://feeds.arstechnica.com/arstechnica/index", "https://arstechnica.com", "科技综合"),
        ]

        created = 0
        for name, feed_url, site_url, category in sources:
            _, is_new = RssSource.objects.get_or_create(
                feed_url=feed_url,
                defaults={"name": name, "site_url": site_url, "category": category},
            )
            if is_new:
                created += 1
                self.stdout.write(f"  ➕ {name} ({category})")

        self.stdout.write(self.style.SUCCESS(f"\n🎉 完成！新增 {created} 个订阅源"))
        self.stdout.write("   运行 python manage.py fetch_rss 开始抓取")
