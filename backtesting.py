import pandas as pd
import sqlite3
import asyncio
import numpy as np
from strategies.moving_average import MovingAverageCrossover
from strategies.rsi import RSIThreshold
from datetime import datetime, timedelta
import logging

class Backtester:
    def __init__(self, db_path, strategies, lookback_days, portfolio_mgr):
        self.db_path = db_path
        self.strategies = strategies
        self.lookback = lookback_days
        self.last_backtest_time = None
        self.pm = portfolio_mgr

    def get_user_symbols(self):
        """Get all unique symbols held by users"""
        symbols = set()
        for user_id in self.pm.list_users():
            holdings = self.pm.get(user_id)
            if holdings:
                symbols.update(holdings.keys())
        return list(symbols)

    def load_data(self, symbol, interval='1h'):
        """Load price data from database for backtesting"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # First get historical data
                hist_query = """
                SELECT timestamp, open, high, low, close, volume 
                FROM prices 
                WHERE symbol = ? 
                AND timestamp >= datetime('now', '-' || ? || ' days')
                ORDER BY timestamp ASC
                """
                hist_df = pd.read_sql(hist_query, conn, params=[symbol, self.lookback], parse_dates=['timestamp'])
                
                # Then get the latest real-time data
                latest_query = """
                SELECT timestamp, open, high, low, close, volume 
                FROM prices 
                WHERE symbol = ? 
                AND timestamp > (SELECT MAX(timestamp) FROM prices WHERE symbol = ?)
                ORDER BY timestamp ASC
                """
                latest_df = pd.read_sql(latest_query, conn, params=[symbol, symbol], parse_dates=['timestamp'])
                
                # Combine the data, handling empty DataFrames
                if hist_df.empty and latest_df.empty:
                    logging.warning(f"No data found for {symbol}")
                    return pd.DataFrame()
                
                # Initialize empty DataFrame with correct columns
                df = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                # Add data if available, handling empty DataFrames
                if not hist_df.empty:
                    df = pd.concat([df, hist_df], ignore_index=True)
                if not latest_df.empty:
                    df = pd.concat([df, latest_df], ignore_index=True)
                
                # Set timestamp as index
                df = df.set_index('timestamp')
                
                # Resample to hourly if needed
                if interval == '1h':
                    df = df.resample('1h').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    })
                
                # Remove any duplicate timestamps
                df = df[~df.index.duplicated(keep='last')]
                
                # Ensure we have enough data points for analysis
                if len(df) < 50:  # Minimum required for most strategies
                    logging.warning(f"Not enough data points for {symbol} (got {len(df)}, need at least 50)")
                    return pd.DataFrame()
                
                # Ensure all required columns are present
                required_columns = ['open', 'high', 'low', 'close', 'volume']
                for col in required_columns:
                    if col not in df.columns:
                        df[col] = df['close']  # Use close price as fallback
                
                # Add symbol column for strategy analysis
                df['symbol'] = symbol
                
                logging.info(f"Loaded {len(df)} rows of data for {symbol} (historical: {len(hist_df)}, latest: {len(latest_df)})")
                return df
                
        except Exception as e:
            logging.error(f"Error loading data for {symbol}: {e}")
            return pd.DataFrame()

    def calculate_metrics(self, signals, returns):
        """Calculate comprehensive trading metrics"""
        if len(signals) == 0:
            return {
                'win_rate': 0,
                'drawdown': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'annual_return': 0,
                'volatility': 0,
                'sortino_ratio': 0
            }

        # Basic metrics
        win_rate = (signals['signal'] != 0).mean()
        drawdown = (returns[returns < 0].sum() / len(returns)) if len(returns) > 0 else 0
        
        # Calculate maximum drawdown
        cumulative_returns = (1 + returns).cumprod()
        rolling_max = cumulative_returns.expanding().max()
        drawdowns = (cumulative_returns - rolling_max) / rolling_max
        max_drawdown = drawdowns.min()

        # Calculate annualized metrics
        annual_returns = (1 + returns.mean()) ** 252 - 1  # Assuming daily data
        volatility = returns.std() * np.sqrt(252)  # Annualized volatility
        
        # Calculate Sharpe ratio (assuming 0 risk-free rate)
        sharpe_ratio = annual_returns / volatility if volatility != 0 else 0
        
        # Calculate Sortino ratio
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        sortino_ratio = annual_returns / downside_std if downside_std != 0 else 0

        return {
            'win_rate': win_rate,
            'drawdown': drawdown,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'annual_return': annual_returns,
            'volatility': volatility,
            'sortino_ratio': sortino_ratio
        }

    async def run_all(self):
        """Run backtesting on all strategies for user-held symbols"""
        try:
            # Only run backtest if an hour has passed since last run
            now = datetime.now()
            if self.last_backtest_time and (now - self.last_backtest_time) < timedelta(hours=1):
                logging.info("Skipping backtest - too soon since last run")
                return None

            self.last_backtest_time = now
            results = {}
            
            # Get symbols held by users
            user_symbols = self.get_user_symbols()
            if not user_symbols:
                logging.info("No symbols held by users, skipping backtest")
                return None
            
            for strat in self.strategies:
                # Only backtest symbols held by users
                for sym in user_symbols:
                    try:
                        # Run in executor to avoid blocking
                        df = await asyncio.get_event_loop().run_in_executor(None, self.load_data, sym)
                        
                        if df.empty:
                            logging.warning(f"No data available for {sym}, skipping backtest")
                            continue
                            
                        # Split data into historical and latest for analysis
                        hist_cutoff = datetime.now() - timedelta(days=self.lookback)
                        hist_df = df[df.index <= hist_cutoff]
                        latest_df = df[df.index > hist_cutoff]
                        
                        # Run strategy on historical data
                        hist_signals = strat.analyze(hist_df)
                        
                        if hist_signals.empty:
                            logging.warning(f"No historical signals generated for {sym} with {strat.__class__.__name__}")
                            continue
                            
                        # Calculate historical metrics
                        hist_returns = hist_signals['close'].pct_change()
                        hist_metrics = self.calculate_metrics(hist_signals, hist_returns)
                        
                        # Run strategy on latest data
                        latest_signals = strat.analyze(latest_df) if not latest_df.empty else pd.DataFrame()
                        
                        # Only include results if there's a non-HOLD signal
                        last_hist_signal = hist_signals['signal'].iloc[-1] if len(hist_signals) > 0 else 0
                        last_latest_signal = latest_signals['signal'].iloc[-1] if len(latest_signals) > 0 else 0
                        
                        if last_hist_signal != 0 or last_latest_signal != 0:
                            results[(strat.__class__.__name__, sym)] = {
                                'historical': {
                                    **hist_metrics,
                                    'signals': hist_signals,
                                    'last_signal': last_hist_signal,
                                    'last_price': hist_signals['close'].iloc[-1] if len(hist_signals) > 0 else 0
                                },
                                'latest': {
                                    'signals': latest_signals,
                                    'last_signal': last_latest_signal,
                                    'last_price': latest_signals['close'].iloc[-1] if len(latest_signals) > 0 else 0
                                }
                            }
                            logging.info(f"Completed backtest for {sym} with {strat.__class__.__name__}")
                        
                    except Exception as e:
                        logging.error(f"Error running backtest for {sym} with {strat.__class__.__name__}: {e}")
                        continue
                
            return results if results else None
            
        except Exception as e:
            logging.error(f"Error in run_all: {e}")
            return None