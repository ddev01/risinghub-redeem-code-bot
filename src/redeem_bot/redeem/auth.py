"""Authentication and session cookie persistence."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from redeem_bot.redeem.html_utils import get_token_from_html

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


def create_default_headers(base_url: str) -> dict[str, str]:
    return {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Origin": base_url.rstrip("/"),
    }


class LoginManager:
    """Manages httpx sessions with cookie persistence."""

    def __init__(
        self,
        base_url: str,
        cookie_file: Path,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"
        self.cookie_file = cookie_file
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _clear_session(self) -> None:
        """Drop cached cookies so a broken session cannot poison the next login."""
        self.client.cookies.clear()
        if self.cookie_file.exists():
            self.cookie_file.unlink()

    def login(self, username: str, password: str) -> httpx.Client | None:
        if self.load_cookies() and self.verify_session():
            logger.debug("Using cached session for %s", username)
            return self.client

        self._clear_session()
        login_url = f"{self.base_url}login"

        try:
            response = self.client.get(login_url)
            if response.status_code != 200:
                logger.error("Failed to connect to login page")
                return None

            token = get_token_from_html(response.text)
            if not token:
                logger.error("Failed to extract CSRF token from login page")
                return None

            login_data = {
                "_token": token,
                "username": username,
                "login": username,
                "password": password,
                "remember": "1",
            }

            headers = create_default_headers(self.base_url)
            headers.update(
                {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": login_url,
                }
            )

            response = self.client.post(login_url, data=login_data, headers=headers)
            if response.status_code >= 400:
                logger.error("Login request failed with status %s", response.status_code)
                return None

            if "Dashboard" in response.text or "profile" in response.text:
                self.save_cookies()
                return self.client

            logger.error("Login failed — incorrect credentials or captcha required")
            return None

        except httpx.HTTPError as exc:
            logger.error("Login failed with exception: %s", exc)
            return None

    def save_cookies(self) -> bool:
        try:
            cookies = dict(self.client.cookies)
            self.cookie_file.write_text(json.dumps(cookies), encoding="utf-8")
            return True
        except OSError as exc:
            logger.error("Failed to save cookies: %s", exc)
            return False

    def load_cookies(self) -> bool:
        if not self.cookie_file.exists():
            return False

        try:
            cookies = json.loads(self.cookie_file.read_text(encoding="utf-8"))
            for name, value in cookies.items():
                self.client.cookies.set(name, value)
            return True
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed to load cookies: %s", exc)
            return False

    def verify_session(self) -> bool:
        profile_url = f"{self.base_url}profile"
        try:
            response = self.client.get(profile_url)
            if response.status_code != 200:
                return False
            text_lower = response.text.lower()
            return "logout" in text_lower
        except httpx.HTTPError as exc:
            logger.warning("Session verification failed: %s", exc)
            return False

    def test_connection(self) -> bool:
        login_url = f"{self.base_url}login"
        try:
            response = self.client.get(login_url)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def get_profile_page(self) -> httpx.Response | None:
        profile_url = f"{self.base_url}profile"
        try:
            response = self.client.get(profile_url)
            if response.status_code == 200:
                return response
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch profile page: %s", exc)
        return None


def get_authenticated_session(
    base_url: str,
    username: str,
    password: str,
    cookie_file: Path,
    client: httpx.Client | None = None,
) -> tuple[httpx.Client | None, httpx.Response | None]:
    login_manager = LoginManager(base_url, cookie_file, client=client)

    if not login_manager.test_connection():
        login_manager.close()
        return None, None

    session = login_manager.login(username, password)
    if not session:
        login_manager.close()
        return None, None

    profile_response = login_manager.get_profile_page()
    return session, profile_response
