import os
import yaml
from typing import Dict, Any
from pathlib import Path
import logging

class Config:
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
        self.load()

    def load(self) -> None:
        """Load configuration from YAML file and environment variables"""
        try:
            with open(self.config_path, 'r') as f:
                raw_config = f.read()
            
            # Replace environment variables
            config_str = os.path.expandvars(raw_config)
            self.config = yaml.safe_load(config_str)
            
            # Validate required settings
            self._validate_config()
            
            # Create necessary directories
            self._create_directories()
            
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            raise

    def _validate_config(self) -> None:
        """Validate required configuration settings"""
        required_sections = [
            'telegram',
            'database',
            'api',
            'polling',
            'alerts',
            'backtesting',
            'logging',
            'security'
        ]
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required configuration section: {section}")
            
            if section == 'telegram' and not self.config[section].get('token'):
                raise ValueError("Telegram bot token is required")
            
            if section == 'database':
                if not self.config[section].get('portfolio_path'):
                    raise ValueError("Database portfolio path is required")
                if not self.config[section].get('prices_path'):
                    raise ValueError("Database prices path is required")

    def _create_directories(self) -> None:
        """Create necessary directories if they don't exist"""
        directories = [
            Path(self.config['database']['backup_path']),
            Path(self.config['logging']['file_path']).parent
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def get(self, *keys: str, default: Any = None) -> Any:
        """Get configuration value by key path"""
        try:
            value = self.config
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def get_telegram_token(self) -> str:
        """Get Telegram bot token"""
        return self.get('telegram', 'token')

    def get_database_paths(self) -> Dict[str, str]:
        """Get database paths"""
        return {
            'portfolio': self.get('database', 'portfolio_path'),
            'prices': self.get('database', 'prices_path')
        }

    def get_polling_config(self) -> Dict[str, Any]:
        """Get polling configuration"""
        return self.get('polling')

    def get_backtesting_config(self) -> Dict[str, Any]:
        """Get backtesting configuration"""
        return self.get('backtesting')

    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration"""
        return self.get('logging')

    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return self.get('security')

# Create a global config instance
config = Config() 