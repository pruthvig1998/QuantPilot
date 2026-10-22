"""Market X-Ray (build plan module 3).

Two reads of the whole market in one pass:

1. Breadth across the 12-name watchlist. Every name runs through the
   indicator engine's playbook snapshot and gets classified bullish /
   bearish / neutral, with the counts broken out by signal family:
   above vs below the 200DMA, bullish vs bearish EMA stack, and RSI
   zone (overbought / oversold / neutral). The classification rule is
   the engine's own regime rule: bullish stack + above the 200DMA is
   bullish, bearish stack + below it is bearish, anything else is
   neutral. No hidden scoring - the counts ARE the read.

2. Sector rotation from the 10 US sector ETFs. Each sector is ranked
   by a momentum blend of its 5 / 21 / 63-day returns, with 21-day
   relative strength vs SPY carried alongside so "leading" means
   beating the index, not just rising with it.

Everything is a pure function of provider data (bars in, JSON out).
A name whose fetch fails lands in "errors" instead of sinking the
scan, same contract as the liquidity board.

US markets only. Works against any MarketDataProvider.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .. import config
from ..data.provider import MarketDataProvider
from ..indicators import analyze_symbol, rsi, sma

BENCHMARK = "SPY"


# ----------------------------------------------------------------------
# classification (pure over an indicator snapshot)
# ----------------------------------------------------------------------
def rsi_zone(value: Optional[float]) -> Optional[str]:
    """RSI zone label: overbought / oversold / neutral (None if no RSI)."""
    if value is None:
        return None
    if value >= config.XRAY_RSI_OVERBOUGHT:
        return "overbought"
    if value <= config.XRAY_RSI_OVERSOLD:
        return "oversold"
    return "neutral"


def classify_snapshot(snapshot: Dict) -> Dict:
    """Classify one analyze_symbol() snapshot.

    Direction follows the engine's regime rule exactly, so the X-Ray
    never disagrees with the morning briefing about what an uptrend is.
    The signal-family booleans ride along for the breadth counts.
    """
    em = snapshot["ema"]
    lf = snapshot["long_filter"]
    zone = rsi_zone(snapshot.get("rsi_daily"))
    if em["bullish_stack"] and lf["price_above_200dma"]:
        direction = "bullish"
    elif em["bearish_stack"] and not lf["price_above_200dma"]:
        direction = "bearish"
    else:
        direction = "neutral"
    return {
        "ticker": snapshot["ticker"],
        "price": snapshot["price"],
        "direction": direction,
        "regime": snapshot.get("regime"),
        "above_200dma": bool(lf["price_above_200dma"]),
        "distance_200dma_pct": round(float(lf["distance_200dma_pct"]), 2),
        "bullish_stack": bool(em["bullish_stack"]),
        "bearish_stack": bool(em["bearish_stack"]),
        "rsi_daily": (
            round(float(snapshot["rsi_daily"]), 1)
            if snapshot.get("rsi_daily") is not None
            else None
        ),
        "rsi_zone": zone,
    }


# ----------------------------------------------------------------------
# breadth across the watchlist
# ----------------------------------------------------------------------
def breadth(
    provider: MarketDataProvider,
    tickers: Optional[Sequence[str]] = None,
) -> Dict:
    """Classify every watchlist name and total the signal families."""
    rows: List[Dict] = []
    errors: List[Dict] = []
    for ticker in tickers or config.WATCHLIST:
        try:
            daily = provider.get_bars(ticker, interval="1d", period="2y")
            try:
                weekly = provider.get_bars(ticker, interval="1wk", period="5y")
            except Exception:
                weekly = None  # weekly RSI is a bonus, not a blocker
            rows.append(classify_snapshot(analyze_symbol(ticker, daily, weekly)))
        except Exception as exc:  # one bad name must not sink the scan
            errors.append({"ticker": ticker, "error": str(exc)})

    counts = {
        "total": len(rows),
        "bullish": sum(1 for r in rows if r["direction"] == "bullish"),
        "bearish": sum(1 for r in rows if r["direction"] == "bearish"),
        "neutral": sum(1 for r in rows if r["direction"] == "neutral"),
        "above_200dma": sum(1 for r in rows if r["above_200dma"]),
        "below_200dma": sum(1 for r in rows if not r["above_200dma"]),
        "bullish_stack": sum(1 for r in rows if r["bullish_stack"]),
        "bearish_stack": sum(1 for r in rows if r["bearish_stack"]),
        "rsi_overbought": sum(1 for r in rows if r["rsi_zone"] == "overbought"),
        "rsi_oversold": sum(1 for r in rows if r["rsi_zone"] == "oversold"),
        "rsi_neutral": sum(1 for r in rows if r["rsi_zone"] == "neutral"),
    }
    counts["pct_above_200dma"] = (
        round(100.0 * counts["above_200dma"] / counts["total"], 1)
        if counts["total"]
        else 0.0
    )
    return {"counts": counts, "symbols": rows, "errors": errors}


# ----------------------------------------------------------------------
# sector rotation
# ----------------------------------------------------------------------
def _return_pct(closes, days: int) -> Optional[float]:
    """Percent return over the last `days` bars (None if too short)."""
    if len(closes) <= days:
        return None
    start = float(closes.iloc[-1 - days])
    end = float(closes.iloc[-1])
    return (end / start - 1.0) * 100.0 if start else None


def _sector_row(ticker: str, name: str, provider: MarketDataProvider) -> Dict:
    daily = provider.get_bars(ticker, interval="1d", period="1y")
    closes = daily["close"]
    ret_5d = _return_pct(closes, 5)
    ret_21d = _return_pct(closes, 21)
    ret_63d = _return_pct(closes, 63)
    # Momentum blend in raw percent: the month dominates, the quarter
    # confirms, the week breaks ties. Explainable on purpose.
    score = (
        0.5 * (ret_21d or 0.0)
        + 0.3 * (ret_63d or 0.0)
        + 0.2 * (ret_5d or 0.0)
    )
    ma200 = sma(closes, config.SMA_LONG).iloc[-1] if len(closes) >= config.SMA_LONG else None
    price = float(closes.iloc[-1])
    return {
        "ticker": ticker,
        "sector": name,
        "price": price,
        "ret_5d_pct": round(ret_5d, 2) if ret_5d is not None else None,
        "ret_21d_pct": round(ret_21d, 2) if ret_21d is not None else None,
        "ret_63d_pct": round(ret_63d, 2) if ret_63d is not None else None,
        "momentum_score": round(score, 2),
        "rsi_daily": round(float(rsi(closes).iloc[-1]), 1),
        "above_200dma": bool(price > ma200) if ma200 is not None else None,
        "_ret_21d_raw": ret_21d,  # stripped before output
    }


def sector_rotation(provider: MarketDataProvider) -> Dict:
    """Rank the 10 sector ETFs by momentum, with RS vs SPY."""
    bench_daily = provider.get_bars(BENCHMARK, interval="1d", period="1y")
    bench_21d = _return_pct(bench_daily["close"], 21)

    rows: List[Dict] = []
    errors: List[Dict] = []
    for ticker, name in config.SECTOR_ETFS.items():
        try:
            rows.append(_sector_row(ticker, name, provider))
        except Exception as exc:  # one bad ETF must not sink the scan
            errors.append({"ticker": ticker, "error": str(exc)})

    for row in rows:
        raw = row.pop("_ret_21d_raw")
        row["rs_21d_pct"] = (
            round(raw - bench_21d, 2)
            if raw is not None and bench_21d is not None
            else None
        )
    rows.sort(key=lambda r: r["momentum_score"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        if rank <= 3:
            row["label"] = "leading"
        elif rank > len(rows) - 3:
            row["label"] = "lagging"
        else:
            row["label"] = "neutral"
    return {
        "benchmark": BENCHMARK,
        "benchmark_ret_21d_pct": (
            round(bench_21d, 2) if bench_21d is not None else None
        ),
        "sectors": rows,
        "errors": errors,
    }


# ----------------------------------------------------------------------
# full x-ray
# ----------------------------------------------------------------------
def market_xray(provider: MarketDataProvider) -> Dict:
    """Breadth + sectors + one overall posture read."""
    b = breadth(provider)
    s = sector_rotation(provider)
    counts = b["counts"]
    total = counts["total"] or 1
    bull_share = counts["bullish"] / total
    bear_share = counts["bearish"] / total
    if bull_share >= 0.6:
        posture = "risk_on"
    elif bear_share >= 0.6:
        posture = "risk_off"
    else:
        posture = "mixed"
    leading = [r["sector"] for r in s["sectors"] if r.get("label") == "leading"]
    lagging = [r["sector"] for r in s["sectors"] if r.get("label") == "lagging"]
    return {
        "breadth": b,
        "sectors": s,
        "read": {
            "posture": posture,
            "bullish_share_pct": round(bull_share * 100, 1),
            "bearish_share_pct": round(bear_share * 100, 1),
            "pct_above_200dma": counts["pct_above_200dma"],
            "leading_sectors": leading,
            "lagging_sectors": lagging,
        },
    }
