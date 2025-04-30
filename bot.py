from typing import Optional, Dict, Any, List, Union, Callable
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class CommandError(Exception):
    """Custom exception for command-related errors"""
    message: str
    user_friendly: bool = True

class CryptoBot:
    def __init__(
        self,
        token: Optional[str],
        portfolio_mgr: 'PortfolioManager',
        alert_mgr: Optional['AlertManager'],
        advice_func: Optional[Callable],
        backtester: Optional['Backtester'] = None,
        poller: Optional['DataPoller'] = None
    ) -> None:
        """
        Initialize the CryptoBot with required components.
        
        Args:
            token: Telegram bot token
            portfolio_mgr: Portfolio manager instance
            alert_mgr: Alert manager instance
            advice_func: Function to get trading advice
            backtester: Backtester instance
            poller: Data poller instance for price updates
        """
        if token:
            self.app = Application.builder().token(token).build()
        else:
            self.app = None

        self.pm = portfolio_mgr
        self.am = alert_mgr
        self.advice_func = advice_func
        self.bt = backtester
        self.poller = poller
        self.logger = logging.getLogger(__name__)

    def setup_handlers(self) -> None:
        """Set up command handlers for the bot"""
        try:
            self.app.add_handler(CommandHandler("start", self.start))
            self.app.add_handler(CommandHandler("add", self.add))
            self.app.add_handler(CommandHandler("remove", self.remove))
            self.app.add_handler(CommandHandler("remove_all", self.remove_all))
            self.app.add_handler(CommandHandler("portfolio", self.portfolio))
            self.app.add_handler(CommandHandler("watch", self.watch))
            self.app.add_handler(CommandHandler("advice", self.advice))
            self.app.add_handler(CommandHandler("backtest", self.backtest))
            self.app.add_handler(CommandHandler("alert", self.alert))
            self.app.add_handler(CommandHandler("help", self.help))
        except Exception as e:
            self.logger.error(f"Error setting up handlers: {e}")
            raise

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle the /start command"""
        try:
            welcome_text = """
🎉 *Welcome to the Crypto Trading Bot!* 🎉

I'm here to help you manage your cryptocurrency portfolio and stay updated with market movements.

*Quick Start Guide:*
1️⃣ Use `/add <SYMBOL> <AMOUNT>` to track your holdings
   Example: `/add BTC-USD 1.5`

2️⃣ Set up price alerts with `/alert <SYMBOL> <UP|DOWN> <PERCENT>`
   Example: `/alert BTC-USD UP 5`

3️⃣ Get trading advice with `/advice`

4️⃣ View your portfolio with `/portfolio`

For a complete list of commands, use `/help`

