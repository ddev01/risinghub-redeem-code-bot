"""
Authentication and session management for the RisingHub code redemption bot.
"""

import json
import time
import requests
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

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

        Args:
            username: The username to log in with
            password: The password to log in with

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
            # First request to get CSRF token
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
                "login": username,
                "password": password,
                "remember": "1",
            }

            # Submit login form
            login_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": login_url,
                "Origin": self.base_url.rstrip("/"),
            }

            response = RequestHandler.post(
                self.session, login_url, login_data, login_headers
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
        Save session cookies to file

        Returns:
            True if cookies were saved successfully, False otherwise
        """
        try:
            # Extract cookies from session
            cookies = self.session.cookies.get_dict()

            # Save cookies to file
            with open(self.cookie_file, "w") as f:
                json.dump(cookies, f)

            return True
        except Exception as e:
            self.logger.error(f"Failed to save cookies: {str(e)}")
            return False

    def load_cookies(self) -> bool:
        """
        Load cookies from file into session

        Returns:
            True if cookies were loaded successfully, False otherwise
        """
        try:
            with open(self.cookie_file, "r") as f:
                cookies = json.load(f)

            # Add cookies to session
            for key, value in cookies.items():
                self.session.cookies.set(key, value)

            return True
        except FileNotFoundError:
            self.logger.info("No cookies file found")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load cookies: {str(e)}")
            return False

    def verify_session(self) -> bool:
        """
        Verify if the current session is authenticated

        Returns:
            True if session is valid, False otherwise
        """
        try:
            # Try to access a protected page
            profile_url = f"{self.base_url}profile"
            response = RequestHandler.get(self.session, profile_url)

            if not response:
                return False

            # Check if we got a valid profile page response
            return "My Profile" in response.text or "Dashboard" in response.text
        except Exception:
            return False


def get_authenticated_session(
    base_url: str, username: str, password: str, cookie_file: str, logger=None
) -> Tuple[Optional[requests.Session], Optional[requests.Response]]:
    """
    Get an authenticated session

    Args:
        base_url: The base URL for authentication
        username: The username to authenticate with
        password: The password to authenticate with
        cookie_file: Path to the cookie file
        logger: Optional console logger

    Returns:
        A tuple of (session, response) if successful, (None, None) otherwise
    """
    logger = logger or ConsoleLogger()

    # Initialize login manager
    login_manager = LoginManager(base_url, cookie_file, logger)

    # Try to log in
    session = login_manager.login(username, password)
    if not session:
        return None, None

    # Get the response for the redeem panel to use later
    try:
        redeem_url = f"{base_url}profile#redeem-panel"
        response = RequestHandler.get(session, redeem_url)

        return session, response
    except Exception as e:
        logger.error(f"Failed to access redeem panel: {str(e)}")
        return session, None
