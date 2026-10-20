from typing import List

def split_csv_line(line: str) -> List[str]:
    # BUG: Naive split breaks on quoted commas
    return [col.strip() for col in line.split(",")]
