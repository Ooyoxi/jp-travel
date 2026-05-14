"""
ETF轮动策略系统
基于《打开量化的黑箱》框架

框架结构：
  1. 阿尔法模型（Alpha Model）— 动量+均值回归复合因子
  2. 风险模型（Risk Model） — 低相关ETF选择 + 2周持有
  3. 交易成本模型（Transaction Cost Model） — Min5元 + 0.2%滑点
  4. 投资组合构建模型（Portfolio Construction） — 等权组合

作者：基于 quant.ipynb 中的动量策略重构
"""

import tushare as ts
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

# 贝叶斯优化依赖
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel, ConstantKernel
from scipy.stats import norm
from scipy.optimize import differential_evolution

# ===== 中文显示设置 =====
matplotlib.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'PingFang SC', 'Heiti SC']
matplotlib.rcParams['axes.unicode_minus'] = False

# ============================================================
# ETF 池（以指数/期货ETF为主，覆盖不同大类资产实现低相关性）
# ============================================================
ETF_POOL = {
    # ── A股核心宽基（精选、减少行业重叠） ──
    '510300.SH': '沪深300ETF',       # 全市场大盘
    '510500.SH': '中证500ETF',       # 中盘
    '159915.SZ': '创业板ETF',        # 成长
    '510880.SH': '红利ETF',          # 红利/价值

    # ── 全球/跨国 ETF（低相关核心来源） ──
    '513100.SH': '纳指ETF(QDII)',    # 美股科技
    '513500.SH': '标普500ETF',       # 美股全市场
    '513310.SH': '中韩半导体ETF',    # 中韩半导体
    '513080.SH': '法国CAC40ETF',     # 欧洲
    '513520.SH': '日经ETF',          # 日本
    '159509.SZ': '纳指科技ETF景顺',    # 美股科技（景顺长城纳斯达克科技市值加权ETF）
    '513180.SH': '恒生科技ETF',      # 港股科技

    # ── 商品 ──
    '518880.SH': '黄金ETF',          # 黄金
    '159985.SZ': '豆粕ETF',          # 农产品期货

    # ── 港股 ──
    '159920.SZ': '恒生ETF',          # 香港市场
}


# ============================================================
# 第一步：阿尔法模型 — 多周期动量因子
# ============================================================
class AlphaModel:
    """
    阿尔法模型：多周期动量因子

    采用多周期复合动量（6周、12周、18周加权），
    配合波动率调整、排名归一化和因子时序衰减。
    """

    def __init__(self, periods=[10, 14, 19], weights=[0.5, 0.3, 0.2],
                 vol_adjust=True, rank_normalize=True, decay_rate=0.25):
        """
        periods: 动量计算周期列表（周）
        weights: 各周期权重
        vol_adjust: 是否进行波动率调整
        rank_normalize: 是否进行排名归一化
        decay_rate: 因子时序衰减率，>0 表示近期权重更高（指数衰减）
        """
        self.periods = periods
        self.weights = np.array(weights)
        self.vol_adjust = vol_adjust
        self.rank_normalize = rank_normalize
        self.decay_rate = decay_rate
        self.weights = self.weights / self.weights.sum()

    def compute_scores(self, weekly_data):
        """
        计算所有ETF的多周期动量得分

        Returns
        -------
        pd.Series : 各ETF综合得分
        """
        scores = pd.Series(index=weekly_data.columns, dtype=float)

        for code in weekly_data.columns:
            series = weekly_data[code].dropna()
            if len(series) < max(self.periods) + 1:
                scores[code] = np.nan
                continue

            mom = 0.0
            for period, weight in zip(self.periods, self.weights):
                # 带时序衰减的动量计算
                ret = self._decayed_momentum(series, period)
                mom += weight * ret
            scores[code] = mom

        if self.rank_normalize:
            ranks = scores.rank(ascending=True, na_option='bottom')
            scores = (ranks - 1) / (ranks.max() - 1) * 2 - 1

        return scores

    def _decayed_momentum(self, series, period):
        """
        计算带指数时序衰减的周期动量

        在周期内对每周收益率进行指数加权，
        近期收益权重更高，体现因子时序衰减。
        """
        returns = series.pct_change().iloc[-(period + 1):]
        returns = returns.iloc[1:]  # 去掉第一个 NaN
        if len(returns) < 1:
            return np.nan

        # 指数衰减权重：越近权重越高
        n = len(returns)
        decay = np.exp(self.decay_rate * np.arange(n))
        decay = decay / decay.sum()

        mom = np.dot(returns.values, decay)

        if self.vol_adjust:
            vol = returns.std()
            if vol > 0:
                mom = mom / vol
        return mom


# ============================================================
# 第二步：风险模型 — 低相关性ETF选择
# ============================================================
class RiskModel:
    """
    风险模型：每次选取5只低相关性的ETF进行交易

    方法：
      1. 从候选池（阿尔法得分前列的ETF）中
      2. 使用贪心算法选择N只，使组内平均相关性最低
      3. 每3周调仓一次
      4. 相关性估计支持：EWMA（指数加权）、Ledoit-Wolf 收缩、Pearson
    """

    def __init__(self, select_n=5, corr_window=20, holding_weeks=3,
                 corr_method='ewma', ewma_span=61):
        """
        select_n: 每次选择的ETF数量
        corr_window: 相关性计算窗口（周数）
        holding_weeks: 持仓周数
        corr_method: 相关性估计方法 ('ewma', 'ledoit_wolf', 'pearson')
        ewma_span: EWMA衰减因子（仅 corr_method='ewma' 时使用）
        """
        self.select_n = select_n
        self.corr_window = corr_window
        self.holding_weeks = holding_weeks
        self.corr_method = corr_method
        self.ewma_span = ewma_span

    def select(self, weekly_returns, momentum_scores, candidate_ratio=2):
        """
        从ETF池中选出具低相关性的N只ETF

        Parameters
        ----------
        weekly_returns : pd.DataFrame
            周收益率矩阵
        momentum_scores : pd.Series
            动量得分
        candidate_ratio : float
            候选池倍率（从动量前 select_n*candidate_ratio 名中选）

        Returns
        -------
        list : 选中的ETF代码列表
        """
        # 按动量排序，取前 N*candidate_ratio 作为候选
        ranked = momentum_scores.dropna().sort_values(ascending=False)
        n_candidates = min(self.select_n * candidate_ratio, len(ranked))
        candidates = ranked.head(int(n_candidates)).index.tolist()

        if len(candidates) <= self.select_n:
            return candidates

        # 计算候选ETF的相关性矩阵
        returns = weekly_returns[candidates].dropna()
        if self.corr_method == 'ewma':
            corr = self._ewma_corr(returns)
        elif self.corr_method == 'ledoit_wolf':
            corr = self._ledoit_wolf_corr(returns)
        else:
            corr = returns.corr()

        # === 贪心算法 ===
        # 选出N只使组内平均相关性最低
        selected = []
        remaining = list(candidates)

        # 第一个：选与其他所有ETF平均相关性最低的
        avg_corrs = corr.mean()
        first = avg_corrs.idxmin()
        selected.append(first)
        remaining.remove(first)

        # 后续：每步选与已选组合平均相关性最低的
        while len(selected) < self.select_n:
            best_code = None
            best_corr = float('inf')

            for code in remaining:
                mean_corr = corr.loc[code, selected].mean()
                if mean_corr < best_corr:
                    best_corr = mean_corr
                    best_code = code

            if best_code:
                selected.append(best_code)
                remaining.remove(best_code)

        return selected

    def get_rebalance_dates(self, weekly_index):
        """
        生成调仓日期列表（每 holding_weeks 周一次）

        使用行索引间隔（W-FRI 周线数据每行相隔1周）
        避免因节假日造成的日期间隔不准确

        Returns
        -------
        list : 调仓日期
        """
        dates = sorted(weekly_index)
        # 每 holding_weeks 行选一个日期
        return [dates[i] for i in range(0, len(dates), self.holding_weeks)]

    def _ewma_corr(self, returns):
        """
        EWMA（指数加权移动平均）相关性估计

        给予近期收益率更高权重，体现时序衰减，
        比等权 Pearson 更能捕捉最新的相关性结构。
        """
        ew_cov = returns.ewm(span=self.ewma_span).cov()
        last_date = ew_cov.index.get_level_values(0)[-1]
        cov_matrix = ew_cov.loc[last_date]
        diag_std = np.sqrt(np.diag(cov_matrix))
        corr = cov_matrix / np.outer(diag_std, diag_std)
        return corr.clip(-1, 1)

    def _ledoit_wolf_corr(self, returns):
        """
        Ledoit-Wolf 收缩相关性估计

        将样本协方差向结构化目标收缩，
        降低估计噪声，在高维环境中更稳健。
        """
        try:
            from sklearn.covariance import LedoitWolf
            lw = LedoitWolf().fit(returns.values)
            cov = lw.covariance_
        except ImportError:
            print("⚠ sklearn 未安装，回退到 Pearson 相关系数")
            return returns.corr()

        diag_std = np.sqrt(np.diag(cov))
        corr = cov / np.outer(diag_std, diag_std)
        return pd.DataFrame(corr, index=returns.columns, columns=returns.columns).clip(-1, 1)


