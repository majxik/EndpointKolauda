"""Streamlit dashboard for EndpointKolauda audits."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kolauda.cli.main import (
    _collect_issue_statuses_by_path,
    _load_json_file,
    _resolve_sample_files,
    _status_for_path,
)
from kolauda.core.auditor import AuditReport, KolaudaAuditor
from kolauda.core.engine import IssueStatus, Observation, ResponseComparator


@dataclass(frozen=True)
class DashboardMetrics:
    """High-level numbers shown in the dashboard header."""

    total_files: int
    total_errors: int
    healthy_fields_percent: float


def run_audit(template: Path, samples: str) -> tuple[AuditReport, list[Observation], list[Path]]:
    """Execute the standard audit flow and return report data for the UI."""
    template_data = _load_json_file(template)
    sample_files = _resolve_sample_files(samples, template_path=template)

    comparator = ResponseComparator()
    observations_by_response: list[list[Observation]] = []
    for sample_file in sample_files:
        sample_data = _load_json_file(sample_file)
        observations_by_response.append(
            comparator.compare(
                template_data,
                sample_data,
                source_filename=sample_file.name,
            )
        )

    report = KolaudaAuditor(observations_by_response).generate_report()
    all_observations = [obs for response in observations_by_response for obs in response]
    return report, all_observations, sample_files


def compute_dashboard_metrics(
    report: AuditReport,
    observations: list[Observation],
    issue_statuses_by_path: dict[str, set[IssueStatus]],
    total_files: int,
) -> DashboardMetrics:
    """Compute headline metrics displayed above the audit table."""
    tracked_statuses = {IssueStatus.MISSING, IssueStatus.EXTRA, IssueStatus.TYPE_MISMATCH}
    total_errors = sum(1 for observation in observations if observation.status in tracked_statuses)

    healthy_fields = 0
    for path, path_report in report.by_path.items():
        status, _ = _status_for_path(path_report, issue_statuses_by_path.get(path))
        if status == "OK":
            healthy_fields += 1

    healthy_fields_percent = (
        (healthy_fields / len(report.by_path) * 100.0)
        if report.by_path
        else 0.0
    )
    return DashboardMetrics(
        total_files=total_files,
        total_errors=total_errors,
        healthy_fields_percent=healthy_fields_percent,
    )


def build_audit_rows(
    report: AuditReport,
    issue_statuses_by_path: dict[str, set[IssueStatus]],
) -> list[dict[str, Any]]:
    """Build row objects for st.dataframe from the audit report."""
    rows: list[dict[str, Any]] = []
    for path, path_report in sorted(report.by_path.items()):
        status, _ = _status_for_path(path_report, issue_statuses_by_path.get(path))
        rows.append(
            {
                "Field Path": path,
                "Presence %": round(path_report.presence_rate * 100.0, 1),
                "Null %": round(path_report.null_rate * 100.0, 1),
                "Unique Vals": len(path_report.field_audit.unique_values),
                "Status": status,
            }
        )
    return rows


def load_sample_json(path: Path) -> Any:
    """Load one sample JSON document for the explorer panel."""
    return _load_json_file(path)


def main() -> None:
    """Run the Streamlit dashboard app."""
    import streamlit as st

    st.set_page_config(page_title="EndpointKolauda", page_icon="K", layout="wide")
    st.title("EndpointKolauda Dashboard")

    with st.sidebar:
        st.header("Inputs")
        template_path_input = st.text_input("Template File Path", value="examples/template.json")
        samples_path_input = st.text_input("Samples Directory Path", value="examples/samples")
        run_clicked = st.button("Run Kolauda", type="primary", use_container_width=True)

    if "last_result" not in st.session_state:
        st.session_state.last_result = None

    if run_clicked:
        try:
            report, observations, sample_files = run_audit(
                template=Path(template_path_input),
                samples=samples_path_input,
            )
            issue_statuses_by_path = _collect_issue_statuses_by_path(observations)
            metrics = compute_dashboard_metrics(
                report=report,
                observations=observations,
                issue_statuses_by_path=issue_statuses_by_path,
                total_files=len(sample_files),
            )
            st.session_state.last_result = {
                "report": report,
                "observations": observations,
                "issue_statuses_by_path": issue_statuses_by_path,
                "sample_files": sample_files,
                "metrics": metrics,
            }
        except ValueError as error:
            st.error(str(error))

    if st.session_state.last_result is None:
        st.info("Pick input paths in the sidebar and click 'Run Kolauda'.")
        return

    result = st.session_state.last_result
    report: AuditReport = result["report"]
    issue_statuses_by_path: dict[str, set[IssueStatus]] = result["issue_statuses_by_path"]
    sample_files: list[Path] = result["sample_files"]
    metrics: DashboardMetrics = result["metrics"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Files", metrics.total_files)
    col2.metric("Total Errors", metrics.total_errors)
    col3.metric("Healthy Fields %", f"{metrics.healthy_fields_percent:.1f}%")

    st.subheader("Audit Table")
    st.dataframe(build_audit_rows(report, issue_statuses_by_path), use_container_width=True)

    st.subheader("JSON Explorer")
    selected_sample = st.selectbox("Select sample file", options=sample_files, format_func=lambda p: p.name)
    try:
        sample_payload = load_sample_json(selected_sample)
        st.code(json.dumps(sample_payload, indent=2), language="json")
    except ValueError as error:
        st.error(str(error))


if __name__ == "__main__":
    main()

