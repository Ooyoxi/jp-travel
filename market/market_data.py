"""每日市场行情 — 从 yfinance 获取指数/商品/外汇数据"""
import json
import os
import time
import yfinance as yf
import warnings

warnings.filterwarnings("ignore")

CACHE_FILE = os.path.join(os.path.dirname(__file__), "_news_cache.json")
CACHE_TTL = 1800  # 30 分钟

# 主要跟踪标的
INDICES = {
    "^GSPC":  ("S&P 500", "SPY"),
    "^IXIC":  ("Nasdaq", "QQQ"),
    "^DJI":   ("道琼斯", "DIA"),
    "^VIX":   ("VIX 恐慌指数", None),
    "^RUT":   ("罗素2000", "IWM"),
    "DX-Y.NYB": ("美元指数", None),
    "CL=F":   ("原油", "USO"),
    "GC=F":   ("黄金", "GLD"),
    "^TNX":   ("10年美债收益率", None),
    "BTC-USD": ("比特币", "IBIT"),
}

# 另加关注的个股（最新价）
STOCKS = {
    "NVDA": "NVIDIA",
    "GOOGL": "Google",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "AMZN": "Amazon",
    "META": "Meta",
    "TSLA": "Tesla",
    "AVGO": "Broadcom",
    "VRT": "Vertiv",
    "COHR": "Coherent",
}


def fetch_market_data():
    """获取所有指数和股票的最新行情"""
    tickers = list(INDICES.keys()) + list(STOCKS.keys())
    data = yf.download(tickers, period="5d", group_by="ticker", progress=False)

    indices_data = []
    for symbol, (name, etf) in INDICES.items():
        try:
            if symbol in data.columns.levels[1] if isinstance(data.columns, pd.MultiIndex) else False:
                # MultiIndex columns
                df = data[symbol]
            else:
                # Try to get ticker data separately
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="5d")
                if hist.empty:
                    continue
                last_close = float(hist["Close"].iloc[-1])
                prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_close
                change = last_close - prev_close
                change_pct = (change / prev_close) * 100
                indices_data.append({
                    "symbol": symbol, "name": name, "etf": etf,
                    "price": round(last_close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                })
                continue

            if df.empty or len(df) < 2:
                continue
            last_close = float(df["Close"].iloc[-1])
            prev_close = float(df["Close"].iloc[-2])
            change = last_close - prev_close
            change_pct = (change / prev_close) * 100
            indices_data.append({
                "symbol": symbol, "name": name, "etf": etf,
                "price": round(last_close, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            })
        except Exception:
            continue

    stocks_data = []
    for symbol, name in STOCKS.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if hist.empty:
                continue
            last_close = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last_close
            change = last_close - prev_close
            change_pct = (change / prev_close) * 100
            stocks_data.append({
                "symbol": symbol, "name": name,
                "price": round(last_close, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            })
        except Exception:
            continue

    return indices_data, stocks_data


def _translate(text, target="zh-CN"):
    """翻译英文到中文（带缓存）"""
    if not text or len(text.strip()) < 5:
        return text
    try:
        from deep_translator import GoogleTranslator
        t = GoogleTranslator(source="en", target=target)
        # 分段翻译（单次不超过 5000 字符）
        if len(text) > 4000:
            chunks = []
            for i in range(0, len(text), 3000):
                chunk = text[i:i+3000]
                chunks.append(t.translate(chunk))
            return " ".join(chunks)
        return t.translate(text)
    except Exception:
        return text


def _fetch_article_content(url, timeout=10):
    """抓取并提取文章正文"""
    import requests
    from readability import Document
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        s = requests.Session()
        s.headers.update(headers)
        # 先访问首页获取 cookies
        s.get("https://finance.yahoo.com", timeout=10)
        r = s.get(url, timeout=timeout)
        if r.status_code != 200:
            return None, None
        doc = Document(r.text)
        html = doc.summary()
        if not html:
            return None, None
        soup = BeautifulSoup(html, "lxml")
        # 移除无用元素
        for tag in soup(["script", "style", "aside", "nav", "figure"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # 合并短行
        lines = [l for l in text.split("\n") if len(l.strip()) > 20]
        content = "\n\n".join(lines[:50])
        return doc.title(), content
    except Exception:
        return None, None


def _load_cache():
    """读取缓存"""
    try:
        if os.path.exists(CACHE_FILE) and time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TTL:
            with open(CACHE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save_cache(data):
    """写入缓存"""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_market_news(force_refresh=False):
    """
    从 yfinance 获取市场新闻，提取正文并翻译为中文。
    缓存 30 分钟避免每次加载耗时过长。
    """
    if not force_refresh:
        cached = _load_cache()
        if cached:
            return cached

    from datetime import datetime
    import concurrent.futures

    queries = ["US stock market", "market news", "wall street", "tech stocks"]
    seen = set()
    articles = []
    for q in queries:
        try:
            s = yf.Search(q)
            for n in s.news:
                uid = n.get("uuid", "")
                if uid and uid not in seen:
                    seen.add(uid)
                    pub_time = datetime.fromtimestamp(n.get("providerPublishTime", 0))
                    articles.append({
                        "title": n.get("title", ""),
                        "publisher": n.get("publisher", ""),
                        "link": n.get("link", ""),
                        "published_at": pub_time.isoformat(),
                        "tickers": n.get("relatedTickers", []),
                    })
        except Exception:
            continue
    articles.sort(key=lambda a: a["published_at"], reverse=True)
    articles = articles[:7]

    def process(art):
        url = art["link"]
        orig_title, content = _fetch_article_content(url)
        cn_title = _translate(orig_title or art["title"])
        cn_content = ""
        if content:
            cn_content = _translate(content)
        art["cn_title"] = cn_title
        art["content"] = content
        art["cn_content"] = cn_content
        return art

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(process, articles))

    _save_cache(results)
    return results

    return results


# 单独调用测试
if __name__ == "__main__":
    import pandas as pd
    idx, stk = fetch_market_data()
    print(f"{'指数行情':=^60}")
    for d in idx:
        arrow = "🔺" if d["change"] > 0 else "🔻"
        print(f"  {d['name']:12s} ${d['price']:>8.2f}  {arrow} {d['change']:+.2f} ({d['change_pct']:+.2f}%)")
    print(f"\n{'个股行情':=^60}")
    for d in stk:
        arrow = "🔺" if d["change"] > 0 else "🔻"
        print(f"  {d['symbol']:6s} {d['name']:12s} ${d['price']:>8.2f}  {arrow} {d['change']:+.2f} ({d['change_pct']:+.2f}%)")
