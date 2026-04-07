"""
StrategyRouter — يختار الاستراتيجية المناسبة لكل زوج

طريقة التبديل بين الاستراتيجيات:
  1. عدّل config.py: PAIR_STRATEGIES["XAUUSD"] = "GoldICTStrategy"
  2. أرسل /reload على Telegram
  3. الاستراتيجية الجديدة تشتغل في الدورة القادمة — بدون restart
"""

from typing import Optional
import pandas as pd

from config import PAIR_STRATEGIES
from strategy.london_signal import LondonSignalGenerator
from strategy.xauusd_signal import XAUUSDSignalGenerator
from strategy.eurusd_signal import EURUSDSignalGenerator
from strategy.gbpusd_signal import GBPUSDSignalGenerator

_STRATEGY_MAP = {
    "LondonBreakout":    LondonSignalGenerator,
    "GoldATRBreakout":   XAUUSDSignalGenerator,
    "EURUSDNYBreakout":  EURUSDSignalGenerator,
    "GBPUSDNYBreakout":  GBPUSDSignalGenerator,
}


def get_strategy(pair: str, h1_df: pd.DataFrame, h4_df: Optional[pd.DataFrame] = None):
    """
    يرجع instance الاستراتيجية المناسبة للزوج.
    يقرأ PAIR_STRATEGIES من config للتحديد.
    Fallback: LondonBreakout إذا الزوج غير معرّف.
    """
    strategy_name = PAIR_STRATEGIES.get(pair, "LondonBreakout")
    cls = _STRATEGY_MAP.get(strategy_name)

    if cls is None:
        raise ValueError(
            f"استراتيجية '{strategy_name}' غير موجودة في _STRATEGY_MAP. "
            f"أضفها أولاً في strategy_router.py"
        )

    return cls(pair, h1_df, h4_df)
