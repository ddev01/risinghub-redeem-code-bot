"""
File operation utilities for the RisingHub code redemption bot.
"""

import json
import csv
from pathlib import Path
from typing import Dict, Any, List, Optional


def ensure_directory_exists(directory_path: str) -> None:
    """
    Ensure that a directory exists, creating it if necessary.

    Args:
        directory_path: The path to the directory to ensure exists
    """
    Path(directory_path).mkdir(exist_ok=True, parents=True)


def remove_comments_from_json(json_str: str) -> str:
    """
    Remove JavaScript-style comments from JSON string.

    Args:
        json_str: The JSON string with comments

    Returns:
        A cleaned JSON string without comments
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


def load_json_with_comments(file_path: str) -> Dict[str, Any]:
    """
    Load a JSON file that may contain comments.

    Args:
        file_path: Path to the JSON file

    Returns:
        The parsed JSON data as a dictionary

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the JSON is invalid
    """
    with open(file_path, "r") as f:
        content = remove_comments_from_json(f.read())
        return json.loads(content)


def save_json(data: Dict[str, Any], file_path: str, use_tabs: bool = True) -> None:
    """
    Save data to a JSON file.

    Args:
        data: The data to save
        file_path: The path to save the file to
        use_tabs: Whether to use tabs for indentation (defaults to True)
    """
    with open(file_path, "w") as f:
        indent = "\t" if use_tabs else 2
        json.dump(data, f, indent=indent)


def initialize_csv_file(file_path: str, headers: List[str]) -> None:
    """
    Initialize a CSV file with headers if it doesn't exist.

    Args:
        file_path: The path to the CSV file
        headers: The column headers to use
    """
    file_path_obj = Path(file_path)
    file_path_obj.parent.mkdir(exist_ok=True, parents=True)

    if not file_path_obj.exists():
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)


def load_file_lines(file_path: str, ignore_comments: bool = True) -> List[str]:
    """
    Load lines from a file, optionally ignoring comment lines.

    Args:
        file_path: The path to the file
        ignore_comments: Whether to ignore lines starting with # and remove inline comments

    Returns:
        A list of lines from the file
    """
    lines = []
    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                # Remove inline comments if needed
                if ignore_comments and "#" in line:
                    line = line.split("#")[0].strip()
                # Skip empty lines and full comment lines if ignoring comments
                if line and (not ignore_comments or not line.startswith("#")):
                    lines.append(line)
        return lines
    except FileNotFoundError:
        return []


def create_sample_codes_file(file_path: str) -> None:
    """
    Create a sample redemption codes file with instructions.

    Args:
        file_path: The path to create the file at
    """
    ensure_directory_exists(Path(file_path).parent)

    with open(file_path, "w") as f:
        f.write("# RisingHub Redemption Codes\n")
        f.write("# Add your codes below, one per line\n")
        f.write("# Lines starting with # are comments and will be ignored\n")
        f.write("# Example:\n")
        f.write("# MS15-ABCD-1234\n")
        f.write("\n")
        f.write("# Your codes here:\n")
