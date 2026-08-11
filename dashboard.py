from flask import Flask, jsonify, render_template_string, request
import json
import os
import subprocess
import psutil
from datetime import datetime
from coinbase_client import get_btc_price

app = Flask(__name__)

STATE_FILE = "logs/bot_state.json"
TRADES_FILE = "logs/trades.json"
CONFIG_FILE = "config_live.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "balance_usd": 1000.0,
        "bags": [],
        "wins": 0,
        "losses": 0,
        "last_saved": "Never"
    }

def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, "r") as f:
            trades = json.load(f)
            return list(reversed(trades))
    return []

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "take_profit_pct": 0.03,
        "stop_loss_pct": 0.06,
        "trigger_drop_pct": 0.03,
        "trade_size_usd": 200,
        "max_bags": 3,
        "dca_drop_pct": 0.02,
        "paper_trading": True
    }

def is_bot_running():
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('paper_trade.py' in c for c in cmdline):
                    return True
        except:
            pass
    return False

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Crypto Bot Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #050a0e;
            --bg2: #0a1520;
            --bg3: #0f1f2e;
            --green: #00ff88;
            --red: #ff3355;
            --yellow: #ffd700;
            --blue: #00aaff;
            --text: #c8d8e8;
            --text-dim: #5a7a8a;
            --border: #1a3a4a;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            background: var(--bg);
            color: var(--text);
            font-family: 'Rajdhani', sans-serif;
            min-height: 100vh;
        }

        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: 
                radial-gradient(ellipse at 20% 20%, rgba(0,255,136,0.03) 0%, transparent 60%),
                radial-gradient(ellipse at 80% 80%, rgba(0,170,255,0.03) 0%, transparent 60%);
            pointer-events: none;
            z-index: 0;
        }

        .scanline {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: repeating-linear-gradient(
                0deg, transparent, transparent 2px,
                rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px
            );
            pointer-events: none;
            z-index: 1;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            position: relative;
            z-index: 2;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 30px;
        }

        .logo {
            font-family: 'Share Tech Mono', monospace;
            font-size: 1.4rem;
            color: var(--green);
            text-shadow: 0 0 20px rgba(0,255,136,0.5);
            letter-spacing: 3px;
        }

        .logo span {
            color: var(--text-dim);
            font-size: 0.8rem;
            display: block;
            letter-spacing: 5px;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .last-update {
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-dim);
        }

        .bot-status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            letter-spacing: 2px;
            text-transform: uppercase;
        }

        .status-dot {
            width: 8px; height: 8px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 10px var(--green);
            animation: pulse 2s infinite;
        }

        .status-dot.offline {
            background: var(--red);
            box-shadow: 0 0 10px var(--red);
            animation: none;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.8); }
        }

        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px; }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
        .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }

        .card {
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 20px;
            position: relative;
            overflow: hidden;
            transition: border-color 0.3s;
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--green), transparent);
            opacity: 0.3;
        }

        .card:hover { border-color: rgba(0,255,136,0.3); }

        .card-label {
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 10px;
        }

        .card-value {
            font-family: 'Share Tech Mono', monospace;
            font-size: 2rem;
            color: var(--green);
            text-shadow: 0 0 20px rgba(0,255,136,0.3);
            line-height: 1;
        }

        .card-value.red { color: var(--red); text-shadow: 0 0 20px rgba(255,51,85,0.3); }
        .card-value.blue { color: var(--blue); text-shadow: 0 0 20px rgba(0,170,255,0.3); }

        .card-sub {
            font-size: 0.75rem;
            color: var(--text-dim);
            margin-top: 6px;
            font-family: 'Share Tech Mono', monospace;
        }

        .btc-card { grid-column: span 2; }

        .btc-price {
            font-family: 'Share Tech Mono', monospace;
            font-size: 3.5rem;
            color: var(--green);
            text-shadow: 0 0 30px rgba(0,255,136,0.4);
            line-height: 1;
        }

        /* Bags */
        .bags-card { grid-column: span 2; }

        .bag-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 12px;
            background: var(--bg3);
            border-radius: 3px;
            border: 1px solid var(--border);
            margin-bottom: 8px;
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.8rem;
        }

        .bag-item:last-child { margin-bottom: 0; }

        .bag-label { color: var(--text-dim); }
        .bag-entry { color: var(--text); }
        .bag-change-pos { color: var(--green); }
        .bag-change-neg { color: var(--red); }

        .no-bags {
            text-align: center;
            padding: 20px;
            color: var(--text-dim);
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.8rem;
            letter-spacing: 2px;
        }

        /* Controls */
        .btn-group { display: flex; gap: 12px; margin-bottom: 12px; }

        .btn {
            flex: 1;
            padding: 12px;
            border: none;
            border-radius: 3px;
            font-family: 'Rajdhani', sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 3px;
            text-transform: uppercase;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-start {
            background: rgba(0,255,136,0.1);
            border: 1px solid var(--green);
            color: var(--green);
        }

        .btn-start:hover { background: rgba(0,255,136,0.2); box-shadow: 0 0 20px rgba(0,255,136,0.2); }

        .btn-stop {
            background: rgba(255,51,85,0.1);
            border: 1px solid var(--red);
            color: var(--red);
        }

        .btn-stop:hover { background: rgba(255,51,85,0.2); box-shadow: 0 0 20px rgba(255,51,85,0.2); }

        .btn-dump {
            width: 100%;
            padding: 12px;
            background: rgba(255,215,0,0.1);
            border: 1px solid var(--yellow);
            color: var(--yellow);
            border-radius: 3px;
            font-family: 'Rajdhani', sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 3px;
            text-transform: uppercase;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-dump:hover { background: rgba(255,215,0,0.2); box-shadow: 0 0 20px rgba(255,215,0,0.2); }

        /* Settings */
        .settings-card {
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 20px;
            margin-bottom: 16px;
        }

        .settings-title {
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 16px;
        }

        .settings-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 16px;
            margin-bottom: 16px;
        }

        .setting-item label {
            display: block;
            font-size: 0.65rem;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 6px;
        }

        .setting-item input {
            width: 100%;
            background: var(--bg3);
            border: 1px solid var(--border);
            border-radius: 3px;
            padding: 8px 12px;
            color: var(--green);
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.2s;
        }

        .setting-item input:focus { border-color: var(--green); }

        .btn-save {
            padding: 10px 24px;
            background: rgba(0,255,136,0.1);
            border: 1px solid var(--green);
            color: var(--green);
            border-radius: 3px;
            font-family: 'Rajdhani', sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 3px;
            text-transform: uppercase;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-save:hover { background: rgba(0,255,136,0.2); }

        /* Stats */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-top: 12px;
        }

        .stat-item {
            text-align: center;
            padding: 12px;
            background: var(--bg3);
            border-radius: 3px;
            border: 1px solid var(--border);
        }

        .stat-value {
            font-family: 'Share Tech Mono', monospace;
            font-size: 1.4rem;
            color: var(--green);
        }

        .stat-label {
            font-size: 0.65rem;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-top: 4px;
        }

        /* Trade History */
        .trades-card {
            background: var(--bg2);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 20px;
        }

        .trades-title {
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 16px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.8rem;
        }

        th {
            text-align: left;
            padding: 8px 12px;
            font-size: 0.65rem;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-dim);
            border-bottom: 1px solid var(--border);
        }

        td {
            padding: 10px 12px;
            border-bottom: 1px solid rgba(26,58,74,0.5);
            color: var(--text);
        }

        tr:last-child td { border-bottom: none; }
        tr:hover td { background: rgba(0,255,136,0.02); }

        .trade-buy { color: var(--green); }
        .trade-sell { color: var(--blue); }
        .pnl-positive { color: var(--green); }
        .pnl-negative { color: var(--red); }

        .no-trades {
            text-align: center;
            padding: 40px;
            color: var(--text-dim);
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.8rem;
            letter-spacing: 2px;
        }

        /* Alert */
        .alert {
            padding: 12px 16px;
            border-radius: 3px;
            font-size: 0.8rem;
            font-weight: 600;
            letter-spacing: 1px;
            margin-bottom: 16px;
            display: none;
        }

        .alert.success { background: rgba(0,255,136,0.1); border: 1px solid var(--green); color: var(--green); display: block; }
        .alert.error { background: rgba(255,51,85,0.1); border: 1px solid var(--red); color: var(--red); display: block; }

        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.8);
            z-index: 100;
            justify-content: center;
            align-items: center;
        }

        .modal-overlay.active { display: flex; }

        .modal {
            background: var(--bg2);
            border: 1px solid var(--yellow);
            border-radius: 4px;
            padding: 30px;
            max-width: 400px;
            width: 90%;
            text-align: center;
        }

        .modal-title {
            font-size: 1.1rem;
            font-weight: 700;
            letter-spacing: 3px;
            color: var(--yellow);
            margin-bottom: 12px;
        }

        .modal-body {
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.85rem;
            color: var(--text);
            margin-bottom: 24px;
            line-height: 1.6;
        }

        .modal-pnl { font-size: 1.2rem; margin: 12px 0; }

        .modal-buttons { display: flex; gap: 12px; }

        .btn-cancel {
            flex: 1; padding: 12px;
            background: rgba(90,122,138,0.2);
            border: 1px solid var(--text-dim);
            color: var(--text-dim);
            border-radius: 3px;
            font-family: 'Rajdhani', sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            cursor: pointer;
        }

        .btn-confirm-dump {
            flex: 1; padding: 12px;
            background: rgba(255,215,0,0.1);
            border: 1px solid var(--yellow);
            color: var(--yellow);
            border-radius: 3px;
            font-family: 'Rajdhani', sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            cursor: pointer;
        }

        footer {
            text-align: center;
            padding: 20px 0;
            color: var(--text-dim);
            font-family: 'Share Tech Mono', monospace;
            font-size: 0.7rem;
            letter-spacing: 2px;
            border-top: 1px solid var(--border);
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="scanline"></div>

    <!-- Dump Confirmation Modal -->
    <div class="modal-overlay" id="dumpModal">
        <div class="modal">
            <div class="modal-title">CONFIRM DUMP ALL BAGS</div>
            <div class="modal-body">
                This will immediately sell all open positions at market price.
                <div class="modal-pnl" id="modalPnl">--</div>
            </div>
            <div class="modal-buttons">
                <button class="btn-cancel" onclick="closeDumpModal()">Cancel</button>
                <button class="btn-confirm-dump" onclick="confirmDump()">Yes, Sell Everything</button>
            </div>
        </div>
    </div>

    <div class="container">
        <header>
            <div class="logo">
                CRYPTO-BOT
                <span>TRADING DASHBOARD v2.0</span>
            </div>
            <div class="header-right">
                <div class="last-update" id="lastUpdate">UPDATING...</div>
                <div class="bot-status">
                    <div class="status-dot" id="statusDot"></div>
                    <span id="statusText">LOADING</span>
                </div>
            </div>
        </header>

        <div id="alert" class="alert"></div>

        <!-- Top Stats -->
        <div class="grid">
            <div class="card btc-card">
                <div class="card-label">BTC / USD</div>
                <div class="btc-price" id="btcPrice">--</div>
                <div class="card-sub">LIVE PRICE</div>
            </div>

            <div class="card bags-card">
                <div class="card-label">Active Bags <span id="bagCount" style="color:var(--green)">0/3</span></div>
                <div id="bagsContent">
                    <div class="no-bags">WATCHING — NO ACTIVE POSITIONS</div>
                </div>
            </div>

            <div class="card">
                <div class="card-label">Total P&L</div>
                <div class="card-value" id="totalPnl">$0.00</div>
                <div class="card-sub" id="pnlBase">FROM $1,000.00</div>
            </div>

            <div class="card">
                <div class="card-label">USD Balance</div>
                <div class="card-value blue" id="usdBalance">$1,000.00</div>
                <div class="card-sub">AVAILABLE</div>
            </div>
        </div>

        <!-- Performance + Controls -->
        <div class="grid-2">
            <div class="card">
                <div class="card-label">Performance</div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="winRate">0%</div>
                        <div class="stat-label">Win Rate</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="totalWins">0</div>
                        <div class="stat-label">Wins</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="totalLosses">0</div>
                        <div class="stat-label">Losses</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-label">Bot Controls</div>
                <div class="btn-group">
                    <button class="btn btn-start" onclick="controlBot('start')">&#9654; Start Bot</button>
                    <button class="btn btn-stop" onclick="controlBot('stop')">&#9632; Stop Bot</button>
                </div>
                <button class="btn-dump" onclick="showDumpModal()">&#9888; Dump All Bags</button>
                <div style="margin-top: 12px; font-size: 0.75rem; color: var(--text-dim); font-family: 'Share Tech Mono', monospace;">
                    Last saved: <span id="lastSaved">--</span>
                </div>
            </div>
        </div>

        <!-- Live Settings -->
        <div class="settings-card">
            <div class="settings-title">Live Settings</div>
            <div class="settings-grid">
                <div class="setting-item">
                    <label>Take Profit %</label>
                    <input type="number" id="takeProfitPct" step="0.5" min="1" max="20" placeholder="3">
                </div>
                <div class="setting-item">
                    <label>Stop Loss %</label>
                    <input type="number" id="stopLossPct" step="0.5" min="1" max="20" placeholder="6">
                </div>
                <div class="setting-item">
                    <label>Trigger Drop %</label>
                    <input type="number" id="triggerDropPct" step="0.5" min="0.5" max="20" placeholder="3">
                </div>
                <div class="setting-item">
                    <label>Trade Size ($)</label>
                    <input type="number" id="tradeSizeUsd" step="50" min="50" max="1000" placeholder="200">
                </div>
                <div class="setting-item">
                    <label>Max Bags</label>
                    <input type="number" id="maxBags" step="1" min="1" max="5" placeholder="3">
                </div>
                <div class="setting-item">
                    <label>DCA Drop %</label>
                    <input type="number" id="dcaDropPct" step="0.5" min="1" max="10" placeholder="2">
                </div>
            </div>
            <button class="btn-save" onclick="saveSettings()">&#128190; Save Settings</button>
        </div>

        <!-- Trade History -->
        <div class="trades-card">
            <div class="trades-title">Trade History</div>
            <div id="tradesContent">
                <div class="no-trades">NO TRADES YET</div>
            </div>
        </div>

        <footer>
            CRYPTO-BOT v2.0 &nbsp;|&nbsp; PAPER TRADING MODE &nbsp;|&nbsp;
            AUTO-REFRESH: 30s &nbsp;|&nbsp;
            <span id="footerTime">--</span>
        </footer>
    </div>

    <script>
        let currentBtcPrice = 0;
        let currentBags = [];

        function updateDashboard() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    currentBtcPrice = data.btc_price;
                    currentBags = data.bags || [];

                    document.getElementById('btcPrice').textContent =
                        '$' + data.btc_price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});

                    const dot = document.getElementById('statusDot');
                    const statusText = document.getElementById('statusText');
                    if (data.bot_running) {
                        dot.className = 'status-dot';
                        statusText.textContent = 'BOT RUNNING';
                    } else {
                        dot.className = 'status-dot offline';
                        statusText.textContent = 'BOT STOPPED';
                    }

                    // Bags display
                    const bagsContent = document.getElementById('bagsContent');
                    const bagCount = document.getElementById('bagCount');
                    bagCount.textContent = `${data.bags.length}/${data.config.max_bags}`;

                    if (data.bags.length === 0) {
                        bagsContent.innerHTML = '<div class="no-bags">WATCHING - NO ACTIVE POSITIONS</div>';
                    } else {
                        let html = '';
                        data.bags.forEach((bag, i) => {
                            const change = ((data.btc_price - bag.buy_price) / bag.buy_price * 100).toFixed(2);
                            const changeClass = change >= 0 ? 'bag-change-pos' : 'bag-change-neg';
                            html += `<div class="bag-item">
                                <span class="bag-label">BAG #${i+1}</span>
                                <span class="bag-entry">Entry: $${bag.buy_price.toLocaleString()}</span>
                                <span class="${changeClass}">${change >= 0 ? '+' : ''}${change}%</span>
                                <span class="bag-entry">${bag.btc_held.toFixed(6)} BTC</span>
                            </div>`;
                        });
                        bagsContent.innerHTML = html;
                    }

                    // P&L
                    const totalBtcValue = data.bags.reduce((sum, b) => sum + (b.btc_held * data.btc_price), 0);
                    const totalValue = data.balance_usd + totalBtcValue;
                    const pnl = totalValue - data.starting_balance;
                    const pnlEl = document.getElementById('totalPnl');
                    pnlEl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2);
                    pnlEl.className = 'card-value ' + (pnl >= 0 ? '' : 'red');

                    document.getElementById('usdBalance').textContent =
                        '$' + data.balance_usd.toLocaleString('en-US', {minimumFractionDigits: 2});

                    const total = data.wins + data.losses;
                    const winRate = total > 0 ? ((data.wins / total) * 100).toFixed(0) : 0;
                    document.getElementById('winRate').textContent = winRate + '%';
                    document.getElementById('totalWins').textContent = data.wins;
                    document.getElementById('totalLosses').textContent = data.losses;
                    document.getElementById('lastSaved').textContent = data.last_saved || '--';

                    // Populate settings
                    const cfg = data.config;
                    document.getElementById('takeProfitPct').value = (cfg.take_profit_pct * 100).toFixed(1);
                    document.getElementById('stopLossPct').value = (cfg.stop_loss_pct * 100).toFixed(1);
                    document.getElementById('triggerDropPct').value = (cfg.trigger_drop_pct * 100).toFixed(1);
                    document.getElementById('tradeSizeUsd').value = cfg.trade_size_usd;
                    document.getElementById('maxBags').value = cfg.max_bags;
                    document.getElementById('dcaDropPct').value = (cfg.dca_drop_pct * 100).toFixed(1);

                    const now = new Date().toLocaleTimeString();
                    document.getElementById('lastUpdate').textContent = 'UPDATED: ' + now;
                    document.getElementById('footerTime').textContent = now;
                })
                .catch(err => console.error('Status fetch error:', err));

            fetch('/api/trades')
                .then(r => r.json())
                .then(trades => {
                    const container = document.getElementById('tradesContent');
                    if (trades.length === 0) {
                        container.innerHTML = '<div class="no-trades">NO TRADES YET</div>';
                        return;
                    }
                    let html = `<table><thead><tr>
                        <th>Time</th><th>Action</th><th>Price</th>
                        <th>Amount</th><th>P&L</th><th>Balance</th><th>Reason</th>
                    </tr></thead><tbody>`;
                    trades.forEach(t => {
                        const pnlText = t.pnl !== null ?
                            `<span class="${t.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}">${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}</span>` : '--';
                        html += `<tr>
                            <td>${t.timestamp}</td>
                            <td class="${t.action === 'BUY' ? 'trade-buy' : 'trade-sell'}">${t.action}</td>
                            <td>$${t.price.toLocaleString()}</td>
                            <td>$${t.amount.toFixed(2)}</td>
                            <td>${pnlText}</td>
                            <td>$${t.balance.toFixed(2)}</td>
                            <td>${t.reason}</td>
                        </tr>`;
                    });
                    html += '</tbody></table>';
                    container.innerHTML = html;
                });
        }

        function showDumpModal() {
            const totalBtcValue = currentBags.reduce((sum, b) => sum + (b.btc_held * currentBtcPrice), 0);
            const estimatedPnl = totalBtcValue - (currentBags.length * 200);
            const pnlEl = document.getElementById('modalPnl');
            pnlEl.textContent = `Estimated P&L: ${estimatedPnl >= 0 ? '+' : ''}$${estimatedPnl.toFixed(2)}`;
            pnlEl.style.color = estimatedPnl >= 0 ? 'var(--green)' : 'var(--red)';
            document.getElementById('dumpModal').classList.add('active');
        }

        function closeDumpModal() {
            document.getElementById('dumpModal').classList.remove('active');
        }

        function confirmDump() {
            closeDumpModal();
            fetch('/api/bot/dump', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    showAlert(data.success ? 'success' : 'error', data.message);
                    setTimeout(() => updateDashboard(), 2000);
                });
        }

        function controlBot(action) {
            fetch(`/api/bot/${action}`, {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    showAlert(data.success ? 'success' : 'error', data.message);
                    setTimeout(() => updateDashboard(), 2000);
                });
        }

        function saveSettings() {
            const settings = {
                take_profit_pct: parseFloat(document.getElementById('takeProfitPct').value) / 100,
                stop_loss_pct: parseFloat(document.getElementById('stopLossPct').value) / 100,
                trigger_drop_pct: parseFloat(document.getElementById('triggerDropPct').value) / 100,
                trade_size_usd: parseFloat(document.getElementById('tradeSizeUsd').value),
                max_bags: parseInt(document.getElementById('maxBags').value),
                dca_drop_pct: parseFloat(document.getElementById('dcaDropPct').value) / 100,
                
            };

            fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(settings)
            })
            .then(r => r.json())
            .then(data => showAlert(data.success ? 'success' : 'error', data.message));
        }

        function showAlert(type, message) {
            const alertEl = document.getElementById('alert');
            alertEl.className = 'alert ' + type;
            alertEl.textContent = message;
            setTimeout(() => { alertEl.className = 'alert'; }, 3000);
        }

        updateDashboard();
        setInterval(updateDashboard, 30000);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/status')
