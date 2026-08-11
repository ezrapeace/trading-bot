import os
import json
from dotenv import load_dotenv

load_dotenv()

# Load CDP credentials from JSON file
# rename to cdp_api_key.json and fill in your own credentials
CDP_KEY_FILE = "your_csp_api_key.json"

with open(CDP_KEY_FILE, "r") as f:
    cdp_creds = json.load(f)

# Extract credentials
API_KEY = cdp_creds.get("name")
PRIVATE_KEY = cdp_creds.get("privateKey")

# Trading config
TRADING_PAIR = "BTC-USDC"
PAPER_TRADING = False  # Set to False when you're ready for real money

# Strategy settings
BUY_AMOUNT_USD = 200        # How much to spend per trade
TAKE_PROFIT_PCT = 0.03      # 3% profit target
STOP_LOSS_PCT = 0.06        # 6% stop loss
TRIGGER_DROP_PCT = 0.03     # Buy when price drops this % from 24h high

# Fees
COINBASE_FEE = 0.006        # 0.6% per side (conservative estimate)