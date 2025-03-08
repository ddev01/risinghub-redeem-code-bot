"""
Utilities for tracking code redemptions.
"""

import os
import csv
from typing import List, Dict, Set, Tuple


class CodeTracker:
    """
    Tracks code redemptions to avoid duplicate redemption attempts.
    """

    def __init__(self, csv_file: str = "redeemed_codes.csv"):
        """
        Initialize the code tracker
        """
        self.csv_file = csv_file
        self.redeemed_codes = self._load_redeemed_codes()

    def _load_redeemed_codes(self) -> Set[Tuple[str, str]]:
        """
        Load redeemed codes from CSV file

        Returns:
            Set of (code, hero) tuples that have been redeemed
        """
        redeemed = set()

        if not os.path.exists(self.csv_file):
            # Create the file with headers if it doesn't exist
            with open(self.csv_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["code", "hero", "date"])
            return redeemed

        try:
            with open(self.csv_file, "r", newline="") as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header row
                for row in reader:
                    if len(row) >= 2:
                        redeemed.add((row[0].strip(), row[1].strip()))
        except Exception:
            # If there's any error reading the file, return an empty set
            pass

        return redeemed

    def is_redeemed(self, code: str, hero: str) -> bool:
        """
        Check if a code has already been redeemed for a hero

        Returns:
            True if the code has been redeemed for the hero, False otherwise
        """
        return (code.strip(), hero.strip()) in self.redeemed_codes

    def add_redeemed_code(self, code: str, hero: str, date: str = "") -> None:
        """
        Add a redeemed code to the tracker and save to CSV
        """
        code = code.strip()
        hero = hero.strip()

        if (code, hero) not in self.redeemed_codes:
            self.redeemed_codes.add((code, hero))

            # Append to CSV file
            with open(self.csv_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([code, hero, date])

    def add_redemption_history(self, history: List[Dict[str, str]]) -> int:
        """
        Add multiple redemption records from history

        Args:
            history: List of dictionaries with code, hero, and date info

        Returns:
            Number of new redemption records added
        """
        if not history:
            return 0

        new_records = 0
        for record in history:
            code = record.get("code", "").strip()
            hero = record.get("hero", "").strip()
            date = record.get("date", "").strip()

            if code and hero and (code, hero) not in self.redeemed_codes:
                self.add_redeemed_code(code, hero, date)
                new_records += 1

        return new_records
