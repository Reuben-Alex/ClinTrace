"""Extract structured fields from CLINTRACE audit report text."""

from __future__ import annotations

import re


def _audit_field(report: str, pattern: str) -> str | None:
    match = re.search(pattern, report, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value and value.upper() != "N/A" else None


def extract_esi_from_report(report: str) -> int | None:
    """Extract ESI level (1-5) from audit report text."""
    field = _audit_field(report, r"•\s*ESI Level:\s*(\d)")
    if field:
        level = int(field)
        return level if 1 <= level <= 5 else None
    patterns = [
        r"ESI\s*Level:\s*(\d)",
        r"esi_level[\"']?\s*:\s*(\d)",
        r"ESI-(\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, report, re.IGNORECASE)
        if match:
            level = int(match.group(1))
            if 1 <= level <= 5:
                return level
    return None


def extract_confidence_from_report(report: str) -> float | None:
    """Extract model confidence from audit report (0.0-1.0)."""
    field = _audit_field(
        report,
        r"•\s*ESI Level:\s*\d+\s*\(Confidence:\s*(\d+)%\)",
    )
    if field:
        return int(field) / 100.0
    match = re.search(
        r"Confidence:\s*(\d+)%",
        report,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)) / 100.0
    return None


def extract_destination_from_report(report: str) -> str | None:
    """Extract routing destination from audit report."""
    return _audit_field(report, r"•\s*Destination:\s*([^\n]+)")


def extract_priority_from_report(report: str) -> str | None:
    """Extract routing priority from audit report."""
    return _audit_field(
        report,
        r"•\s*Priority:\s*([^\n]+)",
    )
