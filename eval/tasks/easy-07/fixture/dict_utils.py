from typing import Any, Dict

def merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    # BUG: Shallow merge destroys nested keys
    result = base.copy()
    result.update(override)
    return result
