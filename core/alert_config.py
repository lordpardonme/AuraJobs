"""
AuraJobs Alert Configuration Loader
Loads and validates alerts.yaml with Pydantic models.
All secrets are sourced from environment variables.
"""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class ScheduleConfig(BaseModel):
    cron: str = "0 8 * * *"
    timezone: str = ""

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        # Basic cron validation - 5 or 6 fields
        parts = v.strip().split()
        if len(parts) not in (5, 6):
            raise ValueError(f"Invalid cron expression: '{v}'. Expected 5 or 6 fields.")
        return v


class TelegramConfig(BaseModel):
    enabled: bool = True
    min_match_score: int = Field(default=75, ge=0, le=100)
    max_alert_cards: int = Field(default=5, ge=1, le=20)
    send_csv_digest: bool = True
    include_visa_sponsored: bool = True
    include_relocation: bool = True


class FiltersConfig(BaseModel):
    regions: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    visa_required: bool = False
    relocation_required: bool = False
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: list[str]) -> list[str]:
        valid = {"India", "Middle East", "Global"}
        for r in v:
            if r not in valid:
                raise ValueError(f"Invalid region: '{r}'. Valid: {valid}")
        return v

    @field_validator("seniority")
    @classmethod
    def validate_seniority(cls, v: list[str]) -> list[str]:
        valid = {"Intern", "Junior", "Mid-Level", "Senior", "Staff", "Lead", "Principal", "Any"}
        for s in v:
            if s not in valid:
                raise ValueError(f"Invalid seniority: '{s}'. Valid: {valid}")
        return v


class DeduplicationConfig(BaseModel):
    enabled: bool = True
    ttl_days: int = Field(default=30, ge=1, le=365)
    store_type: str = "sqlite"
    db_path: str = "alerts/alert_state.db"

    @field_validator("store_type")
    @classmethod
    def validate_store_type(cls, v: str) -> str:
        if v not in ("sqlite", "json"):
            raise ValueError(f"store_type must be 'sqlite' or 'json', got '{v}'")
        return v


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file_path: str = "alerts/alerts.log"
    json_format: bool = False

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR"}
        v_upper = v.upper()
        if v_upper not in valid:
            raise ValueError(f"Invalid log level: '{v}'. Valid: {valid}")
        return v_upper


class AlertConfig(BaseModel):
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # Runtime-resolved secrets (not from YAML)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    def load_secrets_from_env(self) -> None:
        """Load secrets from environment variables."""
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    def validate_secrets(self) -> list[str]:
        """Return list of missing required secrets."""
        missing = []
        if self.telegram.enabled:
            if not self.telegram_bot_token:
                missing.append("TELEGRAM_BOT_TOKEN")
            if not self.telegram_chat_id:
                missing.append("TELEGRAM_CHAT_ID")
        return missing


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "alerts.yaml"


def load_alert_config(config_path: str | None = None) -> AlertConfig:
    """
    Load alert configuration from YAML file and environment variables.

    Args:
        config_path: Optional path to alerts.yaml. Defaults to config/alerts.yaml.

    Returns:
        Validated AlertConfig with secrets loaded from env.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(f"Alert config not found at {path}. Run 'python alerts.py --setup' to create it.")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = AlertConfig(**raw)
    config.load_secrets_from_env()
    return config


def save_alert_config(config: AlertConfig, config_path: str | None = None) -> bool:
    """
    Save alert configuration to YAML file (without secrets).
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # Dump without runtime secrets
    data = config.model_dump(exclude={"telegram_bot_token", "telegram_chat_id"})

    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save alert config: {e}")
        return False


if __name__ == "__main__":
    # Quick validation test
    try:
        cfg = load_alert_config()
        print("[OK] Config loaded successfully")
        print(f"  Schedule: {cfg.schedule.cron}")
        print(f"  Telegram enabled: {cfg.telegram.enabled}")
        missing = cfg.validate_secrets()
        if missing:
            print(f"[WARN] Missing secrets: {missing}")
        else:
            print("[OK] All secrets present")
    except Exception as e:
        print(f"[ERROR] {e}")