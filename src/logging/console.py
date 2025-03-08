"""
Console logging utilities for the RisingHub code redemption bot.
"""

from typing import List, Dict, Any, Optional
from enum import Enum


class LogLevel(Enum):
    """
    Logging levels for console output.
    """

    DEBUG = 0
    INFO = 1
    SUCCESS = 2
    WARNING = 3
    ERROR = 4


class ConsoleLogger:
    """
    Console logger with emoji indicators and formatted output.
    """

    def __init__(self, min_level: LogLevel = LogLevel.INFO):
        """
        Initialize the console logger.

        Args:
            min_level: The minimum log level to display
        """
        self.min_level = min_level
        self.emoji_map = {
            LogLevel.DEBUG: "🔍",
            LogLevel.INFO: "ℹ️",
            LogLevel.SUCCESS: "✅",
            LogLevel.WARNING: "⚠️",
            LogLevel.ERROR: "❌",
        }

    def _should_log(self, level: LogLevel) -> bool:
        """
        Determine if a message at the given level should be logged.

        Args:
            level: The log level to check

        Returns:
            True if the message should be logged, False otherwise
        """
        return level.value >= self.min_level.value

    def _format_message(self, level: LogLevel, message: str) -> str:
        """
        Format a message with the appropriate emoji.

        Args:
            level: The log level
            message: The message to format

        Returns:
            The formatted message
        """
        emoji = self.emoji_map.get(level, "")
        return f"{emoji} {message}"

    def debug(self, message: str) -> None:
        """
        Log a debug message.

        Args:
            message: The message to log
        """
        if self._should_log(LogLevel.DEBUG):
            print(self._format_message(LogLevel.DEBUG, message))

    def info(self, message: str) -> None:
        """
        Log an info message.

        Args:
            message: The message to log
        """
        if self._should_log(LogLevel.INFO):
            print(self._format_message(LogLevel.INFO, message))

    def success(self, message: str) -> None:
        """
        Log a success message.

        Args:
            message: The message to log
        """
        if self._should_log(LogLevel.SUCCESS):
            print(self._format_message(LogLevel.SUCCESS, message))

    def warning(self, message: str) -> None:
        """
        Log a warning message.

        Args:
            message: The message to log
        """
        if self._should_log(LogLevel.WARNING):
            print(self._format_message(LogLevel.WARNING, message))

    def error(self, message: str) -> None:
        """
        Log an error message.

        Args:
            message: The message to log
        """
        if self._should_log(LogLevel.ERROR):
            print(self._format_message(LogLevel.ERROR, message))

    def section(self, title: str) -> None:
        """
        Log a section header.

        Args:
            title: The section title
        """
        print(f"\n📊 === {title} ===")

    def account_section(self, username: str) -> None:
        """
        Log an account section header.

        Args:
            username: The username of the account
        """
        print(f"\n🧑‍🚀 === Processing account: {username} ===")

    def progress(self, current: int, total: int, description: str) -> None:
        """
        Log a progress update.

        Args:
            current: The current progress
            total: The total progress
            description: A description of the progress
        """
        print(f"🔑 [{current}/{total}] {description}")

    def summary(self, title: str, items: Dict[str, Any]) -> None:
        """
        Log a summary of items.

        Args:
            title: The summary title
            items: The items to summarize
        """
        print(f"📋 {title}:")
        for key, value in items.items():
            print(f"  - {key}: {value}")

    def wait_message(self, seconds: float) -> None:
        """
        Log a wait message.

        Args:
            seconds: The number of seconds to wait
        """
        print(f"⏱️ Waiting {seconds} seconds...")

    def skip_wait_message(self) -> None:
        """
        Log a message indicating that waiting was skipped.
        """
        print("⏭️ Skipping wait time (no server requests made)")

    def hero_processing(self, hero_name: str, code_count: int) -> None:
        """
        Log a hero processing message.

        Args:
            hero_name: The name of the hero
            code_count: The number of codes to process
        """
        print(f"🦸 Processing {code_count} codes for hero {hero_name}")

    def completion(self) -> None:
        """
        Log a completion message.
        """
        print("\n🎉 All accounts processed successfully!")
