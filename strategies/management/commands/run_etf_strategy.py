"""
运行 ETF 轮动策略 — 更新最新信号到数据库

用法：
    python manage.py run_etf_strategy [--token YOUR_TUSHARE_TOKEN]
                                       [--start 20200101]
                                       [--end 20260510]

如果不传 token，默认使用策略文件中内置的 token（建议配置环境变量 TUSHARE_TOKEN）
"""
import os
import sys
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from strategies.models import Strategy, BacktestResult, Signal


class Command(BaseCommand):
    help = "运行 ETF 轮动策略并更新信号到数据库"

    def add_arguments(self, parser):
        parser.add_argument("--token", default=None, help="tushare API token")
        parser.add_argument("--start", default="20200101", help="回测开始日期")
        parser.add_argument("--end", default=None, help="回测结束日期（默认今天）")

    def handle(self, *args, **options):
        # 检查 tushare
        try:
            import tushare as ts
        except ImportError:
            raise CommandError(
                "需要安装 tushare：pip install tushare\n"
                "或者先通过管理后台手动录入策略数据。"
            )

        token = options["token"] or os.getenv("TUSHARE_TOKEN") or "d45373f7d85863f2d4193ce5fdd0d58e8e7d42f5db4db422be883cbc171d"
        start = options["start"]
        end = options["end"] or date.today().strftime("%Y%m%d")

        self.stdout.write(f"📡 ETF轮动策略 — 回测区间 {start} ~ {end}")
        self.stdout.write(f"   Token: {'已设置' if token else '未设置'}")

        # 动态导入策略（从 scripts/ 目录）
        sys.path.insert(0, str(settings.BASE_DIR / "scripts"))
        try:
            from etf_rotation_strategy import ETF_POOL, ETFRotationStrategy
        except ImportError as e:
            raise CommandError(f"无法导入策略模块: {e}")

        # 运行策略
        self.stdout.write("   正在获取数据...")
        try:
            strategy = ETFRotationStrategy(ETF_POOL, start, end, token, init_cash=30000)
            strategy.fetch_all_data()
            self.stdout.write(self.style.SUCCESS(f"   数据获取完成 ({len(ETF_POOL)} 只 ETF)"))
        except Exception as e:
            raise CommandError(f"数据获取失败: {e}")

        self.stdout.write("   正在运行回测...")
        try:
            perf = strategy.run_backtest(verbose=False, stop_loss=0)
            self.stdout.write(self.style.SUCCESS("   回测完成"))
        except Exception as e:
            raise CommandError(f"回测失败: {e}")

        # 保存结果
        strategy_obj, _ = Strategy.objects.get_or_create(
            slug="etf-rotation",
            defaults={"name": "ETF轮动策略", "description": "基于多周期动量因子的ETF轮动系统"},
        )

        # 回测指标
        metrics = strategy._calc_performance()
        BacktestResult.objects.create(
            strategy=strategy_obj,
            date=date.today(),
            annual_return=metrics.get("年化收益率"),
            sharpe_ratio=metrics.get("夏普比率"),
            max_drawdown=metrics.get("最大回撤"),
            win_rate=metrics.get("胜率"),
            metrics_json=metrics,
        )

        # 最新持仓信号
        latest_holdings = getattr(strategy, 'current_holdings', [])
        if latest_holdings:
            holdings_detail = []
            for h in latest_holdings:
                code = h.get("code", "")
                name = ETF_POOL.get(code, code)
                holdings_detail.append({
                    "code": code,
                    "name": name,
                    "weight": round(1.0 / len(latest_holdings), 3),
                })

            Signal.objects.create(
                strategy=strategy_obj,
                date=date.today(),
                summary=f"持仓信号: {', '.join(h['name'] for h in holdings_detail[:5])}",
                details_json={"holdings": holdings_detail},
            )

        self.stdout.write(self.style.SUCCESS(f"\n🎉 策略运行完成！"))
        self.stdout.write(f"   年化收益: {metrics.get('年化收益率', 'N/A')}")
        self.stdout.write(f"   夏普比率: {metrics.get('夏普比率', 'N/A')}")
        self.stdout.write(f"   最大回撤: {metrics.get('最大回撤', 'N/A')}")
        self.stdout.write(f"   查看详情: http://localhost:8000/strategies/etf-rotation/")
