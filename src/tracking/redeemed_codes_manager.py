"""
Tracking module for redeemed codes across heroes and accounts.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Any

from src.utils.file_helpers import initialize_csv_file


class RedeemedCodesManager:
    """
    Manages tracking of redeemed codes across all accounts and heroes
    """

    def __init__(self, file_path: str = "logs/redeemed_codes.csv"):
        """
        Initialize with file path for storing redeemed codes

        Args:
            file_path: Path to the CSV file storing redeemed codes
        """
        self.file_path = file_path
        # Dict of {username: {hero_name: set(codes)}}
        self.redeemed_codes: Dict[str, Dict[str, Set[str]]] = {}

        # Ensure logs directory exists
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        self._load_redeemed_codes()

    def _initialize_file(self) -> None:
        """
        Initialize the redeemed codes file with headers if it doesn't exist
        """
        initialize_csv_file(
            self.file_path,
            ["Timestamp", "Username", "Hero Name", "Hero ID", "Code", "Status"],
        )

    def _load_redeemed_codes(self) -> None:
        """
        Load previously redeemed codes from CSV file
        """
        self._initialize_file()

        try:
            with open(self.file_path, "r") as f:
                reader = csv.reader(f)
                # Skip header
                next(reader, None)

                account_count = 0
                code_count = 0

                for row in reader:
                    if len(row) >= 5:
                        timestamp, username, hero_name, hero_id, code, status = (
                            row + [""] if len(row) == 5 else row
                        )

                        # Skip invalid entries
                        if not all([username, hero_name, code]):
                            continue

                        # Initialize nested dictionaries if needed
                        if username not in self.redeemed_codes:
                            self.redeemed_codes[username] = {}
                            account_count += 1

                        if hero_name not in self.redeemed_codes[username]:
                            self.redeemed_codes[username][hero_name] = set()

                        # Add code to the set
                        self.redeemed_codes[username][hero_name].add(code)
                        code_count += 1

                if account_count > 0:
                    print(
                        f"📝 Loaded {code_count} redeemed codes for {account_count} accounts"
                    )

        except FileNotFoundError:
            # No need to print anything for a new file
            self._initialize_file()
        except Exception as e:
            print(f"❌ Error loading redeemed codes: {e}")

    def is_code_redeemed(self, username: str, hero_name: str, code: str) -> bool:
        """
        Check if a code has already been redeemed for a specific hero

        Args:
            username: Account username
            hero_name: Hero name
            code: Redemption code

        Returns:
            True if the code has been redeemed, False otherwise
        """
        return (
            username in self.redeemed_codes
            and hero_name in self.redeemed_codes[username]
            and code in self.redeemed_codes[username][hero_name]
        )

    def mark_as_redeemed(
        self,
        username: str,
        hero_name: str,
        hero_id: str,
        code: str,
        status: str = "success",
    ) -> None:
        """
        Mark a code as redeemed for a specific hero

        Args:
            username: Account username
            hero_name: Hero name
            hero_id: Hero ID
            code: Redemption code
            status: Status of the redemption (success, already_redeemed, etc.)
        """
        # Update in-memory structure
        if username not in self.redeemed_codes:
            self.redeemed_codes[username] = {}

        if hero_name not in self.redeemed_codes[username]:
            self.redeemed_codes[username][hero_name] = set()

        self.redeemed_codes[username][hero_name].add(code)

        # Write to CSV file
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.file_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, username, hero_name, hero_id, code, status])

    def get_unredeemed_codes(
        self, username: str, hero_names: List[str], codes: List[str]
    ) -> Dict[str, List[str]]:
        """
        Get codes that haven't been redeemed yet for each hero

        Args:
            username: Account username
            hero_names: List of hero names
            codes: List of redemption codes

        Returns:
            A dictionary with hero names as keys and lists of unredeemed codes as values
        """
        result: Dict[str, List[str]] = {}

        for hero_name in hero_names:
            unredeemed_codes = []

            for code in codes:
                if not self.is_code_redeemed(username, hero_name, code):
                    unredeemed_codes.append(code)

            result[hero_name] = unredeemed_codes

        return result

    def is_fully_redeemed(
        self, username: str, hero_names: List[str], code: str
    ) -> bool:
        """
        Check if a code has been redeemed by all heroes of an account

        Args:
            username: Account username
            hero_names: List of hero names
            code: Redemption code

        Returns:
            True if all heroes have redeemed (or attempted to redeem) the code
        """
        if username not in self.redeemed_codes:
            return False

        # For each hero, check if they've redeemed this code
        for hero_name in hero_names:
            # If any hero hasn't tried this code yet, return False
            if (
                hero_name not in self.redeemed_codes[username]
                or code not in self.redeemed_codes[username][hero_name]
            ):
                return False

        # If we get here, all heroes have redeemed or attempted to redeem this code
        return True