# ============================================================
# 第三步：交易成本模型
# ============================================================
class CostModel:
    """
    交易成本模型

    规则：
      - 最低手续费：5元/笔（ETF正常费率约万3，但不足5元按5元收）
      - 滑点：0.2%（用户设定）
      - 滑点模拟：买入时实际价格 = 价格 * (1 + 滑点率)
                      卖出时实际价格 = 价格 * (1 - 滑点率)
    """

    def __init__(self, min_fee=5.0, fee_rate=0.0003, slippage=0.002):
        """
        min_fee: 最低手续费（元）
        fee_rate: 手续费率（ETF通常万1~万3）
        slippage: 滑点率（0.2%）
        """
        self.min_fee = min_fee
        self.fee_rate = fee_rate
        self.slippage = slippage

    def buy_cost(self, price, shares):
        """
        计算买入成本
        返回: (实际买入价, 总花费, 手续费)
        """
        buy_price = price * (1 + self.slippage)
        principal = shares * buy_price
        fee = max(principal * self.fee_rate, self.min_fee)
        return buy_price, principal + fee, fee

    def sell_proceeds(self, price, shares):
        """
        计算卖出收益
        返回: (实际卖出价, 净收入, 手续费)
        """
        sell_price = price * (1 - self.slippage)
        proceeds = shares * sell_price
        fee = max(proceeds * self.fee_rate, self.min_fee)
        return sell_price, proceeds - fee, fee


