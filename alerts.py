import threading
import datetime
import asyncio
import yfinance as yf
from typing import Dict, List, Tuple
import logging

class AlertManager:
    def __init__(self, bot, portfolio_mgr, config):
        self.bot = bot
        self.pm = portfolio_mgr
        self.default_threshold = config.get('default_threshold_pct', 3)
        self.user_thresholds = {}  # {user_id: {symbol: {'up':3, 'down':5}}}
        self._lock = threading.Lock()
        self.last_signals = {}  # {symbol: {'signal': 'BUY/SELL/HOLD', 'price': float, 'timestamp': datetime}}
        self.price_history = {}  # {symbol: [(timestamp, price), ...]}

    def add_alert(self, user_id, symbol, is_up, pct=None):
        direction = 'up' if is_up else 'down'
        with self._lock:
            if user_id not in self.user_thresholds:
                self.user_thresholds[user_id] = {}
            if symbol not in self.user_thresholds[user_id]:
                self.user_thresholds[user_id][symbol] = {}
            self.user_thresholds[user_id][symbol][direction] = pct if pct is not None else self.default_threshold

    async def check_realtime(self, old_prices: Dict[str, float], new_prices: Dict[str, float]):
        alerts = []
        signals = []
        
        with self._lock:
            # Update price history
            now = datetime.datetime.utcnow()
            for sym, price_data in new_prices.items():
                if sym not in self.price_history:
                    self.price_history[sym] = []
                # Extract the price from the price data dictionary
                price = price_data.get('price', price_data.get('close', 0))
                self.price_history[sym].append((now, price))
                # Keep only last 1000 prices
                if len(self.price_history[sym]) > 1000:
                    self.price_history[sym] = self.price_history[sym][-1000:]

            # Check price alerts
            for uid, ths in self.user_thresholds.items():
                for sym, dirs in ths.items():
                    if sym not in old_prices or sym not in new_prices:
                        continue
                    # Extract prices from the price data dictionaries
                    old_price = old_prices[sym].get('price', old_prices[sym].get('close', 0))
                    new_price = new_prices[sym].get('price', new_prices[sym].get('close', 0))
                    if old_price == 0:  # Avoid division by zero
                        continue
                    change = (new_price - old_price) / old_price * 100
                    if 'up' in dirs and change >= dirs['up']:
                        alerts.append((uid, f"{sym} up {change:.2f}%"))
                    if 'down' in dirs and change <= -dirs['down']:
                        alerts.append((uid, f"{sym} down {change:.2f}%"))

            # Generate trading signals
            for sym, prices in self.price_history.items():
                if len(prices) < 50:  # Need enough data for analysis
                    continue
                
                # Calculate moving averages
                prices_list = [p[1] for p in prices]
                sma20 = sum(prices_list[-20:]) / 20
                sma50 = sum(prices_list[-50:]) / 50
                
                # Calculate RSI
                changes = [prices_list[i] - prices_list[i-1] for i in range(1, len(prices_list))]
                gains = [c for c in changes if c > 0]
                losses = [-c for c in changes if c < 0]
                avg_gain = sum(gains[-14:]) / 14 if gains else 0
                avg_loss = sum(losses[-14:]) / 14 if losses else 0
                rsi = 100 - (100 / (1 + (avg_gain / avg_loss if avg_loss != 0 else float('inf'))))
                
                # Generate signal
                signal = "HOLD"
                if sma20 > sma50 and rsi < 70:  # Golden cross and not overbought
                    signal = "BUY"
                elif sma20 < sma50 and rsi > 30:  # Death cross and not oversold
                    signal = "SELL"
                
                # Only send signal if it's different from last signal
                if sym not in self.last_signals or self.last_signals[sym]['signal'] != signal:
                    current_price = new_prices[sym].get('price', new_prices[sym].get('close', 0))
                    self.last_signals[sym] = {
                        'signal': signal,
                        'price': current_price,
                        'timestamp': now
                    }
                    signals.append((sym, signal, current_price))

        # Send alerts outside the lock
        for uid, msg in alerts:
            await self.bot.send_message(chat_id=uid, text=msg)
            
        # Send signals to users with holdings
        for sym, signal, price in signals:
            for uid in self.pm.list_users():
                holdings = self.pm.get(uid)
                if sym in holdings:
                    await self.bot.send_message(
                        chat_id=uid,
                        text=f"Trading Signal for {sym}:\nSignal: {signal}\nCurrent Price: ${price:.2f}\nYour Holdings: {holdings[sym]}"
                    )

    async def daily_summary(self, user_id=None):
        now = datetime.datetime.utcnow().date()
        users = [user_id] if user_id else self.pm.list_users()
        messages = []
        
        for uid in users:
            ports = self.pm.get(uid)
            if not ports:
                messages.append(
                    "Your portfolio is empty.\n"
                    "Use /add <SYMBOL> <AMOUNT> to add holdings to your portfolio.\n"
                    "For example: /add BTC-USD 0.5"
                )
                continue
                
            # Get current prices
            current_prices = {}
            for sym in ports.keys():
                try:
                    ticker = yf.Ticker(sym)
                    hist = ticker.history(period="1d")
                    if not hist.empty:
                        current_prices[sym] = hist['Close'].iloc[-1]
                except Exception as e:
                    logging.error(f"Error fetching price for {sym}: {e}")
            
            # Build detailed message
            msg = f"Your daily advice for {now}:\n\n"
            total_value = 0
            has_signals = False
            
            for sym, amt in ports.items():
                if sym in current_prices:
                    value = amt * current_prices[sym]
                    total_value += value
                    
                    # Get signal for this symbol
                    signal = self.last_signals.get(sym, {}).get('signal', 'HOLD')
                    
                    # Only show BUY or SELL signals
                    if signal != 'HOLD':
                        has_signals = True
                        signal_emoji = "🟢" if signal == "BUY" else "🔴"
                        msg += f"{signal_emoji} {sym}:\n"
                        msg += f"  Holdings: {amt}\n"
                        msg += f"  Current Price: ${current_prices[sym]:.2f}\n"
                        msg += f"  Value: ${value:.2f}\n"
                        msg += f"  Signal: {signal}\n\n"
            
            if not has_signals:
                msg += "No active trading signals at this time.\n\n"
            
            msg += f"Total Portfolio Value: ${total_value:.2f}\n\n"
            msg += "Signal Legend:\n"
            msg += "🟢 BUY - Consider adding to position\n"
            msg += "🔴 SELL - Consider reducing position\n"
            
            messages.append(msg)
            
        return "\n".join(messages)