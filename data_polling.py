import time, logging
import asyncio
import yfinance as yf
import backoff
import sqlite3
from datetime import datetime, timedelta
import threading
from typing import Dict, Optional, Callable, Set
import aiohttp
import pandas as pd
from functools import lru_cache
from ratelimit import limits, sleep_and_retry

class DataPoller:
    def __init__(self, db_path: str, portfolio_mgr: 'PortfolioManager', backoff_config: Dict):
        self.db_path = db_path
        self.pm = portfolio_mgr
        self.backoff_config = backoff_config
        self.logger = logging.getLogger(__name__)
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_poll_time: Dict[str, float] = {}
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = 60  # Cache TTL in seconds
        self.last_prices = {}
        self.interval = 1  # Polling interval in seconds
        self._local = threading.local()
        self._init_db()
        logging.info("Initialized DataPoller")

    def _get_connection(self):
        """Get a thread-local database connection"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path)
        return self._local.conn

    def _init_db(self):
        """Initialize the database for storing price data"""
        try:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                timestamp DATETIME,
                symbol TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY (timestamp, symbol)
            )
            """)
            conn.commit()
            logging.info("Database initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing database: {e}")
            raise

    def store_prices(self, timestamp, data):
        """Store price data in the database"""
        try:
            conn = self._get_connection()
            c = conn.cursor()
            for sym, price_data in data.items():
                c.execute("""
                INSERT INTO prices (timestamp, symbol, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(timestamp, symbol) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume
                """, (
                    timestamp,
                    sym,
                    price_data.get('open', price_data.get('price')),
                    price_data.get('high', price_data.get('price')),
                    price_data.get('low', price_data.get('price')),
                    price_data.get('close', price_data.get('price')),
                    price_data.get('volume', 0)
                ))
            conn.commit()
            logging.debug(f"Stored prices for {len(data)} symbols")
        except Exception as e:
            logging.error(f"Error storing prices: {e}")

    def get_symbols(self) -> Set[str]:
        """Get all unique symbols from user portfolios"""
        symbols = set()
        for user_id in self.pm.list_users():
            holdings = self.pm.get(user_id)
            if holdings:
                symbols.update(holdings.keys())
        return symbols

    def fetch_once(self):
        """Fetch current prices for all symbols"""
        data = {}
        symbols = self.get_symbols()
        
        if not symbols:
            logging.info("No symbols to poll - no users have holdings")
            return data
            
        for sym in symbols:
            try:
                # Remove any $ prefix and ensure correct format
                clean_sym = sym.replace('$', '')
                ticker = yf.Ticker(clean_sym)
                
                # Try different intervals if 1m fails
                intervals = ['1m', '5m', '15m', '1h', '1d']
                hist = None
                
                for interval in intervals:
                    try:
                        hist = ticker.history(period="1d", interval=interval)
                        if not hist.empty:
                            logging.debug(f"Successfully fetched {sym} data with {interval} interval")
                            break
                    except Exception as e:
                        logging.debug(f"Failed to fetch {sym} with {interval} interval: {e}")
                        continue
                
                if hist is not None and not hist.empty:
                    data[sym] = {
                        'price': hist['Close'].iloc[-1],
                        'open': hist['Open'].iloc[-1],
                        'high': hist['High'].iloc[-1],
                        'low': hist['Low'].iloc[-1],
                        'close': hist['Close'].iloc[-1],
                        'volume': hist['Volume'].iloc[-1]
                    }
                    logging.debug(f"Updated price for {sym}: {data[sym]['price']}")
                else:
                    logging.warning(f"No data available for {sym}")
            except Exception as e:
                logging.error(f"Error fetching {sym}: {e}")
                continue

        return data

    async def __aenter__(self):
        """Initialize aiohttp session"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()

    @sleep_and_retry
    @limits(calls=30, period=60)  # 30 calls per minute
    async def _fetch_price(self, symbol: str) -> Optional[float]:
        """Fetch price for a symbol with rate limiting"""
        if not self.session:
            raise RuntimeError("Session not initialized")

        try:
            url = f"https://api.coinbase.com/v2/prices/{symbol}/spot"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data['data']['amount'])
                else:
                    self.logger.error(f"Error fetching price for {symbol}: {response.status}")
                    return None
        except Exception as e:
            self.logger.error(f"Exception fetching price for {symbol}: {e}")
            return None

    @lru_cache(maxsize=100)
    def _get_cached_price(self, symbol: str, timestamp: int) -> Optional[float]:
        """Get cached price if available and not expired"""
        cache_key = f"{symbol}_{timestamp}"
        if cache_key in self._cache:
            cache_data = self._cache[cache_key]
            if time.time() - cache_data['timestamp'] < self._cache_ttl:
                return cache_data['price']
        return None

    def _update_cache(self, symbol: str, price: float):
        """Update price cache"""
        timestamp = int(time.time())
        cache_key = f"{symbol}_{timestamp}"
        self._cache[cache_key] = {
            'price': price,
            'timestamp': time.time()
        }

    @backoff.on_exception(
        backoff.expo,
        (aiohttp.ClientError, asyncio.TimeoutError),
        max_tries=3,
        max_time=30
    )
    async def get_price(self, symbol: str) -> Optional[float]:
        """Get price for a symbol with caching and retry logic"""
        try:
            # Check cache first
            cached_price = self._get_cached_price(symbol, int(time.time()))
            if cached_price is not None:
                return cached_price

            # Fetch new price
            price = await self._fetch_price(symbol)
            if price is not None:
                self._update_cache(symbol, price)
            return price

        except Exception as e:
            self.logger.error(f"Error getting price for {symbol}: {e}")
            return None

    async def run(self, callback: Optional[Callable] = None) -> None:
        """Run the polling loop"""
        async with self:
            while True:
                try:
                    # Get all symbols from portfolio
                    symbols = self.get_symbols()
                    if not symbols:
                        await asyncio.sleep(60)  # Wait if no symbols
                        continue

                    # Fetch prices for all symbols
                    tasks = [self.get_price(symbol) for symbol in symbols]
                    prices = await asyncio.gather(*tasks)

                    # Update database and call callback
                    for symbol, price in zip(symbols, prices):
                        if price is not None:
                            self._update_price_in_db(symbol, price)
                            if callback:
                                await callback(symbol, price)

                    # Sleep for a while before next poll
                    await asyncio.sleep(self.backoff_config.get('interval', 60))

                except Exception as e:
                    self.logger.error(f"Error in polling loop: {e}")
                    await asyncio.sleep(self.backoff_config.get('backoff', 300))

    def _update_price_in_db(self, symbol: str, price: float) -> None:
        """Update price in database"""
        try:
            conn = self._get_connection()
            c = conn.cursor()
            c.execute("""
            INSERT INTO prices (timestamp, symbol, close)
            VALUES (?, ?, ?)
            """, (datetime.now(), symbol, price))
            conn.commit()
        except Exception as e:
            self.logger.error(f"Error updating price in DB for {symbol}: {e}")