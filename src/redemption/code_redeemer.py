"""
Code redemption functionality for the RisingHub code redemption bot.
"""

import json
import requests
from typing import Dict, List, Set, Optional, Union, Tuple, Any

from src.utils.http import RequestHandler, HtmlParser
from src.logging.csv_logger import CSVLogger
from src.logging.console import ConsoleLogger, LogLevel
from src.redemption.hero import HeroManager


class RedemptionResult:
    """
    Represents the result of a code redemption attempt.
    """

    def __init__(
        self,
        success: bool,
        message: str,
        items: Optional[Dict[str, List]] = None,
        potential_items: Optional[Dict[str, List]] = None,
        error_type: Optional[str] = None,
        raw_response: Optional[str] = None,
        response_status: int = 0,
    ):
        """
        Initialize a redemption result.

        Args:
            success: Whether the redemption was successful
            message: A message describing the result
            items: Dictionary of items received (for successful redemptions)
            potential_items: Dictionary of potential items (for wrong hero class)
            error_type: Type of error if unsuccessful
            raw_response: Raw response from the server
            response_status: HTTP status code
        """
        self.success = success
        self.message = message
        self.items = items or {}
        self.potential_items = potential_items or {}
        self.error_type = error_type
        self.raw_response = raw_response
        self.response_status = response_status

    @property
    def is_already_redeemed(self) -> bool:
        """
        Check if the result indicates the code was already redeemed.

        Returns:
            True if the code was already redeemed, False otherwise
        """
        return self.error_type == "already_redeemed"

    @property
    def is_wrong_hero_class(self) -> bool:
        """
        Check if the result indicates the wrong hero class.

        Returns:
            True if the wrong hero class, False otherwise
        """
        return self.error_type == "wrong_hero_class"

    @classmethod
    def success_result(
        cls,
        items: Dict[str, List],
        message: str = "Redemption successful",
        response_status: int = 200,
        raw_response: Optional[str] = None,
    ) -> "RedemptionResult":
        """
        Create a success result.

        Args:
            items: Dictionary of items received
            message: Success message
            response_status: HTTP status code
            raw_response: Raw response from the server

        Returns:
            A RedemptionResult indicating success
        """
        return cls(
            success=True,
            message=message,
            items=items,
            error_type=None,
            raw_response=raw_response,
            response_status=response_status,
        )

    @classmethod
    def already_redeemed_result(
        cls,
        message: str = "Code already redeemed",
        response_status: int = 200,
        raw_response: Optional[str] = None,
    ) -> "RedemptionResult":
        """
        Create an already redeemed result.

        Args:
            message: Error message
            response_status: HTTP status code
            raw_response: Raw response from the server

        Returns:
            A RedemptionResult indicating the code was already redeemed
        """
        return cls(
            success=False,
            message=message,
            error_type="already_redeemed",
            raw_response=raw_response,
            response_status=response_status,
        )

    @classmethod
    def wrong_hero_class_result(
        cls,
        potential_items: Dict[str, List],
        message: str = "Wrong hero class or faction for this code",
        response_status: int = 200,
        raw_response: Optional[str] = None,
    ) -> "RedemptionResult":
        """
        Create a wrong hero class result.

        Args:
            potential_items: Dictionary of potential items
            message: Error message
            response_status: HTTP status code
            raw_response: Raw response from the server

        Returns:
            A RedemptionResult indicating the wrong hero class
        """
        return cls(
            success=False,
            message=message,
            potential_items=potential_items,
            error_type="wrong_hero_class",
            raw_response=raw_response,
            response_status=response_status,
        )

    @classmethod
    def error_result(
        cls,
        error_type: str,
        message: str,
        response_status: int = 0,
        raw_response: Optional[str] = None,
    ) -> "RedemptionResult":
        """
        Create an error result.

        Args:
            error_type: Type of error
            message: Error message
            response_status: HTTP status code
            raw_response: Raw response from the server

        Returns:
            A RedemptionResult indicating an error
        """
        return cls(
            success=False,
            message=message,
            error_type=error_type,
            raw_response=raw_response,
            response_status=response_status,
        )


