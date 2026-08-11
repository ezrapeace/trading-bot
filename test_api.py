from coinbase_client import get_btc_price, get_account_balance

print("BTC Price:", get_btc_price())
print("Balances:", get_account_balance())