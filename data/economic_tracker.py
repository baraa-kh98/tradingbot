"""
Economic Tracker — محرك البيانات الاقتصادية الكوانتية

يجلب ويخزن بيانات اقتصادية حقيقية من FRED + yfinance:
- أسعار الفائدة: Fed, BOJ
- التضخم: CPI, PCE, Core CPI
- سوق العمل: NFP, Unemployment
- منحنى العائد: 2Y, 5Y, 10Y, 30Y
- بيانات اليابان: BOJ Rate, Japan CPI, JP10Y
- Cross-Asset: DXY, VIX, Gold, Oil, SP500

يستخدم disk cache لتجنب إعادة الجلب كل دورة.
"""

import os
import json
import time
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from data.macro_data import MacroData
from config import FRED_API_KEY, TWELVE_DATA_API_KEY


# ═══════════════════════════════════════════════════════════════
# FRED Series
# ═══════════════════════════════════════════════════════════════

FRED_EXTENDED = {
    "FED_RATE":       "FEDFUNDS",
    "CPI_YOY":        "CPALTT01USM657N",
    "CORE_CPI_YOY":   "CPILFESL",
    "PCE_YOY":        "PCEPI",
    "CORE_PCE_YOY":   "PCEPILFE",
    "NFP":            "PAYEMS",
    "UNEMPLOYMENT":   "UNRATE",
    "GDP_GROWTH":     "A191RL1Q225SBEA",
    "US2Y":           "DGS2",
    "US5Y":           "DGS5",
    "US10Y":          "DGS10",
    "US30Y":          "DGS30",
    "ECB_RATE":       "ECBDFR",
}

YFINANCE_ASSETS = {
    "DXY":   "DX-Y.NYB",
    "VIX":   "^VIX",
    "GOLD":  "GC=F",
    "OIL":   "CL=F",
    "SP500": "^GSPC",
    "US10Y_LIVE": "^TNX",
    "JP10Y": "^JGB",
}

# جدول قرارات BOJ التاريخية (rate %)
BOJ_DECISIONS = {
    "2016-01-29": -0.10,
    "2016-09-21": -0.10,
    "2018-07-31": -0.10,
    "2024-03-19":  0.10,
    "2024-07-31":  0.25,
    "2025-01-24":  0.50,
}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "journal", "macro_cache")


# ═══════════════════════════════════════════════════════════════
# EconomicCache
# ═══════════════════════════════════════════════════════════════

class EconomicCache:
    """Disk cache للبيانات الاقتصادية — يتجنب إعادة الجلب كل دورة"""

    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, key: str) -> str:
        safe = key.replace("/", "_").replace(" ", "_")
        return os.path.join(self.cache_dir, f"{safe}.json")

    def get(self, key: str, max_age_hours: float = 4.0) -> Optional[Dict]:
        path = self._path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                entry = json.load(f)
            saved_at = entry.get("saved_at", 0)
            age_hours = (time.time() - saved_at) / 3600
            if age_hours > max_age_hours:
                return None
            return entry.get("data")
        except Exception:
            return None

    def set(self, key: str, data: Any) -> None:
        path = self._path(key)
        try:
            with open(path, "w") as f:
                json.dump({"saved_at": time.time(), "data": data}, f)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# EconomicTracker
# ═══════════════════════════════════════════════════════════════

