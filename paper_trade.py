import time
import json
import os
from datetime import datetime
from strategy import should_buy, should_sell, get_price_history
from coinbase_client import get_btc_price, get_account_balance, place_limit_order_with_fallback
from config import COINBASE_FEE, PAPER_TRADING, TRADING_PAIR

STATE_FILE = "logs/bot_state.json"
CONFIG_FILE = "config_live.json"
SELL_INTERVAL = 60    # Check sells every 60 seconds
BUY_INTERVAL = 300    # Check buys every 5 minutes
LIMIT_FEE = 0.004     # 0.4% round trip for limit orders (vs 1.2% market)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "take_profit_pct": 0.03,
        "stop_loss_pct": 0.06,
        "trigger_drop_pct": 0.025,
        "trade_size_usd": 200,
        "max_bags": 3,
        "dca_drop_pct": 0.02,
        "paper_trading": True
    }

class Bag:
    def __init__(self, buy_price, btc_held, amount_spent):
        self.buy_price = buy_price
        self.btc_held = btc_held
        self.amount_spent = amount_spent
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self):
        return {
            "buy_price": self.buy_price,
            "btc_held": self.btc_held,
            "amount_spent": self.amount_spent,
            "timestamp": self.timestamp
        }

    @staticmethod
    def from_dict(d):
        bag = Bag(d["buy_price"], d["btc_held"], d["amount_spent"])
        bag.timestamp = d["timestamp"]
        return bag

