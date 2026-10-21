"""Secret protection with combined regex and Shannon-entropy token detection."""

from __future__ import annotations

import math
import re
from typing import ClassVar


class SecretRedactor:
    """Detects and redacts credentials, API keys, and high-entropy strings."""

    _PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        # Generic API keys and tokens
        re.compile(r"(?i)(?:api_key|apikey|secret|token|password|auth_token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{16,})['\"]?"),
        # OpenAI style
        re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),
        # Anthropic style
        re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
        # Groq style
        re.compile(r"gsk_[A-Za-z0-9_\-]{20,}"),
        # GitHub tokens
        re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
        # Bearer tokens
        re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}"),
        # AWS credentials
        re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[A-Z0-9]{16}"),
    ]

    def __init__(self, entropy_threshold: float = 4.2, min_length: int = 24) -> None:
        self.entropy_threshold = entropy_threshold
        self.min_length = min_length

    @staticmethod
    def calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy for a given string."""
        if not text:
            return 0.0
        prob = [float(text.count(c)) / len(text) for c in set(text)]
        return -sum(p * math.log2(p) for p in prob)

    def redact(self, text: str) -> str:
        """Redact known secret patterns and high-entropy secret tokens."""
        if not text:
            return text

        result = text
        # 1. Regex redaction
        for pattern in self._PATTERNS:
            result = pattern.sub("[REDACTED_SECRET]", result)

        # 2. Entropy-based token inspection for remaining unflagged words
        words = result.split()
        modified_words: list[str] = []
        for word in words:
            clean_word = word.strip("\"'()[]{},;:")
            if len(clean_word) >= self.min_length:
                # Discard file paths and URLs from entropy check
                if "/" not in clean_word and "\\" not in clean_word and "http" not in clean_word:
                    ent = self.calculate_entropy(clean_word)
                    if ent >= self.entropy_threshold:
                        word = word.replace(clean_word, "[REDACTED_ENTROPY_TOKEN]")
            modified_words.append(word)

        return " ".join(modified_words)
