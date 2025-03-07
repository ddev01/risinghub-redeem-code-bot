import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from typing import Optional
import sys
import json
import time
from pathlib import Path


class LoginManager:
    """
    Handles authentication with the target website
    """

    def __init__(self, base_url: str, cookie_file: str = "session_cookies.json"):
        """
        Initialize the login manager with base URL and cookie file path
        """
        self.base_url = base_url
        self.session = requests.Session()

        if os.getenv("DEBUG"):
            self.session.proxies = {
                "http": "http://127.0.0.1:8080",
                "https": "http://127.0.0.1:8080",
            }
            proxy = "http://127.0.0.1:8080"
            os.environ["http_proxy"] = proxy
            os.environ["HTTP_PROXY"] = proxy
            os.environ["https_proxy"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
            os.environ["REQUESTS_CA_BUNDLE"] = "certificate.pem"
        self.cookie_file = cookie_file
        # Set common browser headers
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
            }
        )

    def login(self, username: str, password: str) -> Optional[requests.Session]:
        """
        Attempts to log in with the provided credentials
        """
        login_url = self.base_url + "login"
        # Set referrer for initial request to base URL
        self.session.headers.update({"Referer": self.base_url})
        response = self.session.get(login_url)

        # Parse the HTML to find the token
        soup = BeautifulSoup(response.text, "html.parser")
        token_input = soup.find("input", {"name": "_token"})

        if not token_input:
            print("Error: Could not find CSRF token on login page")
            return None

        token = token_input["value"]

        login_data = {
            "_token": token,
            "username": username,
            "password": password,
            "submit": "",
        }

        # Update referrer for login POST request
        self.session.headers.update({"Referer": login_url})

        # Make the login request with allow_redirects=False to see the redirect location
        login_response = self.session.post(
            login_url, data=login_data, allow_redirects=False
        )

        # Check if login was successful based on the redirect location
        if login_response.status_code == 302:
            redirect_location = login_response.headers.get("location", "")

            # Successful login redirects to the base URL or profile, failed login redirects back to login
            if "/login" not in redirect_location:
                print("Login successful!")
                self.save_cookies()
                return self.session

        # If we get here, login failed
        print("Login failed. Wrong credentials?")
        return None

    def save_cookies(self) -> bool:
        """
        Saves the current session cookies to a file
        """
        try:
            cookies_dict = {name: value for name, value in self.session.cookies.items()}

            # Create directory if it doesn't exist
            cookie_path = Path(self.cookie_file)
            cookie_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.cookie_file, "w") as f:
                json.dump({"cookies": cookies_dict, "timestamp": time.time()}, f)
            print(f"Cookies saved to {self.cookie_file}")
            return True
        except Exception as e:
            print(f"Error saving cookies: {e}")
            return False

    def load_cookies(self) -> bool:
        """
        Loads cookies from the cookie file into the current session
        """
        cookie_path = Path(self.cookie_file)

        # If file doesn't exist, return False without error
        if not cookie_path.exists():
            print(
                f"Cookie file {self.cookie_file} not found - will create on successful login"
            )
            return False

        # If file is empty, return False without error
        if cookie_path.stat().st_size == 0:
            print(f"Cookie file is empty - will create proper file on successful login")
            return False

        try:
            with open(self.cookie_file, "r") as f:
                data = json.load(f)

            # Check if cookies are expired (24 hours)
            if time.time() - data.get("timestamp", 0) > 604800:
                print("Cookies have expired")
                return False

            cookies_dict = data.get("cookies", {})
            if not cookies_dict:
                print("No cookies found in file")
                return False

            # Add cookies to session
            for name, value in cookies_dict.items():
                self.session.cookies.set(name, value)

            print("Cookies loaded successfully")
            return True
        except json.JSONDecodeError:
            print(
                f"Invalid JSON in cookie file - will create new file on successful login"
            )
            return False
        except Exception as e:
            print(f"Error loading cookies: {e}")
            return False

    def verify_session(self) -> bool:
        """
        Verifies if the current session is valid by making a request to the redeem panel
        """
        try:
            # Check the redeem-panel page that requires authentication
            redeem_url = self.base_url + "profile#redeem-panel"
            response = self.session.get(redeem_url, allow_redirects=False)

            # If we get redirected to login, the session is invalid
            if response.status_code == 302 and "/login" in response.headers.get(
                "location", ""
            ):
                print("Session invalid: Redirected to login page")
                return False

            # If we get a 200 OK, the session is valid
            if response.status_code == 200:
                print("Session valid: Successfully accessed redeem panel")
                return True

            print(f"Session check: Unexpected status code {response.status_code}")
            return False
        except Exception as e:
            print(f"Error verifying session: {e}")
            return False


def get_authenticated_session(
    base_url: str, username: str, password: str
) -> Optional[requests.Session]:
    """
    Gets an authenticated session either by loading cookies or logging in
    """
    login_manager = LoginManager(base_url)

    # Try to load existing cookies first
    if login_manager.load_cookies() and login_manager.verify_session():
        print("Using existing session from cookies")
        return login_manager.session

    print("Need to login again")
    # If cookies don't work, try logging in
    return login_manager.login(username, password)


def main() -> None:
    """
    Main function
    """
    load_dotenv()

    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    base_url = os.getenv("BASEURL")

    if not all([username, password, base_url]):
        print("Error: Missing required environment variables. Please check .env file.")
        sys.exit(1)

    session = get_authenticated_session(base_url, username, password)

    if not session:
        print("Failed to authenticate. Exiting.")
        sys.exit(1)

    print("Authentication successful.")


if __name__ == "__main__":
    main()
