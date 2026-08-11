import numpy as np
from coinbase_client import get_candles, get_btc_price

def get_price_history():
    """Fetch real OHLCV candle data from Coinbase (1-hour candles)"""
    print("  Fetching candle data from Coinbase...")
    data = get_candles(granularity="ONE_HOUR", limit=50)
    closes = data["closes"]
    volumes = data["volumes"]
    print(f"  Got {len(closes)} hourly candles")
    return closes, volumes

def should_buy(prices, trigger_drop_pct=0.03, last_sell_price=None):
    """
    Buy when the current price has dropped trigger_drop_pct% below the
    rolling 24-candle high. Optionally blocked if price is above the
    last sell price (prevents re-buying higher after a sell).
    """
    if len(prices) < 24:
        return False, "Not enough data"

    current_price = prices[-1]
    rolling_high = max(prices[-24:])
    drop_threshold = rolling_high * (1 - trigger_drop_pct)
    drop_pct = (rolling_high - current_price) / rolling_high * 100

    if last_sell_price is not None and current_price >= last_sell_price:
        print(f"  Drop: {drop_pct:.2f}% from high ${rolling_high:,.2f} | "
              f"Current: ${current_price:,.2f} | Blocked: price above last sell ${last_sell_price:,.2f}")
        return False, f"Price above last sell price (${last_sell_price:,.2f})"

    print(f"  Drop: {drop_pct:.2f}% from high ${rolling_high:,.2f} | "
          f"Current: ${current_price:,.2f} | Trigger: -{trigger_drop_pct*100:.1f}%")

    if current_price <= drop_threshold:
        return True, f"Price dropped {drop_pct:.1f}% from 24h high (${rolling_high:,.2f})"

    return False, f"No signal: only {drop_pct:.1f}% drop from high (need -{trigger_drop_pct*100:.1f}%)"

def should_sell(buy_price, current_price, take_profit_pct=0.03, stop_loss_pct=0.06):
    """
    Sell signal logic:
    - Take profit if price rose by target %
    - Stop loss if price dropped by threshold %
    """
    if buy_price is None:
        return False, "no_position", "No position held"

    change_pct = (current_price - buy_price) / buy_price

    if change_pct >= take_profit_pct:
        return True, "take_profit", f"Take profit hit: +{change_pct*100:.2f}%"

    if change_pct <= -stop_loss_pct:
        return True, "stop_loss", f"Stop loss hit: {change_pct*100:.2f}%"

    return False, "holding", f"Holding: {change_pct*100:.2f}% from entry"
