import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from typing import Optional, Union, Dict, List, Any, Tuple
import sys
import json
import time
from pathlib import Path
import csv
from datetime import datetime


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
        self.cookie_file = cookie_file

        # Set browser-like headers but leave out Accept-Encoding to let requests handle compression
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    def login(self, username: str, password: str) -> Optional[requests.Session]:
        """
        Attempts to log in with the provided credentials
        """
        print(f"Attempting login for user: {username}")

        try:
            login_url = self.base_url + "login"
            print(f"Login URL: {login_url}")

            # Remove Accept-Encoding header if it exists to let requests handle compression
            self.session.headers.pop("Accept-Encoding", None)

            print("Fetching login page...")
            response = self.session.get(login_url, timeout=10)
            print(f"Login page status code: {response.status_code}")

            # Parse the HTML to find the token
            print("Searching for CSRF token...")
            soup = BeautifulSoup(response.text, "html.parser")
            token_input = soup.find("input", {"name": "_token"})

            if not token_input:
                print("Error: Could not find CSRF token on login page")
                return None

            token = token_input["value"]
            print(f"Found CSRF token: {token[:5]}...{token[-5:]}")

            login_data = {
                "_token": token,
                "username": username,
                "password": password,
                "submit": "",
            }

            # Make the login request with allow_redirects=False to see the redirect location
            print(f"Sending login request to {login_url}")
            login_response = self.session.post(
                login_url, data=login_data, allow_redirects=False, timeout=10
            )

            # Check if login was successful based on the redirect location
            if login_response.status_code == 302:
                redirect_location = login_response.headers.get("location", "")
                print(f"Login response: Status 302, Redirect to: {redirect_location}")

                # Successful login redirects to the base URL or profile, failed login redirects back to login
                if "/login" not in redirect_location:
                    print(f"Login successful for user: {username}!")
                    self.save_cookies()
                    return self.session

            # If we get here, login failed
            print(
                f"Login failed for user: {username}. Response code: {login_response.status_code}"
            )
            return None

        except requests.exceptions.Timeout:
            print(f"Login request timed out for user: {username}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"Connection error during login for user: {username}")
            print("Check your network connection and make sure the site is accessible")
            return None
        except Exception as e:
            print(f"Unexpected error during login: {str(e)}")
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


class CSVLogger:
    """
    Handles logging redemption results to CSV files
    """

    def __init__(
        self,
        success_log_file: str = "logs/redemption_success.csv",
        failure_log_file: str = "logs/redemption_failure.csv",
        info_log_file: str = "logs/redemption_info.csv",
    ):
        """
        Initialize with file paths for success, failure and info logs
        """
        # Ensure logs directory exists
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)

        self.success_log_file = success_log_file
        self.failure_log_file = failure_log_file
        self.info_log_file = info_log_file

        # Ensure files exist with headers
        self._initialize_success_log()
        self._initialize_failure_log()
        self._initialize_info_log()

    def _initialize_success_log(self) -> None:
        """
        Initialize success log file with headers if it doesn't exist
        """
        log_path = Path(self.success_log_file)
        log_path.parent.mkdir(exist_ok=True)  # Ensure parent directory exists

        if not log_path.exists():
            with open(self.success_log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Timestamp",
                        "Hero Name",
                        "Hero ID",
                        "Item ID",
                        "Duration Type",
                        "Duration/Count",
                        "Item Name",
                        "Category",
                        "Code Used",
                    ]
                )

    def _initialize_failure_log(self) -> None:
        """
        Initialize failure log file with headers if it doesn't exist
        """
        log_path = Path(self.failure_log_file)
        log_path.parent.mkdir(exist_ok=True)  # Ensure parent directory exists

        if not log_path.exists():
            with open(self.failure_log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Timestamp",
                        "Hero Name",
                        "Hero ID",
                        "Code Used",
                        "Response Status",
                        "Error Type",
                        "Error Message",
                        "Raw Response",
                    ]
                )

    def _initialize_info_log(self) -> None:
        """
        Initialize info log file with headers if it doesn't exist
        For logging informational responses (wrong hero class, already redeemed, etc.)
        """
        log_path = Path(self.info_log_file)
        log_path.parent.mkdir(exist_ok=True)  # Ensure parent directory exists

        if not log_path.exists():
            with open(self.info_log_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "Timestamp",
                        "Hero Name",
                        "Hero ID",
                        "Code Used",
                        "Response Status",
                        "Info Type",
                        "Message",
                        "Potential Items",
                        "Raw Response",
                    ]
                )

    def log_success(
        self, hero_name: str, hero_id: str, code: str, items_data: Dict[str, List]
    ) -> None:
        """
        Log successful redemption items to CSV
        Items data format: {'item_id': [duration_type, duration, name, category]}
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Log each item as a separate row
        with open(self.success_log_file, "a", newline="") as f:
            writer = csv.writer(f)

            for item_id, details in items_data.items():
                if len(details) >= 4:
                    duration_type = details[0]
                    duration = details[1]
                    item_name = details[2]
                    category = details[3]

                    writer.writerow(
                        [
                            timestamp,
                            hero_name,
                            hero_id,
                            item_id,
                            duration_type,
                            duration,
                            item_name,
                            category,
                            code,
                        ]
                    )
                else:
                    # Handle unexpected item format
                    writer.writerow(
                        [
                            timestamp,
                            hero_name,
                            hero_id,
                            item_id,
                            "unknown",
                            "unknown",
                            "unknown",
                            "unknown",
                            code,
                        ]
                    )

        print(
            f"Logged {len(items_data)} successful item redemptions to {self.success_log_file}"
        )

    def log_info(
        self,
        hero_name: str,
        hero_id: str,
        code: str,
        response_status: int,
        info_type: str,
        message: str,
        potential_items: str = "",
        raw_response: str = "",
    ) -> None:
        """
        Log informational responses to CSV
        For cases like wrong hero class, code already redeemed, etc.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.info_log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    timestamp,
                    hero_name,
                    hero_id,
                    code,
                    response_status,
                    info_type,
                    message,
                    potential_items,
                    raw_response,
                ]
            )

    def log_failure(
        self,
        hero_name: str,
        hero_id: str,
        code: str,
        response_status: int,
        error_type: str,
        error_message: str,
        raw_response: str = "",
    ) -> None:
        """
        Log failed redemption to CSV for actual errors (not info responses)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.failure_log_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    timestamp,
                    hero_name,
                    hero_id,
                    code,
                    response_status,
                    error_type,
                    error_message,
                    raw_response,
                ]
            )

        print(f"Logged failure to {self.failure_log_file}: {error_type}")


class CodeRedeemer:
    """
    Handles code redemption functionality
    """

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        response: Optional[requests.Response] = None,
        logger: Optional[CSVLogger] = None,
    ):
        """
        Initialize with an authenticated session and optional response
        """
        self.session = session
        self.base_url = base_url
        self.redeem_page_response = response
        self.logger = logger or CSVLogger()

        # If we don't have a response yet, get one
        if not self.redeem_page_response:
            self.redeem_page_response = self.session.get(
                self.base_url + "profile#redeem-panel"
            )

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
        return heroes

    def redeem_code(
        self,
        code: str,
        hero_id: Optional[Union[str, int]] = None,
        hero_name: Optional[str] = None,
    ) -> bool:
        """
        Redeem a code using the authenticated session
        If hero_name is not provided, will try to find it from hero_id
        """
        # Get the CSRF token
        token = self.extract_token()
        if not token:
            if hero_name and hero_id:
                self.logger.log_failure(
                    hero_name=hero_name,
                    hero_id=str(hero_id),
                    code=code,
                    response_status=0,
                    error_type="token_error",
                    error_message="No CSRF token found",
                    raw_response="",
                )
            print(f"No CSRF token found")
            return False

        # If hero_id wasn't provided, try to extract it
        heroes_dict = None
        if not hero_id:
            heroes_dict = self.extract_hero_ids()
            if not heroes_dict:
                self.logger.log_failure(
                    hero_name="unknown",
                    hero_id="unknown",
                    code=code,
                    response_status=0,
                    error_type="hero_error",
                    error_message="No heroes found",
                    raw_response="",
                )
                print(f"Failed to redeem code '{code}': No heroes found")
                return False

            # Use the first hero if none specified
            hero_id = list(heroes_dict.values())[0]
            hero_name = list(heroes_dict.keys())[0]
            print(f"No hero specified, using: {hero_name}")

        # Ensure hero_id is a string
        hero_id = str(hero_id)

        # If hero_name wasn't provided, try to find it from the hero_id
        if not hero_name:
            if not heroes_dict:
                heroes_dict = self.extract_hero_ids()

            # Look up the hero name from the ID
            for name, id_val in heroes_dict.items():
                if str(id_val) == hero_id:
                    hero_name = name
                    break

            if not hero_name:
                hero_name = f"unknown_hero_{hero_id}"

        # Prepare the payload
        payload = {"_token": token, "hero": hero_id, "code": code}

        # Set up headers
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

                    # Handle successful redemption
                    if (
                        isinstance(result, list)
                        and len(result) >= 2
                        and result[0] == "success"
                    ):
                        # Extract items data
                        items_data = result[1] if len(result) > 1 else {}

                        # Log successful redemption
                        if items_data:
                            self.logger.log_success(
                                hero_name=hero_name,
                                hero_id=hero_id,
                                code=code,
                                items_data=items_data,
                            )
                        return True

                    # Handle special case for wrong hero class/faction
                    elif (
                        isinstance(result, list)
                        and len(result) >= 2
                        and result[0] == "error"
                    ):
                        error_data = result[1]

                        # Case 1: Already redeemed code
                        if (
                            isinstance(error_data, str)
                            and "can't use this code again" in error_data
                        ):
                            self.logger.log_info(
                                hero_name=hero_name,
                                hero_id=hero_id,
                                code=code,
                                response_status=response.status_code,
                                info_type="already_redeemed",
                                message="Code already redeemed",
                                raw_response=str(result),
                            )
                            return False

                        # Case 2: Wrong hero class/faction but shows potential items
                        elif isinstance(error_data, dict):
                            # Extract potential item names from the error
                            potential_items = []
                            for item_id, item_info in error_data.items():
                                if isinstance(item_info, list) and len(item_info) > 0:
                                    potential_items.append(f"{item_id}: {item_info[0]}")
                                else:
                                    potential_items.append(f"{item_id}: unknown")

                            self.logger.log_info(
                                hero_name=hero_name,
                                hero_id=hero_id,
                                code=code,
                                response_status=response.status_code,
                                info_type="wrong_hero_class",
                                message="Wrong hero class or faction for this code",
                                potential_items=", ".join(potential_items),
                                raw_response=str(result),
                            )
                            return False
                        # Case 3: Other error messages
                        else:
                            self.logger.log_info(
                                hero_name=hero_name,
                                hero_id=hero_id,
                                code=code,
                                response_status=response.status_code,
                                info_type="other_info",
                                message=str(error_data),
                                raw_response=str(result),
                            )
                            return False
                    else:
                        # Unexpected response format - treat as actual failure
                        self.logger.log_failure(
                            hero_name=hero_name,
                            hero_id=hero_id,
                            code=code,
                            response_status=response.status_code,
                            error_type="unexpected_format",
                            error_message="Unexpected response format",
                            raw_response=str(result),
                        )
                        return False

                except json.JSONDecodeError:
                    # Non-JSON response
                    self.logger.log_failure(
                        hero_name=hero_name,
                        hero_id=hero_id,
                        code=code,
                        response_status=response.status_code,
                        error_type="json_error",
                        error_message="Invalid JSON response",
                        raw_response=response.text[:500],  # Limit to 500 chars
                    )
                    print(f"Response: {response.text}")
                    return False
            else:
                # Non-200 response
                self.logger.log_failure(
                    hero_name=hero_name,
                    hero_id=hero_id,
                    code=code,
                    response_status=response.status_code,
                    error_type="http_error",
                    error_message=f"HTTP error {response.status_code}",
                    raw_response=response.text[:500],  # Limit to 500 chars
                )
                print(f"Response: {response.text}")
                return False

        except Exception as e:
            # Exception during request
            self.logger.log_failure(
                hero_name=hero_name,
                hero_id=hero_id,
                code=code,
                response_status=0,
                error_type="exception",
                error_message=str(e),
                raw_response=type(e).__name__,
            )
            print(f"Error: {e}")
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
            self.logger.log_failure(
                hero_name="unknown",
                hero_id="unknown",
                code=code,
                response_status=0,
                error_type="hero_error",
                error_message="No heroes found",
                raw_response="",
            )
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

            # Add second priority hero if it exists
            if second_priority and second_priority in remaining_heroes:
                prioritized_heroes.append(second_priority)
                remaining_heroes.remove(second_priority)

        # Combine prioritized heroes with remaining ones
        all_heroes_in_order = prioritized_heroes + remaining_heroes
        print(f"Will try redeeming code in this order: {all_heroes_in_order}")

        # For debugging: If you want to test with just one specific hero, uncomment and modify this line:
        # all_heroes_in_order = [all_heroes_in_order[0]]  # Only use first hero in list
        # all_heroes_in_order = [""]  # Only use a specific hero by name

        # Try redeeming for each hero in priority order
        overall_success = False
        for hero_name in all_heroes_in_order:
            hero_id = heroes[hero_name]
            print(
                f"\nAttempting to redeem code '{code}' for hero {hero_name} (ID: {hero_id})"
            )

            # Call the consolidated redeem_code method with hero name
            result = self.redeem_code(code, hero_id, hero_name)

            if result:
                overall_success = True

        return overall_success


def load_redemption_codes(file_path: str) -> list[str]:
    """
    Load redemption codes from a file, one code per line
    Lines starting with # are treated as comments and ignored
    """
    codes = []
    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    codes.append(line)

        print(f"Loaded {len(codes)} redemption codes from {file_path}")
        return codes
    except FileNotFoundError:
        print(f"Redemption codes file not found: {file_path}")
        return []
    except Exception as e:
        print(f"Error loading redemption codes: {e}")
        return []


def main() -> None:
    """
    Main function
    """
    load_dotenv(override=True)

    username = os.getenv("USERNAME")
    password = os.getenv("PASSWORD")
    base_url = os.getenv("BASEURL")

    # Get codes file path from environment or use default
    codes_file = os.getenv("CODES_FILE", "redemption_codes.txt")

    # Get rate limit delay (in seconds) from environment or use default
    rate_limit_delay = float(os.getenv("RATE_LIMIT_DELAY", "0.3"))

    if not all([username, password, base_url]):
        print("Error: Missing required environment variables. Please check .env file.")
        sys.exit(1)

    # Get authenticated session and possibly response
    session, response = get_authenticated_session(base_url, username, password)

    if not session:
        print("Failed to authenticate. Exiting.")
        sys.exit(1)

    # Create logger with customizable file paths
    logger = CSVLogger(
        success_log_file=os.getenv("SUCCESS_LOG", "logs/redemption_success.csv"),
        failure_log_file=os.getenv("FAILURE_LOG", "logs/redemption_failure.csv"),
        info_log_file=os.getenv("INFO_LOG", "logs/redemption_info.csv"),
    )

    # Initialize code redeemer with existing response if available
    redeemer = CodeRedeemer(session, base_url, response, logger)

    # Load redemption codes from file
    codes = load_redemption_codes(codes_file)
    if not codes:
        print(
            f"No redemption codes found in {codes_file}. Please add codes to this file."
        )
        print(
            "Format: One code per line. Lines starting with # are treated as comments."
        )
        # Create an example file if it doesn't exist
        if not os.path.exists(codes_file):
            with open(codes_file, "w") as f:
                f.write("# Add your redemption codes here, one per line\n")
                f.write("# Example: ABCD-1234-XYZ\n")
            print(f"Created example file at {codes_file}")
        sys.exit(0)

    # Process each code with rate limiting
    print(
        f"\nProcessing {len(codes)} redemption codes with {rate_limit_delay} second(s) delay between attempts..."
    )

    for i, code in enumerate(codes):
        print(f"\n--- [{i+1}/{len(codes)}] Attempting to redeem code: {code} ---")
        redeemer.redeem_code_with_priority(code)

        # Sleep between redemptions to avoid rate limiting (except after the last one)
        if i < len(codes) - 1 and rate_limit_delay > 0:
            print(f"Waiting {rate_limit_delay} second(s) before next redemption...")
            time.sleep(rate_limit_delay)

    print("\nRedemption process complete. Check CSV logs for details.")
    print(f"  Success log: {logger.success_log_file}")
    print(f"  Info log: {logger.info_log_file}")
    print(f"  Failure log: {logger.failure_log_file}")


if __name__ == "__main__":
    main()
