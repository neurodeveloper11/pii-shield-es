"""DataShield (datashield-es): detección y anonimización local de datos personales en español."""

from .anonymize import (
    MODES,
    AnonymizationResult,
    PseudonymTable,
    anonymize,
    anonymize_detailed,
    deanonymize,
)
from .detectors import detect
from .types import Entity, PIIType

__version__ = "0.3.0"

__all__ = [
    "MODES",
    "AnonymizationResult",
    "Entity",
    "PIIType",
    "PseudonymTable",
    "__version__",
    "anonymize",
    "anonymize_detailed",
    "deanonymize",
    "detect",
]
