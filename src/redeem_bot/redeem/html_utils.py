"""HTML parsing helpers for RisingHub profile pages."""

from __future__ import annotations

from bs4 import BeautifulSoup


def get_token_from_html(html_content: str, token_name: str = "_token") -> str | None:
    try:
        soup = BeautifulSoup(html_content, "html.parser")

        meta_token = soup.find("meta", {"name": token_name})
        if meta_token and meta_token.get("content"):
            return meta_token["content"]

        input_token = soup.find("input", {"name": token_name})
        if input_token and input_token.get("value"):
            return input_token["value"]

        return None
    except Exception:
        return None


def extract_select_options(html_content: str, select_name: str) -> dict[str, str]:
    options: dict[str, str] = {}
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
