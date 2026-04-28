import json
from pathlib import Path

from kolauda.core.engine import IssueStatus
from kolauda.ui.app import (
    build_audit_rows,
    build_diff_rows,
    build_field_details,
    build_sample_file_map,
    compute_dashboard_metrics,
    list_picker_entries,
    minimal_plus_tab_labels,
    resolve_base_directory,
    resolve_json_source,
    run_audit,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_ui_run_audit_builds_report_and_observations(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()

    _write_json(template_path, {"user": {"id": 1, "email": "x@example.com"}})
    _write_json(samples_dir / "a.json", {"user": {"id": 1, "email": "x@example.com"}})
    _write_json(samples_dir / "b.json", {"user": {"id": "one"}})

    report, observations, sample_files = run_audit(template=template_path, samples=str(samples_dir))

    assert len(sample_files) == 2
    assert report.total_responses == 2
    assert "user.id" in report.by_path
    assert any(obs.status == IssueStatus.TYPE_MISMATCH for obs in observations)


def test_ui_metrics_and_rows_include_expected_values(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()

    _write_json(template_path, {"offer": {"discount": 10, "currency": "CZK"}})
    _write_json(samples_dir / "a.json", {"offer": {"discount": None, "currency": "CZK"}})
    _write_json(samples_dir / "b.json", {"offer": {"currency": "CZK", "extra": True}})

    report, observations, sample_files = run_audit(template=template_path, samples=str(samples_dir))
    issue_statuses_by_path: dict[str, set[IssueStatus]] = {}
    for observation in observations:
        if observation.status not in {
            IssueStatus.MISSING,
            IssueStatus.EXTRA,
            IssueStatus.TYPE_MISMATCH,
        }:
            continue
        issue_statuses_by_path.setdefault(observation.path, set()).add(observation.status)

    metrics = compute_dashboard_metrics(
        report=report,
        observations=observations,
        issue_statuses_by_path=issue_statuses_by_path,
        total_files=len(sample_files),
    )
    rows = build_audit_rows(report, issue_statuses_by_path)

    assert metrics.total_files == 2
    assert metrics.total_errors == 2
    assert any(row["Status"] == "ALWAYS_NULL, OPTIONAL?" for row in rows)
    assert any("EXTRA" in row["Status"] for row in rows)


def test_ui_resolve_json_source_supports_template_and_sample(tmp_path: Path) -> None:
    sample_path = tmp_path / "response.json"
    _write_json(sample_path, {"ok": True})

    sample_map = build_sample_file_map([sample_path])
    template_payload = {"template": True}

    template_label, template_data = resolve_json_source("Template", template_payload, sample_map)
    sample_label, sample_data = resolve_json_source("response.json", template_payload, sample_map)

    assert template_label == "Template"
    assert template_data == {"template": True}
    assert sample_label == "response.json"
    assert sample_data == {"ok": True}


def test_ui_build_diff_rows_detects_missing_and_extra_paths() -> None:
    left_payload = {"product": {"id": 1, "name": "A"}}
    right_payload = {"product": {"id": 1, "extra": True}}

    diff_rows = build_diff_rows(left_payload, right_payload, "right.json")

    paths_by_type = {(row["Issue Type"], row["Field Path"]) for row in diff_rows}
    assert ("MISSING", "product.name") in paths_by_type
    assert ("EXTRA", "product.extra") in paths_by_type


def test_ui_build_field_details_exposes_audit_statistics(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    samples_dir = tmp_path / "samples"
    samples_dir.mkdir()

    _write_json(template_path, {"offer": {"discount": 10}})
    _write_json(samples_dir / "a.json", {"offer": {"discount": None}})
    _write_json(samples_dir / "b.json", {"offer": {"discount": 5}})

    report, observations, _ = run_audit(template=template_path, samples=str(samples_dir))
    issue_statuses_by_path: dict[str, set[IssueStatus]] = {}
    for observation in observations:
        if observation.status not in {
            IssueStatus.MISSING,
            IssueStatus.EXTRA,
            IssueStatus.TYPE_MISMATCH,
        }:
            continue
        issue_statuses_by_path.setdefault(observation.path, set()).add(observation.status)

    details = build_field_details("offer.discount", report, issue_statuses_by_path)

    assert details is not None
    assert details.status == "NULLABLE, CONSTANT"
    assert details.presence_percent == 100.0
    assert details.null_percent == 50.0


def test_ui_minimal_plus_tab_labels_match_expected_order() -> None:
    assert minimal_plus_tab_labels() == ("Overview", "Diff", "Raw JSON", "History")


def test_ui_resolve_base_directory_returns_existing_dir(tmp_path: Path) -> None:
    resolved = resolve_base_directory(str(tmp_path))
    assert resolved == tmp_path.resolve()


def test_ui_resolve_base_directory_falls_back_when_missing() -> None:
    missing = "Z:/this/path/should/not/exist/for/kolauda"
    resolved = resolve_base_directory(missing)
    assert resolved == Path.cwd().resolve()


def test_ui_list_picker_entries_returns_dirs_and_json_only(tmp_path: Path) -> None:
    subdir = tmp_path / "samples"
    subdir.mkdir()
    _write_json(tmp_path / "template.json", {"ok": True})
    (tmp_path / "notes.txt").write_text("skip", encoding="utf-8")

    directories, json_files = list_picker_entries(tmp_path)

    assert [directory.name for directory in directories] == ["samples"]
    assert [json_file.name for json_file in json_files] == ["template.json"]


