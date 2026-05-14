"""
ETF轮动策略 — 完整回测 + 贝叶斯 Walk-Forward 优化
"""
from etf_rotation_strategy import (
    ETFRotationStrategy, ETF_POOL,
    WalkForwardOptimizer, BayesianWalkForwardOptimizer,
)

TOKEN = "d45373f7d85863f2d4193ce5fdd0d58e8e7d42f5db4db422be883cbc171d"
START = '20180101'
END   = '20260510'
CASH  = 30000

# ============================================================
# 1. 默认策略回测
# ============================================================
print("=" * 60)
print("  【1/3】默认策略回测 (init_cash=30000)")
print("=" * 60)

strategy = ETFRotationStrategy(
    ETF_POOL, START, END, TOKEN,
    alpha_params={
        'periods': [6, 12, 18],
        'weights': [0.5, 0.3, 0.2],
        'vol_adjust': True,
        'rank_normalize': True,
        'decay_rate': 0.15,
    },
    risk_params={
        'select_n': 5,
        'corr_window': 20,
        'holding_weeks': 3,
        'corr_method': 'ewma',
        'ewma_span': 60,
    },
    init_cash=CASH,
)
strategy.fetch_all_data()
strategy.run_backtest(verbose=True, stop_loss=0)
strategy.plot_results()
strategy.print_trade_log(n=20)

# ============================================================
# 2. 网格搜索 Walk-Forward（对照基线）
# ============================================================
print("\n" + "=" * 60)
print("  【2/3】Walk-Forward 网格搜索")
print("=" * 60)

wf = WalkForwardOptimizer(
    ETF_POOL, START, END, TOKEN,
    n_splits=4, init_cash=CASH,
)
wf.fetch_data()
wf.run(verbose=True)
wf.plot_walk_forward()

# ============================================================
# 3. 贝叶斯 Walk-Forward 优化 ← 这是重点
# ============================================================
print("\n" + "=" * 60)
print("  【3/3】Walk-Forward 贝叶斯优化")
print("  (n_initial=15 + n_iterations=30 per fold)")
print("=" * 60)

bof = BayesianWalkForwardOptimizer(
    ETF_POOL, START, END, TOKEN,
    n_splits=3,
    n_initial=15,      # 初始 Latin Hypercube 采样
    n_iterations=30,   # 贝叶斯迭代次数
    random_state=42,
    init_cash=CASH,
)
bof.fetch_data()
bof.run(verbose=True)
bof.plot_walk_forward()

print("\n✅ 全部完成！")
print("   - 贝叶斯优化的 OOS 夏普 =", bof.final_results.get('夏普比率(OOS)', 'N/A'))
