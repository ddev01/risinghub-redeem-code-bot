"""
Main entry point for the RisingHub code redemption bot.
"""

import sys
import time
from typing import List
from pathlib import Path

from src.config.account_manager import AccountManager
from src.utils.file_helpers import load_file_lines, create_sample_codes_file
from src.tracking.redeemed_codes_manager import RedeemedCodesManager
from src.redemption.account_processor import AccountProcessor
from src.logging.console import ConsoleLogger


# Hardcoded base URL
BASE_URL = "https://risinghub.net/"


def process_accounts(codes: List[str], base_url: str = BASE_URL, logger=None) -> None:
    """
    Process all configured accounts.

    Args:
        codes: List of codes to redeem
        base_url: Base URL for requests
        logger: Optional console logger
    """
    logger = logger or ConsoleLogger()

    # Load account configurations
    account_manager = AccountManager()
    accounts = account_manager.get_accounts()

    if not accounts:
        logger.error("No accounts configured. Please edit accounts.json and try again.")
        sys.exit(1)

    # Get rate limit delay from settings
    settings = account_manager.get_settings()
    rate_limit_delay = float(settings.get("rate_limit_delay", 2.0))

    # Initialize the redeemed codes manager
    redeemed_codes_manager = RedeemedCodesManager()

    # Process each account
    logger.info(
        f"Processing {len(accounts)} accounts with {len(codes)} redemption codes"
    )

    for i, account in enumerate(accounts):
        logger.section(f"Account {i+1}/{len(accounts)}")

        # Process the account
        processor = AccountProcessor(
            account, base_url, codes, rate_limit_delay, redeemed_codes_manager, logger
        )

        # Process the account and get whether server requests were made
        server_requests_made = processor.process()

        # Add a delay between accounts only if server requests were made AND there are more accounts to process
        if server_requests_made and i < len(accounts) - 1:
            delay = max(
                rate_limit_delay * 2, 5.0
            )  # Use at least 5 seconds between accounts
            logger.wait_message(delay)
            time.sleep(delay)
        elif i < len(accounts) - 1:
            logger.skip_wait_message()

    logger.completion()


def main() -> None:
    """
    Main entry point.
    """
    # Create logger
    logger = ConsoleLogger()

    # Load account configurations
    account_manager = AccountManager()
    settings = account_manager.get_settings()

    # Get codes file path from settings
    codes_file = settings.get("codes_file", "redemption_codes.txt")

    # Check if codes file exists and create it if not
    if not Path(codes_file).exists():
        logger.info(f"Creating sample redemption codes file at {codes_file}")
        create_sample_codes_file(codes_file)

    # Load redemption codes
    codes = load_file_lines(codes_file, ignore_comments=True)

    if not codes:
        logger.warning(f"No redemption codes found in {codes_file}.")
        logger.info(
            "Please add codes to this file following the format: one code per line."
        )
        logger.info("The file has been created. Edit it and run the program again.")
        sys.exit(0)

    # Process all accounts
    process_accounts(codes, BASE_URL, logger)


if __name__ == "__main__":
    main()
