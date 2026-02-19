"""
Actual Budget API Client
使用 @actual-app/api 类似的思路，通过 Actual 的 API 获取数据
"""
import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Transaction:
    id: str
    date: str
    amount: int  # cents
    payee: str
    category: Optional[str]
    account: str
    notes: Optional[str]
    is_transfer: bool


@dataclass
class Category:
    id: str
    name: str
    group: str
    is_income: bool


class ActualClient:
    """连接 Actual Budget Server 的客户端"""

    def __init__(self, server_url: str, password: str, budget_id: str):
        self.server_url = server_url.rstrip('/')
        self.password = password
        self.budget_id = budget_id
        self.token = None

    def login(self) -> bool:
        """获取 access token"""
        try:
            resp = requests.post(
                f"{self.server_url}/account/login",
                json={"password": self.password},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("data", {}).get("token")
            return bool(self.token)
        except Exception as e:
            print(f"Login failed: {e}")
            return False

    def _api_get(self, path: str) -> Dict:
        """带认证的 GET 请求"""
        if not self.token:
            raise RuntimeError("Not logged in")

        resp = requests.get(
            f"{self.server_url}/{path}",
            headers={"X-Actual-Token": self.token},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def get_transactions(self, start_date: str, end_date: str) -> List[Transaction]:
        """获取指定日期范围的交易"""
        # Actual API 格式: /transactions?startDate=2024-01-01&endDate=2024-01-31
        data = self._api_get(
            f"transactions?startDate={start_date}&endDate={end_date}"
        )

        transactions = []
        for t in data.get("data", []):
            transactions.append(Transaction(
                id=t.get("id"),
                date=t.get("date"),
                amount=t.get("amount", 0),
                payee=t.get("payee", ""),
                category=t.get("category", ""),
                account=t.get("account", ""),
                notes=t.get("notes"),
                is_transfer=t.get("isTransfer", False)
            ))

        return transactions

    def get_categories(self) -> List[Category]:
        """获取所有分类"""
        data = self._api_get("categories")
        categories = []
        for c in data.get("data", []):
            categories.append(Category(
                id=c.get("id"),
                name=c.get("name", ""),
                group=c.get("group", ""),
                is_income=c.get("isIncome", False)
            ))
        return categories

    def get_accounts(self) -> List[Dict]:
        """获取账户列表"""
        return self._api_get("accounts").get("data", [])
