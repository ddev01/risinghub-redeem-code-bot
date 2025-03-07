import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from typing import Optional
import sys


class LoginManager:
    """
    Handles authentication with the target website
    """

    def __init__(self, base_url: str):
        """
        Initialize the login manager with base URL
        """
        self.base_url = base_url
        self.session = requests.Session()
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
                return self.session

        # If we get here, login failed
        print("Login failed. Wrong credentials?")
        return None


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

    login_manager = LoginManager(base_url)
    session = login_manager.login(username, password)

    if not session:
        sys.exit(1)


if __name__ == "__main__":
    main()
