"""
Account processing functionality for the RisingHub code redemption bot.
"""

import os
import time
from typing import Dict, List, Any, Optional, Tuple, Set

from src.config.account_manager import AccountManager
from src.auth.login_manager import get_authenticated_session
from src.logging.csv_logger import CSVLogger
from src.logging.console import ConsoleLogger
from src.tracking.redeemed_codes_manager import RedeemedCodesManager
from src.redemption.code_redeemer import CodeRedeemer
from src.redemption.hero import HeroManager


class AccountProcessor:
    """
    Processes redemption codes for a single account
    """

    def __init__(
        self,
        account_config: Dict[str, Any],
        base_url: str,
        codes: List[str],
        rate_limit_delay: float,
        redeemed_codes_manager: RedeemedCodesManager,
        logger=None,
    ):
        """
        Initialize the account processor.

        Args:
            account_config: The account configuration
            base_url: The base URL to use
            codes: The list of codes to redeem
            rate_limit_delay: The delay between redemption attempts
            redeemed_codes_manager: The manager for tracking redeemed codes
            logger: Optional console logger
        """
        self.account_config = account_config
        self.base_url = base_url
        self.codes = codes
        self.rate_limit_delay = rate_limit_delay
        self.redeemed_codes_manager = redeemed_codes_manager
        self.logger = logger or ConsoleLogger()

        self.username = account_config.get("username", "")
        self.password = account_config.get("password", "")
        self.made_server_requests = False

        self.account_manager = AccountManager()
        self.hero_manager = HeroManager()

    def validate_account_configuration(self) -> bool:
        """
        Validate the account configuration.

        Returns:
            True if the configuration is valid, False otherwise
        """
        if not all([self.username, self.password]):
            self.logger.error(
                f"Missing required configuration for account {self.username}. Skipping."
            )
            return False

        # Ensure base_url has trailing slash
        if not self.base_url.endswith("/"):
            self.base_url += "/"

        return True

    def filter_redeemed_codes(self) -> List[str]:
        """
        Filter out codes that have already been redeemed by all heroes.

        Returns:
            A list of codes that need to be redeemed
        """
        stored_heroes = self.account_manager.get_account_heroes(self.username)

        if not stored_heroes:
            return self.codes

        hero_count = len(stored_heroes)
        self.logger.info(f"Found {hero_count} heroes in configuration")

        # Filter out codes that have already been redeemed by all heroes
        hero_names = list(stored_heroes.keys())
        unredeemed_codes = []

        for code in self.codes:
            if not self.redeemed_codes_manager.is_fully_redeemed(
                self.username, hero_names, code
            ):
                unredeemed_codes.append(code)

        if not unredeemed_codes:
            self.logger.success(
                "All codes have already been redeemed for all heroes. Skipping."
            )
            return []

        self.logger.info(f"Found {len(unredeemed_codes)} codes that need redemption")
        return unredeemed_codes

    def authenticate_account(self) -> Tuple[bool, Optional[Dict[str, str]]]:
        """
        Authenticate the account and extract hero information.

        Returns:
            A tuple of (success, heroes) where heroes is a dictionary of hero names to IDs
        """
        # Get cookie file path for this account
        cookie_file = self.account_manager.get_cookie_file(self.username)

        # Get authenticated session
        session, response = get_authenticated_session(
            self.base_url, self.username, self.password, cookie_file, self.logger
        )

        self.made_server_requests = True

        if not session:
            self.logger.error(
                f"Failed to authenticate for account {self.username}. Skipping."
            )
            return False, None

        # Create logger with account-specific paths
        log_files = self.account_manager.get_log_files(self.username)
        csv_logger = CSVLogger(
            success_log_file=log_files["success"],
            failure_log_file=log_files["failure"],
            info_log_file=log_files["info"],
            username=self.username,
            redeemed_codes_tracker=self.redeemed_codes_manager,
        )

        # Initialize code redeemer
        redeemer = CodeRedeemer(
            session, self.base_url, self.username, response, self.logger, csv_logger
        )

        # Set priority information
        self.hero_manager.set_priority_heroes(
            priority_nat_hero=self.account_config.get("priority_nat_hero", ""),
            priority_roy_hero=self.account_config.get("priority_roy_hero", ""),
            priority_faction=self.account_config.get("priority_faction", ""),
        )

        # Extract hero information
        heroes = redeemer.extract_hero_ids()
        if not heroes:
            self.logger.error(f"No heroes found for account {self.username}. Skipping.")
            return False, None

        # Store redeemer for later use
        self.redeemer = redeemer

        return True, heroes

    def update_hero_information(self, heroes: Dict[str, str]) -> None:
        """
        Update the hero information in the account configuration.

        Args:
            heroes: Dictionary mapping hero names to hero IDs
        """
        stored_heroes = self.account_manager.get_account_heroes(self.username)

        if heroes != stored_heroes:
            self.logger.info(f"Updating hero information ({len(heroes)} heroes)")
            self.account_manager.update_account_heroes(self.username, heroes)

    def process_unredeemed_codes(self, unredeemed_codes: List[str]) -> None:
        """
        Process unredeemed codes using the priority system.

        Args:
            unredeemed_codes: List of codes to redeem
        """
        # Process each code with rate limiting using priority-based redemption
        self.logger.info(f"Processing {len(unredeemed_codes)} redemption codes")

        for i, code in enumerate(unredeemed_codes):
            self.logger.progress(i + 1, len(unredeemed_codes), f"Code: {code}")
            self.redeemer.redeem_code_with_priority(code)

            # Sleep between redemptions to avoid rate limiting (except after the last one)
            if i < len(unredeemed_codes) - 1 and self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

    def process_heroes_separately(self, unredeemed_codes: List[str]) -> None:
        """
        Process each hero separately with their unredeemed codes.

        Args:
            unredeemed_codes: List of codes to redeem
        """
        # Get the detailed unredeemed codes for each hero
        heroes = self.redeemer.extract_hero_ids()
        unredeemed_codes_by_hero = self.redeemed_codes_manager.get_unredeemed_codes(
            self.username, list(heroes.keys()), unredeemed_codes
        )

        heroes_processed = 0
        codes_processed = 0

        # Process each hero separately with their unredeemed codes
        for hero_name, hero_codes in unredeemed_codes_by_hero.items():
            if not hero_codes:
                continue

            heroes_processed += 1
            hero_id = heroes.get(hero_name)

            if not hero_id:
                self.logger.warning(
                    f"Hero {hero_name} not found in current hero list. Skipping."
                )
                continue

            self.logger.hero_processing(hero_name, len(hero_codes))

            for i, code in enumerate(hero_codes):
                codes_processed += 1
                self.logger.progress(i + 1, len(hero_codes), f"Code: {code}")
                self.redeemer.redeem_code(code, hero_id, hero_name)

                # Sleep between redemptions to avoid rate limiting (except after the last one)
                if i < len(hero_codes) - 1 and self.rate_limit_delay > 0:
                    time.sleep(self.rate_limit_delay)

        self.logger.info(
            f"Processed {codes_processed} redemption attempts across {heroes_processed} heroes"
        )

    def process(self) -> bool:
        """
        Process the account.

        Returns:
            True if any server requests were made, False otherwise
        """
        self.logger.account_section(self.username)

        # Validate account configuration
        if not self.validate_account_configuration():
            return False

        # Filter out codes that have already been redeemed by all heroes
        unredeemed_codes = self.filter_redeemed_codes()
        if not unredeemed_codes:
            return False

        # Authenticate and get hero information
        auth_success, heroes = self.authenticate_account()
        if not auth_success or not heroes:
            return True  # Made server requests even though authentication failed

        # Update hero information
        self.update_hero_information(heroes)

        # Process the unredeemed codes
        stored_heroes = self.account_manager.get_account_heroes(self.username)
        if stored_heroes:
            # If we already had hero information, process each hero separately
            self.process_heroes_separately(unredeemed_codes)
        else:
            # If we don't have hero information, use the priority system
            self.process_unredeemed_codes(unredeemed_codes)

        self.logger.success(f"Redemption process complete for account {self.username}")
        return True
