from dataclasses import dataclass


@dataclass
class ReportConfig:
    title: str
    author: str
    version: int

def generate_header(cfg: ReportConfig) -> str:
    return f"{cfg.title} by {cfg.author} (v{cfg.version})"
