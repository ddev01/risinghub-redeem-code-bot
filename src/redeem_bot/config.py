"""Application configuration loaded from environment and JSON account files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AccountSettings(BaseModel):
    """Per-account hero priority configuration."""

    username: str
    password: str
    priority_heroes: list[str] = Field(default_factory=list)
    heroes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_priority_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "priority_heroes" in data:
            return data

        heroes: list[str] = []
        faction = str(data.get("priority_faction", "nat")).lower()
        nat = data.get("priority_nat_hero")
        roy = data.get("priority_roy_hero")
        if nat or roy:
            first = nat if faction == "nat" else roy
            second = roy if faction == "nat" else nat
            if first:
                heroes.append(str(first))
            if second and second != first:
                heroes.append(str(second))

        migrated = dict(data)
        migrated["priority_heroes"] = heroes
        return migrated


class AccountsFileSettings(BaseModel):
    """Global settings block from accounts JSON."""

    rate_limit_delay: float = 2.0
    account_delay_multiplier: float = 2.0


class AccountsConfig(BaseModel):
    """Full accounts JSON document."""

    accounts: list[AccountSettings]
    settings: AccountsFileSettings = Field(default_factory=AccountsFileSettings)


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    risinghub_base_url: str = Field(
        default="https://example.test/",
        validation_alias="RISINGHUB_BASE_URL",
    )
    discord_user_token: str | None = Field(default=None, validation_alias="DISCORD_USER_TOKEN")
    discord_channel_ids: str = Field(default="", validation_alias="DISCORD_CHANNEL_IDS")
    discord_fetch_since: str | None = Field(default=None, validation_alias="DISCORD_FETCH_SINCE")
    discord_webhook_url: str | None = Field(default=None, validation_alias="DISCORD_WEBHOOK_URL")
    discord_webhook_debug: bool = Field(default=False, validation_alias="DISCORD_WEBHOOK_DEBUG")
    discord_guild_id: str | None = Field(default=None, validation_alias="DISCORD_GUILD_ID")

    accounts_file: Path = Field(default=Path("config/accounts.json"), validation_alias="ACCOUNTS_FILE")
    data_dir: Path = Field(default=Path("data"), validation_alias="DATA_DIR")
    sqlite_path: Path | None = Field(default=None, validation_alias="SQLITE_PATH")

    @field_validator("risinghub_base_url")
    @classmethod
    def _ensure_trailing_slash(cls, value: str) -> str:
        return value if value.endswith("/") else f"{value}/"

    @property
    def channel_id_list(self) -> list[str]:
        if not self.discord_channel_ids.strip():
            return []
        return [part.strip() for part in self.discord_channel_ids.split(",") if part.strip()]

    @property
    def state_db_path(self) -> Path:
        if self.sqlite_path is not None:
            return self.sqlite_path
        return self.data_dir / "state.sqlite"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache" / "messages"

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    def load_accounts(self) -> AccountsConfig:
        path = self.accounts_file
        if not path.exists():
            raise FileNotFoundError(
                f"Accounts file not found: {path}. "
                f"Copy config/accounts.example.json to {path} and edit."
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AccountsConfig.model_validate(raw)

    def ensure_data_dirs(self) -> None:
        for directory in (
            self.data_dir,
            self.cache_dir,
            self.sessions_dir,
            self.data_dir / "reports",
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