# ============================================================
# 第四步：投资组合构建 — 等权
# ============================================================
class PortfolioConstruction:
    """
    投资组合构建模型：等权配置 + 增量调仓

    每次调仓：
      - 只卖出离开组合的ETF
      - 只买入新加入的ETF
      - 原有持仓不动（降低交易成本）
      持仓比例因价格变动会自然偏离等权，但避免了不必要的换仓成本。
    """

    def __init__(self, cost_model):
        self.cost_model = cost_model

    def rebalance(self, cash, holdings, selected_codes, prices_df, date,
                  etf_names=None):
        """
        增量调仓：只交易变化的品种

        Parameters
        ----------
        cash : float
            当前现金
        holdings : dict
            当前持仓 {code: shares}
        selected_codes : list
            新选中ETF代码
        prices_df : pd.DataFrame
            价格数据
        date : datetime
            调仓日期
        etf_names : dict
            ETF名称映射

        Returns
        -------
        dict : 新持仓 {code: shares}
        float : 新现金
        list : 交易记录
        """
        etf_names = etf_names or {}
        trades = []
        new_holdings = dict(holdings)  # 复制当前持仓

        # ---- 1. 计算清算所有持仓后的总资金（用于计算目标权重） ----
        # 先估算总资产（当前现金 + 持仓市值）
        total_value = cash
        code_values = {}
        for code, shares in holdings.items():
            if code in prices_df.columns and date in prices_df.index:
                px = prices_df.loc[date, code]
                if not pd.isna(px) and px > 0:
                    v = shares * px
                    code_values[code] = v
                    total_value += v

        n_selected = len(selected_codes)
        if n_selected == 0:
            return {}, cash, trades

        target_per_etf = total_value / n_selected

        # ---- 2. 卖出离开组合的ETF ----
        for code in list(new_holdings.keys()):
            if code not in selected_codes:
                shares = new_holdings[code]
                if code in prices_df.columns and date in prices_df.index:
                    px = prices_df.loc[date, code]
                    if not pd.isna(px):
                        _, proceeds, fee = self.cost_model.sell_proceeds(px, shares)
                        cash += proceeds
                        trades.append({
                            'date': date, 'code': code,
                            'name': etf_names.get(code, ''),
                            'action': 'SELL', 'price': round(px, 3),
                            'shares': shares, 'fee': round(fee, 2),
                            'value': round(proceeds, 2),
                        })
                del new_holdings[code]

        # ---- 3. 买入新加入的ETF ----
        for code in selected_codes:
            if code in new_holdings:
                continue  # 已有持仓，不动

            if code not in prices_df.columns or date not in prices_df.index:
                continue
            px = prices_df.loc[date, code]
            if pd.isna(px) or px <= 0:
                continue

            # 目标买入金额 = target_per_etf，但不能超过可用现金
            buy_target = min(target_per_etf, cash * 0.95)  # 预留fee空间
            buy_price = px * (1 + self.cost_model.slippage)
            divisor = buy_price * (1 + self.cost_model.fee_rate)
            shares = int(buy_target // divisor)

            if shares <= 0:
                continue

            total_cost = shares * buy_price
            fee = max(total_cost * self.cost_model.fee_rate, self.cost_model.min_fee)
            total_cost_with_fee = total_cost + fee

            if total_cost_with_fee <= cash:
                cash -= total_cost_with_fee
                new_holdings[code] = shares
                trades.append({
                    'date': date, 'code': code,
                    'name': etf_names.get(code, ''),
                    'action': 'BUY', 'price': round(buy_price, 3),
                    'shares': shares, 'fee': round(fee, 2),
                    'cost': round(total_cost_with_fee, 2),
                })

        return new_holdings, cash, trades


# ============================================================
# ETF轮动策略 — 主引擎
# ============================================================
class ETFRotationStrategy:
    """
    ETF轮动策略系统

    整合四层框架：
      - AlphaModel: 动量+均值回归复合因子
      - RiskModel: 低相关性ETF选择 + 2周持有
      - CostModel: Min5 + 0.2%滑点
      - PortfolioConstruction: 等权组合

    使用示例：
        strategy = ETFRotationStrategy(ETF_POOL, '20230101', '20260415', token)
        strategy.fetch_all_data()
        strategy.run_backtest()
        strategy.plot_results()
    """

    def __init__(self, etf_dict, start_date, end_date, token,
                 alpha_params=None, risk_params=None, cost_params=None,
                 init_cash=100000):
        """
        Parameters
        ----------
        etf_dict : dict
            {ts_code: name} 格式的ETF池
        start_date : str
            开始日期 (YYYYMMDD)
        end_date : str
            结束日期 (YYYYMMDD)
        token : str
            tushare token
        alpha_params : dict
            阿尔法模型参数
        risk_params : dict
            风险模型参数
        cost_params : dict
            成本模型参数
        init_cash : float
            初始资金
        """
        self.etf_dict = etf_dict
        self.etf_codes = list(etf_dict.keys())
        self.start_date = start_date
        self.end_date = end_date
        self.token = token
        self.init_cash = init_cash

        # 初始化子模型
        alpha_params = alpha_params or {}
        risk_params = risk_params or {}
        cost_params = cost_params or {}

        self.alpha = AlphaModel(**alpha_params)
        self.risk = RiskModel(**risk_params)
        self.cost = CostModel(**cost_params)
        self.pc = PortfolioConstruction(self.cost)

        # 数据容器
        self.raw_data = {}         # {code: daily_df}
        self.weekly_close = None   # 周线收盘价（所有ETF对齐）
        self.weekly_returns = None # 周线收益率

        # 结果容器
        self.equity_curve = pd.Series(dtype=float)
        self.trade_log = []
        self.holdings_history = {}  # {date: {code: shares}}
        self.results = {}
        self.drawdown_series = pd.Series(dtype=float)
        self.cash_history = pd.Series(dtype=float)

    # ----------------------------------------------------------
    # 数据获取
    # ----------------------------------------------------------
    def fetch_all_data(self):
        """
        获取所有ETF日线数据（使用 fund_daily），可选合并复权因子，转为周线
        """
        import time
        pro = ts.pro_api(self.token)
        pro._DataApi__token = self.token
        pro._DataApi__http_url = 'http://jiaoch.site'

        for idx, code in enumerate(self.etf_codes):
            try:
                if idx > 0:
                    time.sleep(0.3)  # 避免触发频率限制

                df = pro.fund_daily(ts_code=code,
                                    start_date=self.start_date,
                                    end_date=self.end_date)
                if df is None or df.empty:
                    print(f"⚠ {code} {self.etf_dict.get(code, '')} 无数据")
                    continue

                adj = pro.fund_adj(ts_code=code,
                                   start_date=self.start_date,
                                   end_date=self.end_date)
                if adj is not None and not adj.empty:
                    df = df.merge(adj, on='trade_date')
                    df['close'] = df['close'] * df['adj_factor']

                df['trade_date'] = pd.to_datetime(df['trade_date'])
                df = df.sort_values('trade_date')
                df.set_index('trade_date', inplace=True)
                self.raw_data[code] = df
                print(f"✓ {code} {self.etf_dict.get(code, '')}: {len(df)} 日")
            except Exception as e:
                print(f"✗ {code} 获取失败: {e}")

        self._build_weekly_matrix()
        return self

    def _build_weekly_matrix(self):
        """
        构建对齐的周线收盘价矩阵
        """
        close_dfs = []
        for code, df in self.raw_data.items():
            weekly = df['close'].resample('W-FRI').last().to_frame(code)
            close_dfs.append(weekly)

        if not close_dfs:
            raise ValueError("没有获取到任何数据")

        self.weekly_close = pd.concat(close_dfs, axis=1)
        # 删除全部为NaN的行
        self.weekly_close = self.weekly_close.dropna(how='all')
        self.weekly_returns = self.weekly_close.pct_change().dropna()

        n_etfs = self.weekly_close.shape[1]
        n_weeks = self.weekly_close.shape[0]
        print(f"\n✅ 周线数据矩阵: {n_weeks} 周 × {n_etfs} 只ETF")
        print(f"   时间范围: {self.weekly_close.index[0].strftime('%Y-%m-%d')} ~ "
              f"{self.weekly_close.index[-1].strftime('%Y-%m-%d')}")
        return self

    # ----------------------------------------------------------
    # 回测引擎
    # ----------------------------------------------------------
    def load_data(self, weekly_close, weekly_returns):
        """加载预计算数据（避免 Walk-Forward 网格搜索中重复API调用）"""
        self.weekly_close = weekly_close
        self.weekly_returns = weekly_returns
        return self

    def run_backtest(self, verbose=True, stop_loss=0):
        """
        执行完整回测

        流程：
          1. 生成所有调仓日期（每2周）
          2. 在每个调仓日：
             a. 阿尔法模型计算复合因子得分（动量+均值回归）
             b. 风险模型选出低相关性ETF
             c. 卖出不在新组合中的持仓
             d. 买入新ETF（等权组合）
             e. 记录持仓和净值
          3. 期间逐周检查止损（单只ETF亏损≥stop_loss时卖出）
          4. 计算绩效指标
        """
        if self.weekly_close is None:
            raise ValueError("请先调用 fetch_all_data()")

        rebalance_dates = self.risk.get_rebalance_dates(self.weekly_close.index)
        if verbose:
            print(f"\n🔄 调仓日期: {len(rebalance_dates)} 个")
            print(f"   首次: {rebalance_dates[0].strftime('%Y-%m-%d')}")
            print(f"   末次: {rebalance_dates[-1].strftime('%Y-%m-%d')}")

        # ---- 初始化 ----
        cash = self.init_cash
        holdings = {}            # {code: shares}
        cost_basis = {}          # {code: 买入时市场价（不含滑点）}
        all_weekly_dates = list(self.weekly_close.index)

        self.trade_log = []
        self.holdings_history = {}
        # 全部初始化为 init_cash，之后覆盖有实际值的
        equity_values = pd.Series(self.init_cash, index=all_weekly_dates, dtype=float)
        cash_values = pd.Series(self.init_cash, index=all_weekly_dates, dtype=float)

        # ---- 逐期调仓 ----
        for i, rebal_date in enumerate(rebalance_dates):
            date_idx = self.weekly_close.index.get_loc(rebal_date)

            # 检查数据是否足够计算动量
            if date_idx < max(self.alpha.periods) + 2:
                if verbose:
                    print(f"   ⏳ {rebal_date.strftime('%Y-%m-%d')}: 数据不足，跳过")
                continue

            # ---- 1. 阿尔法模型：计算复合因子得分 ----
            lookback = self.weekly_close.iloc[:date_idx]
            scores = self.alpha.compute_scores(lookback)

            # ---- 2. 风险模型：选择低相关性ETF ----
            returns_lookback = self.weekly_returns.iloc[:date_idx]
            selected = self.risk.select(returns_lookback, scores)

            if verbose and i % 5 == 0:
                names = [f"{c}({self.etf_dict.get(c,'')})" for c in selected]
                print(f"\n📅 {rebal_date.strftime('%Y-%m-%d')} 调仓:")
                print(f"   选中: {', '.join(names)}")

            # ---- 3. 组合构建：增量调仓（只交易变化的品种） ----
            holdings, cash, new_trades = self.pc.rebalance(
                cash, holdings, selected, self.weekly_close, rebal_date,
                etf_names=self.etf_dict
            )
            self.trade_log.extend(new_trades)

            # 记录调仓日持仓
            self.holdings_history[rebal_date] = dict(holdings)

            # 记录买入成本价（用于止损判断）
            for t in new_trades:
                if t['action'] == 'BUY' and t['code'] in self.weekly_close.columns:
                    if rebal_date in self.weekly_close.index:
                        cost_basis[t['code']] = self.weekly_close.loc[rebal_date, t['code']]

            # ---- 5. 更新净值（含逐周止损检查）----
            for w_idx in range(date_idx, len(all_weekly_dates)):
                w_date = all_weekly_dates[w_idx]

                # 止损检查：单只ETF亏损≥stop_loss时卖出
                if stop_loss < 0 and w_idx > date_idx:
                    for code in list(holdings.keys()):
                        if code not in cost_basis or cost_basis[code] <= 0:
                            continue
                        if code not in self.weekly_close.columns or w_date not in self.weekly_close.index:
                            continue
                        px = self.weekly_close.loc[w_date, code]
                        if pd.isna(px):
                            continue
                        loss = px / cost_basis[code] - 1
                        if loss < stop_loss:
                            shares = holdings[code]
                            _, proceeds, fee = self.cost.sell_proceeds(px, shares)
                            cash += proceeds
                            self.trade_log.append({
                                'date': w_date, 'code': code,
                                'name': self.etf_dict.get(code, ''),
                                'action': 'SELL', 'price': round(px, 3),
                                'shares': shares, 'fee': round(fee, 2),
                                'value': round(proceeds, 2),
                                'note': '止损',
                            })
                            del holdings[code]
                            del cost_basis[code]
                            if verbose:
                                name = self.etf_dict.get(code, '')
                                print(f"   🛑 {w_date.strftime('%Y-%m-%d')} 止损 {code} {name} 亏损{loss:.1%}")

                pv = cash
                for code, shares in holdings.items():
                    if code in self.weekly_close.columns and w_date in self.weekly_close.index:
                        px = self.weekly_close.loc[w_date, code]
                        if not pd.isna(px):
                            pv += shares * px
                equity_values.iloc[w_idx] = pv
                cash_values.iloc[w_idx] = cash

        # ---- 平滑填充（首次调仓前的日期保持 init_cash）----
        equity_values = equity_values.fillna(method='ffill')
        cash_values = cash_values.fillna(method='ffill')

        self.equity_curve = equity_values
        self.cash_history = cash_values

        # ---- 计算绩效 ----
        self._calc_performance()

        if verbose:
            self._print_results()

        return self.results

    # ----------------------------------------------------------
    # 绩效计算
    # ----------------------------------------------------------
    def _calc_performance(self):
        """计算绩效指标"""
        eq = self.equity_curve.dropna()
        if len(eq) < 2:
            self.results = {'error': '数据不足，无法计算绩效'}
            return

        # 总收益率
        total_return = eq.iloc[-1] / self.init_cash - 1

        # 年化收益率
        total_days = (eq.index[-1] - eq.index[0]).days
        years = total_days / 365.25
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        # 最大回撤
        rolling_max = eq.expanding().max()
        drawdown = (eq - rolling_max) / rolling_max
        self.drawdown_series = drawdown * 100
        max_drawdown = drawdown.min()

        # 夏普比率（用周收益率）
        weekly_ret = eq.pct_change().dropna()
        sharpe = np.nan
        if weekly_ret.std() > 0:
            sharpe = (weekly_ret.mean() / weekly_ret.std()) * (52 ** 0.5)

        # 卡玛比率
        calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

        # 交易统计
        buy_trades = [t for t in self.trade_log if t['action'] == 'BUY']
        sell_trades = [t for t in self.trade_log if t['action'] == 'SELL']
        total_fees = sum(t['fee'] for t in self.trade_log)

        # 胜率
        closed_trades = self._calc_win_rate()
        win_rate = closed_trades.get('win_rate', 0)
        profit_loss_ratio = closed_trades.get('profit_loss_ratio', 0)

        # 年化波动率
        annual_vol = weekly_ret.std() * (52 ** 0.5)

        self.results = {
            '总收益率': f"{total_return:.2%}",
            '年化收益率': f"{annual_return:.2%}",
            '年化波动率': f"{annual_vol:.2%}",
            '夏普比率': f"{sharpe:.2f}",
            '卡玛比率': f"{calmar:.2f}",
            '最大回撤': f"{max_drawdown:.2%}",
            '交易总次数': len(self.trade_log),
            '买入次数': len(buy_trades),
            '卖出次数': len(sell_trades),
            '总手续费': f"{total_fees:.2f}",
            '总滑点成本': f"已计入{self.cost.slippage:.1%}单边滑点",
            '最终资产': f"{eq.iloc[-1]:.2f}",
            '总盈利': f"{eq.iloc[-1] - self.init_cash:.2f}",
        }

        if win_rate > 0:
            self.results['胜率'] = f"{win_rate:.2%}"
            self.results['盈亏比'] = f"{profit_loss_ratio:.2f}"

    def _calc_win_rate(self):
        """计算胜率和盈亏比"""
        buys = [t for t in self.trade_log if t['action'] == 'BUY']
        sells = [t for t in self.trade_log if t['action'] == 'SELL']

        wins = 0
        losses = 0
        total_profit = 0
        total_loss = 0

        for sell in sells:
            # 找到这笔卖出对应的买入（同一code、日期最接近的未配对买入）
            matched_buy = None
            for buy in reversed(buys):
                if buy['code'] == sell['code'] and buy['date'] <= sell['date']:
                    matched_buy = buy
                    break

            if matched_buy:
                pnl = (sell['price'] - matched_buy['price']) * matched_buy['shares'] \
                      - matched_buy['fee'] - sell['fee']
                if pnl > 0:
                    wins += 1
                    total_profit += pnl
                else:
                    losses += 1
                    total_loss += pnl

        total = wins + losses
        win_rate = wins / total if total > 0 else 0
        avg_win = total_profit / wins if wins > 0 else 0
        avg_loss = total_loss / losses if losses > 0 else 0
        profit_loss_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else 0

        return {
            'win_rate': win_rate,
            'profit_loss_ratio': profit_loss_ratio,
        }

    # ----------------------------------------------------------
    # 可视化
    # ----------------------------------------------------------
    def plot_results(self, figsize=(14, 10)):
        """
        绘制回测结果（净值曲线 + 回撤 + 持仓结构）
        """
        if self.equity_curve is None or len(self.equity_curve) < 2:
            print("请先运行 run_backtest()")
            return

        fig = plt.figure(figsize=figsize)

        # ---- 净值曲线 ----
        ax1 = fig.add_subplot(3, 1, 1)
        eq = self.equity_curve.dropna()

        ax1.plot(eq.index, eq, color='#1a73e8', linewidth=2, label='策略净值')
        ax1.axhline(y=self.init_cash, color='gray', linestyle='--',
                    alpha=0.6, linewidth=1, label=f'初始资金 ({self.init_cash:,.0f})')

        # 标注调仓点
        for date in self.holdings_history.keys():
            if date in eq.index:
                ax1.axvline(x=date, color='orange', alpha=0.15, linewidth=0.5)

        ax1.set_title('ETF轮动策略 — 资金净值曲线', fontsize=14, fontweight='bold')
        ax1.set_ylabel('净值 (元)', fontsize=11)
        ax1.legend(loc='upper left', fontsize=10)
        ax1.grid(True, alpha=0.3)

        # 标注收益率
        total_ret = (eq.iloc[-1] - self.init_cash) / self.init_cash
        ax1.annotate(f'总收益率: {total_ret:.2%}',
                     xy=(0.02, 0.95), xycoords='axes fraction',
                     fontsize=12, fontweight='bold',
                     bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        # ---- 回撤曲线 ----
        ax2 = fig.add_subplot(3, 1, 2)
        dd = self.drawdown_series.dropna()

        ax2.fill_between(dd.index, 0, dd.values, color='#dc3545', alpha=0.3)
        ax2.plot(dd.index, dd.values, color='#dc3545', linewidth=1, alpha=0.8)
        ax2.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)

        max_dd_val = dd.min()
        max_dd_idx = dd.idxmin()
        ax2.annotate(f'最大回撤: {max_dd_val:.1f}%',
                     xy=(max_dd_idx, max_dd_val),
                     xytext=(max_dd_idx, max_dd_val + 5),
                     arrowprops=dict(arrowstyle='->', color='red'),
                     fontsize=10, color='red', fontweight='bold')

        ax2.set_title('回撤曲线', fontsize=13, fontweight='bold')
        ax2.set_ylabel('回撤 (%)', fontsize=11)
        ax2.grid(True, alpha=0.3)

        # ---- 持仓分布 ----
        ax3 = fig.add_subplot(3, 1, 3)
        self._plot_holdings_allocation(ax3)

        plt.tight_layout(pad=3)
        plt.show()

    def _plot_holdings_allocation(self, ax):
        """绘制持仓分布热力图"""
        if not self.holdings_history:
            ax.text(0.5, 0.5, '无持仓数据', ha='center', va='center', fontsize=12)
            return

        # 构建持仓矩阵
        all_codes = sorted(set(
            code for h in self.holdings_history.values() for code in h.keys()
        ))
        dates = sorted(self.holdings_history.keys())

        # 使用市值占比
        alloc_matrix = pd.DataFrame(0.0, index=dates, columns=all_codes)
        for date in dates:
            holdings = self.holdings_history[date]
            total_value = 0
            for code, shares in holdings.items():
                if code in self.weekly_close.columns and date in self.weekly_close.index:
                    px = self.weekly_close.loc[date, code]
                    if not pd.isna(px):
                        total_value += shares * px
            if total_value > 0:
                for code, shares in holdings.items():
                    if code in self.weekly_close.columns and date in self.weekly_close.index:
                        px = self.weekly_close.loc[date, code]
                        if not pd.isna(px):
                            alloc_matrix.loc[date, code] = (shares * px) / total_value

        # 绘图
        alloc_matrix.plot(kind='bar', stacked=True, ax=ax, width=0.8,
                          colormap='tab20', legend=True)

        ax.set_title('持仓结构（调仓日）', fontsize=13, fontweight='bold')
        ax.set_ylabel('仓位占比', fontsize=11)
        ax.set_xlabel('')
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1), fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')

        # 仅显示部分x轴标签
        n_labels = len(dates)
        step = max(1, n_labels // 8)
        for i, label in enumerate(ax.get_xticklabels()):
            if i % step != 0:
                label.set_visible(False)
            else:
                label.set_rotation(45)
                label.set_fontsize(8)

    def print_trade_log(self, n=20):
        """打印交易记录"""
        if not self.trade_log:
            print("无交易记录")
            return

        log_df = pd.DataFrame(self.trade_log)
        log_df = log_df.sort_values(['date', 'action'], ascending=[True, False])
        print(f"\n📋 最近 {min(n, len(log_df))} 条交易记录:")
        print(log_df.tail(n).to_string(index=False))

    def correlation_matrix(self, method='ewma', ewma_span=60):
        """展示ETF池的相关性矩阵

        Parameters
        ----------
        method : str
            相关性估计方法: 'ewma', 'ledoit_wolf', 'pearson'
        ewma_span : int
            EWMA衰减参数
        """
        if self.weekly_returns is None:
            print("请先调用 fetch_all_data()")
            return

        returns = self.weekly_returns.dropna()
        if method == 'ewma':
            ew_cov = returns.ewm(span=ewma_span).cov()
            last_date = ew_cov.index.get_level_values(0)[-1]
            cov_matrix = ew_cov.loc[last_date]
            diag_std = np.sqrt(np.diag(cov_matrix))
            corr = cov_matrix / np.outer(diag_std, diag_std)
            corr = corr.clip(-1, 1)
            title_suffix = f'（EWMA, span={ewma_span}）'
        elif method == 'ledoit_wolf':
            try:
                from sklearn.covariance import LedoitWolf
                lw = LedoitWolf().fit(returns.values)
                cov = lw.covariance_
                diag_std = np.sqrt(np.diag(cov))
                corr = pd.DataFrame(cov / np.outer(diag_std, diag_std),
                                    index=returns.columns, columns=returns.columns).clip(-1, 1)
            except ImportError:
                print("⚠ sklearn 未安装，回退到 Pearson 相关系数")
                corr = returns.corr()
            title_suffix = '（Ledoit-Wolf 收缩）'
        else:
            corr = returns.corr()
            title_suffix = '（Pearson）'
        names = [f"{c}\n({self.etf_dict.get(c,'')})" for c in corr.columns]

        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.imshow(corr.values, cmap='RdYlBu_r', vmin=-1, vmax=1, aspect='auto')

        ax.set_xticks(range(len(names)))
        ax.set_yticks(range(len(names)))
        ax.set_xticklabels(names, fontsize=7, rotation=45, ha='right')
        ax.set_yticklabels(names, fontsize=7)

        # 标注数值
        for i in range(len(corr)):
            for j in range(len(corr)):
                text = ax.text(j, i, f'{corr.values[i, j]:.2f}',
                               ha='center', va='center', fontsize=6,
                               color='black' if abs(corr.values[i, j]) < 0.6 else 'white')

        plt.colorbar(im, ax=ax, shrink=0.8)
        ax.set_title(f'ETF池相关性矩阵（周收益率）{title_suffix}', fontsize=13, fontweight='bold')
        plt.tight_layout()
        plt.show()

        # 打印低相关对
        print("\n🔗 相关性最低的5组ETF对:")
        pairs = []
        for i in range(len(corr.columns)):
            for j in range(i + 1, len(corr.columns)):
                pairs.append((corr.columns[i], corr.columns[j],
                              corr.values[i, j]))
        pairs.sort(key=lambda x: abs(x[2]))
        for c1, c2, r in pairs[:5]:
            n1 = self.etf_dict.get(c1, c1)
            n2 = self.etf_dict.get(c2, c2)
            print(f"   {c1}({n1})  vs  {c2}({n2}) :  {r:.3f}")

        return corr

    def _print_results(self):
        """打印回测结果"""
        print("\n" + "=" * 55)
        print("   ETF轮动策略 — 回测结果")
        print("  《打开量化的黑箱》框架实现")
        print("=" * 55)
        for k, v in self.results.items():
            print(f"  {k:12s}: {v}")
        print("=" * 55)

        # 打印框架配置
        print("\n📐 策略参数:")
        print(f"  阿尔法模型: 动量周期={self.alpha.periods}, "
              f"权重={[f'{w:.1f}' for w in self.alpha.weights]}, "
              f"时序衰减率={self.alpha.decay_rate}")
        print(f"  风险模型:   选ETF数={self.risk.select_n}, "
              f"持仓={self.risk.holding_weeks}周, "
              f"相关性窗口={self.risk.corr_window}周, "
              f"相关性方法={self.risk.corr_method}")
        print(f"  成本模型:   Min费={self.cost.min_fee}元/笔, "
              f"费率={self.cost.fee_rate:.2%}, "
              f"滑点={self.cost.slippage:.1%}")
        print(f"  组合构建:   等权分配 (增量调仓)")
        print(f"  阿尔法因子: 多周期动量")
        print(f"  ETF池:      {len(self.etf_codes)} 只")


# ============================================================
# 快速使用入口
# ============================================================
def run_default_strategy(token, start_date='20200101', end_date='20260415',
                         etf_pool=None, init_cash=100000):
    """
    使用默认参数运行策略

    Parameters
    ----------
    token : str
        tushare token
    start_date, end_date : str
        回测区间
    etf_pool : dict
        自定义ETF池，默认使用系统ETF_POOL
    init_cash : float
        初始资金

    Returns
    -------
    ETFRotationStrategy : 已运行回测的策略对象
    """
    if etf_pool is None:
        # 默认使用全球低相关ETF池
        etf_pool = {
            '510300.SH': '沪深300ETF',
            '510500.SH': '中证500ETF',
            '159915.SZ': '创业板ETF',
            '510880.SH': '红利ETF',
            '513100.SH': '纳指ETF(QDII)',
            '513500.SH': '标普500ETF',
            '513310.SH': '中韩半导体ETF',
            '513080.SH': '法国CAC40ETF',
            '513520.SH': '日经ETF',
            '159509.SZ': '纳指科技ETF景顺',
            '513180.SH': '恒生科技ETF',
            '518880.SH': '黄金ETF',
            '159985.SZ': '豆粕ETF',
            '159920.SZ': '恒生ETF',
        }

    strategy = ETFRotationStrategy(
        etf_pool, start_date, end_date, token,
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
        cost_params={
            'min_fee': 5.0,
            'fee_rate': 0.0003,
            'slippage': 0.002,
        },
        init_cash=init_cash,
    )

    strategy.fetch_all_data()
    strategy.run_backtest(verbose=True, stop_loss=0)
    strategy.correlation_matrix(method=strategy.risk.corr_method, ewma_span=strategy.risk.ewma_span)
    strategy.plot_results()
    strategy.print_trade_log(n=30)

    return strategy


# ============================================================
# 集成策略快速入口（推荐）
# ============================================================
def run_ensemble_strategy(token, start_date='20200101', end_date='20260415',
                          etf_pool=None, init_cash=100000):
    """
    使用集成策略运行回测（3 组阿尔法模型投票打分）

    参数集来源：
      模型 1 - 默认参数（全区间稳定基准）
      模型 2 - 贝叶斯 Fold 2 最优（适应近 2 年市场）
      模型 3 - 贝叶斯 Fold 1 最优（短周期信号补充）

    Parameters
    ----------
    token : str
        tushare token
    start_date, end_date : str
        回测区间 (YYYYMMDD)
    etf_pool : dict
        自定义ETF池，默认使用系统ETF_POOL
    init_cash : float
        初始资金

    Returns
    -------
    EnsembleStrategy : 已运行回测的策略对象
    """
    if etf_pool is None:
        etf_pool = ETF_POOL

    strategy = EnsembleStrategy(
        etf_pool, start_date, end_date, token,
        param_sets=ENSEMBLE_PARAM_SETS,
        cost_params={
            'min_fee': 5.0,
            'fee_rate': 0.0003,
            'slippage': 0.002,
        },
        init_cash=init_cash,
        stop_loss=0,
    )

    strategy.fetch_all_data()
    strategy.run_backtest(verbose=True)
    strategy.print_ensemble_config()
    strategy.plot_results()
    strategy.print_trade_log(n=30)

    return strategy


# ============================================================
# Walk-Forward 滚动优化
# ============================================================
class WalkForwardOptimizer:
    """
    Walk-Forward 滚动优化

    对动量周期、持仓数量等关键参数做滚动优化，
    使用扩展窗口（expanding window）进行网格搜索和 OOS 验证。

    流程：
        1. 获取全量数据（仅一次API调用）
        2. 将数据按时间顺序划分为 N 个窗口
        3. 每轮在训练窗口上网格搜索最优参数
        4. 在随后的测试窗口上验证
        5. 汇总所有 OOS 片段得到组合绩效
    """

    def __init__(self, etf_dict, start_date, end_date, token,
                 n_splits=4, init_cash=100000):
        self.etf_dict = etf_dict
        self.etf_codes = list(etf_dict.keys())
        self.start_date = start_date
        self.end_date = end_date
        self.token = token
        self.n_splits = n_splits
        self.init_cash = init_cash
        self.weekly_close = None
        self.weekly_returns = None
        self.results = []

    def _build_param_grid(self):
        """定义网格搜索空间"""
        return [
            # (periods, weights, decay_rate, select_n, corr_method)
            ([6, 12, 18], [0.5, 0.3, 0.2], 0.15, 3, 'ewma'),
            ([6, 12, 18], [0.5, 0.3, 0.2], 0.15, 4, 'ewma'),
            ([6, 12, 18], [0.5, 0.3, 0.2], 0.15, 5, 'ewma'),
            ([6, 12, 18], [0.5, 0.3, 0.2], 0.15, 6, 'ewma'),
            ([6, 12, 18], [0.5, 0.3, 0.2], 0.15, 5, 'ledoit_wolf'),
            ([4, 10, 16], [0.4, 0.35, 0.25], 0.15, 5, 'ewma'),
            ([8, 14, 20], [0.5, 0.3, 0.2], 0.1,  5, 'ewma'),
            ([6, 12, 18], [0.4, 0.35, 0.25], 0.2, 5, 'ewma'),
        ]

    def fetch_data(self):
        """获取全量数据"""
        strategy = ETFRotationStrategy(
            self.etf_dict, self.start_date, self.end_date, self.token
        )
        strategy.fetch_all_data()
        self.weekly_close = strategy.weekly_close
        self.weekly_returns = strategy.weekly_returns
        print(f"\n✅ Walk-Forward 数据就绪: {self.weekly_close.shape}")
        return self

    def _run_single_backtest(self, data_close, data_returns, params, verbose=False):
        """用指定参数和数据运行一次回测，返回绩效指标"""
        periods, weights, decay_rate, select_n, corr_method = params

        strategy = ETFRotationStrategy(
            self.etf_dict, self.start_date, self.end_date, self.token,
            alpha_params={
                'periods': periods,
                'weights': weights,
                'decay_rate': decay_rate,
                'vol_adjust': True,
                'rank_normalize': True,
            },
            risk_params={
                'select_n': select_n,
                'corr_window': 20,
                'holding_weeks': 3,
                'corr_method': corr_method,
                'ewma_span': 60,
            }
        )
        # 用预加载数据跳过 API 调用
        strategy.load_data(data_close, data_returns)
        strategy.run_backtest(verbose=verbose, stop_loss=0)

        equity = strategy.equity_curve.dropna()
        weekly_ret = equity.pct_change().dropna()

        return {
            'params': params,
            'total_return': (equity.iloc[-1] / strategy.init_cash - 1),
            'annual_return': (1 + equity.iloc[-1] / strategy.init_cash - 1) **
                             (52 / len(weekly_ret)) - 1 if len(weekly_ret) > 0 else 0,
            'sharpe': float(strategy.results.get('夏普比率', '0')),
            'max_dd': float(strategy.results.get('最大回撤', '0%').strip('%')) / 100,
            'sharpe_weekly': (weekly_ret.mean() / weekly_ret.std() * (52 ** 0.5))
                             if weekly_ret.std() > 0 else 0,
        }

    def _split_windows(self):
        """划分时间窗口（按周数等分）"""
        total = len(self.weekly_close)
        fold_size = total // self.n_splits
        indices = [fold_size * (i + 1) for i in range(self.n_splits)]
        indices[-1] = total
        return indices

    def run(self, verbose=True):
        """
        执行 Walk-Forward 滚动优化

        Returns
        -------
        dict : OOS 汇总结果
        """
        if self.weekly_close is None:
            self.fetch_data()

        split_idx = self._split_windows()
        param_grid = self._build_param_grid()

        oos_equities = []
        oos_fold_results = []
        best_params_per_fold = []

        print("\n" + "=" * 60)
        print("  Walk-Forward 滚动优化")
        print("=" * 60)

        for fold in range(self.n_splits - 1):
            train_end = split_idx[fold]
            test_end = split_idx[fold + 1]

            train_close = self.weekly_close.iloc[:train_end]
            train_returns = self.weekly_returns.iloc[:train_end]
            test_close = self.weekly_close.iloc[train_end:test_end]
            test_returns = self.weekly_returns.iloc[train_end:test_end]

            train_start_str = self.weekly_close.index[0].strftime('%Y-%m-%d')
            train_end_str = train_close.index[-1].strftime('%Y-%m-%d')
            test_start_str = test_close.index[0].strftime('%Y-%m-%d')
            test_end_str = test_close.index[-1].strftime('%Y-%m-%d')

            print(f"\n{'─' * 55}")
            print(f" Fold {fold + 1}: 训练 {train_start_str}~{train_end_str} "
                  f"({len(train_close)}周)")
            print(f"         测试 {test_start_str}~{test_end_str} "
                  f"({len(test_close)}周)")
            print(f"{'─' * 55}")

            # 网格搜索
            best_score = -float('inf')
            best_params = None

            for params in param_grid:
                result = self._run_single_backtest(train_close, train_returns, params)
                score = result['sharpe_weekly']

                periods, weights, decay_rate, select_n, corr_method = params
                label = (f"周期={periods} w={weights} "
                         f"衰减={decay_rate} n={select_n} corr={corr_method}")

                if verbose:
                    print(f"   🔍 {label:55s} SR={score:.2f}")

                if score > best_score:
                    best_score = score
                    best_params = params

            print(f"   ✅ 最优: 周期={best_params[0]} n={best_params[3]} "
                  f"corr={best_params[4]} 训练SR={best_score:.2f}")

            # OOS 验证
            oos_result = self._run_single_backtest(
                test_close, test_returns, best_params, verbose=False
            )
            oos_fold_results.append(oos_result)
            best_params_per_fold.append(best_params)

            # 构建 OOS 净值
            sim_strategy = ETFRotationStrategy(
                self.etf_dict, self.start_date, self.end_date, self.token,
                alpha_params={
                    'periods': best_params[0],
                    'weights': best_params[1],
                    'decay_rate': best_params[2],
                    'vol_adjust': True,
                    'rank_normalize': True,
                },
                risk_params={
                    'select_n': best_params[3],
                    'corr_window': 20,
                    'holding_weeks': 3,
                    'corr_method': best_params[4],
                    'ewma_span': 60,
                }
            )
            sim_strategy.load_data(self.weekly_close.iloc[:test_end],
                                   self.weekly_returns.iloc[:test_end])
            sim_strategy.run_backtest(verbose=False, stop_loss=0)

            fold_equity = sim_strategy.equity_curve.dropna()
            if len(oos_equities) > 0:
                last_idx = oos_equities[-1].index[-1]
                new_part = fold_equity[fold_equity.index > last_idx]
            else:
                new_part = fold_equity

            oos_equities.append(new_part)

            print(f"       OOS: 年化={oos_result['annual_return']:.2%} "
                  f"SR={oos_result['sharpe_weekly']:.2f} "
                  f"DD={oos_result['max_dd']:.2%}")

        # 汇总 OOS
        combined_equity = pd.concat(oos_equities)
        combined_equity = combined_equity[~combined_equity.index.duplicated(keep='first')]
        combined_equity = combined_equity.sort_index()

        equity = pd.Series(index=combined_equity.index, dtype=float)
        equity.iloc[0] = self.init_cash
        cum_ret = 1.0
        for i in range(1, len(equity)):
            prev_val = combined_equity.iloc[i - 1]
            curr_val = combined_equity.iloc[i]
            if prev_val > 0:
                cum_ret *= curr_val / prev_val
            equity.iloc[i] = self.init_cash * cum_ret

        self.final_equity = equity
        self.final_results = self._calc_oos_performance(equity, oos_fold_results)
        self._print_oos_summary(oos_fold_results, best_params_per_fold)

        return self.final_results

    def _calc_oos_performance(self, equity, fold_results):
        """计算 OOS 组合绩效"""
        total_return = equity.iloc[-1] / self.init_cash - 1
        total_days = (equity.index[-1] - equity.index[0]).days
        years = total_days / 365.25 if total_days > 0 else 1
        annual_return = (1 + total_return) ** (1 / years) - 1

        rolling_max = equity.expanding().max()
        drawdown = (equity - rolling_max) / rolling_max
        max_dd = drawdown.min()

        weekly_ret = equity.pct_change().dropna()
        sharpe = (weekly_ret.mean() / weekly_ret.std() * (52 ** 0.5)) if weekly_ret.std() > 0 else 0
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0
        avg_sharpe = np.mean([r['sharpe_weekly'] for r in fold_results])

        return {
            '总收益率': f"{total_return:.2%}",
            '年化收益率': f"{annual_return:.2%}",
            '夏普比率(OOS)': f"{sharpe:.2f}",
            '卡玛比率': f"{calmar:.2f}",
            '最大回撤': f"{max_dd:.2%}",
            '各Fold平均SR': f"{avg_sharpe:.2f}",
        }

    def _print_oos_summary(self, fold_results, best_params):
        """打印 Walk-Forward 汇总"""
        print("\n" + "=" * 60)
        print("  Walk-Forward 滚动优化 — OOS 汇总")
        print("=" * 60)

        for i, (res, params) in enumerate(zip(fold_results, best_params)):
            print(f"  Fold {i + 1}: 周期={params[0]} n={params[3]} "
                  f"corr={params[4]}")
            print(f"          OOS: 年化={res['annual_return']:.2%} "
                  f"夏普={res['sharpe_weekly']:.2f} "
                  f"回撤={res['max_dd']:.2%}")

        print("-" * 60)
        for k, v in self.final_results.items():
            print(f"  {k:16s}: {v}")
        print("=" * 60)

    def plot_walk_forward(self):
        """绘制 Walk-Forward OOS 净值曲线"""
        if not hasattr(self, 'final_equity') or self.final_equity is None:
            print("请先运行 run()")
            return

        fig, ax = plt.subplots(figsize=(14, 6))
        eq = self.final_equity
        ax.plot(eq.index, eq, color='#2e7d32', linewidth=2, label='Walk-Forward OOS')
        ax.axhline(y=self.init_cash, color='gray', linestyle='--', alpha=0.6)

        split_idx = self._split_windows()
        for idx in split_idx[:-1]:
            split_date = self.weekly_close.index[idx]
            if split_date in eq.index:
                ax.axvline(x=split_date, color='orange', alpha=0.3, linestyle=':', linewidth=1)

        total_ret = (eq.iloc[-1] / self.init_cash - 1)
        ax.set_title(f'Walk-Forward OOS 净值曲线（总收益 {total_ret:.2%}）',
                     fontsize=14, fontweight='bold')
        ax.set_ylabel('净值（元）', fontsize=11)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()


# ============================================================
# Walk-Forward 贝叶斯滚动优化
# ============================================================
class BayesianWalkForwardOptimizer(WalkForwardOptimizer):
    """
    Walk-Forward 贝叶斯滚动优化

    使用高斯过程（Gaussian Process）回归建模参数→绩效的映射关系，
    通过 Expected Improvement (EI) 采集函数选择最有潜力的参数组合。

    相比网格搜索的优势：
      - 更少的评估次数即可找到优质参数（样本效率高）
      - 自动平衡探索（exploration）与利用（exploitation）
      - 支持连续参数空间，不再局限于几个离散选项

    优化参数空间：
      阿尔法模型 : 动量周期(短/中/长)、权重分配、时序衰减率
      风险模型   : ETF选择数量、EWMA衰减因子、持仓周数、相关性方法
    """

    def __init__(self, etf_dict, start_date, end_date, token,
                 n_splits=4, init_cash=100000,
                 n_initial=15, n_iterations=30,
                 acq_func='EI', random_state=42):
        """
        Parameters
        ----------
        etf_dict : dict
            {ts_code: name} 格式的ETF池
        start_date, end_date : str
            回测区间 (YYYYMMDD)
        token : str
            tushare token
        n_splits : int
            Walk-Forward 折叠数
        init_cash : float
            初始资金
        n_initial : int
            初始 Latin Hypercube 采样点数
        n_iterations : int
            贝叶斯优化迭代次数
        acq_func : str
            采集函数 ('EI' 或 'LCB')
        random_state : int
            随机种子
        """
        super().__init__(etf_dict, start_date, end_date, token, n_splits, init_cash)
        self.n_initial = n_initial
        self.n_iterations = n_iterations
        self.acq_func = acq_func
        self.random_state = random_state

    # ----------------------------------------------------------
    # 搜索空间定义
    # ----------------------------------------------------------
    def _build_bayesian_space(self):
        """
        定义贝叶斯优化的搜索空间

        Returns
        -------
        list of dict : 每个参数的定义 {name, low, high, type}
        """
        return [
            # ── 阿尔法模型参数 ──
            {'name': 'short_period',  'low': 4,  'high': 10, 'type': 'int'},    # 短期动量周期
            {'name': 'mid_period',    'low': 8,  'high': 20, 'type': 'int'},    # 中期动量周期
            {'name': 'long_period',   'low': 14, 'high': 26, 'type': 'int'},    # 长期动量周期
            {'name': 'short_w',       'low': 0.2, 'high': 0.6, 'type': 'float'},  # 短期权重
            {'name': 'mid_w',         'low': 0.15,'high': 0.4, 'type': 'float'},  # 中期权重
            {'name': 'decay_rate',    'low': 0.05,'high': 0.5, 'type': 'float'},  # 时序衰减率
            # ── 风险模型参数 ──
            {'name': 'select_n',      'low': 3,  'high': 7,  'type': 'int'},    # ETF选择数量
            {'name': 'ewma_span',     'low': 20, 'high': 120,'type': 'int'},    # EWMA衰减因子
            {'name': 'holding_weeks', 'low': 2,  'high': 5,  'type': 'int'},    # 持仓周数
            {'name': 'corr_method',   'low': 0,  'high': 1,  'type': 'cat',     # 相关性方法
             'values': ['ewma', 'ledoit_wolf']},
        ]

    def _params_to_tuple(self, x):
        """
        将优化向量转换回参数字典

        Parameters
        ----------
        x : list
            优化器输出的参数向量 [short_p, mid_p, long_p, short_w, mid_w,
                                decay_r, select_n, ewma_s, hold_w, corr_idx]

        Returns
        -------
        tuple : (periods, weights, decay_rate, select_n, corr_method,
                 ewma_span, holding_weeks)
        """
        short_p, mid_p, long_p = int(x[0]), int(x[1]), int(x[2])
        short_w, mid_w = x[3], x[4]
        decay_r = x[5]
        select_n, ewma_s, hold_w = int(x[6]), int(x[7]), int(x[8])
        corr_idx = int(x[9])

        # 排序动量周期（短 < 中 < 长）
        periods = sorted([short_p, mid_p, long_p])

        # 归一化权重（确保和为1，长期权重不低于5%）
        long_w = 1.0 - short_w - mid_w
        long_w = max(0.05, long_w)
        weights = [short_w, mid_w, long_w]
        total = sum(weights)
        weights = [w / total for w in weights]

        # 相关性方法编码
        corr_method = 'ewma' if corr_idx == 0 else 'ledoit_wolf'

        return (
            periods, weights, decay_r,
            select_n, corr_method,
            ewma_s, hold_w
        )

    # ----------------------------------------------------------
    # 单次回测（支持扩展参数）
    # ----------------------------------------------------------
    def _run_single_backtest(self, data_close, data_returns, params, verbose=False):
        """
        用指定参数和数据运行一次回测（支持扩展到 ewma_span + holding_weeks）

        Returns
        -------
        dict : {params, total_return, annual_return, sharpe, max_dd, sharpe_weekly}
        """
        (periods, weights, decay_rate, select_n, corr_method,
         ewma_span, holding_weeks) = params

        strategy = ETFRotationStrategy(
            self.etf_dict, self.start_date, self.end_date, self.token,
            alpha_params={
                'periods': periods,
                'weights': weights,
                'decay_rate': decay_rate,
                'vol_adjust': True,
                'rank_normalize': True,
            },
            risk_params={
                'select_n': select_n,
                'corr_window': 20,
                'holding_weeks': holding_weeks,
                'corr_method': corr_method,
                'ewma_span': ewma_span,
            }
        )
        strategy.load_data(data_close, data_returns)
        strategy.run_backtest(verbose=verbose, stop_loss=0)

        equity = strategy.equity_curve.dropna()
        weekly_ret = equity.pct_change().dropna()

        total_return = equity.iloc[-1] / strategy.init_cash - 1
        sharpe = (weekly_ret.mean() / weekly_ret.std() * (52 ** 0.5)) if weekly_ret.std() > 0 else 0
        annual_return = (1 + total_return) ** (52 / len(weekly_ret)) - 1 if len(weekly_ret) > 0 else 0
        max_dd = float(strategy.results.get('最大回撤', '0%').strip('%')) / 100

        return {
            'params': params,
            'total_return': total_return,
            'annual_return': annual_return,
            'sharpe': sharpe,
            'max_dd': max_dd,
            'sharpe_weekly': sharpe,
        }

    def _objective(self, x, train_close, train_returns):
        """
        贝叶斯优化的目标函数（最小化负夏普比率）

        Parameters
        ----------
        x : list
            参数向量
        train_close, train_returns : pd.DataFrame
            训练数据

        Returns
        -------
        float : 负夏普比率（越小越好）
        """
        params = self._params_to_tuple(x)
        try:
            result = self._run_single_backtest(
                train_close, train_returns, params, verbose=False
            )
            sharpe = result['sharpe']
            if np.isnan(sharpe) or np.isinf(sharpe):
                return 0.0
            return -sharpe  # 最小化负夏普 = 最大化夏普
        except Exception:
            return 0.0

    # ----------------------------------------------------------
    # Expected Improvement 采集函数
    # ----------------------------------------------------------
    def _expected_improvement(self, X, gp, y_best, xi=0.01):
        """
        Expected Improvement 采集函数

        EI(x) = E[max(0, f(x_best) - f(x) - xi)]

        Parameters
        ----------
        X : ndarray (n_samples, n_dims)
            待评估点
        gp : GaussianProcessRegressor
            训练好的GP模型
        y_best : float
            当前最优目标值（最小化视角，越小越好）
        xi : float
            探索-利用平衡参数，越大越偏向探索

        Returns
        -------
        ndarray : EI 值
        """
        mu, sigma = gp.predict(X, return_std=True)
        sigma = np.maximum(sigma, 1e-10)  # 避免除零

        # 改进量 = 当前最优 - 预测均值 - xi（最小化视角）
        improvement = y_best - mu - xi
        Z = improvement / sigma

        ei = improvement * norm.cdf(Z) + sigma * norm.pdf(Z)
        return np.maximum(ei, 0.0)

    # ----------------------------------------------------------
    # Latin Hypercube 初始采样
    # ----------------------------------------------------------
    def _latin_hypercube_sample(self, n_samples, space_def, bounds, rng):
        """
        Latin Hypercube 采样（比随机均匀采样覆盖更均匀）

        Parameters
        ----------
        n_samples : int
            采样点数
        space_def : list of dict
            搜索空间定义
        bounds : list of tuple
            [(low, high), ...]
        rng : RandomState
            随机数生成器

        Returns
        -------
        ndarray : (n_samples, n_dims) 采样矩阵
        """
        n_dims = len(space_def)
        X = np.zeros((n_samples, n_dims))

        for d in range(n_dims):
            low, high = bounds[d]
            # 将 [low, high] 分为 n_samples 个区间，每个区间内随机取一点
            segments = np.linspace(low, high, n_samples + 1)
            offsets = rng.rand(n_samples) * (segments[1] - segments[0])
            col = segments[:-1] + offsets

            # 打乱顺序确保维度间不相关
            rng.shuffle(col)

            if space_def[d]['type'] == 'int':
                col = np.round(col).clip(low, high).astype(int)
            elif space_def[d]['type'] == 'cat':
                col = np.clip(np.round(col), low, high).astype(int)

            X[:, d] = col

        return X

    # ----------------------------------------------------------
    # 主运行入口
    # ----------------------------------------------------------
    def run(self, verbose=True):
        """
        执行 Walk-Forward 贝叶斯滚动优化

        每轮流程:
          1. Latin Hypercube 初始采样 (n_initial 组)
          2. 用初始数据训练 Gaussian Process
          3. 通过优化 EI 采集函数选择下一组参数
          4. 回测评估新参数，更新 GP
          5. 重复步骤 3-4 共 n_iterations 次
          6. 最优参数在 OOS 窗口上验证

        Returns
        -------
        dict : OOS 汇总绩效
        """
        if self.weekly_close is None:
            self.fetch_data()

        split_idx = self._split_windows()
        space_def = self._build_bayesian_space()
        n_dims = len(space_def)
        bounds = [(s['low'], s['high']) for s in space_def]

        oos_equities = []
        oos_fold_results = []
        best_params_per_fold = []

        print("\n" + "=" * 68)
        print("  Walk-Forward 贝叶斯滚动优化")
        print("  Gaussian Process + Expected Improvement")
        print("  Alpha: 动量周期/权重/衰减率 | Risk: 选ETF数/EWMA/持仓周/相关性")
        print("=" * 68)

        for fold in range(self.n_splits - 1):
            train_end = split_idx[fold]
            test_end = split_idx[fold + 1]

            train_close = self.weekly_close.iloc[:train_end]
            train_returns = self.weekly_returns.iloc[:train_end]
            test_close = self.weekly_close.iloc[train_end:test_end]
            test_returns = self.weekly_returns.iloc[train_end:test_end]

            train_start_str = self.weekly_close.index[0].strftime('%Y-%m-%d')
            train_end_str = train_close.index[-1].strftime('%Y-%m-%d')
            test_start_str = test_close.index[0].strftime('%Y-%m-%d')
            test_end_str = test_close.index[-1].strftime('%Y-%m-%d')

            print(f"\n{'─' * 68}")
            print(f"  Fold {fold + 1}: 训练 {train_start_str}~{train_end_str} "
                  f"({len(train_close)}周)")
            print(f"             测试 {test_start_str}~{test_end_str} "
                  f"({len(test_close)}周)")
            print(f"{'─' * 68}")

            # ---- 阶段1: Latin Hypercube 初始采样 ----
            rng = np.random.RandomState(self.random_state + fold)
            X_init = self._latin_hypercube_sample(
                self.n_initial, space_def, bounds, rng
            )

            y_init = np.zeros(self.n_initial)
            best_x = None
            best_y = float('inf')

            for i in range(self.n_initial):
                x = X_init[i].tolist()
                y = self._objective(x, train_close, train_returns)
                y_init[i] = y
                if y < best_y:
                    best_y = y
                    best_x = x.copy()

            if verbose:
                p0 = self._params_to_tuple(best_x)
                print(f"   初始采样 {self.n_initial} 组完成, 最佳训练SR={-best_y:.3f}")
                print(f"   初始最佳: 周期={p0[0]} "
                      f"n={p0[3]} corr={p0[4]} hold={p0[6]}周")

            # ---- 阶段2: GP 贝叶斯迭代优化 ----
            X_train = X_init.copy()
            y_train = y_init.copy()

            # GP 内核: ConstantKernel * Matern(ν=5/2) + WhiteKernel
            kernel = (
                ConstantKernel(1.0, constant_value_bounds=(0.1, 10.0))
                * Matern(length_scale=np.ones(n_dims), nu=2.5,
                         length_scale_bounds=(0.01, 10.0))
                + WhiteKernel(noise_level=1e-3, noise_level_bounds=(1e-5, 1.0))
            )

            n_iter = self.n_iterations
            ei_xi = 0.01  # 小幅探索津贴

            for iteration in range(n_iter):
                # 训练GP
                gp = GaussianProcessRegressor(
                    kernel=kernel,
                    n_restarts_optimizer=3,
                    random_state=self.random_state + iteration,
                    normalize_y=True,
                )
                gp.fit(X_train, y_train)

                # 优化EI采集函数找下一个评估点
                y_current_best = y_train.min()

                def _ei_obj(x):
                    return -self._expected_improvement(
                        x.reshape(1, -1), gp, y_current_best, xi=ei_xi
                    )[0]

                result = differential_evolution(
                    _ei_obj, bounds,
                    maxiter=300, popsize=25, tol=1e-6,
                    seed=self.random_state + iteration,
                )
                x_next = result.x.tolist()

                # 评估新点
                y_next = self._objective(x_next, train_close, train_returns)

                # 更新数据集
                X_train = np.vstack([X_train, [x_next]])
                y_train = np.append(y_train, y_next)

                if y_next < best_y:
                    best_y = y_next
                    best_x = x_next.copy()

                if verbose and (iteration + 1) % 5 == 0:
                    print(f"   贝叶斯 [{iteration + 1:3d}/{n_iter}] "
                          f"当前最佳SR={-best_y:.3f}")

            # ---- 本轮最优参数 ----
            best_params = self._params_to_tuple(best_x)
            best_sharpe = -best_y

            print(f"\n   ✅ Fold {fold + 1} 最优:")
            print(f"      阿尔法: 周期={best_params[0]} "
                  f"权重=[{','.join(f'{w:.2f}' for w in best_params[1])}]")
            print(f"      阿尔法: 衰减率={best_params[2]:.3f}")
            print(f"      风险:   n={best_params[3]} corr={best_params[4]} "
                  f"ewma_spaN={best_params[5]} hold={best_params[6]}周")
            print(f"      训练SR={best_sharpe:.3f}")

            # ---- OOS 验证 ----
            oos_result = self._run_single_backtest(
                test_close, test_returns, best_params, verbose=False
            )
            oos_fold_results.append(oos_result)
            best_params_per_fold.append(best_params)

            # 构建 OOS 净值片段
            sim = ETFRotationStrategy(
                self.etf_dict, self.start_date, self.end_date, self.token,
                alpha_params={
                    'periods': best_params[0],
                    'weights': best_params[1],
                    'decay_rate': best_params[2],
                    'vol_adjust': True, 'rank_normalize': True,
                },
                risk_params={
                    'select_n': best_params[3],
                    'corr_window': 20,
                    'holding_weeks': best_params[6],
                    'corr_method': best_params[4],
                    'ewma_span': best_params[5],
                }
            )
            sim.load_data(self.weekly_close.iloc[:test_end],
                          self.weekly_returns.iloc[:test_end])
            sim.run_backtest(verbose=False, stop_loss=0)

            fold_equity = sim.equity_curve.dropna()
            if len(oos_equities) > 0:
                last_idx = oos_equities[-1].index[-1]
                new_part = fold_equity[fold_equity.index > last_idx]
            else:
                new_part = fold_equity
            oos_equities.append(new_part)

            print(f"      OOS: 年化={oos_result['annual_return']:.2%} "
                  f"SR={oos_result['sharpe']:.3f} "
                  f"DD={oos_result['max_dd']:.2%}")

        # ---- 汇总全部 OOS 片段 ----
        combined_equity = pd.concat(oos_equities)
        combined_equity = combined_equity[
            ~combined_equity.index.duplicated(keep='first')
        ].sort_index()

        equity = pd.Series(index=combined_equity.index, dtype=float)
        equity.iloc[0] = self.init_cash
        cum_ret = 1.0
        for i in range(1, len(equity)):
            prev_val = combined_equity.iloc[i - 1]
            curr_val = combined_equity.iloc[i]
            if prev_val > 0:
                cum_ret *= curr_val / prev_val
            equity.iloc[i] = self.init_cash * cum_ret

        self.final_equity = equity
        self.final_results = self._calc_oos_performance(equity, oos_fold_results)
        self._print_bayesian_summary(oos_fold_results, best_params_per_fold)

        return self.final_results

    def _print_bayesian_summary(self, fold_results, best_params):
        """打印贝叶斯 Walk-Forward 汇总"""
        print("\n" + "=" * 68)
        print("  Walk-Forward 贝叶斯优化 — OOS 汇总")
        print("=" * 68)

        for i, (res, params) in enumerate(zip(fold_results, best_params)):
            print(f"  Fold {i + 1}:")
            print(f"    阿尔法: 周期={params[0]} "
                  f"衰减率={params[2]:.3f}")
            print(f"    风险:   n={params[3]} corr={params[4]} "
                  f"span={params[5]} hold={params[6]}周")
            print(f"    OOS:    年化={res['annual_return']:.2%} "
                  f"夏普={res['sharpe']:.3f} "
                  f"回撤={res['max_dd']:.2%}")

        print("-" * 68)
        for k, v in self.final_results.items():
            print(f"  {k:20s}: {v}")
        print("=" * 68)


# ============================================================
# 集成策略 — 多参数集投票打分
# ============================================================
DEFAULT_ALPHA_PARAMS = {
    'periods': [6, 12, 18],
    'weights': [0.5, 0.3, 0.2],
    'vol_adjust': True,
    'rank_normalize': True,
    'decay_rate': 0.15,
}

BAYESIAN_FOLD2_PARAMS = {
    'periods': [10, 14, 19],
    'weights': [0.43, 0.24, 0.33],
    'vol_adjust': True,
    'rank_normalize': True,
    'decay_rate': 0.252,
}

BAYESIAN_FOLD1_PARAMS = {
    'periods': [8, 9, 17],
    'weights': [0.26, 0.26, 0.48],
    'vol_adjust': True,
    'rank_normalize': True,
    'decay_rate': 0.321,
}

ENSEMBLE_PARAM_SETS = [
    DEFAULT_ALPHA_PARAMS,
    BAYESIAN_FOLD2_PARAMS,
    BAYESIAN_FOLD1_PARAMS,
]


class EnsembleAlphaModel:
    """
    集成阿尔法模型

    持有多个 AlphaModel 实例，每次计算所有模型的平均动量得分。
    多模型平均天然平滑单一参数的过拟合，对市场风格切换更稳健。
    """

    def __init__(self, param_sets):
        """
        param_sets : list of dict
            每个元素是 AlphaModel 的参数 dict
        """
        self.models = [AlphaModel(**p) for p in param_sets]
        # 暴露属性（供 run_backtest / _print_results 使用）
        self.periods = max((m.periods for m in self.models), key=max)
        self.weights = self.models[0].weights
        self.decay_rate = self.models[0].decay_rate

    def compute_scores(self, weekly_data):
        """
        计算多模型平均动量得分

        Returns
        -------
        pd.Series : 各ETF的集成得分
        """
        scores = pd.DataFrame({
            i: m.compute_scores(weekly_data)
            for i, m in enumerate(self.models)
        })
        return scores.mean(axis=1)


class EnsembleStrategy(ETFRotationStrategy):
    """
    集成 ETF 轮动策略

    用多组阿尔法参数集"投票"打分，降低单组参数过拟合风险。
    风险模型固定 select_n=5（最佳分散效果）。

    参数集来源：
      - 默认参数（稳定基准）
      - 贝叶斯 Fold 2 最优（2023-2024 年适应性）
      - 贝叶斯 Fold 1 最优（中长期信号补充）
    """

    def __init__(self, etf_dict, start_date, end_date, token,
                 param_sets=None, risk_params=None, cost_params=None,
                 init_cash=100000, stop_loss=0):
        """
        stop_loss : float
            单只 ETF 跟踪止损线（从买点算起，默认 -15%）
        """
        # 默认风险模型锁死 select_n=5
        default_risk = {
            'select_n': 5,
            'corr_window': 20,
            'holding_weeks': 3,
            'corr_method': 'ewma',
            'ewma_span': 60,
        }
        if risk_params is not None:
            default_risk.update(risk_params)
            default_risk['select_n'] = 5  # 强制 5 只分散

        super().__init__(etf_dict, start_date, end_date, token,
                         alpha_params={},
                         risk_params=default_risk,
                         cost_params=cost_params,
                         init_cash=init_cash)

        # 用集成模型替换单一 AlphaModel
        param_sets = param_sets or ENSEMBLE_PARAM_SETS
        self.alpha = EnsembleAlphaModel(param_sets)
        self.ensemble_n = len(param_sets)
        self.stop_loss = stop_loss
        self.param_sets = param_sets

    def run_backtest(self, verbose=True, stop_loss=None):
        """
        执行集成策略回测（带跟踪止损）

        与父类区别：
          - 阿尔法得分来自 EnsembleAlphaModel（多参数集平均）
          - 默认启用跟踪止损
        """
        if stop_loss is None:
            stop_loss = self.stop_loss
        return super().run_backtest(verbose=verbose, stop_loss=stop_loss)

    def print_ensemble_config(self):
        """打印集成配置"""
        print(f"\n📐 集成策略配置:")
        print(f"  模型数: {self.ensemble_n}")
        print(f"  止损线: {self.stop_loss:.0%}")
        for i, params in enumerate(self.param_sets):
            print(f"  模型{i + 1}: 周期={params['periods']} "
                  f"权重={[f'{w:.2f}' for w in params['weights']]} "
                  f"衰减率={params['decay_rate']}")


# ============================================================
# 主程序
# ============================================================
if __name__ == '__main__':
    TOKEN = "d45373f7d85863f2d4193ce5fdd0d58e8e7d42f5db4db422be883cbc171d"
    START = '20200101'
    END = '20260415'

    # 1. 默认策略回测
    print("\n" + "=" * 55)
    print("  【1/3】默认策略回测")
    print("=" * 55)
    strategy = run_default_strategy(TOKEN, start_date=START, end_date=END)
    strategy.print_trade_log(n=20)

    # 2. Walk-Forward 滚动优化（网格搜索）
    print("\n" + "=" * 55)
    print("  【2/3】Walk-Forward 网格搜索")
    print("=" * 55)
    wf = WalkForwardOptimizer(
        strategy.etf_dict, START, END, TOKEN,
        n_splits=4, init_cash=100000
    )
    wf.fetch_data()
    wf.run(verbose=True)
    wf.plot_walk_forward()

    # 3. 集成策略（推荐 — 实盘最稳方案）
    print("\n" + "=" * 55)
    print("  【3/3】集成策略（3组阿尔法模型投票）")
    print("=" * 55)
    ensemble = run_ensemble_strategy(
        TOKEN, start_date=START, end_date=END, init_cash=100000
    )
    ensemble.print_trade_log(n=20)
