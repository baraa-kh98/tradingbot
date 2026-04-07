"""
BaseStrategy — العقد المشترك لجميع استراتيجيات التداول

كل استراتيجية جديدة ترث من هذا الـ class وتلتزم بـ:
  - get_signal()       → يرجع signal dict أو None
  - mark_trade_open()  → يُعلم الاستراتيجية بفتح صفقة
  - mark_trade_closed()→ يُعلم الاستراتيجية بإغلاق صفقة
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pandas as pd


class BaseStrategy(ABC):
    """
    Abstract base class لجميع استراتيجيات التداول.

    تنسيق signal dict الإلزامي:
    {
        "pair":      str,    # "XAUUSD"
        "direction": str,    # "BUY" أو "SELL"
        "entry":     float,
        "sl":        float,
        "tp":        float,
        "risk_pips": float,
        "rr":        float,
        "h4_bias":   str,    # "BULLISH" / "BEARISH" / "NEUTRAL"
        "reason":    str,    # شرح مختصر
    }
    """

    def __init__(self, pair: str, h1_df: pd.DataFrame, h4_df: Optional[pd.DataFrame] = None):
        self.pair   = pair
        self.h1     = h1_df
        self.h4     = h4_df

    @abstractmethod
    def get_signal(self) -> Optional[Dict[str, Any]]:
        """
        يحلل البيانات ويرجع signal dict أو None إذا لا توجد إشارة.
        يجب أن يحتوي على جميع المفاتيح الإلزامية.
        """

    def mark_trade_open(self, direction: str, entry: float, sl: float, tp: float) -> None:
        """يُستدعى عند تنفيذ الصفقة — override إذا الاستراتيجية تحتاج تتبع الحالة."""
        pass

    def mark_trade_closed(self) -> None:
        """يُستدعى عند إغلاق الصفقة — override إذا الاستراتيجية تحتاج reset."""
        pass

    def get_session_report(self) -> str:
        """تقرير مختصر للـ Telegram — override لتخصيصه."""
        return f"📊 {self.pair} — {self.__class__.__name__} يراقب السوق"
