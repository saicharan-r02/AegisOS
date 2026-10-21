"""Lightweight syntax diagnostics for common text edits."""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path


def syntax_diagnostics(path: Path, content: str) -> list[str]:
    """Return syntax errors for formats with standard-library parsers."""
    suffix=path.suffix.lower()
    try:
        if suffix == ".py":
            ast.parse(content,filename=str(path))
        elif suffix == ".json":
            json.loads(content)
        elif suffix == ".toml":
            tomllib.loads(content)
    except SyntaxError as exc:
        return [f"SyntaxError at line {exc.lineno}: {exc.msg}"]
    except (json.JSONDecodeError,tomllib.TOMLDecodeError) as exc:
        line=getattr(exc,"lineno",None)
        location=f" at line {line}" if line else ""
        return [f"SyntaxError{location}: {exc}"]
    return []
