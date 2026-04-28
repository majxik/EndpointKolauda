import json
from pathlib import Path

from kolauda.core.engine import IssueStatus
from kolauda.ui.app import build_audit_rows, compute_dashboard_metrics, run_audit


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


