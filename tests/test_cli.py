import json
from pathlib import Path

from typer.testing import CliRunner

from kolauda.cli.main import app

runner = CliRunner()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_cli_audit_renders_table_output(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()

    _write_json(template_path, {"meta": {"version": "v1"}, "user": {"id": 1, "role": "x"}})
    _write_json(
        samples_dir / "a.json",
        {"meta": {"version": "v1"}, "user": {"id": 1, "role": "admin", "extra": True}},
    )
    _write_json(samples_dir / "b.json", {"meta": {"version": "v1"}, "user": {"id": "one"}})

    result = runner.invoke(
        app,
        [
            "audit",
            "--template",
            str(template_path),
            "--samples",
            str(samples_dir / "*.json"),
        ],
    )

    assert result.exit_code == 0
    assert "Audited Files (2): [a.json, b.json]" in result.output
    assert "Field Path" in result.output
    assert "meta.version" in result.output
    assert "Issue Log" in result.output
    assert "MISSING" in result.output
    assert "EXTRA" in result.output
    assert "TYPE_MISMATCH" in result.output
    assert "EXTRA, OPTIONAL?" in result.output
    assert "OPTIONAL?" in result.output
    assert "TYPE_DRIFT" in result.output
    assert result.output.index("user.extra") < result.output.index("user.id")
    assert result.output.index("user.id") < result.output.index("user.role")


def test_cli_audit_handles_invalid_json(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    sample_path = tmp_path / "sample.json"

    _write_json(template_path, {"meta": {"version": "v1"}})
    sample_path.write_text("{broken-json", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "audit",
            "--template",
            str(template_path),
            "--samples",
            str(sample_path),
        ],
    )

    assert result.exit_code == 1
    assert "Invalid JSON" in result.output


def test_cli_issue_log_groups_duplicate_missing_rows(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()

    _write_json(template_path, {"items": [{"currency": "CZK"}]})
    _write_json(
        samples_dir / "a.json",
        {"items": [{"id": 1}, {"id": 2}, {"id": 3}]},
    )

    result = runner.invoke(
        app,
        [
            "audit",
            "--template",
            str(template_path),
            "--samples",
            str(samples_dir),
        ],
    )

    assert result.exit_code == 0
    assert "items.[].currency" in result.output
    assert "<missing> (x3)" in result.output
    assert "MISSING" in result.output
    assert "OPTIONAL?" not in result.output


def test_cli_main_status_marks_nullable_without_type_drift(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()

    _write_json(template_path, {"offer": {"discount": 10}})
    _write_json(samples_dir / "a.json", {"offer": {"discount": 5}})
    _write_json(samples_dir / "b.json", {"offer": {"discount": None}})

    result = runner.invoke(
        app,
        [
            "audit",
            "--template",
            str(template_path),
            "--samples",
            str(samples_dir),
        ],
    )

    assert result.exit_code == 0
    assert "offer.discount" in result.output
    assert "NULLABLE" in result.output
    assert "TYPE_DRIFT, NULLABLE" not in result.output


def test_cli_main_table_covers_all_status_labels(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()

    _write_json(
        template_path,
        {
            "missing_only": 1,
            "optional_field": 1,
            "nullable_field": 1,
            "always_null_field": 1,
            "drift_field": 1,
            "constant_field": "v1",
            "ok_field": 0,
        },
    )
    _write_json(
        samples_dir / "a.json",
        {
            "optional_field": 1,
            "nullable_field": None,
            "always_null_field": None,
            "drift_field": 1,
            "constant_field": "v1",
            "ok_field": 1,
            "extra_field": True,
        },
    )
    _write_json(
        samples_dir / "b.json",
        {
            "nullable_field": 2,
            "always_null_field": None,
            "drift_field": "x",
            "constant_field": "v1",
            "ok_field": 2,
        },
    )

    result = runner.invoke(
        app,
        [
            "audit",
            "--template",
            str(template_path),
            "--samples",
            str(samples_dir),
        ],
    )

    assert result.exit_code == 0
    assert "MISSING" in result.output
    assert "EXTRA" in result.output
    assert "TYPE_DRIFT" in result.output
    assert "NULLABLE" in result.output
    assert "ALWAYS_NULL" in result.output
    assert "OPTIONAL?" in result.output
    assert "CONSTANT" in result.output
    assert "OK" in result.output


