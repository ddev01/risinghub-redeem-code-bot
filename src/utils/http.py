"""
HTTP utilities for the RisingHub code redemption bot.
"""

import requests
from typing import Dict, Any, Optional, Tuple, Union, List
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
    HTML parsing utilities for extracting data from web pages.
    """

    @staticmethod
    def get_token_from_html(
        html_content: str, token_name: str = "_token"
    ) -> Optional[str]:
        """
        Extract CSRF token from HTML content
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Try to find token in meta tags
            meta_token = soup.find("meta", {"name": token_name})
            if meta_token and meta_token.get("content"):
                return meta_token["content"]

            # Try to find token in form inputs
            input_token = soup.find("input", {"name": token_name})
            if input_token and input_token.get("value"):
                return input_token["value"]

            return None
        except Exception:
            return None

    @staticmethod
    def extract_select_options(html_content: str, select_name: str) -> Dict[str, str]:
        """
        Extract options from a select dropdown in HTML content
        """
        options = {}
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            select = soup.find("select", {"name": select_name})

            if select:
                for option in select.find_all("option"):
                    value = option.get("value")
                    text = option.text.strip()
                    if value:
                        options[value] = text
        except Exception:
            pass

        return options

    @staticmethod
    def extract_redemption_history(html_content: str) -> List[Dict[str, str]]:
        """
        Extract redemption history from the profile page table

        Returns:
            List of dictionaries with date, code, and hero information
        """
        redemption_history = []

        try:
            soup = BeautifulSoup(html_content, "html.parser")

            # Look for tables that might contain redemption history
            tables = soup.find_all("table")

            for table in tables:
                # Check if this table has the redemption history headers
                headers = table.find_all("th")

                if headers:
                    header_texts = [h.text.strip() for h in headers]

                    # Convert to lowercase for comparison
                    header_texts_lower = [h.lower() for h in header_texts]

                    # Check if this looks like our redemption table
                    has_date = any("date" in h for h in header_texts_lower)
                    has_code = any("code" in h for h in header_texts_lower)
                    has_hero = any("hero" in h for h in header_texts_lower)

                    if has_date and has_code and has_hero:
                        # Find column indices
                        date_idx = next(
                            (
                                i
                                for i, h in enumerate(header_texts_lower)
                                if "date" in h
                            ),
                            -1,
                        )
                        code_idx = next(
                            (
                                i
                                for i, h in enumerate(header_texts_lower)
                                if "code" in h
                            ),
                            -1,
                        )
                        hero_idx = next(
                            (
                                i
                                for i, h in enumerate(header_texts_lower)
                                if "hero" in h
                            ),
                            -1,
                        )

                        # Only proceed if we found all necessary columns
                        if date_idx >= 0 and code_idx >= 0 and hero_idx >= 0:
                            # Find the table body
                            tbody = table.find("tbody")
                            if tbody:
                                rows = tbody.find_all("tr")
                            else:
                                rows = table.find_all("tr")[1:]  # Skip header row

                            for row in rows:
                                cells = row.find_all("td")

                                if len(cells) > max(date_idx, code_idx, hero_idx):
                                    redemption_data = {
                                        "date": cells[date_idx].text.strip(),
                                        "code": cells[code_idx].text.strip(),
                                        "hero": cells[hero_idx].text.strip(),
                                    }
                                    redemption_history.append(redemption_data)

                            # Found the redemption table, no need to continue searching
                            break

        except Exception as e:
            # Log the error but continue execution
            pass

        return redemption_history
