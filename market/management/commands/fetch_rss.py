"""
RSS 采集命令 — 抓取文章、提取全文、翻译中文

用法：
    python manage.py fetch_rss                    # 抓取所有源
    python manage.py fetch_rss --source 1          # 只抓指定源
    python manage.py fetch_rss --limit 5           # 每源最多5篇
    python manage.py fetch_rss --translate         # 翻译成中文
"""
import re
import feedparser
import requests
from datetime import datetime, timezone
from django.core.management.base import BaseCommand
from django.utils import timezone as tz
from bs4 import BeautifulSoup
from readability import Document
from market.models import RssSource, Article


# ── 目标人物 & 关键词过滤 ──
# 只在标题/摘要/正文包含以下内容的文章才会入库
TARGET_PEOPLE = {
    "jensen huang", "黄仁勋",
    "elon musk", "马斯克",
    "donald trump", "trump", "特朗普",
    "jerome powell", "powell", "鲍威尔",
    "janet yellen", "yellen", "耶伦",
}

TARGET_KEYWORDS = {
    # 黄仁勋 / NVIDIA
    "five-layer cake", "five layer cake", "五层蛋糕",
    "nvidia", "nvda", "blackwell", "h100", "h200", "b100",
    "cuda", "gb200", "dgx", "jensen huang",
    # 马斯克 / 科技前沿
    "tesla", "spacex", "starlink", "星链", "x.ai", "grok",
    "neuralink", "optimus", "cybertruck", "fsd", "full self-driving",
    "dojo", "starship", "星舰",
    "elon musk",
    # 特朗普 / 政策
    "tariff", "tariffs", "关税",
    "trade war", "贸易战",
    "china tariff", "decoupling", "脱钩",
    "trump policy", "trump administration",
    "trump's tariff",
    # 美国宏观政策
    "interest rate", "interest rates", "利率",
    "federal reserve", "fed", "美联储",
    "quantitative easing", "qe", "量化宽松",
    "quantitative tightening", "qt", "量化紧缩",
    "inflation", "cpi", "pce", "通胀",
    "monetary policy", "货币政策",
    "fomc", "federal funds",
    "rate cut", "rate cuts", "rate hike", "rate hikes", "降息", "加息",
    "treasury yield",
    "nonfarm payroll", "jobs report",
    "core inflation", "disinflation",
    # 科技前沿（限定较具体的词）
    "supercomputer", "超算",
    "autonomous driving", "自动驾驶",
    "robotaxi", "humanoid robot", "人形机器人",
}


def _matches_target(title, summary, content_text):
    """检查文章是否匹配目标人物或关键词"""
    title_lower = title.lower()
    text_lower = f"{title} {summary} {content_text}".lower()

    # 1. 人物匹配 — 标题含目标人物名
    for person in TARGET_PEOPLE:
        if person in title_lower:
            return True

    # 2. 关键词匹配 — 标题至少含1个关键词
    title_match = False
    for kw in TARGET_KEYWORDS:
        if kw in title_lower:
            title_match = True
            break
    if title_match:
        return True

    # 3. 人物在正文中提及 + 至少1个关键词在正文中（深度匹配）
    has_person = any(p in text_lower for p in TARGET_PEOPLE)
    has_kw = any(kw in text_lower for kw in TARGET_KEYWORDS)
    if has_person and has_kw:
        return True

    return False


def _make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,en;q=0.9",
    })
    s.timeout = 20
    return s


def fetch_full_text(url, session):
    """下载文章并提取正文（优先 readability，fallback BeautifulSoup）"""
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
    except Exception:
        return ""

    html = resp.text
    if len(html) < 500:
        return ""

    try:
        # readability 提取
        doc = Document(html)
        summary_html = doc.summary()
        summary_soup = BeautifulSoup(summary_html, "html.parser")
        # 移除无用标签
        for tag in summary_soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        # 按段落提取（保留段落结构）
        paragraphs = []
        for tag in summary_soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]):
            t = tag.get_text(strip=True)
            if t:
                paragraphs.append(t)
        # 如果段落提取失败，fallback 到全文本
        if len(paragraphs) < 2:
            text = summary_soup.get_text(separator=" ", strip=True)
            text = ' '.join(text.split())
        else:
            text = "\n\n".join(paragraphs)
        if len(text) > 200:
            return text[:10000]
    except Exception:
        pass

    # fallback: BeautifulSoup 全文提取
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
            tag.decompose()
        blocks = []
        for tag in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]):
            t = tag.get_text(strip=True)
            if t:
                blocks.append(t)
        if blocks:
            text = "\n\n".join(blocks[:50])
            return text[:10000] if len(text) > 200 else ""
        article = soup.find("article") or soup.find("main") or soup.body
        if article:
            text = article.get_text(separator=" ", strip=True)
            text = ' '.join(text.split())
            return text[:10000] if len(text) > 200 else ""
    except Exception:
        pass

    return ""


