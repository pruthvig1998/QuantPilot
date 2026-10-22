"""Central configuration for QuantPilot.

All market data is US only. Times are America/New_York (ET).
"""
import os

# Liquid-options watchlist: 12 most liquid names from his daily briefing
# watchlist (briefing tracks 16 incl. DIA, IWM, ^VIX, JPM - those stay in the
# briefing; QuantPilot scores the 12 below for tradable weekly options).
WATCHLIST = [
    "SPY", "QQQ",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
    "TSLA", "AMD", "NFLX", "AVGO",
]

# US sector ETFs for the Market X-Ray module (bullish/bearish breadth by sector)
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
}

# Market hours in America/New_York
MARKET_OPEN_ET = "09:30"
MARKET_CLOSE_ET = "16:00"

# Indicator engine parameters (his playbook)
EMA_FAST = 9
EMA_MID = 20
EMA_SLOW = 21
SMA_LONG = 200
ATR_PERIOD = 14
RSI_PERIOD = 14
REL_VOL_PERIOD = 20
BREAKOUT_SHORT = 20      # 20-day breakout levels
BREAKOUT_LONG = 252      # 52-week breakout levels (252 trading days)
ZONE_LOOKBACK = 20       # bars used to find swing highs/lows for zones
ZONE_ATR_WIDTH = 0.5     # zone half-width as a fraction of ATR

# Probability guardrail: only rank contracts with delta >= this
MIN_DELTA = 0.30

# Market X-Ray (module 3): RSI zone bounds for the breadth counts
XRAY_RSI_OVERBOUGHT = 70.0
XRAY_RSI_OVERSOLD = 30.0

# Probability guardrail math (module 5). The Yahoo chain carries implied
# volatility but NO Greeks, so delta and theta are computed from the IV
# with Black-Scholes and these assumptions. RISK_FREE_RATE is an
# assumption for the model, not a live quote.
RISK_FREE_RATE = 0.043       # roughly the 3-month T-bill, Oct 2026
DIVIDEND_YIELD = 0.0         # ignored at weekly horizons
# Yahoo prints placeholder IVs (0, 1e-5) on stale / premarket quotes;
# anything below this is missing data, not a volatility (measured live
# Oct 22: NFLX 1 DTE chain at 1e-05 gave delta 1.0 and PoP 0%).
MIN_VALID_IV = 0.01
GUARD_MAX_SPREAD_PCT = 0.30  # (ask - bid) / mid above this = untradeable

# IV / event-risk guard (module 6)
IV_RED_FLAG_PERCENTILE = 70.0  # IV rank above this into an event = crush risk
DEFAULT_HOLDING_DAYS = 5       # one trading week: the weekly-options horizon

# GICS sector ETF for each single-name watchlist member (card context
# line, Part C addition 5). Index ETFs are deliberately absent.
SECTOR_OF = {
    "AAPL": "XLK", "MSFT": "XLK", "NVDA": "XLK", "AMD": "XLK", "AVGO": "XLK",
    "AMZN": "XLY", "TSLA": "XLY",
    "META": "XLC", "GOOGL": "XLC", "NFLX": "XLC",
}

# Risk review pass (Part C addition 1): a TRADE card needs at least this
# reward:risk (target distance / stop distance from entry) to clear.
RISK_MIN_REWARD_RISK = 1.0

# Index ETFs on the watchlist: no company earnings of their own, so the
# earnings check reads "not applicable" instead of "unknown".
INDEX_ETFS = ("SPY", "QQQ")

# IV rank from the journal's own daily ATM-IV snapshots (Part C, Oct 22):
# computed once this many distinct days exist, and labeled
# snapshot-based until IV_SNAPSHOT_FULL_DAYS days (a real 52-week range
# needs ~252 trading days; 60 is the floor we call "established").
IV_SNAPSHOT_MIN_DAYS = 20
IV_SNAPSHOT_FULL_DAYS = 60

# Market-wide event calendar, Oct-Dec 2026 (static list).
# FOMC entries are decision days (day 2 of each meeting) from the
# Federal Reserve's 2026 meeting calendar; CPI and Employment Situation
# (NFP) entries are from the BLS release schedules (bls.gov/schedule),
# all 8:30 AM ET. Refresh from those sources before trading on a date.
MARKET_EVENTS = [
    {"date": "2026-10-28", "type": "FOMC", "label": "FOMC rate decision"},
    {"date": "2026-11-06", "type": "NFP", "label": "Employment Situation (NFP)"},
    {"date": "2026-11-10", "type": "CPI", "label": "Consumer Price Index"},
    {"date": "2026-12-04", "type": "NFP", "label": "Employment Situation (NFP)"},
    {"date": "2026-12-09", "type": "FOMC", "label": "FOMC rate decision"},
    {"date": "2026-12-10", "type": "CPI", "label": "Consumer Price Index"},
]

