import threading
import schedule
import time
import asyncio
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path
from config import config  # Import the global config instance
from data_polling import DataPoller
from backtesting import Backtester
from portfolio import PortfolioManager
from alerts import AlertManager
from bot import CryptoBot
from strategies.moving_average import MovingAverageCrossover
from strategies.rsi import RSIThreshold
from strategies.bollinger_bands import BollingerBands
from telegram.ext import ApplicationBuilder
from telegram import Update

def setup_logging():
    """Configure logging with both file and console handlers"""
    # Create logs directory if it doesn't exist
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Create and configure file handler
    log_file = log_dir / f'crypto_bot_{datetime.now().strftime("%Y%m%d")}.log'
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(file_formatter)
    
    # Create and configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def run_background_tasks(poller, am):
    """Run polling and scheduler in a background thread"""
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(1)

    def run_poller():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(poller.run(am.check_realtime))
        loop.close()

    # Start scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Start poller thread
    poller_thread = threading.Thread(target=run_poller, daemon=True)
    poller_thread.start()

    return scheduler_thread, poller_thread

def main():
    # Set up logging
    logger = setup_logging()
    
    # Get database paths from config
    db_paths = config.get_database_paths()
    
    # Set up DB & modules
    pm = PortfolioManager(db_paths['portfolio'])
    
    # Create bot instance without token
    bot = CryptoBot(None, pm, None, None, None, None)
    
    # Initialize the bot application separately
    application = ApplicationBuilder().token(config.get_telegram_token()).build()
    bot.app = application
    
    # Set up alert manager after bot is initialized
    am = AlertManager(application.bot, pm, config.get('alerts'))
    bot.am = am
    bot.advice_func = am.daily_summary  # Pass the async function directly
    
    # Set up bot with components
    bot.setup_handlers()

    # Initialize backtester with strategies
    strategies = [
        MovingAverageCrossover(config.get('polling', 'symbols'), short=10, long=50),
        RSIThreshold(config.get('polling', 'symbols'), rsi_low=30, rsi_high=70),
        BollingerBands(config.get('polling', 'symbols'), period=20, std_dev=2)
    ]
    bt = Backtester(db_paths['prices'], strategies, config.get('backtesting', 'lookback_days'), pm)
    bot.bt = bt  # Pass backtester to bot

    # Schedule backtests
    schedule.every(config.get('backtesting', 'interval_hours')).hours.do(bt.run_all)

    # Schedule daily summary at e.g. 08:00 UTC
    schedule.every().day.at("08:00").do(am.daily_summary)

    # Initialize data poller with portfolio manager
    poller = DataPoller(db_paths['prices'], pm, config.get_polling_config())
    bot.poller = poller  # Pass poller to bot

    # Start polling in a separate thread
    def run_poller():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(poller.run(am.check_realtime))
    
    poller_thread = threading.Thread(target=run_poller)
    poller_thread.daemon = True
    poller_thread.start()

    try:
        # Run the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
    finally:
        # No need for explicit cleanup as application.run_polling() handles it
        pass

if __name__ == "__main__":
    main()