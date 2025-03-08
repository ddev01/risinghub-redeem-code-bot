import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from typing import Optional, Union
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
        print(f"Attempting login for user: {username}")

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
) -> tuple[Optional[requests.Session], Optional[requests.Response]]:
    """
    Gets an authenticated session either by loading cookies or logging in
    Returns both the session and the response from the redeem panel
    """
    login_manager = LoginManager(base_url)

    # Try to load existing cookies first
    if login_manager.load_cookies():
        # Check if session is valid and get the response
        redeem_url = base_url + "profile#redeem-panel"
        response = login_manager.session.get(redeem_url, allow_redirects=False)

        if response.status_code == 200:
            print("Using existing session from cookies")
            return login_manager.session, response

    print("Need to login again")
    # If cookies don't work, try logging in
    session = login_manager.login(username, password)
    if session:
        # Get the redeem page after login
        redeem_url = base_url + "profile#redeem-panel"
        response = session.get(redeem_url)
        return session, response

    return None, None


class CodeRedeemer:
    """
    Handles code redemption functionality
    """

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        response: Optional[requests.Response] = None,
    ):
        """
        Initialize with an authenticated session and optional response
        """
        self.session = session
        self.base_url = base_url
        self.redeem_page_response = response

    def extract_token(self) -> Optional[str]:
        """
        Extract the CSRF token from the redeem page
        """

        soup = BeautifulSoup(self.redeem_page_response.text, "html.parser")
        token_input = soup.find("input", {"name": "_token"})

        if not token_input:
            print("Error: Could not find CSRF token on redeem page")
            return None

        return token_input["value"]

    def extract_hero_ids(self) -> dict:
        """
        Extract the hero IDs from the redeem page
        Returns a dictionary with hero names as keys and IDs as values
        """
        if not self.redeem_page_response:
            return {}

        soup = BeautifulSoup(self.redeem_page_response.text, "html.parser")

        # Find the hero select dropdown
        hero_select = soup.find("select", {"name": "hero"})
        if not hero_select:
            print("Warning: Could not find hero select dropdown")
            return {}

        # Extract all options
        heroes = {}

        for option in hero_select.find_all("option"):
            hero_id = option.get("value")
            hero_name = option.text.strip()

            if hero_id and hero_name:
                heroes[hero_name] = hero_id

        # Only print this when called directly, not from other methods
        if sys._getframe().f_back.f_code.co_name == "main":
            print(f"Found {len(heroes)} heroes")
        return heroes

    def redeem_code(self, code: str, hero_id: Optional[Union[str, int]] = None) -> bool:
        """
        Redeem a code using the authenticated session
        """
        # Get the CSRF token
        token = self.extract_token()
        if not token:
            print(f"Failed to redeem code '{code}': No CSRF token found")
            return False

        hero_ids = self.extract_hero_ids()

        # Prepare the payload
        payload = {"_token": token, "hero": hero_id, "code": code}

        # Set up headers similar to the manual request
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.base_url + "profile",
            "Origin": self.base_url.rstrip("/"),
            "Accept": "*/*",
        }

        # Make the request
        try:
            redeem_url = self.base_url + "profile/redeem"
            print(f"Attempting to redeem code: {code}")
            response = self.session.post(redeem_url, data=payload, headers=headers)

            # Print status code for debugging
            print(f"Response status code: {response.status_code}")

            # Check if the request was successful
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"Response content: {result}")

                    # Handle both list and dictionary responses
                    if isinstance(result, dict):
                        if "error" in result:
                            print(f"Server rejected code '{code}': {result['error']}")
                            return False
                    elif (
                        isinstance(result, list)
                        and len(result) >= 2
                        and result[0] == "error"
                    ):
                        print(f"Server rejected code '{code}': {result[1]}")
                        return False

                    print(f"Successfully redeemed code: {code}")
                    return True
                except json.JSONDecodeError:
                    print(
                        f"Successfully submitted code '{code}' but got non-JSON response"
                    )
                    print(f"Response: {response.text}")
                    return True
            else:
                print(f"Failed to redeem code '{code}': HTTP {response.status_code}")
                print(f"Response: {response.text}")
                return False

        except Exception as e:
            print(f"Error redeeming code '{code}': {e}")
            print(f"Exception type: {type(e).__name__}")
            return False

    def redeem_code_with_priority(self, code: str) -> bool:
        """
        Redeem a code using priority settings from environment variables
        Will try redeeming in priority order:
        1. Priority faction hero
        2. Secondary faction hero
        3. All other heroes

        Returns True if successful with any hero
        """
        # Extract all heroes first
        heroes = self.extract_hero_ids()
        if not heroes:
            print(f"No heroes found to redeem code '{code}'")
            return False

        # Get priority settings from environment
        priority_nat_hero = os.getenv("PRIORITY_NAT_HERO", "")
        priority_roy_hero = os.getenv("PRIORITY_ROY_HERO", "")
        priority_faction = os.getenv("PRIORITY_FACTION", "").lower()

        # Determine which heroes to try first, second, etc.
        prioritized_heroes = []
        remaining_heroes = list(heroes.keys())

        # Check if we have valid priorities
        has_priorities = priority_faction and (priority_nat_hero or priority_roy_hero)

        if has_priorities:
            print(
                f"Using priority settings: Faction={priority_faction}, NAT={priority_nat_hero}, ROY={priority_roy_hero}"
            )

            # First priority hero based on faction
            first_priority = (
                priority_nat_hero if priority_faction == "nat" else priority_roy_hero
            )
            second_priority = (
                priority_roy_hero if priority_faction == "nat" else priority_nat_hero
            )

            # Add first priority hero if it exists
            if first_priority and first_priority in remaining_heroes:
                prioritized_heroes.append(first_priority)
                remaining_heroes.remove(first_priority)
                print(f"First priority hero: {first_priority}")

            # Add second priority hero if it exists
            if second_priority and second_priority in remaining_heroes:
                prioritized_heroes.append(second_priority)
                remaining_heroes.remove(second_priority)
                print(f"Second priority hero: {second_priority}")
        else:
            print("No priority settings found, will try all heroes in order")

        # Combine prioritized heroes with remaining ones
        all_heroes_in_order = prioritized_heroes + remaining_heroes
        print(f"Will try redeeming code in this order: {all_heroes_in_order}")

        # Try redeeming for each hero in priority order
        success = False
        for hero_name in all_heroes_in_order:
            hero_id = heroes[hero_name]
            print(
                f"\nAttempting to redeem code '{code}' for hero {hero_name} (ID: {hero_id})"
            )

            # Call redeem_code with a special flag to minimize output
            result = self._redeem_code_minimal_output(code, hero_id)

            if result:
                print(f"Successfully redeemed code '{code}' for hero {hero_name}")
                success = True
                # We don't break here because we want to try for all heroes
            else:
                print(f"Failed to redeem code '{code}' for hero {hero_name}")

        return success

    def _redeem_code_minimal_output(self, code: str, hero_id: str) -> bool:
        """
        Internal version of redeem_code with minimal output
        """
        # Get the CSRF token
        token = self.extract_token()
        if not token:
            print(f"No CSRF token found")
            return False

        # Ensure hero_id is a string
        hero_id = str(hero_id)

        # Prepare the payload
        payload = {"_token": token, "hero": hero_id, "code": code}

        # Set up headers similar to the manual request
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.base_url + "profile",
            "Origin": self.base_url.rstrip("/"),
            "Accept": "*/*",
        }

        # Make the request
        try:
            redeem_url = self.base_url + "profile/redeem"
            response = self.session.post(redeem_url, data=payload, headers=headers)

            # Print minimal output
            print(f"Response status code: {response.status_code}")

            # Check if the request was successful
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"Response content: {result}")

                    # Handle both list and dictionary responses
                    if isinstance(result, dict) and "error" in result:
                        return False
                    elif (
                        isinstance(result, list)
                        and len(result) >= 2
                        and result[0] == "error"
                    ):
                        return False

                    return True
                except json.JSONDecodeError:
                    print(f"Response: {response.text}")
                    return True
            else:
                print(f"Response: {response.text}")
                return False

        except Exception as e:
            print(f"Error: {e}")
            return False


def main() -> None:
    """
    Main function
    """
    load_dotenv(override=True)

    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    base_url = os.getenv("BASEURL")

    if not all([username, password, base_url]):
        print("Error: Missing required environment variables. Please check .env file.")
        sys.exit(1)

    # Get authenticated session and possibly response
    session, response = get_authenticated_session(base_url, username, password)

    if not session:
        print("Failed to authenticate. Exiting.")
        sys.exit(1)

    # Initialize code redeemer with existing response if available
    redeemer = CodeRedeemer(session, base_url, response)

    # Display hero information
    heroes = redeemer.extract_hero_ids()
    print("\nAvailable heroes:")
    for name, hero_id in heroes.items():
        print(f"  {name}: {hero_id}")

    # Example code redemption
    code = "MS15-NATG-1000"  # Replace with actual code to redeem
    print(f"\n--- Attempting to redeem code: {code} ---")
    redeemer.redeem_code_with_priority(code)

    print("\nAuthentication successful. Ready for more codes.")


if __name__ == "__main__":
    main()