class PaperTrader:
    def __init__(self, starting_balance=1000):
        self.starting_balance = starting_balance
        self.wins = 0
        self.losses = 0
        self.trade_log = []
        self.bags = []
        self.last_sell_price = None

        if os.path.exists(STATE_FILE):
            self.load_state()
            print("Restored previous state from disk")
        else:
            if not PAPER_TRADING:
                try:
                    balances = get_account_balance()
                    currency = "USDC" if "USDC" in TRADING_PAIR else "USD"
                    self.balance_usd = balances.get(currency, starting_balance)
                    self.starting_balance = self.balance_usd
                    print(f"  Live balance from Coinbase: ${self.balance_usd:,.2f} {currency}")
                except Exception as e:
                    print(f"  Could not fetch live balance: {e}")
                    self.balance_usd = starting_balance
            else:
                self.balance_usd = starting_balance
            print("Starting fresh - no previous state found")

    def save_state(self):
        state = {
            "balance_usd": self.balance_usd,
            "starting_balance": self.starting_balance,
            "wins": self.wins,
            "losses": self.losses,
            "last_sell_price": self.last_sell_price,
            "bags": [b.to_dict() for b in self.bags],
            "last_saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        self.balance_usd = state["balance_usd"]
        self.starting_balance = state.get("starting_balance", state["balance_usd"])
        self.wins = state["wins"]
        self.losses = state["losses"]
        self.last_sell_price = state.get("last_sell_price")
        self.bags = [Bag.from_dict(b) for b in state.get("bags", [])]

        print(f"  Balance: ${self.balance_usd:,.2f}")
        print(f"  Active Bags: {len(self.bags)}")
        print(f"  Wins/Losses: {self.wins}W / {self.losses}L")

        if os.path.exists("logs/trades.json"):
            with open("logs/trades.json", "r") as f:
                self.trade_log = json.load(f)

    def log_trade(self, action, price, amount, reason, pnl=None, order_type="limit"):
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "price": price,
            "amount": amount,
            "reason": reason,
            "pnl": pnl,
            "order_type": order_type,
            "balance": self.balance_usd
        }
        self.trade_log.append(entry)
        with open("logs/trades.json", "w") as f:
            json.dump(self.trade_log, f, indent=2)
        print(f"\n{'='*50}")
        print(f"  {action.upper()} [{order_type.upper()}] | {entry['timestamp']}")
        print(f"  Price: ${price:,.2f}")
        print(f"  Reason: {reason}")
        if pnl is not None:
            print(f"  P&L: ${pnl:,.2f}")
        print(f"  Balance: ${self.balance_usd:,.2f}")
        print(f"{'='*50}\n")

    def buy(self, price, config):
        trade_size = config["trade_size_usd"]

        if trade_size > self.balance_usd:
            print("  Insufficient balance to buy")
            return False

        if not PAPER_TRADING:
            try:
                fill_price, was_limit = place_limit_order_with_fallback("buy", trade_size, price)
                order_type = "limit" if was_limit else "market"
                fee_rate = LIMIT_FEE / 2 if was_limit else COINBASE_FEE
                fee = trade_size * fee_rate
                btc_held = (trade_size - fee) / fill_price
                actual_price = fill_price
            except Exception as e:
                print(f"  Order failed: {e}")
                return False
        else:
            # Paper trading — simulate limit fill at 0.1% below current price
            order_type = "limit"
            fee_rate = LIMIT_FEE / 2
            fee = trade_size * fee_rate
            actual_price = round(price * 0.999, 2)
            btc_held = (trade_size - fee) / actual_price

        actual_spend = trade_size + (trade_size * fee_rate)
        self.balance_usd -= actual_spend
        bag = Bag(actual_price, btc_held, trade_size)
        self.bags.append(bag)

        self.log_trade("BUY", actual_price, trade_size,
                      f"Bag #{len(self.bags)} | Bought {btc_held:.6f} BTC",
                      order_type=order_type)
        self.save_state()
        return True

    def sell_bag(self, bag, price, reason):
        order_type = "limit"

        if not PAPER_TRADING:
            try:
                fill_price, was_limit = place_limit_order_with_fallback("sell", bag.btc_held, price)
                order_type = "limit" if was_limit else "market"
                fee_rate = LIMIT_FEE / 2 if was_limit else COINBASE_FEE
                actual_price = fill_price
            except Exception as e:
                print(f"  Sell order failed: {e}")
                return 0
        else:
            # Paper trading — simulate limit fill at 0.1% above current price
            fee_rate = LIMIT_FEE / 2
            actual_price = round(price * 1.001, 2)

        gross = bag.btc_held * actual_price
        fee = gross * fee_rate
        net = gross - fee
        pnl = net - bag.amount_spent
        self.balance_usd += net

        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1

        self.last_sell_price = actual_price
        self.log_trade("SELL", actual_price, net, reason, pnl, order_type=order_type)
        return pnl

    def dump_all_bags(self, price):
        """Force sell all bags — uses market orders for speed"""
        if not self.bags:
            return False
        total_pnl = 0
        for bag in self.bags[:]:
            # Dump always uses market orders — speed matters more than fees here
            if not PAPER_TRADING:
                try:
                    from coinbase_client import place_market_order
                    place_market_order("sell", bag.btc_held)
                except Exception as e:
                    print(f"  Dump sell failed: {e}")
                    continue
            gross = bag.btc_held * price
            fee = gross * COINBASE_FEE
            net = gross - fee
            pnl = net - bag.amount_spent
            self.balance_usd += net
            if pnl > 0:
                self.wins += 1
            else:
                self.losses += 1
            self.last_sell_price = price
            self.log_trade("SELL", price, net, "Manual dump all bags", pnl, order_type="market")
            total_pnl += pnl
        self.bags = []
        self.save_state()
        print(f"\n  DUMPED ALL BAGS | Total P&L: ${total_pnl:.2f}")
        return True

    def should_add_bag(self, current_price, config):
        if not self.bags:
            return False
        if len(self.bags) >= config["max_bags"]:
            return False
        lowest_buy = min(b.buy_price for b in self.bags)
        dca_threshold = lowest_buy * (1 - config["dca_drop_pct"])
        if current_price <= dca_threshold:
            print(f"  DCA trigger: price ${current_price:,.2f} "
                  f"dropped {config['dca_drop_pct']*100}% below "
                  f"lowest bag at ${lowest_buy:,.2f}")
            return True
        return False

    def print_status(self, current_price):
        config = load_config()
        total_btc = sum(b.btc_held for b in self.bags)
        total_btc_value = total_btc * current_price
        total_value = self.balance_usd + total_btc_value
        pnl_total = total_value - self.starting_balance
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades * 100) if total_trades > 0 else 0
        mode = "LIVE" if not PAPER_TRADING else "PAPER"

        print(f"\n--- STATUS | {datetime.now().strftime('%H:%M:%S')} | {mode} ---")
        print(f"  BTC Price:    ${current_price:,.2f}")
        print(f"  Balance:      ${self.balance_usd:,.2f}")
        print(f"  Active Bags:  {len(self.bags)}/{config['max_bags']}")

        for i, bag in enumerate(self.bags):
            change = ((current_price - bag.buy_price) / bag.buy_price) * 100
            print(f"  Bag #{i+1}:      ${bag.buy_price:,.2f} entry | "
                  f"{change:+.2f}% | {bag.btc_held:.6f} BTC")

        print(f"  Total BTC:    {total_btc:.6f} (${total_btc_value:,.2f})")
        print(f"  Total Value:  ${total_value:,.2f}")
        print(f"  Total P&L:    ${pnl_total:,.2f}")
        print(f"  Win Rate:     {win_rate:.1f}% ({self.wins}W / {self.losses}L)")
        print(f"-----------------------------")
        self.save_state()


