"""Configuration loader for the file watcher daemon.

Loads configuration from YAML file with environment variable expansion.
"""

import os
import re
import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class WatcherConfig:
    """Configuration for the file watcher daemon."""

    watch_paths: List[str]
    exclude_patterns: List[str]
    include_extensions: List[str]
    max_file_size_mb: int
    debounce_ms: int
    batch_size: int

    @property
    def max_file_size_bytes(self) -> int:
        """Convert max file size to bytes."""
        return self.max_file_size_mb * 1024 * 1024

    def should_include_file(self, file_path: str) -> bool:
        """Check if file should be indexed based on extension."""
        return any(file_path.endswith(ext) for ext in self.include_extensions)

    def should_exclude_path(self, file_path: str) -> bool:
        """Check if path matches any exclude pattern."""
        path_parts = Path(file_path).parts
        for pattern in self.exclude_patterns:
            # Check if any part of the path matches the pattern
            if pattern.startswith("*."):
                # Extension pattern
                if file_path.endswith(pattern[1:]):
                    return True
            else:
                # Directory pattern
                if pattern in path_parts:
                    return True
        return False


def expand_env_vars(value: str) -> str:
    """Expand environment variables in string.

    Supports both $VAR and ${VAR} syntax.
    """
    if not isinstance(value, str):
        return value

    # Replace ${VAR} syntax
    pattern = re.compile(r'\$\{([^}]+)\}')
    value = pattern.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)

    # Replace $VAR syntax
    pattern = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)')
    value = pattern.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)

    return value


def expand_env_vars_recursive(data):
    """Recursively expand environment variables in nested data structures."""
    if isinstance(data, dict):
        return {key: expand_env_vars_recursive(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [expand_env_vars_recursive(item) for item in data]
    elif isinstance(data, str):
        return expand_env_vars(data)
    else:
        return data


def load_config(config_path: str = None) -> WatcherConfig:
    """Load watcher configuration from YAML file.

    Args:
        config_path: Path to config file. If None, uses default location.

    Returns:
        WatcherConfig instance with loaded configuration.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config is invalid.
    """
    if config_path is None:
        # Default to config/watcher.yaml relative to this file
        base_dir = Path(__file__).parent.parent
        config_path = base_dir / "config" / "watcher.yaml"

    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Load YAML
    with open(config_path, 'r') as f:
        raw_config = yaml.safe_load(f)

    # Expand environment variables
    raw_config = expand_env_vars_recursive(raw_config)

    # Extract watcher section
    if 'watcher' not in raw_config:
        raise ValueError("Configuration must contain 'watcher' section")

    watcher_config = raw_config['watcher']

    # Validate required fields
    required_fields = [
        'watch_paths',
        'exclude_patterns',
        'include_extensions',
        'max_file_size_mb',
        'debounce_ms',
        'batch_size'
    ]

    for field in required_fields:
        if field not in watcher_config:
            raise ValueError(f"Missing required configuration field: {field}")

    # Create config object
    return WatcherConfig(
        watch_paths=watcher_config['watch_paths'],
        exclude_patterns=watcher_config['exclude_patterns'],
        include_extensions=watcher_config['include_extensions'],
        max_file_size_mb=watcher_config['max_file_size_mb'],
        debounce_ms=watcher_config['debounce_ms'],
        batch_size=watcher_config['batch_size']
    )
