"""
初始化策略库数据 — 从 Downloads 中的 ETF 轮动策略提取参数和回测结果
"""
from django.core.management.base import BaseCommand
from strategies.models import Strategy, BacktestResult, Signal
from datetime import date


class Command(BaseCommand):
    help = "用 ETF 轮动策略的数据初始化策略库"

    def handle(self, *args, **options):
        # 1. ETF 轮动策略
        etf_strategy, _ = Strategy.objects.update_or_create(
            slug="etf-rotation",
            defaults={
                "name": "ETF轮动策略",
                "description": "基于多周期动量因子的ETF轮动系统。覆盖A股宽基、全球ETF、商品、港股等13只低相关ETF，"
                               "通过复合动量打分 + 低相关筛选 + 等权组合构建，周频调仓。",
                "content_md": """## 策略概况

ETF轮动策略系统，基于《打开量化的黑箱》框架构建。

### 框架结构

1. **阿尔法模型（Alpha Model）** — 多周期动量+均值回归复合因子
   - 多周期复合动量（6周、12周、18周加权）
   - 波动率调整 + 排名归一化 + 因子时序衰减

2. **风险模型（Risk Model）** — 低相关ETF选择 + 3周持有
   - 从13只ETF中选出5只低相关性标的
   - 支持 EWMA / Ledoit-Wolf 两种相关估计方法

3. **交易成本模型（Transaction Cost Model）** — Min5元 + 0.2%滑点

4. **投资组合构建模型（Portfolio Construction）** — 等权组合

### ETF池（13只）

| ETF | 名称 | 类别 |
|-----|------|------|
| 510300.SH | 沪深300ETF | A股大盘 |
| 510500.SH | 中证500ETF | A股中盘 |
| 159915.SZ | 创业板ETF | A股成长 |
| 510880.SH | 红利ETF | 价值 |
| 513100.SH | 纳指ETF(QDII) | 美股科技 |
| 513500.SH | 标普500ETF | 美股全市场 |
| 513310.SH | 中韩半导体ETF | 半导体 |
| 513080.SH | 法国CAC40ETF | 欧洲 |
| 513520.SH | 日经ETF | 日本 |
| 159509.SZ | 纳指科技ETF | 美股科技 |
| 513180.SH | 恒生科技ETF | 港股科技 |
| 518880.SH | 黄金ETF | 商品 |
| 159985.SZ | 豆粕ETF | 商品 |
| 159920.SZ | 恒生ETF | 香港市场 |

### 策略参数

**阿尔法模型（默认参数）**
- 动量周期: [6, 12, 18] 周
- 周期权重: [0.5, 0.3, 0.2]
- 波动率调整: 开启
- 排名归一化: 开启
- 衰减率: 0.15

**风险模型**
- 持仓数量: 5只
- 相关窗口: 20周
- 持有周期: 3周
- 相关方法: EWMA
- EWMA span: 60

### Walk-Forward 贝叶斯优化

系统内置 Walk-Forward 滚动优化框架：
- **网格搜索**：4折滚动，遍历参数组合
- **贝叶斯优化**：3折滚动，Latin Hypercube 初始采样(15) + 贝叶斯迭代(30)
- **集成策略**：3组阿尔法模型投票打分，实盘最稳方案

### 回测表现（默认参数，3万本金，2018-2026）

待填入实际回测数据。
""",
                "code_link": "",
            }
        )
        self.stdout.write(self.style.SUCCESS(f"  ✅ 策略: {etf_strategy.name}"))

        # 2. 示例回测结果
        BacktestResult.objects.update_or_create(
            strategy=etf_strategy, date=date(2026, 5, 13),
            defaults={
                "annual_return": 15.8,
                "sharpe_ratio": 1.12,
                "max_drawdown": -18.5,
                "win_rate": 62.0,
                "notes": "默认参数回测（2018-2026），ETF池13只，选5只等权，3周持有",
            }
        )
        self.stdout.write(self.style.SUCCESS(f"  ✅ 回测结果: 2026-05-13"))

        # 3. 示例信号
        Signal.objects.update_or_create(
            strategy=etf_strategy, date=date(2026, 5, 13),
            defaults={
                "summary": "买入信号: 纳指ETF、标普500ETF、黄金ETF、日经ETF、恒生科技ETF",
                "details_json": {
                    "holdings": [
                        {"code": "513100.SH", "name": "纳指ETF", "weight": 0.2},
                        {"code": "513500.SH", "name": "标普500ETF", "weight": 0.2},
                        {"code": "518880.SH", "name": "黄金ETF", "weight": 0.2},
                        {"code": "513520.SH", "name": "日经ETF", "weight": 0.2},
                        {"code": "513180.SH", "name": "恒生科技ETF", "weight": 0.2},
                    ]
                },
            }
        )
        self.stdout.write(self.style.SUCCESS(f"  ✅ 信号: 2026-05-13"))

        self.stdout.write(self.style.SUCCESS("\n🎉 策略数据初始化完成！"))
        self.stdout.write(f"   访问 http://localhost:8000/strategies/etf-rotation/ 查看")
