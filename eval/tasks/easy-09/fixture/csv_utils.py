

def split_csv_line(line: str) -> list[str]:
    # BUG: Naive split breaks on quoted commas
    return [col.strip() for col in line.split(",")]
