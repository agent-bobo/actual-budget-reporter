"""
财务分析引擎 - 纯规则计算，零 LLM Token 消耗
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict

from .actual_client import Transaction


@dataclass
class WeeklyStats:
    """周度统计数据"""
    week_start: str
    week_end: str
    total_income: int  # cents
    total_expense: int  # cents
    net_change: int  # cents
    category_breakdown: Dict[str, int]  # category -> cents
    top_expenses: List[Tuple[str, int]]  # [(category, amount), ...]
    top_transactions: List[Dict]  # Top N transactions by amount (Expenses)
    top_income_transactions: List[Dict]  # Top N income transactions
    uncategorized_count: int
    large_transactions: List[Dict]  # > $100 的交易
    simplified_transactions: List[Dict] # 简化的交易列表，用于 AI 分析
    daily_average: int


@dataclass
class Anomaly:
    """检测到的异常"""
    type: str  # 'spike', 'drop', 'large_transaction', 'uncategorized_cluster'
    severity: str  # 'high', 'medium', 'low'
    description: str
    data: Dict[str, Any]


class FinanceAnalyzer:
    """纯规则引擎，计算所有指标"""

    # 异常检测阈值
    SPIKE_THRESHOLD = 0.30  # 环比增长 >30%
    DROP_THRESHOLD = -0.30  # 环比下降 >30%
    LARGE_TRANSACTION_THRESHOLD = 10000  # $100 (cents)
    UNCATEGORIZED_THRESHOLD = 5  # 未分类交易 >5 笔

    def __init__(self, transactions: List[Transaction]):
        self.transactions = transactions

    def calculate_weekly_stats(self) -> WeeklyStats:
        """计算本周统计"""
        # 1. 过滤掉系统转账 (is_transfer=True)
        # 2. 过滤掉未分类但包含 "Transfer" 关键字的交易
        # 3. 过滤掉 Category 为 None 或者 "Transfer" 的交易
        
        valid_txns = []
        for t in self.transactions:
            if t.is_transfer:
                continue
            
            # Check for manual transfers
            payee_lower = (t.payee or "").lower()
            category_lower = (t.category or "").lower()
            notes_lower = (t.notes or "").lower()
            
            # Keywords often used in transfers
            if "transfer" in payee_lower or "transfer" in category_lower:
                continue
            
            # If notes mention "transfer" and amount is large round number, might still be transfer?
            # Let's be conservative and just check Payee/Category for now.

            valid_txns.append(t)

        if not valid_txns:
            # 没有交易，返回空统计
            return WeeklyStats(
                week_start="",
                week_end="",
                total_income=0,
                total_expense=0,
                net_change=0,
                category_breakdown={},
                top_expenses=[],
                top_transactions=[],
                top_income_transactions=[],
                uncategorized_count=0,
                large_transactions=[],
                simplified_transactions=[],
                daily_average=0
            )

        # 日期范围
        dates = [datetime.strptime(t.date, "%Y-%m-%d") for t in valid_txns]
        week_start = min(dates).strftime("%Y-%m-%d")
        week_end = max(dates).strftime("%Y-%m-%d")

        # 收入和支出（amount: 正数=收入，负数=支出）
        total_income = sum(t.amount for t in valid_txns if t.amount > 0)
        total_expense = abs(sum(t.amount for t in valid_txns if t.amount < 0))
        net_change = total_income - total_expense

        # 分类统计
        category_totals = defaultdict(int)
        uncategorized_count = 0
        
        # 准备交易列表给 AI
        simplified_transactions = []

        for t in valid_txns:
            if t.amount < 0:  # 只统计支出
                if not t.category or t.category == "Uncategorized":
                    uncategorized_count += 1
                    cat_name = "未分类"
                else:
                    cat_name = t.category
                category_totals[cat_name] += abs(t.amount)
            
            # 添加到简化列表
            simplified_transactions.append({
                "date": t.date,
                "payee": t.payee,
                "amount": t.amount / 100, # 转换为美元
                "category": t.category or "未分类",
                "notes": t.notes
            })

        # Top 支出分类
        sorted_categories = sorted(
            category_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )
        top_expenses = sorted_categories[:5]

        # 大额交易（>$100）
        large_transactions = []
        for t in valid_txns:
            if abs(t.amount) >= self.LARGE_TRANSACTION_THRESHOLD:
                large_transactions.append({
                    "date": t.date,
                    "payee": t.payee,
                    "amount": abs(t.amount) / 100,  # 转换为美元
                    "category": t.category or "未分类",
                    "notes": t.notes
                })

        # 日均支出
        days_count = (max(dates) - min(dates)).days + 1
        daily_average = total_expense // max(days_count, 1)

        # Top Transactions (All expenses > $20, or at least Top 5)
        all_expenses = sorted(
            [t for t in simplified_transactions if t['amount'] < 0],
            key=lambda x: abs(x['amount']),
            reverse=True
        )
        
        # Filter > $20 (2000 cents is $20, but amount is already in dollars/float in simplified_transactions? 
        # Wait, simplified_transactions has 'amount' as float (dollars).
        # So check abs(amount) > 20.
        top_transactions = [t for t in all_expenses if abs(t['amount']) > 20]
        
        if len(top_transactions) < 5:
            top_transactions = all_expenses[:5]

        # Top 5 Income Transactions
        top_income_transactions = sorted(
            [t for t in simplified_transactions if t['amount'] > 0],
            key=lambda x: abs(x['amount']),
            reverse=True
        )[:5]

        return WeeklyStats(
            week_start=week_start,
            week_end=week_end,
            total_income=total_income,
            total_expense=total_expense,
            net_change=net_change,
            category_breakdown=dict(category_totals),
            top_expenses=top_expenses,

            top_transactions=top_transactions,
            top_income_transactions=top_income_transactions,
            uncategorized_count=uncategorized_count,
            large_transactions=large_transactions,
            simplified_transactions=simplified_transactions,
            daily_average=daily_average
        )

    def detect_anomalies(
        self,
        current_stats: WeeklyStats,
        previous_stats: Optional[WeeklyStats] = None
    ) -> List[Anomaly]:
        """检测异常，纯规则判断"""
        anomalies = []

        # 1. 未分类交易过多
        if current_stats.uncategorized_count > self.UNCATEGORIZED_THRESHOLD:
            anomalies.append(Anomaly(
                type="uncategorized_cluster",
                severity="medium",
                description=f"本周有 {current_stats.uncategorized_count} 笔未分类交易，建议检查",
                data={"count": current_stats.uncategorized_count}
            ))

        # 2. 大额交易提醒
        for txn in current_stats.large_transactions:
            anomalies.append(Anomaly(
                type="large_transaction",
                severity="low",
                description=f"大额支出: {txn['payee']} ${txn['amount']:.2f}",
                data=txn
            ))

        # 3. 环比分析（需要上周数据）
        if previous_stats:
            # 总支出的环比变化
            if previous_stats.total_expense > 0:
                change_ratio = (
                    current_stats.total_expense - previous_stats.total_expense
                ) / previous_stats.total_expense

                if change_ratio > self.SPIKE_THRESHOLD:
                    anomalies.append(Anomaly(
                        type="spike",
                        severity="high",
                        description=f"本周支出环比增长 {change_ratio*100:.0f}%",
                        data={
                            "ratio": change_ratio,
                            "current": current_stats.total_expense,
                            "previous": previous_stats.total_expense
                        }
                    ))
                elif change_ratio < self.DROP_THRESHOLD:
                    anomalies.append(Anomaly(
                        type="drop",
                        severity="low",
                        description=f"本周支出环比下降 {abs(change_ratio)*100:.0f}%",
                        data={
                            "ratio": change_ratio,
                            "current": current_stats.total_expense,
                            "previous": previous_stats.total_expense
                        }
                    ))

            # 分类级别的环比变化
            for cat, amount in current_stats.category_breakdown.items():
                prev_amount = previous_stats.category_breakdown.get(cat, 0)
                if prev_amount > 0 and amount > prev_amount * (1 + self.SPIKE_THRESHOLD):
                    anomalies.append(Anomaly(
                        type="category_spike",
                        severity="medium",
                        description=f"{cat} 支出激增: ${amount/100:.0f} vs 上周 ${prev_amount/100:.0f}",
                        data={
                            "category": cat,
                            "current": amount,
                            "previous": prev_amount
                        }
                    ))

        return anomalies

    def calculate_budget_health(
        self,
        current_stats: WeeklyStats,
        monthly_budget: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """计算预算健康度"""
        if not monthly_budget:
            return {"status": "unknown", "message": "未设置月度预算"}

        total_budget = sum(monthly_budget.values())
        spent_so_far = current_stats.total_expense
        # 假设本周是月中的某一周，按周平均推算
        projected_monthly = spent_so_far * 4  # 粗略估计

        remaining = total_budget - projected_monthly
        health_ratio = projected_monthly / total_budget if total_budget > 0 else 0

        if health_ratio < 0.8:
            status = "healthy"
            message = "预算进度正常"
        elif health_ratio < 1.0:
            status = "warning"
            message = "预算进度偏快，注意控制"
        else:
            status = "critical"
            message = "预计超支，建议立即调整"

        return {
            "status": status,
            "message": message,
            "projected_monthly": projected_monthly,
            "total_budget": total_budget,
            "remaining": remaining,
            "health_ratio": health_ratio
        }
