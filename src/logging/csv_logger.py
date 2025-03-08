"""
CSV logging utilities for the RisingHub code redemption bot.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.utils.file_helpers import initialize_csv_file


class CSVLogger:
    """
    Handles logging redemption results to CSV files
    """

    def __init__(
        self,
        success_log_file: str = "logs/redemption_success.csv",
        failure_log_file: str = "logs/redemption_failure.csv",
        info_log_file: str = "logs/redemption_info.csv",
        username: str = "",
        redeemed_codes_tracker=None,  # Type annotation will be added after implementing the tracker
    ):
        """
        Initialize with file paths for success, failure and info logs

        Args:
            success_log_file: Path to the success log file
            failure_log_file: Path to the failure log file
            info_log_file: Path to the info log file
            username: Username associated with this logger
            redeemed_codes_tracker: Optional tracker for redeemed codes
        """
        # Ensure logs directory exists
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)

        self.success_log_file = success_log_file
        self.failure_log_file = failure_log_file
        self.info_log_file = info_log_file
        self.username = username
        self.redeemed_codes_tracker = redeemed_codes_tracker

        # Ensure files exist with headers
        self._initialize_logs()

    def _initialize_logs(self) -> None:
        """
        Initialize all log files with their respective headers
        """
        self._initialize_success_log()
        self._initialize_failure_log()
        self._initialize_info_log()

    def _initialize_success_log(self) -> None:
        """
        Initialize success log file with headers if it doesn't exist
        """
        initialize_csv_file(
            self.success_log_file,
            [
                "Timestamp",
                "Hero Name",
                "Hero ID",
                "Item ID",
                "Duration Type",
                "Duration/Count",
                "Item Name",
                "Category",
                "Code Used",
            ],
        )

    def _initialize_failure_log(self) -> None:
        """
        Initialize failure log file with headers if it doesn't exist
        """
        initialize_csv_file(
            self.failure_log_file,
            [
                "Timestamp",
                "Hero Name",
                "Hero ID",
                "Code Used",
                "Response Status",
                "Error Type",
                "Error Message",
                "Raw Response",
            ],
        )

    def _initialize_info_log(self) -> None:
        """
        Initialize info log file with headers if it doesn't exist
        For logging informational responses (wrong hero class, already redeemed, etc.)
        """
        initialize_csv_file(
            self.info_log_file,
            [
                "Timestamp",
                "Hero Name",
                "Hero ID",
                "Code Used",
                "Response Status",
                "Info Type",
                "Message",
                "Potential Items",
                "Raw Response",
            ],
        )

    def log_success(
        self, code: str, hero_name: str, hero_id: str, items: List[str] = None
    ) -> None:
        """
        Log successful redemption items to CSV

        Args:
            code: Redemption code used
            hero_name: Name of the hero
            hero_id: ID of the hero
            items: List of item names or dictionary of item details
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Convert simple item list to dictionary format if needed
        items_data = {}
        if isinstance(items, list):
            # Simple list of items, convert to expected format
            for i, item_name in enumerate(items):
                items_data[f"import_{i}"] = ["imported", "0", item_name, "history"]
        elif isinstance(items, dict):
            # Already in right format
            items_data = items
        else:
            # No valid items, create a generic entry
            items_data = {"unknown": ["unknown", "0", "Unknown Item", "imported"]}

        # Log each item as a separate row
        with open(self.success_log_file, "a", newline="") as f:
            writer = csv.writer(f)

            for item_id, details in items_data.items():
                if len(details) >= 4:
                    duration_type = details[0]
                    duration = details[1]
                    item_name = details[2]
                    category = details[3]

                    writer.writerow(
                        [
                            timestamp,
                            hero_name,
                            hero_id,
                            item_id,
                            duration_type,
                            duration,
                            item_name,
                            category,
                            code,
                        ]
                    )
                else:
                    # Handle unexpected item format
                    writer.writerow(
                        [
                            timestamp,
                            hero_name,
                            hero_id,
                            item_id,
                            "unknown",
                            "unknown",
                            "unknown",
                            "unknown",
                            code,
                        ]
                    )

        # Also mark the code as redeemed in our tracking system
        if self.username and self.redeemed_codes_tracker:
            self.redeemed_codes_tracker.mark_as_redeemed(
                self.username, hero_name, hero_id, code, "success"
            )

    def log_info(
        self,
        hero_name: str,
        hero_id: str,
        code: str,
        response_status: int,
        info_type: str,
        message: str,
        potential_items: str = "",
        raw_response: str = "",
    ) -> None:
        """
        Log informational responses to CSV
        For cases like wrong hero class, code already redeemed, etc.

        Args:
            hero_name: Name of the hero
            hero_id: ID of the hero
            code: Redemption code used
            response_status: HTTP status code of the response
            info_type: Type of information (e.g., already_redeemed, wrong_hero_class)
            message: Informational message
            potential_items: Optional string of potential items
            raw_response: Optional raw response data
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.info_log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    timestamp,
                    hero_name,
                    hero_id,
                    code,
                    response_status,
                    info_type,
                    message,
                    potential_items,
                    raw_response,
                ]
            )

        # For "already_redeemed" and "wrong_hero_class" cases, track in our system
        if (
            info_type in ["already_redeemed", "wrong_hero_class"]
            and self.username
            and self.redeemed_codes_tracker
        ):
            self.redeemed_codes_tracker.mark_as_redeemed(
                self.username, hero_name, hero_id, code, info_type
            )

    def log_failure(
        self,
        hero_name: str,
        hero_id: str,
        code: str,
        response_status: int,
        error_type: str,
        error_message: str,
        raw_response: str = "",
    ) -> None:
        """
        Log failed redemption to CSV for actual errors (not info responses)

        Args:
            hero_name: Name of the hero
            hero_id: ID of the hero
            code: Redemption code used
            response_status: HTTP status code of the response
            error_type: Type of error (e.g., token_error, http_error)
            error_message: Error message
            raw_response: Optional raw response data
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.failure_log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    timestamp,
                    hero_name,
                    hero_id,
                    code,
                    response_status,
                    error_type,
                    error_message,
                    raw_response,
                ]
            )