*Available Symbols:* BTC-USD, ETH-USD, SOL-USD, ADA-USD, DOT-USD, AVAX-USD, MATIC-USD, LINK-USD, UNI-USD, AAVE-USD
"""
            await update.message.reply_text(welcome_text, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Error in start command: {e}")
            await self._handle_error(update, e)

    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Add a holding to the portfolio"""
        try:
            if not update.message:
                raise CommandError("No message in update", user_friendly=False)

            # Get user ID
            user_id = update.effective_user.id
            
            # Parse command arguments
            args = context.args
            if len(args) != 2:
                raise CommandError("Usage: /add <SYMBOL> <AMOUNT>")
            
            sym = args[0].upper()
            try:
                amt = Decimal(args[1])
                if amt <= 0:
                    raise CommandError("Amount must be greater than 0")
            except (ValueError, TypeError):
                raise CommandError("Amount must be a valid number")
            
            # Add to portfolio
            self.pm.add(user_id, sym, amt)
            
            # Send confirmation
            await update.message.reply_text(f"Added {amt} {sym} to your portfolio.")
            
        except CommandError as e:
            await self._handle_command_error(update, e)
        except Exception as e:
            self.logger.error(f"Error in add command: {e}")
            await self._handle_error(update, e)

    async def _handle_command_error(self, update: Update, error: CommandError) -> None:
        """Handle command-specific errors"""
        if error.user_friendly:
            await update.message.reply_text(error.message)
        else:
            self.logger.error(f"Command error: {error.message}")
            await update.message.reply_text("An error occurred. Please try again later.")

    async def _handle_error(self, update: Update, error: Exception) -> None:
        """Handle general errors"""
        self.logger.error(f"Unexpected error: {error}")
        if update.message:
            await update.message.reply_text(
                "An unexpected error occurred. Please try again later."
            )

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user.id
        try:
            sym, amt = context.args[0].upper(), float(context.args[1])
            if self.pm.remove(user, sym, amt):
                await update.message.reply_text(f"Removed {amt} {sym} from your portfolio.")
            else:
                await update.message.reply_text(f"Not enough {sym} in your portfolio.")
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: /remove <SYMBOL> <AMOUNT>")

    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the user's portfolio with current values"""
        try:
            if not update.message:
                raise CommandError("No message in update", user_friendly=False)

            # Get user ID
            user_id = update.effective_user.id
            
            # Get holdings
            holdings = self.pm.get(user_id)
            if not holdings:
                await update.message.reply_text("Your portfolio is empty.\nUse `/add <SYMBOL> <AMOUNT>` to add holdings.")
                return

            # Get current prices and calculate values
            message = "📊 *Your Portfolio*\n\n"
            total_value = 0.0
            
            for symbol, amount in holdings.items():
                try:
                    # Get current price
                    price = await self.poller.get_price(symbol)
                    if price is not None:
                        value = amount * price
                        total_value += value
                        message += f"*{symbol}*\n"
                        message += f"• Amount: {amount}\n"
                        message += f"• Current Price: ${price:.2f}\n"
                        message += f"• Value: ${value:.2f}\n\n"
                    else:
                        message += f"*{symbol}*\n"
                        message += f"• Amount: {amount}\n"
                        message += f"• Current Price: Unavailable\n"
                        message += f"• Value: Unavailable\n\n"
                except Exception as e:
                    self.logger.error(f"Error getting price for {symbol}: {e}")
                    message += f"*{symbol}*\n"
                    message += f"• Amount: {amount}\n"
                    message += f"• Current Price: Error\n"
                    message += f"• Value: Error\n\n"

            # Add total value
            message += f"*Total Portfolio Value:* ${total_value:.2f}"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except CommandError as e:
            await self._handle_command_error(update, e)
        except Exception as e:
            self.logger.error(f"Error in portfolio command: {e}")
            await self._handle_error(update, e)

    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set up a price alert"""
        try:
            # Get user ID and message
            user_id = update.effective_user.id
            if not update.message:
                logging.error("No message in update")
                return
                
            # Parse command arguments
            args = context.args
            if len(args) != 3:
                await update.message.reply_text("Usage: /watch <SYMBOL> <UP|DOWN> <PERCENT>")
                return
                
            sym = args[0].upper()
            direction = args[1].upper()
            pct_str = args[2].replace('%', '')  # Remove % if present
            
            # Validate direction
            if direction not in ['UP', 'DOWN']:
                await update.message.reply_text("Direction must be UP or DOWN")
                return
                
            # Parse percentage - handle both decimal and integer values
            try:
                # Convert to float and round to 2 decimal places
                pct = round(float(pct_str), 2)
                if pct <= 0:
                    await update.message.reply_text("Percentage must be greater than 0")
                    return
            except ValueError:
                await update.message.reply_text("Percentage must be a number")
                return
                
            # Add alert
            self.am.add_alert(user_id, sym, direction == 'UP', pct)
            
            # Send confirmation
            await update.message.reply_text(f"Alert set for {sym} going {direction} {pct}%")
            
        except Exception as e:
            logging.error(f"Error in watch command: {e}")
            if update.message:
                await update.message.reply_text("Error setting alert. Please try again.")

    async def advice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user.id
        if self.advice_func:
            try:
                advice = await self.advice_func(user_id=user)
                if advice:
                    await update.message.reply_text(advice)
                else:
                    await update.message.reply_text("No advice available at this time.")
            except Exception as e:
                logging.error(f"Error getting advice: {e}")
                await update.message.reply_text("Sorry, there was an error getting your advice.")
        else:
            await update.message.reply_text("Trading advice not available.")

    async def backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run backtesting and display results"""
        try:
            if not update.message:
                logging.error("No message in update")
                return

            # Run backtesting
            results = await self.bt.run_all()
            
            if not results:
                await update.message.reply_text("Backtesting results not available yet. Please try again in an hour.")
                return
                
            # Format results
            message = "Backtesting Results:\n\n"
            
            for (strat_name, sym), data in results.items():
                message += f"🔍 {sym} - {strat_name}:\n\n"
                
                # Historical results
                hist = data['historical']
                message += "Historical Performance:\n"
                message += f"  Last Price: ${hist['last_price']:.2f}\n"
                message += f"  Last Signal: {self._get_signal_emoji(hist['last_signal'])}\n"
                message += f"  Win Rate: {hist['win_rate']:.1%}\n"
                message += f"  Annual Return: {hist['annual_return']:.1%}\n"
                message += f"  Sharpe Ratio: {hist['sharpe_ratio']:.2f}\n"
                message += f"  Max Drawdown: {hist['max_drawdown']:.1%}\n"
                message += f"  Volatility: {hist['volatility']:.1%}\n"
                message += f"  Sortino Ratio: {hist['sortino_ratio']:.2f}\n\n"
                
                # Latest results
                latest = data['latest']
                if not latest['signals'].empty:
                    message += "Latest Signals:\n"
                    message += f"  Current Price: ${latest['last_price']:.2f}\n"
                    message += f"  Current Signal: {self._get_signal_emoji(latest['last_signal'])}\n\n"
                
            message += "Signal Legend:\n"
            message += "🟢 BUY - Consider adding to position\n"
            message += "🔴 SELL - Consider reducing position\n"
            message += "🟡 HOLD - Maintain current position\n"
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logging.error(f"Error in backtest command: {e}")
            if update.message:
                await update.message.reply_text("Error running backtest. Please try again later.")

    def _get_signal_emoji(self, signal):
        """Convert signal value to emoji"""
        if signal > 0:
            return "🟢 BUY"
        elif signal < 0:
            return "🔴 SELL"
        else:
            return "🟡 HOLD"

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display help message with all available commands"""
        help_text = """
