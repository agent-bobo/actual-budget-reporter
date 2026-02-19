"""
Gemini Insight Generator - 只处理预聚合后的数据，极低 Token 成本
"""
import os
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

from .analyzer import WeeklyStats, Anomaly


class GeminiSummarizer:
    """用 Gemini 生成自然语言摘要，只输入统计数据，不输入原始交易"""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        self.model = model

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def generate_weekly_summary(
        self,
        stats: WeeklyStats,
        anomalies: List[Anomaly],
        budget_health: Dict[str, Any]
    ) -> str:
        """
        生成周报摘要
        """
        if not self.client:
            return self._fallback_summary(stats, anomalies)

        # 构建极简 prompt，只包含聚合数据
        prompt = self._build_prompt(stats, anomalies, budget_health)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            print(f"Gemini error: {e}")
            return self._fallback_summary(stats, anomalies)

    def _build_prompt(
        self,
        stats: WeeklyStats,
        anomalies: List[Anomaly],
        budget_health: Dict[str, Any]
    ) -> str:
        """构建极简 Prompt"""

        # 金额转换为美元显示
        income = stats.total_income / 100
        expense = stats.total_expense / 100
        daily_avg = stats.daily_average / 100

        # Top 3 支出分类
        top3_str = "\n".join([
            f"- {cat}: ${amount/100:.0f}"
            for cat, amount in stats.top_expenses[:3]
        ])

        # 异常列表
        anomaly_str = ""
        if anomalies:
            anomaly_str = "\n".join([
                f"- [{a.severity}] {a.description}"
                for a in anomalies[:5]  # 最多5条
            ])
        else:
            anomaly_str = "无异常"

        # 预算健康
        budget_str = budget_health.get("message", "预算数据不可用")

        prompt = f"""你是一个财务顾问，用简短、友善的语气写周报摘要。

本周数据 ({stats.week_start} ~ {stats.week_end}):
- 收入: ${income:.0f}
- 支出: ${expense:.0f} (日均 ${daily_avg:.0f})
- 结余: ${(income - expense):.0f}

支出Top3:
{top3_str}

异常提醒:
{anomaly_str}

预算状态: {budget_str}

用3-5句话总结本周财务状况，给一条实用建议。语气轻松，像朋友聊天。"""

        return prompt

    def _fallback_summary(
        self,
        stats: WeeklyStats,
        anomalies: List[Anomaly]
    ) -> str:
        """Gemini 失败时的回退方案"""
        lines = [
            f"本周支出 ${stats.total_expense/100:.0f}，",
        ]

        if stats.total_income > 0:
            lines.append(f"收入 ${stats.total_income/100:.0f}，")

        if anomalies:
            high_priority = [a for a in anomalies if a.severity == "high"]
            if high_priority:
                lines.append(f"注意: {high_priority[0].description}")
            else:
                lines.append("财务状况正常，继续保持。")
        else:
            lines.append("本周无异常支出。")

        return "".join(lines)
