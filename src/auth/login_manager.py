"""
Authentication and session management for the RisingHub code redemption bot.
"""

import json
import time
import requests
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup

from src.utils.http import RequestHandler, HtmlParser
from src.logging.console import ConsoleLogger, LogLevel


class LoginManager:
    """
    Manages authentication and session cookies
    """

    def __init__(
        self, base_url: str, cookie_file: str = "session_cookies.json", logger=None
    ):
        """
        Initialize with base URL and cookie file path

        Args:
            base_url: The base URL for authentication
            cookie_file: Path to the cookie file
            logger: Optional console logger
        """
        self.base_url = base_url
        self.cookie_file = cookie_file
        self.session = requests.Session()
        self.logger = logger or ConsoleLogger()

        # Create the directory for the cookie file if it doesn't exist
        Path(self.cookie_file).parent.mkdir(exist_ok=True, parents=True)

    def login(self, username: str, password: str) -> Optional[requests.Session]:
        """
        Log in to the website

        Returns:
            The authenticated session if successful, None otherwise
        """
        # Try to load cookies first
        if self.load_cookies():
            self.logger.info("Loaded cookies from file")

            # Verify the session is still valid
            if self.verify_session():
                self.logger.success("Using existing session from cookies")
                return self.session
            else:
                self.logger.warning("Cookies expired, logging in again")

        # Set up the login URL
        login_url = f"{self.base_url}login"

        # Start a new session
        self.session = requests.Session()

        try:
            # Get login page to obtain CSRF token
            response = RequestHandler.get(self.session, login_url)
            if not response:
                self.logger.error("Failed to connect to login page")
                return None

            # Parse the token from the login page
            token = HtmlParser.get_token_from_html(response.text)
            if not token:
                self.logger.error("Failed to extract CSRF token from login page")
                return None

            # Prepare login data
            login_data = {
                "_token": token,
                "username": username,
                "login": username,
                "password": password,
                "remember": "1",
            }

            # Submit login form
            login_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": login_url,
                "Origin": self.base_url.rstrip("/"),
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            }

            response = RequestHandler.post(
                self.session, login_url, login_data, login_headers, allow_redirects=True
            )
            if not response:
                self.logger.error("Login request failed")
                return None

            # Check if login was successful
            if "Dashboard" in response.text or "profile" in response.text:
                self.logger.success("Login successful")

                # Save cookies for future use
                if self.save_cookies():
                    self.logger.debug("Cookies saved successfully")

                return self.session
            else:
                self.logger.error(
                    "Login failed - incorrect credentials or captcha required"
                )
                return None

        except Exception as e:
            self.logger.error(f"Login failed with exception: {str(e)}")
            return None

    def save_cookies(self) -> bool:
        """
        Save session cookies to a file

        Returns:
            True if cookies were saved successfully, False otherwise
        """
        if not self.session:
            return False

        try:
            cookies = {name: value for name, value in self.session.cookies.items()}

            with open(self.cookie_file, "w") as f:
                json.dump(cookies, f)

            return True
        except Exception as e:
            self.logger.error(f"Failed to save cookies: {str(e)}")
            return False

    def load_cookies(self) -> bool:
        """
        Load cookies from file into the session

        Returns:
            True if cookies were loaded successfully, False otherwise
        """
        if not os.path.exists(self.cookie_file):
            return False

        try:
            with open(self.cookie_file, "r") as f:
                cookies = json.load(f)

            self.session = requests.Session()
            for name, value in cookies.items():
                self.session.cookies.set(name, value)

            return True
        except FileNotFoundError:
            self.logger.info("No cookies file found")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load cookies: {str(e)}")
            return False

    def verify_session(self) -> bool:
        """
        Verify if the current session is still authenticated

        Returns:
            True if the session is valid, False otherwise
        """
        if not self.session:
            return False

        profile_url = f"{self.base_url}profile"
        try:
            response = RequestHandler.get(self.session, profile_url)

            if not response or response.status_code != 200:
                return False

            # Check for indicators of being logged in
            return "logout" in response.text.lower() or "Logout" in response.text

        except Exception as e:
            self.logger.error(f"Session verification failed: {str(e)}")
            return False

    def test_connection(self) -> bool:
        """
        Test connectivity to the website and verify login page is accessible

        Returns:
            True if the connection was successful, False otherwise
        """
        login_url = f"{self.base_url}login"

        try:
            response = RequestHandler.get(self.session, login_url)
            if not response or response.status_code != 200:
                return False

            # Connection was successful
            return True

        except Exception:
            return False


def get_authenticated_session(
    base_url: str, username: str, password: str, cookie_file: str, logger=None
) -> Tuple[Optional[requests.Session], Optional[requests.Response]]:
    """
    Get an authenticated session

    Returns:
        A tuple with the authenticated session and profile response,
        or (None, None) if authentication failed
    """
    # Create login manager
    login_manager = LoginManager(base_url, cookie_file)

    # Test connection to the website
    if not login_manager.test_connection():
        return None, None

    # Try to log in
    session = login_manager.login(username, password)
    if not session:
        return None, None

    # Get profile page
    profile_url = f"{base_url}profile"
    profile_response = RequestHandler.get(session, profile_url)

    return session, profile_response
