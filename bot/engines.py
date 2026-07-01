from typing import Dict, Any

# ─────────────────────────────────────────────────────────────────────────────
#  Entry engine (1-minute only): 1m HA direction + 1m AO + RSI(50) confirm the DIRECTION;
#  then PRICE-VS-15m-OPEN (persistence) + fair_prob_up agreement + odds-below-cap must all
#  pass. See decide_entry below.
# ─────────────────────────────────────────────────────────────────────────────


def _no_trade(reason: str) -> Dict[str, Any]:
    return {"action": "NO_TRADE", "side": None, "phase": "TREND", "strength": "-", "reason": reason}


def decide_entry(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """1m HA direction + 1m AO confirm + RSI(50) confirm the DIRECTION; then the GBM
    fair probability must agree and pay an edge. Everything is 1-minute — no 5m timeframe.

    - 1m HA colour = the direction. Red -> only DOWN, green -> only UP.
    - 1m Awesome Oscillator must match by BAR COLOUR: green = rising bar (diff > 0),
      red = falling/flat (diff <= 0). UP needs AO green, DOWN needs AO red.
    - RSI(14) confirms at the 50 line: >= 50 = uptrend (UP), < 50 = downtrend (DOWN).
    - PERSISTENCE: current price must be on the side's side of the 15m window OPEN —
      UP needs price ABOVE the open, DOWN needs price BELOW (aboveOpen).
    - fair_prob (mcProbUp) must AGREE on the side: the chosen side's fair prob > 0.5.
    - PRICE CAP: the chosen side's Polymarket ask must be BELOW `maxPrice` (default 0.60).

    All gates are EQUAL and MANDATORY; none overrides another.
    """
    ha1 = inputs.get("ha1Color")          # "green" / "red" / None  (1m direction)
    ao1 = inputs.get("ao1")               # "green" / "red" / None  (1m AO confirm)
    p_up = inputs.get("mcProbUp")         # fair_prob_up (GBM, from 1m)
    price_up = inputs.get("priceUp")
    price_down = inputs.get("priceDown")
    max_price = inputs.get("maxPrice", 0.60)

    if p_up is None:
        return _no_trade("missing_model_data")
    if price_up is None or price_down is None:
        return _no_trade("missing_prices")

    # ── DIRECTION (1m HA) ──
    if ha1 not in ("green", "red"):
        return _no_trade("no_1m_trend")

    side = "UP" if ha1 == "green" else "DOWN"
    p = p_up if side == "UP" else (1.0 - p_up)       # fair prob of the chosen side
    price = price_up if side == "UP" else price_down

    # ── 1m AWESOME OSCILLATOR confirmation by BAR COLOUR — REQUIRED ──
    # Standard AO histogram: green = rising bar (diff > 0), red = falling/flat (diff <= 0).
    if ao1 is None:
        return _no_trade("ao_unavailable")
    if side == "UP" and ao1 != "green":
        return _no_trade("ao1_not_green")
    if side == "DOWN" and ao1 != "red":
        return _no_trade("ao1_not_red")

    # ── RSI trend confirmation at the 50 line (>=50 up, <50 down) — REQUIRED ──
    rsi = inputs.get("rsi")
    if rsi is None:
        return _no_trade("rsi_unavailable")
    if side == "UP" and rsi < 50:
        return _no_trade(f"rsi_{rsi:.0f}_not_uptrend")
    if side == "DOWN" and rsi >= 50:
        return _no_trade(f"rsi_{rsi:.0f}_not_downtrend")

    # ── PERSISTENCE: price must be on the right side of the 15m window OPEN ──
    # aboveOpen = current price > the window's (Chainlink) open. UP needs it above,
    # DOWN needs it below — only trade the side that is currently "winning" the bet.
    above_open = inputs.get("aboveOpen")
    if above_open is None:
        return _no_trade("open_unavailable")
    if side == "UP" and not above_open:
        return _no_trade("price_below_open")
    if side == "DOWN" and above_open:
        return _no_trade("price_above_open")

    # ── fair_prob DIRECTION AGREEMENT: model must favour the side the indicators picked ──
    if p <= 0.5:
        return _no_trade(f"fair_{p:.2f}_disagrees")

    # ── PRICE CAP: only enter when the odds are below the cap ──
    if price is None:
        return _no_trade("no_price")
    if price >= max_price:
        return _no_trade(f"price_{price:.2f}_above_{max_price:.2f}")

    strength = "HIGH_CONVICTION" if p >= 0.70 else "STRONG"
    return {
        "action": "ENTER", "side": side, "phase": "TREND", "strength": strength,
        "prob": p, "price": price, "reason": "trend_confirmed"
    }
