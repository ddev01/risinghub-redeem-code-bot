"""
Code redemption functionality for RisingHub.
"""

import re
import time
import random
import requests
from typing import Dict, List, Tuple, Optional, Set

from bs4 import BeautifulSoup
from src.utils.http import RequestHandler, HtmlParser
from src.utils.code_tracker import CodeTracker
from src.logging.console import ConsoleLogger


class CodeRedeemer:
    """
    Handles the redemption of promotion codes on RisingHub.
    """

    def __init__(
        self, session: requests.Session, base_url: str, hero_config: Dict, logger=None
    ):
        """
        Initialize the code redeemer
        """
        self.session = session
        self.base_url = base_url
        self.hero_config = hero_config
        self.logger = logger or ConsoleLogger()
        self.token = None
        self.profile_response = None
        self.code_tracker = CodeTracker()

    def fetch_profile_page(self) -> bool:
        """
        Fetch the profile page to get the redemption panel

        Returns:
            True if successful, False otherwise
        """
        redeem_url = f"{self.base_url}profile#redeem-panel"
        self.logger.info(f"Fetching redemption panel from: {redeem_url}")

        self.profile_response = RequestHandler.get(self.session, redeem_url)
        if not self.profile_response:
            self.logger.error("Failed to fetch redemption panel")
            return False

        self.logger.info(
            f"Redemption panel response status: {self.profile_response.status_code}"
        )

        # Extract and parse redemption history from the page
        self._update_redemption_history()

        # Update token for redemption requests
        self.token = HtmlParser.get_token_from_html(self.profile_response.text)
        if not self.token:
            self.logger.error("Failed to extract token from redemption panel")
            return False

        return True

    def _update_redemption_history(self) -> None:
        """
        Parse redemption history from the profile page and update the code tracker
        """
        if not self.profile_response:
            return

        redemption_history = HtmlParser.extract_redemption_history(
            self.profile_response.text
        )
        if redemption_history:
            added_records = self.code_tracker.add_redemption_history(redemption_history)
            if added_records > 0:
                self.logger.info(
                    f"Added {added_records} new redemption records from history"
                )

    def update_hero_list(self) -> None:
        """
        Update the hero information from the profile page
        """
        if not self.profile_response:
            return

        try:
            # Parse hero information from redemption form
            soup = BeautifulSoup(self.profile_response.text, "html.parser")
            select = soup.find("select", {"id": "hero"})

            if not select:
                # Try alternative approach - find by name instead of id
                select = soup.find("select", {"name": "hero"})
                if not select:
                    self.logger.warning("Could not find hero selection dropdown")
                    return

            self.logger.debug(
                f"Found hero select: id={select.get('id')}, name={select.get('name')}"
            )

            # Store hero data with name as key and ID as value
            hero_data = {}
            for option in select.find_all("option"):
                hero_id = option.get("value")
                hero_name = option.text.strip()
                if hero_id and hero_name:
                    # Store with hero name as the key and hero ID as the value
                    hero_data[hero_name] = hero_id
                    self.logger.debug(f"Found hero: {hero_name} (ID: {hero_id})")

            if hero_data:
                self.logger.info(f"Found {len(hero_data)} heroes")
                self.hero_config["heroes"] = hero_data

        except Exception as e:
            self.logger.error(f"Failed to update hero list: {str(e)}")

    def redeem_code(self, code: str, hero_id: str) -> Tuple[bool, str]:
        """
        Redeem a code for a specific hero

        Args:
            code: The code to redeem
            hero_id: The ID of the hero to redeem the code for

        Returns:
            (success, message) where success is True if redemption was successful
            and message contains details about the redemption result
        """
        # Check if we have a valid token
        if not self.token:
            if not self.fetch_profile_page() or not self.token:
                return False, "Failed to obtain redemption token"

        # Get the hero name for debugging
        hero_name = next(
            (
                name
                for name, id in self.hero_config.get("heroes", {}).items()
                if id == hero_id
            ),
            "unknown",
        )
        self.logger.debug(
            f"Attempting to redeem code '{code}' for hero: {hero_name} (ID: {hero_id})"
        )

        # Prepare redemption data
        redeem_url = f"{self.base_url}code-redeem"
        redemption_data = {
            "_token": self.token,
            "code": code,
            "hero": hero_id,  # Using hero ID as extracted from the dropdown
        }

        # Prepare headers
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{self.base_url}profile#redeem-panel",
            "X-Requested-With": "XMLHttpRequest",
        }

        # Log the actual request data
        self.logger.debug(f"Redemption request data: {redemption_data}")

        # Send redemption request
        response = RequestHandler.post(
            self.session, redeem_url, redemption_data, headers
        )
        if not response:
            return False, "Redemption request failed"

        # Parse response JSON
        try:
            result = response.json()
            self.logger.debug(f"Redemption response: {result}")
            success = result.get("success", False)
            message = result.get("message", "Unknown response")

            if success:
                # Try to extract what items were redeemed
                items = []
                if "items" in result:
                    for item in result["items"]:
                        item_name = item.get("name", "")
                        if item_name:
                            items.append(item_name)

                if items:
                    return True, f"Code redeemed for {', '.join(items)}"
                else:
                    return True, "Code redeemed successfully"
            else:
                return False, message

        except Exception as e:
            self.logger.error(f"Failed to parse redemption response: {str(e)}")
            return False, f"Failed to parse response: {str(e)}"

    def process_redemption_codes(self, codes: List[str]) -> int:
        """
        Process a list of redemption codes for all heroes

        Returns:
            Number of successful redemptions
        """
        if not codes:
            return 0

        # Fetch profile page and update hero information
        if not self.fetch_profile_page():
            return 0

        self.update_hero_list()
        heroes = self.hero_config.get("heroes", {})

        if not heroes:
            self.logger.error("No heroes found in configuration")
            return 0

        self.logger.info(f"Found {len(codes)} codes that need redemption")

        successful_redemptions = 0
        total_attempts = 0

        # Process all heroes (name:id pairs)
        for hero_name, hero_id in heroes.items():
            self.logger.emoji(
                "🦸", f"Processing {len(codes)} codes for hero {hero_name}"
            )

            for i, code in enumerate(codes, 1):
                # Skip empty codes
                if not code.strip():
                    continue

                self.logger.emoji("🔑", f"[{i}/{len(codes)}] Code: {code}")

                # Check if already redeemed before making the request
                if self.code_tracker.is_redeemed(code, hero_name):
                    self.logger.info(
                        f"Already redeemed: Code was already used by this hero"
                    )
                    continue

                # Attempt to redeem the code
                success, message = self.redeem_code(code, hero_id)
                total_attempts += 1

                if success:
                    self.logger.success(message)
                    # Track redeemed code with hero name for better readability
                    self.code_tracker.add_redeemed_code(code, hero_name)
                    successful_redemptions += 1
                else:
                    # "Already redeemed" messages are merely informational
                    if "already" in message.lower():
                        self.logger.info(message)
                        # Still track as redeemed if the server says it was already used
                        self.code_tracker.add_redeemed_code(code, hero_name)
                    # "Wrong hero" or other issues are warnings
                    else:
                        self.logger.info(f"Info: {message}")

                # Add a short delay between redemptions
                if i < len(codes):
                    time.sleep(random.uniform(0.5, 1.5))

        self.logger.info(
            f"Processed {total_attempts} redemption attempts across {len(heroes)} heroes"
        )
        return successful_redemptions
