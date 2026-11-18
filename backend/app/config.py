from ipaddress import IPv4Interface, IPv4Network
from pathlib import Path
from typing import Literal

from pydantic import Field, PositiveInt, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_NETWORKS = tuple(IPv4Network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PHOTOBOOTH_", env_file=ROOT / ".env", extra="ignore"
    )

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "photobooth_dev"
    db_user: str = "photobooth_app"
    db_password: SecretStr = SecretStr("")
    data_root: Path = ROOT / "data"
    frontend_dir: Path = ROOT / "frontend/dist/photo-booth/browser"
    camera_enabled: bool = True
    download_bind: IPv4Interface | None = None
    download_port: int = Field(default=8001, ge=1, le=65535)
    download_ttl_minutes: PositiveInt = 10
    printer_name: str | None = None
    ai_mode: Literal["disabled", "preview"] = "disabled"

    @field_validator("download_bind")
    @classmethod
    def require_private_download_network(cls, value: IPv4Interface | None) -> IPv4Interface | None:
        if value and not any(value.network.subnet_of(network) for network in PRIVATE_NETWORKS):
            raise ValueError("Use a private IPv4 address and subnet for phone downloads")
        return value

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
