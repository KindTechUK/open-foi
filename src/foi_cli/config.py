"""Configuration loader for foi-cli. Reads ~/.config/foi-cli/config.toml."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


CONFIG_PATH = Path.home() / ".config" / "foi-cli" / "config.toml"


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl: int = 3600
    path: str = ""


@dataclass
class Config:
    rate_limit: float = 1.0
    timeout: float = 30.0
    max_retries: int = 3
    default_format: str = "json"
    fetch_output_dir: str = "./foi-data"
    cache: CacheConfig = field(default_factory=CacheConfig)


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    if not path.exists():
        return Config()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    cache_data = data.get("cache", {})
    return Config(
        rate_limit=data.get("rate_limit", 1.0),
        timeout=data.get("timeout", 30.0),
        max_retries=data.get("max_retries", 3),
        default_format=data.get("default_format", "json"),
        fetch_output_dir=data.get("fetch_output_dir", "./foi-data"),
        cache=CacheConfig(
            enabled=cache_data.get("enabled", True),
            ttl=cache_data.get("ttl", 3600),
            path=cache_data.get("path", ""),
        ),
    )