🤖 *Crypto Trading Bot Help* 🤖

*📊 Portfolio Management*
• `/add <SYMBOL> <AMOUNT>` - Add a cryptocurrency to your portfolio
  Example: `/add BTC-USD 1.5`
• `/remove <SYMBOL> <AMOUNT>` - Remove a cryptocurrency from your portfolio
  Example: `/remove ETH-USD 0.5`
• `/remove_all` - Remove all cryptocurrencies from your portfolio
• `/portfolio` - View your current portfolio holdings and their current values

*📈 Trading Advice*
• `/advice` - Get daily trading advice, portfolio overview, and current trading signals
• `/backtest` - Run backtesting on all strategies to see historical performance

*🔔 Price Alerts*
• `/alert <SYMBOL> <UP|DOWN> <PERCENT>` - Set a price alert
  Example: `/alert BTC-USD UP 5` (alert when price goes up 5%)
  Example: `/alert ETH-USD DOWN 10` (alert when price drops 10%)

*ℹ️ Other Commands*
• `/help` - Show this help message
• `/start` - Start the bot and get welcome message

*💰 Available Symbols*
• BTC-USD (Bitcoin)
• ETH-USD (Ethereum)
• SOL-USD (Solana)
• ADA-USD (Cardano)
• DOT-USD (Polkadot)
• AVAX-USD (Avalanche)
• MATIC-USD (Polygon)
• LINK-USD (Chainlink)
• UNI-USD (Uniswap)
• AAVE-USD (Aave)

*📝 Note*
• All amounts should be positive numbers
• For alerts, the percentage should be a positive number (e.g., 5 for 5%)
• Prices are in USD
• Updates are provided in real-time
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def alert(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set a price alert for a symbol"""
        try:
            if not update.message:
                logging.error("No message in update")
                return

            # Get user ID and message
            user_id = update.effective_user.id
            
            # Parse command arguments
            args = context.args
            if len(args) != 3:
                await update.message.reply_text("Usage: /alert <SYMBOL> <UP|DOWN> <PERCENT>")
                return
                
            sym = args[0].upper()
            direction = args[1].upper()
            pct_str = args[2].replace('%', '')  # Remove % if present
            
            # Validate direction
            if direction not in ['UP', 'DOWN']:
                await update.message.reply_text("Direction must be UP or DOWN")
                return
                
            # Parse percentage - handle both decimal and integer values
            try:
                # Convert to float and round to 2 decimal places
                pct = round(float(pct_str), 2)
                if pct <= 0:
                    await update.message.reply_text("Percentage must be greater than 0")
                    return
            except ValueError:
                await update.message.reply_text("Percentage must be a number")
                return
                
            # Add alert
            self.am.add_alert(user_id, sym, direction == 'UP', pct)
            
            # Send confirmation
            await update.message.reply_text(f"Alert set for {sym} going {direction} {pct}%")
            
        except Exception as e:
            logging.error(f"Error in alert command: {e}")
            if update.message:
                await update.message.reply_text("Error setting alert. Please try again.")

    async def remove_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove all holdings from the user's portfolio"""
        try:
            if not update.message:
                raise CommandError("No message in update", user_friendly=False)

            # Get user ID
            user_id = update.effective_user.id
            
            # Remove all holdings
            self.pm.remove_all(user_id)
            
            # Send confirmation
            await update.message.reply_text("All holdings have been removed from your portfolio.")
            
        except CommandError as e:
            await self._handle_command_error(update, e)
        except Exception as e:
            self.logger.error(f"Error in remove_all command: {e}")
            await self._handle_error(update, e)

    def run(self):
        """Run the bot"""
        application = Application.builder().token(self.token).build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("add", self.add))
        application.add_handler(CommandHandler("remove", self.remove))
        application.add_handler(CommandHandler("portfolio", self.portfolio))
        application.add_handler(CommandHandler("advice", self.advice))
        application.add_handler(CommandHandler("backtest", self.backtest))
        application.add_handler(CommandHandler("help", self.help))
        
        # Add alert handler
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_alert))
        
        # Start the bot
        application.run_polling()