class EconomicTracker:
    """
    المحرك الرئيسي للبيانات الاقتصادية.
    يبني snapshot شاملاً يستخدمه MarketRegimeClassifier وQuantSignalModels.
    """

    def __init__(self, fred_api_key: Optional[str] = None, cache_max_age_hours: float = 4.0):
        self.macro = MacroData(api_key=fred_api_key or FRED_API_KEY)
        self.cache = EconomicCache()
        self.max_age = cache_max_age_hours

    # ──────────────────────────────────────────
    # Fed Rate
    # ──────────────────────────────────────────

    def get_fed_rate(self) -> float:
        cached = self.cache.get("fed_rate", self.max_age)
        if cached is not None:
            return cached

        try:
            df = self.macro.get_series("FEDFUNDS")
            if df is not None and not df.empty:
                val = float(df.iloc[-1].values[0])
                self.cache.set("fed_rate", val)
                return val
        except Exception:
            pass

        # fallback: تقدير من 13-week T-bill
        try:
            tb = yf.download("^IRX", period="5d", progress=False, auto_adjust=True)
            if not tb.empty:
                val = float(tb["Close"].iloc[-1])
                self.cache.set("fed_rate", val)
                return val
        except Exception:
            pass

        return 4.50  # fallback default

    # ──────────────────────────────────────────
    # BOJ Rate
    # ──────────────────────────────────────────

    def get_boj_rate(self) -> float:
        cached = self.cache.get("boj_rate", 24.0)  # BOJ يجتمع نادراً — cache 24 ساعة
        if cached is not None:
            return cached

        today = datetime.now().date()
        rate = -0.10  # default قديم
        for date_str, r in sorted(BOJ_DECISIONS.items()):
            if datetime.strptime(date_str, "%Y-%m-%d").date() <= today:
                rate = r

        self.cache.set("boj_rate", rate)
        return rate

    # ──────────────────────────────────────────
    # Yield Curve
    # ──────────────────────────────────────────

    def get_yield_curve(self) -> Dict[str, Any]:
        cached = self.cache.get("yield_curve", self.max_age)
        if cached is not None:
            return cached

        yields = {}
        yf_map = {
            "US2Y": "^IRX",
            "US10Y": "^TNX",
            "US30Y": "^TYX",
        }

        for label, ticker in yf_map.items():
            try:
                df = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
                if not df.empty:
                    yields[label] = round(float(df["Close"].iloc[-1]), 3)
            except Exception:
                pass

        # FRED للـ 5Y
        try:
            df5 = self.macro.get_series("DGS5")
            if df5 is not None and not df5.empty:
                yields["US5Y"] = round(float(df5.iloc[-1].values[0]), 3)
        except Exception:
            pass

        us2y = yields.get("US2Y", 4.5)
        us10y = yields.get("US10Y", 4.3)
        us30y = yields.get("US30Y", 4.5)
        spread_2_10 = round(us10y - us2y, 3)
        spread_2_30 = round(us30y - us2y, 3)

        if spread_2_10 < -0.25:
            curve_shape = "INVERTED"
        elif spread_2_10 < 0.25:
            curve_shape = "FLAT"
        else:
            curve_shape = "NORMAL"

        result = {
            "US2Y": us2y,
            "US5Y": yields.get("US5Y", 4.2),
            "US10Y": us10y,
            "US30Y": us30y,
            "spread_2_10": spread_2_10,
            "spread_2_30": spread_2_30,
            "curve_shape": curve_shape,
        }
        self.cache.set("yield_curve", result)
        return result

    # ──────────────────────────────────────────
    # CPI / Inflation
    # ──────────────────────────────────────────

    def get_cpi_data(self) -> Dict[str, float]:
        cached = self.cache.get("cpi_data", self.max_age)
        if cached is not None:
            return cached

        result = {"cpi_yoy": 2.5, "core_cpi_yoy": 2.8, "pce_yoy": 2.3, "core_pce_yoy": 2.5}

        try:
            df = self.macro.get_series("CPALTT01USM657N")
            if df is not None and not df.empty:
                result["cpi_yoy"] = round(float(df.iloc[-1].values[0]), 2)
        except Exception:
            pass

        try:
            df = self.macro.get_series("CPILFESL")
            if df is not None and not df.empty:
                vals = df.iloc[-13:].values.flatten()
                if len(vals) >= 13:
                    result["core_cpi_yoy"] = round((vals[-1] / vals[0] - 1) * 100, 2)
        except Exception:
            pass

        try:
            df = self.macro.get_series("PCEPI")
            if df is not None and not df.empty:
                vals = df.iloc[-13:].values.flatten()
                if len(vals) >= 13:
                    result["pce_yoy"] = round((vals[-1] / vals[0] - 1) * 100, 2)
        except Exception:
            pass

        self.cache.set("cpi_data", result)
        return result

    # ──────────────────────────────────────────
    # Labor Market
    # ──────────────────────────────────────────

    def get_labor_data(self) -> Dict[str, float]:
        cached = self.cache.get("labor_data", self.max_age)
        if cached is not None:
            return cached

        result = {"nfp_last": 200.0, "nfp_3m_avg": 190.0, "unemployment": 4.0}

        try:
            df = self.macro.get_series("PAYEMS")
            if df is not None and len(df) >= 2:
                vals = df.iloc[-4:].values.flatten()
                nfp_last = float(vals[-1] - vals[-2]) * 1000 if len(vals) >= 2 else 200000
                result["nfp_last"] = round(nfp_last / 1000, 0)
                if len(vals) >= 4:
                    changes = [float(vals[i] - vals[i-1]) * 1000 for i in range(1, 4)]
                    result["nfp_3m_avg"] = round(np.mean(changes) / 1000, 0)
        except Exception:
            pass

        try:
            df = self.macro.get_series("UNRATE")
            if df is not None and not df.empty:
                result["unemployment"] = round(float(df.iloc[-1].values[0]), 1)
        except Exception:
            pass

        self.cache.set("labor_data", result)
        return result

    # ──────────────────────────────────────────
    # GDP
    # ──────────────────────────────────────────

    def get_gdp_data(self) -> Dict[str, float]:
        cached = self.cache.get("gdp_data", 24.0)
        if cached is not None:
            return cached

        result = {"gdp_growth_qoq": 2.0, "gdp_growth_yoy": 2.5}

        try:
            df = self.macro.get_series("A191RL1Q225SBEA")
            if df is not None and not df.empty:
                result["gdp_growth_qoq"] = round(float(df.iloc[-1].values[0]), 2)
                if len(df) >= 4:
                    vals = df.iloc[-4:].values.flatten()
                    result["gdp_growth_yoy"] = round(float(np.mean(vals)), 2)
        except Exception:
            pass

        self.cache.set("gdp_data", result)
        return result

    # ──────────────────────────────────────────
    # Japan Data
    # ──────────────────────────────────────────

    def get_japan_data(self) -> Dict[str, float]:
        cached = self.cache.get("japan_data", self.max_age)
        if cached is not None:
            return cached

        boj_rate = self.get_boj_rate()
        jp10y = 0.9

        try:
            df = yf.download("^JGB", period="5d", progress=False, auto_adjust=True)
            if not df.empty:
                jp10y = round(float(df["Close"].iloc[-1]), 3)
        except Exception:
            pass

        us10y = self.get_yield_curve().get("US10Y", 4.3)
        jp_us_spread = round(us10y - jp10y, 3)

        result = {
            "boj_rate": boj_rate,
            "japan_cpi_yoy": 2.3,
            "jp10y_yield": jp10y,
            "jp_us_yield_spread": jp_us_spread,
        }
        self.cache.set("japan_data", result)
        return result

    # ──────────────────────────────────────────
    # Cross-Asset Snapshot
    # ──────────────────────────────────────────

    def _fetch_td_asset(self, td_symbol: str) -> Dict[str, Any]:
        """يجلب أصل واحد من Twelve Data — يرجع dict فارغ عند الفشل"""
        if not TWELVE_DATA_API_KEY:
            return {}
        try:
            from twelvedata import TDClient
            td = TDClient(apikey=TWELVE_DATA_API_KEY)
            ts = td.time_series(symbol=td_symbol, interval="1day", outputsize=10, timezone="UTC").as_pandas()
            if ts is None or len(ts) < 2:
                return {}
            ts = ts.sort_index()
            close = ts["close"].astype(float)
            price = float(close.iloc[-1])
            chg_1d = round((price / float(close.iloc[-2]) - 1) * 100, 2) if len(close) >= 2 else 0.0
            chg_5d = round((price / float(close.iloc[-6]) - 1) * 100, 2) if len(close) >= 6 else 0.0
            return {"price": round(price, 3), "change_1d": chg_1d, "change_5d": chg_5d}
        except Exception:
            return {}

    def get_cross_asset(self) -> Dict[str, Dict]:
        cached = self.cache.get("cross_asset", self.max_age)
        if cached is not None:
            return cached

        result = {}

        # Twelve Data أولاً للأصول الأساسية (أكثر دقة من yfinance للفوركس والذهب)
        td_assets = {
            "GOLD": "XAU/USD",
            "DXY":  "DX-Y.NYB",
        }
        for name, td_sym in td_assets.items():
            entry = self._fetch_td_asset(td_sym)
            if entry:
                result[name] = entry

        # yfinance للباقي (VIX, Oil, SP500) + fallback للـ GOLD/DXY إذا فشل TD
        yf_assets = {
            "DXY":   "DX-Y.NYB",
            "VIX":   "^VIX",
            "GOLD":  "GC=F",
            "OIL":   "CL=F",
            "SP500": "^GSPC",
        }

        for name, ticker in yf_assets.items():
            if name in result:          # تجاوز إذا جلبناه من TD بنجاح
                continue
            try:
                df = yf.download(ticker, period="10d", progress=False, auto_adjust=True)
                if df.empty:
                    continue
                close = df["Close"].dropna()
                price = float(close.iloc[-1])
                chg_1d = round((price / float(close.iloc[-2]) - 1) * 100, 2) if len(close) >= 2 else 0.0
                chg_5d = round((price / float(close.iloc[-6]) - 1) * 100, 2) if len(close) >= 6 else 0.0
                result[name] = {"price": round(price, 3), "change_1d": chg_1d, "change_5d": chg_5d}
            except Exception:
                pass

        # VIX percentile
        if "VIX" in result:
            try:
                df_y = yf.download("^VIX", period="1y", progress=False, auto_adjust=True)
                hist = df_y["Close"].dropna().values
                vix_price = result["VIX"]["price"]
                pct = round(float(np.sum(hist < vix_price) / len(hist) * 100), 1)
                result["VIX"]["percentile_1y"] = pct
            except Exception:
                result["VIX"]["percentile_1y"] = 50.0

        self.cache.set("cross_asset", result)
        return result

    # ──────────────────────────────────────────
    # ECB Rate
    # ──────────────────────────────────────────

    def get_ecb_rate(self) -> float:
        cached = self.cache.get("ecb_rate", 24.0)
        if cached is not None:
            return cached

        try:
            df = self.macro.get_series("ECBDFR")
            if df is not None and not df.empty:
                val = round(float(df.iloc[-1].values[0]), 2)
                self.cache.set("ecb_rate", val)
                return val
        except Exception:
            pass

        return 2.50  # fallback

    # ──────────────────────────────────────────
    # Full Snapshot — الدالة الرئيسية
    # ──────────────────────────────────────────

    def get_full_snapshot(self) -> Dict[str, Any]:
        """
        يرجع snapshot شامل لكل البيانات الاقتصادية.
        يُستخدم من قِبل MarketRegimeClassifier و QuantSignalAggregator.
        """
        fed_rate = self.get_fed_rate()
        boj_rate = self.get_boj_rate()
        ecb_rate = self.get_ecb_rate()
        yield_curve = self.get_yield_curve()
        cpi = self.get_cpi_data()
        labor = self.get_labor_data()
        gdp = self.get_gdp_data()
        japan = self.get_japan_data()
        cross_asset = self.get_cross_asset()

        # فوارق أسعار الفائدة
        rate_diff_usd_jpy = round(fed_rate - boj_rate, 2)
        rate_diff_eur_usd = round(ecb_rate - fed_rate, 2)

        vix_price = cross_asset.get("VIX", {}).get("price", 20.0)
        sp500_chg_5d = cross_asset.get("SP500", {}).get("change_5d", 0.0)

        # تحديد اتجاه الفيد: HIKING / CUTTING / HOLDING
        fed_direction = "HOLDING"
        try:
            df_fed = self.macro.get_series("FEDFUNDS")
            if df_fed is not None and len(df_fed) >= 3:
                vals = df_fed.iloc[-3:].values.flatten()
                if vals[-1] > vals[-3] + 0.1:
                    fed_direction = "HIKING"
                elif vals[-1] < vals[-3] - 0.1:
                    fed_direction = "CUTTING"
        except Exception:
            pass

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fed_rate": fed_rate,
            "boj_rate": boj_rate,
            "ecb_rate": ecb_rate,
            "fed_direction": fed_direction,
            "rate_differential_usd_jpy": rate_diff_usd_jpy,
            "rate_differential_eur_usd": rate_diff_eur_usd,
            "yield_curve": yield_curve,
            "cpi": cpi,
            "labor": labor,
            "gdp": gdp,
            "japan": japan,
            "cross_asset": cross_asset,
            "vix": vix_price,
            "sp500_5d_change": sp500_chg_5d,
            "dxy_1d_change": cross_asset.get("DXY", {}).get("change_1d", 0.0),
        }


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("═══ اختبار EconomicTracker ═══\n")
    tracker = EconomicTracker()
    snap = tracker.get_full_snapshot()

    print(f"Fed Rate:    {snap['fed_rate']}%")
    print(f"BOJ Rate:    {snap['boj_rate']}%")
    print(f"USD/JPY Carry Diff: {snap['rate_differential_usd_jpy']}%")
    print(f"Yield Curve: {snap['yield_curve']['curve_shape']} (2-10 spread: {snap['yield_curve']['spread_2_10']})")
    print(f"CPI YoY:     {snap['cpi']['cpi_yoy']}%")
    print(f"NFP Last:    {snap['labor']['nfp_last']}K")
    print(f"Unemployment:{snap['labor']['unemployment']}%")
    print(f"GDP Growth:  {snap['gdp']['gdp_growth_qoq']}%")
    print(f"VIX:         {snap['vix']}")
    print(f"DXY 1d:      {snap['dxy_1d_change']}%")
    print(f"SP500 5d:    {snap['sp500_5d_change']}%")
