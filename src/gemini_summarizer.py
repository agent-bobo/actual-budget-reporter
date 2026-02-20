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

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            print(f"✨ Gemini initialized with model: {self.model}")
        else:
            print("⚠️ Gemini API key not found, using fallback summary")
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
        """构建结构化 Prompt"""

        # 金额转换为美元显示
        income = stats.total_income / 100
        expense = stats.total_expense / 100
        balance = (stats.total_income - stats.total_expense) / 100
        daily_avg = stats.daily_average / 100

        # Top 5 支出交易
        top5_list = []
        for i, txn in enumerate(stats.top_transactions[:5], 1):
            amount = txn['amount'] # already in dollars from analyzer
            top5_list.append(f"{i}. {txn['payee']}: ${amount:.0f} ({txn['category']})")
        top5_str = "\n".join(top5_list)

        # 异常/大额交易提醒
        attention_list = []
        # 添加大额交易
        for txn in stats.large_transactions[:5]: # limit to 5
            attention_list.append(f"• {txn['date'][5:]}有一笔${txn['amount']:.0f}的{txn['category']}支出 ({txn['payee']})")
        
        # 添加高优先级异常
        for a in anomalies:
            if a.severity == "high":
                attention_list.append(f"• {a.description}")
        
        attention_str = "\n".join(attention_list) if attention_list else "无特别关注事项"

        # 预算健康
        budget_status = budget_health.get("message", "预算数据不可用")

        # 准备交易详情 (Top 30 by amount)
        # Sort by absolute amount descending
        sorted_txns = sorted(
            stats.simplified_transactions,
            key=lambda x: abs(x['amount']),
            reverse=True
        )[:30]

        txn_list_str = "\n".join([
            f"- {t['date']} {t['payee']}: ${t['amount']:.2f} ({t['category']}) {t.get('notes') or ''}"
            for t in sorted_txns
        ])

        prompt = f"""你是一个专业的财务助手。请根据以下数据，完全按照指定的 Markdown 格式生成周报。不要添加任何开场白或结束语。

数据:
日期范围: {stats.week_start} ~ {stats.week_end}
收入: ${income:.0f}
支出: ${expense:.0f}
日均支出: ${daily_avg:.0f}
结余: ${balance:.0f}

Top5支出:
{top5_str}

预算状态: {budget_status}

异常/关注事项:
{attention_str}

本周交易详情 (按金额排序, Top 30):
{txn_list_str}

要求:
1. "本周洞察"部分：请根据收支数据、预算状态和交易详情，写一段简短的分析（3-5句话）。计算支出占收入的比例。语气专业但亲切。
2. 保持格式整洁，使用emoji。
3. 如果结余为负，请在洞察中委婉提醒。
4. 参考“交易详情”来提供更具体的分析，例如具体是哪笔交易导致了支出过高。

输出格式模板:
# 📊 本周财务简报
**{stats.week_start} ~ {stats.week_end}**

## 💰 收支概览
• 收入: **${income:.0f}**
• 支出: **${expense:.0f}** (日均 ${daily_avg:.0f})
• 结余: **${balance:.0f}**

## 📈 支出Top5
{top5_str}

## ✅ 预算状态
{budget_status}

## 💡 本周洞察
[在此处生成分析]

## 🚨 需要关注
{attention_str}
"""
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