def status():
    state = load_state()
    config = load_config()
    try:
        btc_price = get_btc_price()
    except:
        btc_price = 0

    return jsonify({
        "btc_price": btc_price,
        "balance_usd": state.get("balance_usd", 1000),
        "starting_balance": state.get("starting_balance", 1000),
        "bags": state.get("bags", []),
        "wins": state.get("wins", 0),
        "losses": state.get("losses", 0),
        "last_saved": state.get("last_saved", "Never"),
        "bot_running": is_bot_running(),
        "config": config
    })

    

@app.route('/api/trades')
def trades():
    return jsonify(load_trades())

@app.route('/api/settings', methods=['POST'])
def save_settings():
    try:
        settings = request.json
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        return jsonify({"success": True, "message": "Settings saved — takes effect on next cycle"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to save: {e}"})

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    if is_bot_running():
        return jsonify({"success": False, "message": "Bot is already running"})
    try:
        python_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'venv', 'Scripts', 'python.exe'
        )
        subprocess.Popen(
            [python_path, 'paper_trade.py'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        return jsonify({"success": True, "message": "Bot started successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to start: {e}"})

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    stopped = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('paper_trade.py' in c for c in cmdline):
                    proc.terminate()
                    stopped = True
        except:
            pass
    if stopped:
        return jsonify({"success": True, "message": "Bot stopped successfully"})
    return jsonify({"success": False, "message": "Bot was not running"})

@app.route('/api/bot/dump', methods=['POST'])
def dump_bags():
    try:
        state = load_state()
        bags = state.get("bags", [])
        if not bags:
            return jsonify({"success": False, "message": "No bags to dump"})

        # Write a dump signal file that the bot reads
        with open("logs/dump_signal.json", "w") as f:
            json.dump({"dump": True, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f)

        return jsonify({"success": True, "message": f"Dump signal sent — {len(bags)} bag(s) will be sold on next cycle"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed: {e}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)