"""
美股七强（Magnificent 7）最新季度财报重点总结
以管理命令方式写入学习笔记
"""
import django
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import yfinance as yf
from notes.models import NoteCategory, Note

MAG7 = {
    "AAPL": "苹果 (Apple)",
    "MSFT": "微软 (Microsoft)",
    "GOOGL": "谷歌 (Alphabet)",
    "AMZN": "亚马逊 (Amazon)",
    "NVDA": "英伟达 (NVIDIA)",
    "META": "Meta",
    "TSLA": "特斯拉 (Tesla)",
}


def fmt_b(val):
    """format dollar amount in billions"""
    if val is None:
        return "N/A"
    return "${:.2f}B".format(val / 1e9)


def fmt_d(val):
    """format dollar amount as unit price"""
    if val is None:
        return "N/A"
    return "${:.2f}".format(val)


def get_quarter_data(tk):
    """提取最新季度关键财务数据"""
    qf = tk.quarterly_financials
    if qf is None or qf.empty:
        return None

    cols = qf.columns
    lq = cols[0]
    # 找去年同期
    lq_yoy = None
    for c in cols:
        if c.month == lq.month and c.year == lq.year - 1:
            lq_yoy = c
            break

    def v(series_name, date):
        if series_name not in qf.index or date not in qf.columns:
            return None
        return float(qf.loc[series_name, date])

    rev = v("Total Revenue", lq)
    rev_yoy = v("Total Revenue", lq_yoy) if lq_yoy else None
    ni = v("Net Income", lq)
    ni_yoy = v("Net Income", lq_yoy) if lq_yoy else None
    eps = v("Diluted EPS", lq)
    eps_yoy = v("Diluted EPS", lq_yoy) if lq_yoy else None
    gp = v("Gross Profit", lq)
    op = v("Operating Income", lq)
    rd = v("Research And Development", lq)

    def pct(a, b):
        if a and b and b != 0:
            return "{:+.1f}".format((a / b - 1) * 100)
        return None

    info = tk.info
    return {
        "quarter_end": lq,
        "revenue": rev,
        "revenue_yoy_pct": pct(rev, rev_yoy),
        "net_income": ni,
        "net_income_yoy_pct": pct(ni, ni_yoy),
        "eps": eps,
        "eps_yoy_pct": pct(eps, eps_yoy),
        "gross_profit": gp,
        "gross_margin": "{:.1f}%".format(gp / rev * 100) if gp and rev else "N/A",
        "operating_income": op,
        "operating_margin": "{:.1f}%".format(op / rev * 100) if op and rev else "N/A",
        "rd_expense": rd,
        "rd_pct": "{:.1f}%".format(rd / rev * 100) if rd and rev else "N/A",
        "market_cap": info.get("marketCap"),
        "pe": info.get("trailingPE"),
        "industry": info.get("industry", ""),
        "sector": info.get("sector", ""),
        "description": info.get("longBusinessSummary", ""),
    }


def build_summary(data):
    """生成中文财报总结"""
    q = data["quarter_end"]
    y = q.year
    m = q.month
    if m <= 3:
        q_label = "Q1"
    elif m <= 6:
        q_label = "Q2"
    elif m <= 9:
        q_label = "Q3"
    else:
        q_label = "Q4"

    rev_str = fmt_b(data["revenue"])
    ni_str = fmt_b(data["net_income"])
    gp_str = fmt_b(data["gross_profit"])
    op_str = fmt_b(data["operating_income"])
    rd_str = fmt_b(data["rd_expense"])
    cap_str = fmt_b(data["market_cap"])

    lines = [
        "### {name} ({ticker})".format(
            name=data["company_name"], ticker=data["ticker"]
        ),
        "📅 {q} {year}（截止 {date}）| 市值 {cap} | P/E {pe}".format(
            q=q_label,
            year=y,
            date=data["quarter_end"].date(),
            cap=cap_str,
            pe=data["pe"] or "N/A",
        ),
        "",
        "**核心业绩**",
        "- 营收: {rev}（同比 **{yoy}%**）".format(
            rev=rev_str, yoy=data["revenue_yoy_pct"]
        ),
        "- 净利润: {ni}（同比 **{yoy}%**）".format(
            ni=ni_str, yoy=data["net_income_yoy_pct"]
        ),
        "- EPS: {eps}（同比 **{yoy}%**）".format(
            eps=fmt_d(data["eps"]), yoy=data["eps_yoy_pct"]
        ),
        "",
        "**盈利能力**",
        "- 毛利: {gp}（毛利率 {margin}）".format(
            gp=gp_str, margin=data["gross_margin"]
        ),
        "- 营业利润: {op}（营业利润率 {margin}）".format(
            op=op_str, margin=data["operating_margin"]
        ),
        "- 研发投入: {rd}（占营收 {pct}）".format(
            rd=rd_str, pct=data["rd_pct"]
        ),
        "",
        "**业务概况**",
        data["description"][:300] + "...",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def main():
    cat, _ = NoteCategory.objects.get_or_create(
        name="公司分析", defaults={"slug": "company-analysis"}
    )

    parts = [
        "# 美股七强最新季度财报总结",
        "",
        "**更新日期**: {}".format(
            __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        ),
        "",
        "涵盖苹果（AAPL）、微软（MSFT）、谷歌（GOOGL）、亚马逊（AMZN）、",
        "英伟达（NVDA）、Meta（META）、特斯拉（TSLA）的最新季度财务表现。",
        "",
        "---",
        "",
    ]

    all_data = []
    for sym, name in MAG7.items():
        print("📡 获取 {} {}...".format(sym, name))
        tk = yf.Ticker(sym)
        data = get_quarter_data(tk)
        if data:
            data["ticker"] = sym
            data["company_name"] = name
            all_data.append(data)
            parts.append(build_summary(data))

    # 汇总对比表
    parts.append("## 七强横向对比")
    parts.append("")
    parts.append(
        "| 公司 | 营收 | 营收同比 | 净利润 | 净利润同比 | EPS | 毛利率 | 营业利润率 | P/E |"
    )
    parts.append(
        "|------|------|----------|--------|------------|-----|--------|------------|-----|"
    )

    for d in all_data:
        parts.append(
            "| {name} | {rev} | {rev_yoy}% | {ni} | {ni_yoy}% | ${eps} | {gm} | {om} | {pe} |".format(
                name=d["company_name"],
                rev=fmt_b(d["revenue"]),
                rev_yoy=d["revenue_yoy_pct"],
                ni=fmt_b(d["net_income"]),
                ni_yoy=d["net_income_yoy_pct"],
                eps=d["eps"],
                gm=d["gross_margin"],
                om=d["operating_margin"],
                pe=d["pe"] or "N/A",
            )
        )

    parts.append("")
    parts.append("*数据来源: Yahoo Finance (yfinance)*")
    parts.append("")

    content = "\n".join(parts)

    note, created = Note.objects.update_or_create(
        slug="mag7-earnings-summary",
        defaults={
            "title": "美股七强最新季度财报总结",
            "category": cat,
            "tags": "美股,七强,MAG7,财报,Apple,Microsoft,Google,Amazon,NVIDIA,Meta,Tesla",
            "summary": "苹果、微软、谷歌、亚马逊、英伟达、Meta、特斯拉最新季度财务数据汇总与横向对比。",
            "content_md": content,
            "is_published": True,
        },
    )

    print("\n✅ 笔记已{}: {}".format("创建" if created else "更新", note.title))
    print("   访问: /notes/{}/".format(note.slug))


if __name__ == "__main__":
    main()
