"""Configuration validation and parsing package."""

from aegis_os.config.validator import AegisTomlSchema, validate_config_file

__all__ = ["AegisTomlSchema", "validate_config_file"]