def translate_text(text, target="zh-CN"):
    """翻译成中文（依次尝试多个翻译后端）"""
    if not text or len(text) < 80:
        return ""
    chunks = [text[i:i+1500] for i in range(0, len(text), 1500)]
    result = []
    for chunk in chunks:
        if len(chunk.strip()) < 20:
            result.append(chunk)
            continue
        translated = _try_translate(chunk, target)
        result.append(translated or chunk)
    return "\n".join(result)


def translate_title(title):
    """翻译文章标题为中文"""
    if not title or len(title) < 10:
        return title
    try:
        from deep_translator import GoogleTranslator
        t = GoogleTranslator(source="auto", target="zh-CN").translate(title)
        if t:
            return t
    except Exception:
        pass
    try:
        from deep_translator import MyMemoryTranslator
        t = MyMemoryTranslator(source="en-US", target="zh-CN").translate(title)
        if t:
            return t
    except Exception:
        pass
    return title


def _try_translate(text, target):
    """依次尝试多个翻译后端"""
    # 1. Google Translate（VPN下最快）
    try:
        from deep_translator import GoogleTranslator
        t = GoogleTranslator(source="auto", target=target).translate(text)
        if t and t != text:
            return t
    except Exception:
        pass
    # 2. MyMemory（备选）
    try:
        from deep_translator import MyMemoryTranslator
        t = MyMemoryTranslator(source="en-US", target=target).translate(text)
        if t and t != text:
            return t
    except Exception:
        pass
    return None


class Command(BaseCommand):
    help = "抓取 RSS → 提取全文 → 入库"

    def add_arguments(self, parser):
        parser.add_argument("--source", type=int, help="只抓取指定源 ID")
        parser.add_argument("--limit", type=int, default=20, help="每源最多抓取篇数")
        parser.add_argument("--no-translate", action="store_true", help="跳过翻译")

    def handle(self, *args, **options):
        sources = RssSource.objects.filter(is_active=True)
        if options["source"]:
            sources = sources.filter(id=options["source"])

        session = _make_session()
        total_new = 0

        for src in sources:
            self.stdout.write(f"\n📡 {src.name} ", ending="")
            self.stdout.flush()

            try:
                feed = feedparser.parse(src.feed_url)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ 连接失败"))
                continue

            if feed.bozo and not feed.entries:
                self.stdout.write(self.style.ERROR(f"✗ 解析失败"))
                continue

            self.stdout.write(f"({len(feed.entries)} 篇)")

            new_count = 0
            for entry in feed.entries[: options["limit"]]:
                url = (entry.get("link") or "").strip()
                if not url:
                    continue
                if Article.objects.filter(url=url).exists():
                    continue

                title = (entry.get("title") or "").strip()
                if not title:
                    continue

                # 作者
                author = ""
                if hasattr(entry, "author") and entry.author:
                    author = entry.author.strip()
                elif hasattr(entry, "authors") and entry.authors:
                    author = entry.authors[0].get("name", "")

                # 摘要
                summary = ""
                if hasattr(entry, "summary") and entry.summary:
                    summary = entry.summary.strip()
                elif hasattr(entry, "description") and entry.description:
                    summary = entry.description.strip()
                if summary:
                    summary = re.sub(r"<[^>]+>", "", summary)[:500]

                # 日期
                pub_date = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

                # 标签
                tags = []
                if hasattr(entry, "tags"):
                    for t in entry.tags:
                        term = t.get("term", "") or t.get("label", "")
                        if term:
                            tags.append(term)

                # 关键词过滤（先检查标题+摘要，不匹配则跳过）
                if not _matches_target(title, summary, ""):
                    self.stdout.write(f"⏭")
                    continue

                # 获取全文
                self.stdout.write(f"\n    ↓ {title[:40]}... ", ending="")
                self.stdout.flush()
                content_text = fetch_full_text(url, session)

                # 用全文再做一次过滤
                if content_text and not _matches_target(title, summary, content_text):
                    self.stdout.write("⏭ (内容不匹配)")
                    continue

                # 翻译
                content_translated = ""
                if not options.get("no_translate") and content_text:
                    self.stdout.write("🌐 ", ending="")
                    self.stdout.flush()
                    content_translated = translate_text(content_text)

                # 标题翻译成中文
                if content_text or content_translated:
                    cn_title = translate_title(title)
                    if cn_title and cn_title != title:
                        title = cn_title

                self.stdout.write("✓")
                if not content_text:
                    self.stdout.write(" (摘要)")

                Article.objects.create(
                    title=title,
                    url=url,
                    source="rss",
                    source_name=src.name,
                    author=author,
                    summary=summary,
                    content_text=content_text[:10000] if content_text else "",
                    content_translated=content_translated[:10000] if content_translated else "",
                    tags=",".join(tags[:5]),
                    published_at=pub_date,
                )
                new_count += 1

            src.last_fetched = tz.now()
            src.save(update_fields=["last_fetched"])
            total_new += new_count
            self.stdout.write(f"\n    ➡ {new_count} 篇新增")

        self.stdout.write(self.style.SUCCESS(f"\n🎉 完成！共新增 {total_new} 篇文章"))
