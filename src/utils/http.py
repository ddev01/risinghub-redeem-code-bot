"""
HTTP utilities for the RisingHub code redemption bot.
"""

import requests
from typing import Dict, Any, Optional, Tuple, Union
from bs4 import BeautifulSoup


class RequestHandler:
    """
    Handles HTTP requests with consistent headers and error handling.
    """

    @staticmethod
    def create_default_headers(base_url: str) -> Dict[str, str]:
        """
        Create default headers for HTTP requests.

        Args:
            base_url: The base URL for the request

        Returns:
            A dictionary of default headers
        """
        return {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": base_url + "profile",
            "Origin": base_url.rstrip("/"),
            "Accept": "*/*",
        }

    @staticmethod
    def get(
        session: requests.Session, url: str, headers: Optional[Dict[str, str]] = None
    ) -> Optional[requests.Response]:
        """
        Send a GET request with error handling.

        Args:
            session: The requests session to use
            url: The URL to request
            headers: Optional headers to include

        Returns:
            The response if successful, None otherwise
        """
        try:
            return session.get(url, headers=headers)
        except requests.exceptions.RequestException:
            return None

    @staticmethod
    def post(
        session: requests.Session,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[requests.Response]:
        """
        Send a POST request with error handling.

        Args:
            session: The requests session to use
            url: The URL to request
            data: The data to send
            headers: Optional headers to include

        Returns:
            The response if successful, None otherwise
        """
        try:
            return session.post(url, data=data, headers=headers)
        except requests.exceptions.RequestException:
            return None


class HtmlParser:
    """
    Utility for parsing HTML responses.
    """

    @staticmethod
    def get_token_from_html(
        html_content: str, token_name: str = "_token"
    ) -> Optional[str]:
        """
        Extract a CSRF token from HTML content.

        Args:
            html_content: The HTML content to parse
            token_name: The name of the token input field

        Returns:
            The token value if found, None otherwise
        """
        soup = BeautifulSoup(html_content, "html.parser")
        token_input = soup.find("input", {"name": token_name})

        if not token_input:
            return None

        return token_input.get("value")

    @staticmethod
    def extract_select_options(html_content: str, select_name: str) -> Dict[str, str]:
        """
        Extract options from a select dropdown in HTML.

        Args:
            html_content: The HTML content to parse
            select_name: The name of the select element

        Returns:
            A dictionary mapping option text to option value
        """
        soup = BeautifulSoup(html_content, "html.parser")
        select_element = soup.find("select", {"name": select_name})

        options = {}
        if not select_element:
            return options

        for option in select_element.find_all("option"):
            value = option.get("value")
            text = option.text.strip()

            if value and text:
                options[text] = value

        return options
