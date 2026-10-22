"""Agent tools (plain Python functions, dict in / dict out).

On Oct 22 each function here registers as a Meterless skill via
MeterlessRuntime.register_tool(). Until then they are importable and
testable directly.

Planned tools (build days 2-4):
  get_quote, get_intraday_bars, get_option_chain, compute_indicators,
  detect_order_blocks, score_liquidity, market_xray, check_events,
  build_trade_card, generate_briefing
"""
