"""
Account configuration management for the RisingHub code redemption bot.
"""

import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

from src.utils.file_helpers import load_json_with_comments, save_json
from src.config.validation import validate_full_config


class AccountManager:
    """
    Manages multiple account configurations
    """

    def __init__(self, config_file: str = "accounts.json"):
        """
        Initialize with configuration file path

        Args:
                config_file: Path to the account configuration file
        """
        self.config_file = config_file
        self.config = self._load_config()

        # Create necessary directories
        self._ensure_directories()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load account configuration from JSON file

        Returns:
                The loaded configuration

        Raises:
                SystemExit: If the configuration file is not found or cannot be parsed
        """
        try:
            config = load_json_with_comments(self.config_file)

            # Print this only when called directly from __init__, not from other methods
            if not hasattr(self, "config"):
                print(
                    f"📝 Loaded configuration from {self.config_file} with {len(config.get('accounts', []))} account(s)"
                )

            # Validate configuration
            errors = validate_full_config(config)
            if errors:
                print("❌ Configuration validation errors:")
                for error in errors:
                    print(f"  - {error}")
                print("Please fix the errors in your configuration file.")
                sys.exit(1)

            return config
        except FileNotFoundError:
            print(f"❌ Configuration file not found: {self.config_file}")
            print("Creating a template configuration file...")
            self._create_template_config()
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            sys.exit(1)

    def _create_template_config(self) -> None:
        """
        Create a template configuration file
        """
        template = {
            "accounts": [
                {
                    "username": "your_username",
                    "password": "your_password",
                    "priority_nat_hero": "yournatgunner",
                    "priority_roy_hero": "yourroygunner",
                    "priority_faction": "nat",
                    "heroes": {},  # Will store hero information after first login
                }
            ],
            "settings": {"rate_limit_delay": 2.0, "codes_file": "redemption_codes.txt"},
        }

        save_json(template, self.config_file, use_tabs=True)

        print(f"📝 Created template configuration file at {self.config_file}")
        print(
            "Please edit this file with your account information and run the script again."
        )

    def _ensure_directories(self) -> None:
        """
        Create necessary directories for sessions and logs
        """
        # Create base directories
        Path("sessions").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Create directories for each account
        for account in self.get_accounts():
            username = account.get("username", "unknown")
            Path(f"sessions/{username}").mkdir(exist_ok=True)
            Path(f"logs/{username}").mkdir(exist_ok=True)

    def get_accounts(self) -> List[Dict[str, Any]]:
        """
        Get all configured accounts

        Returns:
                List of account configurations
        """
        return self.config.get("accounts", [])

    def get_settings(self) -> Dict[str, Any]:
        """
        Get global settings

        Returns:
                Dictionary of settings
        """
        return self.config.get("settings", {})

    def get_cookie_file(self, username: str) -> str:
        """
        Get cookie file path for a specific account

        Args:
                username: The username to get the cookie file for

        Returns:
                Path to the cookie file
        """
        return f"sessions/{username}/session_cookies.json"

    def get_log_files(self, username: str) -> Dict[str, str]:
        """
        Get log file paths for a specific account

        Args:
                username: The username to get log files for

        Returns:
                Dictionary of log file paths
        """
        return {
            "success": f"logs/{username}/{username}_redemption_success.csv",
            "failure": f"logs/{username}/{username}_redemption_failure.csv",
            "info": f"logs/{username}/{username}_redemption_info.csv",
        }

    def update_account_heroes(self, username: str, heroes: Dict[str, str]) -> None:
        """
        Update the heroes information for a specific account

        Args:
                username: The username to update heroes for
                heroes: Dictionary mapping hero names to hero IDs
        """
        accounts = self.get_accounts()
        for account in accounts:
            if account.get("username") == username:
                account["heroes"] = heroes
                break

        # Update the config file
        self.config["accounts"] = accounts
        self._save_config()

    def _save_config(self) -> None:
        """
        Save the current configuration to the config file
        """
        # Use tab indentation to match the user's preference
        save_json(self.config, self.config_file, use_tabs=True)

        print(f"📝 Updated configuration saved to {self.config_file}")

    def get_account_heroes(self, username: str) -> Dict[str, str]:
        """
        Get the heroes for a specific account

        Args:
                username: The username to get heroes for

        Returns:
                Dictionary mapping hero names to hero IDs
        """
        accounts = self.get_accounts()

        for account in accounts:
            if account.get("username") == username:
                return account.get("heroes", {})

        return {}
