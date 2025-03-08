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
        """
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Origin": base_url.rstrip("/"),
        }

    @staticmethod
    def get(
        session: requests.Session,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        allow_redirects: bool = True,
    ) -> Optional[requests.Response]:
        """
        Send a GET request and handle errors.
        """
        try:
            headers = headers or {}
            response = session.get(
                url, headers=headers, allow_redirects=allow_redirects, timeout=30
            )
            return response
        except requests.RequestException:
            return None

    @staticmethod
    def post(
        session: requests.Session,
        url: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        allow_redirects: bool = True,
    ) -> Optional[requests.Response]:
        """
        Send a POST request and handle errors.
        """
        try:
            headers = headers or {}
            response = session.post(
                url,
                data=data,
                headers=headers,
                allow_redirects=allow_redirects,
                timeout=30,
            )
            return response
        except requests.RequestException:
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
