import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from typing import Optional, Union, Dict, List, Any, Tuple, Set
import sys
import json
import time
from pathlib import Path
import csv
from datetime import datetime

# Hardcoded base URL
BASE_URL = "https://risinghub.net/"


class RedeemedCodesManager:
    """
    Manages tracking of redeemed codes across all accounts and heroes
    """

    def __init__(self, file_path: str = "logs/redeemed_codes.csv"):
        """
        Initialize with file path for storing redeemed codes
        """
        self.file_path = file_path
        self.redeemed_codes = {}  # Dict of {username: {hero_name: set(codes)}}

        # Ensure logs directory exists
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        self._load_redeemed_codes()

    def _initialize_file(self) -> None:
        """
        Initialize the redeemed codes file with headers if it doesn't exist
        """
        file_path = Path(self.file_path)

        if not file_path.exists():
            with open(self.file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["Timestamp", "Username", "Hero Name", "Hero ID", "Code", "Status"]
                )

    def _load_redeemed_codes(self) -> None:
        """
        Load previously redeemed codes from CSV file
        """
        self._initialize_file()

        try:
            with open(self.file_path, "r") as f:
                reader = csv.reader(f)
                # Skip header
                next(reader, None)

                account_count = 0
                code_count = 0

                for row in reader:
                    if len(row) >= 5:
                        timestamp, username, hero_name, hero_id, code, status = (
                            row + [""] if len(row) == 5 else row
                        )

                        # Skip invalid entries
                        if not all([username, hero_name, code]):
                            continue

                        # Initialize nested dictionaries if needed
                        if username not in self.redeemed_codes:
                            self.redeemed_codes[username] = {}
                            account_count += 1

                        if hero_name not in self.redeemed_codes[username]:
                            self.redeemed_codes[username][hero_name] = set()

                        # Add code to the set
                        self.redeemed_codes[username][hero_name].add(code)
                        code_count += 1

                if account_count > 0:
                    print(
                        f"Loaded {code_count} redeemed codes for {account_count} accounts"
                    )

        except FileNotFoundError:
            # No need to print anything for a new file
            self._initialize_file()
        except Exception as e:
            print(f"Error loading redeemed codes: {e}")

    def is_code_redeemed(self, username: str, hero_name: str, code: str) -> bool:
        """
        Check if a code has already been redeemed for a specific hero
        """
        return (
            username in self.redeemed_codes
            and hero_name in self.redeemed_codes[username]
            and code in self.redeemed_codes[username][hero_name]
        )

    def mark_as_redeemed(
        self,
        username: str,
        hero_name: str,
        hero_id: str,
        code: str,
        status: str = "success",
    ) -> None:
        """
        Mark a code as redeemed for a specific hero
        """
        # Update in-memory structure
        if username not in self.redeemed_codes:
            self.redeemed_codes[username] = {}

        if hero_name not in self.redeemed_codes[username]:
            self.redeemed_codes[username][hero_name] = set()

        self.redeemed_codes[username][hero_name].add(code)

        # Write to CSV file
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(self.file_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, username, hero_name, hero_id, code, status])

    def get_unredeemed_codes(
        self, username: str, hero_names: List[str], codes: List[str]
    ) -> Dict[str, List[str]]:
        """
        Get codes that haven't been redeemed yet for each hero
        Returns a dictionary with hero names as keys and lists of unredeemed codes as values
        """
        result = {}

        for hero_name in hero_names:
            unredeemed_codes = []

            for code in codes:
                if not self.is_code_redeemed(username, hero_name, code):
                    unredeemed_codes.append(code)

            result[hero_name] = unredeemed_codes

        return result

    def is_fully_redeemed(
        self, username: str, hero_names: List[str], code: str
    ) -> bool:
        """
        Check if a code has been redeemed by all heroes of an account
        Returns True if all heroes have redeemed (or attempted to redeem) the code
        """
        if username not in self.redeemed_codes:
            return False

        # For each hero, check if they've redeemed this code
        for hero_name in hero_names:
            # If any hero hasn't tried this code yet, return False
            if (
                hero_name not in self.redeemed_codes[username]
                or code not in self.redeemed_codes[username][hero_name]
            ):
                return False

        # If we get here, all heroes have redeemed or attempted to redeem this code
        return True


