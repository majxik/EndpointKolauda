"""Persistence helpers for saving and loading UI audit history snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HISTORY_SCHEMA_VERSION = 2


def _infer_endpoint_key(inputs: dict[str, Any]) -> str:
    """Infer endpoint key from inputs when metadata is missing in older snapshots."""
    samples_path = str(inputs.get("samples_path", "")).strip()
    if not samples_path:
        return "unknown"
    return Path(samples_path).name or "unknown"


def validate_history_entry(entry: Any) -> dict[str, Any]:
    """Validate one history entry payload and return it when schema is usable."""
    if not isinstance(entry, dict):
        raise ValueError("History entry must be a JSON object.")

    required_top_level = {
        "schema_version",
        "audit_id",
        "timestamp_utc",
        "inputs",
        "metrics",
        "template_payload",
        "sample_payloads",
        "audit_rows",
        "field_details_by_path",
    }
    missing_top_level = sorted(required_top_level - set(entry.keys()))
    if missing_top_level:
        raise ValueError(f"History entry is missing keys: {', '.join(missing_top_level)}")

    schema_version = int(entry["schema_version"])
    if schema_version not in {1, HISTORY_SCHEMA_VERSION}:
        raise ValueError(
            f"Unsupported history schema version: {schema_version} "
            f"(supported: 1, {HISTORY_SCHEMA_VERSION})"
        )

    if not isinstance(entry["inputs"], dict):
        raise ValueError("History entry 'inputs' must be an object.")
    if not isinstance(entry["metrics"], dict):
        raise ValueError("History entry 'metrics' must be an object.")
    if not isinstance(entry["sample_payloads"], dict):
        raise ValueError("History entry 'sample_payloads' must be an object.")
    if not isinstance(entry["audit_rows"], list):
        raise ValueError("History entry 'audit_rows' must be an array.")
    if not isinstance(entry["field_details_by_path"], dict):
        raise ValueError("History entry 'field_details_by_path' must be an object.")

    metadata = entry.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("History entry 'metadata' must be an object when provided.")

    normalized_metadata = {
        "endpoint_key": str(metadata.get("endpoint_key") or _infer_endpoint_key(entry["inputs"])),
        "endpoint_label": str(metadata.get("endpoint_label") or ""),
        "environment": str(metadata.get("environment") or ""),
        "notes": str(metadata.get("notes") or ""),
    }
    entry["metadata"] = normalized_metadata
    entry["schema_version"] = HISTORY_SCHEMA_VERSION

    return entry


def save_history_entry(entry: dict[str, Any], history_dir: Path) -> Path:
    """Persist one validated history entry to disk as a JSON file."""
    validated = validate_history_entry(entry)
    history_dir.mkdir(parents=True, exist_ok=True)

    timestamp_slug = str(validated["timestamp_utc"]).replace(":", "-")
    filename = f"{timestamp_slug}_{validated['audit_id']}.json"
    destination = history_dir / filename
    destination.write_text(json.dumps(validated, indent=2), encoding="utf-8")
    return destination


def load_history_entry(path: Path) -> dict[str, Any]:
    """Load and validate one history JSON file from disk."""
    if not path.exists() or not path.is_file():
        raise ValueError(f"History file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid history JSON in {path}: {error.msg}") from error

    return validate_history_entry(payload)


def load_history_entries(history_dir: Path) -> list[dict[str, Any]]:
    """Load all valid history entries from a directory, sorted by timestamp."""
    if not history_dir.exists() or not history_dir.is_dir():
        return []

    loaded: list[dict[str, Any]] = []
    for file_path in sorted(history_dir.glob("*.json")):
        try:
            loaded.append(load_history_entry(file_path))
        except ValueError:
            continue

    loaded.sort(key=lambda entry: str(entry.get("timestamp_utc", "")))
    return loaded

