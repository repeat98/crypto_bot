import pandas as pd
import numpy as np

class RSIThreshold:
    def __init__(self, symbols, rsi_period=14, rsi_low=30, rsi_high=70):
        """
        Initialize RSI Threshold strategy.
        
        Args:
            symbols (list): List of trading symbols
            rsi_period (int): RSI calculation period
            rsi_low (float): RSI oversold threshold
            rsi_high (float): RSI overbought threshold
        """
        self.symbols = symbols
        self.period = rsi_period
        self.low = rsi_low
        self.high = rsi_high
        
    def calculate_rsi(self, prices):
        """Calculate RSI for a price series."""
        deltas = np.diff(prices)
        seed = deltas[:self.period+1]
        up = seed[seed >= 0].sum()/self.period
        down = -seed[seed < 0].sum()/self.period
        
        # Handle division by zero
        if down == 0:
            rs = float('inf')
        else:
            rs = up/down
            
        rsi = np.zeros_like(prices)
        rsi[:self.period] = 100. - 100./(1.+rs)

        for i in range(self.period, len(prices)):
            delta = deltas[i-1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta

            up = (up*(self.period-1) + upval)/self.period
            down = (down*(self.period-1) + downval)/self.period
            
            # Handle division by zero
            if down == 0:
                rs = float('inf')
            else:
                rs = up/down
                
            rsi[i] = 100. - 100./(1.+rs)
            
        return pd.Series(data=rsi, index=prices.index)
        
    def analyze(self, data):
        """
        Analyze price data and generate trading signals.
        
        Args:
            data (pd.DataFrame): Price data with columns ['timestamp', 'symbol', 'close']
            
        Returns:
            pd.DataFrame: Trading signals
        """
        signals = []
        
        for symbol in self.symbols:
            symbol_data = data[data['symbol'] == symbol].sort_index()
            
            # Calculate RSI
            rsi = self.calculate_rsi(symbol_data['close'])
            
            # Generate signals
            signal = pd.Series(index=symbol_data.index, data=np.nan)
            signal[rsi < self.low] = 1  # Buy signal when oversold
            signal[rsi > self.high] = -1  # Sell signal when overbought
            
            # Create signal DataFrame
            signal_df = pd.DataFrame({
                'signal': signal,
                'rsi': rsi,
                'close': symbol_data['close']
            })
            
            signals.append(signal_df)
            
        return pd.concat(signals) 