class AccountManager:
    """
    Manages multiple account configurations
    """

    def __init__(self, config_file: str = "accounts.json"):
        """
        Initialize with configuration file path
        """
        self.config_file = config_file
        self.config = self._load_config()

        # Create necessary directories
        self._ensure_directories()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load account configuration from JSON file
        """
        try:
            with open(self.config_file, "r") as f:
                # Remove JavaScript-style comments from JSON
                content = self._remove_comments(f.read())
                config = json.loads(content)

                # Print this only when called directly from __init__, not from other methods
                if not hasattr(self, "config"):
                    print(
                        f"Loaded configuration from {self.config_file} with {len(config.get('accounts', []))} account(s)"
                    )
                return config
        except FileNotFoundError:
            print(f"Configuration file not found: {self.config_file}")
            print("Creating a template configuration file...")
            self._create_template_config()
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON in {self.config_file}: {e}")
            print("Please check the format of your configuration file.")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading configuration: {e}")
            sys.exit(1)

    def _remove_comments(self, json_str: str) -> str:
        """
        Remove JavaScript-style comments from JSON string
        """
        lines = json_str.split("\n")
        result = []

        for line in lines:
            # Remove everything after //
            comment_pos = line.find("//")
            if comment_pos >= 0:
                line = line[:comment_pos]

            # Only add non-empty lines
            if line.strip():
                result.append(line)

        return "\n".join(result)

    def _create_template_config(self) -> None:
        """
        Create a template configuration file
        """
        template = {
            "accounts": [
                {
                    "username": "your_username",
                    "password": "your_password",
                    "priority_nat_hero": "yournatgunner",
                    "priority_roy_hero": "yourroygunner",
                    "priority_faction": "nat",
                    "heroes": {},  # Will store hero information after first login
                }
            ],
            "settings": {"rate_limit_delay": 2.0, "codes_file": "redemption_codes.txt"},
        }

        with open(self.config_file, "w") as f:
            # Use tab indentation to match the user's preference
            json.dump(template, f, indent="\t")

        print(f"Created template configuration file at {self.config_file}")
        print(
            "Please edit this file with your account information and run the script again."
        )

    def _ensure_directories(self) -> None:
        """
        Create necessary directories for sessions and logs
        """
        # Create base directories
        Path("sessions").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Create directories for each account
        for account in self.get_accounts():
            username = account.get("username", "unknown")
            Path(f"sessions/{username}").mkdir(exist_ok=True)
            Path(f"logs/{username}").mkdir(exist_ok=True)

    def get_accounts(self) -> List[Dict[str, Any]]:
        """
        Get all configured accounts
        """
        return self.config.get("accounts", [])

    def get_settings(self) -> Dict[str, Any]:
        """
        Get global settings
        """
        return self.config.get("settings", {})

    def get_cookie_file(self, username: str) -> str:
        """
        Get cookie file path for a specific account
        """
        return f"sessions/{username}/session_cookies.json"

    def get_log_files(self, username: str) -> Dict[str, str]:
        """
        Get log file paths for a specific account
        """
        return {
            "success": f"logs/{username}/{username}_redemption_success.csv",
            "failure": f"logs/{username}/{username}_redemption_failure.csv",
            "info": f"logs/{username}/{username}_redemption_info.csv",
        }

    def update_account_heroes(self, username: str, heroes: Dict[str, str]) -> None:
        """
        Update the heroes information for a specific account
        """
        accounts = self.get_accounts()

        for account in accounts:
            if account.get("username") == username:
                account["heroes"] = heroes
                break

        # Update the config file
        self.config["accounts"] = accounts
        self._save_config()

    def _save_config(self) -> None:
        """
        Save the current configuration to the config file
        """
        with open(self.config_file, "w") as f:
            # Use tab indentation instead of spaces with a size of 4
            json.dump(self.config, f, indent="\t")

        print(f"Updated configuration saved to {self.config_file}")

    def get_account_heroes(self, username: str) -> Dict[str, str]:
        """
        Get the heroes for a specific account
        """
        accounts = self.get_accounts()

        for account in accounts:
            if account.get("username") == username:
                return account.get("heroes", {})

        return {}


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

            # Check if cookies are expired (7 days)
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
    base_url: str, username: str, password: str, cookie_file: str
) -> tuple[Optional[requests.Session], Optional[requests.Response]]:
    """
    Gets an authenticated session either by loading cookies or logging in
    Returns both the session and the response from the redeem panel
    """
    login_manager = LoginManager(base_url, cookie_file=cookie_file)

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
        username: str = "",
        redeemed_codes_manager: Optional[RedeemedCodesManager] = None,
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
        self.username = username
        self.redeemed_codes_manager = redeemed_codes_manager or RedeemedCodesManager()

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

        # Also mark the code as redeemed in our tracking system
        if self.username and self.redeemed_codes_manager:
            self.redeemed_codes_manager.mark_as_redeemed(
                self.username, hero_name, hero_id, code, "success"
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

        # For "already_redeemed" and "wrong_hero_class" cases, track in our system
        if (
            info_type in ["already_redeemed", "wrong_hero_class"]
            and self.username
            and self.redeemed_codes_manager
        ):
            self.redeemed_codes_manager.mark_as_redeemed(
                self.username, hero_name, hero_id, code, info_type
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
            print(f"Error: No CSRF token found")
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

            # Print minimal output for status code
            status_message = f"Response: {response.status_code}"

            # Check if the request was successful
            if response.status_code == 200:
                try:
                    result = response.json()

                    # Handle successful redemption
                    if (
                        isinstance(result, list)
                        and len(result) >= 2
                        and result[0] == "success"
                    ):
                        # Extract items data
                        items_data = result[1] if len(result) > 1 else {}

                        # Show success message with items
                        item_names = []
                        for item_id, details in items_data.items():
                            if len(details) >= 3:  # Make sure we have at least the name
                                item_names.append(details[2])

                        items_str = ", ".join(item_names) if item_names else "no items"
                        print(f"✅ SUCCESS: Code redeemed for {items_str}")

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
                            print(
                                "ℹ️ Already redeemed: Code was already used by this hero"
                            )
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
                                    potential_items.append(item_info[0])
                                else:
                                    potential_items.append(f"Item #{item_id}")

                            item_list = ", ".join(potential_items)
                            print(
                                f"⚠️ Wrong hero: Items available ({item_list}) but wrong hero type"
                            )

                            self.logger.log_info(
                                hero_name=hero_name,
                                hero_id=hero_id,
                                code=code,
                                response_status=response.status_code,
                                info_type="wrong_hero_class",
                                message="Wrong hero class or faction for this code",
                                potential_items=", ".join(
                                    (
                                        f"{item_id}: {item_info[0]}"
                                        if isinstance(item_info, list)
                                        and len(item_info) > 0
                                        else f"{item_id}: unknown"
                                    )
                                    for item_id, item_info in error_data.items()
                                ),
                                raw_response=str(result),
                            )
                            return False
                        # Case 3: Other error messages
                        else:
                            print(f"ℹ️ Info: {error_data}")
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
                        print(f"❌ Error: Unexpected response format - {result}")
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
                    print(f"❌ Error: Invalid JSON response")
                    self.logger.log_failure(
                        hero_name=hero_name,
                        hero_id=hero_id,
                        code=code,
                        response_status=response.status_code,
                        error_type="json_error",
                        error_message="Invalid JSON response",
                        raw_response=response.text[:500],  # Limit to 500 chars
                    )
                    return False
            else:
                # Non-200 response
                print(f"❌ Error: HTTP {response.status_code}")
                self.logger.log_failure(
                    hero_name=hero_name,
                    hero_id=hero_id,
                    code=code,
                    response_status=response.status_code,
                    error_type="http_error",
                    error_message=f"HTTP error {response.status_code}",
                    raw_response=response.text[:500],  # Limit to 500 chars
                )
                return False

        except Exception as e:
            # Exception during request
            print(f"❌ Error: {e}")
            self.logger.log_failure(
                hero_name=hero_name,
                hero_id=hero_id,
                code=code,
                response_status=0,
                error_type="exception",
                error_message=str(e),
                raw_response=type(e).__name__,
            )
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
        print(f"Trying code on {len(all_heroes_in_order)} heroes in priority order")

        # Try redeeming for each hero in priority order
        overall_success = False
        already_redeemed_count = 0
        wrong_hero_count = 0

        for hero_name in all_heroes_in_order:
            hero_id = heroes[hero_name]

            # Call the consolidated redeem_code method with hero name
            result = self.redeem_code(code, hero_id, hero_name)

            if result:
                print(f"✅ Successfully redeemed with hero {hero_name}")
                overall_success = True
                break  # Stop after first success

        return overall_success


def process_account(
    account_config: Dict[str, str],
    codes: List[str],
    rate_limit_delay: float,
    redeemed_codes_manager: RedeemedCodesManager,
) -> bool:
    """
    Process redemption codes for a single account
    Returns True if any server requests were made, False otherwise
    """
    username = account_config.get("username")
    password = account_config.get("password")

    # Use the hardcoded base URL instead of getting it from account_config
    base_url = BASE_URL

    if not all([username, password]):
        print(f"❌ Missing required configuration for account {username}. Skipping.")
        return False

    # Ensure base_url has trailing slash
    if not base_url.endswith("/"):
        base_url += "/"

    # Check if we already have hero information stored
    account_manager = AccountManager()
    stored_heroes = account_manager.get_account_heroes(username)

    # If we have hero information, filter out codes that have already been tried on all heroes
    print(f"\n🧑‍🚀 === Processing account: {username} ===")

    if stored_heroes:
        hero_count = len(stored_heroes)
        print(f"📋 Found {hero_count} heroes in configuration")

        # Filter out codes that have already been redeemed by all heroes
        hero_names = list(stored_heroes.keys())
        unredeemed_codes = []

        for code in codes:
            if not redeemed_codes_manager.is_fully_redeemed(username, hero_names, code):
                unredeemed_codes.append(code)

        if not unredeemed_codes:
            print(f"✅ All codes have already been redeemed for all heroes. Skipping.")
            return False  # No server requests made

        print(f"🔍 Found {len(unredeemed_codes)} codes that need redemption")

        # Update our working codes list
        codes = unredeemed_codes

    # Get cookie file path for this account
    cookie_file = f"sessions/{username}/session_cookies.json"

    # Get authenticated session
    session, response = get_authenticated_session(
        base_url, username, password, cookie_file
    )

    if not session:
        print(f"❌ Failed to authenticate for account {username}. Skipping.")
        return True  # Authentication attempt counts as a server request

    # We've made server requests by this point
    made_server_requests = True

    # Create logger with account-specific paths
    logger = CSVLogger(
        success_log_file=f"logs/{username}/{username}_redemption_success.csv",
        failure_log_file=f"logs/{username}/{username}_redemption_failure.csv",
        info_log_file=f"logs/{username}/{username}_redemption_info.csv",
        username=username,
        redeemed_codes_manager=redeemed_codes_manager,
    )

    # Set environment variables for the account preferences
    # This is used by CodeRedeemer.redeem_code_with_priority
    os.environ["PRIORITY_NAT_HERO"] = account_config.get("priority_nat_hero", "")
    os.environ["PRIORITY_ROY_HERO"] = account_config.get("priority_roy_hero", "")
    os.environ["PRIORITY_FACTION"] = account_config.get("priority_faction", "")

    # Initialize code redeemer
    redeemer = CodeRedeemer(session, base_url, response, logger)

    # Extract hero information
    heroes = redeemer.extract_hero_ids()
    if not heroes:
        print(f"❌ No heroes found for account {username}. Skipping.")
        return True  # We still made server requests

    # Store hero information in accounts.json if it's different from what we have
    if heroes != stored_heroes:
        print(f"📝 Updating hero information ({len(heroes)} heroes)")
        account_manager.update_account_heroes(username, heroes)

    # If we already had hero information, we need to check each code for each hero
    if stored_heroes:
        # Get the detailed unredeemed codes for each hero
        unredeemed_codes_by_hero = redeemed_codes_manager.get_unredeemed_codes(
            username, list(heroes.keys()), codes
        )
        heroes_processed = 0
        codes_processed = 0

        # Process each hero separately with their unredeemed codes
        for hero_name, hero_codes in unredeemed_codes_by_hero.items():
            if not hero_codes:
                continue

            heroes_processed += 1
            hero_id = heroes.get(hero_name)

            if not hero_id:
                print(f"⚠️ Hero {hero_name} not found in current hero list. Skipping.")
                continue

            print(f"🦸 Processing {len(hero_codes)} codes for hero {hero_name}")

            for i, code in enumerate(hero_codes):
                codes_processed += 1
                print(f"🔑 [{i+1}/{len(hero_codes)}] Code: {code}")
                redeemer.redeem_code(code, hero_id, hero_name)

                # Sleep between redemptions to avoid rate limiting (except after the last one)
                if i < len(hero_codes) - 1 and rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)

        print(
            f"🏁 Processed {codes_processed} redemption attempts across {heroes_processed} heroes"
        )
    else:
        # Process each code with rate limiting using priority-based redemption
        print(f"🔄 Processing {len(codes)} redemption codes")

        for i, code in enumerate(codes):
            print(f"🔑 [{i+1}/{len(codes)}] Code: {code}")
            redeemer.redeem_code_with_priority(code)

            # Sleep between redemptions to avoid rate limiting (except after the last one)
            if i < len(codes) - 1 and rate_limit_delay > 0:
                time.sleep(rate_limit_delay)

    print(f"✅ Redemption process complete for account {username}")
    return True  # We made server requests


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
                # Remove inline comments
                if "#" in line:
                    line = line.split("#")[0].strip()
                # Skip empty lines and comment lines
                if line and not line.startswith("#"):
                    codes.append(line)

        if codes:
            print(f"📝 Loaded {len(codes)} redemption codes from {file_path}")
        return codes
    except FileNotFoundError:
        print(f"⚠️ Redemption codes file not found: {file_path}")
        return []
    except Exception as e:
        print(f"❌ Error loading redemption codes: {e}")
        return []


def main() -> None:
    """
    Main function
    """
    # Load configuration from accounts.json
    account_manager = AccountManager()

    # Get accounts and settings
    accounts = account_manager.get_accounts()
    settings = account_manager.get_settings()

    if not accounts:
        print("❌ No accounts configured. Please edit accounts.json and try again.")
        sys.exit(1)

    # Get rate limit delay from settings
    rate_limit_delay = float(settings.get("rate_limit_delay", 2.0))

    # Get codes file path from settings
    codes_file = settings.get("codes_file", "redemption_codes.txt")

    # Load redemption codes
    codes = load_redemption_codes(codes_file)
    if not codes:
        print(
            f"❌ No redemption codes found in {codes_file}. Please add codes to this file."
        )
        print(
            "ℹ️ Format: One code per line. Lines starting with # are treated as comments."
        )
        # Create an example file if it doesn't exist
        if not os.path.exists(codes_file):
            with open(codes_file, "w") as f:
                f.write("# Add your redemption codes here, one per line\n")
                f.write("# Example: ABCD-1234-XYZ\n")
            print(f"📝 Created example file at {codes_file}")
        sys.exit(0)

    # Initialize the redeemed codes manager to track code redemption across all accounts
    redeemed_codes_manager = RedeemedCodesManager()

    # Process each account
    print(f"🚀 Processing {len(accounts)} accounts with {len(codes)} redemption codes")
    for i, account in enumerate(accounts):
        print(f"\n📊 === Account {i+1}/{len(accounts)} ===")

        # Process the account and get whether server requests were made
        server_requests_made = process_account(
            account, codes, rate_limit_delay, redeemed_codes_manager
        )

        # Add a delay between accounts only if server requests were made AND there are more accounts to process
        if server_requests_made and i < len(accounts) - 1:
            delay = max(
                rate_limit_delay * 2, 5.0
            )  # Use at least 5 seconds between accounts
            print(f"⏱️ Waiting {delay} seconds before next account...")
            time.sleep(delay)
        elif i < len(accounts) - 1:
            print("⏭️ Skipping wait time (no server requests made)")

    print("\n🎉 All accounts processed successfully!")


if __name__ == "__main__":
    main()
