import os
import json
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from actual import Actual
from actual.database import Transactions, Categories, Accounts

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
    """连接 Actual Budget Server 的客户端 (using actualpy)"""

    def __init__(self, server_url: str, password: str, budget_id: str):
        self.server_url = server_url.rstrip('/')
        self.password = password
        self.budget_id = budget_id
        # Allow disabling SSL verification for local/self-hosted instances
        self.verify_ssl = os.getenv("ACTUAL_VERIFY_SSL", "true").lower() == "true"
        
        self.actual = Actual(
            base_url=self.server_url,
            password=self.password,
            file=self.budget_id,
            cert=False if not self.verify_ssl else None
        )
        self._session_active = False

    def login(self) -> bool:
        """Initialize connection and download budget"""
        try:
            self.actual.__enter__()
            self._session_active = True
            return True
        except Exception as e:
            print(f"Login/Download failed: {e}")
            return False

    def close(self):
        if self._session_active:
            self.actual.__exit__(None, None, None)
            self._session_active = False

    def __del__(self):
        self.close()

    def get_transactions(self, start_date: str, end_date: str) -> List[Transaction]:
        """获取指定日期范围的交易"""
        # Convert YYYY-MM-DD string to YYYYMMDD int
        start_int = int(start_date.replace('-', ''))
        end_int = int(end_date.replace('-', ''))

        session = self.actual.session
        
        # Query transactions
        db_txns = session.query(Transactions).filter(
            Transactions.date >= start_int,
            Transactions.date <= end_int,
            Transactions.is_parent == 0,
            Transactions.tombstone == 0
        ).all()

        transactions = []
        for t in db_txns:
            # Payee might be None for transfers or if deleted
            payee_name = t.payee.name if t.payee else ""
            if not payee_name and t.transfer:
                 # Check if it's a transfer
                 payee_name = f"Transfer: {t.transfer.account.name}" if t.transfer.account else "Transfer"

            category_name = t.category.name if t.category else ""
            account_name = t.account.name if t.account else ""
            
            # Date conversion int -> str YYYY-MM-DD
            date_str = str(t.date)
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

            transactions.append(Transaction(
                id=t.id,
                date=date_fmt,
                amount=t.amount,
                payee=payee_name,
                category=category_name,
                account=account_name,
                notes=t.notes,
                is_transfer=t.transferred_id is not None
            ))

        return transactions

    def get_categories(self) -> List[Category]:
        """获取所有分类"""
        session = self.actual.session
        db_cats = session.query(Categories).filter(Categories.tombstone == 0).all()
        
        categories = []
        for c in db_cats:
            group_name = c.group.name if c.group else ""
            categories.append(Category(
                id=c.id,
                name=c.name,
                group=group_name,
                is_income=c.is_income == 1
            ))
        return categories

    def get_accounts(self) -> List[Dict]:
        """获取账户列表"""
        session = self.actual.session
        db_accts = session.query(Accounts).filter(Accounts.tombstone == 0).all()
        
        accounts = []
        for a in db_accts:
            accounts.append({
                "id": a.id,
                "name": a.name,
                "offbudget": a.offbudget == 1,
                "closed": a.closed == 1
            })
        return accounts
