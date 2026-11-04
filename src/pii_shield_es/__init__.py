"""pii-shield-es: detección y anonimización 100 % local de datos personales en español."""

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

__version__ = "0.2.0"

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
