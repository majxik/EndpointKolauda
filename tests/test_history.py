import json
from pathlib import Path

from kolauda.core.history import (
    load_history_entries,
    load_history_entry,
    save_history_entry,
    validate_history_entry,
)


def _entry(audit_id: str, timestamp: str) -> dict:
    return {
        "schema_version": 1,
        "audit_id": audit_id,
        "timestamp_utc": timestamp,
        "inputs": {
            "template_path": "template.json",
            "samples_path": "samples",
            "sample_files": ["a.json"],
        },
        "metrics": {
            "total_files": 1,
            "total_errors": 2,
            "healthy_fields_percent": 50.0,
        },
        "template_payload": {"ok": True},
        "sample_payloads": {"a.json": {"ok": True}},
        "audit_rows": [{"Field Path": "ok", "Status": "OK"}],
        "field_details_by_path": {
            "ok": {
                "path": "ok",
                "status": "OK",
                "presence_percent": 100.0,
                "null_percent": 0.0,
                "unique_values": 1,
                "observed_types": "bool",
            }
        },
    }


def test_history_save_and_load_round_trip(tmp_path: Path) -> None:
    history_dir = tmp_path / ".kolauda" / "history"
    entry = _entry("abc123", "2026-04-29T10:00:00+00:00")

    saved_path = save_history_entry(entry, history_dir)
    loaded = load_history_entry(saved_path)

    assert saved_path.exists()
    assert loaded["audit_id"] == "abc123"
    assert loaded["metrics"]["total_errors"] == 2


def test_history_load_entries_sorts_by_timestamp_and_skips_invalid(tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    save_history_entry(_entry("new", "2026-04-29T11:00:00+00:00"), history_dir)
    save_history_entry(_entry("old", "2026-04-29T09:00:00+00:00"), history_dir)

    invalid = history_dir / "broken.json"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_text("{not json}", encoding="utf-8")

    entries = load_history_entries(history_dir)

    assert [entry["audit_id"] for entry in entries] == ["old", "new"]


def test_history_validate_requires_schema_keys() -> None:
    payload = {"audit_id": "missing-fields"}

    try:
        validate_history_entry(payload)
        assert False, "Expected ValueError for invalid payload"
    except ValueError as error:
        assert "missing keys" in str(error)


def test_history_load_entry_reports_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"

    try:
        load_history_entry(missing)
        assert False, "Expected ValueError for missing file"
    except ValueError as error:
        assert "not found" in str(error)


def test_history_file_is_json_serializable(tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    entry = _entry("serial", "2026-04-29T12:00:00+00:00")

    saved_path = save_history_entry(entry, history_dir)
    parsed = json.loads(saved_path.read_text(encoding="utf-8"))

    assert parsed["schema_version"] == 1
    assert parsed["sample_payloads"]["a.json"]["ok"] is True

