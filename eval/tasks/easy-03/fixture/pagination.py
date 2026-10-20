from typing import Any, List

def paginate(items: List[Any], page: int, page_size: int) -> List[Any]:
    """Return items for a 1-indexed page number."""
    # BUG: Using 0-indexed formula for 1-indexed page
    start = page * page_size
    end = start + page_size
    return items[start:end]
