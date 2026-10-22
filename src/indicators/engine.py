"""Indicator engine: Pruthvi's exact pre-market playbook.

Every function is pure (DataFrame/Series in, values out) so the same engine
serves the morning briefing, the liquidity board and the backtester.

Playbook components:
 1. 9/20/21 EMA stack
 2. 200-day moving average (his hard long filter)
 3. ATR-based supply/demand zones
 4. Daily and weekly RSI(14)
 5. Relative volume vs 20-day average
 6. 20-day and 52-week breakout levels

US equities only. All prices as traded (no currency conversion).
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from .. import config


# ----------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------
def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period).mean()


def atr(df: pd.DataFrame, period: int = config.ATR_PERIOD) -> pd.Series:
    """Average True Range (Wilder smoothing)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def rsi(series: pd.Series, period: int = config.RSI_PERIOD) -> pd.Series:
    """Relative Strength Index (Wilder smoothing), 0-100 scale."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    # Flat market (no losses at all) reads as 100; no gains at all reads 0
    out = out.fillna(100.0 * (avg_gain > 0).astype(float))
    return out.clip(0, 100)


# ----------------------------------------------------------------------
# playbook components
# ----------------------------------------------------------------------
def ema_stack(df: pd.DataFrame) -> Dict[str, float | bool]:
    """9/20/21 EMA stack and where price sits relative to it."""
    close = df["close"]
    e9 = ema(close, config.EMA_FAST).iloc[-1]
    e20 = ema(close, config.EMA_MID).iloc[-1]
    e21 = ema(close, config.EMA_SLOW).iloc[-1]
    price = float(close.iloc[-1])
    return {
        "ema9": float(e9),
        "ema20": float(e20),
        "ema21": float(e21),
        "bullish_stack": bool(e9 > e20 > e21),
        "bearish_stack": bool(e9 < e20 < e21),
        "price_above_stack": bool(price > e9 and price > e20 and price > e21),
        "price_below_stack": bool(price < e9 and price < e20 and price < e21),
    }


def long_filter(df: pd.DataFrame) -> Dict[str, float | bool]:
    """200-day MA: his hard long filter. No longs below it, period."""
    ma200 = sma(df["close"], config.SMA_LONG).iloc[-1]
    price = float(df["close"].iloc[-1])
    return {
        "sma200": float(ma200),
        "price_above_200dma": bool(price > ma200),
        "distance_200dma_pct": float((price - ma200) / ma200 * 100),
    }


def supply_demand_zones(
    df: pd.DataFrame,
    lookback: int = config.ZONE_LOOKBACK,
    width: float = config.ZONE_ATR_WIDTH,
) -> Dict[str, Dict[str, float]]:
    """ATR-based supply/demand zones from recent swing points.

    Supply zone is boxed around the highest high of the lookback window,
    demand zone around the lowest low; each zone is +/- width * ATR.
    These are the zones the order-block detector (build day 3) refines
    into intraday entry zones.
    """
    window = df.iloc[-lookback:]
    atr_now = float(atr(df).iloc[-1])
    swing_high = float(window["high"].max())
    swing_low = float(window["low"].min())
    half = width * atr_now
    price = float(df["close"].iloc[-1])
    return {
        "supply": {
            "top": swing_high + half,
            "bottom": swing_high - half,
            "distance_pct": (swing_high - price) / price * 100,
        },
        "demand": {
            "top": swing_low + half,
            "bottom": swing_low - half,
            "distance_pct": (price - swing_low) / price * 100,
        },
        "atr": atr_now,
    }


def relative_volume(
    df: pd.DataFrame, period: int = config.REL_VOL_PERIOD
) -> Dict[str, float]:
    """Current volume vs its N-day average. >1.5x is elevated."""
    vol = df["volume"]
    avg = vol.rolling(window=period).mean().iloc[-1]
    now = float(vol.iloc[-1])
    return {
        "volume": now,
        "avg_volume_20d": float(avg),
        "relative_volume": float(now / avg) if avg else 0.0,
    }


def intraday_relative_volume(
    bars: pd.DataFrame, lookback_sessions: int = 4
) -> Optional[Dict]:
    """Same-time-of-day relative volume from intraday bars, or None.

    During the regular session a partial day compared with full-day
    averages reads near zero all morning. This compares today's volume
    up to the latest bar's time with the SAME time of day on the prior
    sessions in the bars (Zetaris holds 5m/5d: up to 4 prior sessions).
    No volume curve is assumed - every number is a real bar.

    None when the bars are not intraday, the latest session is already
    complete (last bar at/after 15:55 ET: use the daily method), or no
    prior session covers the same time of day.
    """
    from zoneinfo import ZoneInfo

    if bars is None or len(bars) < 2 or "volume" not in bars:
        return None
    idx = pd.DatetimeIndex(bars.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    spacing = pd.Series(idx).diff().dropna().median()
    if spacing is pd.NaT or spacing > pd.Timedelta(minutes=15):
        return None
    et = idx.tz_convert(ZoneInfo("America/New_York"))
    frame = pd.DataFrame(
        {"volume": bars["volume"].to_numpy(dtype=float),
         "day": et.date, "minute": et.hour * 60 + et.minute}
    )
    today = frame["day"].iloc[-1]
    cutoff = int(frame["minute"].iloc[-1])
    if cutoff >= 15 * 60 + 55:
        return None  # session complete: the daily bar is the right measure
    today_cum = float(frame.loc[(frame["day"] == today) & (frame["minute"] <= cutoff), "volume"].sum())
    prior_days = sorted(d for d in frame["day"].unique() if d < today)[-lookback_sessions:]
    cums = []
    for day in prior_days:
        rows = frame[(frame["day"] == day) & (frame["minute"] <= cutoff)]
        if len(rows) and float(rows["volume"].sum()) > 0:
            cums.append(float(rows["volume"].sum()))
    if not cums:
        return None
    avg = sum(cums) / len(cums)
    hh, mm = divmod(cutoff + 5, 60)  # the bar starting at cutoff ends 5m later
    return {
        "relative_volume": today_cum / avg,
        "volume_so_far": today_cum,
        "avg_same_time": avg,
        "sessions": len(cums),
        "basis": f"same-time-of-day to {hh:02d}:{mm:02d} ET vs {len(cums)} prior sessions",
    }


def breakout_levels(df: pd.DataFrame) -> Dict[str, float | bool]:
    """20-day and 52-week breakout levels and where price sits vs them."""
    price = float(df["close"].iloc[-1])
    hi20 = float(df["high"].iloc[-config.BREAKOUT_SHORT:].max())
    lo20 = float(df["low"].iloc[-config.BREAKOUT_SHORT:].min())
    hi52 = float(df["high"].iloc[-config.BREAKOUT_LONG:].max())
    lo52 = float(df["low"].iloc[-config.BREAKOUT_LONG:].min())

    def _near(level: float) -> bool:
        return abs(price - level) / level <= 0.005  # within 0.5%

    return {
        "high_20d": hi20,
        "low_20d": lo20,
        "high_52w": hi52,
        "low_52w": lo52,
        "at_20d_high": _near(hi20),
        "at_20d_low": _near(lo20),
        "at_52w_high": _near(hi52),
        "at_52w_low": _near(lo52),
        "dist_20d_high_pct": (hi20 - price) / price * 100,
        "dist_52w_high_pct": (hi52 - price) / price * 100,
    }


# ----------------------------------------------------------------------
# full snapshot
# ----------------------------------------------------------------------
def analyze_symbol(
    ticker: str,
    daily: pd.DataFrame,
    weekly: Optional[pd.DataFrame] = None,
) -> Dict:
    """Run the full playbook on one symbol.

    daily: daily OHLCV with >= 252 bars (needed for 200DMA + 52w levels).
    weekly: weekly OHLCV for the weekly RSI. If omitted, weekly RSI is None.
    Returns a JSON-serializable snapshot dict for the briefing engine.
    """
    if len(daily) < config.BREAKOUT_LONG:
        raise ValueError(
            f"{ticker}: need >= {config.BREAKOUT_LONG} daily bars, "
            f"got {len(daily)}"
        )
    price = float(daily["close"].iloc[-1])
    snapshot: Dict = {
        "ticker": ticker,
        "price": price,
        "ema": ema_stack(daily),
        "long_filter": long_filter(daily),
        "zones": supply_demand_zones(daily),
        "rsi_daily": float(rsi(daily["close"]).iloc[-1]),
        "rsi_weekly": (
            float(rsi(weekly["close"]).iloc[-1]) if weekly is not None and len(weekly) > config.RSI_PERIOD else None
        ),
        "volume": relative_volume(daily),
        "breakouts": breakout_levels(daily),
    }
    # One-line regime read for the briefing: trend + momentum + filter
    lf = snapshot["long_filter"]
    em = snapshot["ema"]
    if em["bullish_stack"] and lf["price_above_200dma"]:
        regime = "uptrend"
    elif em["bearish_stack"] and not lf["price_above_200dma"]:
        regime = "downtrend"
    else:
        regime = "mixed"
    snapshot["regime"] = regime
    return snapshot
