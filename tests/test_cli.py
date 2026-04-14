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

    _write_json(template_path, {"meta": {"version": "v1"}, "user": {"id": 1}})
    _write_json(samples_dir / "a.json", {"meta": {"version": "v1"}, "user": {"id": 1}})
    _write_json(samples_dir / "b.json", {"meta": {"version": "v1"}})

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
    assert "Field Path" in result.output
    assert "meta.version" in result.output
    assert "CONSTANT" in result.output


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