# Liquidity board scoring (module 1). Each component is normalized to
# [-1, +1] (positive = bullish) and blended with these weights; the final
# score is 100 x the blend, so it lands in [-100, +100].
LIQ_WEIGHT_OI = 0.30          # options open-interest bias
LIQ_WEIGHT_OPT_VOL = 0.25     # options volume bias
LIQ_WEIGHT_MOMENTUM = 0.25    # price momentum
LIQ_WEIGHT_RELVOL = 0.20      # relative volume, signed by momentum
LIQ_CHAIN_BAND = 0.15         # only strikes within +/-15% of spot count
LIQ_MOMENTUM_SCALE = 0.03     # blended return that saturates momentum (3%)
LIQ_RELVOL_SATURATION = 2.5   # relative volume that counts as full intensity
LIQ_BULLISH_THRESHOLD = 15.0  # score at/above = bullish
LIQ_BEARISH_THRESHOLD = -15.0  # score at/below = bearish; between = choppy

# Order block detection (module 2)
OB_IMPULSE_PCT = 0.01         # min displacement from the origin candle (1%)
OB_IMPULSE_BARS = 3           # bars allowed for the impulsive leg to break
OB_SWING_WINDOW = 2           # bars each side for a swing high/low
POOL_TOLERANCE = 0.0015       # highs/lows within 0.15% count as "equal"

# Data provider selection: flipped to "zetaris" 2026-10-20 (Zetaris serves
# Yahoo data on the Mac); "yahoo" remains the direct fallback.
DATA_PROVIDER = "zetaris"

# Agent core (Day 3 drop: packet, debate loop, trade cards, journal).
# Trade-card contract selection uses the signals bot's battle-tested
# filter values (delta band around 0.35, spread, volume, OI, DTE
# window), expressed as checks on every card (module 7).
ACCOUNT_SIZE_USD = 10000.0        # paper account the 1% risk rule sizes on
AGENT_RISK_PCT = 0.01             # risk per card: contracts = risk$ / (stop distance x 100)
CARD_TARGET_DELTA = 0.35          # signals-bot band center for |delta|
CARD_DELTA_TOLERANCE = 0.10       # |delta| within +/- this of target = in band
CARD_MAX_SPREAD_PCT = 20.0        # selection filter: spread <= 20% of premium
CARD_MIN_OPTION_VOLUME = 50       # selection filter: contract volume >= 50
CARD_MIN_OPEN_INTEREST = 100     # selection filter: open interest >= 100
CARD_MIN_DTE = 1                  # selection window: 1-7 days to expiry
CARD_MAX_DTE = 7
CARD_CANDIDATES_PER_PACKET = 3    # ranked guardrail survivors carried in a packet
CARD_STOP_BUFFER_FRACTION = 0.25  # stop sits this fraction of zone width beyond the zone
# Premium outlay cap (audit repair, Oct 22). The 1% rule sizes off the
# stop distance, but a long option's real worst case is the whole
# premium (a gap through the stop, or holding to expiry). Without this
# cap a tight stop could size a card into most of the account.
CARD_MAX_PREMIUM_PCT = 0.05       # total premium <= 5% of the account

# Self-scoring journal (module 8): SQLite, append-only on the ledger
# model - entries are never rewritten; outcomes are appended later.
JOURNAL_DB_PATH = os.path.expanduser(
    os.environ.get("QUANTPILOT_JOURNAL_DB", "~/workspace/quantpilot/journal.db")
)
CIRCUIT_BREAKER_LOSSES = 2        # module 9: consecutive scored losses that trip it

# Optional insider-pattern context (Oct 20 EDGAR Form 4 scan). A second
# fragmented source for the Track 02 story; absent on the Mac, where the
# packet simply reports it as null - never invented.
INSIDER_PATTERNS_PATH = os.path.expanduser(
    "~/workspace/trading/scanner/insider_patterns.json"
)

# Morning runner (Day 4 drop: scripts/run_morning.py). The runner
# debates the top N board names by |score| each morning.
RUNNER_TOP_N = 3                  # symbols debated per morning run

# AI brain (Power layer): NVIDIA Nemotron via the OpenAI-compatible API.
# Default switched 2026-10-22: nemotron-3-super-120b-a12b 404s on NVIDIA's
# side; ultra-550b is verified working. Env override stays (same name the
# .env and smoke_test.py already use).
NEMOTRON_MODEL = os.environ.get(
    "NEMOTRON_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"
)

# Yahoo Finance endpoints (no API key required)
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
YAHOO_COOKIE_URL = "https://fc.yahoo.com"
YAHOO_CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
YAHOO_OPTIONS_URL = "https://query1.finance.yahoo.com/v7/finance/options/{ticker}"
YAHOO_SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
YAHOO_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
