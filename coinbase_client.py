from coinbase.rest import RESTClient
from config import TRADING_PAIR
import time

client = RESTClient(key_file="cdp_api_key.json")

LIMIT_OFFSET = 0.001       # 0.1% offset for limit orders
ORDER_TIMEOUT = 300        # 5 minutes before fallback to market
POLL_INTERVAL = 30         # Check fill status every 30 seconds

def get_btc_price():
    """Fetch current BTC price"""
    try:
        book = client.get_best_bid_ask(product_ids=[TRADING_PAIR])
        best_ask = float(book.pricebooks[0].asks[0].price)
        best_bid = float(book.pricebooks[0].bids[0].price)
        return (best_ask + best_bid) / 2
    except Exception as e:
        print(f"  ⚠️ Price fetch error: {e}")
        raise

def get_candles(granularity="ONE_HOUR", limit=50):
    """Fetch OHLCV candle data"""
    try:
        end_time = int(time.time())
        granularity_seconds = {
            "ONE_MINUTE": 60,
            "FIVE_MINUTE": 300,
            "FIFTEEN_MINUTE": 900,
            "THIRTY_MINUTE": 1800,
            "ONE_HOUR": 3600,
            "TWO_HOUR": 7200,
            "SIX_HOUR": 21600,
            "ONE_DAY": 86400
        }
        seconds = granularity_seconds.get(granularity, 3600)
        start_time = end_time - (seconds * limit)
        candles = client.get_candles(
            product_id=TRADING_PAIR,
            start=str(start_time),
            end=str(end_time),
            granularity=granularity
        )
        candle_list = sorted(candles.candles, key=lambda x: x.start)
        closes = [float(c.close) for c in candle_list]
        highs = [float(c.high) for c in candle_list]
        lows = [float(c.low) for c in candle_list]
        volumes = [float(c.volume) for c in candle_list]
        return {
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
            "candles": candle_list
        }
    except Exception as e:
        print(f"  ⚠️ Candle fetch error: {e}")
        raise

def get_account_balance():
    """Get account balances"""
    try:
        accounts = client.get_accounts()
        balances = {"USD": 0.0, "BTC": 0.0, "USDC": 0.0}
        for account in accounts.accounts:
            currency = account.currency
            if currency in balances:
                balances[currency] = float(account.available_balance["value"])
        return balances
    except Exception as e:
        print(f"  ⚠️ Balance fetch error: {e}")
        raise

def get_order_status(order_id):
    """Check if an order has been filled"""
    try:
        order = client.get_order(order_id=order_id)
        return order.order.status
    except Exception as e:
        print(f"  ⚠️ Order status check error: {e}")
        return None

def cancel_order(order_id):
    """Cancel an open order"""
    try:
        client.cancel_orders(order_ids=[order_id])
        print(f"  Order {order_id} cancelled")
        return True
    except Exception as e:
        print(f"  ⚠️ Cancel error: {e}")
        return False

def place_market_order(side, amount):
    """Place a market buy or sell order (fallback)"""
    try:
        client_order_id = f"bot_mkt_{int(time.time())}"
        if side == "buy":
            result = client.market_order_buy(
                client_order_id=client_order_id,
                product_id=TRADING_PAIR,
                quote_size=str(round(amount, 2))
            )
        else:
            result = client.market_order_sell(
                client_order_id=client_order_id,
                product_id=TRADING_PAIR,
                base_size=str(round(amount, 8))
            )
        print(f"  Market {side} order placed")
        return result
    except Exception as e:
        print(f"  ⚠️ Market order error: {e}")
        raise

def place_limit_order_with_fallback(side, amount, current_price):
    """
    Place a limit order with 0.1% offset.
    Polls every 30s for fill. Falls back to market order after 5 minutes.
    Returns (fill_price, was_limit) tuple.
    """
    try:
        client_order_id = f"bot_lmt_{int(time.time())}"

        if side == "buy":
            limit_price = round(current_price * (1 - LIMIT_OFFSET), 2)
            print(f"  Placing limit buy at ${limit_price:,.2f} (current: ${current_price:,.2f})")
            result = client.limit_order_gtc_buy(
                client_order_id=client_order_id,
                product_id=TRADING_PAIR,
                base_size=str(round(amount / limit_price, 8)),
                limit_price=str(limit_price)
            )
        else:
            limit_price = round(current_price * (1 + LIMIT_OFFSET), 2)
            print(f"  Placing limit sell at ${limit_price:,.2f} (current: ${current_price:,.2f})")
            result = client.limit_order_gtc_sell(
                client_order_id=client_order_id,
                product_id=TRADING_PAIR,
                base_size=str(round(amount, 8)),
                limit_price=str(limit_price)
            )

        order_id = result.order_id
        print(f"  Limit order placed: {order_id}")

        # Poll for fill
        start_time = time.time()
        while time.time() - start_time < ORDER_TIMEOUT:
            time.sleep(POLL_INTERVAL)
            status = get_order_status(order_id)
            elapsed = int(time.time() - start_time)
            print(f"  Order status: {status} ({elapsed}s elapsed)")

            if status == "FILLED":
                print(f"  ✅ Limit order filled at ${limit_price:,.2f}")
                return limit_price, True

            if status in ("CANCELLED", "EXPIRED", "FAILED"):
                print(f"  ⚠️ Order {status} — falling back to market order")
                break

        # Timeout or bad status — cancel and fall back
        print(f"  ⏱ Limit order timeout — cancelling and placing market order")
        cancel_order(order_id)
        time.sleep(1)

        market_result = place_market_order(side, amount)
        fill_price = current_price  # Best estimate for market fill
        return fill_price, False

    except Exception as e:
        print(f"  ⚠️ Limit order error: {e}")
        print(f"  Falling back to market order")
        market_result = place_market_order(side, amount)
        return current_price, False