class CodeRedeemer:
    """
    Handles code redemption functionality
    """

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        username: str,
        response: Optional[requests.Response] = None,
        logger=None,
        csv_logger: Optional[CSVLogger] = None,
    ):
        """
        Initialize with an authenticated session and optional response

        Args:
            session: Authenticated session
            base_url: Base URL for requests
            username: Username of the account
            response: Optional response from the redeem page
            logger: Optional console logger
            csv_logger: Optional CSV logger
        """
        self.session = session
        self.base_url = base_url
        self.username = username
        self.redeem_page_response = response
        self.console = logger or ConsoleLogger()
        self.logger = csv_logger
        self.hero_manager = HeroManager()

        # If we don't have a response yet, get one
        if not self.redeem_page_response:
            self.redeem_page_response = RequestHandler.get(
                self.session, self.base_url + "profile#redeem-panel"
            )

    def extract_token(self) -> Optional[str]:
        """
        Extract the CSRF token from the redeem page

        Returns:
            The CSRF token if found, None otherwise
        """
        if not self.redeem_page_response:
            return None

        return HtmlParser.get_token_from_html(self.redeem_page_response.text)

    def extract_hero_ids(self) -> Dict[str, str]:
        """
        Extract the hero IDs from the redeem page
        
        Returns:
            A dictionary mapping hero names to hero IDs
        """
        if not self.redeem_page_response:
            return {}

        # Extract options from the hero select dropdown
        heroes = HtmlParser.extract_select_options(
            self.redeem_page_response.text, "hero"
        )

        if not heroes:
            self.console.warning("Could not find hero select dropdown")

        # Flip the dictionary to make it name:id instead of id:name
        flipped_heroes = {name: hero_id for hero_id, name in heroes.items()}

        # Update the hero manager with the extracted heroes
        self.hero_manager.add_heroes_from_dict(heroes)

        return flipped_heroes

    def prepare_redemption_request(
        self, code: str, hero_id: str, token: str
    ) -> Tuple[str, Dict[str, str], Dict[str, str]]:
        """
        Prepare the data for a redemption request.

        Args:
            code: The code to redeem
            hero_id: The hero ID to redeem for
            token: The CSRF token

        Returns:
            A tuple of (URL, payload, headers)
        """
        # Prepare URL
        redeem_url = self.base_url + "profile/redeem"

        # Prepare payload
        payload = {"_token": token, "hero": hero_id, "code": code}

        # Prepare headers
        headers = RequestHandler.create_default_headers(self.base_url)

        return redeem_url, payload, headers

    def parse_redemption_response(
        self, response: requests.Response, hero_name: str, hero_id: str, code: str
    ) -> RedemptionResult:
        """
        Parse the response from a redemption request.

        Args:
            response: The response from the server
            hero_name: The name of the hero
            hero_id: The ID of the hero
            code: The code that was redeemed

        Returns:
            A RedemptionResult object
        """
        try:
            result = response.json()

            # Handle successful redemption
            if isinstance(result, list) and len(result) >= 2 and result[0] == "success":
                # Extract items data
                items_data = result[1] if len(result) > 1 else {}

                # Show success message with items
                item_names = []
                for item_id, details in items_data.items():
                    if len(details) >= 3:  # Make sure we have at least the name
                        item_names.append(details[2])

                items_str = ", ".join(item_names) if item_names else "no items"
                self.console.success(f"Code redeemed for {items_str}")

                return RedemptionResult.success_result(
                    items=items_data,
                    response_status=response.status_code,
                    raw_response=str(result),
                )

            # Handle error cases
            elif isinstance(result, list) and len(result) >= 2 and result[0] == "error":
                error_data = result[1]

                # Case 1: Already redeemed code
                if (
                    isinstance(error_data, str)
                    and "can't use this code again" in error_data
                ):
                    self.console.info(
                        "Already redeemed: Code was already used by this hero"
                    )
                    return RedemptionResult.already_redeemed_result(
                        response_status=response.status_code, raw_response=str(result)
                    )

                # Case 2: Wrong hero class/faction but shows potential items
                elif isinstance(error_data, dict):
                    # Extract potential item names from the error
                    potential_items = []
                    for item_id, item_info in error_data.items():
                        if isinstance(item_info, list) and len(item_info) > 0:
                            potential_items.append(item_info[0])
                        else:
                            potential_items.append(f"Item #{item_id}")

                    item_list = ", ".join(potential_items)
                    self.console.warning(
                        f"Wrong hero: Items available ({item_list}) but wrong hero type"
                    )

                    return RedemptionResult.wrong_hero_class_result(
                        potential_items=error_data,
                        response_status=response.status_code,
                        raw_response=str(result),
                    )

                # Case 3: Other error messages
                else:
                    self.console.info(f"Info: {error_data}")
                    return RedemptionResult.error_result(
                        error_type="other_info",
                        message=str(error_data),
                        response_status=response.status_code,
                        raw_response=str(result),
                    )
            else:
                # Unexpected response format
                self.console.error(f"Unexpected response format - {result}")
                return RedemptionResult.error_result(
                    error_type="unexpected_format",
                    message="Unexpected response format",
                    response_status=response.status_code,
                    raw_response=str(result),
                )

        except json.JSONDecodeError:
            # Non-JSON response
            self.console.error("Invalid JSON response")
            return RedemptionResult.error_result(
                error_type="json_error",
                message="Invalid JSON response",
                response_status=response.status_code,
                raw_response=response.text[:500],  # Limit to 500 chars
            )

    def log_redemption_result(
        self, result: RedemptionResult, hero_name: str, hero_id: str, code: str
    ) -> None:
        """
        Log the result of a redemption attempt.

        Args:
            result: The redemption result
            hero_name: The name of the hero
            hero_id: The ID of the hero
            code: The code that was redeemed
        """
        if not self.logger:
            return

        if result.success:
            # Log successful redemption
            self.logger.log_success(
                hero_name=hero_name, hero_id=hero_id, code=code, items_data=result.items
            )
        elif result.is_already_redeemed or result.is_wrong_hero_class:
            # Log informational responses
            potential_items_str = ""
            if result.potential_items:
                potential_items_str = ", ".join(
                    (
                        f"{item_id}: {item_info[0]}"
                        if isinstance(item_info, list) and len(item_info) > 0
                        else f"{item_id}: unknown"
                    )
                    for item_id, item_info in result.potential_items.items()
                )

            self.logger.log_info(
                hero_name=hero_name,
                hero_id=hero_id,
                code=code,
                response_status=result.response_status,
                info_type=result.error_type or "other_info",
                message=result.message,
                potential_items=potential_items_str,
                raw_response=result.raw_response or "",
            )
        else:
            # Log failure
            self.logger.log_failure(
                hero_name=hero_name,
                hero_id=hero_id,
                code=code,
                response_status=result.response_status,
                error_type=result.error_type or "unknown_error",
                error_message=result.message,
                raw_response=result.raw_response or "",
            )

    def redeem_code(
        self,
        code: str,
        hero_id: Optional[Union[str, int]] = None,
        hero_name: Optional[str] = None,
    ) -> RedemptionResult:
        """
        Redeem a code using the authenticated session

        Args:
            code: The code to redeem
            hero_id: Optional hero ID to redeem for
            hero_name: Optional hero name (will be looked up if not provided)

        Returns:
            A RedemptionResult object
        """
        # Get the CSRF token
        token = self.extract_token()
        if not token:
            error_result = RedemptionResult.error_result(
                error_type="token_error",
                message="No CSRF token found",
                response_status=0,
            )

            if hero_name and hero_id:
                self.log_redemption_result(error_result, hero_name, str(hero_id), code)

            self.console.error("No CSRF token found")
            return error_result

        # If hero_id wasn't provided, try to extract it
        heroes_dict = None
        if not hero_id:
            heroes_dict = self.extract_hero_ids()
            if not heroes_dict:
                error_result = RedemptionResult.error_result(
                    error_type="hero_error",
                    message="No heroes found",
                    response_status=0,
                )

                self.log_redemption_result(error_result, "unknown", "unknown", code)

                self.console.error(f"Failed to redeem code '{code}': No heroes found")
                return error_result

            # Use the first hero if none specified
            hero_id = list(heroes_dict.values())[0]
            hero_name = list(heroes_dict.keys())[0]
            self.console.info(f"No hero specified, using: {hero_name}")

        # Ensure hero_id is a string
        hero_id = str(hero_id)

        # If hero_name wasn't provided, try to find it from the hero_id
        if not hero_name:
            if not heroes_dict:
                heroes_dict = self.extract_hero_ids()

            # Look up the hero name from the ID
            for name, id_val in heroes_dict.items():
                if str(id_val) == hero_id:
                    hero_name = name
                    break

            if not hero_name:
                hero_name = f"unknown_hero_{hero_id}"

        # Make the redemption request
        try:
            # Prepare the request
            redeem_url, payload, headers = self.prepare_redemption_request(
                code, hero_id, token
            )

            # Send the request
            response = RequestHandler.post(self.session, redeem_url, payload, headers)

            if not response:
                error_result = RedemptionResult.error_result(
                    error_type="request_error",
                    message="Failed to send redemption request",
                    response_status=0,
                )

                self.log_redemption_result(error_result, hero_name, hero_id, code)

                self.console.error("Failed to send redemption request")
                return error_result

            # Parse the response
            result = self.parse_redemption_response(response, hero_name, hero_id, code)

            # Log the result
            self.log_redemption_result(result, hero_name, hero_id, code)

            return result

        except Exception as e:
            # Exception during request
            error_result = RedemptionResult.error_result(
                error_type="exception",
                message=str(e),
                response_status=0,
                raw_response=type(e).__name__,
            )

            self.log_redemption_result(error_result, hero_name, hero_id, code)

            self.console.error(f"Error: {e}")
            return error_result

    def redeem_code_with_priority(self, code: str) -> bool:
        """
        Redeem a code using priority settings

        Args:
            code: The code to redeem

        Returns:
            True if redemption was successful with any hero, False otherwise
        """
        # Extract all heroes first if needed
        if not self.hero_manager.heroes:
            heroes = self.extract_hero_ids()
            if not heroes:
                self.console.error(f"No heroes found to redeem code '{code}'")
                if self.logger:
                    self.logger.log_failure(
                        hero_name="unknown",
                        hero_id="unknown",
                        code=code,
                        response_status=0,
                        error_type="hero_error",
                        error_message="No heroes found",
                        raw_response="",
                    )
                return False

        # Get the prioritized hero names
        all_heroes_in_order = self.hero_manager.get_prioritized_hero_names()
        self.console.info(
            f"Trying code on {len(all_heroes_in_order)} heroes in priority order"
        )

        # Try redeeming for each hero in priority order
        overall_success = False

        for hero_name in all_heroes_in_order:
            hero_id = self.hero_manager.heroes[hero_name].id

            # Call the redeem_code method with hero name
            result = self.redeem_code(code, hero_id, hero_name)

            if result.success:
                self.console.success(f"Successfully redeemed with hero {hero_name}")
                overall_success = True
                break  # Stop after first success

        return overall_success