def run_paper_trader():
    os.makedirs("logs", exist_ok=True)
    mode = "LIVE TRADING" if not PAPER_TRADING else "PAPER TRADING"
    print(f"\nBitcoin DCA Bot Starting...")
    print(f"   Mode: {mode}")
    print(f"   Pair: {TRADING_PAIR}")
    print(f"   Orders: LIMIT (market fallback after 5 min)")
    print(f"   Sell check: every {SELL_INTERVAL}s")
    print(f"   Buy check:  every {BUY_INTERVAL}s\n")

    trader = PaperTrader(starting_balance=1000)

    last_buy_check = 0
    closes, volumes = [], []

    while True:
        try:
            config = load_config()
            current_price = get_btc_price()
            trader.print_status(current_price)

            # --- DUMP SIGNAL ---
            dump_signal_file = "logs/dump_signal.json"
            if os.path.exists(dump_signal_file):
                os.remove(dump_signal_file)
                if trader.bags:
                    print("\n  DUMP SIGNAL RECEIVED — selling all bags")
                    trader.dump_all_bags(current_price)

            # --- SELL CHECK (every 60 seconds) ---
            bags_to_remove = []
            for i, bag in enumerate(trader.bags):
                sell_signal, signal_type, reason = should_sell(
                    bag.buy_price,
                    current_price,
                    config["take_profit_pct"],
                    config["stop_loss_pct"]
                )
                if sell_signal:
                    trader.sell_bag(bag, current_price, reason)
                    bags_to_remove.append(bag)
                else:
                    print(f"  Bag #{i+1}: {reason}")

            for bag in bags_to_remove:
                trader.bags.remove(bag)
            if bags_to_remove:
                trader.save_state()

            # --- BUY CHECK (every 5 minutes) ---
            now = time.time()
            if now - last_buy_check >= BUY_INTERVAL:
                last_buy_check = now
                print("  Fetching candle data...")
                closes, volumes = get_price_history()

                if trader.bags and trader.should_add_bag(current_price, config):
                    trader.buy(current_price, config)
                elif not trader.bags:
                    buy_signal, reason = should_buy(
                        closes,
                        trigger_drop_pct=config["trigger_drop_pct"],
                        last_sell_price=trader.last_sell_price
                    )
                    if buy_signal:
                        trader.buy(current_price, config)
                    else:
                        print(f"  Signal: {reason}")
            else:
                secs_until_buy = int(BUY_INTERVAL - (now - last_buy_check))
                print(f"  Next buy check in {secs_until_buy}s")

            print(f"  Next sell check in {SELL_INTERVAL}s...")
            time.sleep(SELL_INTERVAL)

        except KeyboardInterrupt:
            print("\n\nBot stopped by user")
            trader.save_state()
            print(f"Final Balance: ${trader.balance_usd:,.2f}")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_paper_trader()