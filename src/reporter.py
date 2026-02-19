"""
主程序：预算周报生成器
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from .actual_client import ActualClient
from .analyzer import FinanceAnalyzer, WeeklyStats
from .gemini_summarizer import GeminiSummarizer
from .discord_notifier import DiscordNotifier


class BudgetReporter:
    """预算周报生成器"""

    def __init__(
        self,
        actual_url: Optional[str] = None,
        actual_password: Optional[str] = None,
        actual_budget_id: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        discord_webhook: Optional[str] = None,
    ):
        # Actual Budget 配置
        self.actual_url = actual_url or os.getenv("ACTUAL_SERVER_URL")
        self.actual_password = actual_password or os.getenv("ACTUAL_PASSWORD")
        self.actual_budget_id = actual_budget_id or os.getenv("ACTUAL_BUDGET_ID")

        # Gemini 配置
        self.gemini_api_key = gemini_api_key or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")

        # Discord 配置
        self.discord_webhook = discord_webhook or os.getenv("DISCORD_WEBHOOK_URL")

        # 月度预算配置（可选，从环境变量读取 JSON）
        self.monthly_budget = self._load_budget_config()

    def _load_budget_config(self) -> Optional[Dict[str, int]]:
        """加载月度预算配置"""
        import json
        budget_str = os.getenv("MONTHLY_BUDGET", "")
        if budget_str:
            try:
                # 格式: {"餐饮": 50000, "交通": 20000} (单位: cents)
                return json.loads(budget_str)
            except json.JSONDecodeError:
                print("Warning: Invalid MONTHLY_BUDGET format")
        return None

    def generate_weekly_report(
        self,
        reference_date: Optional[datetime] = None,
        compare_with_previous: bool = True
    ) -> Dict[str, Any]:
        """
        生成周报

        Args:
            reference_date: 参考日期，默认今天
            compare_with_previous: 是否对比上周数据

        Returns:
            包含 stats, anomalies, summary, budget_health 的字典
        """
        if not reference_date:
            reference_date = datetime.now()

        # 计算本周日期范围 (周日 -> 周六)
        # 如果今天是周日，这周日就是今天
        days_since_sunday = reference_date.weekday() + 1  # weekday(): Mon=0, Sun=6
        if days_since_sunday == 7:
            days_since_sunday = 0
        week_end = reference_date - timedelta(days=days_since_sunday)
        week_start = week_end - timedelta(days=6)

        start_str = week_start.strftime("%Y-%m-%d")
        end_str = week_end.strftime("%Y-%m-%d")

        print(f"Generating report for: {start_str} ~ {end_str}")

        if not self.actual_url or not self.actual_password:
            print("❌ Error: ACTUAL_SERVER_URL and ACTUAL_PASSWORD are required")
            return {}

        # 连接 Actual Budget
        client = ActualClient(
            server_url=self.actual_url,
            password=self.actual_password,
            budget_id=self.actual_budget_id
        )

        if not client.login():
            raise RuntimeError("Failed to login to Actual Budget")

        # 获取本周交易
        transactions = client.get_transactions(start_str, end_str)
        print(f"Found {len(transactions)} transactions this week")

        # 分析本周数据
        analyzer = FinanceAnalyzer(transactions)
        current_stats = analyzer.calculate_weekly_stats()

        # 获取上周数据用于对比
        previous_stats = None
        if compare_with_previous:
            prev_week_start = week_start - timedelta(days=7)
            prev_week_end = week_end - timedelta(days=7)
            prev_transactions = client.get_transactions(
                prev_week_start.strftime("%Y-%m-%d"),
                prev_week_end.strftime("%Y-%m-%d")
            )
            previous_stats = FinanceAnalyzer(prev_transactions).calculate_weekly_stats()

        # 检测异常
        anomalies = analyzer.detect_anomalies(current_stats, previous_stats)
        print(f"Detected {len(anomalies)} anomalies")

        # 预算健康度
        budget_health = analyzer.calculate_budget_health(current_stats, self.monthly_budget)

        # 生成自然语言摘要（仅当有 Gemini key 时）
        summarizer = GeminiSummarizer(api_key=self.gemini_api_key)
        summary = summarizer.generate_weekly_summary(
            current_stats, anomalies, budget_health
        )

        return {
            "stats": current_stats,
            "anomalies": anomalies,
            "summary": summary,
            "budget_health": budget_health,
            "previous_stats": previous_stats
        }

    def send_report(self, report: Dict[str, Any]) -> bool:
        """发送报告到 Discord"""
        notifier = DiscordNotifier(self.discord_webhook)
        return notifier.send_weekly_report(
            stats=report["stats"],
            anomalies=report["anomalies"],
            summary=report["summary"],
            budget_health=report["budget_health"]
        )

    def run(self) -> bool:
        """运行完整流程：生成 + 发送"""
        try:
            report = self.generate_weekly_report()
            success = self.send_report(report)
            if success:
                print("✅ Weekly report sent successfully")
            else:
                print("❌ Failed to send report")
            return success
        except Exception as e:
            print(f"❌ Error: {e}")
            # 尝试发送错误通知
            try:
                notifier = DiscordNotifier(self.discord_webhook)
                notifier.send_report(f"❌ 预算报告生成失败: {str(e)}")
            except:
                pass
            return False


def main():
    """CLI 入口"""
    reporter = BudgetReporter()
    success = reporter.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
