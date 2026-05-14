"""
翻译已有文章到中文 — 逐篇翻译 content_text → content_translated

用法：
    python manage.py translate_articles              # 翻译所有未翻译的
    python manage.py translate_articles --source 1    # 只翻译指定文章ID
"""
from django.core.management.base import BaseCommand
from market.models import Article
from market.management.commands.fetch_rss import translate_text


class Command(BaseCommand):
    help = "翻译文章到中文"

    def add_arguments(self, parser):
        parser.add_argument("--pk", type=int, help="只翻译指定文章ID")

    def handle(self, *args, **options):
        qs = Article.objects.exclude(content_text="").exclude(content_text__isnull=True)
        if options["pk"]:
            qs = qs.filter(pk=options["pk"])

        total = qs.count()
        done = 0
        self.stdout.write(f"📖 待翻译: {total} 篇")

        for article in qs:
            if article.content_translated:
                self.stdout.write(f"  ⏭ [{article.pk}] {article.title[:40]} — 已有翻译")
                continue

            self.stdout.write(f"  🌐 [{article.pk}] {article.title[:40]}... ", ending="")
            self.stdout.flush()

            try:
                translated = translate_text(article.content_text)
                if translated:
                    article.content_translated = translated
                    article.save(update_fields=["content_translated"])
                    self.stdout.write(self.style.SUCCESS("✓"))
                else:
                    self.stdout.write(self.style.WARNING("略"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"失败: {e}"))

            done += 1

        self.stdout.write(self.style.SUCCESS(f"\n🎉 完成！翻译 {done} 篇"))
