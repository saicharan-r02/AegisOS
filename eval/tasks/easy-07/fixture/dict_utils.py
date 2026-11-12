from typing import Any


def merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    # BUG: Shallow merge destroys nested keys
    result = base.copy()
    result.update(override)
    return result
