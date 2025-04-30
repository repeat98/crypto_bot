import pandas as pd
import numpy as np

class BollingerBands:
    def __init__(self, symbols, period=20, std_dev=2):
        """
        Initialize Bollinger Bands strategy.
        
        Args:
            symbols (list): List of trading symbols
            period (int): Moving average period
            std_dev (float): Number of standard deviations for bands
        """
        self.symbols = symbols
        self.period = period
        self.std_dev = std_dev
        
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
            
            # Calculate middle band (SMA)
            middle_band = symbol_data['close'].rolling(window=self.period).mean()
            
            # Calculate standard deviation
            std = symbol_data['close'].rolling(window=self.period).std()
            
            # Calculate upper and lower bands
            upper_band = middle_band + (std * self.std_dev)
            lower_band = middle_band - (std * self.std_dev)
            
            # Generate signals
            signal = pd.Series(index=symbol_data.index, data=np.nan)
            
            # Buy when price crosses below lower band
            signal[symbol_data['close'] < lower_band] = 1
            
            # Sell when price crosses above upper band
            signal[symbol_data['close'] > upper_band] = -1
            
            # Create signal DataFrame
            signal_df = pd.DataFrame({
                'signal': signal,
                'middle_band': middle_band,
                'upper_band': upper_band,
                'lower_band': lower_band,
                'close': symbol_data['close']
            })
            
            signals.append(signal_df)
            
        return pd.concat(signals) 