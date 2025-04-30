import pandas as pd
import numpy as np

class MovingAverageCrossover:
    def __init__(self, symbols, short=10, long=50):
        """
        Initialize Moving Average Crossover strategy.
        
        Args:
            symbols (list): List of trading symbols
            short (int): Short moving average period
            long (int): Long moving average period
        """
        self.symbols = symbols
        self.short = short
        self.long = long
        
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
            
            # Calculate moving averages
            short_ma = symbol_data['close'].rolling(window=self.short).mean()
            long_ma = symbol_data['close'].rolling(window=self.long).mean()
            
            # Generate signals
            signal = pd.Series(index=symbol_data.index, data=np.nan)
            signal[short_ma > long_ma] = 1  # Buy signal
            signal[short_ma < long_ma] = -1  # Sell signal
            
            # Create signal DataFrame
            signal_df = pd.DataFrame({
                'signal': signal,
                'short_ma': short_ma,
                'long_ma': long_ma,
                'close': symbol_data['close']
            })
            
            signals.append(signal_df)
            
        return pd.concat(signals) 