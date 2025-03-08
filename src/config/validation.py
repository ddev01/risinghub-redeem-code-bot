"""
Configuration validation for the RisingHub code redemption bot.
"""

from typing import Dict, Any, List, Tuple


def validate_account_config(account_config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate an account configuration.

    Args:
        account_config: The account configuration to validate

    Returns:
        A tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ["username", "password"]
    for field in required_fields:
        if field not in account_config or not account_config[field]:
            return False, f"Missing required field: {field}"

    # Check priority hero settings
    if "priority_faction" in account_config:
        faction = account_config["priority_faction"].lower()
        if faction and faction not in ["nat", "roy"]:
            return (
                False,
                f"Invalid priority faction: {faction}. Must be 'nat' or 'roy'.",
            )

    return True, ""


def validate_settings(settings: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate global settings.

    Args:
        settings: The settings to validate

    Returns:
        A tuple of (is_valid, error_message)
    """
    # Check rate_limit_delay
    if "rate_limit_delay" in settings:
        try:
            rate_limit_delay = float(settings["rate_limit_delay"])
            if rate_limit_delay < 0:
                return False, "rate_limit_delay must be a non-negative number"
        except ValueError:
            return False, "rate_limit_delay must be a number"

    # Check codes_file
    if "codes_file" in settings and not settings["codes_file"]:
        return False, "codes_file cannot be empty"

    return True, ""


def validate_heroes_data(heroes: Dict[str, str]) -> Tuple[bool, str]:
    """
    Validate hero data.

    Args:
        heroes: Dictionary mapping hero names to hero IDs

    Returns:
        A tuple of (is_valid, error_message)
    """
    for hero_name, hero_id in heroes.items():
        if not hero_name:
            return False, "Hero name cannot be empty"
        if not hero_id:
            return False, f"Hero ID for {hero_name} cannot be empty"
        try:
            int(hero_id)  # Hero IDs should be integers
        except ValueError:
            return False, f"Hero ID for {hero_name} must be a number, got: {hero_id}"

    return True, ""


def validate_full_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate the full configuration.

    Args:
        config: The full configuration

    Returns:
        A list of error messages, empty if valid
    """
    errors = []

    # Check if accounts is present and is a list
    if "accounts" not in config:
        errors.append("Missing 'accounts' section")
        return errors

    if not isinstance(config["accounts"], list):
        errors.append("'accounts' must be a list")
        return errors

    # Validate each account
    for i, account in enumerate(config["accounts"]):
        valid, error = validate_account_config(account)
        if not valid:
            errors.append(
                f"Account {i+1} ({account.get('username', 'unknown')}): {error}"
            )

        # Validate heroes if present
        if "heroes" in account and account["heroes"]:
            valid, error = validate_heroes_data(account["heroes"])
            if not valid:
                errors.append(
                    f"Account {i+1} ({account.get('username', 'unknown')}) heroes: {error}"
                )

    # Validate settings
    if "settings" in config:
        valid, error = validate_settings(config["settings"])
        if not valid:
            errors.append(f"Settings: {error}")

    return errors
