# Crypto Trading Bot

A sophisticated cryptocurrency trading bot that provides portfolio management, price alerts, and trading signals through Telegram.

## Features

- **Portfolio Management**: Track your cryptocurrency holdings
- **Price Alerts**: Set custom price alerts for your favorite cryptocurrencies
- **Trading Signals**: Get trading advice based on multiple technical indicators
- **Backtesting**: Test trading strategies on historical data
- **Real-time Price Updates**: Get instant price updates for your portfolio
- **Security**: Secure configuration management and rate limiting

## Improvements

The bot has been significantly improved with:

1. **Enhanced Error Handling**
   - Custom exception handling
   - Detailed error logging
   - User-friendly error messages

2. **Improved Architecture**
   - Type hints throughout the codebase
   - Dependency injection
   - Modular design
   - Configuration management

3. **Performance Optimizations**
   - Caching for frequently accessed data
   - Rate limiting for API calls
   - Efficient database operations

4. **Security Enhancements**
   - Environment variable support
   - Input validation
   - Rate limiting for commands
   - Secure configuration management

5. **Testing Infrastructure**
   - Unit tests
   - Integration tests
   - Test coverage reporting

## Setup

1. **Install Dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configuration**
   - Copy `config.yaml` to your working directory
   - Set up your Telegram bot token
   - Configure other settings as needed

3. **Environment Variables**
   - Create a `.env` file with your configuration
   - Required variables:
     ```
     TELEGRAM_BOT_TOKEN=your_bot_token
     ```

4. **Database Setup**
   - The bot will create necessary database files automatically
   - Backups are stored in the configured backup directory

## Usage

1. **Start the Bot**
   ```bash
   python main.py
   ```

2. **Telegram Commands**
   - `/start` - Get started with the bot
   - `/add <SYMBOL> <AMOUNT>` - Add a cryptocurrency to your portfolio
   - `/remove <SYMBOL> <AMOUNT>` - Remove a cryptocurrency from your portfolio
   - `/portfolio` - View your current portfolio
   - `/watch <SYMBOL> <UP|DOWN> <PCT>` - Set a price alert
   - `/advice` - Get trading advice
   - `/backtest` - Run backtesting
   - `/signals` - Get current trading signals
   - `/help` - Show help message

## Development

1. **Running Tests**
   ```bash
   pytest tests/
   ```

2. **Code Style**
   ```bash
   black .
   isort .
   mypy .
   ```

3. **Logging**
   - Logs are stored in the `logs` directory
   - Configure log level in `config.yaml`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Coinbase API for price data
- Python-Telegram-Bot for the Telegram interface
- Pandas for data analysis
- NumPy for numerical computations 