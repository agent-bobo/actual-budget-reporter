"""
Discord Webhook 通知器
"""
import os
import json
import requests
from typing import Optional


class DiscordNotifier:
    """发送报告到 Discord"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")

    def send_report(self, content: str) -> bool:
        """发送 Markdown 格式的报告"""
        if not self.webhook_url:
            print("Warning: DISCORD_WEBHOOK_URL not set")
            return False

        # Discord 限制: content 最长 2000 字符
        if len(content) > 2000:
            content = content[:1997] + "..."

        payload = {
            "content": content,
            "username": "Budget Reporter",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/3135/3135679.png"
        }

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to send Discord notification: {e}")
            return False

    def send_weekly_report(
        self,
        stats: "WeeklyStats",
        anomalies: list,
        summary: str,
        budget_health: dict
    ) -> bool:
        """格式化并发送周报"""
        
        # 如果有 AI 摘要，直接使用 AI 摘要（它已经包含了所有必要信息）
        if summary:
            return self.send_report(summary)

        # 降级方案：如果没有 AI 摘要，使用旧的拼接逻辑
        
        # 金额格式化
        def fmt_cents(cents: int) -> str:
            return f"${cents/100:.0f}"

        # 构建 Discord 消息
        lines = [
            "# 📊 本周财务简报 (Fallback)",
            f"**{stats.week_start} ~ {stats.week_end}**\n",
            "## 💰 收支概览",
            f"• 收入: **{fmt_cents(stats.total_income)}**",
            f"• 支出: **{fmt_cents(stats.total_expense)}** (日均 {fmt_cents(stats.daily_average)})",
            f"• 结余: **{fmt_cents(stats.net_change)}**\n",
        ]

        # Top 5 支出
        if stats.top_expenses:
            lines.append("## 📈 支出Top5")
            for i, (cat, amount) in enumerate(stats.top_expenses[:5], 1):
                lines.append(f"{i}. {cat}: {fmt_cents(amount)}")
            lines.append("")

        # 预算健康度
        if budget_health.get("status"):
            emoji = {"healthy": "✅", "warning": "⚠️", "critical": "🚨", "unknown": "❓"}
            status_emoji = emoji.get(budget_health["status"], "❓")
            lines.append(f"## {status_emoji} 预算状态")
            lines.append(f"{budget_health.get('message', 'N/A')}\n")

        # 异常提醒
        high_anomalies = [a for a in anomalies if a.severity == "high"]
        if high_anomalies:
            lines.append("## 🚨 需要关注")
            for a in high_anomalies[:5]:
                lines.append(f"• {a.description}")
            lines.append("")

        content = "\n".join(lines)
        return self.send_report(content)
