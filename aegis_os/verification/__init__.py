"""Verification and anti-gaming package for AegisOS."""

from __future__ import annotations

from aegis_os.verification.baseline import BaselineVerifier, TestBaseline
from aegis_os.verification.integrity import TestIntegrityGuard
from aegis_os.verification.reviewer import (
    AegisReviewer,
    ReviewDecision,
    ReviewFinding,
    ReviewReport,
)
from aegis_os.verification.tdd import TDDCoordinator, TDDPhase, TDDResult

__all__ = [
    "AegisReviewer",
    "BaselineVerifier",
    "ReviewDecision",
    "ReviewFinding",
    "ReviewReport",
    "TDDCoordinator",
    "TDDPhase",
    "TDDResult",
    "TestBaseline",
    "TestIntegrityGuard",
]
