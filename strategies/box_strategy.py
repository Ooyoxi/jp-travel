"""
个股箱体策略 v2 — 滚动箱体分析
Django 视图调用版本
"""
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

WINDOW = 60
STEP = 5
BOX_LOW_PCT = 20
BOX_HIGH_PCT = 80
MIN_TOUCHES = 3
BREAKOUT_PCT = 0.02

TICKERS = ["DRAM", "GOOGL", "NVDA", "BE", "NASA", "INTC"]
PERIODS = {"DRAM": "3mo", "GOOGL": "1y", "NVDA": "1y", "BE": "1y", "NASA": "6mo", "INTC": "1y"}
NAMES = {
    "DRAM": "Roundhill Memory ETF", "GOOGL": "Alphabet (Google)", "NVDA": "NVIDIA",
    "BE": "Bloom Energy", "NASA": "Tema Space Innovators ETF", "INTC": "Intel",
}


def fetch_data(ticker):
    period = PERIODS.get(ticker, "1y")
    df = yf.download(ticker, period=period, progress=False)
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def rolling_boxes(df):
    boxes = []
    n = len(df)
    if n < WINDOW:
        # 数据不足时，直接用全部数据做单箱体
        lo = float(np.percentile(df["Low"], BOX_LOW_PCT))
        hi = float(np.percentile(df["High"], BOX_HIGH_PCT))
        tl = int(((df["Low"] <= lo * 1.01) & (df["Low"] >= lo * 0.99)).sum())
        th = int(((df["High"] >= hi * 0.99) & (df["High"] <= hi * 1.01)).sum())
        boxes.append({
            "start_date": str(df.index[0].date()),
            "end_date": str(df.index[-1].date()),
            "box_low": round(lo, 2), "box_high": round(hi, 2),
            "range_pct": round((hi/lo-1)*100, 1),
            "touches_low": tl, "touches_high": th,
            "valid": tl >= MIN_TOUCHES and th >= MIN_TOUCHES,
        })
        return boxes
    for start in range(0, n - WINDOW + 1, STEP):
        win = df.iloc[start:start + WINDOW]
        lo = float(np.percentile(win["Low"], BOX_LOW_PCT))
        hi = float(np.percentile(win["High"], BOX_HIGH_PCT))
        tl = int(((win["Low"] <= lo*1.01) & (win["Low"] >= lo*0.99)).sum())
        th = int(((win["High"] >= hi*0.99) & (win["High"] <= hi*1.01)).sum())
        boxes.append({
            "start_date": str(df.index[start].date()),
            "end_date": str(df.index[start+WINDOW-1].date()),
            "box_low": round(lo, 2), "box_high": round(hi, 2),
            "range_pct": round((hi/lo-1)*100, 1),
            "touches_low": tl, "touches_high": th,
            "valid": tl >= MIN_TOUCHES and th >= MIN_TOUCHES,
        })
    return boxes


def cluster_levels(boxes, tolerance=0.05):
    lows = sorted([b["box_low"] for b in boxes if b["valid"]])
    highs = sorted([b["box_high"] for b in boxes if b["valid"]])

    def cluster(vals):
        if not vals:
            return []
        groups = []
        cur = [vals[0]]
        for v in vals[1:]:
            if v / cur[0] - 1 <= tolerance:
                cur.append(v)
            else:
                groups.append({"level": round(np.mean(cur), 2), "count": len(cur),
                               "min": round(min(cur), 2), "max": round(max(cur), 2)})
                cur = [v]
        groups.append({"level": round(np.mean(cur), 2), "count": len(cur),
                       "min": round(min(cur), 2), "max": round(max(cur), 2)})
        return groups

    return {"support_levels": cluster(lows), "resistance_levels": cluster(highs)}


def generate_signals(df, boxes):
    signals = []
    half_year_ago = df.index[-1] - timedelta(days=180)
    recent = [b for b in boxes if b["valid"] and b["end_date"] >= str(half_year_ago.date())]
    if not recent and boxes:
        recent = [b for b in boxes if b["valid"]]
    if not recent:
        return signals

    for i in range(len(df)):
        close = float(df["Close"].iloc[i])
        date = str(df.index[i].date())
        active = [b for b in recent if b["end_date"] <= date]
        if not active:
            continue
        for box in active:
            if close <= box["box_low"] * 1.02:
                if not signals or (pd.Timestamp(date) - pd.Timestamp(signals[-1]["date"])).days >= 7:
                    signals.append({"date": date, "price": round(close, 2), "type": "buy_support",
                                    "ref_low": box["box_low"], "ref_high": box["box_high"],
                                    "label": "支撑买入"})
                break
            if close >= box["box_high"] * (1 + BREAKOUT_PCT):
                if not signals or (pd.Timestamp(date) - pd.Timestamp(signals[-1]["date"])).days >= 7:
                    signals.append({"date": date, "price": round(close, 2), "type": "add_breakout",
                                    "ref_low": box["box_low"], "ref_high": box["box_high"],
                                    "label": "突破加仓"})
                break
    return signals


def backtest(df, signals):
    trades = []
    for i, s in enumerate(signals):
        if s["type"] == "buy_support":
            future = [x for x in signals[i+1:] if x["type"] == "add_breakout"]
            if future:
                fs = future[0]
                ret = (fs["price"] / s["price"] - 1) * 100
                trades.append({"buy_date": s["date"], "buy_price": s["price"],
                               "sell_date": fs["date"], "sell_price": fs["price"],
                               "return": round(ret, 1)})
            else:
                ret = (float(df["Close"].iloc[-1]) / s["price"] - 1) * 100
                trades.append({"buy_date": s["date"], "buy_price": s["price"],
                               "sell_date": str(df.index[-1].date()),
                               "sell_price": round(float(df["Close"].iloc[-1]), 2),
                               "return": round(ret, 1), "open": True})
    return trades


def run_analysis():
    results = {}
    for ticker in TICKERS:
        df = fetch_data(ticker)
        if df is None:
            results[ticker] = {"error": f"{ticker} 数据获取失败"}
            continue
        boxes = rolling_boxes(df)
        levels = cluster_levels(boxes)
        signals = generate_signals(df, boxes)
        trades = backtest(df, signals)
        valid_boxes = [b for b in boxes if b["valid"]]
        current_box = valid_boxes[-1] if valid_boxes else (boxes[-1] if boxes else None)
        last_close = round(float(df["Close"].iloc[-1]), 2)
        closed_trades = [t for t in trades if not t.get("open")]
        open_trades = [t for t in trades if t.get("open")]
        wins = sum(1 for t in closed_trades if t["return"] > 0)
        results[ticker] = {
            "name": NAMES.get(ticker, ticker),
            "box": current_box,
            "levels": levels,
            "last_close": last_close,
            "last_date": str(df.index[-1].date()),
            "data_points": len(df),
            "total_windows": len(boxes),
            "valid_windows": len(valid_boxes),
            "buy_signals": [s for s in signals if s["type"] == "buy_support"],
            "add_signals": [s for s in signals if s["type"] == "add_breakout"],
            "closed_trades": closed_trades,
            "open_trades": open_trades,
            "trade_count": len(closed_trades),
            "win_count": wins,
            "win_rate": round(wins / len(closed_trades) * 100) if closed_trades else 0,
        }
    return results
